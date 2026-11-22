"""모듈 dining_hideout (밥그릇과 물병이 달린 은신처): 은신처 오른쪽 옆면에 그릇 받침, 왼쪽 옆면에 물병 거치대를
슬라이드 결합으로 붙인 모듈.

라이브러리 공통 검사(tests/test_modules.py)에 더해 이 모듈만의 것을 확인한다: 두 햄스터 크기에서 엔진 결과,
그릇 받침·물병 거치대가 옆면에 들어가게 세로를 넓히는 관계, 출력 파트(은신처 본체·그릇 받침·물병 거치대 받침판·물병 컵)와
도브테일 끼움 틈새, 모의 해석기 낱말 (더 단순한 요청 "밥그릇 달린 은신처" 를 가져가지 않는지).
"""

from __future__ import annotations

import pytest
from build123d import Pos

from app.domain import Cage
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MODULE_KEYWORDS, MockInterpreter
from app.llm.spec import to_item_specs
from app.modules.assembly import OVERLAP_MM, PLATE_MM
from app.modules.definition import library
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.base import RuleContext
from app.templates.bottle_stand import total_height
from app.templates.bowl_holder import outer_radius
from app.templates.registry import get_template
from app.validation.autofix import clamp_params
from app.validation.checks import overhang_area
from app.validation.report import Severity

KEY = "dining_hideout"
SIZES = ["dwarf", "syrian"]


@pytest.fixture(scope="module")
def t():
    return get_template(KEY)


def ctx(rules, size: str, count: int = 1) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), count=count,
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


def _parts(t, p) -> dict:
    parts, _ = t.expand(p)
    return {q.id: q.params for q in parts}


def test_definition_is_in_the_library_and_allowed_for_hamsters(t, rules):
    assert t.defn.enclosure and t.defn.height_param == "height_mm"
    assert [p.template for p in t.defn.parts] == ["hideout", "bowl_holder", "bottle_stand"]
    assert [(j.parent, j.child, j.mount) for j in t.defn.joins] == [
        ("hide.right", "bowl.back", "slide"), ("hide.left", "bottle.back", "slide")]
    assert KEY in rules.allowed_templates("hamster")
    assert KEY not in rules.allowed_templates("aquarium")


def test_default_build_is_one_closed_body(t):
    p = t.Params()
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    q = _parts(t, p)
    # 물병 거치대 바닥판(세로 120 의 절반 + 50 = 110) + 연결판 + 은신처(140) + 연결판 + 그릇 받침(지름 90 + 틈새·벽 → 98)
    assert q["bottle"].base_depth_mm == q["bottle"].base_width_mm == 110
    assert m.extents[0] == pytest.approx(110 + 2 * (PLATE_MM - OVERLAP_MM) + 140 + 98, abs=0.1)
    assert m.extents[1] == pytest.approx(120, abs=1e-3)
    # 가장 높은 곳은 물병 컵 입구 (급수관 55 + 마개·급수관 60 + 컵 70)
    assert m.extents[2] == pytest.approx(total_height(q["bottle"]), abs=1e-3) == 185


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
    """여러 마리면 출입구 개수가 2(앞·뒤)로 보정되고, 양옆의 그릇 받침·물병 거치대는 그대로다."""
    c = ctx(rules, size, count=2)
    p, fixes = clamp_params(t, t.Params(), c)
    assert p.entrance_count == 2
    assert not [i for i in fixes if i.severity == Severity.error]
    assert t.rule_issues(p, c) == []
    f = t.features(p)
    assert f.entrance_count == 2
    assert {"front", "back", "left", "right"} <= set(f.access_sides)


