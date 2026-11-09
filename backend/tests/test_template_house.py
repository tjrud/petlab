"""조립형 집 템플릿: 부품 조합별 생성·출력성·특징·결정성, 종별 기본값, 호환 불가 조합."""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest
from pydantic import ValidationError

from app.domain import Cage, PlacementHint
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.services.engine import EngineContext, ItemSpec, build_item, run_engine
from app.templates.base import RuleContext
from app.templates.house import HouseParams, HouseTemplate, is_cap, roof_rise
from app.templates.parts.common import arch_height
from app.templates.parts.levels import LANDING_MM, PORCH_MM, run_length
from app.validation.autofix import clamp_params
from app.validation.checks import measure_thickness, overhang_area

T = HouseTemplate()

COMBOS = {
    "flat_1f": {},
    "flat_1f_floor": {"floor": {"enabled": True}},
    "pitched_1f": {"roof": {"kind": "pitched", "pitch_deg": 50}},
    "rounded_1f": {"roof": {"kind": "rounded", "tip_deg": 55}},
    "two_internal": {"floors": {"count": 2, "climb": "internal_ramp"}},
    "two_external": {"floors": {"count": 2, "climb": "external_ramp", "exit_side": "back"}},
    "two_internal_pitched_floor": {"floors": {"count": 2}, "roof": {"kind": "pitched"}, "floor": {"enabled": True}},
    "port": {"ports": {"sides": ["left"]}},
    "two_doors": {"doors": {"sides": ["front", "back"]}},
    "windows4": {"windows": {"count": 4}},
}
EXPECTED_PARTS = {
    "flat_1f": ["body"], "flat_1f_floor": ["body", "floor"], "pitched_1f": ["body", "roof"],
    "rounded_1f": ["body", "roof"], "two_internal": ["body", "roof", "floor2"], "two_external": ["body", "roof", "floor2"],
    "two_internal_pitched_floor": ["body", "roof", "floor2"], "port": ["body"], "two_doors": ["body"], "windows4": ["body"],
}


def ctx(rules, size="syrian", count=1) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), count,
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def params_for(rules, name: str, size="syrian") -> HouseParams:
    """기본값에 조합을 덮어쓰고 종 규칙·상호 제약으로 보정한 파라미터 (오류 없이 보정되어야 한다)."""
    c = ctx(rules, size)
    d = T.default_params(c).model_dump()
    for k, v in COMBOS[name].items():
        d[k].update(v)
    p, issues = clamp_params(T, HouseParams(**d), c)
    assert not [i for i in issues if i.code == "param_conflict"], issues
    return p


@pytest.mark.parametrize("name", list(COMBOS))
def test_combo_builds_watertight_and_printable(rules, name):
    """조합마다: 조립 형상·파트 모두 watertight, 파트별 출력 자세 오버행 없음, 벽 두께 실측 ≥ 최소."""
    p = params_for(rules, name)
    printing = rules.printing
    parts = T.print_parts(p)
    assert [pp.key for pp in parts] == EXPECTED_PARTS[name]
    assembled = part_to_mesh(T.build(p))
    assert mesh_health(assembled).ok
    lo, hi = assembled.bounds
    assert abs(lo[2]) < 1e-6
    assert hi[2] == pytest.approx(p.height_mm, abs=0.05)
    for pp in parts:
        m = part_to_mesh(pp.part)
        assert mesh_health(m).ok, pp.key
        pm = to_print_orientation(m, pp.rotation)
        assert overhang_area(pm, printing.max_overhang_deg) < 1.0, pp.key
        assert np.percentile(measure_thickness(m), 1) >= 0.9 * rules.min_wall_for("hamster", "syrian"), pp.key


