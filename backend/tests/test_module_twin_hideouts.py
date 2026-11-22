"""모듈 twin_hideouts (터널로 이은 쌍둥이 은신처): 은신처 A 앞문 ← 둥근 아치 터널 → 은신처 B 앞문, 끼움 결합 셋으로 출력.

라이브러리 공통 기준(닫힌 메시·검증·출력 크기)은 tests/test_modules.py 가 모든 모듈에 확인한다. 여기서는 이 모듈의 설계:
두 은신처가 크기 파라미터를 함께 쓰는지, 햄스터 크기마다 기본값이 오류 없이 통과하는지, 출력 파트 셋이 프린터에 들어가고
조립하면 겹치지 않으며 끼움 턱에 틈새가 있는지, 모의 해석기가 한국어·영어 요청을 이 모듈로 읽는지 본다.
"""

from __future__ import annotations

import itertools

import pytest
from build123d import Pos

from app.domain import Cage
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.modules.assembly import anchor_frame, merge_features, place_parts
from app.modules.definition import Bind, library
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.base import RuleContext
from app.templates.registry import get_template
from app.validation.autofix import clamp_params
from app.validation.checks import overhang_area

KEY = "twin_hideouts"
SIZES = ["dwarf", "syrian"]
# 끼움 턱(1.5mm)은 메시 두께 측정에서 빠지므로(PrintPart.thin_ok) 경고가 없어야 한다
KNOWN_WARNINGS: set[str] = set()


def _ctx(rules, size: str) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size),
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def _volume(a, b) -> float:
    try:
        return float((a & b).volume)
    except Exception:  # noqa: BLE001 - 겹침이 없으면 빈 형상
        return 0.0


def _fixed(rules, size: str, **raw):
    t = get_template(KEY)
    p, _ = clamp_params(t, t.Params.model_validate({**t.Params().model_dump(), **raw}), _ctx(rules, size))
    return t, p


def test_definition_shares_hideout_params_and_plugs_both_ends():
    m = next(d for d in library() if d.key == KEY)
    a, tube, b = m.parts
    assert (a.template, tube.template, b.template) == ("hideout", "tunnel", "hideout")
    assert a.params == b.params  # 두 은신처는 같은 모듈 파라미터에 묶인다
    assert {k: v.param for k, v in a.params.items() if isinstance(v, Bind)} == {
        "width_mm": "width_mm", "depth_mm": "depth_mm", "height_mm": "height_mm",
        "entrance_diameter_mm": "entrance_mm", "wall_thickness_mm": "wall_mm"}
    assert a.params["entrance_count"] == 2  # 앞문은 터널로 이어지므로 뒤 출입구가 바깥 출입구
    # 출입구(둥근 아치)와 같은 단면·폭의 곧은 터널
    assert tube.params["shape"] == "round_arch" and tube.params["bend_angle_deg"] == 0
    assert tube.params["inner_diameter_mm"] == Bind(param="entrance_mm")
    assert [(j.parent, j.child, j.passage, j.mount) for j in m.joins] == [
        ("a.front", "tube.end_b", True, "plug"), ("tube.end_a", "hideout_b.front", "into_child", "plug")]
    assert m.enclosure and m.height_param == "height_mm"


@pytest.mark.parametrize("size", SIZES)
def test_defaults_pass_the_engine_for_each_hamster_size(rules, size):
    """API 와 같은 경로(run_engine: 자동 보정·배치·검증)로 기본값이 오류 없이 통과한다. 경고는 끼움 턱 두께 측정뿐."""
    t = get_template(KEY)
    for count in (1, 2):  # 두 마리면 은신처마다 출입구 2개 기준 (모듈 바깥 출입구도 2개)
        ectx = EngineContext(cage=Cage(1000, 600, 500), species="hamster", size=size, count=count, rules=rules)
        res = run_engine([ItemSpec(template=KEY, params=t.Params().model_dump())], ectx)
        assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]
        warnings = {i.code for i in res.report.issues if i.severity.value == "warning"} - {"count_exceeds"}
        assert warnings <= KNOWN_WARNINGS, warnings
        assert res.items[0].placement is not None
    fixed = {i.details["field"] for i in res.report.issues if i.code == "param_adjusted"}
    # 골든은 출입구·터널 최소 내경 70mm 라 터널 길이만 내경의 1.5배(105mm)로 늘어난다. 드워프는 그대로
    assert fixed == ({"tunnel_length_mm"} if size == "syrian" else set())


