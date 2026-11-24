"""LLM 파라미터 변환: 스키마 계약, 재시도, 오류 안내, 모의 해석기."""

from __future__ import annotations

import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain import Cage
from app.llm.anthropic_client import AnthropicInterpreter
from app.llm.base import (
    HabitatInfo,
    InterpretRequest,
    LLMConfigError,
    LLMRefusalError,
    LLMSchemaError,
    LLMUnavailableError,
)
from app.llm.interpreter import make_interpreter
from app.llm.mock import MockInterpreter
from app.llm.spec import api_schema, parse_spec, to_item_specs
from app.services.engine import EngineContext, run_engine

CAGE = Cage(600, 400, 300)

VALID = {
    "summary_ko": "왼쪽에 은신처를 두었습니다.",
    "items": [{
        "template": "hideout",
        "params": {"width_mm": 200, "depth_mm": 150, "height_mm": 120, "entrance_diameter_mm": 75,
                   "vent_count": 6, "vent_diameter_mm": 5, "wall_thickness_mm": 3},
        "placement": {"zone": "left", "group": None, "rotation": None},
        "reason_ko": "시리안 기준에 맞춘 크기입니다.",
    }],
    "notes_ko": [],
}


def invalid(**param_overrides) -> dict:
    d = json.loads(json.dumps(VALID))
    d["items"][0]["params"].update(param_overrides)
    return d


@pytest.fixture
def req(rules) -> InterpretRequest:
    return InterpretRequest(
        prompt="은신처를 왼쪽에 넣고 싶어요",
        habitat=HabitatInfo("hamster", "햄스터", "syrian", 1, CAGE),
        size_rules=rules.size_rules("hamster", "syrian"),
        min_wall_mm=rules.min_wall_for("hamster", "syrian"),
    )


# ── 스키마 계약 ─────────────────────────────────────────────


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_api_schema_uses_only_supported_features():
    schema = api_schema()
    banned = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength",
              "maxLength", "minItems", "maxItems", "oneOf", "discriminator"}
    for node in _walk(schema):
        assert not (banned & node.keys()), node
        if node.get("type") == "object" and "properties" in node:
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])


def test_api_schema_states_ranges_in_descriptions():
    hideout = api_schema()["$defs"]["HideoutParams"]["properties"]
    assert "허용 범위: 60~350" in hideout["width_mm"]["description"]
    assert hideout["vent_count"]["type"] == "integer"


def test_api_schema_returns_independent_copies():
    """호출 측이 받은 스키마를 바꿔도 다음 호출 결과(캐시)는 그대로다."""
    a = api_schema()
    snapshot = json.dumps(a, sort_keys=True)
    a["$defs"].clear()
    a["properties"]["items"]["maxItems"] = -1
    b = api_schema()
    assert b is not a
    assert json.dumps(b, sort_keys=True) == snapshot


def test_parse_valid_spec():
    spec = parse_spec(json.dumps(VALID))
    items = to_item_specs(spec)
    assert items[0].template == "hideout" and items[0].hint.zone == "left"


@pytest.mark.parametrize("bad", [
    invalid(width_mm=5),                                   # 범위 위반
    invalid(roof="dome"),                                  # 알 수 없는 키
    {**VALID, "items": []},                                # 빈 목록
    {**VALID, "items": [{**VALID["items"][0], "template": "castle"}]},  # 없는 템플릿
    {k: v for k, v in VALID.items() if k != "summary_ko"},  # 필수 키 누락
    {**VALID, "items": [{**VALID["items"][0], "placement": {"zone": "upstairs", "group": None, "rotation": None}}]},
])
def test_parse_rejects_schema_violations(bad):
    with pytest.raises(ValidationError):
        parse_spec(json.dumps(bad))


# ── Anthropic 해석기 (가짜 클라이언트) ──────────────────────────


