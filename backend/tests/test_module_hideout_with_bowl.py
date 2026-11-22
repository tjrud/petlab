"""모듈 hideout_with_bowl (밥그릇 받침이 달린 은신처): 은신처 오른쪽 옆면에 그릇 받침을 슬라이드 결합으로 붙인 모듈.

라이브러리 공통 검사(tests/test_modules.py)에 더해 이 모듈만의 것을 확인한다: 두 햄스터 크기에서 엔진 결과,
그릇 받침이 옆면에 들어가게 세로를 넓히는 limit, 출력 파트(은신처 본체·그릇 받침)와 도브테일 끼움 틈새, 모의 해석기 낱말.
"""

from __future__ import annotations

import pytest
from build123d import Pos

from app.domain import Cage
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.llm.spec import to_item_specs
from app.modules.assembly import OVERLAP_MM, PLATE_MM
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.base import RuleContext
from app.templates.bowl_holder import outer_radius
from app.templates.registry import get_template
from app.validation.autofix import clamp_params
from app.validation.checks import overhang_area
from app.validation.report import Severity

KEY = "hideout_with_bowl"
SIZES = ["dwarf", "syrian"]


@pytest.fixture(scope="module")
def t():
    return get_template(KEY)


def ctx(rules, size: str) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size),
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def _volume(a, b) -> float:
    inter = a & b
    return float(inter.volume) if inter is not None else 0.0


def _printable(t, p, rules) -> dict:
    """출력 파트마다 출력 자세로: 닫힌 한 덩어리, 오버행 허용 면적 안, 기준 프린터 안."""
    bx, by, bz = rules.printing.build_volume_mm
    out = {}
    for pp in t.print_parts(p):
        pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
        assert mesh_health(pm).ok and pm.body_count == 1, pp.key
        assert pm.bounds[0][2] == pytest.approx(0, abs=1e-6), pp.key
        assert overhang_area(pm, rules.printing.max_overhang_deg) <= rules.printing.overhang_area_tolerance_mm2, pp.key
        assert all(a <= b for a, b in zip(sorted(pm.extents[:2]), sorted([bx, by]))), (pp.key, pm.extents)
        assert pm.extents[2] <= bz, (pp.key, pm.extents)
        out[pp.key] = pp
    return out


def test_definition_is_in_the_library_and_allowed_for_hamsters(t, rules):
    assert t.defn.enclosure and t.defn.height_param == "height_mm"
    assert [p.template for p in t.defn.parts] == ["hideout", "bowl_holder"]
    assert [(j.parent, j.child, j.mount) for j in t.defn.joins] == [("hide.right", "bowl.back", "slide")]
    assert KEY in rules.allowed_templates("hamster")
    assert KEY not in rules.allowed_templates("aquarium")


def test_default_build_is_one_closed_body(t):
    m = part_to_mesh(t.build(t.Params()))
    assert mesh_health(m).ok and m.body_count == 1
    # 은신처(가로 140) + 연결판 + 그릇 받침(지름 90 + 틈새·벽 → 앞뒤 98)
    assert m.extents[0] == pytest.approx(140 + PLATE_MM - OVERLAP_MM + 98, abs=0.1)
    assert m.extents[1] == pytest.approx(120, abs=1e-3) and m.extents[2] == pytest.approx(95, abs=1e-3)


@pytest.mark.parametrize("size", SIZES)
def test_defaults_have_no_rule_issues(t, rules, size):
    c = ctx(rules, size)
    p, fixes = clamp_params(t, t.Params(), c)
    assert not [i for i in fixes if i.severity != Severity.info], [i.message_ko for i in fixes]
    assert t.rule_issues(p, c) == []


@pytest.mark.parametrize("size", SIZES)
def test_engine_passes_defaults_without_errors_or_warnings(t, rules, size):
    """API 와 같은 길(run_engine: 자동 보정·검증·배치)로 한 마리를 넓은 케이지에 놓으면 오류도 경고도 없다."""
    ectx = EngineContext(cage=Cage(1000, 600, 500), species="hamster", size=size, count=1, rules=rules)
    res = run_engine([ItemSpec(template=KEY, params=t.Params().model_dump())], ectx)
    bad = [(i.severity.value, i.code, i.message_ko) for i in res.report.issues if i.severity != Severity.info]
    assert not bad, bad
    assert res.items[0].placement is not None


