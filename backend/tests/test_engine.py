"""엔진(파라미터 보정 → 형상 → 배치 → 공간 보정 → 검증) 통합 테스트."""

from __future__ import annotations

import pytest

from app.domain import Cage, Placement, PlacementHint
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.base import ParamConstraint
from app.templates.registry import get_template
from app.validation.autofix import clamp_params, constraint_violations


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


# ── 엔진 배치 결과 고정 (골든) ─────────────────────────────
# 실제 템플릿 형상으로 배치한 좌표를 Placement 로 정확히(==) 비교한다. 값은 uv.lock 의 OCP 테셀레이션에
# 따른 것이라, 템플릿 build() 를 의도적으로 바꾸면 이 값을 다시 뽑아야 한다.


def _placements(items):
    return {it.index: it.placement for it in items}


def _defaults(key, c, **kw):
    return {**get_template(key).default_params(c.rule_ctx).model_dump(), **kw}


def test_golden_engine_placements(rules):
    c = ctx(rules, Cage(1000, 500, 400))
    four = [ItemSpec(k, _defaults(k, c), PlacementHint(zone=z))
            for k, z in [("hideout", "left"), ("tunnel", "back"), ("ramp", "right"), ("sand_bath", "front")]]
    assert _placements(run_engine(four, c, measure_thickness=False).items) == {
        0: Placement(65.5, 250.0, 90), 1: Placement(500.0, 459.5, 90),
        2: Placement(919.9538057742676, 250.0, 270), 3: Placement(500.0, 108.0, 180)}

    c = ctx(rules, Cage(800, 500, 400))
    grouped = [ItemSpec("hideout", _defaults("hideout", c), PlacementHint(group="g1")),
               ItemSpec("tunnel", _defaults("tunnel", c, bend_angle_deg=90), PlacementHint(group="g1")),
               ItemSpec("ramp", _defaults("ramp", c))]
    assert _placements(run_engine(grouped, c, measure_thickness=False).items) == {
        0: Placement(233.323954, 262.17604600000004, 90),
        1: Placement(83.91197723675813, 416.0880232367581, 90),
        2: Placement(719.9538057742676, 460.0, 270)}

    c = ctx(rules, Cage(600, 400, 300), size="dwarf", count=2)
    pair = [ItemSpec("hideout", _defaults("hideout", c), PlacementHint(zone="back_left")),
            ItemSpec("tunnel", _defaults("tunnel", c, bend_angle_deg=180), PlacementHint(zone="front")),
            ItemSpec("sand_bath", _defaults("sand_bath", c))]
    assert _placements(run_engine(pair, c, measure_thickness=False).items) == {
        0: Placement(70.0, 294.5, 0), 1: Placement(300.0000002367581, 47.08098861837907, 180),
        2: Placement(492.0, 292.0, 270)}

    # 공간 보정(_shrink_to_fit)이 같은 항목 객체로 place_all 을 여러 번 부르는 경로
    c = ctx(rules, Cage(260, 230, 300))
    spec = ItemSpec("hideout", {"width_mm": 300, "depth_mm": 250, "height_mm": 150, "entrance_diameter_mm": 75})
    res = run_engine([spec], c, measure_thickness=False)
    assert [i.code for i in by_code(res.report, "resized_to_fit")] == ["resized_to_fit"]
    assert _placements(res.items) == {0: Placement(90.0, 155.0, 0)}


# ── 자동 보정 이슈 문구·세부값 고정 ─────────────────────────
# message_ko 와 details(키 순서, int/float 구분 포함)를 그대로 고정한다. repr 로 비교해 90 과 90.0 을 구별한다.


def test_wall_adjusted_issue_is_stable(rules):
    res = run_engine([ItemSpec("hideout", {"entrance_diameter_mm": 75, "wall_thickness_mm": 1.2})], ctx(rules))
    [i] = by_code(res.report, "param_adjusted")
    assert i.message_ko == ("은신처 #1: 벽·지붕 두께 1.2 → 3 로 보정했습니다. "
                            "벽 두께는 최소 3mm 이상이어야 합니다 (갉음 내구성·출력 기준)")
    assert repr(i.details) == "{'field': 'wall_thickness_mm', 'from': 1.2, 'to': 3.0}"
    assert i.auto_fixed and i.item_index == 0


