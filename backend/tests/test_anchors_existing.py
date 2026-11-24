"""기존 템플릿(집·램프·모래목욕통)의 연결 지점: 위치·방향이 형상과 맞는지, 조립 엔진으로 이으면 한 덩어리·통로가 되는지."""

from __future__ import annotations

import numpy as np
import pytest

from app.geometry.mesh import mesh_health, part_to_mesh
from app.library.verify.anchors import build_mesh
from app.library.verify.anchors import check_anchors as verify_anchors
from app.modules.assembly import (
    JoinSpec,
    PartSpec,
    _plane,
    build_assembly,
    join_problems,
    merge_features,
    place_parts,
)
from app.templates.base import RuleContext
from app.templates.hideout import HideoutParams, HideoutTemplate
from app.templates.house import (
    HouseParams,
    HouseTemplate,
    eave_height,
    is_cap,
    make_shell,
)
from app.templates.parts.common import arch_height
from app.templates.parts.levels import PORCH_MM
from app.templates.parts.shell import SKIRT_MM
from app.templates.ramp import TOP_LANDING_MM, RampParams, RampTemplate, run_length
from app.templates.sand_bath import SandBathParams, SandBathTemplate
from app.templates.tunnel import TunnelParams, TunnelTemplate
from app.validation.autofix import clamp_params

HOUSE, RAMP, SAND, HIDEOUT, TUNNEL = HouseTemplate(), RampTemplate(), SandBathTemplate(), HideoutTemplate(), TunnelTemplate()

HOUSE_COMBOS = {
    "flat_1f": {},
    "flat_1f_floor_ports": {"floor": {"enabled": True}, "ports": {"sides": ["right"]}, "windows": {"count": 4}},
    "pitched_1f_port_front": {"roof": {"kind": "pitched"}, "doors": {"sides": ["left"]}, "ports": {"sides": ["front"]}},
    "rounded_1f_two_doors": {"roof": {"kind": "rounded"}, "doors": {"sides": ["front", "back"]}},
    "two_internal": {"floors": {"count": 2, "climb": "internal_ramp"}},
    "two_external": {"floors": {"count": 2, "climb": "external_ramp", "exit_side": "back"}},
}


def ctx(rules, size="syrian") -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size),
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def house_params(rules, name: str) -> HouseParams:
    c = ctx(rules)
    d = HOUSE.default_params(c).model_dump()
    for k, v in HOUSE_COMBOS[name].items():
        d[k].update(v)
    p, issues = clamp_params(HOUSE, HouseParams(**d), c)
    assert not [i for i in issues if i.code == "param_conflict"], issues
    return p


def check_anchors(t, p):
    """연결 지점이 형상 바깥면 위에 있고 방향이 맞는지 (검증기 C01·C02, app.library.verify.anchors 와 같은 검사).
    통로 자리는 개구부 꼭대기 바로 위 벽(집 연결부는 플랜지 고리) 위 점으로 본다."""
    m = build_mesh(t, p)
    bad = [r for r in verify_anchors(t, p, m) if not r.ok]
    assert not bad, [(r.id, r.path, r.message) for r in bad]
    return m


# ── 집 ─────────────────────────────────────────────────────


@pytest.mark.parametrize("name", list(HOUSE_COMBOS))
def test_house_anchors_lie_on_outer_faces(rules, name):
    p = house_params(rules, name)
    check_anchors(HOUSE, p)
    a = HOUSE.anchors(p)
    f = HOUSE.features(p)
    # 통로 자리 = 출입구·연결부 (조립에서 바깥 출입구 수로 센다)
    assert sum(1 for x in a.values() if x.port is not None) == f.entrance_count
    assert {x.side for x in a.values() if x.side} == set(f.access_sides)
    assert ("top" in a) == (not is_cap(p))
    for side in p.ports.sides:
        assert a[side].wall_mm == pytest.approx(p.walls.thickness_mm + p.ports.flange_mm)
        assert a[side].port == p.ports.diameter_mm
    for side in p.doors.sides:
        assert a[side].port == p.doors.width_mm


