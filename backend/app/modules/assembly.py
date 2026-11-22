"""조립 엔진: 부품(템플릿)들을 연결 지점끼리 이어 하나의 형상으로 만든다.

좌표: 뿌리 부품의 build() 좌표계. 자식은 부모 연결 지점에 '마주 보게' 붙는다.
  자식 연결 지점의 법선이 부모 법선과 반대 방향, 위쪽(up)이 같은 방향이 되도록 돌린 뒤
  부모 연결 지점 + 면 위 이동(shift·lift) 자리로 옮기고, 맞닿는 면이 확실히 붙도록 OVERLAP 만큼 파묻는다.
통로 연결(passage)은 자식 통로의 단면 기둥으로 부모 벽을 뚫는다.

형상 커널(build123d)은 build_assembly 에서만 쓴다. 배치 계산(place_parts)과 특징 합치기(merge_features)는
연결 지점 좌표만으로 하므로 형상을 만들지 않고도 출입 면·출입구 수를 알 수 있다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.templates.base import Anchor, Features, Opening, Side, Template, TemplateParams

# 맞닿는 면을 확실히 하나로 합치려고 자식을 부모 쪽으로 파묻는 깊이 mm
OVERLAP_MM = 0.3

_SIDE_VEC: dict[str, tuple[float, float, float]] = {
    "front": (0, -1, 0), "back": (0, 1, 0), "left": (-1, 0, 0), "right": (1, 0, 0),
}


@dataclass(frozen=True)
class PartSpec:
    id: str
    template: Template
    params: TemplateParams


@dataclass(frozen=True)
class JoinSpec:
    parent: str
    parent_anchor: str
    child: str
    child_anchor: str
    shift: float = 0.0
    lift: float = 0.0
    spin: int = 0
    passage: bool = False


@dataclass(frozen=True)
class PlacedPart:
    spec: PartSpec
    rotation: np.ndarray  # 3x3, 부품 좌표 → 조립 좌표
    translation: np.ndarray  # 3

    def point(self, p) -> np.ndarray:  # noqa: ANN001
        return self.rotation @ np.asarray(p, dtype=float) + self.translation

    def vector(self, v) -> np.ndarray:  # noqa: ANN001
        return self.rotation @ np.asarray(v, dtype=float)


class AssemblyError(ValueError):
    """조립 설계도가 잘못됨 (없는 연결 지점, 맞지 않는 방향 등). 메시지는 한국어."""


def _axis(v) -> np.ndarray:  # noqa: ANN001
    a = np.asarray(v, dtype=float)
    n = np.linalg.norm(a)
    if n < 1e-9:
        raise AssemblyError("연결 지점 방향이 0 입니다")
    return a / n


def _rot_about(axis: np.ndarray, deg: int) -> np.ndarray:
    a = math.radians(deg)
    c, s = round(math.cos(a), 12), round(math.sin(a), 12)
    x, y, z = axis
    return np.array([
        [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
        [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
        [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
    ])


def _frame(a: Anchor) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(기준점, 가로 t, 위 u, 법선 n). t = u × n: 면을 바깥에서 볼 때 오른쪽."""
    n, u = _axis(a.normal), _axis(a.up)
    if abs(float(n @ u)) > 1e-6:
        raise AssemblyError("연결 지점의 법선과 위쪽이 수직이 아닙니다")
    return np.asarray(a.origin, dtype=float), np.cross(u, n), u, n


def _anchor(part: PartSpec, name: str) -> Anchor:
    a = part.template.anchors(part.params).get(name)
    if a is None:
        raise AssemblyError(f"{part.template.display_name_ko}({part.id})에 연결 지점 '{name}'이(가) 없습니다")
    return a


def place_parts(parts: list[PartSpec], joins: list[JoinSpec]) -> dict[str, PlacedPart]:
    """뿌리(첫 부품)부터 연결을 따라 각 부품의 회전·이동을 정한다."""
    by_id = {p.id: p for p in parts}
    placed: dict[str, PlacedPart] = {parts[0].id: PlacedPart(parts[0], np.eye(3), np.zeros(3))}
    pending = list(joins)
    while pending:
        progressed = False
        for j in list(pending):
            if j.parent not in placed:
                continue
            parent = placed[j.parent]
            child = by_id[j.child]
            pa, ta, ua, na = _frame(_anchor(parent.spec, j.parent_anchor))
            pb, tb, ub, nb = _frame(_anchor(child, j.child_anchor))
            # 부모 연결 지점을 조립 좌표로
            pa, ta, ua, na = parent.point(pa), parent.vector(ta), parent.vector(ua), parent.vector(na)
            # 자식 좌표틀 [tb ub nb] → 원하는 좌표틀 [-ta ua -na] (마주 보기), 그다음 법선 둘레로 spin
            want = np.column_stack([-ta, ua, -na])
            have = np.column_stack([tb, ub, nb])
            rot = _rot_about(na, j.spin) @ want @ have.T
            rot = np.round(rot, 12)
            target = pa - na * OVERLAP_MM + ta * j.shift + ua * j.lift
            placed[j.child] = PlacedPart(child, rot, target - rot @ pb)
            pending.remove(j)
            progressed = True
        if not progressed:
            raise AssemblyError("뿌리 부품에서 이어지지 않는 연결이 있습니다")
    return placed


def _plane(part: PlacedPart):  # noqa: ANN202
    from build123d import Location, Plane

    r, t = part.rotation, part.translation
    return Location(Plane(origin=tuple(t), x_dir=tuple(r[:, 0]), z_dir=tuple(r[:, 2])))