def test_print_parts_fit_and_slide_play(t, rules):
    """출력 파트 넷: 은신처 본체(+양옆 연결판·홈), 그릇 받침(+혀), 물병 거치대 받침판, 물병 컵(뒤판 + 혀).
    혀는 틈새를 두고 홈 안에 있고, 옆·바깥으로는 0.5·1mm 만 움직여도 걸리며(도브테일), 위로는 빠진다."""
    p = t.Params()
    pps = _printable(t, p, rules)
    assert set(pps) == {"body", "bowl", "bottle_base", "bottle_holder"}
    body = pps["body"].part
    x_face = p.width_mm / 2
    back = x_face + PLATE_MM - OVERLAP_MM  # 연결판 바깥 면 (자식 뒷면이 닿는 곳)
    bowl, base, holder = pps["bowl"].part, pps["bottle_base"].part, pps["bottle_holder"].part
    # 그릇 받침: 오른쪽(+X). 혀는 그릇 받침에
    assert bowl.bounding_box().min.X < back - 2.0
    # 물병 거치대: 왼쪽(-X). 혀는 연결판에 가장 넓게 닿는 물병 컵(뒤판)에, 받침판은 연결판에 맞닿기만 한다
    assert holder.bounding_box().max.X > -back + 2.0
    assert base.bounding_box().max.X == pytest.approx(-back, abs=1e-3)
    for child, out in ((bowl, Pos(1.0, 0, 0)), (holder, Pos(-1.0, 0, 0))):
        assert _volume(body, child) < 1.0                          # 혀는 틈새를 두고 홈 안에
        for dy in (0.5, -0.5):
            assert _volume(body, Pos(0, dy, 0) * child) > 1.0      # 옆 틈새 ≤ 0.5mm
        assert _volume(body, out * child) > 1.0                    # 바깥으로 당겨도 빠지지 않는다 (도브테일)
        assert _volume(body, Pos(0, 0, 60) * child) < 1.0          # 위로는 빠진다 (홈 위아래가 트였다)
    # 따로 출력하는 파트끼리 겹치지 않는다
    assert _volume(base, holder) < 1.0 and _volume(body, base) < 1.0
    # 은신처는 뒤집어(지붕이 베드), 그릇 받침·받침판은 사용 자세로, 물병 컵은 뒤집어(컵 입구가 베드) 출력한다
    assert pps["body"].rotation[2][2] == pytest.approx(-1.0)
    assert pps["bowl"].rotation[2][2] == pytest.approx(1.0)
    assert pps["bottle_base"].rotation[2][2] == pytest.approx(1.0)
    assert pps["bottle_holder"].rotation[2][2] == pytest.approx(-1.0)


@pytest.mark.parametrize("raw", [
    # 가장 큰 그릇·물병·높은 급수관, 두꺼운 벽, 작은 은신처 (물병 거치대가 가장 높다: 250mm)
    {"width_mm": 90, "depth_mm": 100, "height_mm": 60, "entrance_mm": 100, "entrance_count": 2, "bowl_mm": 140,
     "bowl_height_mm": 60, "bottle_mm": 80, "cap_mm": 20, "spout_height_mm": 80, "spout_drop_mm": 85,
     "holder_height_mm": 85, "wall_mm": 5},
    # 가장 작은 그릇·물병·낮은 급수관, 얇은 벽, 큰 은신처
    {"width_mm": 200, "depth_mm": 200, "height_mm": 110, "entrance_mm": 40, "bowl_mm": 60, "bowl_height_mm": 35,
     "bottle_mm": 45, "cap_mm": 60, "spout_height_mm": 30, "spout_drop_mm": 30, "holder_height_mm": 50, "wall_mm": 2},
])
@pytest.mark.parametrize("size", SIZES)
def test_extremes_are_fixed_and_printable(t, rules, size, raw):
    c = ctx(rules, size)
    p, fixes = clamp_params(t, t.Params(**raw), c)
    assert not [i for i in fixes if i.severity == Severity.error], [i.message_ko for i in fixes]
    assert t.rule_issues(p, c) == []
    q = _parts(t, p)
    assert p.depth_mm >= 2 * outer_radius(q["bowl"])            # 그릇 받침이 오른쪽 옆면 안에
    assert p.depth_mm >= q["bottle"].base_width_mm               # 물병 거치대 바닥판이 왼쪽 옆면 안에
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
    q = _parts(t, t.Params(bowl_mm=130, depth_mm=144, wall_mm=5))
    assert 2 * outer_radius(q["bowl"]) == pytest.approx(142)