def test_house_anchor_positions(rules):
    p = house_params(rules, "two_external")
    sh = make_shell(p)
    a = HOUSE.anchors(p)
    # 뚜껑을 씌우는 집: 벽 바깥면은 외형보다 벽 두께만큼 안쪽, 착지판 면은 착지판 바깥면이고 뚫을 수 없다
    assert a["front"].origin == pytest.approx((0, -sh.wy / 2, 0))
    assert a["back"].origin == pytest.approx((0, sh.wy / 2 + PORCH_MM, 0))
    assert a["back"].wall_mm is None and a["back"].port is None
    # 2층 집은 출입구 없는 벽을 통로로 뚫지 않는다 (선반·층판)
    assert a["left"].wall_mm is None and a["right"].wall_mm is None
    assert a["front"].wall_mm == p.walls.thickness_mm
    q = house_params(rules, "two_internal")
    assert HOUSE.anchors(q)["back"].wall_mm is None
    f = house_params(rules, "flat_1f")
    fa = HOUSE.anchors(f)
    assert fa["right"].wall_mm == f.walls.thickness_mm and fa["right"].port is None
    assert fa["top"].origin == pytest.approx((0, 0, f.height_mm))


def test_house_port_cutter_matches_opening(rules):
    """연결부 면의 port_cutter 는 그 개구부(뾰족 아치)와 같은 단면: 개구부 안쪽 점을 포함하고 바깥으로 뻗는다."""
    p = house_params(rules, "flat_1f_floor_ports")
    a = HOUSE.anchors(p)["right"]
    c = part_to_mesh(HOUSE.port_cutter(p, "right", 10.0))
    o = np.asarray(a.origin)
    assert c.contains([o + np.array([5.0, 0, 20.0])])[0]
    assert c.contains([o + np.array([5.0, 0, arch_height(p.ports.diameter_mm) - 3.0])])[0]
    assert not c.contains([o + np.array([5.0, p.ports.diameter_mm / 2 + 2, 10.0])])[0]
    assert HOUSE.port_cutter(p, "left", 10.0) is None  # 개구부 없는 면
    assert HOUSE.port_cutter(p, "front", 10.0) is not None  # 출입구


# ── 램프·모래목욕통 ──────────────────────────────────────────


@pytest.mark.parametrize("kw", [dict(), dict(height_mm=90, width_mm=80, slope_deg=35, steps=3),
                                dict(height_mm=200, width_mm=250, slope_deg=45, steps=0)])
def test_ramp_anchors(kw):
    p = RampParams(**kw)
    check_anchors(RAMP, p)
    a = RAMP.anchors(p)
    # README: top/bottom 은 위·아래 면 이름. 양 끝 세로면은 landing(발판 끝)·entry(입구 끝)
    assert set(a) == {"landing", "entry", "left", "right", "bottom"}
    assert a["landing"].origin[1] == pytest.approx(run_length(p) + TOP_LANDING_MM)
    assert a["landing"].normal == (0.0, 1.0, 0.0) and a["entry"].normal == (0.0, -1.0, 0.0)
    assert a["entry"].side == "front"
    assert a["bottom"].normal == (0.0, 0.0, -1.0) and a["bottom"].up == (0.0, 1.0, 0.0)
    assert all(x.port is None and x.wall_mm is None for x in a.values())


@pytest.mark.parametrize("kw", [dict(), dict(width_mm=250, depth_mm=220, basin_depth_mm=60, lip_height_mm=40)])
def test_sand_bath_anchors(kw):
    p = SandBathParams(**kw)
    check_anchors(SAND, p)
    a = SAND.anchors(p)
    assert set(a) == {"front", "back", "left", "right", "bottom"}
    assert a["front"].side == "front"
    # 출입 홈은 위가 트인 턱이라 통로가 아니고, 모래가 쏟아지지 않도록 어느 벽도 뚫지 않는다
    assert all(x.port is None and x.wall_mm is None for x in a.values())
    # 슬라이드 결합 연결판 자리: 옆·뒤는 면 전체, 앞면은 가로 전체 × 턱 높이 (출입 홈 아래)
    W, D, H = p.width_mm, p.depth_mm, p.basin_depth_mm + p.wall_thickness_mm
    assert a["front"].mount == pytest.approx((-W / 2, W / 2, p.lip_height_mm))
    assert a["back"].mount == pytest.approx((-W / 2, W / 2, H))
    assert a["left"].mount == pytest.approx((-D / 2, D / 2, H)) and a["right"].mount == pytest.approx((-D / 2, D / 2, H))
    assert a["bottom"].mount is None
    # 앞면 연결판 꼭대기(턱 높이)는 출입 홈 바닥과 같고, 연결판 가로 범위에 홈이 들어 있다 (홈은 그 위로만 파여 있다)
    m = part_to_mesh(SAND.build(p))
    y = -p.depth_mm / 2 + p.wall_thickness_mm / 2
    assert m.contains([[0, y, p.lip_height_mm - 0.5]])[0] and not m.contains([[0, y, p.lip_height_mm + 0.5]])[0]


# ── 조립 ───────────────────────────────────────────────────