@pytest.mark.parametrize("size", SIZES)
def test_two_animals_get_two_entrances(t, rules, size):
    """여러 마리면 출입구 개수가 2(앞·뒤)로 보정되고, 뒷면에 문이 나도 오른쪽 옆면의 그릇 받침은 그대로다."""
    c = RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), count=2,
                    printing_max_overhang_deg=rules.printing.max_overhang_deg)
    p, fixes = clamp_params(t, t.Params(), c)
    assert p.entrance_count == 2
    assert not [i for i in fixes if i.severity == Severity.error]
    assert t.rule_issues(p, c) == []
    assert t.features(p).entrance_count == 2


def test_print_parts_fit_and_slide_play(t, rules):
    """출력 파트 둘(은신처 본체+연결판, 그릇 받침+혀). 혀는 틈새를 두고 홈 안에 있고, 옆·바깥으로는 0.5·1mm 만
    움직여도 걸리며(도브테일), 위로는 빠진다 (홈 위아래가 트였다)."""
    p = t.Params()
    pps = _printable(t, p, rules)
    assert set(pps) == {"body", "bowl"} and pps["bowl"].name_ko == "그릇 받침"
    body, bowl = pps["body"].part, pps["bowl"].part
    x_face = p.width_mm / 2
    assert _volume(body, bowl) < 1.0
    assert bowl.bounding_box().min.X < x_face + PLATE_MM - OVERLAP_MM - 2.0  # 혀가 홈 깊이만큼 벽 쪽으로
    for dy in (0.5, -0.5):
        assert _volume(body, Pos(0, dy, 0) * bowl) > 1.0
    assert _volume(body, Pos(1.0, 0, 0) * bowl) > 1.0
    assert _volume(body, Pos(0, 0, 60) * bowl) < 1.0
    # 받침은 사용 자세(바닥판이 베드), 은신처는 뒤집어(지붕이 베드) 출력한다
    assert pps["bowl"].rotation[2][2] == pytest.approx(1.0)
    assert pps["body"].rotation[2][2] == pytest.approx(-1.0)


@pytest.mark.parametrize("raw", [
    {"bowl_mm": 140, "wall_mm": 5, "depth_mm": 80, "width_mm": 90},   # 가장 큰 그릇·두꺼운 벽, 작은 은신처
    {"bowl_mm": 60, "bowl_height_mm": 60, "width_mm": 200, "depth_mm": 200, "height_mm": 160},
])
@pytest.mark.parametrize("size", SIZES)
def test_extremes_are_fixed_and_printable(t, rules, size, raw):
    c = ctx(rules, size)
    p, fixes = clamp_params(t, t.Params(**raw), c)
    assert not [i for i in fixes if i.severity == Severity.error], [i.message_ko for i in fixes]
    assert t.rule_issues(p, c) == []
    holder_width = 2 * (p.bowl_mm / 2 + 1.0 + p.wall_mm)
    assert p.depth_mm >= holder_width  # 그릇 받침이 은신처 옆면 안에
    _printable(t, p, rules)
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1


def test_limit_widens_the_hideout_for_a_big_bowl(t, rules):
    c = ctx(rules, "dwarf")
    p, fixes = clamp_params(t, t.Params(bowl_mm=130, depth_mm=100), c)
    assert p.depth_mm == 144 and p.bowl_mm == 130
    reason = t.defn.limits[0].reason_ko
    assert any(i.code == "param_adjusted" and reason in i.message_ko for i in fixes)
    # 벽이 가장 두꺼워도(5mm) 그릇 받침 외형 폭은 그릇 + 12 라 세로 = 그릇 + 14 면 2mm 여유가 남는다
    parts, _ = t.expand(t.Params(bowl_mm=130, depth_mm=144, wall_mm=5))
    bowl = next(q for q in parts if q.id == "bowl")
    assert 2 * outer_radius(bowl.params) == pytest.approx(142)


def test_text_is_translated(t):
    from app.i18n import catalog

    cat = catalog()
    d = t.defn
    for ko in [d.name_ko, d.description_ko, *[p.description_ko for p in d.params], *[lim.reason_ko for lim in d.limits],
               *[p.description_ko.split(".")[0].replace(" mm", "") for p in d.params]]:
        assert cat.translate(ko) != ko, ko


