"""모듈 '물병 거치대가 붙은 은신처'(hideout_with_bottle): 은신처 왼쪽 벽에 물병 거치대를 슬라이드 결합으로 붙인다.

라이브러리 공통 검사(tests/test_modules.py)에 더해 이 모듈만의 것을 본다: 햄스터 두 크기 기본값이 보정 없이 깨끗한지,
출력 파트 셋(본체·받침판·물병 컵)이 프린터에 들어가고 서로 겹치지 않는지, 도브테일 틈새, 연결판이 은신처 지붕과 같은
높이에서 끝나 그 위에 끼임 틈이 없는지, 모의 해석기가 한국어·영어 요청을 이 모듈로 읽는지.
"""

from __future__ import annotations

import itertools

import pytest
from build123d import Pos

from app.domain import Cage
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.modules.assembly import OVERLAP_MM, PLATE_MM
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.base import RuleContext
from app.templates.bottle_stand import total_height
from app.templates.registry import get_template
from app.validation.autofix import clamp_params
from app.validation.checks import overhang_area

KEY = "hideout_with_bottle"
HAMSTERS = ["dwarf", "syrian"]


@pytest.fixture(scope="module")
def t():
    return get_template(KEY)


def rctx(rules, size: str) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size),
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def _volume(a, b) -> float:
    inter = a & b
    return float(inter.volume) if inter is not None else 0.0


def test_defaults_build_one_closed_body(t):
    p = t.Params()
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.is_watertight and m.body_count == 1
    # 거치대가 은신처보다 높다 (컵 밑 = 급수관 끝 높이 + 급수관 길이)
    stand = t.expand(p)[0][1].params
    assert m.extents[2] == pytest.approx(total_height(stand), abs=0.1)
    assert total_height(stand) > p.height_mm


@pytest.mark.parametrize("size", HAMSTERS)
def test_defaults_are_clean_for_hamsters_without_autofix(t, rules, size):
    """기본값은 두 햄스터 크기에서 자동 보정할 것이 없고 규칙 오류도 없다."""
    c = rctx(rules, size)
    p, notes = clamp_params(t, t.Params(), c)
    assert p == t.Params() and not notes
    assert t.rule_issues(p, c) == []


@pytest.mark.parametrize("size", HAMSTERS)
def test_engine_passes_without_issues(t, rules, size):
    """API 와 같은 엔진 경로(자동 보정·배치·검증)에서 오류도 경고도 없다."""
    ectx = EngineContext(cage=Cage(1000, 600, 500), species="hamster", size=size, count=1, rules=rules)
    res = run_engine([ItemSpec(template=KEY, params=t.Params().model_dump())], ectx)
    assert res.report.issues == [], [(i.code, i.message_ko) for i in res.report.issues]
    assert res.items[0].placement is not None


def test_group_of_hamsters_needs_no_change(t, rules):
    """은신처 출입구가 앞뒤 2개라 여러 마리 기준(출입구 2개 이상)도 그대로 맞는다."""
    c = RuleContext(rules.size_rules("hamster", "dwarf"), rules.min_wall_for("hamster", "dwarf"), count=2)
    assert c.hideout_min_entrances == 2
    assert t.rule_issues(t.Params(), c) == []
    assert t.features(t.Params()).entrance_count == 2


def _print_parts(t, p, rules) -> dict:
    bx, by, bz = rules.printing.build_volume_mm
    out = {}
    for pp in t.print_parts(p):
        pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
        assert mesh_health(pm).ok and pm.body_count == 1, pp.key
        assert overhang_area(pm, rules.printing.max_overhang_deg) <= rules.printing.overhang_area_tolerance_mm2, pp.key
        assert pm.extents[2] <= bz, (pp.key, pm.extents)
        assert all(a <= b for a, b in zip(sorted(pm.extents[:2]), sorted([bx, by]))), (pp.key, pm.extents)
        out[pp.key] = pp
    return out


@pytest.mark.parametrize("over", [{}, {"spout_height_mm": 80, "spout_drop_mm": 80, "holder_height_mm": 90,
                                       "bottle_mm": 90, "wall_mm": 6, "stand_mm": 160, "depth_mm": 200}])
def test_print_parts_fit_and_do_not_overlap(t, rules, over):
    """본체(은신처 + 연결판·홈), 거치대 받침판, 물병 컵(+ 혀) 세 파트. 가장 큰 값에서도 프린터에 들어간다."""
    p, _ = clamp_params(t, t.Params(**over), rctx(rules, "syrian"))
    pps = _print_parts(t, p, rules)
    assert set(pps) == {"body", "bottle_base", "bottle_holder"}
    for a, b in itertools.combinations(pps.values(), 2):
        assert _volume(a.part, b.part) < 1.0, (a.key, b.key)


def test_dovetail_play(t, rules):
    """물병 컵의 혀는 연결판 홈에 틈새를 두고 들어간다: 옆으로 0.5mm 밀면 닿고, 바깥으로는 빠지지 않고, 위로는 빠진다."""
    p = t.Params()
    pps = _print_parts(t, p, rules)
    body, holder = pps["body"].part, pps["bottle_holder"].part
    face = -p.width_mm / 2 - (PLATE_MM - OVERLAP_MM)       # 연결판 바깥면 (은신처 왼쪽 = -X)
    assert holder.bounding_box().max.X > face + 2.0          # 혀가 홈 깊이만큼 벽 쪽으로 나와 있다
    assert pps["bottle_base"].part.bounding_box().max.X == pytest.approx(face, abs=1e-3)
    for dy in (0.5, -0.5):
        assert _volume(body, Pos(0, dy, 0) * holder) > 1.0   # 옆 틈새 ≤ 0.5mm
    assert _volume(body, Pos(-1.0, 0, 0) * holder) > 1.0     # 바깥으로 당겨도 빠지지 않는다
    assert _volume(body, Pos(0, 0, p.height_mm) * holder) < 1.0  # 위로 들어 올리면 빠진다


