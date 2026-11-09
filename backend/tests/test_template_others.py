"""터널·램프/계단·모래목욕통 템플릿 테스트 (은신처와 같은 기준 + 무서포트 출력, 은신처를 포함한 공통 벽 두께 제약)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from build123d import Vector
from pydantic import ValidationError

from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.templates.base import RuleContext
from app.templates.hideout import HideoutTemplate
from app.templates.ramp import TOE_MM, TOP_LANDING_MM, RampParams, RampTemplate, run_length
from app.templates.sand_bath import SandBathParams, SandBathTemplate, entry_width
from app.templates.tunnel import TunnelParams, TunnelTemplate, end_side, outer_height
from app.validation.checks import measure_thickness, overhang_area

TUNNEL, RAMP, SAND = TunnelTemplate(), RampTemplate(), SandBathTemplate()
HIDEOUT = HideoutTemplate()


def ctx(rules, size="syrian") -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size))


def violated(t, p, c):
    return {k.field for k in t.constraints(p, c) if k.violates(getattr(p, k.field))}


def assert_printable(t, p, min_wall=3.0):
    """닫힌 메시 + 서포트 불필요 + 측정 두께가 기준 이상."""
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok
    pm = to_print_orientation(m, t.print_rotation(p))
    assert overhang_area(pm, 45) < 1.0
    assert np.percentile(measure_thickness(m), 1) >= 0.9 * min_wall
    return m


# ── 터널 ───────────────────────────────────────────────────


@pytest.mark.parametrize("kw", [
    dict(),
    dict(length_mm=80, inner_diameter_mm=35, bend_angle_deg=0, wall_thickness_mm=3),
    dict(length_mm=600, inner_diameter_mm=130, bend_angle_deg=180, wall_thickness_mm=8),
    dict(length_mm=300, inner_diameter_mm=70, bend_angle_deg=90, wall_thickness_mm=3),
    dict(length_mm=300, inner_diameter_mm=70, bend_angle_deg=30, wall_thickness_mm=3),
])
def test_tunnel_builds_printable(kw):
    p = TunnelParams(**kw)
    m = assert_printable(TUNNEL, p, min_wall=min(3.0, p.wall_thickness_mm))
    assert m.extents[2] == pytest.approx(outer_height(p), abs=0.05)
    if p.bend_angle_deg == 0:
        assert m.extents[1] == pytest.approx(p.length_mm, abs=0.01)
        assert m.extents[0] == pytest.approx(p.inner_diameter_mm + 2 * p.wall_thickness_mm, abs=0.01)


def test_tunnel_bend_keeps_volume():
    """수평으로 휘어도 단면·중심선 길이가 같으면 부피가 같다 (파푸스 정리)."""
    straight = TUNNEL.build(TunnelParams(length_mm=300, inner_diameter_mm=70, bend_angle_deg=0)).volume
    bent = TUNNEL.build(TunnelParams(length_mm=300, inner_diameter_mm=70, bend_angle_deg=120)).volume
    assert bent == pytest.approx(straight, rel=5e-3)


def test_tunnel_passage_is_open_and_floor_open():
    p = TunnelParams(length_mm=200, inner_diameter_mm=70, bend_angle_deg=0, wall_thickness_mm=3)
    part = TUNNEL.build(p)
    mid_y = -p.length_mm / 2
    assert not part.is_inside(Vector(0, mid_y, 35))          # 통로 내부
    assert not part.is_inside(Vector(0, mid_y, 0.5))         # 바닥이 열려 있음
    assert part.is_inside(Vector(35 + 1.5, mid_y, 20))       # 옆 벽
    assert not part.is_inside(Vector(0, mid_y, outer_height(p) - 6))  # 티어드롭 안쪽 꼭대기도 비어 있음


@pytest.mark.parametrize("angle,side", [(0, "back"), (45, "back"), (90, "left"), (135, "left"), (180, "front")])
def test_tunnel_end_side(angle, side):
    assert end_side(angle) == side
    sides = TUNNEL.features(TunnelParams(bend_angle_deg=angle, length_mm=400, inner_diameter_mm=70)).access_sides
    assert sides[0] == "front" and side in sides


def test_tunnel_constraints(rules):
    c = ctx(rules)
    bad = TunnelParams(length_mm=100, inner_diameter_mm=50, bend_angle_deg=180, wall_thickness_mm=1.5)
    assert {"inner_diameter_mm", "wall_thickness_mm", "length_mm", "bend_angle_deg"} <= violated(TUNNEL, bad, c)
    good = TunnelParams(length_mm=200, inner_diameter_mm=75, bend_angle_deg=90, wall_thickness_mm=3)
    assert violated(TUNNEL, good, c) == set()


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_tunnel_max_length_rule(rules, size):
    """종별 최대 길이(몸길이 2배, DTSchB): 기본값은 그 안이고, 넘으면 위반·보정, 저장본은 범위 밖으로 알린다."""
    from app.validation.autofix import clamp_params, constraint_violations

    c = ctx(rules, size)
    max_len = c.size.tunnel_max_length_mm
    d = TUNNEL.default_params(c)
    assert d.length_mm <= max_len
    assert violated(TUNNEL, d, c) == set()

    too_long = d.model_copy(update={"length_mm": max_len + 50})
    assert "length_mm" in violated(TUNNEL, too_long, c)
    fixed, issues = clamp_params(TUNNEL, too_long, c)
    assert fixed.length_mm == pytest.approx(max_len)
    assert any(i.code == "param_adjusted" and i.details["field"] == "length_mm" and "2배" in i.message_ko for i in issues)
    assert not [i for i in issues if i.code == "param_conflict"]

    # 나중에 더한 기준이라 저장된 버전은 막지 않는다: 다시 검증해도 error 가 아닌 rule_changed 경고
    stored = constraint_violations(TUNNEL, too_long, c)
    assert [(i.code, i.severity.value, i.details["field"]) for i in stored] == [("rule_changed", "warning", "length_mm")]
    assert stored[0].details["max"] == pytest.approx(max_len)
    assert "막지는 않" in stored[0].message_ko and "내려받을 수 있" not in stored[0].message_ko
    assert "). 이 기준은" in stored[0].message_ko  # 까닭과 안내 사이에 마침표


def test_dwarf_u_tunnel_reason_names_max_length(rules):
    """드워프는 최대 길이 때문에 U자가 안 된다: 휨 각도를 줄일 때 까닭(최대 길이)을 밝힌다."""
    from app.templates.tunnel import end_side
    from app.validation.autofix import clamp_params

    c = ctx(rules, "dwarf")
    p = TUNNEL.default_params(c).model_copy(update={"bend_angle_deg": 180})
    fixed, issues = clamp_params(TUNNEL, p, c)
    assert fixed.bend_angle_deg < 180 and end_side(fixed.bend_angle_deg) != "front"
    bend = [i for i in issues if i.details.get("field") == "bend_angle_deg"]
    assert bend and "U자" in bend[0].message_ko and f"{c.size.tunnel_max_length_mm:g}mm" in bend[0].message_ko
    # 최대 길이보다 짧은 터널에서 U자를 요청해도(예: '작은 U자 터널') 까닭을 밝힌다
    short = TunnelParams(length_mm=85, inner_diameter_mm=55, bend_angle_deg=180, wall_thickness_mm=3)
    _, issues2 = clamp_params(TUNNEL, short, c)
    msg = next(i.message_ko for i in issues2 if i.details.get("field") == "bend_angle_deg")
    assert "U자" in msg and "지금 길이로는" in msg
    # 최대 길이 안에서 닿는 각도면 일반 문구 (U자 언급 없음)
    reachable = TunnelParams(length_mm=85, inner_diameter_mm=55, bend_angle_deg=100, wall_thickness_mm=3)
    _, issues3 = clamp_params(TUNNEL, reachable, c)
    assert all("U자" not in i.message_ko for i in issues3)
    # 골든은 최대 길이 250mm 라 내경 70~75 에서 U자가 된다
    cs = ctx(rules, "syrian")
    u = TunnelParams(length_mm=250, inner_diameter_mm=75, bend_angle_deg=180, wall_thickness_mm=3)
    assert violated(TUNNEL, u, cs) == set()


def test_min_length_reason_when_max_wins(rules):
    """아주 넓은 드워프 터널: 내경 1.5배 대신 최대 길이까지만 요구하고, 메시지도 그렇게 말한다."""
    from app.validation.autofix import clamp_params

    c = ctx(rules, "dwarf")
    p = TunnelParams(length_mm=80, inner_diameter_mm=120, bend_angle_deg=0, wall_thickness_mm=3)
    fixed, issues = clamp_params(TUNNEL, p, c)
    assert fixed.length_mm == pytest.approx(c.size.tunnel_max_length_mm)
    msg = next(i.message_ko for i in issues if i.details.get("field") == "length_mm")
    assert "까지만 요구합니다" in msg


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_tunnel_wide_and_short_has_no_conflict(rules, size):
    """아주 넓은 터널이라도 '내경 1.5배 이상' 모양 기준이 최대 길이를 넘어서 요구하지 않는다 (복지 기준이 우선)."""
    from app.validation.autofix import clamp_params

    c = ctx(rules, size)
    p = TunnelParams(length_mm=600, inner_diameter_mm=130, bend_angle_deg=0, wall_thickness_mm=c.default_wall_mm)
    fixed, issues = clamp_params(TUNNEL, p, c)
    assert not [i for i in issues if i.code == "param_conflict"]
    assert fixed.length_mm <= c.size.tunnel_max_length_mm + 1e-6
    assert violated(TUNNEL, fixed, c) == set()


# ── 터널: 어항 (길이 상한 없음) ─────────────────────────────

AQUARIUM_SIZES = ("shrimp", "nano_fish", "small_fish", "community")


def aq_ctx(rules, size, count=1) -> RuleContext:
    return RuleContext(rules.size_rules("aquarium", size), rules.min_wall_for("aquarium", size), count)


@pytest.mark.parametrize("size", AQUARIUM_SIZES)
def test_aquarium_tunnel_defaults(rules, size):
    """어항 터널: 기본 길이는 내경의 6배(80~200mm), 길이 상한 제약이 없고, 기본값은 규칙을 지키며 출력할 수 있다."""
    c = aq_ctx(rules, size)
    p = TUNNEL.default_params(c)
    inner = math.ceil(c.size.tunnel_min_inner_diameter_mm + 5)
    assert p.inner_diameter_mm == inner
    assert p.length_mm == min(200, max(80, 6 * inner))
    assert p.wall_thickness_mm == c.default_wall_mm and p.bend_angle_deg == 0
    assert violated(TUNNEL, p, c) == set()
    assert_printable(TUNNEL, p)
    assert not [k for k in TUNNEL.constraints(p, c) if k.field == "length_mm" and k.max is not None]
    # 길이 상한이 없으니 긴 U자 터널도 된다
    long_u = p.model_copy(update={"length_mm": 600, "bend_angle_deg": 180})
    assert violated(TUNNEL, long_u, c) == set()
    wall = next(k for k in TUNNEL.constraints(p, c) if k.field == "wall_thickness_mm")
    assert wall.reason_ko == f"벽 두께는 최소 {c.min_wall_mm:g}mm 이상이어야 합니다 (물속 내구성·출력 기준)"


def test_aquarium_tunnel_reasons_do_not_mention_max_length(rules):
    from app.validation.autofix import clamp_params

    c = aq_ctx(rules, "small_fish")
    p = TunnelParams(length_mm=80, inner_diameter_mm=50, bend_angle_deg=180, wall_thickness_mm=3)
    fixed, issues = clamp_params(TUNNEL, p, c)
    assert not [i for i in issues if i.code == "param_conflict"]
    assert fixed.length_mm == 80 and fixed.bend_angle_deg < 180
    msgs = [i.message_ko for i in issues]
    assert any("굽힘이 너무 급하면" in m for m in msgs)
    assert all("최대 길이" not in m and "U자" not in m and "2배" not in m for m in msgs)
    # 아주 넓고 짧은 터널: 모양 기준(내경의 1.5배)을 그대로 요구한다
    wide = TunnelParams(length_mm=80, inner_diameter_mm=130, bend_angle_deg=0, wall_thickness_mm=3)
    fixed2, issues2 = clamp_params(TUNNEL, wide, c)
    assert fixed2.length_mm == pytest.approx(195)
    assert any(i.message_ko.endswith("터널 길이는 내경의 1.5배 이상이어야 합니다") for i in issues2)


@pytest.mark.parametrize("kw", [
    dict(length_mm=80, inner_diameter_mm=12, bend_angle_deg=0, wall_thickness_mm=2),
    dict(length_mm=150, inner_diameter_mm=20, bend_angle_deg=90, wall_thickness_mm=2),
])
def test_small_bore_tunnel_builds_printable(kw):
    """어항 크기(내경 15~20mm)의 가는 터널도 닫힌 메시로 서포트 없이 출력된다."""
    p = TunnelParams(**kw)
    m = assert_printable(TUNNEL, p, min_wall=p.wall_thickness_mm)
    assert m.extents[2] == pytest.approx(outer_height(p), abs=0.05)


# ── 램프 / 계단 ────────────────────────────────────────────


@pytest.mark.parametrize("kw", [
    dict(),
    dict(height_mm=20, width_mm=40, slope_deg=10, steps=0),
    dict(height_mm=200, width_mm=250, slope_deg=45, steps=0),
    dict(height_mm=90, width_mm=80, slope_deg=35, steps=3),
    dict(height_mm=150, width_mm=100, slope_deg=30, steps=12),
])
def test_ramp_builds_printable(kw):
    p = RampParams(**kw)
    m = assert_printable(RAMP, p)
    np.testing.assert_allclose(m.extents, [p.width_mm, run_length(p) + TOP_LANDING_MM, p.height_mm], atol=0.01)


def test_ramp_slope_angle_is_exact():
    p = RampParams(height_mm=80, slope_deg=25, steps=0)
    assert math.degrees(math.atan((p.height_mm - TOE_MM) / run_length(p))) == pytest.approx(25)


def test_ramp_has_grip_ridges_and_stairs_have_steps():
    smooth = part_to_mesh(RAMP.build(RampParams(height_mm=80, slope_deg=25, steps=0)))
    stairs = part_to_mesh(RAMP.build(RampParams(height_mm=80, slope_deg=25, steps=4)))
    up = lambda m: int(np.sum(m.face_normals[:, 2] > 0.999))  # noqa: E731 - 수평 윗면 삼각형 수
    assert up(smooth) > 6        # 턱 윗면들
    assert up(stairs) >= 2 * 4   # 디딤판 4개(각 2삼각형)


def test_ramp_features():
    f = RAMP.features(RampParams(height_mm=90, steps=3))
    assert f.climb_height_mm == 90 and f.step_height_mm == 30 and f.slope_deg is None
    f0 = RAMP.features(RampParams(height_mm=90, slope_deg=20, steps=0))
    assert f0.slope_deg == 20 and f0.step_height_mm is None


def test_ramp_constraints(rules):
    c = ctx(rules)
    s = rules.size_rules("hamster", "syrian")
    steep = RampParams(height_mm=180, width_mm=50, slope_deg=40, steps=0)
    assert {"height_mm", "width_mm", "slope_deg"} <= violated(RAMP, steep, c)
    stairs = RampParams(height_mm=120, width_mm=80, slope_deg=40, steps=1)
    cons = [k for k in RAMP.constraints(stairs, c) if k.field == "steps" and k.min is not None]
    assert cons[0].min == math.ceil(120 / s.max_step_height_mm)
    assert "slope_deg" not in violated(RAMP, stairs, c)  # 계단은 경사로 기준 대신 단 높이 기준


# ── 모래목욕통 ─────────────────────────────────────────────


@pytest.mark.parametrize("kw", [
    dict(),
    dict(width_mm=100, depth_mm=80, basin_depth_mm=20, lip_height_mm=15, wall_thickness_mm=3),
    dict(width_mm=350, depth_mm=300, basin_depth_mm=120, lip_height_mm=60, wall_thickness_mm=8),
])
def test_sand_bath_builds_printable(kw):
    p = SandBathParams(**kw)
    m = assert_printable(SAND, p, min_wall=min(3.0, p.wall_thickness_mm))
    np.testing.assert_allclose(m.extents, [p.width_mm, p.depth_mm, p.basin_depth_mm + p.wall_thickness_mm], atol=0.01)


def test_sand_bath_geometry():
    p = SandBathParams()
    part = SAND.build(p)
    t, D = p.wall_thickness_mm, p.depth_mm
    assert part.is_inside(Vector(0, 0, t / 2))                       # 바닥판
    assert not part.is_inside(Vector(0, 0, t + 5))                   # 모래 공간
    front = -D / 2 + t / 2
    assert not part.is_inside(Vector(0, front, p.lip_height_mm + 2))  # 출입 홈 (턱 위)
    assert part.is_inside(Vector(0, front, p.lip_height_mm - 2))      # 턱 아래는 벽
    assert part.is_inside(Vector(entry_width(p) / 2 + 3, front, p.lip_height_mm + 2))  # 홈 옆 벽


def test_sand_bath_constraints(rules):
    c = ctx(rules)
    s = rules.size_rules("hamster", "syrian")
    small = SandBathParams(width_mm=150, depth_mm=100, basin_depth_mm=30, lip_height_mm=60, wall_thickness_mm=2)
    assert {"width_mm", "depth_mm", "basin_depth_mm", "lip_height_mm", "wall_thickness_mm"} <= violated(SAND, small, c)
    d = SAND.default_params(c)
    assert violated(SAND, d, c) == set()
    assert d.width_mm - 2 * d.wall_thickness_mm >= s.sand_bath_min_inner_mm[0]


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
@pytest.mark.parametrize("template", [TUNNEL, RAMP, SAND])
def test_species_defaults_satisfy_rules(rules, template, size):
    c = ctx(rules, size)
    p = template.default_params(c)
    assert violated(template, p, c) == set()


# ── 공통: 벽 두께 제약 ─────────────────────────────────────


def _wall_rule(t, c):
    """기본 파라미터의 제약 목록에서 벽 두께 제약(하나뿐)과 그 위치를 돌려준다."""
    cons = t.constraints(t.default_params(c), c)
    idx = [i for i, k in enumerate(cons) if k.field == "wall_thickness_mm"]
    assert len(idx) == 1
    return cons[idx[0]], idx[0]


@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("size", ["dwarf", "syrian"])
@pytest.mark.parametrize("template", [HIDEOUT, SAND, TUNNEL], ids=lambda t: t.key)
def test_wall_thickness_rule_is_shared(rules, template, size, count):
    """은신처·모래목욕통·터널의 벽 두께 제약과 기본 벽 두께는 같은 문구·기준을 쓴다."""
    base = ctx(rules, size)
    c = RuleContext(base.size, base.min_wall_mm, count)
    w, pos = _wall_rule(template, c)
    assert w.reason_ko == f"벽 두께는 최소 {c.min_wall_mm:g}mm 이상이어야 합니다 (갉음 내구성·출력 기준)"
    assert w.min == c.min_wall_mm
    assert w.max is None
    # 저장소 규칙에서는 종 갉음 기준이 출력 최소 벽보다 두껍다
    assert w.source == "species"
    # 은신처는 여러 마리 규칙(출입구 개수) 바로 뒤, 나머지는 첫 원소
    assert pos == (1 if template is HIDEOUT and c.hideout_min_entrances > 1 else 0)
    assert template.default_params(c).wall_thickness_mm == max(3.0, c.min_wall_mm)

    # 출력 기준이 종 기준보다 두꺼우면 출처는 printing
    cp = RuleContext(c.size, c.size.min_wall_thickness_mm + 1)
    wp, _ = _wall_rule(template, cp)
    assert wp.source == "printing"
    assert wp.min == cp.min_wall_mm
    assert wp.reason_ko == f"벽 두께는 최소 {cp.min_wall_mm:g}mm 이상이어야 합니다 (갉음 내구성·출력 기준)"
    assert template.default_params(cp).wall_thickness_mm == max(3.0, cp.min_wall_mm)


def test_out_of_range_rejected():
    for cls, kw in [(TunnelParams, dict(inner_diameter_mm=5)), (RampParams, dict(steps=50)),
                    (SandBathParams, dict(lid=True))]:
        with pytest.raises(ValidationError):
            cls(**kw)
