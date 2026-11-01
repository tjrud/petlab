"""터널·램프/계단·모래목욕통 템플릿 테스트 (은신처와 같은 기준 + 무서포트 출력)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from build123d import Vector
from pydantic import ValidationError

from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.templates.base import RuleContext
from app.templates.ramp import TOE_MM, TOP_LANDING_MM, RampParams, RampTemplate, run_length
from app.templates.sand_bath import SandBathParams, SandBathTemplate, entry_width
from app.templates.tunnel import TunnelParams, TunnelTemplate, end_side, outer_height
from app.validation.checks import measure_thickness, overhang_area

TUNNEL, RAMP, SAND = TunnelTemplate(), RampTemplate(), SandBathTemplate()


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
    good = TunnelParams(length_mm=300, inner_diameter_mm=75, bend_angle_deg=90, wall_thickness_mm=3)
    assert violated(TUNNEL, good, c) == set()


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


def test_out_of_range_rejected():
    for cls, kw in [(TunnelParams, dict(inner_diameter_mm=5)), (RampParams, dict(steps=50)),
                    (SandBathParams, dict(lid=True))]:
        with pytest.raises(ValidationError):
            cls(**kw)