def test_ramp_against_flat_roof_house_wall_is_one_solid(rules):
    """1층 평 지붕 집의 오른쪽 벽에 램프 꼭대기 끝을 대면 한 덩어리가 되고, 발판이 지붕 높이에서 벽에 닿는다."""
    p = house_params(rules, "flat_1f")
    r = RampParams(height_mm=p.height_mm, width_mm=70, slope_deg=25)
    parts = [PartSpec("house", HOUSE, p), PartSpec("ramp", RAMP, r)]
    joins = [JoinSpec("house", "right", "ramp", "landing")]
    assert join_problems(parts, joins) == []
    m = part_to_mesh(build_assembly(parts, joins))
    assert mesh_health(m).ok
    assert m.body_count == 1
    lo, hi = m.bounds
    total = run_length(r) + TOP_LANDING_MM
    assert hi[0] == pytest.approx(p.width_mm / 2 + total - 0.3, abs=0.05)  # 램프가 +X 로 뻗는다
    assert lo[2] == pytest.approx(0, abs=1e-6) and hi[2] == pytest.approx(p.height_mm, abs=1e-6)
    # 발판 윗면 바로 아래(벽 옆)는 램프 속
    assert m.contains([[p.width_mm / 2 + 5, 0, p.height_mm - 1]])[0]
    f = merge_features(parts, joins, enclosure=True)
    assert f.entrance_count == 1 and "front" in f.access_sides  # 집 출입구는 그대로, 램프 입구는 +X 쪽
    assert "right" in f.access_sides


@pytest.mark.parametrize("name,face", [("flat_1f_floor_ports", "right"), ("pitched_1f_port_front", "front")])
def test_tunnel_into_house_port_is_open_passage(rules, name, face):
    """터널 끝을 집의 연결부 플랜지에 통로로 이으면 벽·플랜지가 뚫린 채 한 덩어리가 된다."""
    p = house_params(rules, name)
    d = p.ports.diameter_mm
    tp = TunnelParams(length_mm=100, inner_diameter_mm=d, wall_thickness_mm=p.walls.thickness_mm)
    parts = [PartSpec("house", HOUSE, p), PartSpec("tube", TUNNEL, tp)]
    joins = [JoinSpec("house", face, "tube", "end_b", passage=True)]
    assert join_problems(parts, joins) == []
    m = part_to_mesh(build_assembly(parts, joins))
    assert mesh_health(m).ok
    assert m.body_count == 1
    a = HOUSE.anchors(p)[face]
    o, n = np.asarray(a.origin), np.asarray(a.normal)
    # 벽 두께 가운데·플랜지 가운데·터널 입구: 통로 높이 중간은 비어 있다
    for depth in (p.walls.thickness_mm / 2 + p.ports.flange_mm, p.ports.flange_mm / 2, -5.0):
        q = o - n * depth + np.array([0, 0, d / 2])
        assert not m.contains([q])[0], depth
    f = merge_features(parts, joins, enclosure=True)
    assert f.entrance_count == len(p.doors.sides) + 1  # 연결부는 터널로 이어지고 터널 바깥 끝이 출입구


def test_tunnel_into_plain_house_wall_opens_it(rules):
    p = house_params(rules, "flat_1f")
    tp = TunnelParams(length_mm=100, inner_diameter_mm=60, wall_thickness_mm=p.walls.thickness_mm)
    parts = [PartSpec("house", HOUSE, p), PartSpec("tube", TUNNEL, tp)]
    m = part_to_mesh(build_assembly(parts, [JoinSpec("house", "left", "tube", "end_b", passage=True)]))
    assert mesh_health(m).ok and m.body_count == 1
    assert not m.contains([[-p.width_mm / 2 + p.walls.thickness_mm / 2, 0, 25.0]])[0]


def test_house_door_passage_into_hideout(rules):
    """집(자식)의 출입구 면을 은신처 옆벽에 통로로 이으면 집의 port_cutter 가 은신처 벽을 출입구 모양으로 뚫는다."""
    p = house_params(rules, "flat_1f")
    hp = HideoutParams(width_mm=200, depth_mm=160, height_mm=110)
    parts = [PartSpec("hide", HIDEOUT, hp), PartSpec("house", HOUSE, p)]
    joins = [JoinSpec("hide", "right", "house", "front", passage=True)]
    assert join_problems(parts, joins) == []
    m = part_to_mesh(build_assembly(parts, joins))
    assert mesh_health(m).ok and m.body_count == 1
    assert not m.contains([[hp.width_mm / 2 - hp.wall_thickness_mm / 2, 0, 20.0]])[0]
    assert merge_features(parts, joins, enclosure=True).entrance_count == 1  # 은신처 앞문만 바깥 출입구