@pytest.mark.parametrize("prompt,language", [
    ("밥그릇 달린 은신처 만들어 주세요", "ko"),
    ("먹이그릇이 붙은 은신처를 왼쪽에 넣어 주세요", "ko"),
    ("a hideout with a food bowl, please", "en"),
])
@pytest.mark.parametrize("size", SIZES)
def test_mock_interpreter_picks_the_module(rules, prompt, language, size):
    cage = Cage(800, 500, 400)
    req = InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo("hamster", "햄스터", size, 1, cage),
        size_rules=rules.size_rules("hamster", size),
        min_wall_mm=rules.min_wall_for("hamster", size),
        language=language,
        allowed_templates=rules.allowed_templates("hamster"),
    )
    spec = MockInterpreter().interpret(req).spec
    assert [it.template for it in spec.items] == [KEY]
    if "왼쪽" in prompt:
        assert spec.items[0].placement.zone == "left"
    res = run_engine(to_item_specs(spec), EngineContext(cage=cage, species="hamster", size=size, count=1, rules=rules))
    assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]


def test_separate_hideout_and_bowl_stay_separate(rules):
    """'은신처랑 밥그릇' 처럼 붙인다는 말이 없으면 따로 놓는 두 구조물이다."""
    req = InterpretRequest(
        prompt="은신처랑 밥그릇 넣어 주세요",
        habitat=HabitatInfo("hamster", "햄스터", "dwarf", 1, Cage(800, 500, 400)),
        size_rules=rules.size_rules("hamster", "dwarf"),
        min_wall_mm=rules.min_wall_for("hamster", "dwarf"),
        allowed_templates=rules.allowed_templates("hamster"),
    )
    assert [it.template for it in MockInterpreter().interpret(req).spec.items] == ["hideout", "bowl_holder"]


@pytest.mark.parametrize("bowl_height", [35, 40, 60])
def test_bowl_collar_leaves_only_a_shallow_groove_against_the_wall(t, bowl_height):
    """사서 쓰는 그릇은 형상에 없어 그릇 바깥 벽과 은신처 벽 사이 홈(1 + 벽 + 3.7mm 폭)은 엔진이 재지 않는다.
    받침 턱을 그릇 테두리 − 5mm 까지 올려 그 홈을 5mm 깊이로 줄인다."""
    p = t.Params(bowl_height_mm=bowl_height)
    parts, _ = t.expand(p)
    q = next(x for x in parts if x.id == "bowl").params
    assert q.bowl_height_mm - q.collar_height_mm <= 5.0 + 1e-9


@pytest.mark.parametrize("size", SIZES)
def test_low_hideout_is_raised_above_a_tall_bowl(t, rules, size):
    """그릇 테두리가 지붕보다 높지 않게 은신처 높이 ≥ 그릇 높이 + 15 (limits)."""
    c = ctx(rules, size)
    p, _ = clamp_params(t, t.Params(height_mm=60, bowl_height_mm=60), c)
    assert p.height_mm >= 75 and p.bowl_height_mm == 60
    assert t.rule_issues(p, c) == []


@pytest.mark.parametrize("prompt,language,expected", [
    # 은신처를 말하지 않는 'bowl attached' 로 모듈을 고르면 은신처가 하나 더 생긴다
    ("a ramp with a bowl attached", "en", ["ramp", "bowl_holder"]),
    ("a bowl attached to the hideout", "en", [KEY]),
    ("밥그릇 달린 숨숨집", "ko", [KEY]),
    ("숨숨집에 밥그릇 붙여 주세요", "ko", [KEY]),
])
def test_mock_keywords_name_the_hideout(rules, prompt, language, expected):
    req = InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo("hamster", "햄스터", "dwarf", 1, Cage(800, 500, 400)),
        size_rules=rules.size_rules("hamster", "dwarf"),
        min_wall_mm=rules.min_wall_for("hamster", "dwarf"),
        language=language,
        allowed_templates=rules.allowed_templates("hamster"),
    )
    assert [it.template for it in MockInterpreter().interpret(req).spec.items] == expected
