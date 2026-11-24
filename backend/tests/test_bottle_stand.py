"""물병 거치대 템플릿 테스트: 닫힌 메시, 서포트 없는 출력(파트별 오버행·허공 섬), 출력 공간, 제약(틈새·안정성·컵 아래 공간),
연결 지점, 은신처에 붙인 조립."""

from __future__ import annotations

import numpy as np
import pytest
from build123d import Vector
from shapely.ops import unary_union

from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.modules.assembly import (
    JoinSpec,
    PartSpec,
    build_assembly,
    merge_features,
    place_parts,
)
from app.templates.base import RuleContext
from app.templates.bottle_stand import (
    HOLE_CH,
    SOCKET_DEPTH_MM,
    BottleStandParams,
    BottleStandTemplate,
    _geom,
    base_thickness,
    gap_widening,
    holder_bottom,
    total_height,
)
from app.templates.hideout import HideoutParams, HideoutTemplate
from app.validation.checks import measure_thickness, overhang_area

STAND = BottleStandTemplate()
HIDEOUT = HideoutTemplate()
BUILD_VOLUME = (220.0, 220.0, 250.0)  # rules/printing.yaml build_volume_mm
OVERHANG_TOL = 100.0  # rules/printing.yaml overhang_area_tolerance_mm2


def ctx(rules, size="syrian") -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size))


def violated(p, c):
    return {k.field for k in STAND.constraints(p, c) if k.violates(getattr(p, k.field))}


def floating_islands(pm, step: float = 0.5) -> list[float]:
    """출력 자세 메시를 층마다 잘라, 아래층과 겹치지 않고 새로 생기는 섬(허공에서 시작하는 층)의 높이 목록.

    면 기울기만 보는 오버행 검사는 아래로 뾰족한 'V' 끝(양쪽 면이 45° 안)에서 시작하는 섬을 놓친다."""
    out, prev = [], None
    for z in np.arange(step / 2, pm.bounds[1][2], step):
        sec = pm.section(plane_origin=(0, 0, z), plane_normal=(0, 0, 1))
        if sec is None:
            prev = None
            continue
        to_plane = np.eye(4)
        to_plane[2, 3] = -z
        planar, _ = sec.to_2D(to_2D=to_plane, check=False)
        cur = unary_union(list(planar.polygons_full))
        if prev is not None:
            out += [float(z) for g in getattr(cur, "geoms", [cur]) if g.intersection(prev).area < 1e-3]
        prev = cur
    return out


def assert_printable(p: BottleStandParams, min_wall: float = 3.0):
    """조립 형상은 닫힌 한 덩어리 + 출력 파트마다 닫힌 메시·서포트 불필요(오버행·허공 섬 없음)·측정 두께·출력 공간."""
    part = STAND.build(p)
    assert len(part.solids()) == 1
    m = part_to_mesh(part)
    assert mesh_health(m).ok
    for pp in STAND.print_parts(p):
        assert len(pp.part.solids()) == 1, pp.key
        pmesh = part_to_mesh(pp.part)
        assert mesh_health(pmesh).ok, pp.key
        pm = to_print_orientation(pmesh, pp.rotation)
        assert overhang_area(pm, 45) < 1.0 < OVERHANG_TOL, pp.key
        assert floating_islands(pm) == [], pp.key
        assert np.percentile(measure_thickness(pmesh), 1) >= 0.9 * min_wall, pp.key
        assert all(e <= v + 1e-6 for e, v in zip(pm.extents, BUILD_VOLUME)), pp.key
    return part, m


CASES = [
    {},
    {"bottle_diameter_mm": 40, "cap_diameter_mm": 15, "spout_height_mm": 30, "spout_drop_mm": 50,
     "holder_height_mm": 60, "base_width_mm": 80, "base_depth_mm": 80, "wall_thickness_mm": 1.2, "clearance_mm": 0.5},
    {"bottle_diameter_mm": 90, "cap_diameter_mm": 45, "spout_height_mm": 70, "spout_drop_mm": 60,
     "holder_height_mm": 95, "base_width_mm": 125, "base_depth_mm": 125, "wall_thickness_mm": 3, "clearance_mm": 2.0},
    {"bottle_diameter_mm": 65, "cap_diameter_mm": 40, "spout_height_mm": 80, "spout_drop_mm": 70,
     "holder_height_mm": 80, "base_width_mm": 120, "base_depth_mm": 120, "wall_thickness_mm": 8, "clearance_mm": 1.0},
]