def build_assembly(parts: list[PartSpec], joins: list[JoinSpec]):  # noqa: ANN201 (build123d Part)
    """부품을 만들어 제자리에 놓고 하나로 합친 뒤, 통로 연결 자리를 뚫는다."""
    placed = place_parts(parts, joins)
    if parts[0].template.cutter:
        raise AssemblyError("기준(첫) 부품은 빼는 모양(창문 등)일 수 없습니다")
    shape = None
    for p in parts:
        if p.template.cutter:
            continue
        solid = _plane(placed[p.id]) * p.template.build(p.params)
        shape = solid if shape is None else shape + solid
    for p in parts:
        if p.template.cutter:
            shape = shape - _plane(placed[p.id]) * p.template.build(p.params)
    for j in joins:
        if not j.passage:
            continue
        parent, child = placed[j.parent], placed[j.child]
        pa = _anchor(parent.spec, j.parent_anchor)
        if pa.wall_mm is None:
            raise AssemblyError(f"{parent.spec.template.display_name_ko}의 '{j.parent_anchor}' 면은 뚫을 수 없습니다")
        cutter = child.spec.template.port_cutter(child.spec.params, j.child_anchor, pa.wall_mm + OVERLAP_MM + 1.0)
        if cutter is None:
            raise AssemblyError(f"{child.spec.template.display_name_ko}의 '{j.child_anchor}'은(는) 통로가 아닙니다")
        shape = shape - _plane(child) * cutter
    return shape


def _side_of(v: np.ndarray) -> Side | None:
    for name, s in _SIDE_VEC.items():
        if float(np.dot(v, s)) > 0.99:
            return name  # type: ignore[return-value]
    return None


def merge_features(parts: list[PartSpec], joins: list[JoinSpec], enclosure: bool) -> Features:
    """부품 특징을 조립 하나의 특징으로 합친다 (형상 없이 연결 지점 좌표만으로)."""
    placed = place_parts(parts, joins)
    used: dict[str, set[str]] = {p.id: set() for p in parts}
    for j in joins:
        used[j.parent].add(j.parent_anchor)
        used[j.child].add(j.child_anchor)
    openings: list[Opening] = []
    sides: list[Side] = []
    exits = 0
    walls: list[float] = []
    climb = slope = step = None
    for p in parts:
        f = p.template.features(p.params)
        anchors = p.template.anchors(p.params)
        walls.append(f.min_wall_thickness_mm)
        openings.extend(f.openings)
        joined_sides = {a.side for n, a in anchors.items() if n in used[p.id] and a.side}
        for s in f.access_sides:
            if s in joined_sides:
                continue
            world = _side_of(placed[p.id].vector(_SIDE_VEC[s]))
            if world and world not in sides:
                sides.append(world)
        exits += sum(1 for n, a in anchors.items() if a.port is not None and n not in used[p.id])
        if f.climb_height_mm is not None:
            climb = max(climb or 0.0, f.climb_height_mm)
        if f.slope_deg is not None:
            slope = max(slope or 0.0, f.slope_deg)
        if f.step_height_mm is not None:
            step = max(step or 0.0, f.step_height_mm)
    return Features(
        min_wall_thickness_mm=min(walls),
        openings=tuple(openings),
        access_sides=tuple(sides),
        climb_height_mm=climb,
        slope_deg=slope,
        step_height_mm=step,
        entrance_count=exits if enclosure else None,
        extra={"parts": [p.id for p in parts]},
    )


def join_problems(parts: list[PartSpec], joins: list[JoinSpec]) -> list[str]:
    """형상 없이 알 수 있는 조립 규칙 위반 (한국어 문구)."""
    out: list[str] = []
    by_id = {p.id: p for p in parts}
    for j in joins:
        for pid, name, other in ((j.parent, j.parent_anchor, j.child), (j.child, j.child_anchor, j.parent)):
            a = by_id[pid].template.anchors(by_id[pid].params).get(name)
            if a is None:
                out.append(f"{by_id[pid].template.display_name_ko}에 연결 지점 '{name}'이(가) 없습니다")
            elif a.port is not None and not j.passage:
                # 출입구·터널 끝을 다른 부품으로 막으면 드나들 수 없다
                out.append(f"{by_id[pid].template.display_name_ko}의 출입구를 "
                           f"{by_id[other].template.display_name_ko}이(가) 막습니다")
        if j.passage:
            cp = by_id[j.child].template.anchors(by_id[j.child].params).get(j.child_anchor)
            pp = by_id[j.parent].template.anchors(by_id[j.parent].params).get(j.parent_anchor)
            if cp is not None and cp.port is None:
                out.append(f"{by_id[j.child].template.display_name_ko}의 '{j.child_anchor}'은(는) 통로가 아닙니다")
            if pp is not None and pp.wall_mm is None:
                out.append(f"{by_id[j.parent].template.display_name_ko}의 '{j.parent_anchor}' 면은 뚫을 수 없습니다")
    return out


def internal_gaps(parts: list[PartSpec], joins: list[JoinSpec], shape_bounds: dict[str, tuple]) -> list[tuple[str, str, float]]:
    """서로 잇지 않은 부품 쌍 사이의 틈 (축 정렬 상자 사이 거리). 끼임 틈 검사에 쓴다."""
    joined = {frozenset((j.parent, j.child)) for j in joins}
    out = []
    ids = [p.id for p in parts]
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if frozenset((a, b)) in joined:
                continue
            (alo, ahi), (blo, bhi) = shape_bounds[a], shape_bounds[b]
            gap = np.maximum(0.0, np.maximum(np.asarray(blo) - ahi, np.asarray(alo) - bhi))
            out.append((a, b, float(np.linalg.norm(gap))))
    return out
