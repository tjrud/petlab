"""어항(담수 관상어·새우) 엔진·검증 테스트 (저장소 규칙 파일 사용).

Cage 는 어항에서 수조 안쪽 가로·세로와 물 깊이(바닥재 위 ~ 수면)를 뜻한다.
바닥·부피 기준은 겉 크기라, 그 둘만 안쪽 치수에 유리 두께 어림(6mm)을 더해 비교한다.
"""

from __future__ import annotations

import itertools
import re

import pytest

from app.domain import Cage, Placement, PlacementHint
from app.services.engine import EngineContext, ItemSpec, build_item, revalidate, run_engine
from app.templates.base import Features
from app.templates.cave import CaveTemplate
from app.templates.cave import min_height as cave_min_height
from app.templates.registry import get_template
from app.templates.tunnel import TunnelTemplate
from app.validation import checks
from tests.helpers import box_item

SPECIES = "aquarium"
NANO_TANK = Cage(600, 300, 280)  # 수조 안쪽 600×300mm·물 깊이 280mm (겉 크기로 어림하면 약 69.9L)
# 흔한 60×30×36cm 수조(유리 6mm)를 안내대로 잰 값: 안쪽 588×288mm, 물 깊이 360 − 바닥 유리 6 − 바닥재 50 − 윗여유 30
#   → 겉 크기로 어림한 부피 600 × 300 × 360 = 64.8L
STD_60_TANK = Cage(588, 288, 274)
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


@pytest.mark.parametrize("size,depth", [("small_fish", 120), ("small_fish", 100), ("small_fish", 143),
                                        ("community", 144)])
def test_water_too_shallow_for_cave_is_one_clear_error(rules, size, depth):
    """가장 작게 만들어도 들어가지 않으면 높이 보정·충돌 문구 대신, 필요한 물 깊이를 밝힌 오류 하나만 낸다."""
    c = actx(rules, size=size, cage=Cage(600, 300, depth), count=6)
    need = CaveTemplate().min_height_mm(c.rule_ctx)  # 종별 최소 출입구·벽·지붕 경사에 꼭대기 구멍을 가장 넓힌 동굴
    assert need == {"small_fish": 68.3, "community": 69.4}[size]
    res = run_engine([ItemSpec("cave", defaults("cave", c))], c)
    assert codes(res.report.errors) == ["water_too_shallow"]
    err = res.report.errors[0]
    assert err.item_index == 0
    assert err.message_ko == (
        f"물속 동굴 #1: 물 깊이 {depth}mm 로는 만들 수 없습니다. 생물이 구조물 위로 지나가고 수면 가까이에서 숨 쉴 수 있도록 "
        f"위에 75mm 를 남기면, 가장 낮게 만들어도 높이가 {need:g}mm 라 물 깊이가 {need + 75:g}mm 이상이어야 합니다.")
    assert err.details["min_water_depth_mm"] == pytest.approx(need + 75)
    # '높이를 45mm 이하로 맞췄습니다'처럼 어긋나는 보정 문구를 함께 내지 않는다
    assert not [i for i in res.report.issues if i.code in ("param_adjusted", "param_conflict")]
    assert not res.report.passed
    assert codes(revalidate(res.items, c).errors) == ["water_too_shallow"]


