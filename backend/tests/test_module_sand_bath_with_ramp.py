"""모듈 sand_bath_with_ramp (경사로 달린 모래목욕통): 모래목욕통 앞면에 턱 높이 경사로(또는 계단)를 슬라이드 결합으로 붙인 모듈.

라이브러리 공통 검사(tests/test_modules.py)에 더해 이 모듈만의 것을 확인한다: 두 햄스터 크기에서 엔진 결과,
발판이 턱 윗면과 같은 높이이고 폭이 출입 홈과 같은지, 출력 파트(모래목욕통 본체·경사로)와 도브테일 끼움 틈새,
끝값 자동 보정, 모의 해석기 낱말.
"""

from __future__ import annotations

import pytest
from build123d import Pos

from app.domain import Cage
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.llm.spec import to_item_specs
from app.modules.assembly import OVERLAP_MM, PLATE_MM, SLOPE_RISE, place_parts
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.base import RuleContext
from app.templates.ramp import TOP_LANDING_MM, run_length
from app.templates.registry import get_template
from app.templates.sand_bath import entry_width
from app.validation.autofix import clamp_params
from app.validation.checks import overhang_area
from app.validation.report import Severity

KEY = "sand_bath_with_ramp"
SIZES = ["dwarf", "syrian"]
FACE = PLATE_MM - OVERLAP_MM  # 연결판 바깥면 (모래목욕통 앞면에서)


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


def _parts(t, p) -> dict:
    parts, _ = t.expand(p)
    return {q.id: q for q in parts}


def test_definition_is_in_the_library_and_allowed_for_hamsters(t, rules):
    d = t.defn
    assert not d.enclosure and d.height_param is None and d.size_params == ["width_mm", "depth_mm"]
    assert [p.template for p in d.parts] == ["sand_bath", "ramp"]
    assert [(j.parent, j.child, j.mount) for j in d.joins] == [("bath.front", "ramp.landing", "slide")]
    assert KEY in rules.allowed_templates("hamster")
    assert KEY not in rules.allowed_templates("aquarium")


def test_default_build_is_one_closed_body(t):
    p = t.Params()
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    ramp = _parts(t, p)["ramp"].params
    ramp_len = run_length(ramp) + TOP_LANDING_MM
    assert m.extents[0] == pytest.approx(p.width_mm, abs=1e-3)
    assert m.extents[1] == pytest.approx(p.depth_mm + FACE + ramp_len, abs=0.1)
    assert m.extents[2] == pytest.approx(p.basin_depth_mm + 3, abs=1e-3)


@pytest.mark.parametrize("raw", [{}, {"steps": 2}, {"width_mm": 206, "lip_height_mm": 20}, {"width_mm": 220, "lip_height_mm": 35}])
def test_ramp_matches_the_entry_notch(t, rules, raw):
    """경사로 폭 = 출입 홈 폭, 경사로 높이 = 턱 높이. 발판은 턱 윗면 높이에서 끝나고 출입 홈 바로 앞에 가운데로 놓인다.
    연결판은 턱 높이 아래에서 경사로 끝나 출입 홈(턱 위)을 덮지 않는다."""
    p = t.Params(**raw)
    parts = _parts(t, p)
    bath, ramp = parts["bath"].params, parts["ramp"].params
    assert ramp.width_mm == pytest.approx(entry_width(bath))
    assert ramp.height_mm == pytest.approx(bath.lip_height_mm)
    plan = next(iter(t._layout(p).plans.values()))
    lip = p.lip_height_mm
    assert plan.top == pytest.approx(lip) and plan.h == pytest.approx(lip - SLOPE_RISE * FACE)
    m = part_to_mesh(t.build(p))
    y_wall = -p.depth_mm / 2
    half = entry_width(bath) / 2
    # 발판 윗면 = 턱 윗면 높이, 그 위와 출입 홈은 비어 있다
    assert m.contains([[0, y_wall - FACE - 2, lip - 0.5], [half - 2, y_wall - FACE - 2, lip - 0.5]]).all()
    assert not m.contains([[0, y_wall - FACE - 2, lip + 0.5], [0, y_wall + 1.5, lip + 0.5],
                           [0, y_wall - 1.0, lip + 0.3]]).any()
    # 발판은 출입 홈 폭 안에 있다 (홈 바깥 벽 앞은 비어 있다)
    assert not m.contains([[half + 2, y_wall - FACE - 2, lip - 0.5]])[0]
    parts_l, joins = t.expand(p)
    entry = parts["ramp"].template.anchors(ramp)["entry"]
    assert place_parts(parts_l, joins)["ramp"].point(entry.origin)[1] < y_wall - 50
    assert t.features(p).access_sides == ("front",)
    assert t.rule_issues(p, ctx(rules, "dwarf")) == []


@pytest.mark.parametrize("size", SIZES)
def test_defaults_have_no_rule_issues(t, rules, size):
    c = ctx(rules, size)
    p, fixes = clamp_params(t, t.Params(), c)
    assert not fixes, [i.message_ko for i in fixes]
    assert t.rule_issues(p, c) == []


@pytest.mark.parametrize("size", SIZES)
def test_engine_passes_defaults_without_errors_or_warnings(t, rules, size):
    """API 와 같은 길(run_engine: 자동 보정·검증·배치)로 한 마리를 넓은 케이지에 놓으면 오류도 경고도 없다."""
    ectx = EngineContext(cage=Cage(1000, 600, 500), species="hamster", size=size, count=1, rules=rules)
    res = run_engine([ItemSpec(template=KEY, params=t.Params().model_dump())], ectx)
    bad = [(i.severity.value, i.code, i.message_ko) for i in res.report.issues if i.severity != Severity.info]
    assert not bad, bad
    assert res.items[0].placement is not None