@pytest.mark.parametrize("size", SIZES)
def test_build_is_one_watertight_body_and_rule_issues_are_clean(rules, size):
    t, p = _fixed(rules, size)
    assert t.rule_issues(p, _ctx(rules, size)) == []
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    parts, joins = t.expand(p)
    assert merge_features(parts, joins, enclosure=True).entrance_count == 2  # 두 은신처의 뒤 출입구


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("end", ["default", "min", "max"])
def test_print_parts_fit_the_printer_and_do_not_intersect(rules, size, end):
    """기본값과 크기 파라미터 끝값(자동 보정 뒤)에서 출력 파트 셋(은신처 A·터널·은신처 B)이 저마다 닫힌 한 덩어리로
    기준 프린터에 들어가고, 서포트가 필요 없고, 조립 자리에서 서로 겹치지 않는다."""
    t = get_template(KEY)
    raw = {} if end == "default" else {d.name: getattr(d, end) for d in t.defn.params if d.name in t.defn.size_params}
    t, p = _fixed(rules, size, **raw)
    assert t.rule_issues(p, _ctx(rules, size)) == []
    bed = sorted(rules.printing.build_volume_mm[:2])
    pps = t.print_parts(p)
    assert [pp.key for pp in pps] == ["body", "tube", "hideout_b"]
    for pp in pps:
        pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
        assert mesh_health(pm).ok and pm.body_count == 1, pp.key
        assert all(a <= b for a, b in zip(sorted(pm.extents[:2]), bed)), (pp.key, pm.extents)
        assert pm.extents[2] <= rules.printing.build_volume_mm[2], (pp.key, pm.extents)
        assert overhang_area(pm, rules.printing.max_overhang_deg) <= rules.printing.overhang_area_tolerance_mm2, pp.key
    assert max(_volume(a.part, b.part) for a, b in itertools.combinations(pps, 2)) < 1.0


def test_tunnel_plugs_into_both_hideouts_with_clearance(rules):
    """양 끝 끼움 턱과 넓힌 구멍 사이 틈새(0.2mm): 터널을 0.15mm 옮겨도 어느 은신처와도 겹치지 않고 0.5mm 옮기면 걸린다."""
    t, p = _fixed(rules, "dwarf")
    pps = {pp.key: pp.part for pp in t.print_parts(p)}
    parts, joins = t.expand(p)
    placed = place_parts(parts, joins)
    tube = pps["tube"]
    for hideout, key in (("a", "body"), ("hideout_b", "hideout_b")):
        _, tt, u, _n = anchor_frame(placed, hideout, "front")
        for d in (tt, -tt, u):
            assert _volume(pps[key], Pos(*(d * 0.15)) * tube) < 1.0, (hideout, d)
            assert _volume(pps[key], Pos(*(d * 0.5)) * tube) > 1.0, (hideout, d)


def _mock(rules, prompt: str, size: str = "dwarf", language: str = "ko"):
    req = InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo("hamster", "햄스터", size, 1, Cage(800, 500, 400)),
        size_rules=rules.size_rules("hamster", size),
        min_wall_mm=rules.min_wall_for("hamster", size),
        language=language,
        allowed_templates=rules.allowed_templates("hamster"),
    )
    return MockInterpreter().interpret(req).spec


@pytest.mark.parametrize("prompt,language", [
    ("은신처 두 개를 터널로 이어 주세요", "ko"),
    ("쌍둥이 은신처를 오른쪽에 놓아 주세요", "ko"),
    ("방 두 개 은신처가 있으면 좋겠어요", "ko"),
    ("Two hideouts connected by a tunnel, please", "en"),
    ("I'd like twin hideouts in the left corner", "en"),
    # 모듈 이름 그대로: '터널' 이 남아 따로 터널이 하나 더 생기지 않는다
    ("터널로 이은 쌍둥이 은신처", "ko"),
    ("Twin hideouts joined by a tunnel", "en"),
    ("은신처 두개를 터널로 이어줘", "ko"),
    ("two hideouts connected with a tunnel", "en"),
])
def test_mock_interpreter_reads_the_module(rules, prompt, language):
    assert KEY in rules.allowed_templates("hamster")
    spec = _mock(rules, prompt, language=language)
    assert [it.template for it in spec.items] == [KEY]


def test_mock_interpreter_keeps_other_module_words(rules):
    """'터널 달린 은신처' 는 여전히 한 덩어리 모듈, 은신처만 말하면 기본 은신처."""
    assert [it.template for it in _mock(rules, "터널 달린 은신처 하나 주세요").items] == ["hideout_with_tunnel"]
    assert [it.template for it in _mock(rules, "은신처를 왼쪽에 놓아 주세요").items] == ["hideout"]
