"""조립 엔진: 부품(템플릿)들을 연결 지점끼리 이어 하나의 형상으로 만든다.

좌표: 뿌리 부품의 build() 좌표계. 자식은 부모 연결 지점에 '마주 보게' 붙는다.
  자식 연결 지점의 법선이 부모 법선과 반대 방향, 위쪽(up)이 같은 방향이 되도록 돌린 뒤
  부모 연결 지점 + 면 위 이동(shift·lift) 자리로 옮기고, 맞닿는 면이 확실히 붙도록 OVERLAP 만큼 파묻는다.
통로 연결(passage)은 자식 통로의 단면 기둥으로 부모 벽을 뚫는다.
슬라이드 결합(mount="slide")은 한 덩어리로 출력할 수 없는 부품(은신처 옆 그릇 받침 등)을 따로 출력해 끼우는 방식이다:
  부모 면에 두께 PLATE_MM 의 연결판을 붙이고 자식은 연결판 바깥에 놓는다. 조립 형상(build)은 부모 ∪ 연결판 ∪ 자식의
  한 덩어리이고, 출력 파트에서만 연결판에 세로 도브테일 홈을, 자식 뒷면에 틈새를 둔 도브테일 혀를 낸다
  (자식을 위에서 밀어 내리면 끼워지고, 옆으로는 빠지지 않는다).

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

# ── 슬라이드 결합 ──
# 연결판 두께. 자식이 연결판보다 높으면 연결판 위로 벽과 자식 뒷면 사이에 PLATE_MM − OVERLAP_MM(3.7mm) 틈이 남는다:
# 가장 작은 햄스터 끼임 안전 틈(4mm)보다 작게 둔다 (종별 기준을 넘으면 규칙 오류)
PLATE_MM = 4.0
SLIDE_CLEARANCE_MM = 0.25      # 도브테일 혀와 홈 사이 틈새 (한쪽)
DOVETAIL_DEPTH_MM = PLATE_MM - OVERLAP_MM - 1.0  # 홈 깊이: 연결판 뒤(벽 쪽)에 1mm 를 남긴다
DOVETAIL_NECK_MM = 10.0        # 홈 입구 폭 (연결판 바깥면)
DOVETAIL_ANGLE_DEG = 20.0      # 홈 옆면이 법선에서 벌어지는 각도 (안쪽이 넓다). 혀가 옆으로 물리는 폭 ≈ 0.6mm
DOVETAIL_PITCH_MM = 100.0      # 이 폭마다 도브테일 하나 (뾰족한 혀 모서리가 많으면 얇은 곳으로 재진다)
DOVETAIL_MARGIN_MM = 3.0       # 도브테일과 자식 뒷면 가장자리 사이 최소 여유
DOVETAIL_MIN_LENGTH_MM = 10.0  # 혀의 최소 세로 길이
# 연결판·혀 끝을 출력 자세에서 아래를 보지 않게 깎는 경사: 세로 ÷ 가로 (1.2 → 수평에서 약 50°, 오버행 40°)
SLOPE_RISE = 1.2

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
    mount: str = "fused"  # "fused" | "slide"

    @property
    def slide(self) -> bool:
        return self.mount == "slide"


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
            # 슬라이드 결합: 자식 뒷면이 연결판 바깥면에 OVERLAP 만큼 묻히게 연결판 두께만큼 더 바깥에
            out = PLATE_MM - OVERLAP_MM if j.slide else -OVERLAP_MM
            target = pa + na * out + ta * j.shift + ua * j.lift
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
    """부품을 만들어 제자리에 놓고 하나로 합친 뒤(슬라이드 결합은 연결판까지), 통로 연결 자리를 뚫는다."""
    placed = place_parts(parts, joins)
    if parts[0].template.cutter:
        raise AssemblyError("기준(첫) 부품은 빼는 모양(창문 등)일 수 없습니다")
    shape = None
    solids: dict[str, object] = {}
    for p in parts:
        if p.template.cutter:
            continue
        solid = _plane(placed[p.id]) * p.template.build(p.params)
        solids[p.id] = solid
        shape = solid if shape is None else shape + solid
    for j in joins:
        if j.slide:
            plan = slide_plan(placed, j, _bounds(solids[j.parent]), _bounds(solids[j.child]))
            shape = shape + plate_solid(plan, for_print=False)
    for p in parts:
        if p.template.cutter:
            shape = shape - _plane(placed[p.id]) * p.template.build(p.params)
    for j in joins:
        if not j.passage:
            continue
        shape = shape - passage_cutter(placed, j)
    return shape


def passage_cutter(placed: dict[str, PlacedPart], j: JoinSpec, extra_mm: float = 1.0):  # noqa: ANN201
    """통로 연결(passage)에서 부모 벽을 뚫는 자식 통로 단면 기둥 (조립 좌표)."""
    parent, child = placed[j.parent], placed[j.child]
    pa = _anchor(parent.spec, j.parent_anchor)
    if pa.wall_mm is None:
        raise AssemblyError(f"{parent.spec.template.display_name_ko}의 '{j.parent_anchor}' 면은 뚫을 수 없습니다")
    cutter = child.spec.template.port_cutter(child.spec.params, j.child_anchor, pa.wall_mm + OVERLAP_MM + extra_mm)
    if cutter is None:
        raise AssemblyError(f"{child.spec.template.display_name_ko}의 '{j.child_anchor}'은(는) 통로가 아닙니다")
    return _plane(child) * cutter


def _bounds(shape) -> tuple[np.ndarray, np.ndarray]:  # noqa: ANN001
    bb = shape.bounding_box()
    return np.array([bb.min.X, bb.min.Y, bb.min.Z]), np.array([bb.max.X, bb.max.Y, bb.max.Z])


# ── 통로가 부모 개구부를 덮는지 ─────────────────────────────


def passage_leftover(placed: dict[str, PlacedPart], j: JoinSpec, child_solid=None):  # noqa: ANN001, ANN201
    """출입구·터널 끝(port 가 있는 부모 연결 지점)에 통로로 이은 자식이 그 개구부를 다 덮지 못하고 남긴 빈 곳 (조립 좌표).

    남은 곳 = 부모 개구부 단면 기둥(부모 면에서 바깥으로 부모 벽 두께만큼) − 자식 형상 − 자식 통로 단면 기둥.
    = 부모 개구부에서 자식 벽과 통로 밖으로 바깥이 보이는 곳 (바깥으로 뚫린 틈).
    자식 통로가 더 좁거나 모양이 다르면(뾰족 아치 출입구에 둥근 아치·관·네모 터널) 그 차이가 바깥으로 뚫린 틈이 된다.
    바닥(Z=0) 아래는 빼고 센다. 부모 연결 지점이 통로 자리가 아니면 None."""
    from build123d import Align, Box, Pos

    parent, child = placed[j.parent], placed[j.child]
    pa = _anchor(parent.spec, j.parent_anchor)
    if pa.port is None or pa.wall_mm is None:
        return None
    opening = parent.spec.template.port_cutter(parent.spec.params, j.parent_anchor, pa.wall_mm)
    if opening is None:
        return None
    # port_cutter 는 면 안쪽 0.5mm 에서 시작한다: 면 바깥(자식이 있는 쪽)만 보도록 0.5mm 밀어낸다.
    # 그래서 자식 벽이 개구부를 덮고 통로만 좁은 경우(벽 속에 막힌 턱이 남을 뿐 바깥으로 뚫리지 않는다)는 세지 않는다
    _, _, _, na = _frame(pa)
    opening = _plane(parent) * (Pos(*(na * 0.5)) * opening)
    if child_solid is None:
        child_solid = _plane(child) * child.spec.template.build(child.spec.params)
    # 자식 통로 기둥을 자식 쪽으로도 늘인다 (통로 끝 근처의 자식 통로 속 = 빈 곳이지만 통로다)
    depth = pa.wall_mm + 2.0
    bore = child.spec.template.port_cutter(child.spec.params, j.child_anchor, 2 * depth)
    if bore is None:
        return None
    _, _, _, nb = _frame(_anchor(child.spec, j.child_anchor))
    bore = _plane(child) * (Pos(*(-nb * depth)) * bore)
    left = opening - child_solid - bore
    if not left.solids():
        return left
    lo, hi = _bounds(opening)
    above_floor = Box(hi[0] - lo[0] + 2, hi[1] - lo[1] + 2, max(hi[2], 0.0) + 1.0,
                      align=(Align.CENTER, Align.CENTER, Align.MIN))
    return left & (Pos((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 0) * above_floor)


# ── 슬라이드 결합: 연결판·도브테일 ──────────────────────────


@dataclass(frozen=True)
class SlidePlan:
    """슬라이드 결합 하나의 연결판 자리 (조립 좌표). 면 좌표: t(가로, 바깥에서 볼 때 오른쪽), u(위), d(법선 바깥 방향).

    연결판은 t ∈ [t0, t1], u ∈ [0, h] 를 덮고, 자식보다 부모 면이 높으면 h 위로 벽 쪽으로 올라가는 경사(wedge)를
    top 까지 둔다 (출력 자세에서 연결판 윗면이 아래를 보지 않게, 자식 윗모서리와 벽 사이에 홈이 남지 않게).
    """

    join: JoinSpec
    origin: np.ndarray
    t: np.ndarray
    u: np.ndarray
    n: np.ndarray
    t0: float           # 연결판 가로 범위 = 자식 외곽 범위
    t1: float
    h: float            # 자식이 기대는 연결판 높이 = min(자식 높이, 붙일 수 있는 높이 (− 경사 높이))
    top: float          # 경사 포함 연결판 꼭대기 (h 이상, 붙일 수 있는 높이 이하)
    mount: tuple[float, float, float] | None  # 부모 면이 허락한 영역 (left, right, height)
    child_u: tuple[float, float]   # 자식 외곽의 위·아래 범위
    parent_u_top: float            # 부모 외곽의 꼭대기 (면 좌표 u)

    @property
    def face_d(self) -> float:
        """자식 뒷면(출력 파트의 연결판 바깥면) 위치 d."""
        return PLATE_MM - OVERLAP_MM

    def frame_point(self, t: float, u: float, d: float) -> np.ndarray:
        return self.origin + self.t * t + self.u * u + self.n * d


def anchor_frame(placed: dict[str, PlacedPart], part_id: str, name: str):  # noqa: ANN201
    """조립 좌표의 연결 지점 좌표틀 (기준점, t, u, n)."""
    pl = placed[part_id]
    o, t, u, n = _frame(_anchor(pl.spec, name))
    return pl.point(o), pl.vector(t), pl.vector(u), pl.vector(n)


def _project(lo: np.ndarray, hi: np.ndarray, o: np.ndarray, axis: np.ndarray) -> tuple[float, float]:
    """축 정렬 상자를 축 방향으로 투영한 범위 (기준점 o 기준)."""
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    v = (corners - o) @ axis
    return float(v.min()), float(v.max())


def slide_frame_ok(placed: dict[str, PlacedPart], j: JoinSpec) -> bool:
    """슬라이드 결합은 옆면끼리만: 부모 연결 면 법선이 수평이고 두 연결 지점의 위쪽이 +Z."""
    _, _, ua, na = anchor_frame(placed, j.parent, j.parent_anchor)
    _, _, ub, _ = anchor_frame(placed, j.child, j.child_anchor)
    z = np.array([0.0, 0.0, 1.0])
    return abs(float(na[2])) < 1e-6 and float(ua @ z) > 1 - 1e-6 and float(ub @ z) > 1 - 1e-6


def slide_plan(placed: dict[str, PlacedPart], j: JoinSpec, parent_bounds, child_bounds) -> SlidePlan:  # noqa: ANN001
    """연결판 자리. parent_bounds·child_bounds: 조립 좌표에 놓인 부모·자식 형상의 축 정렬 상자 (lo, hi)."""
    if not slide_frame_ok(placed, j):
        raise AssemblyError(f"{placed[j.parent].spec.template.display_name_ko}와(과) "
                            f"{placed[j.child].spec.template.display_name_ko}의 슬라이드 결합은 "
                            "옆면끼리만 할 수 있습니다 (세로 면, 위쪽이 위)")
    o, t, u, n = anchor_frame(placed, j.parent, j.parent_anchor)
    mount = _anchor(placed[j.parent].spec, j.parent_anchor).mount
    t0, t1 = _project(*child_bounds, o, t)
    cu = _project(*child_bounds, o, u)
    pu = _project(*parent_bounds, o, u)
    limit = mount[2] if mount is not None else pu[1]
    rise = SLOPE_RISE * (PLATE_MM - OVERLAP_MM)
    if limit >= pu[1] - 1e-6:
        # 붙일 수 있는 높이 = 부모 꼭대기: 연결판 윗면이 부모 윗면과 같은 높이로 끝날 수 있다 (뒤집어 출력하면 베드,
        # 바로 세우면 위를 보는 면). 자식이 더 낮으면 그 위로 경사를 두고, 경사는 꼭대기에서 잘린다
        h = max(0.0, min(cu[1], limit))
        top = h if h >= limit - 1e-6 else min(limit, h + rise)
    else:
        # 부모 면 중간에서 끝나는 연결판: 윗면이 수평이면 뒤집어 출력할 때 오버행이므로 늘 경사로 끝나고, 경사 끝이
        # 붙일 수 있는 높이를 넘지 않게 한다
        h = max(0.0, min(cu[1], limit - rise))
        top = h + rise
    return SlidePlan(j, o, t, u, n, t0, t1, h, top, mount, cu, pu[1])


def _ccw(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """다각형 꼭짓점을 반시계 방향으로 (Polygon 면의 법선 = 평면 z 방향이 되어 밀어내는 방향이 정해진다)."""
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
    return pts if area > 0 else pts[::-1]


def _side_profile_solid(plan: SlidePlan, pts: list[tuple[float, float]], t0: float, t1: float):  # noqa: ANN202
    """면 좌표 (d, u) 다각형을 가로 t0~t1 로 밀어낸 솔리드 (조립 좌표)."""
    from build123d import Plane, Polygon, extrude

    plane = Plane(origin=tuple(plan.frame_point(t1, 0, 0)), x_dir=tuple(plan.n), z_dir=tuple(-plan.t))
    return extrude(plane * Polygon(*_ccw(pts), align=None), amount=t1 - t0)


def plate_solid(plan: SlidePlan, for_print: bool):  # noqa: ANN201
    """연결판 (도브테일 홈 없이). 부모 벽 속으로 OVERLAP 만큼 묻힌다.

    조립 형상(for_print=False)은 자식 속으로 OVERLAP 만큼 더 들어가 한 덩어리가 되고, 출력 파트(for_print=True)는
    자식 뒷면에 딱 맞닿는 면(face_d)에서 끝난다. h 위의 경사(wedge)는 자식 뒷면 윗모서리(face_d, h)에서 벽 쪽으로
    SLOPE_RISE 기울기로 올라가 top 에서 잘린다."""
    f = plan.face_d
    d_out = f if for_print else PLATE_MM
    pts: list[tuple[float, float]] = [(-OVERLAP_MM, 0.0), (d_out, 0.0), (d_out, plan.h)]
    if plan.top > plan.h + 1e-6:
        if not for_print:
            pts.append((f, plan.h))
        rise = SLOPE_RISE * f
        if plan.h + rise <= plan.top + 1e-6:
            pts += [(0.0, plan.h + rise), (-OVERLAP_MM, plan.h + rise)]
        else:
            pts += [(f * (1 - (plan.top - plan.h) / rise), plan.top), (-OVERLAP_MM, plan.top)]
    else:
        pts.append((-OVERLAP_MM, plan.h))
    return _side_profile_solid(plan, pts, plan.t0, plan.t1)


def dovetail_centers(t0: float, t1: float) -> list[float]:
    """자식 뒷면 가로 범위 [t0, t1] 에 고르게 둔 도브테일 가운데 (DOVETAIL_PITCH_MM 마다 하나, 최소 하나)."""
    width = t1 - t0
    k = max(1, int(round(width / DOVETAIL_PITCH_MM)))
    return [t0 + (i + 0.5) * width / k for i in range(k)]


def dovetail_fits(t0: float, t1: float) -> bool:
    """가로 범위에 도브테일이 여유를 두고 들어가는지."""
    half = DOVETAIL_NECK_MM / 2 + DOVETAIL_DEPTH_MM * math.tan(math.radians(DOVETAIL_ANGLE_DEG))
    width = (t1 - t0) / len(dovetail_centers(t0, t1))
    return width >= 2 * (half + DOVETAIL_MARGIN_MM)


def _dovetail_prism(plan: SlidePlan, center: float, d_top: float, d_bottom: float, inset: float,
                    u_lo: float, u_hi: float):  # noqa: ANN202
    """세로(u) 방향 도브테일 기둥. 단면: 자식 뒷면(face_d)에서 벽 쪽으로 δ 들어간 곳의 반폭 = 입구 반폭 + δ·tan(각도),
    inset 만큼 옆면을 안쪽으로 (혀의 틈새). d_top(바깥 쪽 끝)·d_bottom(벽 쪽 끝)은 d 좌표."""
    from build123d import Plane, Polygon, extrude

    tan = math.tan(math.radians(DOVETAIL_ANGLE_DEG))
    cos = math.cos(math.radians(DOVETAIL_ANGLE_DEG))
    f = plan.face_d

    def half(d: float) -> float:
        return DOVETAIL_NECK_MM / 2 + (f - d) * tan - inset / cos

    pts = [(center - half(d_top), -d_top), (center + half(d_top), -d_top),
           (center + half(d_bottom), -d_bottom), (center - half(d_bottom), -d_bottom)]
    # 평면 좌표: x = t, y = u × t = −n (그래서 d 는 −y)
    plane = Plane(origin=tuple(plan.frame_point(0, u_lo, 0)), x_dir=tuple(plan.t), z_dir=tuple(plan.u))
    return extrude(plane * Polygon(*_ccw(pts), align=None), amount=u_hi - u_lo)


def slot_cutters(plan: SlidePlan, centers: list[float]) -> list:
    """연결판(출력 파트)에 내는 세로 도브테일 홈. 위·아래로 트여 있다 (자식을 위에서 밀어 내린다)."""
    f = plan.face_d
    return [_dovetail_prism(plan, c, f + 1.0, f - DOVETAIL_DEPTH_MM, 0.0, -1.0, plan.top + 1.0) for c in centers]


def tongue_solid(plan: SlidePlan, centers: list[float], u_lo: float, u_hi: float,
                 slope_top: bool, slope_bottom: bool):  # noqa: ANN201
    """자식 뒷면의 도브테일 혀 (출력 파트). 홈보다 옆·끝이 SLIDE_CLEARANCE_MM 작고, 자식 속으로 0.5mm 묻힌다.

    slope_top/slope_bottom: 출력 자세에서 그 끝면이 아래를 보면(베드에 닿지 않는 곳) 끝을 경사로 깎는다
    (자식 뒷면 쪽이 길고 벽 쪽 끝이 SLOPE_RISE 기울기로 짧아진다)."""
    f = plan.face_d
    c = SLIDE_CLEARANCE_MM
    tip = f - (DOVETAIL_DEPTH_MM - c)
    out = None
    for cen in centers:
        prism = _dovetail_prism(plan, cen, f + 0.5, tip, c, u_lo, u_hi)
        out = prism if out is None else out + prism
    depth = f + 0.5 - tip + 2.0
    w0, w1 = min(centers) - DOVETAIL_NECK_MM * 2, max(centers) + DOVETAIL_NECK_MM * 2
    if slope_top:
        # 자식 뒷면(f, u_hi) 에서 벽 쪽으로 내려가는 면 위를 잘라 낸다
        cut = [(f, u_hi), (f - depth, u_hi - SLOPE_RISE * depth), (f - depth, u_hi + 5), (f + 1, u_hi + 5), (f + 1, u_hi)]
        out = out - _side_profile_solid(plan, cut, w0, w1)
    if slope_bottom:
        cut = [(f, u_lo), (f - depth, u_lo + SLOPE_RISE * depth), (f - depth, u_lo - 5), (f + 1, u_lo - 5), (f + 1, u_lo)]
        out = out - _side_profile_solid(plan, cut, w0, w1)
    return out


def plate_gaps(plan: SlidePlan, child_mesh, other_mesh) -> tuple[float, ...]:  # noqa: ANN001
    """자식이 기대는 연결판 높이(h) 위에서 자식 뒷면과 그 뒤(부모 벽·연결판 경사·지붕 뚜껑 등 자식이 아닌 출력 파트) 사이
    틈 (mm, 0.1 단위로 모은 값).

    자식 뒷면 위 격자점마다 벽 쪽(−n)으로 광선을 쏘아 처음 닿는 곳까지 거리를 잰다 (닿지 않으면 뒤가 트여 틈이 아니다).
    연결판 경사 앞은 0 에서 PLATE_MM − OVERLAP_MM 까지 벌어지는 홈, 그 위 벽 앞은 PLATE_MM − OVERLAP_MM 의 고른 틈이고,
    자식이 처마보다 높으면 지붕 경사면과 자식 뒷면 사이가 위로 갈수록 넓어지는 쐐기 틈이 된다 (지붕에서 미끄러진 다리가
    끼는 곳). child_mesh·other_mesh: 조립 좌표 trimesh."""
    if plan.child_u[1] <= plan.h + 0.5 or plan.t1 - plan.t0 < 1.0:
        return ()
    f = plan.face_d
    n_t = max(3, min(24, int((plan.t1 - plan.t0) / 5) + 1))
    ts = np.linspace(plan.t0 + 0.75, plan.t1 - 0.75, n_t)
    us = np.arange(plan.h + 0.3, plan.child_u[1] - 0.3, 1.0)
    if len(us) == 0:
        return ()
    T, U = (a.ravel() for a in np.meshgrid(ts, us))
    base = plan.origin + np.outer(T, plan.t) + np.outer(U, plan.u)
    # 자식 뒷면이 실제로 있는 자리만: 뒷면 바로 앞(벽 쪽)에서 바깥(+n)으로 쏜 광선이 곧바로 자식에 닿는 곳
    probe = base + plan.n * (f - 0.5)
    loc, idx, _ = child_mesh.ray.intersects_location(probe, np.tile(plan.n, (len(probe), 1)), multiple_hits=False)
    inside = np.zeros(len(probe), dtype=bool)
    inside[idx[np.linalg.norm(loc - probe[idx], axis=1) < 1.0]] = True
    if not inside.any():
        return ()
    org = base[inside] + plan.n * (f - 0.01)
    dirs = np.tile(-plan.n, (len(org), 1))
    loc, idx, _ = other_mesh.ray.intersects_location(org, dirs, multiple_hits=False)
    if len(idx) == 0:
        return ()
    gaps = np.linalg.norm(loc - org[idx], axis=1) + 0.01
    return tuple(float(g) for g in np.unique(np.round(gaps, 1)))


def leftover_width(left, placed: dict[str, PlacedPart], j: JoinSpec) -> float:  # noqa: ANN001
    """통로가 덮지 못한 빈 곳(passage_leftover)을 부모 면에 비춘 모양의 가장 넓은 폭 (내접원 지름, mm).
    벽을 뚫고 나간 틈의 폭이다 (부피가 있어도 폭이 출력 선 폭보다 좁으면 실제로는 메워지는 실금)."""
    import shapely
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from app.geometry.mesh import part_to_mesh

    _, t, u, _ = anchor_frame(placed, j.parent, j.parent_anchor)
    m = part_to_mesh(left)
    if len(m.faces) == 0:
        return 0.0
    tri = m.vertices[m.faces]
    pts = np.stack([tri @ t, tri @ u], axis=-1)
    polys = [Polygon(q) for q in pts]
    shape = unary_union([q for q in polys if q.is_valid and q.area > 1e-6])
    if shape.is_empty:
        return 0.0
    geoms = getattr(shape, "geoms", [shape])
    return max(2.0 * float(shapely.maximum_inscribed_circle(g, 0.01).length) for g in geoms)


def slide_problems(parts: list[PartSpec], joins: list[JoinSpec]) -> list[str]:
    """형상 없이 알 수 있는 슬라이드 결합 규칙 위반 (한국어 문구)."""
    out: list[str] = []
    by_id = {p.id: p for p in parts}
    slides = [j for j in joins if j.slide]
    if not slides:
        return out
    try:
        placed = place_parts(parts, joins)
    except AssemblyError:
        return out  # 없는 연결 지점은 join_problems 가, 그 밖의 배치 오류는 형상 검사가 알린다
    for j in slides:
        pname = by_id[j.parent].template.display_name_ko
        cname = by_id[j.child].template.display_name_ko
        if j.passage:
            out.append(f"{pname}와(과) {cname}의 슬라이드 결합은 통로로 이을 수 없습니다")
            continue
        try:
            pa = _anchor(by_id[j.parent], j.parent_anchor)
            _anchor(by_id[j.child], j.child_anchor)
        except AssemblyError:
            continue  # join_problems 가 알린다
        if not slide_frame_ok(placed, j):
            out.append(f"{pname}와(과) {cname}의 슬라이드 결합은 옆면끼리만 할 수 있습니다 (세로 면, 위쪽이 위)")
        elif pa.mount is None and pa.port is None:  # 출입구 면은 join_problems 가 '막습니다'로 알린다
            out.append(f"{pname}의 '{j.parent_anchor}' 면에는 슬라이드 결합 연결판을 붙일 수 없습니다")
    return out


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