def test_plate_ends_flush_with_roof_so_no_gap_above_it(t):
    """거치대가 은신처보다 높아 연결판은 은신처 지붕 높이에서 평평하게 끝나고(경사 없음), 연결판 위 거치대 뒷면 뒤에는
    아무것도 없어 끼임 틈이 없다."""
    p = t.Params()
    layout = t._layout(p)
    (ji, plan), = layout.plans.items()
    assert plan.h == pytest.approx(p.height_mm) and plan.top == pytest.approx(p.height_mm)
    assert plan.t1 - plan.t0 == pytest.approx(p.stand_mm, abs=0.01)
    parts, joins = t.expand(p)
    assert t._plate_gaps(layout, plan, joins[ji], parts, joins) == ()


@pytest.mark.parametrize("size", HAMSTERS)
def test_tallest_hideout_is_no_taller_than_the_shortest_stand(t, rules, size):
    """은신처가 거치대보다 높으면 연결판이 거치대 높이에서 끝나 그 위로 물병(형상에 없음)과 은신처 벽 사이에 12.7mm 틈이
    남는다. 은신처 높이 최대값에서 거치대를 가장 낮게 해도 거치대가 지붕보다 높아 연결판이 지붕까지 올라가고 틈이 없다."""
    c = rctx(rules, size)
    raw = {"height_mm": 110, "spout_height_mm": 30, "spout_drop_mm": 40, "holder_height_mm": 45}
    p, _ = clamp_params(t, t.Params(**raw), c)
    assert p.height_mm == 110 and t.rule_issues(p, c) == []
    parts, joins = t.expand(p)
    stand = next(q for q in parts if q.id == "bottle").params
    assert total_height(stand) > p.height_mm
    layout = t._layout(p)
    (ji, plan), = layout.plans.items()
    assert plan.h == pytest.approx(p.height_mm)
    assert t._plate_gaps(layout, plan, joins[ji], parts, joins) == ()
    # 높이 최대값은 가장 넓은 출입구·두꺼운 벽도 받는다 (출입구 + 벽 두 겹 ≤ 높이)
    widest = {d.name: d.max for d in t.defn.params if d.name in ("entrance_mm", "wall_mm")}
    assert widest["entrance_mm"] + 2 * widest["wall_mm"] <= p.height_mm


@pytest.mark.parametrize("size", HAMSTERS)
def test_shallow_hideout_is_widened_to_fit_the_stand(t, rules, size):
    """은신처 세로가 거치대 바닥판 + 10mm 보다 작으면 자동 보정이 세로를 늘린다 (limits)."""
    c = rctx(rules, size)
    p, _ = clamp_params(t, t.Params(depth_mm=90, stand_mm=130), c)
    assert p.depth_mm == pytest.approx(140) and p.stand_mm == 130
    assert t.rule_issues(p, c) == []


def _mock(rules, prompt: str, size: str = "syrian", language: str = "ko"):
    from app.llm.base import HabitatInfo, InterpretRequest
    from app.llm.mock import MockInterpreter

    entry = rules.species_entry("hamster")
    req = InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo("hamster", entry.display_name, size, 1, Cage(1000, 500, 500), habitat=entry.habitat),
        size_rules=rules.size_rules("hamster", size), min_wall_mm=rules.min_wall_for("hamster", size),
        language=language, allowed_templates=rules.allowed_templates("hamster"),
    )
    return MockInterpreter().interpret(req).spec


@pytest.mark.parametrize("prompt,language", [
    ("물병 달린 은신처 만들어 주세요", "ko"),
    ("급수기 붙은 은신처가 필요해요", "ko"),
    ("유리 수조라 물병 거치대가 붙은 은신처를 넣고 싶어요", "ko"),
    ("I'd like a hideout with a water bottle stand", "en"),
    ("물통 달린 은신처", "ko"),
    ("은신처에 물병 거치대를 붙여 주세요", "ko"),
    ("물병 거치대가 붙은 숨숨집", "ko"),
])
def test_mock_interpreter_reads_the_module(rules, prompt, language):
    assert KEY in rules.allowed_templates("hamster")
    spec = _mock(rules, prompt, language=language)
    assert [it.template for it in spec.items] == [KEY]


def test_mock_keeps_separate_bottle_stand_and_hideout(rules):
    """붙인다는 말 없이 둘을 나열하면 따로 만든다 (모듈로 읽지 않는다)."""
    spec = _mock(rules, "은신처와 물병 거치대를 만들어 주세요")
    assert sorted(it.template for it in spec.items) == ["bottle_stand", "hideout"]


@pytest.mark.parametrize("size", HAMSTERS)
def test_mock_design_runs_through_engine(rules, size):
    from app.llm.spec import to_item_specs

    spec = _mock(rules, "물병 달린 은신처 하나 넣어 주세요", size=size)
    ectx = EngineContext(cage=Cage(1000, 500, 500), species="hamster", size=size, count=1, rules=rules)
    res = run_engine(to_item_specs(spec), ectx)
    assert res.report.passed, [(i.code, i.message_ko) for i in res.report.errors]
    assert [it.key for it in res.items] == [KEY] and res.items[0].placement is not None