@pytest.mark.parametrize("kw", CASES)
def test_builds_printable_in_two_parts(kw):
    p = BottleStandParams(**kw)
    _, m = assert_printable(p, min_wall=min(3.0, p.wall_thickness_mm))
    base, holder = STAND.print_parts(p)
    assert (base.key, holder.key) == ("base", "holder")
    assert np.allclose(base.rotation, np.eye(3))                    # 받침판은 사용 자세 그대로
    assert np.allclose(holder.rotation, np.diag([1.0, -1.0, -1.0]))  # 컵 기둥은 뒤집어 컵 입구가 베드
    assert np.allclose(STAND.print_rotation(p), base.rotation)
    assert m.extents[0] == pytest.approx(p.base_width_mm, abs=0.01)
    assert m.extents[1] == pytest.approx(p.base_depth_mm, abs=0.01)
    assert m.extents[2] == pytest.approx(total_height(p), abs=0.01)
    lo, hi = m.bounds
    assert np.allclose((lo[:2] + hi[:2]) / 2, 0, atol=1e-6) and lo[2] == pytest.approx(0, abs=1e-6)


def test_one_piece_upright_would_need_support():
    """한 덩어리로 세워 출력하면 컵 밑 고리가 뒤판에 닿기 전 허공에서 시작한다 (파트를 나눈 이유)."""
    p = BottleStandParams()
    g = _geom(p)
    pm = part_to_mesh(STAND.build(p))
    islands = floating_islands(pm)
    assert islands and all(abs(z - g.z0) < 1.0 for z in islands)


def test_parts_fit_flush_in_socket():
    """뒤판 발이 받침판 소켓에 밀착해 끼워진다: 두 파트는 겹치지 않고, 합치면 한 덩어리이며, 발은 소켓 깊이만큼 들어간다."""
    p = BottleStandParams()
    g = _geom(p)
    base, holder = (pp.part for pp in STAND.print_parts(p))
    assert (base & holder).volume < 1e-3
    assert len((base + holder).solids()) == 1
    assert holder.bounding_box().min.Z == pytest.approx(g.base_t)
    assert base.bounding_box().max.Z == pytest.approx(g.base_t + SOCKET_DEPTH_MM)
    y = g.y_back - g.back_t / 2
    assert holder.is_inside(Vector(0, y, g.base_t + SOCKET_DEPTH_MM / 2))   # 소켓 안의 발
    assert base.is_inside(Vector(0, g.y_front_plate - 1.0, g.base_t + 2))   # 소켓 앞벽
    assert base.is_inside(Vector(g.ro + 1.0, y, g.base_t + 2))              # 소켓 옆벽


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_defaults_meet_rules_and_print(rules, size):
    c = ctx(rules, size)
    p = STAND.default_params(c)
    assert violated(p, c) == set()
    assert p.wall_thickness_mm == c.default_wall_mm
    assert_printable(p, min_wall=c.min_wall_mm)


def test_bottle_seat_and_spout_space_are_open():
    """물병 자리·마개 구멍은 비어 있고, 컵 아래(급수관 자리)와 그 앞은 바닥판까지 막힌 곳이 없다."""
    p = BottleStandParams()
    g = _geom(p)
    part = STAND.build(p)
    y = g.y_axis
    assert not part.is_inside(Vector(0, y, (g.seat_top + g.height) / 2))      # 물병 몸통 자리
    assert not part.is_inside(Vector(0, y, g.z0 + 0.5))                       # 마개 구멍
    assert part.is_inside(Vector(0, y + g.ri + g.t / 2, (g.seat_top + g.height) / 2))  # 컵 뒤 벽
    assert part.is_inside(Vector(0, y - g.ri - g.t / 2, (g.seat_top + g.height) / 2))  # 컵 앞 벽 (360° 감싼다)
    # 급수관 끝 자리와 그 앞·옆: 바닥판 위 ~ 컵 밑 사이에 아무것도 없다
    for z in np.linspace(g.base_t + 0.5, g.z0 - 0.5, 6):
        for dy in (0.0, -g.ro, -p.base_depth_mm / 2 - y + 1.0):
            assert not part.is_inside(Vector(0, y + dy, z))
        assert not part.is_inside(Vector(g.ro - 1.0, y, z))
    assert part.is_inside(Vector(0, -p.base_depth_mm / 2 + 5, g.base_t / 2))  # 앞까지 이어진 바닥판