def test_shallow_tank_lowers_cave_roof_instead_of_failing(rules):
    """45×30×24cm 수조(물 깊이 160): 기본 동굴(102×86, 높이 92)은 한도 85mm 를 넘지만, 꼭대기 구멍을 넓혀 지붕을 낮추면 들어간다."""
    c = actx(rules, size="small_fish", cage=Cage(450, 300, 160), count=6)
    base = CaveTemplate().default_params(c.rule_ctx)
    res = run_engine([ItemSpec("cave", base.model_dump())], c)
    assert res.report.passed, res.report.errors
    p = res.items[0].params
    assert res.items[0].height_mm == pytest.approx(85, abs=1e-3)
    assert (p.width_mm, p.depth_mm) == (base.width_mm, base.depth_mm)  # 바닥 크기는 그대로
    assert p.top_opening_mm > base.top_opening_mm
    assert cave_min_height(p) <= 85 + 1e-9
    fixed = {i.details["field"]: i.message_ko for i in by_code(res.report, "param_adjusted")}
    assert set(fixed) == {"height_mm", "top_opening_mm"}
    assert fixed["top_opening_mm"] == (
        f"물속 동굴 #1: 꼭대기 구멍 폭 50 → {p.top_opening_mm:g} 로 보정했습니다. "
        "물이 얕아 동굴을 높이 85mm(물 깊이 − 75mm) 안에 맞추려고 함께 조정했습니다")
    assert revalidate(res.items, c).passed


@pytest.mark.parametrize("depth", [144, 150, 152, 166, 167])
def test_shallow_tank_cave_fits_down_to_minimum_water_depth(rules, depth):
    """구멍을 가장 넓혀도 높으면 지붕 경사 → 벽 두께 → 출입구 폭을 종 기준까지 줄인다 (모두 종 기준 이상)."""
    c = actx(rules, size="small_fish", cage=Cage(450, 300, depth), count=6)
    s = c.size_rules
    res = run_engine([ItemSpec("cave", defaults("cave", c))], c)
    assert res.report.passed, res.report.errors
    p = res.items[0].params
    assert res.items[0].height_mm <= depth - 75 + 1e-6
    assert p.entrance_diameter_mm >= s.entrance_min_diameter_mm
    assert p.wall_thickness_mm >= c.min_wall_mm
    assert p.roof_slope_deg >= 40 and p.top_opening_mm >= s.gap_trap.passable_min_mm
    assert not by_code(res.report, "param_conflict")


def test_shallow_tank_big_cave_shrinks_short_side_when_top_opening_maxes_out(rules):
    """꼭대기 구멍은 150mm 까지만 넓힐 수 있어, 큰 동굴은 짧은 변을 줄여 지붕을 낮춘다."""
    c = actx(rules, size="small_fish", cage=Cage(900, 450, 200), count=6)
    res = run_engine([ItemSpec("cave", dict(width_mm=250, depth_mm=220, height_mm=150, entrance_diameter_mm=60,
                                            top_opening_mm=50, wall_thickness_mm=3))], c)
    assert res.report.passed, res.report.errors
    p = res.items[0].params
    assert p.top_opening_mm == 150 and p.width_mm == 250 and p.depth_mm < 220
    assert res.items[0].height_mm <= 125 + 1e-6


def test_top_opening_max_uses_the_grown_footprint_in_engine(rules):
    """세로가 출입구 때문에 커지면 꼭대기 구멍 상한도 그만큼 커진다 (예전 세로로 구멍을 줄여 높이 충돌이 나던 경우)."""
    c = actx(rules, size="community", cage=Cage(900, 450, 250), count=6)
    res = run_engine([ItemSpec("cave", dict(width_mm=174, depth_mm=50, entrance_diameter_mm=120, top_opening_mm=150,
                                            wall_thickness_mm=2.4))], c)
    assert not by_code(res.report, "param_conflict")
    p = res.items[0].params
    assert p.depth_mm == pytest.approx(124.8) and p.top_opening_mm == pytest.approx(110)
    assert res.report.passed, res.report.errors


# ── 터널 높이 (구조물 위 최소 물 깊이) ─────────────────────────


