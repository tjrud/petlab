from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
from build123d import Vector
from pydantic import ValidationError

from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.templates.base import RuleContext
from app.templates.hideout import HideoutParams, HideoutTemplate, vent_positions

T = HideoutTemplate()


def _mesh(p: HideoutParams):
    return part_to_mesh(T.build(p))


def test_default_is_watertight_and_valid():
    p = HideoutParams()
    part = T.build(p)
    assert part.is_valid
    h = mesh_health(part_to_mesh(part))
    assert h.ok, h


@pytest.mark.parametrize(
    "kwargs",
    [
        # 최소 경계 조합
        dict(width_mm=60, depth_mm=60, height_mm=50, entrance_diameter_mm=25,
             vent_count=0, vent_diameter_mm=2, wall_thickness_mm=1.0),
        # 최대 경계 조합
        dict(width_mm=350, depth_mm=350, height_mm=250, entrance_diameter_mm=150,
             vent_count=30, vent_diameter_mm=10, wall_thickness_mm=8),
        # 시리안 기준 전형값
        dict(width_mm=200, depth_mm=150, height_mm=120, entrance_diameter_mm=75,
             vent_count=9, vent_diameter_mm=5, wall_thickness_mm=3),
        # 길쭉한 형태
        dict(width_mm=300, depth_mm=90, height_mm=80, entrance_diameter_mm=55,
             vent_count=4, vent_diameter_mm=4, wall_thickness_mm=2.4),
    ],
)
def test_parameter_range_builds_watertight(kwargs):
    p = HideoutParams(**kwargs)
    m = _mesh(p)
    assert mesh_health(m).ok
    lo, hi = m.bounds
    np.testing.assert_allclose(hi - lo, [p.width_mm, p.depth_mm, p.height_mm], atol=0.01)
    # 바닥 Z=0, XY 중심 원점
    assert abs(lo[2]) < 1e-6
    np.testing.assert_allclose((lo[:2] + hi[:2]) / 2, [0, 0], atol=1e-6)


def test_volume_matches_analytic_openings():
    """출입구·환기구가 정확히 뚫렸는지 해석적 부피와 비교."""
    p = HideoutParams(width_mm=150, depth_mm=120, height_mm=100, entrance_diameter_mm=60,
                      vent_count=6, vent_diameter_mm=4, wall_thickness_mm=3)
    W, D, H, t, d = p.width_mm, p.depth_mm, p.height_mm, p.wall_thickness_mm, p.entrance_diameter_mm
    r = d / 2
    shell = W * D * H - (W - 2 * t) * (D - 2 * t) * (H - t)
    entrance = t * (d * r + math.pi * r**2 / 2)
    vents = p.vent_count * math.pi * (p.vent_diameter_mm / 2) ** 2 * t
    expected = shell - entrance - vents
    actual = T.build(p).volume
    assert actual == pytest.approx(expected, rel=2e-3)


def test_entrance_and_vents_are_open():
    p = HideoutParams()
    part = T.build(p)
    t, r, D, H = p.wall_thickness_mm, p.entrance_diameter_mm / 2, p.depth_mm, p.height_mm
    front_wall_y = -D / 2 + t / 2
    # 출입구 중앙(직사각형 부분과 아치 부분)은 비어 있어야 한다
    assert not part.is_inside(Vector(0, front_wall_y, r * 0.5))
    assert not part.is_inside(Vector(0, front_wall_y, r * 1.9))
    # 출입구 옆 벽은 채워져 있어야 한다
    assert part.is_inside(Vector(p.width_mm / 2 - t / 2, front_wall_y, r))
    # 출입구 위 벽도 채워져 있어야 한다 (아치 위 여유)
    assert part.is_inside(Vector(0, front_wall_y, (2 * r + H - t) / 2))
    # 환기구 중심은 비어 있어야 하고 지붕의 다른 곳은 채워져 있어야 한다
    for x, y in vent_positions(p):
        assert not part.is_inside(Vector(x, y, H - t / 2))
    assert part.is_inside(Vector(p.width_mm / 2 - 2 * t, p.depth_mm / 2 - 2 * t, H - t / 2))
    # 바닥은 열려 있다
    assert not part.is_inside(Vector(0, 0, 0.5))


def test_vent_positions_fit_roof_and_keep_spacing():
    p = HideoutParams(width_mm=200, depth_mm=150, vent_count=11, vent_diameter_mm=5)
    pts = vent_positions(p)
    assert len(pts) == 11
    margin = p.wall_thickness_mm + p.vent_diameter_mm / 2
    for x, y in pts:
        assert abs(x) <= p.width_mm / 2 - margin
        assert abs(y) <= p.depth_mm / 2 - margin
    for (x1, y1), (x2, y2) in itertools.combinations(pts, 2):
        assert math.hypot(x1 - x2, y1 - y2) >= 3 * p.vent_diameter_mm - 1e-6


def test_too_many_vents_raises():
    p = HideoutParams(width_mm=60, depth_mm=60, vent_count=30, vent_diameter_mm=10)
    with pytest.raises(ValueError, match="환기구"):
        vent_positions(p)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(width_mm=10),
        dict(height_mm=1000),
        dict(entrance_diameter_mm=-5),
        dict(vent_count=2.5),
        dict(wall_thickness_mm=0.2),
        dict(roof_style="dome"),  # 알 수 없는 키
    ],
)
def test_out_of_range_rejected(kwargs):
    with pytest.raises(ValidationError):
        HideoutParams(**kwargs)


def test_species_constraints_detect_violations(rules):
    ctx = RuleContext(rules.size_rules("hamster", "syrian"), rules.min_wall_for("hamster", "syrian"))
    p = HideoutParams(entrance_diameter_mm=50, vent_diameter_mm=8, wall_thickness_mm=1.2)
    violated = {c.field for c in T.constraints(p, ctx) if c.violates(getattr(p, c.field))}
    assert {"entrance_diameter_mm", "vent_diameter_mm", "wall_thickness_mm"} <= violated


def test_species_constraints_pass_for_good_params(rules):
    ctx = RuleContext(rules.size_rules("hamster", "syrian"), rules.min_wall_for("hamster", "syrian"))
    p = HideoutParams(width_mm=200, depth_mm=150, height_mm=120, entrance_diameter_mm=75,
                      vent_count=6, vent_diameter_mm=5, wall_thickness_mm=3)
    violated = [c for c in T.constraints(p, ctx) if c.violates(getattr(p, c.field))]
    assert violated == []


def test_print_orientation_puts_roof_on_bed():
    p = HideoutParams()
    m = to_print_orientation(_mesh(p), T.print_rotation(p))
    lo, hi = m.bounds
    assert abs(lo[2]) < 1e-6
    np.testing.assert_allclose(hi - lo, [p.width_mm, p.depth_mm, p.height_mm], atol=0.01)
    # 베드에 닿는 하향 면적 ≈ 지붕 면적 - 환기구 면적
    down = m.face_normals[:, 2] < -0.999
    on_bed = np.all(np.abs(m.vertices[m.faces][:, :, 2]) < 1e-6, axis=1)
    bed_area = m.area_faces[down & on_bed].sum()
    vent_area = p.vent_count * math.pi * (p.vent_diameter_mm / 2) ** 2
    assert bed_area == pytest.approx(p.width_mm * p.depth_mm - vent_area, rel=1e-2)


def test_features():
    f = T.features(HideoutParams(vent_count=0))
    assert f.access_sides == ("front",)
    assert [o.kind for o in f.openings] == ["passage"]
    f2 = T.features(HideoutParams(vent_count=4))
    assert {o.kind for o in f2.openings} == {"passage", "vent"}
