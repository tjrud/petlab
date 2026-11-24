"""그릇 받침(bowl_holder) 부품 템플릿 테스트: 닫힌 메시·무서포트·벽 두께·제약·연결 지점·은신처와의 조립."""

from __future__ import annotations

import numpy as np
import pytest
from build123d import Vector

from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.modules.assembly import (
    OVERLAP_MM,
    JoinSpec,
    PartSpec,
    build_assembly,
    merge_features,
    place_parts,
)
from app.rules.loader import GapTrapRule
from app.templates.base import RuleContext
from app.templates.bowl_holder import (
    BowlHolderParams,
    BowlHolderTemplate,
    bowl_gap_top_mm,
    outer_radius,
    seat_radius,
    total_height,
)
from app.templates.hideout import HideoutParams, HideoutTemplate
from app.validation.checks import measure_thickness, overhang_area

HOLDER = BowlHolderTemplate()
HIDEOUT = HideoutTemplate()

MIN = {"bowl_diameter_mm": 60, "bowl_height_mm": 35, "clearance_mm": 0.5, "wall_thickness_mm": 1.0, "collar_height_mm": 10}
MAX = {"bowl_diameter_mm": 160, "bowl_height_mm": 80, "clearance_mm": 2.0, "wall_thickness_mm": 8, "collar_height_mm": 75}


def ctx(rules, size="syrian") -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size))


def violated(p, c):
    return {k.field for k in HOLDER.constraints(p, c) if k.violates(getattr(p, k.field))}


@pytest.mark.parametrize("kw", [{}, MIN, MAX, {"wall_thickness_mm": 2.4, "bowl_diameter_mm": 120, "collar_height_mm": 40}])
def test_builds_watertight_support_free(rules, kw):
    p = BowlHolderParams(**kw)
    m = part_to_mesh(HOLDER.build(p))
    assert mesh_health(m).ok
    assert m.body_count == 1
    # 외형: 가로·세로 = 2 × 바깥 반지름 (D 모양: 반원 + 뒤 직사각형), 높이 = 바닥판 + 턱
    Ro = outer_radius(p)
    assert m.extents == pytest.approx([2 * Ro, 2 * Ro, total_height(p)], abs=0.05)
    assert m.bounds[1][1] == pytest.approx(Ro, abs=0.01)  # 뒷면 = +Y
    # 사용 자세 그대로 서포트 없이 출력 (오버행 ~0)
    pm = to_print_orientation(m, HOLDER.print_rotation(p))
    assert overhang_area(pm, rules.printing.max_overhang_deg) < 1.0
    # 출력 공간 안
    assert all(pm.extents <= np.asarray(rules.printing.build_volume_mm) + 1e-6)
    # 측정 두께 ≥ 벽 두께 (턱·바닥판)
    assert np.percentile(measure_thickness(m), 1) >= 0.9 * p.wall_thickness_mm


def test_shape_seat_floor_and_collar():
    p = BowlHolderParams()
    part = HOLDER.build(p)
    t, Rs = p.wall_thickness_mm, seat_radius(p)
    assert part.is_inside(Vector(0, 0, t / 2))                         # 닫힌 바닥판
    assert not part.is_inside(Vector(0, 0, t + 1))                     # 그릇 자리 (위가 열린 홈)
    assert not part.is_inside(Vector(Rs - 0.1, 0, t + 5))              # 그릇 옆 틈새까지 비어 있음
    assert part.is_inside(Vector(Rs + t / 2, 0, t + 5))                # 턱 벽
    assert part.is_inside(Vector(0, -Rs - t / 2, t + 5))               # 앞(반원) 턱 벽
    assert not part.is_inside(Vector(Rs + t / 2, 0, total_height(p) + 0.5))


def test_features():
    p = BowlHolderParams()
    f = HOLDER.features(p)
    assert f.min_wall_thickness_mm == p.wall_thickness_mm
    assert f.openings == ()
    assert f.access_sides == ("front",)
    assert f.entrance_count is None
    assert f.extra["bowl_diameter_mm"] == p.bowl_diameter_mm


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_defaults_satisfy_rules(rules, size):
    c = ctx(rules, size)
    d = HOLDER.default_params(c)
    assert violated(d, c) == set()
    assert d.wall_thickness_mm >= c.min_wall_mm
    assert d.collar_height_mm <= d.bowl_height_mm - 5