def test_tunnel_inner_diameter_clamped_to_water_clearance(rules):
    """터널은 높이 파라미터가 없어도 내경으로 높이를 맞춘다 (높이 = 내경 × 약 1.28 + 벽 두께 × 약 1.56)."""
    c = actx(rules, size="small_fish", cage=Cage(300, 300, 220), count=6)
    res = run_engine([ItemSpec("tunnel", {**defaults("tunnel", c), "inner_diameter_mm": 120})], c)
    it = res.items[0]
    assert it.params.inner_diameter_mm == pytest.approx(109.8)
    assert 144 < it.height_mm <= 145 + 1e-6
    fixed = [i for i in by_code(res.report, "param_adjusted") if i.details["field"] == "inner_diameter_mm"]
    assert [i.message_ko for i in fixed] == [
        "터널 #1: 터널 안쪽 폭(=내경) 120 → 109.8 로 보정했습니다. 생물이 구조물 위로 지나가고 수면 가까이에서 숨 쉴 수 "
        "있도록 높이를 145mm(물 깊이 − 75mm) 이하로 맞췄습니다."]
    assert res.report.passed, res.report.errors


def test_default_tunnel_in_shallow_tank_keeps_clearance(rules):
    c = actx(rules, size="small_fish", cage=Cage(600, 300, 140), count=6)
    res = run_engine([ItemSpec("tunnel", defaults("tunnel", c))], c)
    assert res.items[0].height_mm <= 65 + 1e-6
    assert res.items[0].params.inner_diameter_mm >= c.size_rules.tunnel_min_inner_diameter_mm
    assert res.report.passed, res.report.errors


def test_thick_walled_tunnel_lowers_wall_to_fit(rules):
    c = actx(rules, size="small_fish", cage=Cage(600, 300, 140), count=6)
    res = run_engine([ItemSpec("tunnel", {**defaults("tunnel", c), "wall_thickness_mm": 8})], c)
    p = res.items[0].params
    assert c.min_wall_mm <= p.wall_thickness_mm < 8
    assert p.inner_diameter_mm >= c.size_rules.tunnel_min_inner_diameter_mm
    assert res.items[0].height_mm <= 65 + 1e-6
    assert res.report.passed, res.report.errors


def test_tunnel_too_tall_for_water_flagged_on_revalidate(rules):
    deep = actx(rules, size="small_fish", cage=Cage(300, 300, 400), count=6)
    res = run_engine([ItemSpec("tunnel", {**defaults("tunnel", deep), "inner_diameter_mm": 120})], deep)
    assert res.report.passed and res.items[0].params.inner_diameter_mm == 120
    report = revalidate(res.items, actx(rules, size="small_fish", cage=Cage(300, 300, 220), count=6))
    errs = [i for i in by_code(report, "param_out_of_range") if i.details["field"] == "inner_diameter_mm"]
    assert errs and "높이를 145mm(물 깊이 − 75mm) 이하로" in errs[0].message_ko
    assert not report.passed


def test_tunnel_in_water_too_shallow_for_any_tunnel(rules):
    c = actx(rules, size="community", cage=Cage(600, 300, 100), count=6)
    res = run_engine([ItemSpec("tunnel", {**defaults("tunnel", c), "inner_diameter_mm": 60})], c)
    assert codes(res.report.errors) == ["water_too_shallow"]
    need = TunnelTemplate().min_height_mm(c.rule_ctx)
    assert res.report.errors[0].message_ko.startswith("터널 #1: 물 깊이 100mm 로는 만들 수 없습니다.")
    assert res.report.errors[0].details["min_water_depth_mm"] == pytest.approx(need + 75)


def test_tunnel_with_enough_water_is_unchanged(rules):
    c = actx(rules, size="small_fish", cage=NANO_TANK, count=6)
    p = defaults("tunnel", c)
    res = run_engine([ItemSpec("tunnel", p)], c)
    assert res.items[0].params.model_dump() == p
    assert not by_code(res.report, "param_adjusted")