def test_cage_height_conflict_issue_is_stable(rules):
    """높이 130 케이지: 천장 기준으로 낮춘 높이가 출입구 기준 최소 높이와 충돌한다."""
    res = run_engine([ItemSpec("hideout", {"entrance_diameter_mm": 75})], ctx(rules, Cage(600, 400, 130)))
    [adj] = by_code(res.report, "param_adjusted")
    assert adj.message_ko == ("은신처 #1: 외형 높이(Z) 90 → 60 로 보정했습니다. "
                              "케이지 천장과의 틈에 끼이지 않도록 높이를 60mm(천장 높이 − 70mm) 이하로 맞췄습니다.")
    assert repr(adj.details) == "{'field': 'height_mm', 'from': 90, 'to': 60.0}"
    [conf] = by_code(res.report, "param_conflict")
    assert conf.message_ko == ("은신처 #1: 외형 높이(Z) 조건을 만족시킬 수 없습니다. "
                               "출입구 아치 위로 벽이 남도록 높이가 출입구보다 커야 합니다")
    assert repr(conf.details) == "{'field': 'height_mm', 'value': 60.0, 'min': 81.0, 'max': None}"
    assert not conf.auto_fixed and conf.item_index == 0


def test_contradictory_extra_constraints_issue_is_stable(rules):
    """같은 필드에 서로 모순되는 제약: 한 패스 안에서 뒤 제약이 앞 제약이 바꾼 값을 보고 다시 옮긴다."""
    ramp = get_template("ramp")
    extra = [ParamConstraint("width_mm", min=100, reason_ko="A"), ParamConstraint("width_mm", max=90, reason_ko="B")]
    p, issues = clamp_params(ramp, ramp.Params(), ctx(rules).rule_ctx, extra)
    assert p.width_mm == 90
    assert [i.code for i in issues] == ["param_adjusted", "param_conflict"]
    adj, conf = issues
    assert adj.message_ko == "램프/계단: 폭 80 → 90 로 보정했습니다. B"
    assert repr(adj.details) == "{'field': 'width_mm', 'from': 80, 'to': 90}"
    assert conf.message_ko == "램프/계단: 폭 조건을 만족시킬 수 없습니다. A"
    assert repr(conf.details) == "{'field': 'width_mm', 'value': 90.0, 'min': 100, 'max': None}"


def test_out_of_range_issue_is_stable(rules):
    hideout = get_template("hideout")
    p = hideout.Params(entrance_diameter_mm=60, wall_thickness_mm=3)
    [i] = constraint_violations(hideout, p, ctx(rules).rule_ctx, item_index=0, label_ko="은신처 #1")
    assert i.code == "param_out_of_range"
    assert i.message_ko == ("은신처 #1: 아치형 출입구 폭(=높이) 60 이(가) 지금 기준 허용 범위를 벗어납니다. "
                            "골든 (시리안) 출입구는 최소 70mm 이상이어야 합니다")
    assert repr(i.details) == "{'field': 'entrance_diameter_mm', 'value': 60.0, 'min': 70.0, 'max': None}"
    assert not i.auto_fixed and i.item_index == 0


@pytest.mark.parametrize("start,rule,expected", [
    (0, ParamConstraint("steps", min=2.3, reason_ko="x"), 3),  # 하한은 올림
    (5, ParamConstraint("steps", max=2.7, reason_ko="y"), 2),  # 상한은 내림
])
def test_int_field_rounds_toward_allowed_range(rules, start, rule, expected):
    ramp = get_template("ramp")
    p, issues = clamp_params(ramp, ramp.Params(steps=start), ctx(rules).rule_ctx, [rule])
    assert p.steps == expected and type(p.steps) is int
    [i] = issues
    assert i.message_ko == f"램프/계단: 계단 단 수 {start} → {expected} 로 보정했습니다. {rule.reason_ko}"
    assert repr(i.details) == f"{{'field': 'steps', 'from': {start}, 'to': {expected}}}"