def _seat_radius_at_top(p: BowlHolderParams) -> float:
    """메시에서 잰 턱 꼭대기 바로 아래의 그릇 자리 반지름 (안쪽 둥글림으로 넓어진 값)."""
    m = part_to_mesh(HOLDER.build(p))
    sec = m.section(plane_origin=[0, 0, total_height(p) - 0.005], plane_normal=[0, 0, 1])
    # 단면 고리 둘(바깥 외형·안쪽 그릇 자리) 중 안쪽 고리
    return min(float(np.linalg.norm(loop[:, :2], axis=1).max()) for loop in sec.discrete)


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_clearance_gap_never_trap(rules, size):
    """그릇을 한쪽 벽에 밀었을 때 반대쪽 틈(턱 꼭대기, 안쪽 둥글림 포함)이 종별 안전 틈새 이하로 제약된다.

    가장 넓은 허용 틈새로 실제 형상을 만들어 메시에서 잰다. 그릇이 한쪽 벽(자리 반지름)에 닿으면 반대쪽 틈 =
    꼭대기 자리 반지름 + 자리 반지름 − 그릇 지름."""
    c = ctx(rules, size)
    safe = c.size.gap_trap.safe_max_mm
    (k,) = [k for k in HOLDER.constraints(BowlHolderParams(), c) if k.field == "clearance_mm"]
    assert k.source == "species" and k.blocking
    clearance_field_max = BowlHolderParams.model_fields["clearance_mm"].metadata[1].le
    widest_allowed = min(k.max, clearance_field_max)
    for d in (60, 160):
        p = BowlHolderParams(bowl_diameter_mm=d, clearance_mm=widest_allowed)
        assert "clearance_mm" not in violated(p, c)
        far_side_gap = _seat_radius_at_top(p) + seat_radius(p) - d
        assert far_side_gap == pytest.approx(bowl_gap_top_mm(p), abs=0.1)
        assert not c.size.gap_trap.is_trap(far_side_gap)
        assert far_side_gap <= safe + 0.05
    # 조금만 넓혀도 (제약 위반) 반대쪽 틈이 끼임 구간에 든다: 제약이 느슨하지 않다
    if k.max + 0.1 <= clearance_field_max:
        p = BowlHolderParams(clearance_mm=k.max + 0.1)
        assert "clearance_mm" in violated(p, c)
        assert c.size.gap_trap.is_trap(_seat_radius_at_top(p) + seat_radius(p) - p.bowl_diameter_mm)


def test_clearance_limit_by_size(rules):
    """드워프(안전 틈새 4mm)는 필드 최대 2mm 틈새를 쓸 수 없다 (밀린 그릇 반대쪽 4.5mm 틈)."""
    dwarf, syrian = ctx(rules, "dwarf"), ctx(rules, "syrian")
    assert "clearance_mm" in violated(BowlHolderParams(clearance_mm=2.0), dwarf)
    assert "clearance_mm" not in violated(BowlHolderParams(clearance_mm=2.0), syrian)
    # 규칙이 더 엄격해지면 같은 틈새가 위반이 된다
    strict = RuleContext(
        syrian.size.model_copy(update={"gap_trap": GapTrapRule(safe_max_mm=2.0, passable_min_mm=70)}),
        syrian.min_wall_mm,
    )
    assert "clearance_mm" in violated(BowlHolderParams(clearance_mm=1.0), strict)
    assert "clearance_mm" not in violated(BowlHolderParams(clearance_mm=0.75), strict)


def test_collar_below_rim_and_wall_constraints(rules):
    c = ctx(rules, "syrian")
    assert "collar_height_mm" in violated(BowlHolderParams(bowl_height_mm=45, collar_height_mm=41), c)
    assert "collar_height_mm" not in violated(BowlHolderParams(bowl_height_mm=45, collar_height_mm=40), c)
    assert "wall_thickness_mm" in violated(BowlHolderParams(wall_thickness_mm=2.0), c)
    assert "wall_thickness_mm" not in violated(BowlHolderParams(wall_thickness_mm=3.0), c)