def test_print_parts_fit_and_slide_play(t, rules):
    """출력 파트 둘(모래목욕통 본체+연결판, 경사로+혀). 혀는 틈새를 두고 홈 안에 있고, 옆(X)·바깥(−Y)으로는
    0.5·1mm 만 움직여도 걸리며(도브테일), 위로는 빠진다 (홈 위아래가 트였다). 둘 다 사용 자세로 출력한다."""
    p = t.Params()
    pps = _printable(t, p, rules)
    assert set(pps) == {"body", "ramp"}
    body, ramp = pps["body"].part, pps["ramp"].part
    y_face = -p.depth_mm / 2 - FACE
    assert _volume(body, ramp) < 1.0
    assert ramp.bounding_box().max.Y > y_face + 2.0  # 혀가 홈 깊이만큼 벽 쪽으로 나와 있다
    for dx in (0.5, -0.5):
        assert _volume(body, Pos(dx, 0, 0) * ramp) > 1.0
    assert _volume(body, Pos(0, -1.0, 0) * ramp) > 1.0
    assert _volume(body, Pos(0, 0, p.lip_height_mm + 1) * ramp) < 1.0
    for key in ("body", "ramp"):
        assert pps[key].rotation[2][2] == pytest.approx(1.0), key
    assert ramp.bounding_box().max.Z == pytest.approx(p.lip_height_mm, abs=1e-6)


@pytest.mark.parametrize("raw", [
    # 가장 작은 모래목욕통에 가장 높은 턱·완만한 경사 (경사로가 가장 길다)
    {"width_mm": 206, "depth_mm": 206, "basin_depth_mm": 45, "lip_height_mm": 45, "slope_deg": 15},
    # 가장 큰 모래목욕통 (연결판까지 220 × 219.7), 깊은 통, 낮은 턱, 가파른 계단 3단 (디딤판이 짧아 단 수를 줄인다)
    {"width_mm": 220, "depth_mm": 216, "basin_depth_mm": 100, "lip_height_mm": 20, "slope_deg": 30, "steps": 3},
    # 높은 턱에 완만한 계단 3단
    {"width_mm": 220, "depth_mm": 216, "lip_height_mm": 45, "slope_deg": 15, "steps": 3},
])
@pytest.mark.parametrize("size", SIZES)
def test_extremes_are_fixed_and_printable(t, rules, size, raw):
    c = ctx(rules, size)
    p, fixes = clamp_params(t, t.Params(**raw), c)
    assert not [i for i in fixes if i.severity == Severity.error], [i.message_ko for i in fixes]
    assert t.rule_issues(p, c) == []
    assert p.lip_height_mm <= c.size.max_step_height_mm
    if p.steps:
        assert p.lip_height_mm / p.steps <= c.size.max_step_height_mm
    _printable(t, p, rules)
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1


def test_steep_short_stairs_get_fewer_steps(t, rules):
    """낮은 턱·가파른 경사의 계단은 디딤판이 20mm 이상이 되도록 단 수가 줄어든다 (경사로 부품 제약을 모듈 단 수로 되돌린다)."""
    p, fixes = clamp_params(t, t.Params(lip_height_mm=20, slope_deg=30, steps=3), ctx(rules, "dwarf"))
    assert p.steps == 1
    assert any(i.code == "param_adjusted" for i in fixes)


def test_dwarf_lip_is_lowered_to_the_species_step(t, rules):
    p, _ = clamp_params(t, t.Params(lip_height_mm=45), ctx(rules, "dwarf"))
    assert p.lip_height_mm == pytest.approx(35)
    ramp = _parts(t, p)["ramp"].params
    assert ramp.height_mm == pytest.approx(35)  # 경사로도 같이 낮아진다 (같은 파라미터에 묶임)


def test_text_is_translated(t):
    from app.i18n import catalog

    cat = catalog()
    d = t.defn
    for ko in [d.name_ko, d.description_ko, *[p.description_ko for p in d.params],
               *[p.description_ko.split(".")[0].replace(" mm", "") for p in d.params]]:
        assert cat.translate(ko) != ko, ko


@pytest.mark.parametrize("prompt,language", [
    ("계단 달린 모래목욕통 만들어 주세요", "ko"),
    ("경사로가 달린 모래 목욕통을 오른쪽에 넣어 주세요", "ko"),
    ("a sand bath with a ramp, please", "en"),
    ("램프 달린 모래 목욕통", "ko"),
    ("모래목욕통 앞에 경사로를 붙여 주세요", "ko"),
    ("a dust bath with stairs", "en"),
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
    # 계단을 말하면 계단 (램프와 같은 모의 해석 규칙), 아니면 미끄럼 방지 턱 경사로
    assert (spec.items[0].params.steps > 0) == ("계단" in prompt or "stairs" in prompt)
    if "오른쪽" in prompt:
        assert spec.items[0].placement.zone == "right"
    res = run_engine(to_item_specs(spec), EngineContext(cage=cage, species="hamster", size=size, count=1, rules=rules))
    assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]


def test_separate_sand_bath_and_ramp_stay_separate(rules):
    """'모래목욕통이랑 경사로' 처럼 붙인다는 말이 없으면 따로 놓는 두 구조물이다."""
    req = InterpretRequest(
        prompt="모래목욕통이랑 경사로 넣어 주세요",
        habitat=HabitatInfo("hamster", "햄스터", "dwarf", 1, Cage(800, 500, 400)),
        size_rules=rules.size_rules("hamster", "dwarf"),
        min_wall_mm=rules.min_wall_for("hamster", "dwarf"),
        allowed_templates=rules.allowed_templates("hamster"),
    )
    assert sorted(it.template for it in MockInterpreter().interpret(req).spec.items) == ["ramp", "sand_bath"]