def test_tall_bottle_stand_widens_its_base_through_the_hideout_depth(t, rules):
    """물병 거치대 바닥판(은신처 세로의 절반 + 50)은 넘어지지 않게 전체 높이의 절반 이상이어야 한다.
    거치대 제약이 묶인 세로로 되돌려져 자동 보정이 은신처 세로를 넓힌다."""
    c = ctx(rules, "dwarf")
    raw = {"depth_mm": 104, "spout_height_mm": 80, "spout_drop_mm": 85, "holder_height_mm": 85}
    p, fixes = clamp_params(t, t.Params(**raw), c)
    q = _parts(t, p)
    assert total_height(q["bottle"]) == pytest.approx(250)
    assert p.depth_mm == pytest.approx(150) and q["bottle"].base_width_mm == pytest.approx(125)
    assert any(i.code == "param_adjusted" and "넘어지지 않도록" in i.message_ko for i in fixes)
    assert t.rule_issues(p, c) == []


def test_text_is_translated(t):
    from app.i18n import catalog

    cat = catalog()
    d = t.defn
    for ko in [d.name_ko, d.description_ko, *[p.description_ko for p in d.params], *[lim.reason_ko for lim in d.limits],
               *[p.description_ko.split(".")[0].replace(" mm", "") for p in d.params]]:
        assert cat.translate(ko) != ko, ko


def _interpret(rules, prompt: str, size: str = "dwarf", language: str = "ko", cage: Cage | None = None):
    req = InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo("hamster", "햄스터", size, 1, cage or Cage(800, 500, 400)),
        size_rules=rules.size_rules("hamster", size),
        min_wall_mm=rules.min_wall_for("hamster", size),
        language=language,
        allowed_templates=rules.allowed_templates("hamster"),
    )
    return MockInterpreter().interpret(req).spec


@pytest.mark.parametrize("prompt,language", [
    ("밥그릇과 물병이 달린 은신처 만들어 주세요", "ko"),
    ("식당 은신처 하나 넣어 주세요", "ko"),
    ("물병과 밥그릇이 달린 은신처를 오른쪽에 놓아 주세요", "ko"),
    ("a hideout with a food bowl and a water bottle, please", "en"),
])
@pytest.mark.parametrize("size", SIZES)
def test_mock_interpreter_picks_the_module(rules, prompt, language, size):
    cage = Cage(800, 500, 400)
    spec = _interpret(rules, prompt, size, language, cage)
    assert [it.template for it in spec.items] == [KEY]
    if "오른쪽" in prompt:
        assert spec.items[0].placement.zone == "right"
    res = run_engine(to_item_specs(spec), EngineContext(cage=cage, species="hamster", size=size, count=1, rules=rules))
    assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]


@pytest.mark.parametrize("prompt,language", [
    ("밥그릇 달린 은신처 만들어 주세요", "ko"),
    ("물병 달린 은신처", "ko"),
    ("은신처랑 밥그릇이랑 물병 넣어 주세요", "ko"),
    ("a hideout with a food bowl, please", "en"),
])
def test_simpler_requests_are_not_taken(rules, prompt, language):
    """그릇이나 물병 하나만 말하거나 따로 놓는다는 요청은 이 모듈이 가져가지 않는다.
    밥그릇 받침 은신처 모듈(hideout_with_bowl)이 라이브러리에 있으면 "밥그릇 달린 은신처" 는 그 모듈이 된다."""
    keys = [it.template for it in _interpret(rules, prompt, language=language).items]
    assert KEY not in keys
    modules = {m.key for m in library()}
    if "hideout_with_bowl" in modules and ("밥그릇 달린" in prompt or "food bowl" in prompt):
        assert keys == ["hideout_with_bowl"]


@pytest.mark.parametrize("prompt,language", [
    ("물병과 밥그릇이 달린 은신처", "ko"),
    ("밥그릇하고 물병이 달린 은신처", "ko"),
    ("밥그릇, 물병 달린 은신처", "ko"),
    ("물통과 밥그릇이 달린 은신처", "ko"),
    ("hideout with a bowl and a water bottle", "en"),
    ("hideout with a drinker and a bowl", "en"),
])
def test_module_wins_over_one_attachment_modules_in_any_library_order(rules, monkeypatch, prompt, language):
    """"물병과 밥그릇이 달린 은신처" 에는 hideout_with_bowl 낱말("밥그릇이 달린 은신처")도 들어 있다. 모의 해석기는 모든
    모듈의 낱말 가운데 긴 것부터 고르므로 라이브러리(파일) 순서를 뒤집어도 이 모듈이 된다."""
    from app.llm import mock

    for order in (MODULE_KEYWORDS, list(reversed(MODULE_KEYWORDS))):
        monkeypatch.setattr(mock, "MODULE_KEYWORDS", order)
        assert [it.template for it in _interpret(rules, prompt, language=language).items] == [KEY], order[0][0]