def test_hamster_tunnel_has_no_height_limit(rules):
    """케이지 터널은 예전처럼 천장 틈 검사만 받는다 (내경을 높이에 맞춰 줄이지 않는다)."""
    c = hctx(rules, cage=Cage(600, 400, 120))
    res = run_engine([ItemSpec("tunnel", {**defaults("tunnel", c), "inner_diameter_mm": 90})], c)
    assert res.items[0].params.inner_diameter_mm == 90
    assert not [i for i in by_code(res.report, "param_adjusted") if i.details["field"] == "inner_diameter_mm"]
    assert not by_code(res.report, "water_too_shallow")


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
    assert codes(issues) == ["tank_volume_below_recommended", "tank_volume_species_note"]
    i = issues[0]
    assert i.severity == "warning"
    # 겉 크기로 어림: (300 + 유리 2 × 6)² × (200 + 바닥재 50 + 윗여유 30 + 바닥 유리 6) = 27.84L
    assert i.details == {"volume_l": pytest.approx(27.84, abs=0.01), "need_l": 54, "per_animal_l": 1.5}
    # 54L 는 법령·감정서의 하한이라 '권장 최소'가 아니라 '최소 기준'
    assert i.message_ko == (f"수조 부피가 약 27L(안쪽 치수에 유리 두께 6mm, 물 깊이에 바닥재 50mm·윗여유 30mm를 더한 "
                            f"겉 크기로 어림)로 {nano.display_name} 최소 기준 54L 보다 작습니다.")


def test_tank_volume_per_animal(rules):
    nano = rules.size_rules(SPECIES, "nano_fish")
    assert codes(checks.check_tank_volume(STD_60_TANK, nano, count=10)) == ["tank_volume_species_note"]  # 64.8L ≥ 54
    issues = checks.check_tank_volume(STD_60_TANK, nano, count=50)  # 50 × 1.5 = 75L > 64.8L
    assert codes(issues) == ["tank_volume_below_recommended", "tank_volume_species_note"]
    assert issues[0].details["need_l"] == pytest.approx(75)
    assert issues[0].details["volume_l"] == pytest.approx(64.8)
    # 64.8L 는 내려서 64L 로 보인다 (반올림하면 65L)
    assert issues[0].message_ko == ("수조 부피가 약 64L(안쪽 치수에 유리 두께 6mm, 물 깊이에 바닥재 50mm·윗여유 30mm를 "
                                    "더한 겉 크기로 어림)로 50마리 기준 권장 최소 75L 보다 작습니다.")
    small = rules.size_rules(SPECIES, "small_fish")
    msg = checks.check_tank_volume(STD_60_TANK, small, count=12)[0].message_ko  # 12 × 5.6 = 67.2L
    assert "12마리 기준 권장 최소 67.2L" in msg


@pytest.mark.parametrize("size,cage,count", [
    ("nano_fish", Cage(588, 288, 213), 10),   # 겉 600×300×299 = 53.82L: 반올림하면 '약 54L … 최소 기준 54L 보다 작습니다'
    ("nano_fish", Cage(588, 318, 215), 40),   # 겉 600×330×301 = 59.6L < 40 × 1.5 = 60L
    ("shrimp", Cage(188, 138, 251), 5),       # 겉 200×150×317 = 9.51L < 10L
])
def test_tank_volume_shown_below_the_minimum_it_misses(rules, size, cage, count):
    """부피를 내려서 보여 '약 54L … 54L 보다 작습니다'처럼 스스로 어긋나는 경고가 나오지 않는다."""
    [warn] = [i for i in checks.check_tank_volume(cage, rules.size_rules(SPECIES, size), count)
              if i.code == "tank_volume_below_recommended"]
    shown = int(re.search(r"약 (\d+)L", warn.message_ko).group(1))
    assert shown < warn.details["need_l"] and shown == int(warn.details["volume_l"])


