"""어항(담수 관상어·새우) 엔진·검증 테스트 (저장소 규칙 파일 사용).

Cage 는 어항에서 수조 안쪽 가로·세로와 물 깊이(바닥재 위 ~ 수면)를 뜻한다.
"""

from __future__ import annotations

import itertools
import re

import pytest

from app.domain import Cage, Placement, PlacementHint
from app.services.engine import EngineContext, ItemSpec, build_item, revalidate, run_engine
from app.templates.base import Features
from app.templates.cave import CaveTemplate
from app.templates.registry import get_template
from app.templates.tunnel import TunnelTemplate
from app.validation import checks
from tests.helpers import box_item

SPECIES = "aquarium"
NANO_TANK = Cage(600, 300, 280)  # 60×30×36cm 수조, 바닥재 50·윗여유 30mm 를 뺀 물 깊이
HANGUL = re.compile(r"[가-힣]")


def actx(rules, size="nano_fish", cage=NANO_TANK, count=10) -> EngineContext:
    return EngineContext(cage=cage, species=SPECIES, size=size, count=count, rules=rules)


def hctx(rules, cage=Cage(600, 400, 300), size="syrian", count=1) -> EngineContext:
    return EngineContext(cage=cage, species="hamster", size=size, count=count, rules=rules)


def by_code(report_or_issues, code):
    issues = report_or_issues.issues if hasattr(report_or_issues, "issues") else report_or_issues
    return [i for i in issues if i.code == code]


def codes(issues):
    return [i.code for i in issues]


def defaults(key: str, ctx: EngineContext) -> dict:
    return get_template(key).default_params(ctx.rule_ctx).model_dump()


# ── 엔진 문맥 ───────────────────────────────────────────────


def test_engine_context_exposes_habitat_templates_and_buoyancy(rules):
    a, h = actx(rules), hctx(rules)
    assert a.habitat == "aquarium" and h.habitat == "cage"
    assert a.allowed_templates == ("cave", "tunnel")
    assert h.allowed_templates == ("hideout", "tunnel", "ramp", "sand_bath")
    assert a.buoyancy is not None and a.buoyancy.material_density_g_cm3 == pytest.approx(1.24)
    assert h.buoyancy is None


# ── 깨끗한 설계 ─────────────────────────────────────────────


@pytest.mark.parametrize("size,count", [("nano_fish", 10), ("shrimp", 10), ("small_fish", 6), ("community", 20)])
def test_cave_and_tunnel_build_clean(rules, size, count):
    c = actx(rules, size=size, count=count)
    res = run_engine([ItemSpec("cave", defaults("cave", c), PlacementHint(zone="left")),
                      ItemSpec("tunnel", defaults("tunnel", c), PlacementHint(zone="right"))], c)
    assert res.report.passed, res.report.errors
    assert [it.key for it in res.items] == ["cave", "tunnel"]
    assert all(it.placement is not None for it in res.items)
    assert not [i for i in res.report.issues if i.severity == "warning"], res.report.issues
    assert not by_code(res.report, "gap_trap_ceiling")
    # 어항 안내: 물속 무게 1건 + 터널 공기 1건
    assert len(by_code(res.report, "underwater_weight")) == 1
    assert [i.item_index for i in by_code(res.report, "tunnel_trapped_air")] == [1]


def test_hamster_report_has_no_aquarium_checks(rules):
    res = run_engine([ItemSpec("hideout", dict(entrance_diameter_mm=75)), ItemSpec("tunnel", {})], hctx(rules))
    aquarium_codes = {"underwater_weight", "tunnel_trapped_air", "tank_volume_below_recommended", "tip_over_risk",
                      "count_below_recommended", "template_not_allowed"}
    assert not aquarium_codes & set(codes(res.report.issues))


# ── 만들 수 없는 구조물 ──────────────────────────────────────


@pytest.mark.parametrize("key", ["ramp", "sand_bath", "hideout"])
def test_cage_only_templates_not_allowed_in_aquarium(rules, key):
    res = run_engine([ItemSpec("cave", {}), ItemSpec(key, {})], actx(rules))
    errs = by_code(res.report, "template_not_allowed")
    assert len(errs) == 1 and errs[0].item_index == 1 and errs[0].severity == "error"
    name = get_template(key).display_name_ko
    species_name = rules.display_names(SPECIES, "nano_fish")[0]
    assert errs[0].message_ko == f"{name} #2: {species_name}에는 만들 수 없는 구조물입니다."
    assert errs[0].details == {"template": key, "allowed": ["cave", "tunnel"]}
    assert [it.key for it in res.items] == ["cave"]  # 만들지 않는다
    assert not res.report.passed