def test_cup_gap_and_hole_match_clearance():
    """물병·마개와 컵 사이 틈 = 틈새 (구멍은 마개 + 틈새, 컵 안은 물병 + 틈새)."""
    p = BottleStandParams(bottle_diameter_mm=70, cap_diameter_mm=38, clearance_mm=1.5)
    g = _geom(p)
    assert g.ri == pytest.approx(35 + 1.5) and g.rh == pytest.approx(19 + 1.5)
    part = STAND.build(p)
    z_body = (g.seat_top + g.height) / 2
    assert not part.is_inside(Vector(g.ri - 0.1, g.y_axis, z_body))
    assert part.is_inside(Vector(g.ri + 0.1, g.y_axis, z_body))
    z_hole = (g.z0 + HOLE_CH + g.lip_top) / 2
    assert not part.is_inside(Vector(g.rh - 0.1, g.y_axis, z_hole))
    assert part.is_inside(Vector(g.rh + 0.1, g.y_axis, z_hole))


def _min_radius_at(m, axis_y: float, z: float) -> float:
    """메시를 높이 z 에서 자른 단면에서 물병 축까지 가장 가까운 점의 거리 (그 높이의 구멍·컵 안 반지름)."""
    sec = m.section(plane_origin=(0, 0, z), plane_normal=(0, 0, 1))
    pts = np.vstack(sec.discrete)
    return float(np.min(np.hypot(pts[:, 0], pts[:, 1] - axis_y)))


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_worst_case_gap_within_safe_max(rules, size):
    """틈새를 제약 상한으로 두고 물병을 한쪽으로 밀어 붙였을 때, 메시에서 잰 컵 입구·밑 구멍의 반대쪽 틈이 안전 틈새 이하."""
    c = ctx(rules, size)
    gt = c.size.gap_trap
    base = STAND.default_params(c)
    for wall in (c.min_wall_mm, 8.0):
        p = base.model_copy(update={"wall_thickness_mm": wall})
        cmax = next(k.max for k in STAND.constraints(p, c) if k.field == "clearance_mm")
        assert cmax >= 0.5  # 필드 범위 안에서 고를 수 있다
        p = p.model_copy(update={"clearance_mm": cmax})
        g = _geom(p)
        m = part_to_mesh(STAND.build(p))
        br, cr = p.bottle_diameter_mm / 2, p.cap_diameter_mm / 2
        r_body = _min_radius_at(m, g.y_axis, (g.seat_top + g.height) / 2)
        r_lip = _min_radius_at(m, g.y_axis, (g.z0 + HOLE_CH + g.lip_top) / 2)
        shift = min(r_body - br, r_lip - cr)  # 물병이 한쪽으로 밀릴 수 있는 거리
        r_rim = _min_radius_at(m, g.y_axis, g.height - 0.05)  # 컵 입구 (안쪽 모따기)
        r_tip = _min_radius_at(m, g.y_axis, g.z0 + 0.05)      # 밑 구멍 아래 끝 (모따기)
        assert r_rim - br + shift <= gt.safe_max_mm + 0.05
        assert r_tip - cr + shift <= gt.safe_max_mm + 0.05


def test_constraints(rules):
    c = ctx(rules, "syrian")
    gt = c.size.gap_trap
    cons = {k.field: k for k in STAND.constraints(BottleStandParams(), c)}
    # 물병이 한쪽으로 밀리면 반대쪽 틈 = 2 × 틈새 + 입구·밑 구멍 모따기
    assert 2 * cons["clearance_mm"].max + gap_widening(BottleStandParams()) == pytest.approx(gt.safe_max_mm)
    assert cons["clearance_mm"].source == "species"
    assert cons["wall_thickness_mm"].min == pytest.approx(c.min_wall_mm)

    good = BottleStandParams()
    assert violated(good, c) == set()
    # 컵 아래 공간: 바닥판 위 ~ 컵 밑이 통과 기준보다 낮으면 위반 (끼임 위험 높이의 선반 틈)
    low = BottleStandParams(spout_height_mm=30, spout_drop_mm=30)
    assert holder_bottom(low) - base_thickness(low) < gt.passable_min_mm
    assert "spout_drop_mm" in violated(low, c)
    fixed = low.model_copy(update={"spout_drop_mm": cons_min(low, c, "spout_drop_mm")})
    assert holder_bottom(fixed) - base_thickness(fixed) == pytest.approx(gt.passable_min_mm)
    # 안정성: 바닥판 가로·세로 ≥ 전체 높이의 절반
    tall = BottleStandParams(spout_height_mm=80, spout_drop_mm=80, holder_height_mm=90, base_width_mm=100,
                             base_depth_mm=100)
    assert total_height(tall) == 250
    assert {"base_width_mm", "base_depth_mm"} <= violated(tall, c)
    assert cons_min(tall, c, "base_depth_mm") == pytest.approx(125)
    # 마개가 물병만큼 크면 물병 어깨가 앉을 곳이 없다
    assert "cap_diameter_mm" in violated(BottleStandParams(bottle_diameter_mm=50, cap_diameter_mm=45), c)
    # 컵이 너무 낮으면 물병이 기운다
    assert "holder_height_mm" in violated(BottleStandParams(holder_height_mm=30), c)
    # 얇은 벽
    assert "wall_thickness_mm" in violated(BottleStandParams(wall_thickness_mm=1.5), c)