def _resp(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return SimpleNamespace(stop_reason=stop_reason, stop_details=None,
                           content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_valid_first_try(req):
    client = FakeClient([_resp(VALID)])
    res = AnthropicInterpreter(client, "test-model", max_retries=2).interpret(req)
    assert res.attempts == 1 and res.provider == "anthropic"
    call = client.calls[0]
    assert call["model"] == "test-model"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "tool_choice" not in call  # 강제 tool_choice 는 최신 모델에서 400 → 구조화 출력 사용
    user_msg = call["messages"][0]["content"]
    # 종별 기준 수치가 species.yaml 에서 주입되었는지
    assert '"출입구 최소 폭(mm)": 70.0' in user_msg
    assert '"터널 최대 길이(mm) — 이 크기 구분에서 가장 작은 개체 몸길이의 2배"' in user_msg
    assert '"터널 최대 휨 각도(도)' in user_msg
    assert "은신처를 왼쪽에" in user_msg


def test_retry_after_schema_violation(req):
    client = FakeClient([_resp(invalid(width_mm=5)), _resp(VALID)])
    res = AnthropicInterpreter(client, "m", max_retries=2).interpret(req)
    assert res.attempts == 2
    second = client.calls[1]["messages"]
    assert second[1]["role"] == "assistant"
    assert second[2]["role"] == "user" and "width_mm" in second[2]["content"]


def test_retry_after_broken_json(req):
    client = FakeClient([_resp('{"summary_ko": "잘린 출', stop_reason="max_tokens"), _resp(VALID)])
    res = AnthropicInterpreter(client, "m", max_retries=2).interpret(req)
    assert res.attempts == 2
    assert "잘렸습니다" in client.calls[1]["messages"][2]["content"]


def test_gives_up_with_user_message(req):
    client = FakeClient([_resp(invalid(width_mm=5))] * 3)
    with pytest.raises(LLMSchemaError) as ei:
        AnthropicInterpreter(client, "m", max_retries=2).interpret(req)
    assert len(client.calls) == 3
    assert "다시 시도" in ei.value.user_message_ko
    assert ei.value.status_code == 422


def test_refusal_is_not_retried(req):
    client = FakeClient([_resp("", stop_reason="refusal")])
    with pytest.raises(LLMRefusalError):
        AnthropicInterpreter(client, "m").interpret(req)
    assert len(client.calls) == 1


def test_connection_error_maps_to_unavailable(req):
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    with pytest.raises(LLMUnavailableError) as ei:
        AnthropicInterpreter(FakeClient([err]), "m").interpret(req)
    assert ei.value.status_code == 503


def test_auth_error_maps_to_config(req):
    r = httpx2.Response(401, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    err = anthropic.AuthenticationError("invalid x-api-key", response=r, body=None)
    with pytest.raises(LLMConfigError):
        AnthropicInterpreter(FakeClient([err]), "m").interpret(req)


def test_missing_model_is_config_error():
    with pytest.raises(LLMConfigError):
        AnthropicInterpreter(FakeClient([]), "")


def test_make_interpreter_selection():
    assert make_interpreter(Settings(llm_provider="auto", anthropic_api_key=None, _env_file=None)).name == "mock"
    s = Settings(llm_provider="auto", anthropic_api_key="sk-test", anthropic_model="some-model", _env_file=None)
    assert make_interpreter(s).name == "anthropic"
    with pytest.raises(LLMConfigError):
        make_interpreter(Settings(llm_provider="anthropic", anthropic_api_key=None, _env_file=None))


# ── 모의 해석기 ─────────────────────────────────────────────


def _mock(req, prompt, previous=None):
    r = InterpretRequest(prompt=prompt, habitat=req.habitat, size_rules=req.size_rules,
                         min_wall_mm=req.min_wall_mm, previous=previous)
    return MockInterpreter().interpret(r).spec


def test_mock_zone_and_species_defaults(req):
    spec = _mock(req, "은신처를 왼쪽에 넣어 주세요")
    it = spec.items[0]
    assert it.template == "hideout" and it.placement.zone == "left"
    assert it.params.entrance_diameter_mm >= req.size_rules.entrance_min_diameter_mm
    assert it.params.vent_diameter_mm <= req.size_rules.gap_trap.safe_max_mm
    assert "모의 해석기" in spec.summary_ko


def test_mock_grouping_and_numbers(req):
    spec = _mock(req, "은신처를 한쪽에 몰아서 크게, 환기구 10개로 해 주세요")
    it = spec.items[0]
    assert it.placement.group == "g1" and it.placement.zone == "left"
    assert it.params.vent_count == 10
    base = _mock(req, "은신처").items[0].params
    assert it.params.width_mm > base.width_mm


@pytest.mark.parametrize("phrase", ["환기구 8개", "환기구는 8개로", "환기구를 8개 정도"])
def test_mock_vent_count_with_particles(req, phrase):
    assert _mock(req, f"은신처, {phrase} 해 주세요").items[0].params.vent_count == 8


def test_mock_revision_keeps_and_changes(req):
    v1 = _mock(req, "은신처를 왼쪽에")
    v2 = _mock(req, "더 작게 해 주세요", previous=v1)
    assert v2.items[0].params.width_mm < v1.items[0].params.width_mm
    assert v2.items[0].placement.zone == "left"  # 언급 안 한 속성은 유지


def test_mock_output_runs_through_engine(req, rules):
    spec = _mock(req, "은신처를 오른쪽 구석에 넣고 싶어요")
    assert spec.items[0].placement.zone == "back_right"
    ctx = EngineContext(CAGE, "hamster", "syrian", 1, rules)
    res = run_engine(to_item_specs(spec), ctx)
    assert res.report.passed, res.report.errors
    p = res.items[0].placement
    assert p.x_mm > CAGE.width_mm / 2 and p.y_mm > CAGE.depth_mm / 2


# ── 조립형 집 (중첩 Params) ──────────────────────────────────

HOUSE_ITEM = {
    "template": "house",
    "params": {
        "width_mm": 200, "depth_mm": 150, "height_mm": 230,
        "walls": {"thickness_mm": 3},
        "floor": {"enabled": False, "thickness_mm": 3},
        "roof": {"kind": "pitched", "pitch_deg": 50, "tip_deg": 50},
        "floors": {"count": 2, "level_height_mm": 110, "plate_thickness_mm": 3, "climb": "external_ramp",
                   "ramp_width_mm": 80, "slope_deg": 30, "exit_side": "back"},
        "doors": {"sides": ["front"], "width_mm": 75},
        "windows": {"count": 2, "diameter_mm": 5},
        "ports": {"sides": [], "diameter_mm": 75, "flange_mm": 3},
    },
    "placement": {"zone": "left", "group": None, "rotation": None, "attach_to": None},
    "reason_ko": "2층 집입니다.",
}
RAMP_ITEM = {
    "template": "ramp",
    "params": {"height_mm": 110, "width_mm": 80, "slope_deg": 30, "steps": 0},
    "placement": {"zone": "auto", "group": None, "rotation": None, "attach_to": {"item_index": 0, "side": "back"}},
    "reason_ko": "2층 착지판에 닿는 램프입니다.",
}


def test_house_spec_with_nested_params_passes_schema():
    spec = parse_spec(json.dumps({**VALID, "items": [HOUSE_ITEM, RAMP_ITEM]}))
    items = to_item_specs(spec)
    assert items[0].template == "house" and items[0].params["roof"]["kind"] == "pitched"
    assert items[0].params["doors"]["sides"] == ["front"]
    assert items[1].hint.attach_to == (0, "back")
    assert items[0].hint.attach_to is None
    # attach_to 를 빼도(옛 출력 형식) 통과한다
    legacy = {**VALID["items"][0], "placement": {"zone": "left", "group": None, "rotation": None}}
    assert to_item_specs(parse_spec(json.dumps({**VALID, "items": [legacy]})))[0].hint.attach_to is None


@pytest.mark.parametrize("patch", [
    {"roof": {"kind": "dome", "pitch_deg": 50, "tip_deg": 50}},                 # 없는 지붕 종류
    {"doors": {"sides": ["front", "front"], "width_mm": 75}},                   # 같은 면 중복
    {"doors": {"sides": [], "width_mm": 75}},                                   # 출입구 없음
    {"floors": {**HOUSE_ITEM["params"]["floors"], "count": 3}},                 # 3층
    {"windows": {"count": 9, "diameter_mm": 5}},                                # 창 개수 범위 밖
    {"ports": {"sides": ["front"], "diameter_mm": 75, "flange_mm": 3}},         # 출입구 면과 충돌
    {"chimney": {"height_mm": 30}},                                             # 모르는 부품
])
def test_house_spec_rejects_bad_parts(patch):
    item = json.loads(json.dumps(HOUSE_ITEM))
    item["params"].update(patch)
    with pytest.raises(ValidationError):
        parse_spec(json.dumps({**VALID, "items": [item]}))


def test_api_schema_has_nested_house_parts():
    schema = api_schema()
    house = schema["$defs"]["HouseParams"]["properties"]
    assert house["roof"]["$ref"].endswith("RoofPart")
    roof = schema["$defs"]["RoofPart"]["properties"]
    assert set(roof["kind"]["enum"]) == {"flat", "pitched", "rounded"}
    assert "허용 범위: 45~65" in roof["pitch_deg"]["description"]
    doors = schema["$defs"]["DoorsPart"]["properties"]["sides"]
    assert doors["type"] == "array" and set(doors["items"]["enum"]) == {"front", "back", "left", "right"}
    placement = schema["$defs"]["LLMPlacement"]["properties"]["attach_to"]
    assert any(opt.get("$ref", "").endswith("AttachTo") for opt in placement["anyOf"])


def test_template_catalog_serializes_nested_parts():
    from app.llm.prompts import template_catalog

    cat = {t["template"]: t for t in template_catalog()}
    json.dumps(cat, ensure_ascii=False)  # 기본값(중첩 모델)이 JSON 으로 직렬화된다
    house = cat["house"]["파라미터"]
    assert house["roof"]["부품"]["kind"]["선택지"] == ["flat", "pitched", "rounded"]
    assert house["doors"]["부품"]["sides"]["목록 선택지"] == ["front", "back", "left", "right"]
    assert house["floors"]["부품"]["count"]["선택지"] == [1, 2]


def test_system_prompt_mentions_house_and_attach_to():
    from app.llm.prompts import SYSTEM_PROMPT

    assert "house" in SYSTEM_PROMPT and "attach_to" in SYSTEM_PROMPT and "external_ramp" in SYSTEM_PROMPT


def test_mock_two_story_house_with_outside_ramp(req, rules):
    spec = _mock(req, "2층 집을 왼쪽에, 바깥 램프로 올라가게 해 주세요")
    assert [it.template for it in spec.items] == ["house", "ramp"]
    house, ramp = spec.items
    assert house.params.floors.count == 2 and house.params.floors.climb == "external_ramp"
    assert ramp.placement.attach_to.item_index == 0 and ramp.placement.attach_to.side == house.params.floors.exit_side
    assert ramp.params.height_mm == house.params.floors.level_height_mm
    other = _mock(req, "창문 3개 있는 경사 지붕 집")
    assert other.items[0].template == "house" and other.items[0].params.windows.count == 3
    assert other.items[0].params.roof.kind == "pitched"
    assert _mock(req, "집 하나").items[0].template == "hideout"  # '집' 만으로는 은신처


# ── 장식 명세 (decor) ────────────────────────────────────────


def test_decor_spec_accepts_pattern_and_text_and_rejects_bad_text():
    item = json.loads(json.dumps(VALID["items"][0]))
    item["decor"] = {"kind": "pattern", "pattern": "honeycomb", "density": 2, "direction": 45, "depth_mm": 0.6,
                     "face": "walls", "mode": "engrave"}
    spec = parse_spec(json.dumps({**VALID, "items": [item]}))
    assert to_item_specs(spec)[0].decor["pattern"] == "honeycomb"
    item["decor"] = {"kind": "text", "text": "뽀송이 Mochi-01", "face": "left", "height_mm": 15, "depth_mm": 0.6}
    assert to_item_specs(parse_spec(json.dumps({**VALID, "items": [item]})))[0].decor["text"] == "뽀송이 Mochi-01"
    assert to_item_specs(parse_spec(json.dumps(VALID)))[0].decor is None  # decor 생략 가능 (옛 출력)
    for bad in ({"kind": "text", "text": "😀", "face": "left", "height_mm": 15, "depth_mm": 0.6},
                {"kind": "text", "text": "열세글자가넘어가는긴이름입니다", "face": "left", "height_mm": 15, "depth_mm": 0.6},
                {"kind": "pattern", "pattern": "plaid", "density": 2, "direction": 0, "depth_mm": 0.6, "face": "walls", "mode": "engrave"},
                {"kind": "text", "text": "Mochi", "face": "left", "height_mm": 15, "depth_mm": 0.6, "svg": "<path/>"}):
        item["decor"] = bad
        with pytest.raises(ValidationError):
            parse_spec(json.dumps({**VALID, "items": [item]}))


def test_api_schema_decor_has_no_regex_and_states_charset():
    schema = api_schema()
    text = schema["$defs"]["TextDecor"]["properties"]["text"]
    assert "pattern" not in text and "한글" in text["description"]
    assert set(schema["$defs"]["PatternDecor"]["properties"]["pattern"]["enum"]) == {
        "stripes", "dots", "scales", "brick", "wave", "honeycomb"}
    decor = schema["$defs"]["HideoutItem"]["properties"]["decor"]
    assert any(opt.get("type") == "null" for opt in decor["anyOf"])
    from app.llm.prompts import SYSTEM_PROMPT
    assert "decor" in SYSTEM_PROMPT and "안전 치수" in SYSTEM_PROMPT


def test_mock_understands_engraving_and_patterns(req):
    spec = _mock(req, "은신처 왼쪽에 '뽀송이'라고 새겨 주세요")
    assert spec.items[0].decor.kind == "text" and spec.items[0].decor.text == "뽀송이"
    spec = _mock(req, "벌집 무늬 은신처")
    assert spec.items[0].decor.kind == "pattern" and spec.items[0].decor.pattern == "honeycomb"
    spec = _mock(req, "터널에 줄무늬")
    assert spec.items[0].template == "tunnel" and spec.items[0].decor is None
    assert _mock(req, "은신처").items[0].decor is None


# ── 조립 항목 (부품 + 연결) ──────────────────────────────────

HIDE = {"width_mm": 140, "depth_mm": 110, "height_mm": 90, "entrance_diameter_mm": 60, "entrance_count": 1,
        "vent_count": 6, "vent_diameter_mm": 4, "wall_thickness_mm": 3}
BOWL = {"bowl_diameter_mm": 90, "bowl_height_mm": 40, "clearance_mm": 1.0, "wall_thickness_mm": 3, "collar_height_mm": 30}
BOTTLE = {"bottle_diameter_mm": 60, "cap_diameter_mm": 40, "spout_height_mm": 55, "spout_drop_mm": 60,
          "holder_height_mm": 70, "base_width_mm": 110, "base_depth_mm": 110, "wall_thickness_mm": 3, "clearance_mm": 1.0}
TUBE = {"length_mm": 100, "inner_diameter_mm": 60, "bend_angle_deg": 0, "wall_thickness_mm": 3, "shape": "tube",
        "path": "arc"}
RAMP = {"height_mm": 60, "width_mm": 80, "slope_deg": 25, "steps": 0}
BATH = {"width_mm": 216, "depth_mm": 216, "basin_depth_mm": 55, "lip_height_mm": 30, "wall_thickness_mm": 3}
PARAMS = {"hideout": HIDE, "bowl_holder": BOWL, "bottle_stand": BOTTLE, "tunnel": TUBE, "ramp": RAMP, "sand_bath": BATH}
PLACEMENT = {"zone": "auto", "group": None, "rotation": None, "attach_to": None}


def assembly(parts: list[tuple[str, str]], connections: list[tuple[str, str, str]], **extra) -> dict:
    """조립 항목 dict: parts = [(id, 템플릿)], connections = [(part, to, at)]."""
    return {
        "template": "assembly",
        "name_ko": "조립 구조물",
        "parts": [{"id": pid, "template": t, "params": PARAMS[t]} for pid, t in parts],
        "connections": [{"part": a, "to": b, "at": at} for a, b, at in connections],
        "placement": PLACEMENT,
        "reason_ko": "이유",
        **extra,
    }


# 설계 문서의 예: 은신처 오른쪽 그릇 받침, 왼쪽 물병 거치대, 앞에 터널, 터널 끝에 은신처 하나 더
EXAMPLE = assembly(
    [("hide", "hideout"), ("bowl", "bowl_holder"), ("bottle", "bottle_stand"), ("tube", "tunnel"), ("hide2", "hideout")],
    [("bowl", "hide", "right"), ("bottle", "hide", "left"), ("tube", "hide", "front"), ("hide2", "tube", "free_end")],
)


def spec_with(*items, **extra) -> str:
    return json.dumps({**VALID, "items": list(items), **extra}, ensure_ascii=False)


def test_assembly_item_parses_and_becomes_an_assembly_item_spec():
    spec = parse_spec(spec_with(EXAMPLE, VALID["items"][0]))
    items = to_item_specs(spec)
    it = items[0]
    assert it.template == "assembly" and it.decor is None and it.hint.zone == "auto"
    # params 는 부품 id → 그 부품 파라미터 (템플릿 Params 로 검증한 값)
    assert list(it.params) == ["hide", "bowl", "bottle", "tube", "hide2"]
    assert it.params["tube"]["shape"] == "tube" and it.params["bowl"]["bowl_diameter_mm"] == 90
    req = it.assembly
    assert req is not None and req.root == "hide" and req.name_ko == "조립 구조물"
    assert [p.template for p in req.parts] == ["hideout", "bowl_holder", "bottle_stand", "tunnel", "hideout"]
    assert req.part("hide2").params == it.params["hide2"]
    assert req.part("hide2").params is not it.params["hide2"]  # 엔진이 한쪽을 고쳐도 다른 쪽은 그대로
    assert [(c.part, c.to, c.at) for c in req.walk()] == [
        ("bowl", "hide", "right"), ("bottle", "hide", "left"), ("tube", "hide", "front"), ("hide2", "tube", "free_end")]
    # 단일 항목은 예전 그대로
    assert items[1].template == "hideout" and items[1].assembly is None


def test_stored_spec_reader_accepts_assembly_and_old_specs_without_missing_parts():
    """저장된 명세 읽기(parse_spec 의 templates=None)도 조립 항목을 받고, missing_parts 가 없던 옛 명세도 읽는다."""
    spec = parse_spec(spec_with(EXAMPLE))
    assert spec.missing_parts == []
    again = parse_spec(spec.model_dump_json())  # 직전 설계(수정 요청)로 다시 읽는 형태
    assert to_item_specs(again)[0].assembly == to_item_specs(spec)[0].assembly
    spec = parse_spec(spec_with(VALID["items"][0], missing_parts=[{"name_ko": "쳇바퀴", "purpose_ko": "운동용"}]))
    assert spec.missing_parts[0].name_ko == "쳇바퀴"


def _rejects(item: dict, *needles: str, templates=None) -> None:
    with pytest.raises(ValidationError) as ei:
        parse_spec(spec_with(item), templates)
    text = str(ei.value)
    for n in needles:
        assert n in text, text


@pytest.mark.parametrize(("parts", "connections", "needle"), [
    # 나무 구조 (structure.tree_problems)
    ([("hide", "hideout"), ("hide", "bowl_holder")], [("hide", "hide", "right")], "겹칩니다"),
    ([("hide", "hideout"), ("bowl", "bowl_holder")], [("bowl", "nowhere", "right")], "없는 부품"),
    ([("hide", "hideout"), ("bowl", "bowl_holder"), ("bottle", "bottle_stand")],
     [("bowl", "hide", "right"), ("bowl", "hide", "left"), ("bottle", "hide", "back")], "한 부품에만"),
    ([("hide", "hideout"), ("tube", "tunnel"), ("hide2", "hideout")],
     [("tube", "hide2", "free_end"), ("hide2", "tube", "free_end")], "순환"),
    ([("hide", "hideout"), ("bowl", "bowl_holder")], [("hide", "bowl", "right")], "기준(첫) 부품"),
    ([("hide", "hideout"), ("bowl", "bowl_holder"), ("bottle", "bottle_stand")], [("bowl", "hide", "right")],
     "어디에도 붙이지 않은"),
    ([("hide", "hideout")], [], "2~8개"),
    ([("hide", "hideout"), ("Bowl", "bowl_holder")], [("Bowl", "hide", "right")], "소문자"),
    ([("hide", "hideout")] + [(f"b{i}", "bowl_holder") for i in range(8)],
     [(f"b{i}", "hide", "auto") for i in range(8)], "2~8개"),
    # 역할로 바로 알 수 있는 잘못
    ([("hide", "hideout"), ("bowl", "bowl_holder"), ("bottle", "bottle_stand")],
     [("bowl", "hide", "right"), ("bottle", "bowl", "right")], "그릇 받침에는 다른 부품을 붙일 수 없습니다"),
    ([("hide", "hideout"), ("bath", "sand_bath")], [("bath", "hide", "right")], "기준 부품(parts 의 첫 부품)으로만"),
    ([("hide", "hideout"), ("bowl", "bowl_holder")], [("bowl", "hide", "free_end")], "free_end 는 터널에 이을 때만"),
    ([("hide", "hideout"), ("tube", "tunnel"), ("tube2", "tunnel")],
     [("tube", "hide", "front"), ("tube2", "tube", "free_end")], "바로 이을 수 없습니다"),
    ([("hide", "hideout"), ("tube", "tunnel"), ("bowl", "bowl_holder")],
     [("tube", "hide", "front"), ("bowl", "tube", "free_end")], "같은 방만"),
    ([("hide", "hideout"), ("tube", "tunnel"), ("hide2", "hideout")],
     [("tube", "hide", "front"), ("hide2", "tube", "left")], "at 을 free_end 로"),
    ([("hide", "hideout"), ("tube", "tunnel"), ("hide2", "hideout"), ("hide3", "hideout")],
     [("tube", "hide", "front"), ("hide2", "tube", "free_end"), ("hide3", "tube", "free_end")], "남은 끝은 1개"),
])
def test_assembly_rejects_bad_trees(parts, connections, needle):
    _rejects(assembly(parts, connections), needle)


def test_tunnel_root_has_two_free_ends():
    """뿌리 터널은 두 끝이 모두 비어 있어 방을 둘 이을 수 있다 (셋은 안 된다)."""
    ok = assembly([("tube", "tunnel"), ("hide", "hideout"), ("hide2", "hideout")],
                  [("hide", "tube", "free_end"), ("hide2", "tube", "auto")])
    parse_spec(spec_with(ok))
    bad = assembly([("tube", "tunnel"), ("hide", "hideout"), ("hide2", "hideout"), ("hide3", "hideout")],
                   [("hide", "tube", "free_end"), ("hide2", "tube", "free_end"), ("hide3", "tube", "free_end")])
    _rejects(bad, "남은 끝은 2개")


@pytest.mark.parametrize("patch", [
    {"connections": [{"part": "bowl", "to": "hide", "at": "top"}]},                         # 위에 얹기 (아직 없음)
    {"connections": [{"part": "bowl", "to": "hide", "at": "right", "mount": "slide"}]},     # 결합 방식은 서버가 정한다
    {"parts": [{"id": "hide", "template": "hideout", "params": HIDE},
               {"id": "bowl", "template": "cave", "params": {}}]},                         # 조립 부품이 아닌 템플릿
    {"parts": [{"id": "hide", "template": "hideout", "params": {**HIDE, "width_mm": 5}},
               {"id": "bowl", "template": "bowl_holder", "params": BOWL}]},                # 부품 파라미터 범위
    {"name_ko": None},                                                                      # 모든 필드는 필수
    {"shift": 3.0},                                                                         # 모르는 키
])
def test_assembly_rejects_schema_violations(patch):
    item = {**assembly([("hide", "hideout"), ("bowl", "bowl_holder")], [("bowl", "hide", "right")]), **patch}
    _rejects(item)


def test_assembly_parts_must_be_allowed_templates():
    item = assembly([("hide", "hideout"), ("bowl", "bowl_holder")], [("bowl", "hide", "right")],
                    placement={"zone": "auto", "group": None, "rotation": None})  # 집·램프가 없는 묶음: attach_to 없음
    parse_spec(spec_with(item), ["hideout", "bowl_holder"])
    _rejects(item, "bowl_holder", templates=["hideout", "tunnel"])


def test_assembly_is_offered_only_with_a_host_template():
    from app.rules.loader import AQUARIUM_TEMPLATES, CAGE_TEMPLATES

    assert "AssemblyItem" in api_schema(CAGE_TEMPLATES)["$defs"]
    assert "AssemblyItem" in api_schema(["sand_bath", "ramp"])["$defs"]
    assert "AssemblyItem" not in api_schema(AQUARIUM_TEMPLATES)["$defs"]  # 어항: 기준 구조물이 없다
    assert "AssemblyItem" not in api_schema(["tunnel", "ramp", "bowl_holder"])["$defs"]
    with pytest.raises(ValidationError):
        parse_spec(spec_with(assembly([("tube", "tunnel"), ("ramp", "ramp")], [("ramp", "tube", "auto")])),
                   ["tunnel", "ramp"])


def test_api_schema_assembly_reuses_param_defs():
    schema = api_schema(["hideout", "tunnel", "bowl_holder", "cave"])
    defs = schema["$defs"]
    item = defs["AssemblyItem"]["properties"]
    assert item["template"]["const"] == "assembly"
    refs = {o["$ref"].rsplit("/", 1)[1] for o in item["parts"]["items"]["anyOf"]}
    assert refs == {"HideoutPart", "TunnelPart", "BowlHolderPart"}  # 물속 동굴은 조립 부품이 아니다
    # 부품 모델은 일반 항목과 같은 Params 정의를 가리킨다 (정의를 두 번 싣지 않는다)
    assert defs["HideoutPart"]["properties"]["params"]["$ref"] == defs["HideoutItem"]["properties"]["params"]["$ref"]
    assert set(defs["HideoutPart"]["required"]) == {"id", "template", "params"}
    assert set(defs["Connection"]["properties"]["at"]["enum"]) == {"front", "back", "left", "right", "free_end", "auto"}
    assert "decor" not in item  # 조립 항목의 장식은 아직 없다
    assert schema["properties"]["missing_parts"]["items"]["$ref"].endswith("MissingPart")
    assert "missing_parts" in schema["required"]  # 구조화 출력에서는 늘 적는다
    # 부품이 한 템플릿뿐이면 합집합 없이 그 모델 하나
    single = api_schema(["hideout"])["$defs"]["AssemblyItem"]["properties"]["parts"]["items"]
    assert single["$ref"].endswith("HideoutPart")


def test_template_keys_drop_fixed_modules(rules):
    """레지스트리에 남은 고정 조립 모듈(library)은 계약에 넣지 않는다: 부품을 잇는 일은 조립 항목이 한다."""
    from app.llm.spec import template_keys
    from app.rules.loader import CAGE_TEMPLATES
    from app.templates.registry import all_templates, primitives

    assert template_keys(rules.allowed_templates("hamster")) == CAGE_TEMPLATES
    assert set(template_keys()) <= set(primitives())
    modules = [t.key for t in all_templates() if t.key not in primitives()]
    assert not set(modules) & {d.removesuffix("Item") for d in api_schema()["$defs"]}
    with pytest.raises(ValueError):
        template_keys(["hideout", "castle"])


def test_api_schema_size_stays_bounded(rules):
    """구조화 출력 스키마가 너무 커지지 않게 (조립 항목은 Params 정의를 다시 쓰므로 크게 늘지 않는다)."""
    cage = json.dumps(api_schema(rules.allowed_templates("hamster")), ensure_ascii=False)
    assert len(cage) < 30_000, len(cage)


# ── 프롬프트: 연결 설명·조립 안내·예시 ───────────────────────────


def test_catalog_has_connection_entries_from_template_metadata():
    from app.llm.prompts import template_catalog
    from app.rules.loader import AQUARIUM_TEMPLATES, CAGE_TEMPLATES

    cat = {t["template"]: t for t in template_catalog(CAGE_TEMPLATES)}
    hide = cat["hideout"]["연결"]
    assert "front: 출입구(터널만)" in hide
    assert "left/right: 옆면(" in hide and "그릇 받침" in hide and "물병 거치대" in hide
    # 뒷면·옆면은 터널을 이으면 출입구를 연다 (뒷면: 출입구 2개, 옆면: 옆면 출입구)
    assert "back/left/right: 옆면(" in hide and "출입구를 낸다" in hide
    assert "free_end" in hide
    assert "front: 출입 면(램프/계단)" in cat["sand_bath"]["연결"]  # 출입 면에는 출입을 막지 않는 램프만
    assert "기준 부품으로만" in cat["sand_bath"]["연결"]
    assert "free_end" in cat["tunnel"]["연결"] and "은신처·집" in cat["tunnel"]["연결"]
    assert "옆면에 붙인다" in cat["bowl_holder"]["연결"]
    assert "height_mm" in cat["ramp"]["연결"]  # 램프 높이는 서버가 붙는 면에 맞춘다
    assert list(cat["hideout"]) == ["template", "이름", "설명", "연결", "파라미터"]
    # 어항(기준 구조물 없음)에는 연결 설명이 없다
    assert all("연결" not in t for t in template_catalog(AQUARIUM_TEMPLATES))
    # 허용된 부품만 이름에 나온다
    only = {t["template"]: t for t in template_catalog(["hideout", "bowl_holder"])}
    assert "물병" not in only["hideout"]["연결"] and "터널" not in only["hideout"]["연결"]
    assert "front: 출입구" in only["hideout"]["연결"]
    # 고정 조립 모듈은 카탈로그에 없다
    assert set(cat) == set(CAGE_TEMPLATES)


def test_user_message_catalog_drops_fixed_modules(req, rules):
    from app.llm.prompts import build_user_message

    r = InterpretRequest(prompt=req.prompt, habitat=req.habitat, size_rules=req.size_rules, min_wall_mm=req.min_wall_mm,
                         allowed_templates=rules.allowed_templates("hamster"))
    msg = build_user_message(r)
    assert '"연결"' in msg and "dining_hideout" not in msg and "twin_hideouts" not in msg


def test_system_prompt_has_composition_block_and_valid_few_shots():
    from app.llm.prompts import FEW_SHOTS, SYSTEM_PROMPT

    for word in ('template "assembly"', "connections", "free_end", "missing_parts", "하나 더", "위에 얹기", "개별 항목"):
        assert word in SYSTEM_PROMPT, word
    assert [p for p, _ in FEW_SHOTS] and len(FEW_SHOTS) == 2
    for prompt, item in FEW_SHOTS:
        assert prompt in SYSTEM_PROMPT
        assert json.dumps(item, ensure_ascii=False) in SYSTEM_PROMPT
        it = to_item_specs(parse_spec(spec_with(item)))[0]  # 예시가 지금 계약을 통과한다
        assert it.template == "assembly" and len(it.assembly.parts) >= 2
    dining, twin = (item for _, item in FEW_SHOTS)
    assert [p["template"] for p in dining["parts"]] == ["hideout", "bowl_holder", "bottle_stand"]
    assert [(c["part"], c["at"]) for c in dining["connections"]] == [("bowl", "right"), ("bottle", "left")]
    assert [p["template"] for p in twin["parts"]] == ["hideout", "tunnel", "hideout"]
    assert [(c["part"], c["to"], c["at"]) for c in twin["connections"]] == [
        ("tube", "hide", "front"), ("hide2", "tube", "free_end")]


def test_system_prompt_states_missing_parts_rules():
    """없는 부품은 응답 언어의 짧은 일반 명사로, 쓰임새는 한 문장으로. 대신 만들어도 적고, 색·장식·크기·목록 부품은 적지 않는다
    (부품 수요로 모아 세므로 이름이 고르게 나와야 한다)."""
    from app.llm.prompts import SYSTEM_PROMPT

    rules = SYSTEM_PROMPT.split("missing_parts 에 {name_ko, purpose_ko}", 1)[1].split("\n조립", 1)[0]
    for word in ("짧은 일반 명사", "종·크기 말", "넣지 않습니다", "한 문장", "대신할 수 있으면", "그대로 적습니다",
                 "색·장식·크기", "적지 않습니다"):
        assert word in rules, word


def test_retry_after_assembly_tree_error(req):
    bad = assembly([("hide", "hideout"), ("bowl", "bowl_holder")], [("bowl", "hide", "free_end")])
    client = FakeClient([_resp(json.loads(spec_with(bad))), _resp(json.loads(spec_with(EXAMPLE)))])
    res = AnthropicInterpreter(client, "m", max_retries=2).interpret(req)
    assert res.attempts == 2 and res.spec.items[0].template == "assembly"
    assert "free_end 는 터널에 이을 때만" in client.calls[1]["messages"][2]["content"]
    schema = client.calls[0]["output_config"]["format"]["schema"]
    assert "AssemblyItem" in schema["$defs"]