def test_tank_volume_species_note_for_corydoras_sized_tanks(rules):
    """소형 어종: 54L 는 하한일 뿐이라 100L 보다 작은 수조에는 종별 권장 부피를 참고로 알린다 (경고 없이도)."""
    small = rules.size_rules(SPECIES, "small_fish")
    issues = checks.check_tank_volume(STD_60_TANK, small, count=6)  # 64.8L: 코리도라스 6마리
    assert codes(issues) == ["tank_volume_species_note"]
    note = issues[0]
    assert note.severity == "info" and note.message_ko == small.aquatic.volume_note_ko
    assert "코리도라스 무리는 80L 이상" in note.message_ko
    assert note.details == {"volume_l": pytest.approx(64.8), "note_below_l": 100}
    assert checks.check_tank_volume(Cage(900, 450, 370), small, count=6) == []  # 겉 912×462×456 ≈ 192L
    c = actx(rules, size="small_fish", count=6)
    res = run_engine([ItemSpec("cave", defaults("cave", c))], c)
    assert by_code(res.report, "tank_volume_species_note") and res.report.passed


def test_tank_volume_without_per_animal_rule_uses_minimum_only(rules):
    community = rules.size_rules(SPECIES, "community")
    assert community.aquatic.volume_l_per_animal is None
    assert codes(checks.check_tank_volume(NANO_TANK, community, count=200)) == ["tank_volume_species_note"]
    shrimp = rules.size_rules(SPECIES, "shrimp")
    assert checks.check_tank_volume(Cage(300, 300, 200), shrimp, count=50) == []  # 겉 312×312×266 ≈ 25.9L ≥ 10L
    assert codes(checks.check_tank_volume(Cage(200, 150, 150), shrimp, count=5)) == ["tank_volume_below_recommended"]


def test_tank_volume_skipped_for_cage(rules):
    assert checks.check_tank_volume(Cage(100, 100, 100), rules.size_rules("hamster", "syrian")) == []


def test_tank_volume_warning_in_engine_report(rules):
    c = actx(rules, cage=Cage(300, 300, 200))
    res = run_engine([ItemSpec("cave", defaults("cave", c))], c)
    assert by_code(res.report, "tank_volume_below_recommended")
    assert res.report.passed  # 경고만, 설계는 막지 않는다


@pytest.mark.parametrize("w,d,warn", [(600, 300, False), (300, 600, False), (450, 300, True), (600, 250, True),
                                      # 흔한 60×30cm 수조를 안내대로 안쪽에서 잰 값 (유리 6mm·5mm): 기준을 채운다
                                      (588, 288, False), (590, 290, False), (288, 588, False),
                                      # 겉 크기로 어림해도 1mm 모자라다
                                      (587, 300, True), (600, 287, True)])
def test_tank_floor_below_recommended(rules, w, d, warn):
    """바닥 기준('60cm' 등급 60×30cm)은 겉 크기라, 입력한 안쪽 치수에 유리 두께 어림 6mm 를 양쪽에 더해 비교한다."""
    nano = rules.size_rules(SPECIES, "nano_fish")
    issues = checks.check_enclosure(Cage(w, d, 280), nano)
    assert codes(issues) == (["cage_below_recommended"] if warn else [])
    if warn:
        assert issues[0].message_ko == (f"수조 겉 크기가 약 {w + 12}×{d + 12}mm(안쪽 {w}×{d}mm에 유리 두께 6mm를 더해 "
                                        f"어림)로 {nano.display_name} 최소 기준 600×300mm 보다 작습니다. 더 큰 수조를 권장합니다.")
        assert issues[0].details == {"floor_mm": [w, d], "recommended_mm": [600, 300],
                                     "outer_floor_mm": [w + 12, d + 12], "glass_mm": 6}


def test_standard_60cm_tank_measured_inside_meets_floor_and_volume(rules):
    """법령·감정서의 최소 수조(60×30×30cm, 겉 크기 54L)를 안쪽 치수로 재 넣어도 바닥·부피 경고가 나오지 않는다."""
    for glass in (5, 6):
        tank = Cage(600 - 2 * glass, 300 - 2 * glass, 300 - glass - 50 - 30)  # 물 깊이: 바닥 유리·바닥재·윗여유를 뺀다
        for size in ("nano_fish", "small_fish", "community"):
            s = rules.size_rules(SPECIES, size)
            assert checks.check_enclosure(tank, s) == [], (glass, size)
            assert not by_code(checks.check_tank_volume(tank, s, count=1), "tank_volume_below_recommended"), (glass, size)
    # 6mm 유리면 겉 크기 부피가 정확히 54L
    assert checks.tank_volume_l(Cage(588, 288, 214), rules.size_rules(SPECIES, "nano_fish")) == pytest.approx(54.0)
    assert checks.tank_outer_floor_mm(Cage(588, 288, 214), rules.size_rules(SPECIES, "nano_fish")) == (600, 300)


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