@pytest.mark.parametrize("name", list(COMBOS))
def test_features_match_params(rules, name):
    p = params_for(rules, name)
    f = T.features(p)
    passages = [o for o in f.openings if o.kind == "passage"]
    vents = [o for o in f.openings if o.kind == "vent"]
    n_doors = len(p.doors.sides) + (1 if p.floors.count == 2 and p.floors.climb == "external_ramp" else 0)
    assert len(passages) == n_doors + len(p.ports.sides)
    assert all(o.size_mm == p.doors.width_mm for o in passages if o.rule_key == "entrance_min_diameter_mm")
    assert all(o.size_mm == p.ports.diameter_mm for o in passages if o.rule_key == "tunnel_min_inner_diameter_mm")
    assert len(vents) == (1 if p.windows.count else 0)
    assert set(f.access_sides) == set(p.doors.sides) | set(p.ports.sides)
    assert f.entrance_count == len(p.doors.sides) + len(p.ports.sides)
    assert f.min_wall_thickness_mm == pytest.approx(min(p.walls.thickness_mm, p.floor.thickness_mm if p.floor.enabled else 99,
                                                         p.floors.plate_thickness_mm if p.floors.count == 2 else 99))
    if p.floors.count == 2:
        assert f.climb_height_mm == p.floors.level_height_mm
        if p.floors.climb == "internal_ramp":
            assert f.slope_deg == p.floors.slope_deg and "attach_side" not in f.extra
        else:
            assert f.slope_deg is None
            assert f.extra["attach_side"] == p.floors.exit_side
            assert f.extra["landing_height_mm"] == p.floors.level_height_mm
            assert p.floors.exit_side not in f.access_sides
    else:
        assert f.climb_height_mm is None and f.slope_deg is None
    assert f.extra["part_count"] == len(EXPECTED_PARTS[name])


def test_same_params_give_identical_stl_bytes(rules):
    p = params_for(rules, "two_internal_pitched_floor")
    a = build_item(0, T, p, PlacementHint(), rules.printing)
    b = build_item(0, T, copy.deepcopy(p), PlacementHint(), rules.printing)
    assert a.mesh.export(file_type="stl") == b.mesh.export(file_type="stl")
    assert [x.key for x in a.parts] == [x.key for x in b.parts]
    for x, y in zip(a.parts, b.parts):
        assert x.print_mesh.export(file_type="stl") == y.print_mesh.export(file_type="stl")


def test_assembled_volume_equals_sum_of_parts(rules):
    """파트는 서로 겹치지 않게 밀착 조립된다: 조립 형상 부피 = 파트 부피 합."""
    for name in ("two_external", "rounded_1f", "flat_1f_floor"):
        p = params_for(rules, name)
        parts = T.print_parts(p)
        total = sum(pp.part.volume for pp in parts)
        assert T.build(p).volume == pytest.approx(total, rel=1e-4), name


def test_external_porch_and_upper_door(rules):
    p = params_for(rules, "two_external")
    m = part_to_mesh(T.build(p))
    # 착지판이 뒷면 바깥으로 튀어나와 세로가 PORCH 만큼 길다 (벽 안으로 0.5 겹친 몫과 스커트 두께 제외)
    assert m.extents[1] == pytest.approx(p.depth_mm - p.walls.thickness_mm + PORCH_MM, abs=0.1)
    # 착지판 윗면 = 2층 바닥 높이: 뒷벽 바깥 가운데 점이 그 높이 바로 아래는 채워져 있고 위는 비어 있다
    y_out = p.depth_mm / 2 - p.walls.thickness_mm + PORCH_MM / 2
    assert m.contains([[0, y_out, p.floors.level_height_mm - 1]])[0]
    assert not m.contains([[0, y_out, p.floors.level_height_mm + 2]])[0]
    # 2층 출입구가 뒷벽에 뚫려 있다
    wall_y = p.depth_mm / 2 - 1.5 * p.walls.thickness_mm
    assert not m.contains([[0, wall_y, p.floors.level_height_mm + p.doors.width_mm / 2]])[0]


def test_internal_ramp_geometry(rules):
    p = params_for(rules, "two_internal")
    m = part_to_mesh(T.print_parts(p)[0].part)
    t = p.walls.thickness_mm
    inset = t if is_cap(p) else 0
    x1 = p.width_mm / 2 - inset - t
    y_ramp = p.depth_mm / 2 - inset - t - p.floors.ramp_width_mm / 2
    lvl = p.floors.level_height_mm
    # 꼭대기 발판: 오른쪽 벽 바로 안쪽, 2층 바닥 높이까지 채워짐
    assert m.contains([[x1 - LANDING_MM / 2, y_ramp, lvl - 1]])[0]
    assert not m.contains([[x1 - LANDING_MM / 2, y_ramp, lvl + 2]])[0]
    # 경사로 중간 높이는 경사각을 따른다
    L = run_length(lvl, 0.0, p.floors.slope_deg)
    x_mid = x1 - LANDING_MM - L / 2
    z_mid = (lvl + 4) / 2
    assert m.contains([[x_mid, y_ramp, z_mid - 3]])[0] and not m.contains([[x_mid, y_ramp, z_mid + 6]])[0]
    # 층판은 경사로 띠를 덮지 않는다
    plate = part_to_mesh(T.print_parts(p)[2].part)
    assert plate.bounds[1][1] == pytest.approx(p.depth_mm / 2 - inset - t - p.floors.ramp_width_mm, abs=1e-6)