def test_cave_not_allowed_for_hamster(rules):
    res = run_engine([ItemSpec("cave", {})], hctx(rules))
    errs = by_code(res.report, "template_not_allowed")
    assert len(errs) == 1 and errs[0].message_ko == "물속 동굴 #1: 햄스터에는 만들 수 없는 구조물입니다."
    assert res.items == []


def test_revalidate_flags_stored_item_whose_template_is_not_allowed(rules):
    hamster = run_engine([ItemSpec("hideout", dict(entrance_diameter_mm=75))], hctx(rules))
    assert hamster.report.passed
    report = revalidate(hamster.items, actx(rules, cage=Cage(600, 400, 300)))
    errs = by_code(report, "template_not_allowed")
    assert len(errs) == 1 and errs[0].item_index == 0
    assert errs[0].message_ko.startswith("은신처 #1: ") and not report.passed


def test_revalidate_cage_only_items_against_aquarium_rules_does_not_crash(rules):
    """램프·모래목욕통 제약은 어항 크기 구분에 없는 값(오르기·모래 기준)을 쓰므로 계산하지 않고 오류만 남긴다."""
    hamster = run_engine([ItemSpec("ramp", {}), ItemSpec("sand_bath", {})], hctx(rules, cage=Cage(800, 500, 300)))
    assert len(hamster.items) == 2
    report = revalidate(hamster.items, actx(rules, cage=Cage(800, 500, 300)))
    assert [i.item_index for i in by_code(report, "template_not_allowed")] == [0, 1]
    assert not by_code(report, "param_out_of_range")


def test_revalidate_clean_aquarium_design_passes(rules):
    c = actx(rules)
    res = run_engine([ItemSpec("cave", defaults("cave", c)), ItemSpec("tunnel", defaults("tunnel", c))], c)
    assert res.report.passed
    report = revalidate(res.items, c)
    assert report.passed, report.errors
    assert not by_code(report, "template_not_allowed")


# ── 높이 제한 (물 깊이 − 구조물 위 최소 물 깊이) ─────────────────


@pytest.mark.parametrize("size,clearance", [("nano_fish", 30), ("small_fish", 75)])
def test_height_clamped_to_water_depth_minus_clearance(rules, size, clearance):
    tank = Cage(600, 300, 200)
    assert rules.size_rules(SPECIES, size).aquatic.structure_top_clearance_mm == clearance
    c = actx(rules, size=size, cage=tank, count=10)
    res = run_engine([ItemSpec("cave", {**defaults("cave", c), "height_mm": 190})], c)
    limit = tank.height_mm - clearance
    assert res.items[0].params.height_mm == pytest.approx(limit)
    assert res.items[0].height_mm <= limit + 1e-6
    fixed = [i for i in by_code(res.report, "param_adjusted") if i.details["field"] == "height_mm"]
    assert len(fixed) == 1
    assert fixed[0].message_ko.endswith(
        f"생물이 구조물 위로 지나가고 수면 가까이에서 숨 쉴 수 있도록 높이를 {limit:g}mm(물 깊이 − {clearance:g}mm) "
        "이하로 맞췄습니다.")
    assert "케이지" not in fixed[0].message_ko
    assert res.report.passed, res.report.errors


def test_water_too_shallow_for_cave_is_param_conflict(rules):
    c = actx(rules, size="small_fish", cage=Cage(600, 300, 120), count=6)  # 120 − 75 = 45mm < 동굴 최소 높이
    res = run_engine([ItemSpec("cave", defaults("cave", c))], c)
    assert [i for i in by_code(res.report, "param_conflict") if i.details["field"] == "height_mm"]
    assert not res.report.passed


def test_revalidate_flags_cave_taller_than_water_limit(rules):
    c = actx(rules)
    res = run_engine([ItemSpec("cave", {**defaults("cave", c), "height_mm": 200})], c)
    assert res.report.passed
    shallow = actx(rules, cage=Cage(600, 300, 150))  # 한도 120mm
    report = revalidate(res.items, shallow)
    errs = [i for i in by_code(report, "param_out_of_range") if i.details["field"] == "height_mm"]
    assert errs and "물 깊이 − 30mm" in errs[0].message_ko