def test_blocking_house_door_or_porch_rules(rules):
    """출입구를 램프로 막으면 오류, 착지판 면은 통로로 뚫을 수 없다."""
    p = house_params(rules, "flat_1f")
    parts = [PartSpec("house", HOUSE, p), PartSpec("ramp", RAMP, RampParams())]
    assert any("막습니다" in m for m in join_problems(parts, [JoinSpec("house", "front", "ramp", "landing")]))
    q = house_params(rules, "two_external")
    parts = [PartSpec("house", HOUSE, q), PartSpec("tube", TUNNEL, TunnelParams())]
    assert join_problems(parts, [JoinSpec("house", "back", "tube", "end_b", passage=True)])


def test_external_ramp_on_porch_is_one_solid(rules):
    """2층 바깥 램프 집: 착지판 면에 램프 꼭대기 끝을 대면 발판이 착지판(2층 바닥) 높이에 맞닿는다."""
    p = house_params(rules, "two_external")
    r = RampParams(height_mm=p.floors.level_height_mm, width_mm=70, slope_deg=25)
    parts = [PartSpec("house", HOUSE, p), PartSpec("ramp", RAMP, r)]
    joins = [JoinSpec("house", "back", "ramp", "landing")]
    assert join_problems(parts, joins) == []
    m = part_to_mesh(build_assembly(parts, joins))
    assert mesh_health(m).ok and m.body_count == 1
    y_porch = HOUSE.anchors(p)["back"].origin[1]
    # 착지판과 램프 발판 사이: 같은 높이로 이어져 한 면 (윗면 바로 아래는 속이 차 있다)
    assert m.contains([[0, y_porch + 2, p.floors.level_height_mm - 1]])[0]
    assert not m.contains([[0, y_porch + 2, p.floors.level_height_mm + 1]])[0]


def test_ramp_to_sand_bath_lip_and_hideout(rules):
    """모래목욕통 앞면에 턱 높이 계단을 붙이면 출입 면이 계단 쪽으로 넘어간다. 은신처 옆벽에 램프를 대도 한 덩어리."""
    sp = SandBathParams()
    r = RampParams(height_mm=sp.lip_height_mm, width_mm=60, slope_deg=30, steps=1)
    parts = [PartSpec("bath", SAND, sp), PartSpec("step", RAMP, r)]
    joins = [JoinSpec("bath", "front", "step", "landing")]
    m = part_to_mesh(build_assembly(parts, joins))
    assert mesh_health(m).ok and m.body_count == 1
    f = merge_features(parts, joins, enclosure=False)
    assert f.access_sides == ("front",)  # 계단 입구 (모래목욕통 앞면은 이어져 빠지고 계단이 앞을 향한다)
    hp = HideoutParams()
    parts = [PartSpec("hide", HIDEOUT, hp), PartSpec("ramp", RAMP, RampParams(height_mm=hp.height_mm))]
    m = part_to_mesh(build_assembly(parts, [JoinSpec("hide", "left", "ramp", "landing")]))
    assert mesh_health(m).ok and m.body_count == 1


def _open_holes(parts, joins, face_part, face) -> list[tuple[float, float]]:
    """통로로 이은 면의 벽 두께 가운데 평면에서, 부모 개구부 안이면서 자식 통로 속이 아닌 빈 점 중 바깥이 보이는 점
    (= 이어 붙인 뒤에도 남은, 바깥으로 뚫린 틈)."""
    m = part_to_mesh(build_assembly(parts, joins))
    placed = place_parts(parts, joins)
    j = joins[0]
    child = placed[j.child]
    bore = part_to_mesh(_plane(child) * child.spec.template.port_cutter(child.spec.params, j.child_anchor, 200.0))
    pp = placed[face_part].spec.params
    a = HOUSE.anchors(pp)[face]
    o, n, up = (np.asarray(v, float) for v in (a.origin, a.normal, a.up))
    across = np.cross(up, n)
    mid = o - n * (a.wall_mm - pp.walls.thickness_mm / 2)
    pts = np.array([mid + across * u + up * v
                    for u in np.arange(-a.port / 2 + 0.5, a.port / 2, 1.0)
                    for v in np.arange(0.5, arch_height(a.port) + 1, 1.0)])
    air = ~m.contains(pts) & ~bore.contains(pts)
    seen = ~m.ray.intersects_any(pts[air], np.tile(n, (int(air.sum()), 1)))
    return [tuple(q) for q in pts[air][seen]]


@pytest.mark.parametrize("name,face", [("flat_1f", "front"), ("flat_1f_floor_ports", "right"),
                                       ("pitched_1f_port_front", "front")])