BENT_TUNNEL_CASES = [("small_fish", 45, "center"), ("community", 90, "center"), ("community", 45, "left")]


@pytest.mark.parametrize("size,bend,zone", BENT_TUNNEL_CASES)
def test_bent_tunnel_and_cave_in_same_zone_leave_no_trap_gap(rules, size, bend, zone):
    """휜 터널은 바닥 사각형보다 윤곽이 작다: 사각형끼리 붙어도 실제 윤곽 사이에 끼임 틈이 남지 않게 배치한다."""
    c = actx(rules, size=size, count=6)
    tunnel = {**defaults("tunnel", c), "bend_angle_deg": bend, "length_mm": 200}
    res = run_engine([ItemSpec("tunnel", tunnel, PlacementHint(zone=zone)),
                      ItemSpec("cave", defaults("cave", c), PlacementHint(zone=zone))], c)
    assert not by_code(res.report, "gap_trap")
    assert res.report.passed, res.report.errors
    gt = c.size_rules.gap_trap
    a, b = (it.world_footprint for it in res.items)
    assert not gt.is_trap(a.distance(b))


@pytest.mark.parametrize("size,bend,zone", BENT_TUNNEL_CASES)
def test_placer_exact_gaps_only_when_asked(rules, size, bend, zone):
    """사각형 틈만 보면(케이지 배치처럼) 이 배치는 끼임 틈을 남긴다: exact_gaps 가 실제로 그 틈을 막는다."""
    from app.layout.placer import place_all

    c = actx(rules, size=size, count=6)
    tp = TunnelTemplate().default_params(c.rule_ctx).model_copy(update={"bend_angle_deg": bend, "length_mm": 200})
    cp = CaveTemplate().default_params(c.rule_ctx)
    traps = {}
    for exact in (False, True):
        items = [build_item(0, TunnelTemplate(), tp, PlacementHint(zone=zone), rules.printing),
                 build_item(1, CaveTemplate(), cp, PlacementHint(zone=zone), rules.printing)]
        assert place_all(items, c.cage, c.size_rules.gap_trap, exact_gaps=exact) == []
        traps[exact] = by_code(checks.check_gaps(items, c.cage, c.size_rules), "gap_trap")
    assert traps[False] and not traps[True]


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


