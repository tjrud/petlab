"""조립 엔진: 부품(템플릿)들을 연결 지점끼리 이어 하나의 형상으로 만든다.

좌표: 뿌리 부품의 build() 좌표계. 자식은 부모 연결 지점에 '마주 보게' 붙는다.
  자식 연결 지점의 법선이 부모 법선과 반대 방향, 위쪽(up)이 같은 방향이 되도록 돌린 뒤
  부모 연결 지점 + 면 위 이동(shift·lift) 자리로 옮기고, 맞닿는 면이 확실히 붙도록 OVERLAP 만큼 파묻는다.
통로 연결(passage)은 자식 통로의 단면 기둥으로 부모 벽을 뚫는다 (passage="into_child" 면 거꾸로 부모 통로로 자식 벽을).
끼움 결합(mount="plug")은 통로 연결을 따로 출력해 끼우는 방식이다: 통로 쪽 부품 끝에 끼움 턱을 내고 벽은 넓힌 구멍으로 뚫는다.
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
from typing import TYPE_CHECKING

import numpy as np

from app.rules.loader import GapTrapRule
from app.templates.base import Anchor, Features, Opening, Side, Template, TemplateParams

if TYPE_CHECKING:
    import trimesh

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

# ── 끼움 결합 (mount="plug") ──
# 통로 쪽 부품(터널) 끝에 안쪽 단면이 통로와 같은 끼움 턱(spigot)을 내고, 벽 쪽 부품의 벽은 통로 단면을
# PLUG_SPIGOT_MM + PLUG_CLEARANCE_MM 만큼 넓혀 뚫는다. 터널 벽 고리(끼움 턱 바깥)가 넓힌 구멍을 덮는다
PLUG_SPIGOT_MM = 1.5       # 끼움 턱 두께 (통로 단면을 바깥으로 넓힌 폭)
PLUG_CLEARANCE_MM = 0.2    # 끼움 턱과 벽 구멍 사이 틈새 (한쪽)
PLUG_TIP_GAP_MM = 0.3      # 끼움 턱 길이 = 벽 두께 − 이 값 (벽 안쪽 면보다 튀어나오지 않게)
PLUG_MIN_RING_MM = 0.5     # 넓힌 구멍 바깥으로 벽 면에 닿는 터널 벽 고리의 최소 폭
PLUG_MIN_LENGTH_MM = 2.0   # 끼움 턱 최소 길이 (이보다 짧으면 끼워도 자리를 잡지 못한다)
# 끼움 턱 안쪽 면을 통로 단면보다 이만큼 바깥에 둔다. 끼움 턱 뿌리(터널 끝 0.5mm 안)의 안쪽 면이 터널 안쪽 면과 겹치면
# (휜 터널은 곧은 끼움 턱과 터널 안쪽 곡면이 끝에서 맞닿는다) 형상 커널이 합치기에 실패한다. 통로는 이만큼 넓어질 뿐이다
PLUG_EPS_MM = 0.05
# 출력 자세에서 아래를 보는 끼움 턱(세워 출력하는 터널의 아래 끝)은 터널 끝 면이 끼움 턱 바깥으로 아래를 보는 턱이 된다.
# 그 끝은 끼움 턱 뿌리에서 SLOPE_RISE 기울기로 벌어지는 경사(깔때기)로 깎는다: 끼움 턱 바깥 이만큼까지
PLUG_CHAMFER_REACH_MM = 10.0

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
    mount: str = "fused"  # "fused" | "slide" | "plug"
    # 통로가 자식 벽을 뚫는다 (passage="into_child": 부모가 통로 쪽, 자식이 벽 쪽)
    reverse: bool = False

    @property
    def slide(self) -> bool:
        return self.mount == "slide"

    @property
    def plug(self) -> bool:
        return self.mount == "plug"

    @property
    def separate(self) -> bool:
        """따로 출력하는 결합 (슬라이드·끼움): 출력 파트 묶음을 나눈다."""
        return self.mount in ("slide", "plug")

    @property
    def wall_end(self) -> tuple[str, str]:
        """통로 연결에서 벽이 뚫리는 쪽 (부품 id, 연결 지점)."""
        return (self.child, self.child_anchor) if self.reverse else (self.parent, self.parent_anchor)

    @property
    def port_end(self) -> tuple[str, str]:
        """통로 연결에서 통로 단면(port_cutter)을 내는 쪽 (부품 id, 연결 지점)."""
        return (self.parent, self.parent_anchor) if self.reverse else (self.child, self.child_anchor)


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
            # 슬라이드 결합: 자식 뒷면이 연결판 바깥면에 OVERLAP 만큼 묻히게 연결판 두께만큼 더 바깥에.
            # 끼움 결합: 따로 출력하는 두 파트가 겹치지 않게 묻지 않고 맞닿게
            out = PLATE_MM - OVERLAP_MM if j.slide else 0.0 if j.plug else -OVERLAP_MM
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
    """부품을 만들어 제자리에 놓고 하나로 합친 뒤(슬라이드 결합은 연결판까지), 통로 연결 자리를 뚫는다.

    끼움 결합은 합치기 전에 벽 쪽 부품만 넓힌 구멍으로 뚫고 통로 쪽 부품에 끼움 턱을 붙인다 (넓힌 구멍 기둥은 통로 쪽
    부품 끝 0.5mm 안에서 시작하므로 합친 뒤에 뚫으면 터널 끝과 끼움 턱이 깎인다). 조립 형상은 출력 파트를 끼운 자리 그대로
    (터널 끝 면이 벽 면에 맞닿는다)이되, 끼움 턱을 틈새까지 메우고 벽 속으로 OVERLAP_MM 묻히는 두께로 붙여 한 덩어리가 되게 한다
    (틈새·아래 끝 깔때기는 출력 파트에만 있다).

    형상 커널이 세 부품 이상을 합칠 때 맞닿은 면(출입구 옆면과 터널 안쪽 다리 면 등) 때문에, 또 휜 터널 끝의 안쪽 곡면이
    곧은 통로 기둥과 맞닿을 때 깨진 형상을 내는 경우가 있다 (은신처 ← 터널 → 은신처, 휜 터널). 그러면 통로도 합치기 전에
    벽 쪽 부품마다 PLUG_EPS_MM 넓혀 뚫고 다시 합친다. 처음 방식이 성한 형상을 내면 그대로 둔다 (공개한 모듈의 형상이 바뀌지 않게)."""
    placed = place_parts(parts, joins)
    if parts[0].template.cutter:
        raise AssemblyError("기준(첫) 부품은 빼는 모양(창문 등)일 수 없습니다")
    solids: dict[str, object] = {}
    for p in parts:
        if p.template.cutter:
            continue
        solids[p.id] = _plane(placed[p.id]) * p.template.build(p.params)
    shape = _assemble(parts, joins, placed, solids, cut_first=False)
    if any(j.passage and not j.plug for j in joins):
        # 형상 검사(is_valid)는 이 깨짐을 잡지 못한다: 메시가 닫혔는지 본다
        from app.geometry.mesh import mesh_health, part_to_mesh

        if not mesh_health(part_to_mesh(shape)).ok:
            other = _assemble(parts, joins, placed, solids, cut_first=True)
            if mesh_health(part_to_mesh(other)).ok:
                shape = other
    return shape


def _assemble(parts: list[PartSpec], joins: list[JoinSpec], placed: dict[str, PlacedPart],
              solids: dict[str, object], cut_first: bool):  # noqa: ANN202
    """build_assembly 의 합치기. cut_first: 통로(끼움 결합이 아닌 것도)를 합치기 전에 벽 쪽 부품마다 뚫는다."""
    shaped = dict(solids)
    for j in joins:
        if j.plug or (cut_first and j.passage):
            wall_id, port_id = j.wall_end[0], j.port_end[0]
            shaped[wall_id] = shaped[wall_id] - passage_cutter(placed, j, widen=cut_first)
            if j.plug:
                shaped[port_id] = shaped[port_id] + spigot_solid(placed, j, fill=True)
    shape = None
    for solid in shaped.values():
        shape = solid if shape is None else shape + solid
    for j in joins:
        if j.slide:
            plan = slide_plan(placed, j, _bounds(solids[j.parent]), _bounds(solids[j.child]))
            shape = shape + plate_solid(plan, for_print=False)
    for p in parts:
        if p.template.cutter:
            shape = shape - _plane(placed[p.id]) * p.template.build(p.params)
    for j in joins:
        if j.passage and not j.plug and not cut_first:
            shape = shape - passage_cutter(placed, j)
    return shape


def _passage_ends(placed: dict[str, PlacedPart], j: JoinSpec) -> tuple[PlacedPart, str, PlacedPart, str]:
    """(벽 쪽 부품, 그 연결 지점, 통로 쪽 부품, 그 연결 지점)."""
    (wid, wa), (pid, pa) = j.wall_end, j.port_end
    return placed[wid], wa, placed[pid], pa


def _wall_mm(wall: PlacedPart, anchor: str) -> float:
    a = _anchor(wall.spec, anchor)
    if a.wall_mm is None:
        raise AssemblyError(f"{wall.spec.template.display_name_ko}의 '{anchor}' 면은 뚫을 수 없습니다")
    return a.wall_mm


def plug_profiles(port: PlacedPart, anchor: str):  # noqa: ANN201
    """끼움 결합의 2D 단면 (통로 쪽 연결 지점의 cutter_at 좌표): (통로, 끼움 턱 고리, 넓힌 구멍).

    끼움 턱 고리 = 통로 단면을 PLUG_SPIGOT_MM 넓힌 것 − 통로 단면을 PLUG_EPS_MM 넓힌 것, 바닥(y=0) 위만 (바닥이 열린 아치는
    다리 끝이 베드에 선다). 넓힌 구멍 = 통로 단면을 PLUG_SPIGOT_MM + PLUG_CLEARANCE_MM 넓힌 것."""
    from build123d import Align, Kind, Rectangle, offset

    prof = port.spec.template.port_profile(port.spec.params, anchor)
    if prof is None:
        raise AssemblyError(f"{port.spec.template.display_name_ko}의 '{anchor}'에는 끼움 턱을 낼 수 없습니다")
    above = Rectangle(1e4, 1e4, align=(Align.CENTER, Align.MIN))
    ring = (offset(prof, PLUG_SPIGOT_MM, kind=Kind.ARC) & above) - offset(prof, PLUG_EPS_MM, kind=Kind.ARC)
    hole = offset(prof, PLUG_SPIGOT_MM + PLUG_CLEARANCE_MM, kind=Kind.ARC)
    return prof, ring, hole


def plug_length(placed: dict[str, PlacedPart], j: JoinSpec) -> float:
    """끼움 턱 길이 = 벽 쪽 부품의 벽 두께 − PLUG_TIP_GAP_MM."""
    wall, wa, _, _ = _passage_ends(placed, j)
    return _wall_mm(wall, wa) - PLUG_TIP_GAP_MM


def spigot_solid(placed: dict[str, PlacedPart], j: JoinSpec, fill: bool = False):  # noqa: ANN201
    """끼움 턱 (조립 좌표): 통로 쪽 부품 끝에서 벽 속으로 plug_length 만큼. 부품 끝 0.5mm 안에서 시작해 한 덩어리가 된다.

    fill=True: 조립 형상용. 틈새를 메우고 벽 구멍 둘레에 OVERLAP_MM 만큼 묻히는 두께 (맞닿은 면에만 기대지 않고
    벽 쪽 부품과 확실히 한 덩어리가 되게)."""
    from build123d import Align, Kind, Rectangle, offset

    from app.templates.base import cutter_at

    _, _, port, pa = _passage_ends(placed, j)
    prof, ring, _ = plug_profiles(port, pa)
    if fill:
        above = Rectangle(1e4, 1e4, align=(Align.CENTER, Align.MIN))
        ring = ((offset(prof, PLUG_SPIGOT_MM + PLUG_CLEARANCE_MM + OVERLAP_MM, kind=Kind.ARC) & above)
                - offset(prof, PLUG_EPS_MM, kind=Kind.ARC))
    return _plane(port) * cutter_at(_anchor(port.spec, pa), ring, plug_length(placed, j))


def plug_chamfer(placed: dict[str, PlacedPart], j: JoinSpec):  # noqa: ANN201
    """아래를 보는 끼움 턱 둘레에서 통로 쪽 부품 끝을 깎는 모양 (조립 좌표).

    끼움 턱 뿌리(끝 면, 끼움 턱 바깥 단면)에서 부품 속으로 들어갈수록 SLOPE_RISE 기울기로 벌어지는 깔때기 바깥,
    끼움 턱 바깥 PLUG_CHAMFER_REACH_MM 안쪽. 깎은 끝은 벽 면에 닿지 않고 넓힌 구멍 가장자리에 걸린다 (끼움 턱 바깥과
    구멍 사이 틈새 PLUG_CLEARANCE_MM 가 실금으로 보인다)."""
    from build123d import Kind, Plane, extrude, offset

    from app.templates.base import anchor_location

    _, _, port, pa = _passage_ends(placed, j)
    prof, _, _ = plug_profiles(port, pa)
    reach = PLUG_CHAMFER_REACH_MM
    rise = SLOPE_RISE * reach
    base = Plane.XZ.offset(-rise)  # 끝 면에서 부품 속으로 rise (기준 좌표틀: 법선 −Y)
    cone = extrude(base * offset(prof, PLUG_SPIGOT_MM + reach, kind=Kind.ARC), amount=rise,
                   taper=math.degrees(math.atan(1 / SLOPE_RISE)))
    band = extrude(base * offset(prof, PLUG_SPIGOT_MM + reach + 1.0, kind=Kind.ARC), amount=rise)
    return _plane(port) * (anchor_location(_anchor(port.spec, pa)) * (band - cone))


def passage_cutter(placed: dict[str, PlacedPart], j: JoinSpec, extra_mm: float = 1.0,
                   widen: bool = False):  # noqa: ANN201
    """통로 연결(passage)에서 벽 쪽 부품(보통 부모, passage="into_child" 면 자식)의 벽을 뚫는 통로 단면 기둥 (조립 좌표).
    끼움 결합이면 넓힌 구멍 단면.

    widen: 통로 단면을 PLUG_EPS_MM 넓혀 뚫는다 (단면을 아는 통로만). 휜 터널은 끝에서 안쪽 곡면이 곧은 기둥과 맞닿아
    형상 커널이 닫히지 않은 형상을 낸다. 조립 형상·출력 파트 묶음이 처음 방식으로 깨졌을 때만 쓴다 (공개한 모듈의 형상은 그대로)."""
    from app.templates.base import cutter_at

    wall, wa, port, pa = _passage_ends(placed, j)
    depth = _wall_mm(wall, wa) + OVERLAP_MM + extra_mm
    if j.plug:
        _, _, hole = plug_profiles(port, pa)
        return _plane(port) * cutter_at(_anchor(port.spec, pa), hole, depth)
    prof = port.spec.template.port_profile(port.spec.params, pa) if widen else None
    if prof is not None:
        from build123d import Kind, offset

        return _plane(port) * cutter_at(_anchor(port.spec, pa), offset(prof, PLUG_EPS_MM, kind=Kind.ARC), depth)
    cutter = port.spec.template.port_cutter(port.spec.params, pa, depth)
    if cutter is None:
        raise AssemblyError(f"{port.spec.template.display_name_ko}의 '{pa}'은(는) 통로가 아닙니다")
    return _plane(port) * cutter


def _bounds(shape) -> tuple[np.ndarray, np.ndarray]:  # noqa: ANN001
    bb = shape.bounding_box()
    return np.array([bb.min.X, bb.min.Y, bb.min.Z]), np.array([bb.max.X, bb.max.Y, bb.max.Z])


# ── 통로가 부모 개구부를 덮는지 ─────────────────────────────


def passage_leftover(placed: dict[str, PlacedPart], j: JoinSpec, port_solid=None):  # noqa: ANN001, ANN201
    """출입구·터널 끝(port 가 있는 벽 쪽 연결 지점)에 통로로 이은 부품이 그 개구부를 다 덮지 못하고 남긴 빈 곳 (조립 좌표).

    벽 쪽 = 보통 부모, passage="into_child" 면 자식. 통로 쪽 = 그 반대 (port_solid 는 통로 쪽 부품의 조립 좌표 형상).
    남은 곳 = 벽 쪽 개구부 단면 기둥(벽 면에서 바깥으로 벽 두께만큼) − 통로 쪽 형상 − 통로 단면 기둥.
    = 벽 쪽 개구부에서 통로 쪽 벽과 통로 밖으로 바깥이 보이는 곳 (바깥으로 뚫린 틈).
    통로가 더 좁거나 모양이 다르면(뾰족 아치 출입구에 둥근 아치·관·네모 터널) 그 차이가 바깥으로 뚫린 틈이 된다.
    끼움 결합이면 개구부에 넓힌 구멍(끼움 턱 + 틈새)을 더한다: 출입구가 없는 벽이어도 넓힌 구멍은 터널 벽 고리가 덮어야 한다.
    바닥(Z=0) 아래는 빼고 센다. 벽 쪽 연결 지점이 통로 자리가 아니면(끼움 결합이 아니면) None."""
    from build123d import Align, Box, Pos

    from app.templates.base import cutter_at

    wall, wa_name, port, pa_name = _passage_ends(placed, j)
    wa = _anchor(wall.spec, wa_name)
    if wa.wall_mm is None or (wa.port is None and not j.plug):
        return None
    opening = wall.spec.template.port_cutter(wall.spec.params, wa_name, wa.wall_mm) if wa.port is not None else None
    if opening is None and not j.plug:
        return None
    # port_cutter 는 면 안쪽 0.5mm 에서 시작한다: 면 바깥(통로 쪽 부품이 있는 쪽)만 보도록 0.5mm 밀어낸다.
    # 그래서 통로 쪽 벽이 개구부를 덮고 통로만 좁은 경우(벽 속에 막힌 턱이 남을 뿐 바깥으로 뚫리지 않는다)는 세지 않는다
    # 끼움 결합은 통로 쪽 부품 끝 면이 벽 면에 맞닿아 있다: 그 면과 겹치지 않게 PLUG_EPS_MM 더 밀어낸다
    lift = 0.5 + (PLUG_EPS_MM if j.plug else 0.0)
    _, _, _, na = _frame(wa)
    if opening is not None:
        opening = _plane(wall) * (Pos(*(na * lift)) * opening)
    _, _, _, nb = _frame(_anchor(port.spec, pa_name))
    if j.plug:
        # 넓힌 구멍을 벽 면 바깥(통로 쪽 부품 속)으로 벽 두께만큼: 통로 쪽 연결 지점에서 −법선 쪽으로
        _, _, hole = plug_profiles(port, pa_name)
        d = max(wa.wall_mm - 0.5, 0.1)
        enlarged = _plane(port) * (Pos(*(-nb * (d + PLUG_EPS_MM))) * cutter_at(_anchor(port.spec, pa_name), hole, d))
        opening = enlarged if opening is None else opening + enlarged
    if port_solid is None:
        port_solid = _plane(port) * port.spec.template.build(port.spec.params)
    # 통로 기둥을 통로 쪽 부품 쪽으로도 늘인다 (통로 끝 근처의 통로 속 = 빈 곳이지만 통로다)
    # 통로 단면을 PLUG_EPS_MM 넓혀 통로 쪽 부품 안쪽 면과 겹치지 않게 한다 (휜 터널의 안쪽 곡면과 곧은 기둥이 끝에서 맞닿으면
    # 형상 커널이 빼기를 건너뛴다). 단면을 모르는 부품은 port_cutter 그대로
    depth = wa.wall_mm + 2.0
    prof = port.spec.template.port_profile(port.spec.params, pa_name)
    if prof is not None:
        from build123d import Kind, offset

        bore = cutter_at(_anchor(port.spec, pa_name), offset(prof, PLUG_EPS_MM, kind=Kind.ARC), 2 * depth)
    else:
        bore = port.spec.template.port_cutter(port.spec.params, pa_name, 2 * depth)
    if bore is None:
        return None
    bore = _plane(port) * (Pos(*(-nb * depth)) * bore)
    left = opening - port_solid - bore
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
    """통로가 덮지 못한 빈 곳(passage_leftover)을 벽 쪽 면에 비춘 모양의 가장 넓은 폭 (내접원 지름, mm).
    벽을 뚫고 나간 틈의 폭이다 (부피가 있어도 폭이 출력 선 폭보다 좁으면 실제로는 메워지는 실금)."""
    import shapely
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from app.geometry.mesh import part_to_mesh

    _, t, u, _ = anchor_frame(placed, *j.wall_end)
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


def axis_aligned(rotation: np.ndarray) -> bool:
    """회전이 축끼리만 바꾸는지 (0°·90°·180°·270°)."""
    r = np.abs(np.asarray(rotation, dtype=float))
    return bool(np.allclose(r, np.round(r), atol=1e-6))


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
        elif not axis_aligned(placed[j.parent].rotation):
            # 연결판 자리는 조립 좌표의 축 정렬 상자로 정한다 (slide_plan): 비스듬한 부모면 연결판이 면을 벗어난다
            out.append(f"비스듬히 놓인 {pname}(휜 터널 끝의 방)에는 {cname}을(를) 끼울 수 없습니다. "
                       "터널을 덜 휘게 하거나 다른 방에 붙이세요")
        elif pa.mount is None and pa.port is None:  # 출입구 면은 join_problems 가 '막습니다'로 알린다
            out.append(f"{pname}의 '{j.parent_anchor}' 면에는 슬라이드 결합 연결판을 붙일 수 없습니다")
    return out


def _side_of(v: np.ndarray) -> Side | None:
    for name, s in _SIDE_VEC.items():
        if float(np.dot(v, s)) > 0.99:
            return name  # type: ignore[return-value]
    return None


ACCESS_DOT = 0.7  # 쓰지 않은 출입구 방향이 이만큼 맞는 옆면은 모두 드나드는 면 (45° 면 이웃한 두 면)


def _sides_near(v: np.ndarray) -> list[Side]:
    """수평 방향 v 가 향하는 옆면들 (가까운 순). 위·아래를 향하면 빈 목록."""
    v = np.asarray(v, dtype=float)
    h = np.array([v[0], v[1], 0.0])
    if np.linalg.norm(h) < 0.5 * np.linalg.norm(v):
        return []
    h /= np.linalg.norm(h)
    near = [(float(np.dot(h, s)), name) for name, s in _SIDE_VEC.items() if float(np.dot(h, s)) > ACCESS_DOT]
    return [name for _, name in sorted(near, reverse=True)]  # type: ignore[misc]


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
        # 출입구·터널 끝(port)은 연결 지점마다: 쓰지 않은 것의 조립 좌표 방향을 가까운 옆면(비스듬하면 이웃한 두 면)으로.
        # 이름(side)으로 빼면 휜 터널의 두 끝이 같은 이름일 때 남은 끝까지 빠지고, 비스듬한 끝은 어느 면도 아니게 된다
        port_sides = {a.side for a in anchors.values() if a.port is not None and a.side}
        for n, a in anchors.items():
            if a.port is None or n in used[p.id]:
                continue
            world = _sides_near(placed[p.id].vector(np.asarray(a.normal, dtype=float)))
            if not world:
                continue
            exits += 1
            sides.extend(w for w in world if w not in sides)
        joined_sides = {a.side for n, a in anchors.items() if n in used[p.id] and a.side}
        for s in f.access_sides:
            if s in joined_sides or s in port_sides:
                continue
            world = _side_of(placed[p.id].vector(_SIDE_VEC[s]))
            if world and world not in sides:
                sides.append(world)
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
            # 통로 쪽(보통 자식, passage="into_child" 면 부모)은 통로 자리, 벽 쪽은 뚫을 수 있는 면이어야 한다
            (wid, wname), (pid, pname) = j.wall_end, j.port_end
            pp = by_id[pid].template.anchors(by_id[pid].params).get(pname)
            wp = by_id[wid].template.anchors(by_id[wid].params).get(wname)
            if pp is not None and pp.port is None:
                out.append(f"{by_id[pid].template.display_name_ko}의 '{pname}'은(는) 통로가 아닙니다")
            if wp is not None and wp.wall_mm is None:
                out.append(f"{by_id[wid].template.display_name_ko}의 '{wname}' 면은 뚫을 수 없습니다")
    return out


def plug_problems(parts: list[PartSpec], joins: list[JoinSpec]) -> list[str]:
    """형상 없이 알 수 있는 끼움 결합 규칙 위반 (한국어 문구): 통로 없이 끼움, 끼움 턱을 낼 수 없는 통로,
    끼움 턱과 틈새를 두면 벽 고리가 넓힌 구멍을 덮지 못할 만큼 얇은 통로 쪽 벽, 끼움 턱이 너무 짧은 벽 쪽 벽."""
    out: list[str] = []
    by_id = {p.id: p for p in parts}
    for j in joins:
        if not j.plug:
            continue
        pname, cname = by_id[j.parent].template.display_name_ko, by_id[j.child].template.display_name_ko
        if not j.passage:
            out.append(f"{pname}와(과) {cname}의 끼움 결합은 통로로만 이을 수 있습니다")
            continue
        (wid, wname), (pid, aname) = j.wall_end, j.port_end
        wall, port = by_id[wid], by_id[pid]
        wa = wall.template.anchors(wall.params).get(wname)
        pa = port.template.anchors(port.params).get(aname)
        if wa is None or pa is None or wa.wall_mm is None or pa.port is None:
            continue  # join_problems 가 알린다
        if port.template.port_profile(port.params, aname) is None:
            out.append(f"{port.template.display_name_ko}의 '{aname}'에는 끼움 턱을 낼 수 없습니다")
            continue
        need = PLUG_SPIGOT_MM + PLUG_CLEARANCE_MM + PLUG_MIN_RING_MM
        t = port.template.features(port.params).min_wall_thickness_mm
        if t < need - 1e-6:
            out.append(f"{port.template.display_name_ko}의 벽 두께 {t:g}mm 로는 끼움 턱과 틈새를 두고 "
                       f"{wall.template.display_name_ko}의 구멍을 덮을 수 없습니다. 벽 두께를 {need:g}mm 이상으로 하세요")
        if wa.wall_mm - PLUG_TIP_GAP_MM < PLUG_MIN_LENGTH_MM - 1e-6:
            out.append(f"{wall.template.display_name_ko}의 벽이 {wa.wall_mm:g}mm 로 얇아 끼움 턱이 너무 짧습니다. "
                       f"벽 두께를 {PLUG_MIN_LENGTH_MM + PLUG_TIP_GAP_MM:g}mm 이상으로 하세요")
    return out


# ── 마주 보는 면 사이 틈 (slot_gaps) ──
# 잇지 않은 두 부품 사이에 몸이 끼는 틈은 두 면이 서로 마주 볼 때 생긴다. 상자 사이 거리만 보면
# 은신처 앞 모서리를 사이에 둔 그릇 받침과 터널처럼 마주 보는 면이 없는 자리까지 틈으로 센다.
SLOT_SAMPLES = 600        # 부품마다 겉면에서 고르게 뽑는 점 수 (상대 부품 가까이에 있는 면에서만)
SLOT_SEED = 0             # 같은 설계면 늘 같은 점을 뽑는다
SLOT_MIN_HITS = 3         # 두 방향 합쳐 이만큼 닿아야 틈으로 본다 (모서리를 스치는 광선 한두 개는 무시)
SLOT_FACING_DOT = -0.5    # 닿은 면의 바깥 법선과 광선 방향의 내적이 이보다 작아야 마주 보는 면 (120° 이상)
SLOT_RAY_EPS_MM = 0.01    # 광선을 겉면에서 이만큼 띄워 쏜다 (자기 면에 바로 닿지 않게)
SLOT_JOINT_MARGIN_MM = 6.0  # 이은 자리(끼움 구멍 둘레·연결판)를 이만큼 넓혀 틈 검사에서 뺀다


def part_meshes(parts: list[PartSpec], joins: list[JoinSpec]) -> dict[str, trimesh.Trimesh]:
    """빼는 모양이 아닌 부품마다 제자리에 놓은 형상의 trimesh (조립 좌표, 통로 뚫기·연결판 없이 부품 그대로)."""
    from app.geometry.mesh import part_to_mesh

    placed = place_parts(parts, joins)
    return {p.id: part_to_mesh(_plane(placed[p.id]) * p.template.build(p.params))
            for p in parts if not p.template.cutter}


def _box_distance(a: tuple[np.ndarray, np.ndarray], b: tuple[np.ndarray, np.ndarray]) -> float:
    gap = np.maximum(0.0, np.maximum(b[0] - a[1], a[0] - b[1]))
    return float(np.linalg.norm(gap))


def _first_hits(tris: np.ndarray, tree, origins: np.ndarray, dirs: np.ndarray,
                length: float) -> tuple[np.ndarray, np.ndarray]:
    """광선마다 길이 length 안에서 처음 닿는 삼각형 번호와 거리 (닿지 않으면 −1, inf).
    tree: 삼각형 경계 상자의 rtree (trimesh 의 triangles_tree). 광선을 선분으로 잘라 후보만 계산한다."""
    ends = origins + dirs * length
    lo, hi = np.minimum(origins, ends), np.maximum(origins, ends)
    ray_ids: list[np.ndarray] = []
    tri_ids: list[np.ndarray] = []
    for i in range(len(origins)):
        c = np.fromiter(tree.intersection((*lo[i], *hi[i])), dtype=np.int64)
        if len(c):
            ray_ids.append(np.full(len(c), i, dtype=np.int64))
            tri_ids.append(c)
    face = np.full(len(origins), -1, dtype=np.int64)
    dist = np.full(len(origins), np.inf)
    if not ray_ids:
        return face, dist
    r, t = np.concatenate(ray_ids), np.concatenate(tri_ids)
    # Möller–Trumbore
    v0 = tris[t, 0]
    e1, e2 = tris[t, 1] - v0, tris[t, 2] - v0
    d = dirs[r]
    pvec = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, pvec)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    tvec = origins[r] - v0
    u = np.einsum("ij,ij->i", tvec, pvec) * inv
    qvec = np.cross(tvec, e1)
    v = np.einsum("ij,ij->i", d, qvec) * inv
    s = np.einsum("ij,ij->i", e2, qvec) * inv
    hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (s > 0) & (s <= length)
    r, t, s = r[hit], t[hit], s[hit]
    if len(r) == 0:
        return face, dist
    order = np.lexsort((s, r))
    r, t, s = r[order], t[order], s[order]
    first = np.r_[True, r[1:] != r[:-1]]
    face[r[first]] = t[first]
    dist[r[first]] = s[first]
    return face, dist


def _joint_masks(parts: list[PartSpec], joins: list[JoinSpec], boxes: dict[str, tuple[np.ndarray, np.ndarray]]
                 ) -> tuple[dict[frozenset, list], set[frozenset]]:
    """이은 두 부품 쌍 → 이은 자리 판정 함수들 (점 배열 → 그 자리 안인지), 그리고 아예 보지 않을 쌍.
    이은 자리의 맞닿은 면·연결판은 틈이 아니다. 한 덩어리(fused)로 이은 쌍과 배치를 알 수 없는 쌍은 예전처럼 보지 않는다.

      - 끼움(통로) 결합: 연결 지점 기준점에서 통로 폭의 반 + 벽 + SLOT_JOINT_MARGIN_MM 안 (구멍 둘레의 벽과 터널 끝)
      - 슬라이드 결합: 부모 면 위에서 자식이 차지하는 직사각형(자식 상자를 면에 투영)을 SLOT_JOINT_MARGIN_MM 넓히고,
        면에서 바깥으로 연결판 두께 + SLOT_JOINT_MARGIN_MM 까지 (연결판·도브테일 자리)"""
    pairs = {frozenset((j.parent, j.child)) for j in joins}
    if not joins:
        return {}, set()
    try:
        placed = place_parts(parts, joins)
    except AssemblyError:
        return {}, pairs
    m = SLOT_JOINT_MARGIN_MM
    out: dict[frozenset, list] = {}
    skip: set[frozenset] = set()
    for j in joins:
        key = frozenset((j.parent, j.child))
        if not j.separate:
            skip.add(key)
            continue
        o, t, u, n = anchor_frame(placed, j.parent, j.parent_anchor)
        if j.slide:
            if j.child not in boxes:
                continue
            t0, t1 = _project(*boxes[j.child], o, t)
            u0, u1 = _project(*boxes[j.child], o, u)

            def inside(pts: np.ndarray, o=o, t=t, u=u, n=n, t0=t0, t1=t1, u0=u0, u1=u1) -> np.ndarray:
                v = pts - o
                vt, vu, vn = v @ t, v @ u, v @ n
                return ((vt >= t0 - m) & (vt <= t1 + m) & (vu >= u0 - m) & (vu <= u1 + m)
                        & (vn >= -m) & (vn <= PLATE_MM + m))
        else:
            (pid, pname) = j.port_end
            (wid, wname) = j.wall_end
            pa = _anchor(placed[pid].spec, pname)
            wa = _anchor(placed[wid].spec, wname)
            r = (pa.port or 0.0) / 2 + (wa.wall_mm or 0.0) + PLUG_SPIGOT_MM + m

            def inside(pts: np.ndarray, o=o, r=r) -> np.ndarray:
                return np.linalg.norm(pts - o, axis=1) <= r
        out.setdefault(key, []).append(inside)
    return out, skip


def slot_gaps(parts: list[PartSpec], joins: list[JoinSpec], meshes: dict[str, trimesh.Trimesh],
              gap: GapTrapRule) -> list[tuple[str, str, float]]:
    """부품 쌍 사이에서 두 면이 마주 보는 끼임 위험 틈 [(부품 a, 부품 b, 틈 mm)].

    슬라이드·끼움으로 이은 쌍도 본다 (휜 터널 안쪽과 그 은신처 앞벽 사이 주머니): 이은 자리(_joint_masks: 끼움 구멍 둘레,
    연결판)에서 쏘거나 거기에 닿는 광선만 뺀다. 한 덩어리(fused)로 이은 쌍은 보지 않는다.

    상자 사이 거리가 gap.passable_min_mm 보다 가까운 쌍마다, 상대 부품 가까이(상대 상자를 passable_min 만큼 넓힌 곳)에
    있는 겉면에서 SLOT_SAMPLES 개 점을 면적에 고르게 뽑아(seed SLOT_SEED) 바깥 법선 방향으로 광선을 쏜다. 다른 모든
    부품(자기 자신 포함) 가운데 처음 닿는 것이 상대 부품이고, 거리가 끼임 위험 구간(gap.is_trap)이며, 닿은 면의 바깥 법선이
    광선을 마주 볼 때(내적 < SLOT_FACING_DOT), 그리고 광선 구간이 어느 부품 속도 아닐 때(이은 부품에 묻힌 면이 아님)
    한 번으로 센다. 반대 방향(상대 → 이쪽)도 같이 세어 합이 SLOT_MIN_HITS 이상이면 틈으로 보고, 닿은 거리들의 중앙값을
    틈으로 돌려준다.

    meshes: 부품 id → 조립 좌표의 닫힌 trimesh (바깥 법선, part_meshes). 메시가 없는 부품(빼는 모양)은 건너뛴다.
    상자 사이 거리만 보는 검사와 달리 열린 모서리 너머 거리는 틈으로 세지 않는다."""
    import trimesh

    ids = [p.id for p in parts if p.id in meshes]
    if len(ids) < 2:
        return []
    reach = float(gap.passable_min_mm)
    boxes = {pid: (np.asarray(meshes[pid].bounds[0], float), np.asarray(meshes[pid].bounds[1], float)) for pid in ids}
    masks, skip = _joint_masks(parts, joins, boxes)
    partners: dict[str, list[str]] = {pid: [] for pid in ids}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if frozenset((a, b)) in skip or _box_distance(boxes[a], boxes[b]) >= reach:
                continue
            partners[a].append(b)
            partners[b].append(a)
    if not any(partners.values()):
        return []

    # 광선을 쏘는 부품: 가까운 쌍에 든 부품. 가리는 부품(장면): 그 부품들에서 reach 안에 있는 모든 부품
    # (이어 붙인 부품도 가린다. 더 먼 부품은 길이 reach 인 광선에 닿지 않는다)
    used = [pid for pid in ids if partners[pid]]
    scene_ids = [pid for pid in ids if any(_box_distance(boxes[pid], boxes[u]) < reach for u in used)]
    scene = trimesh.util.concatenate([meshes[pid] for pid in scene_ids])
    owner = np.repeat(np.arange(len(scene_ids)), [len(meshes[pid].faces) for pid in scene_ids])
    index = {pid: k for k, pid in enumerate(scene_ids)}
    tris, normals, tree = scene.triangles, scene.face_normals, scene.triangles_tree

    hits: dict[frozenset, list[float]] = {}
    for a in used:
        mesh = meshes[a]
        near = np.zeros(len(mesh.faces), dtype=bool)
        tlo, thi = mesh.triangles.min(axis=1), mesh.triangles.max(axis=1)
        for b in partners[a]:
            blo, bhi = boxes[b][0] - reach, boxes[b][1] + reach
            near |= np.all(thi >= blo, axis=1) & np.all(tlo <= bhi, axis=1)
        weight = mesh.area_faces * near
        if weight.sum() <= 0:
            continue
        pts, fi = trimesh.sample.sample_surface(mesh, SLOT_SAMPLES, face_weight=weight, seed=SLOT_SEED)
        dirs = mesh.face_normals[fi]
        origins = pts + dirs * SLOT_RAY_EPS_MM
        face, dist = _first_hits(tris, tree, origins, dirs, reach)
        got = face >= 0
        face, dist, dirs, origins = face[got], dist[got], dirs[got], origins[got]
        who = owner[face]
        ok = np.einsum("ij,ij->i", normals[face], dirs) < SLOT_FACING_DOT
        ok &= np.isin(who, [index[b] for b in partners[a]])
        ok &= np.array([gap.is_trap(float(x)) for x in dist + SLOT_RAY_EPS_MM], dtype=bool)
        if not ok.any():
            continue
        face, dist, dirs, origins, who = face[ok], dist[ok], dirs[ok], origins[ok], who[ok]
        # 광선 구간이 다른 부품 속을 지나면(이은 부품에 묻힌 겉면에서 쏘았거나 묻힌 겉면에 닿음) 빈 틈이 아니다.
        # 처음 닿는 곳까지 어떤 겉면도 지나지 않으므로 구간 가운데 한 점만 보면 된다
        mid = origins + dirs * (dist / 2)[:, None]
        free = np.ones(len(mid), dtype=bool)
        for pid in scene_ids:
            lo, hi = boxes[pid]
            box_in = np.all((mid >= lo) & (mid <= hi), axis=1)
            if box_in.any():
                free[box_in] &= ~meshes[pid].contains(mid[box_in])
        hit_pts = origins + dirs * dist[:, None]
        for b in partners[a]:
            sel = free & (who == index[b])
            for m in masks.get(frozenset((a, b)), ()):
                sel &= ~(m(origins) | m(hit_pts))
            if sel.any():
                hits.setdefault(frozenset((a, b)), []).extend(float(x) for x in dist[sel] + SLOT_RAY_EPS_MM)

    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ds = hits.get(frozenset((a, b)), [])
            if len(ds) >= SLOT_MIN_HITS:
                out.append((a, b, float(np.median(ds))))
    return out