def test_matching_tunnel_closes_house_opening(rules, name, face):
    """출입구·연결부와 같은 폭·같은 단면(뾰족 아치)의 터널을 통로로 이으면 개구부가 바깥으로 남지 않는다 (끼임 틈 없음)."""
    p = house_params(rules, name)
    d = HOUSE.anchors(p)[face].port
    tp = TunnelParams(length_mm=100, inner_diameter_mm=d, wall_thickness_mm=p.walls.thickness_mm)
    parts = [PartSpec("house", HOUSE, p), PartSpec("tube", TUNNEL, tp)]
    assert _open_holes(parts, [JoinSpec("house", face, "tube", "end_b", passage=True)], "house", face) == []


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
@pytest.mark.parametrize("roof", ["flat", "pitched", "rounded"])
@pytest.mark.parametrize("wall", [None, 8.0])
def test_port_flange_stays_below_roof_band(rules, size, roof, wall):
    """가장 낮은 높이로 보정해도 연결부 플랜지 고리가 지붕 위로 솟거나(평 지붕) 뚜껑 스커트 띠에 들어가지 않는다."""
    c = ctx(rules, size)
    d = HOUSE.default_params(c).model_dump()
    d["roof"]["kind"] = roof
    d["ports"]["sides"] = ["right"]
    d["windows"]["count"] = 4  # 창 띠도 플랜지 위에 있어야 한다
    d["height_mm"] = 60  # 최소로 끌어올려지게
    if wall:
        d["walls"]["thickness_mm"] = wall
    p, issues = clamp_params(HOUSE, HouseParams(**d), c)
    assert not [i for i in issues if i.code == "param_conflict"], issues
    ring_top = arch_height(p.ports.diameter_mm + 2 * p.walls.thickness_mm)
    limit = eave_height(p) - (SKIRT_MM if is_cap(p) else p.walls.thickness_mm)
    assert ring_top <= limit + 1e-6
    m = part_to_mesh(HOUSE.build(p))
    assert m.bounds[1][2] == pytest.approx(p.height_mm, abs=1e-6)  # 아무것도 지붕 위로 솟지 않는다


# ── 은신처 옆면 출입구 ─────────────────────────────────────────

HIDEOUT_SIDE_DOORS = {
    "left": HideoutParams(side_doors="left", depth_mm=130),
    "right_2": HideoutParams(side_doors="right", entrance_count=2, depth_mm=130),
    "both": HideoutParams(side_doors="both", depth_mm=136),
    "four_doors": HideoutParams(side_doors="both", entrance_count=2, depth_mm=136),
}


@pytest.mark.parametrize("name", list(HIDEOUT_SIDE_DOORS))
def test_hideout_side_door_anchors_lie_on_outer_faces(name):
    p = HIDEOUT_SIDE_DOORS[name]
    m = check_anchors(HIDEOUT, p)
    assert mesh_health(m).ok and m.body_count == 1
    a = HIDEOUT.anchors(p)
    f = HIDEOUT.features(p)
    assert sum(1 for x in a.values() if x.port is not None) == f.entrance_count
    assert {x.side for x in a.values() if x.port is not None} == set(f.access_sides)


@pytest.mark.parametrize("side", ["left", "right"])
def test_tunnel_into_hideout_side_door_is_open_passage(side):
    """은신처 옆면 출입구에 같은 폭·둥근 아치 터널을 끼우면 한 덩어리가 되고, 옆벽·터널 속 통로가 비어 있다."""
    p = HideoutParams(side_doors=side, depth_mm=130)
    d = p.entrance_diameter_mm
    tp = TunnelParams(length_mm=100, inner_diameter_mm=d, wall_thickness_mm=3, shape="round_arch")
    parts = [PartSpec("hide", HIDEOUT, p), PartSpec("tube", TUNNEL, tp)]
    joins = [JoinSpec("hide", side, "tube", "end_b", passage=True, mount="plug")]
    assert join_problems(parts, joins) == []
    m = part_to_mesh(build_assembly(parts, joins))
    assert mesh_health(m).ok
    a = HIDEOUT.anchors(p)[side]
    o, n = np.asarray(a.origin), np.asarray(a.normal)
    # 벽 두께 가운데·안쪽·터널 입구: 출입구 높이 가운데는 비어 있다
    for depth in (p.wall_thickness_mm / 2, p.wall_thickness_mm + 5, -5.0):
        q = o - n * depth + np.array([0, 0, d / 2])
        assert not m.contains([q])[0], depth
    f = merge_features(parts, joins, enclosure=True)
    assert f.entrance_count == 2  # 앞 출입구 + 터널 바깥 끝