def cons_min(p, c, field):
    return next(k.min for k in STAND.constraints(p, c) if k.field == field and k.min is not None)


def test_autofix_resolves_everything(rules):
    from app.validation.autofix import clamp_params

    c = ctx(rules, "syrian")
    bad = BottleStandParams(spout_height_mm=30, spout_drop_mm=20, holder_height_mm=30, base_width_mm=60,
                            base_depth_mm=60, wall_thickness_mm=1.2, clearance_mm=2.0)
    fixed, issues = clamp_params(STAND, bad, c)
    assert not [i for i in issues if i.code == "param_conflict"]
    assert violated(fixed, c) == set()
    assert_printable(fixed, min_wall=c.min_wall_mm)


def test_features():
    p = BottleStandParams(spout_height_mm=62)
    f = STAND.features(p)
    assert f.openings == () and f.access_sides == ("front",)
    assert f.min_wall_thickness_mm == p.wall_thickness_mm
    assert f.extra == {"spout_height_mm": 62}
    assert f.entrance_count is None


def test_anchors():
    p = BottleStandParams()
    a = STAND.anchors(p)
    assert set(a) == {"back", "bottom"}
    assert all(x.port is None and x.wall_mm is None and x.side is None for x in a.values())
    back = a["back"]
    assert back.origin == (0, p.base_depth_mm / 2, 0)
    assert back.normal == (0, 1, 0) and back.up == (0, 0, 1)
    assert a["bottom"].origin == (0, 0, 0) and a["bottom"].normal == (0, 0, -1) and a["bottom"].up == (0, 1, 0)
    # 뒷면은 평평한 면: 뒤판 높이 전체에서 바로 안쪽은 채워져 있고 바깥은 비어 있다
    part = STAND.build(p)
    for z in (1.0, 50.0, total_height(p) - 3):
        assert part.is_inside(Vector(0, p.base_depth_mm / 2 - 0.2, z))
        assert not part.is_inside(Vector(0, p.base_depth_mm / 2 + 0.2, z))


def test_attach_back_to_hideout_left_wall():
    """은신처 왼쪽 벽에 거치대 뒷면을 붙이면 하나로 이어진 닫힌 메시가 되고, 거치대 앞(마시는 쪽)은 비어 있다."""
    hp = HideoutParams()
    sp = BottleStandParams()
    parts = [PartSpec("house", HIDEOUT, hp), PartSpec("water", STAND, sp)]
    joins = [JoinSpec("house", "left", "water", "back")]
    placed = place_parts(parts, joins)
    w = placed["water"]
    # 거치대 뒷면은 +X (은신처 쪽), 위는 그대로, 바닥 높이가 맞는다
    assert np.allclose(w.vector((0, 1, 0)), (1, 0, 0))
    assert np.allclose(w.vector((0, 0, 1)), (0, 0, 1))
    assert w.point(STAND.anchors(sp)["back"].origin)[2] == pytest.approx(0)
    shape = build_assembly(parts, joins)
    assert len(shape.solids()) == 1
    m = part_to_mesh(shape)
    assert mesh_health(m).ok
    assert m.bounds[0][2] == pytest.approx(0, abs=1e-6)
    assert m.extents[2] == pytest.approx(total_height(sp), abs=0.01)
    f = merge_features(parts, joins, enclosure=True)
    # 은신처 앞 출입구 쪽(-Y)과 거치대 앞(마시는 쪽, 은신처 왼쪽 벽 바깥 = 조립 좌표 -X) 모두 비워야 한다
    assert set(f.access_sides) == {"front", "left"}
    assert f.entrance_count == 1