def test_resized_to_fit_uses_tank_wording(rules):
    c = actx(rules, cage=Cage(250, 250, 280))  # 앞뒤 출입구 앞 20mm 씩 비우면 240mm 동굴은 들어가지 않는다
    res = run_engine([ItemSpec("cave", {**defaults("cave", c), "width_mm": 240, "depth_mm": 240})], c)
    resized = by_code(res.report, "resized_to_fit")
    assert resized and re.fullmatch(r"물속 동굴 #1: 수조 공간이 부족해 크기를 \d+% 로 줄였습니다\.", resized[0].message_ko)
    assert res.items[0].placement is not None


# ── 수조 부피 / 바닥 / 마릿수 ─────────────────────────────────


def test_tank_volume_below_minimum(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    tank = Cage(300, 300, 200)
    issues = checks.check_tank_volume(tank, nano, count=10)
    assert codes(issues) == ["tank_volume_below_recommended"]
    i = issues[0]
    assert i.severity == "warning"
    # 300 × 300 × (200 + 바닥재 50 + 윗여유 30) = 25.2L
    assert i.details == {"volume_l": pytest.approx(25.2), "need_l": 54, "per_animal_l": 1.5}
    assert i.message_ko == (f"수조 부피가 약 25L(물 깊이에 바닥재 50mm·윗여유 30mm를 더해 어림)로 "
                            f"{nano.display_name} 권장 최소 54L 보다 작습니다.")


def test_tank_volume_per_animal(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    assert checks.check_tank_volume(NANO_TANK, nano, count=10) == []  # 64.8L ≥ max(54, 15)
    issues = checks.check_tank_volume(NANO_TANK, nano, count=50)  # 50 × 1.5 = 75L > 64.8L
    assert codes(issues) == ["tank_volume_below_recommended"]
    assert issues[0].details["need_l"] == pytest.approx(75)
    assert issues[0].message_ko == ("수조 부피가 약 65L(물 깊이에 바닥재 50mm·윗여유 30mm를 더해 어림)로 "
                                    "50마리 기준 권장 최소 75L 보다 작습니다.")
    small = rules.size_rules(SPECIES, "small_fish")
    msg = checks.check_tank_volume(NANO_TANK, small, count=12)[0].message_ko  # 12 × 5.6 = 67.2L
    assert "12마리 기준 권장 최소 67.2L" in msg


def test_tank_volume_without_per_animal_rule_uses_minimum_only(rules):
    community = rules.size_rules(SPECIES, "community")
    assert community.aquatic.volume_l_per_animal is None
    assert checks.check_tank_volume(NANO_TANK, community, count=200) == []
    shrimp = rules.size_rules(SPECIES, "shrimp")
    assert checks.check_tank_volume(Cage(300, 300, 200), shrimp, count=50) == []  # 23.4L ≥ 10L
    assert codes(checks.check_tank_volume(Cage(200, 150, 150), shrimp, count=5)) == ["tank_volume_below_recommended"]


def test_tank_volume_skipped_for_cage(rules):
    assert checks.check_tank_volume(Cage(100, 100, 100), rules.size_rules("hamster", "syrian")) == []


def test_tank_volume_warning_in_engine_report(rules):
    c = actx(rules, cage=Cage(300, 300, 200))
    res = run_engine([ItemSpec("cave", defaults("cave", c))], c)
    assert by_code(res.report, "tank_volume_below_recommended")
    assert res.report.passed  # 경고만, 설계는 막지 않는다


@pytest.mark.parametrize("w,d,warn", [(600, 300, False), (300, 600, False), (450, 300, True), (600, 250, True)])
def test_tank_floor_below_recommended(rules, w, d, warn):
    nano = rules.size_rules(SPECIES, "nano_fish")
    issues = checks.check_enclosure(Cage(w, d, 280), nano)
    assert codes(issues) == (["cage_below_recommended"] if warn else [])
    if warn:
        assert issues[0].message_ko == (f"수조 바닥 {w}×{d}mm 가 {nano.display_name} 권장 최소 600×300mm 보다 작습니다. "
                                        "더 큰 수조를 권장합니다.")


def test_shrimp_has_no_floor_rule(rules):
    assert checks.check_enclosure(Cage(200, 150, 150), rules.size_rules(SPECIES, "shrimp")) == []


def test_min_count_warning(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    issues = checks.check_count(3, nano)
    assert codes(issues) == ["count_below_recommended"]
    assert issues[0].severity == "warning"
    assert issues[0].message_ko == f"3마리: {nano.min_count_warning_ko}"
    assert issues[0].details == {"count": 3, "min": 10}
    assert checks.check_count(10, nano) == []
    assert checks.check_count(200, nano) == []  # 최대 권장 마릿수 없음
    assert checks.check_count(1, rules.size_rules(SPECIES, "community")) == []  # 합사 수조는 최소 마릿수 없음


def test_min_count_warning_in_engine_report(rules):
    c = actx(rules, count=3)
    res = run_engine([ItemSpec("cave", defaults("cave", c))], c)
    assert by_code(res.report, "count_below_recommended")


# ── 수조 문구 / 틈새 ────────────────────────────────────────


def test_no_ceiling_gap_check_in_aquarium(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    tank = Cage(600, 300, 100)
    it = box_item(0, 100, 100, 90, x=100, y=100)  # 수면까지 10mm: 케이지라면 천장 끼임 구간(2~20mm)
    assert checks.check_gaps([it], tank, nano) == []
    hamster_like = rules.size_rules("hamster", "syrian")
    assert "gap_trap_ceiling" in codes(checks.check_gaps([it], Cage(600, 300, 100), hamster_like))


def test_fit_and_access_use_tank_wording(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    tank = Cage(300, 300, 100)
    tall = box_item(0, 50, 50, 150, x=100, y=100)
    unplaced = box_item(1, 50, 50, 50)
    outside = box_item(2, 100, 100, 50, x=30, y=150)
    msgs = [i.message_ko for i in checks.check_fit([tall, unplaced, outside], tank, aquarium=True)]
    assert msgs == [
        "test #1: 높이 150mm 가 물 깊이 100mm 보다 높습니다.",
        "test #2: 수조 안에 안전하게 놓을 자리가 없습니다. 구조물 수나 크기를 줄여 주세요.",
        "test #3: 수조 바닥 밖으로 벗어납니다.",
    ]
    assert all("케이지" not in m for m in msgs)
    # 케이지 문구는 그대로
    assert checks.check_fit([tall], tank)[0].message_ko == "test #1: 높이 150mm 가 케이지 내부 높이 100mm 보다 높습니다."

    c = actx(rules, cage=Cage(600, 300, 280))
    cave = build_item(0, CaveTemplate(), CaveTemplate().default_params(c.rule_ctx), PlacementHint(), rules.printing)
    cave.placement = Placement(300, cave.mesh.extents[1] / 2, 0)  # 앞 출입구가 앞 유리에 붙음
    blocked = checks.check_access([cave], c.cage, nano)
    assert codes(blocked) == ["access_blocked"]
    assert blocked[0].message_ko == "물속 동굴 #1: 출입구 앞 20mm 공간이 수조 벽에 막혀 있습니다."


def test_gap_to_tank_wall_wording(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    it = box_item(0, 100, 100, 50, x=60, y=150)  # 왼쪽 유리와 10mm
    issues = [i for i in checks.check_gaps([it], Cage(600, 300, 280), nano) if i.code == "gap_trap_wall"]
    assert issues[0].message_ko == "test #1 와(과) 왼쪽 수조 벽 사이 틈 10.0mm 가 끼임 위험 구간(2~20mm)에 있습니다."


def test_community_gap_range_and_placement(rules):
    """합사 수조: 새우 기준 safe_max 1.0mm 와 소형 어종 기준 passable_min 45mm 를 함께 쓴다."""
    community = rules.size_rules(SPECIES, "community")
    assert (community.gap_trap.safe_max_mm, community.gap_trap.passable_min_mm) == (1.0, 45)
    a = box_item(0, 100, 100, 50, x=100, y=150)
    b = box_item(1, 100, 100, 50, x=210, y=150)  # 10mm 틈
    issues = checks.check_gaps([a, b], Cage(600, 300, 280), community)
    assert codes(issues) == ["gap_trap"]
    assert "끼임 위험 구간(1~45mm)" in issues[0].message_ko

    c = actx(rules, size="community", count=20)
    res = run_engine([ItemSpec("cave", defaults("cave", c)) for _ in range(3)], c)
    assert res.report.passed, res.report.errors
    gt = community.gap_trap
    fps = [it.world_footprint for it in res.items]
    for x, y in itertools.combinations(fps, 2):
        assert not gt.is_trap(x.distance(y))
    for fp in fps:
        x0, y0, x1, y1 = fp.bounds
        assert not any(gt.is_trap(g) for g in (x0, 600 - x1, y0, 300 - y1))


def test_too_few_entrances_aquarium_wording(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    c = actx(rules)
    p = CaveTemplate().default_params(c.rule_ctx).model_copy(update={"entrance_count": 1})
    cave = build_item(0, CaveTemplate(), p, PlacementHint(), rules.printing)
    issues = checks.check_openings([cave], nano, count=1)
    assert codes(issues) == ["too_few_entrances"]
    assert issues[0].message_ko == ("물속 동굴 #1: 출입구가 1개뿐입니다. 물고기는 좁은 곳에서 뒤로 잘 빠져나오지 못해 "
                                    "2개 이상(앞뒤로 뚫린 관통형)이어야 합니다.")


def test_wall_too_thin_aquarium_wording(rules):
    f = Features(min_wall_thickness_mm=1.0)
    it = box_item(0, 50, 50, 50, x=100, y=100, features=f)
    msg = checks.check_wall_thickness([it], 2.0, measure=False, aquarium=True)[0].message_ko
    assert msg == "test #1: 벽 두께 1mm 가 최소 기준 2mm 보다 얇습니다 (물속 내구성·출력 기준)."
    assert "갉음" in checks.check_wall_thickness([it], 2.0, measure=False)[0].message_ko


def test_climb_checks_skip_missing_rules(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    assert nano.max_climb_height_mm is None and nano.max_ramp_angle_deg is None and nano.max_step_height_mm is None
    f = Features(min_wall_thickness_mm=5, climb_height_mm=500, slope_deg=50, step_height_mm=100)
    it = box_item(0, 50, 50, 50, x=100, y=100, features=f)
    assert checks.check_climb([it], nano) == []


# ── 넘어짐 / 물속 무게 / 터널 공기 ────────────────────────────


def test_tip_over_warning_for_tall_narrow_cave(rules):
    c = actx(rules)
    p = {**defaults("cave", c), "width_mm": 60, "depth_mm": 60, "height_mm": 200}
    res = run_engine([ItemSpec("cave", p)], c)
    assert res.items[0].params.height_mm == 200
    tips = by_code(res.report, "tip_over_risk")
    assert len(tips) == 1 and tips[0].severity == "warning" and tips[0].item_index == 0
    assert tips[0].message_ko == ("물속 동굴 #1: 높이 200mm 가 바닥 짧은 변 60mm 의 1.5배를 넘어 물속에서 넘어지기 쉽습니다. "
                                  "바닥을 넓히거나 높이를 낮춰 주세요.")
    assert tips[0].details["ratio"] == pytest.approx(200 / 60, rel=1e-3)
    assert res.report.passed  # 경고만


def test_tip_over_threshold(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    ok = box_item(0, 100, 60, 90, x=100, y=100)  # 90 / 60 = 1.5 (경계)
    tall = box_item(1, 100, 60, 91, x=300, y=100)
    assert codes(checks.check_tip_over([ok, tall], nano)) == ["tip_over_risk"]
    assert checks.check_tip_over([tall], rules.size_rules("hamster", "syrian")) == []


def test_underwater_weight(rules):
    c = actx(rules)
    res = run_engine([ItemSpec("cave", defaults("cave", c)), ItemSpec("tunnel", defaults("tunnel", c))], c)
    w = by_code(res.report, "underwater_weight")
    assert len(w) == 1 and w[0].severity == "info" and w[0].item_index is None
    b = rules.buoyancy(SPECIES)
    expected = sum(it.mesh.volume for it in res.items) / 1000 * (b.material_density_g_cm3 - b.water_density_g_cm3)
    assert w[0].details["total_g"] == pytest.approx(expected)
    assert 1 < w[0].details["total_g"] < 200  # 작은 동굴·터널 둘: 수십 g
    assert [x["index"] for x in w[0].details["items"]] == [0, 1]
    assert sum(x["grams"] for x in w[0].details["items"]) == pytest.approx(expected)
    assert w[0].details["percent_of_dry"] == pytest.approx((1.24 - 0.997) / 1.24 * 100)
    assert w[0].message_ko == (
        f"출력물의 물속 무게는 모두 합쳐 약 {expected:.0f}g 이에요(채움 100% 기준, 마른 무게의 약 20%). "
        "가벼워서 물살이나 물고기에 밀릴 수 있으니 설치 뒤 하루 동안 뜨거나 밀리지 않는지 지켜봐 주세요.")


def test_underwater_weight_needs_items_and_buoyancy(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    b = rules.buoyancy(SPECIES)
    assert checks.check_underwater_weight([], nano, b) == []
    it = box_item(0, 10, 10, 10, x=100, y=100)
    assert checks.check_underwater_weight([it], nano, None) == []
    assert checks.check_underwater_weight([it], rules.size_rules("hamster", "syrian"), b) == []
    # 1cm³ × (1.24 − 0.997) = 0.243g
    assert checks.check_underwater_weight([it], nano, b)[0].details["total_g"] == pytest.approx(0.243)


def test_tunnel_trapped_air_notice_only_for_tunnels(rules):
    c = actx(rules)
    tunnel = build_item(1, TunnelTemplate(), TunnelTemplate().default_params(c.rule_ctx), PlacementHint(),
                        rules.printing)
    cave = build_item(0, CaveTemplate(), CaveTemplate().default_params(c.rule_ctx), PlacementHint(), rules.printing)
    issues = checks.check_tunnel_air([cave, tunnel], c.size_rules)
    assert codes(issues) == ["tunnel_trapped_air"]
    assert issues[0].item_index == 1 and issues[0].severity == "info"
    assert issues[0].message_ko == ("터널 #2: 수평으로 놓으면 꼭대기를 따라 공기가 남아 뜰 수 있어요. "
                                    "물속에서 한쪽 끝을 들어 공기를 뺀 뒤 놓아 주세요.")
    assert checks.check_tunnel_air([tunnel], rules.size_rules("hamster", "syrian")) == []


def test_validate_all_orders_aquarium_checks(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    c = actx(rules, cage=Cage(300, 300, 200), count=3)
    tunnel = build_item(0, TunnelTemplate(), TunnelTemplate().default_params(c.rule_ctx), PlacementHint(),
                        rules.printing)
    tunnel.placement = Placement(150, 150, 0)
    issues = checks.validate_all([tunnel], c.cage, nano, rules.printing, c.min_wall_mm, count=3,
                                 measure_thickness_mesh=False, buoyancy=rules.buoyancy(SPECIES))
    got = [i for i in codes(issues) if i in {"count_below_recommended", "cage_below_recommended",
                                            "tank_volume_below_recommended", "underwater_weight",
                                            "tunnel_trapped_air"}]
    assert got == ["count_below_recommended", "cage_below_recommended", "tank_volume_below_recommended",
                   "underwater_weight", "tunnel_trapped_air"]


# ── 영어 ──────────────────────────────────────────────────


def test_new_messages_translate_to_english(rules):
    from app.i18n import catalog

    c = catalog()
    samples = [
        "터널 #2: 수평으로 놓으면 꼭대기를 따라 공기가 남아 뜰 수 있어요. 물속에서 한쪽 끝을 들어 공기를 뺀 뒤 놓아 주세요.",
        "출력물의 물속 무게는 모두 합쳐 약 39g 이에요(채움 100% 기준, 마른 무게의 약 20%). "
        "가벼워서 물살이나 물고기에 밀릴 수 있으니 설치 뒤 하루 동안 뜨거나 밀리지 않는지 지켜봐 주세요.",
        "물속 동굴 #1: 외형 높이(Z) 200 → 170 로 보정했습니다. 생물이 구조물 위로 지나가고 수면 가까이에서 숨 쉴 수 있도록 "
        "높이를 170mm(물 깊이 − 30mm) 이하로 맞췄습니다.",
        "물속 동굴 #1: 수조 공간이 부족해 크기를 80% 로 줄였습니다.",
        "물속 동굴 #1: 출입구 앞 20mm 공간이 수조 벽에 막혀 있습니다.",
        "test #1 와(과) 왼쪽 수조 벽 사이 틈 10.0mm 가 끼임 위험 구간(2~20mm)에 있습니다.",
        "수조 부피가 약 65L(물 깊이에 바닥재 50mm·윗여유 30mm를 더해 어림)로 50마리 기준 권장 최소 75L 보다 작습니다.",
        "물속 동굴 #1: 높이 200mm 가 바닥 짧은 변 60mm 의 1.5배를 넘어 물속에서 넘어지기 쉽습니다. 바닥을 넓히거나 높이를 낮춰 주세요.",
    ]
    for s in samples:
        out = c.translate(s)
        assert not HANGUL.search(out), (s, out)
    assert "the tank wall" in c.translate("물속 동굴 #1: 출입구 앞 20mm 공간이 수조 벽에 막혀 있습니다.")
    assert c.translate(samples[6]).endswith("for 50 animals.")
