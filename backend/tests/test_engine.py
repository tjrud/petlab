"""엔진(파라미터 보정 → 형상 → 배치 → 공간 보정 → 검증) 통합 테스트."""

from __future__ import annotations

import pytest

from app.domain import Cage, PlacementHint
from app.services.engine import EngineContext, ItemSpec, run_engine


def ctx(rules, cage=Cage(600, 400, 300), size="syrian", count=1):
    return EngineContext(cage=cage, species="hamster", size=size, count=count, rules=rules)


def by_code(report, code):
    return [i for i in report.issues if i.code == code]


def test_good_design_passes(rules):
    spec = ItemSpec("hideout", dict(width_mm=200, depth_mm=150, height_mm=120,
                                    entrance_diameter_mm=75, vent_count=6, vent_diameter_mm=5,
                                    wall_thickness_mm=3), PlacementHint(zone="left"))
    res = run_engine([spec], ctx(rules))
    assert res.report.passed, res.report.issues
    assert res.items[0].placement is not None


def test_species_violations_are_auto_fixed(rules):
    """드워프용 값(출입구 50, 환기구 8, 벽 1.2)을 시리안에 쓰면 규칙에 맞게 자동 보정된다."""
    spec = ItemSpec("hideout", dict(entrance_diameter_mm=50, vent_diameter_mm=8, wall_thickness_mm=1.2))
    res = run_engine([spec], ctx(rules))
    fixed = {i.details["field"]: i.details["to"] for i in by_code(res.report, "param_adjusted")}
    s = rules.size_rules("hamster", "syrian")
    assert fixed["entrance_diameter_mm"] == s.entrance_min_diameter_mm
    assert fixed["vent_diameter_mm"] == s.gap_trap.safe_max_mm
    assert fixed["wall_thickness_mm"] == rules.min_wall_for("hamster", "syrian")
    assert all(i.auto_fixed for i in by_code(res.report, "param_adjusted"))
    assert res.report.passed, res.report.errors
    p = res.items[0].params
    assert p.height_mm >= p.entrance_diameter_mm + 2 * p.wall_thickness_mm  # 연쇄 보정


def test_height_clamped_to_cage(rules):
    cage = Cage(600, 400, 180)
    res = run_engine([ItemSpec("hideout", dict(height_mm=200, entrance_diameter_mm=75))], ctx(rules, cage))
    P = rules.size_rules("hamster", "syrian").gap_trap.passable_min_mm
    assert res.items[0].params.height_mm == pytest.approx(cage.height_mm - P)
    assert res.report.passed, res.report.errors


def test_resized_to_fit_small_cage(rules):
    cage = Cage(260, 230, 300)
    spec = ItemSpec("hideout", dict(width_mm=300, depth_mm=250, height_mm=150, entrance_diameter_mm=75))
    res = run_engine([spec], ctx(rules, cage))
    assert by_code(res.report, "resized_to_fit")
    assert res.items[0].placement is not None
    assert res.report.passed, res.report.errors


@pytest.mark.parametrize("count,doors", [(1, 1), (2, 2), (3, 2)])
def test_hideout_entrances_follow_animal_count(rules, count, doors):
    """혼자면 출입구 1개(추가 요구 없음), 여러 마리면 DTSchB 근거로 2개."""
    res = run_engine([ItemSpec("hideout", dict(entrance_diameter_mm=75))], ctx(rules, count=count))
    assert res.items[0].params.entrance_count == doors
    assert res.report.passed, res.report.errors


def test_single_door_hideout_raised_for_group_with_notice(rules):
    res = run_engine([ItemSpec("hideout", dict(entrance_diameter_mm=75, entrance_count=1))], ctx(rules, count=2))
    assert res.items[0].params.entrance_count == 2
    fixed = [i for i in by_code(res.report, "param_adjusted") if i.details.get("field") == "entrance_count"]
    assert fixed and fixed[0].auto_fixed and "2마리" in fixed[0].message_ko


def test_impossible_cage_reports_error(rules):
    cage = Cage(120, 120, 300)  # 시리안 은신처 + 출입구 앞 공간이 들어갈 수 없음
    res = run_engine([ItemSpec("hideout", dict(entrance_diameter_mm=75))], ctx(rules, cage))
    assert not res.report.passed
    assert by_code(res.report, "cannot_place")


def test_conflicting_constraints_reported(rules):
    cage = Cage(600, 400, 130)  # 높이 한도 130-70=60 < 최소 높이 75+2*3=81
    res = run_engine([ItemSpec("hideout", dict(entrance_diameter_mm=75))], ctx(rules, cage))
    assert by_code(res.report, "param_conflict")
    assert not res.report.passed


def test_unknown_template_and_invalid_params(rules):
    res = run_engine([ItemSpec("castle", {}), ItemSpec("hideout", {"width_mm": 5})], ctx(rules))
    assert [i.code for i in res.report.errors][:2] == ["unknown_template", "invalid_params"]


def test_count_warning_does_not_block(rules):
    res = run_engine([ItemSpec("hideout", dict(entrance_diameter_mm=75))], ctx(rules, count=2))
    assert by_code(res.report, "count_exceeds")
    assert res.report.passed


def test_all_four_templates_in_one_cage(rules):
    """네 가지 템플릿을 한 케이지에 넣어도 배치·검증을 통과한다."""
    from app.templates.registry import get_template

    c = ctx(rules, Cage(1000, 500, 400))
    specs = [
        ItemSpec(k, get_template(k).default_params(c.rule_ctx).model_dump(), PlacementHint(zone=z))
        for k, z in [("hideout", "left"), ("tunnel", "back"), ("ramp", "right"), ("sand_bath", "front")]
    ]
    res = run_engine(specs, c)
    assert res.report.passed, res.report.errors
    assert all(it.placement is not None for it in res.items)


def test_mixed_grouped_design_from_mock(rules):
    """'은신처와 터널을 한쪽에 몰아서' → 두 구조물이 같은 그룹으로 서로 붙어 배치된다."""
    from app.llm.base import HabitatInfo, InterpretRequest
    from app.llm.mock import MockInterpreter
    from app.llm.spec import to_item_specs

    cage = Cage(800, 500, 400)
    req = InterpretRequest(
        prompt="은신처와 터널을 한쪽에 몰아서 넣고 싶어요",
        habitat=HabitatInfo("hamster", "햄스터", "syrian", 1, cage),
        size_rules=rules.size_rules("hamster", "syrian"),
        min_wall_mm=rules.min_wall_for("hamster", "syrian"),
    )
    spec = MockInterpreter().interpret(req).spec
    assert [it.template for it in spec.items] == ["hideout", "tunnel"]
    assert {it.placement.group for it in spec.items} == {"g1"}
    res = run_engine(to_item_specs(spec), ctx(rules, cage))
    assert res.report.passed, res.report.errors
    a, b = res.items
    assert a.world_footprint.distance(b.world_footprint) == pytest.approx(0, abs=0.5)
    assert max(a.world_rect.cx, b.world_rect.cx) < cage.width_mm / 2  # 한쪽(왼쪽)에 모임