def test_roof_rise_and_eave(rules):
    p = params_for(rules, "pitched_1f")
    assert roof_rise(p) > 0 and p.height_mm > roof_rise(p)
    flat = params_for(rules, "flat_1f")
    assert roof_rise(flat) == 0 and not is_cap(flat)
    assert is_cap(params_for(rules, "two_internal"))  # 2층 평 지붕은 뚜껑


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_species_defaults_pass_validate_all(rules, size):
    c = EngineContext(Cage(900, 500, 400), "hamster", size, 1, rules)
    d = T.default_params(c.rule_ctx)
    violated = [k for k in T.constraints(d, c.rule_ctx) if k.violates(_get(d, k.field))]
    assert violated == []
    res = run_engine([ItemSpec("house", d.model_dump())], c)
    assert res.report.passed, res.report.errors
    assert [p.key for p in res.items[0].print_parts] == ["body"]
    assert res.items[0].features.openings[0].size_mm >= c.size_rules.entrance_min_diameter_mm


def _get(p, path):
    v = p
    for name in path.split("."):
        v = getattr(v, name)
    return v


def test_two_floors_in_low_cage_conflicts(rules):
    """2층인데 높이가 모자라면(케이지 천장 한도) 명확한 오류."""
    c = EngineContext(Cage(900, 500, 200), "hamster", "syrian", 1, rules)
    d = T.default_params(c.rule_ctx).model_dump()
    d["floors"].update(count=2)
    res = run_engine([ItemSpec("house", d)], c)
    conflicts = [i for i in res.report.issues if i.code == "param_conflict"]
    assert conflicts and conflicts[0].details["field"] == "height_mm"
    assert not res.report.passed


def test_duplicate_or_clashing_sides_rejected():
    with pytest.raises(ValidationError, match="같은 면"):
        HouseParams(doors={"sides": ["front", "front"]})
    with pytest.raises(ValidationError, match="함께 낼 수 없습니다"):
        HouseParams(doors={"sides": ["front"]}, ports={"sides": ["front"]})
    with pytest.raises(ValidationError, match="램프가 앞을 막는다"):
        HouseParams(floors={"count": 2, "climb": "external_ramp", "exit_side": "front"})
    with pytest.raises(ValidationError):
        HouseParams(roof={"kind": "dome"})
    with pytest.raises(ValidationError):
        HouseParams(chimney=True)


def test_small_port_is_widened_to_tunnel_minimum(rules):
    c = ctx(rules)
    d = T.default_params(c).model_dump()
    d["ports"].update(sides=["left"], diameter_mm=40)
    p, issues = clamp_params(T, HouseParams(**d), c)
    assert p.ports.diameter_mm == c.size.tunnel_min_inner_diameter_mm
    adj = [i for i in issues if i.details.get("field") == "ports.diameter_mm"]
    assert adj and adj[0].code == "param_adjusted" and "연결부 아치 폭" in adj[0].message_ko


def test_pitch_below_overhang_limit_is_raised(rules):
    c = ctx(rules)
    d = T.default_params(c).model_dump()
    d["roof"].update(kind="pitched", pitch_deg=45)
    p, issues = clamp_params(T, HouseParams(**d), c)
    assert p.roof.pitch_deg == pytest.approx(90 - rules.printing.max_overhang_deg + 1)
    assert any(i.details.get("field") == "roof.pitch_deg" for i in issues)


def test_arch_height_is_pointed(rules):
    assert arch_height(70) > 70  # 뾰족 아치는 폭보다 높다 (반지름 + 반지름/cos50°)


def test_stored_params_roundtrip():
    p = HouseParams(floors={"count": 2, "climb": "external_ramp"}, windows={"count": 2})
    assert T.load_stored_params(json.loads(p.model_dump_json())) == p