def test_anchors():
    p = BowlHolderParams()
    a = HOLDER.anchors(p)
    assert set(a) == {"back", "bottom"}  # 옆면은 앞쪽이 반원이라 붙이면 쐐기 틈이 생겨 두지 않는다
    for anc in a.values():
        assert anc.port is None and anc.wall_mm is None and anc.side is None
        assert abs(float(np.dot(anc.normal, anc.up))) < 1e-9
    assert a["back"].normal == (0.0, 1.0, 0.0) and a["back"].up == (0.0, 0.0, 1.0)
    assert a["back"].origin[2] == 0.0
    assert a["bottom"].normal == (0.0, 0.0, -1.0)


@pytest.mark.parametrize("kw", [{}, MIN, MAX])
def test_back_anchor_on_flat_back_face(kw):
    """뒷면 연결 지점이 평평한 뒷면 위에 있다: 그 면을 따라 가로·위로 옮긴 점들이 모두 메시 표면 위."""
    p = BowlHolderParams(**kw)
    m = part_to_mesh(HOLDER.build(p))
    o = np.asarray(HOLDER.anchors(p)["back"].origin)
    Ro, H = outer_radius(p), total_height(p)
    pts = np.array([o + [dx, 0, dz] for dx in (-0.8 * Ro, 0.0, 0.8 * Ro) for dz in (0.1, H / 2, H - 2.0)])
    _, dist, tri = m.nearest.on_surface(pts)
    assert dist.max() < 0.05
    assert np.all(m.face_normals[tri] @ [0, 1, 0] > 0.999)  # 평평한 +Y 면
    assert m.contains(pts - [0, 0.5, 0]).all() and not m.contains(pts + [0, 0.5, 0]).any()


def test_bottom_anchor_on_bed_face():
    p = BowlHolderParams()
    m = part_to_mesh(HOLDER.build(p))
    _, dist, tri = m.nearest.on_surface([HOLDER.anchors(p)["bottom"].origin])
    assert dist[0] < 0.05 and m.face_normals[tri[0]][2] < -0.999


@pytest.mark.parametrize("kw", [{}, MAX])
def test_assembles_to_hideout_right_wall(kw):
    """은신처 오른쪽 벽에 뒷면으로 붙이면 한 덩어리의 닫힌 메시가 되고, 뒷면이 벽에 틈 없이 맞닿는다."""
    hp, bp = HideoutParams(), BowlHolderParams(**kw)
    parts = [PartSpec("hideout", HIDEOUT, hp), PartSpec("bowl", HOLDER, bp)]
    joins = [JoinSpec("hideout", "right", "bowl", "back")]
    placed = place_parts(parts, joins)
    bowl = placed["bowl"]
    # 받침 뒷면 법선이 은신처 쪽(-X)을 보고, 그릇 중심은 벽 바깥 Ro - OVERLAP 거리, 바닥 높이는 같다
    assert np.allclose(bowl.vector((0, 1, 0)), (-1, 0, 0))
    centre = bowl.point((0, 0, 0))
    assert centre == pytest.approx([hp.width_mm / 2 + outer_radius(bp) - OVERLAP_MM, 0, 0], abs=1e-6)

    m = part_to_mesh(build_assembly(parts, joins))
    assert mesh_health(m).ok
    assert m.body_count == 1
    assert m.bounds[0][2] == pytest.approx(0.0, abs=1e-6)
    assert m.bounds[1][0] == pytest.approx(hp.width_mm / 2 + 2 * outer_radius(bp) - OVERLAP_MM, abs=0.05)

    f = merge_features(parts, joins, enclosure=True)
    assert f.entrance_count == 1  # 은신처 앞 출입구만 (받침은 통로가 아니다)
    assert "right" in f.access_sides  # 받침 앞(반원 쪽)이 바깥(+X)을 본다
