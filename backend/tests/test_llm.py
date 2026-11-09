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