@pytest.mark.parametrize("base,h", [(60.2, 90.4), (60, 90.4), (60.4, 90.7)])
def test_tip_over_numbers_shown_exceed_the_ratio(rules, base, h):
    """반올림하면 90.4/60.2 가 '높이 90mm … 60mm 의 1.5배를 넘어'(= 정확히 1.5배)로 보인다: 높이는 올리고 바닥은 내린다."""
    nano = rules.size_rules(SPECIES, "nano_fish")
    [i] = checks.check_tip_over([box_item(0, 100, base, h, x=100, y=100)], nano)
    m = re.search(r"높이 (\d+)mm 가 바닥 짧은 변 (\d+)mm 의 1\.5배", i.message_ko)
    assert m and int(m.group(1)) / int(m.group(2)) > 1.5


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
        "수조 부피가 약 64L(안쪽 치수에 유리 두께 6mm, 물 깊이에 바닥재 50mm·윗여유 30mm를 더한 겉 크기로 어림)로 "
        "50마리 기준 권장 최소 75L 보다 작습니다.",
        "수조 겉 크기가 약 462×312mm(안쪽 450×300mm에 유리 두께 6mm를 더해 어림)로 나노 어종 (네온·엠버 테트라 등, "
        "꼬리지느러미 뺀 몸길이 2~3cm) 최소 기준 600×300mm 보다 작습니다. 더 큰 수조를 권장합니다.",
        "물속 동굴 #1: 높이 200mm 가 바닥 짧은 변 60mm 의 1.5배를 넘어 물속에서 넘어지기 쉽습니다. 바닥을 넓히거나 높이를 낮춰 주세요.",
    ]
    for s in samples:
        out = c.translate(s)
        assert not HANGUL.search(out), (s, out)
    assert "the tank wall" in c.translate("물속 동굴 #1: 출입구 앞 20mm 공간이 수조 벽에 막혀 있습니다.")
    assert c.translate(samples[6]).endswith("for 50 animals.")
    assert c.translate(samples[7]) == (
        "The tank holds about 64 L (estimated at outer size: the inner width and depth plus 6 mm glass, and the water "
        "depth plus 50 mm of substrate and 30 mm of headroom), less than the recommended minimum of 75 L for 50 animals.")
    assert c.translate(samples[8]) == (
        "The tank's outer size is about 462×312 mm (estimated from the inner 450×300 mm plus 6 mm glass), smaller than "
        "the minimum of 600×300 mm for Nano fish (neon and ember tetras, etc.; adult body length 2–3 cm, not counting "
        "the tail fin). A larger tank is recommended.")


def test_shallow_tank_messages_translate_to_english(rules):
    """얕은 수조 보정·오류와 수조 부피 문구가 실제 엔진 결과 그대로 영어로 바뀐다."""
    from app.i18n import catalog

    c = catalog()
    msgs, seen = [], set()
    for size, cage, spec in [
        ("small_fish", Cage(450, 300, 160), "cave"),
        ("small_fish", Cage(900, 450, 150), {"width_mm": 250, "depth_mm": 220, "height_mm": 150,
                                             "entrance_diameter_mm": 60, "top_opening_mm": 50, "wall_thickness_mm": 3}),
        ("small_fish", Cage(600, 300, 120), "cave"),
        ("community", Cage(600, 300, 100), "tunnel"),
        ("small_fish", Cage(300, 300, 220), {"tunnel": 120}),
    ]:
        ctx = actx(rules, size=size, cage=cage, count=6)
        if spec == "cave" or spec == "tunnel":
            item = ItemSpec(spec, defaults(spec, ctx))
        elif "tunnel" in spec:
            item = ItemSpec("tunnel", {**defaults("tunnel", ctx), "inner_diameter_mm": spec["tunnel"]})
        else:
            item = ItemSpec("cave", spec)
        res = run_engine([item], ctx)
        msgs += [i.message_ko for i in res.report.issues]
        seen |= {i.code for i in res.report.issues}
    # 위 다섯 설계로 새 문구가 모두 나온다
    assert {"param_adjusted", "water_too_shallow", "tank_volume_below_recommended", "tank_volume_species_note"} <= seen
    assert any("함께 조정했습니다" in m for m in msgs)
    for m in msgs:
        out = c.translate(m)
        assert not HANGUL.search(out), (m, out)
    out = c.translate("물속 동굴 #1: 물 깊이 120mm 로는 만들 수 없습니다. 생물이 구조물 위로 지나가고 수면 가까이에서 숨 쉴 수 "
                      "있도록 위에 75mm 를 남기면, 가장 낮게 만들어도 높이가 68.3mm 라 물 깊이가 143.3mm 이상이어야 합니다.")
    assert out.endswith("so the water must be at least 143.3 mm deep.")
    assert c.translate("수조 부피가 약 25L(물 깊이에 바닥재 50mm·윗여유 30mm를 더해 어림)로 나노 어종 (네온·엠버 테트라, "
                       "보라라스 등 성체 3cm 이하) 최소 기준 54L 보다 작습니다.").startswith("The tank holds about 25 L")