@pytest.mark.parametrize("prompt,expected", [
    # 따로 놓는다는 요청은 붙인 모듈이 아니다 ("은신처에 …" 낱말은 '달·붙'까지 맞아야 한다)
    ("은신처에 밥그릇과 물병을 따로 놓아 주세요", ["hideout", "bowl_holder", "bottle_stand"]),
    ("I need a bowl and water bottle attached to the cage wall", ["bowl_holder", "bottle_stand"]),
])
def test_separate_or_wall_requests_are_not_taken(rules, prompt, expected):
    language = "en" if prompt.isascii() else "ko"
    assert [it.template for it in _interpret(rules, prompt, language=language).items] == expected


@pytest.mark.parametrize("size", SIZES)
def test_smallest_depth_keeps_the_bottle_stand_on_the_side_face(t, rules, size):
    """물병 거치대 바닥판은 세로의 절반 + 50 이라 세로 100 미만이면 옆면 밖으로 나간다: 세로 최소값이 100 이다."""
    assert next(d for d in t.defn.params if d.name == "depth_mm").min == 100
    ectx = EngineContext(cage=Cage(1000, 600, 500), species="hamster", size=size, count=1, rules=rules)
    res = run_engine([ItemSpec(template=KEY, params=t.Params(depth_mm=100, bowl_mm=60, width_mm=90).model_dump())], ectx)
    assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]


def test_shrinking_into_a_narrow_cage_keeps_the_design_valid(t, rules):
    """좁은 케이지(세로 150)에서 공간 보정이 크기를 줄여도 물병 거치대 바닥판이 옆면 안에 남고, 저장한 설계를 다시
    검증(revalidate)해도 오류가 없다."""
    from app.services.engine import revalidate

    ectx = EngineContext(cage=Cage(600, 150, 400), species="hamster", size="dwarf", count=1, rules=rules)
    res = run_engine([ItemSpec(template=KEY, params=t.Params(bowl_mm=70).model_dump())], ectx)
    p = res.items[0].params
    assert p.depth_mm >= _parts(t, p)["bottle"].base_width_mm
    assert not [i for i in revalidate(res.items, ectx).issues if i.severity == Severity.error]


@pytest.mark.parametrize("size", SIZES)
def test_tallest_hideout_is_no_taller_than_the_shortest_bottle_stand(t, rules, size):
    """은신처가 물병 거치대보다 높으면 연결판이 거치대 높이에서 끝나 그 위로 물병(형상에 없음)과 은신처 벽 사이에 틈이
    남는다: 은신처 높이 최대값에서 거치대를 가장 낮게 해도 연결판이 지붕까지 올라가고 틈이 없다."""
    c = ctx(rules, size)
    raw = {"height_mm": 110, "entrance_mm": 100, "wall_mm": 5, "spout_height_mm": 30, "spout_drop_mm": 30,
           "holder_height_mm": 50}
    p, _ = clamp_params(t, t.Params(**raw), c)
    assert t.rule_issues(p, c) == []
    assert total_height(_parts(t, p)["bottle"]) >= p.height_mm
    layout = t._layout(p)
    parts, joins = t.expand(p)
    for ji, plan in layout.plans.items():
        if joins[ji].child == "bottle":
            assert plan.h == pytest.approx(p.height_mm)
        assert t._plate_gaps(layout, plan, joins[ji], parts, joins) == ()


@pytest.mark.parametrize("bowl_height", [35, 40, 60])
def test_bowl_collar_leaves_only_a_shallow_groove_against_the_wall(t, bowl_height):
    """사서 쓰는 그릇은 형상에 없어 그릇과 은신처 벽 사이 홈은 엔진이 재지 않는다: 받침 턱을 테두리 − 5mm 까지 올려
    그 홈을 5mm 깊이로 줄이고, 은신처는 그릇보다 높다."""
    p = t.Params(bowl_height_mm=bowl_height)
    q = _parts(t, p)["bowl"]
    assert q.bowl_height_mm - q.collar_height_mm <= 5.0 + 1e-9
