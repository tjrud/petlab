"""어항 종의 LLM 계약: 종마다 다른 템플릿 스키마, 사용자 메시지(종별 기준), 모의 해석기, 영어 안내·카탈로그."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.domain import Cage
from app.i18n import HANGUL, catalog
from app.llm.anthropic_client import AnthropicInterpreter
from app.llm.base import HabitatInfo, InterpretRequest, LLMRefusalError
from app.llm.mock import MockInterpreter
from app.llm.prompts import (
    MATERIAL_RULE,
    MATERIAL_RULE_KEY,
    SYSTEM_PROMPT,
    build_user_message,
    english_instruction,
    template_catalog,
)
from app.llm.spec import api_schema, design_spec_model, parse_spec, template_keys, to_item_specs
from app.rules.loader import AQUARIUM_TEMPLATES, CAGE_TEMPLATES
from app.services.engine import EngineContext, run_engine
from app.templates.base import RuleContext
from app.templates.registry import get_template

TANK = Cage(600, 300, 280)  # 60×30×36cm 수조: 물 깊이 280mm
CAGE = Cage(600, 400, 300)


def make_req(rules, species: str = "aquarium", size: str = "nano_fish", count: int = 10, prompt: str = "동굴",
             cage: Cage | None = None, language: str = "ko", previous=None) -> InterpretRequest:
    entry = rules.species_entry(species)
    cage = cage or (TANK if entry.habitat == "aquarium" else CAGE)
    return InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo(species, entry.display_name, size, count, cage, habitat=entry.habitat),
        size_rules=rules.size_rules(species, size),
        min_wall_mm=rules.min_wall_for(species, size),
        previous=previous,
        language=language,
        allowed_templates=entry.allowed_templates,
    )


def spec_dict(rules, req: InterpretRequest, keys: tuple[str, ...]) -> dict:
    ctx = RuleContext(req.size_rules, req.min_wall_mm, req.habitat.count)
    return {
        "summary_ko": "요약",
        "items": [{"template": k, "params": get_template(k).default_params(ctx).model_dump(),
                   "placement": {"zone": "auto", "group": None, "rotation": None}, "reason_ko": "이유"} for k in keys],
        "notes_ko": [],
    }


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def schema_templates(schema: dict) -> set[str]:
    """스키마의 항목(…Item) 정의가 받는 템플릿 키 (장식 kind·터널 단면 'house' 같은 다른 상수는 빼고)."""
    return {d["properties"]["template"]["const"] for name, d in schema["$defs"].items() if name.endswith("Item")}


# ── 스키마: 템플릿 묶음마다 ──────────────────────────────────


def test_api_schema_for_aquarium_has_only_cave_and_tunnel():
    schema = api_schema(AQUARIUM_TEMPLATES)
    defs = set(schema["$defs"])
    assert {"CaveParams", "TunnelParams"} <= defs
    assert not defs & {"RampParams", "SandBathParams", "HideoutParams"}
    assert schema_templates(schema) == {"cave", "tunnel"}
    text = json.dumps(schema, ensure_ascii=False)
    assert "램프" not in text and "모래목욕통" not in text
    # 장식(decor)·attach_to(집의 바깥 램프)는 어항 계약에 없다: 물속 동굴·터널에는 장식 면이 없고 집·램프도 없다
    assert "decor" not in text and "attach_to" not in text and "HouseParams" not in defs


def test_api_schema_for_hamster_has_no_cave():
    schema = api_schema(CAGE_TEMPLATES)
    assert schema_templates(schema) == {"hideout", "tunnel", "ramp", "sand_bath", "house"}
    assert "CaveParams" not in schema["$defs"]
    # 케이지 계약은 main 그대로 모든 항목에 decor, 배치에 attach_to 가 있다
    assert all("decor" in d["properties"] for n, d in schema["$defs"].items() if n.endswith("Item"))
    assert "attach_to" in schema["$defs"]["LLMPlacement"]["properties"]
    # 기본값(모든 템플릿)은 저장된 버전 읽기용: 여섯 템플릿 모두
    assert schema_templates(api_schema()) == {"hideout", "tunnel", "ramp", "sand_bath", "house", "cave"}


def test_schema_is_cached_per_template_set_regardless_of_order():
    assert template_keys(("tunnel", "cave")) == template_keys(["cave", "tunnel", "cave"]) == ("tunnel", "cave")
    assert design_spec_model(("tunnel", "cave")) is design_spec_model(("cave", "tunnel"))
    assert design_spec_model(AQUARIUM_TEMPLATES) is not design_spec_model(CAGE_TEMPLATES)
    assert api_schema(("tunnel", "cave")) == api_schema(("cave", "tunnel"))
    a = api_schema(AQUARIUM_TEMPLATES)
    a["$defs"].clear()  # 받은 dict 를 바꿔도 캐시는 그대로
    assert "CaveParams" in api_schema(AQUARIUM_TEMPLATES)["$defs"]
    with pytest.raises(ValueError):
        template_keys(("castle",))
    with pytest.raises(ValueError):
        template_keys(())


def test_api_schema_for_aquarium_uses_only_supported_features():
    banned = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength",
              "maxLength", "minItems", "maxItems", "oneOf", "discriminator"}
    for node in _walk(api_schema(AQUARIUM_TEMPLATES)):
        assert not (banned & node.keys()), node
        if node.get("type") == "object" and "properties" in node:
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
    cave = api_schema(AQUARIUM_TEMPLATES)["$defs"]["CaveParams"]["properties"]
    assert "허용 범위: 40.0~65" in cave["roof_slope_deg"]["description"]


def test_parse_spec_rejects_templates_the_species_cannot_have(rules):
    req = make_req(rules)
    ok = json.dumps(spec_dict(rules, req, ("cave", "tunnel")))
    assert [it.template for it in parse_spec(ok, AQUARIUM_TEMPLATES).items] == ["cave", "tunnel"]
    for bad in ("ramp", "sand_bath", "hideout"):
        hreq = make_req(rules, "hamster", "syrian", 1)
        text = json.dumps(spec_dict(rules, hreq, ("cave", bad)))
        with pytest.raises(ValidationError):
            parse_spec(text, AQUARIUM_TEMPLATES)
        assert len(parse_spec(text).items) == 2  # 저장된 버전 읽기(모든 템플릿)는 그대로 받는다
    with pytest.raises(ValidationError):
        parse_spec(ok, CAGE_TEMPLATES)  # 햄스터에는 물속 동굴이 없다


# ── 사용자 메시지 ───────────────────────────────────────────


@pytest.mark.parametrize("size", ["shrimp", "nano_fish", "small_fish", "community"])
def test_user_message_for_aquarium(rules, size):
    req = make_req(rules, size=size)
    msg = build_user_message(req)
    s, aq = req.size_rules, req.size_rules.aquatic
    for absent in ("램프 최대 경사", "오르는 구조물 최대 높이", "최대 턱(단) 높이", "모래목욕통 최소", "터널 최대 휨 각도",
                   "몸길이의 2배", "은신처 최소 출입구", "케이지 내부 치수", "None", "null"):
        assert absent not in msg.split("## 사용 가능한 템플릿")[0], absent
    head = msg.split("## 사용 가능한 템플릿")[0]
    assert '"어항 내부 치수(mm)"' in head and '"물 깊이(Z) — 바닥재 위~수면": 280\n' in head
    assert '"물 깊이(mm) — 사육 환경의 높이(Z)는 바닥재 위~수면": 280,' in head
    assert f'"구조물 위 최소 물 깊이(mm) — 생물이 구조물 위로 지나가고 수면에서 숨 쉴 수 있게": {aq.structure_top_clearance_mm}' in head
    assert f'"구조물 최대 높이(mm) — 물 깊이 − 구조물 위 최소 물 깊이": {280.0 - aq.structure_top_clearance_mm}' in head
    slope = max(40.0, aq.ceiling_min_slope_deg)
    assert f'"물속 동굴 지붕 경사 최소(도) — 안쪽 천장에 공기가 남지 않고 서포트 없이 출력되도록": {slope}' in head
    assert (f'"물속 동굴 꼭대기 구멍 최소 폭(mm) — 공기가 빠지는 구멍이자 몸이 끼지 않는 통과 폭": '
            f'{s.gap_trap.passable_min_mm}') in head
    assert f'"물속 동굴 최소 출입구 개수 (이 마릿수 기준) — 2개면 앞뒤로 뚫린 관통형": {s.hideout_min_entrances.for_count(10)}' in head
    assert '"터널 최대 길이(mm)": "없음' in head
    assert '"만들 수 있는 구조물": "cave(물속 동굴), tunnel(터널)만' in head
    assert '"속이 빈 닫힌 공간": "금지' in head
    # 소재 안전은 화면의 출력·설치 안내(글10)를 따른다: 모델이 '안전하다'·'무독성'이라 단정하거나 코팅을 권하지 않게
    assert f'"{MATERIAL_RULE_KEY}": "단정 금지' in head
    for phrase in ("'안전하다'", "'무독성이다'", "코팅·레진", "화면의 출력·설치 안내를 따르라고만"):
        assert phrase in MATERIAL_RULE and phrase in head, phrase
    for part in ("summary_ko", "reason_ko", "notes_ko"):
        assert part in MATERIAL_RULE, part
    catalog_part = msg.split("## 사용 가능한 템플릿")[1].split("## 보호자 요구사항")[0]
    assert [t["template"] for t in json.loads(catalog_part)] == ["tunnel", "cave"]


def test_user_message_for_hamster_has_no_aquarium_rows(rules):
    msg = build_user_message(make_req(rules, "hamster", "syrian", 1))
    head, rest = msg.split("## 사용 가능한 템플릿")
    assert '"케이지 내부 치수(mm)"' in head and '"램프 최대 경사(도)": 30.0' in head
    assert '"모래목욕통 최소 내부 [가로, 세로](mm)": [\n    200.0,\n    200.0\n  ]' in head
    for absent in ("물 깊이", "어항", "물속 동굴", "만들 수 있는 구조물", "속이 빈", MATERIAL_RULE_KEY):
        assert absent not in head, absent
    templates = [t["template"] for t in json.loads(rest.split("## 보호자 요구사항")[0])]
    assert templates == ["hideout", "tunnel", "ramp", "sand_bath", "house"]


def test_template_catalog_filters_by_allowed():
    assert [t["template"] for t in template_catalog(AQUARIUM_TEMPLATES)] == ["tunnel", "cave"]
    assert [t["template"] for t in template_catalog()] == ["hideout", "tunnel", "ramp", "sand_bath", "house", "cave"]


def test_system_prompt_is_species_neutral():
    assert "케이지" in SYSTEM_PROMPT and "어항" in SYSTEM_PROMPT and "햄스터" not in SYSTEM_PROMPT
    assert "사용 가능한 템플릿" in SYSTEM_PROMPT


def test_english_instruction_has_no_hamster_for_aquarium(rules):
    for size in ("shrimp", "nano_fish", "small_fish", "community"):
        text = english_instruction(make_req(rules, size=size, language="en"))
        assert "hamster" not in text.lower() and not HANGUL.search(text), text
        assert "for pet owners" in text and "aquarium" in text
    assert "Nano fish (neon and ember tetras" in english_instruction(make_req(rules, language="en"))
    ham = english_instruction(make_req(rules, "hamster", "dwarf", 1, language="en"))
    assert "for pet owners" in ham and "Call the pet a Dwarf hamster (Djungarian, Campbell's, Roborovski)." in ham
    msg = build_user_message(make_req(rules, language="en"))
    assert "Output language" in msg and "hamster" not in msg.split("Output language")[1].lower()


# ── Anthropic 해석기 (가짜 클라이언트) ──────────────────────────


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _resp(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return SimpleNamespace(stop_reason=stop_reason, stop_details=None,
                           content=[SimpleNamespace(type="text", text=text)])


def test_anthropic_uses_species_schema_and_retries_on_cage_template(rules):
    req = make_req(rules, prompt="동굴과 경사로를 만들어 주세요")
    bad = spec_dict(rules, make_req(rules, "hamster", "syrian", 1), ("ramp",))
    good = spec_dict(rules, req, ("cave", "tunnel"))
    client = FakeClient([_resp(bad), _resp(good)])
    res = AnthropicInterpreter(client, "m", max_retries=2).interpret(req)
    assert res.attempts == 2 and [it.template for it in res.spec.items] == ["cave", "tunnel"]
    schema = client.calls[0]["output_config"]["format"]["schema"]
    assert schema_templates(schema) == {"cave", "tunnel"}
    assert "template" in client.calls[1]["messages"][2]["content"]  # 재시도 안내에 어긴 곳이 적힌다
    out = run_engine(to_item_specs(res.spec), EngineContext(TANK, "aquarium", "nano_fish", 10, rules))
    assert out.report.passed, out.report.errors

    hreq = make_req(rules, "hamster", "syrian", 1)
    client = FakeClient([_resp(spec_dict(rules, hreq, ("hideout",)))])
    AnthropicInterpreter(client, "m").interpret(hreq)
    assert schema_templates(client.calls[0]["output_config"]["format"]["schema"]) == set(CAGE_TEMPLATES)


def test_refusal_message_by_habitat(rules):
    with pytest.raises(LLMRefusalError) as ei:
        AnthropicInterpreter(FakeClient([_resp("", "refusal")]), "m").interpret(make_req(rules))
    assert ei.value.user_message_ko == ("요청하신 내용으로는 설계를 진행할 수 없어요. "
                                        "어항에 넣을 구조물에 관한 요구사항으로 다시 입력해 주세요.")
    assert "hamster" not in catalog().translate(ei.value.user_message_ko).lower()
    assert "aquarium" in catalog().translate(ei.value.user_message_ko)
    with pytest.raises(LLMRefusalError) as ei:
        AnthropicInterpreter(FakeClient([_resp("", "refusal")]), "m").interpret(make_req(rules, "hamster", "syrian", 1))
    assert ei.value.user_message_ko == ("요청하신 내용으로는 설계를 진행할 수 없어요. "
                                        "케이지 구조물에 관한 요구사항으로 다시 입력해 주세요.")  # 햄스터는 예전 그대로


# ── 모의 해석기 ─────────────────────────────────────────────


def mock(rules, prompt, **kw):
    return MockInterpreter().interpret(make_req(rules, prompt=prompt, **kw)).spec


def templates_of(spec) -> list[str]:
    return [it.template for it in spec.items]


def test_mock_aquarium_keywords(rules):
    assert templates_of(mock(rules, "동굴 하나만")) == ["cave"]
    assert templates_of(mock(rules, "cave please", language="en")) == ["cave"]
    assert templates_of(mock(rules, "숨을 곳이 필요해요")) == ["cave"]
    assert templates_of(mock(rules, "모래 바닥에 둘 동굴")) == ["cave"]  # 어항의 모래는 바닥재
    assert templates_of(mock(rules, "a cave for the sand bed", language="en")) == ["cave"]
    assert templates_of(mock(rules, "a shelter and a swim-through", language="en")) == ["cave", "tunnel"]
    assert templates_of(mock(rules, "새우가 지나갈 관 하나")) == ["tunnel"]
    assert templates_of(mock(rules, "긴 관이랑 동굴")) == ["tunnel", "cave"]
    # 다른 낱말 속의 '관'(관상어·수족관·관찰)은 터널이 아니다
    spec = mock(rules, "관상어 수족관에서 관찰하기 좋게 예쁘게")
    assert templates_of(spec) == ["cave"]
    assert spec.notes_ko == ["구체적인 구조물 언급이 없어 기본 물속 동굴 1개로 설계했습니다."]


@pytest.mark.parametrize("prompt,lang", [("출입구가 앞뒤에 있는 동굴", "ko"), ("a cave open front and back", "en"),
                                         ("앞뒤가 뚫린 동굴", "ko"), ("a cave open at both ends", "en")])
def test_mock_cave_door_phrases_are_not_placement(rules, prompt, lang):
    """'앞뒤에'(뒤에)·'front and back'(front)은 출입구 개수를 말하는 것이지 수조 앞·뒤에 놓으라는 말이 아니다."""
    [item] = mock(rules, prompt, language=lang).items
    assert item.template == "cave" and item.params.entrance_count == 2
    assert item.placement.zone == "auto"


@pytest.mark.parametrize("prompt,lang,zone", [("왼쪽에 앞뒤가 뚫린 동굴", "ko", "left"),
                                              ("뒤쪽에 출입구가 앞뒤에 있는 동굴", "ko", "back"),
                                              ("a cave open front and back on the left", "en", "left")])
def test_mock_cave_door_phrases_keep_real_zone_requests(rules, prompt, lang, zone):
    assert mock(rules, prompt, language=lang).items[0].placement.zone == zone


def test_mock_swim_through_verb_is_not_a_tunnel(rules):
    """'헤엄쳐 지나갈 수 있는 동굴'의 동사 swim through 는 터널을 더하지 않는다 (이름씨 swim-through 는 터널)."""
    assert templates_of(mock(rules, "a cave that fish can swim through", language="en")) == ["cave"]
    assert templates_of(mock(rules, "two swim throughs", language="en")) == ["tunnel"]
    assert templates_of(mock(rules, "a swimthrough", language="en")) == ["tunnel"]


def test_mock_aquarium_reason_text(rules):
    spec = mock(rules, "동굴")
    assert spec.items[0].reason_ko == ("요구사항에서 '물속 동굴'을(를) 찾아 나노 어종 (네온·엠버 테트라 등, 꼬리지느러미 뺀 몸길이 "
                                       "2~3cm) 수조 기준에 맞춰 구성했습니다.")
    en = catalog().translate(spec.items[0].reason_ko)
    assert en == ("Found 'Underwater cave' in your request and used the standard tank values for the "
                  "Nano fish (neon and ember tetras, etc.; adult body length 2–3 cm, not counting the tail fin).")
    spec = mock(rules, "a cave and a ramp", language="en", size="community")
    assert spec.items[0].reason_ko == ("Found 'Underwater cave' in your request and used the standard tank values "
                                       "for the Community tank (shrimp, nano and small fish kept together).")
    assert spec.notes_ko == ["Left out because they can't be made for aquarium (freshwater fish and shrimp): "
                             "Ramp/stairs"]
    for text in (spec.summary_ko, *spec.notes_ko, *(it.reason_ko for it in spec.items)):
        assert not HANGUL.search(text) and "hamster" not in text.lower(), text


def test_mock_cave_entrances(rules):
    assert mock(rules, "출입구가 하나인 동굴", size="shrimp").items[0].params.entrance_count == 1
    assert mock(rules, "앞뒤가 뚫린 동굴").items[0].params.entrance_count == 2
    assert mock(rules, "a cave with one entrance", size="shrimp", language="en").items[0].params.entrance_count == 1
    assert mock(rules, "출입구 30mm 동굴").items[0].params.entrance_diameter_mm == 30
    assert mock(rules, "a cave with a 3 cm entrance", language="en").items[0].params.entrance_diameter_mm == 30
    # 물고기 구분에서 출입구 하나를 요청해도 엔진이 관통형(2개)으로 맞춘다
    spec = mock(rules, "출입구 1개짜리 동굴")
    assert spec.items[0].params.entrance_count == 1
    out = run_engine(to_item_specs(spec), EngineContext(TANK, "aquarium", "nano_fish", 10, rules))
    assert out.items[0].params.entrance_count == 2 and out.report.passed


def test_mock_aquarium_revision(rules):
    v1 = mock(rules, "동굴이랑 터널을 왼쪽에")
    v2 = mock(rules, "동굴을 더 크게", previous=v1)
    assert templates_of(v2) == ["cave", "tunnel"]
    assert v2.items[0].params.width_mm > v1.items[0].params.width_mm
    assert v2.items[1].params == v1.items[1].params and v2.items[0].placement.zone == "left"
    assert templates_of(mock(rules, "터널 빼 주세요", previous=v1)) == ["cave"]


def test_mock_drops_previous_items_the_species_cannot_have(rules):
    """규칙 파일이 바뀌어 직전 설계의 구조물을 더는 만들 수 없으면 실제 LLM 처럼 빼고 알린다."""
    hreq = make_req(rules, "hamster", "syrian", 1)
    previous = parse_spec(json.dumps(spec_dict(rules, hreq, ("tunnel", "ramp"))))
    spec = mock(rules, "더 작게", previous=previous)
    assert templates_of(spec) == ["tunnel"]
    assert spec.notes_ko == ["어항 (담수 관상어·새우)에는 만들 수 없는 구조물이라 제외했습니다: 램프/계단"]


def test_mock_output_runs_clean_for_every_aquarium_size(rules):
    for size, count in (("shrimp", 10), ("nano_fish", 10), ("small_fish", 6), ("community", 10)):
        spec = mock(rules, "동굴이랑 터널", size=size, count=count)
        assert templates_of(spec) == ["cave", "tunnel"]
        out = run_engine(to_item_specs(spec), EngineContext(TANK, "aquarium", size, count, rules))
        assert out.report.passed, (size, out.report.errors)
        warnings = [i.message_ko for i in out.report.issues if i.severity.value == "warning"]
        assert not warnings, (size, warnings)


# ── 영어 카탈로그 ───────────────────────────────────────────


def test_rule_file_strings_have_english_without_hamster(rules):
    c = catalog()
    entry = rules.species_entry("aquarium")
    texts = [entry.display_name, *entry.print_notes_ko, entry.size_hint_ko]
    for size in entry.sizes.values():
        texts += [size.display_name] + ([size.min_count_warning_ko] if size.min_count_warning_ko else [])
    for t in texts:
        out = c.translate(t)
        assert out != t and not HANGUL.search(out) and "hamster" not in out.lower(), (t, out)


def test_size_name_messages_are_species_neutral_in_english(rules):
    """{크기 구분 이름}이 들어가는 문구는 영어에서 'hamsters' 를 붙이지 않는다 (크기 구분 이름에 동물 이름이 들어 있다)."""
    c = catalog()
    nano = rules.size_rules("aquarium", "nano_fish").display_name
    out = c.translate(f"물속 동굴 #1: 출입구 15mm 가 {nano} 기준 최소 20mm 보다 작습니다.")
    assert out == ("Underwater cave #1: Entrance 15 mm is smaller than the 20 mm minimum for the "
                   "Nano fish (neon and ember tetras, etc.; adult body length 2–3 cm, not counting the tail fin).")
    out = c.translate(f"물속 동굴 #1: 출입구 폭 15 → 20 로 보정했습니다. {nano} 출입구는 최소 20mm 이상이어야 합니다")
    assert "hamster" not in out.lower() and not HANGUL.search(out), out
    assert c.translate(f"{nano} 터널 내경은 최소 20mm 이상이어야 합니다").startswith("Tunnel inner diameter for the Nano fish")
    # 햄스터 문구는 크기 구분 이름에 동물 이름이 들어 있어 그대로 읽힌다
    assert c.translate("골든 (시리안) 출입구는 최소 70mm 이상이어야 합니다") == \
        "Entrances for the Golden (Syrian) hamster must be at least 70 mm"
    assert c.translate("요구사항에서 '은신처'을(를) 찾아 햄스터 골든 (시리안) 기준값으로 구성했습니다.") == \
        "Found 'Hideout' in your request and used the standard Hamster values for a Golden (Syrian) hamster."
    assert c.translate("드워프 (정글리안·캠벨·로보로브스키)") == "Dwarf hamster (Djungarian, Campbell's, Roborovski)"
    # 저장된 옛 설계·검증 문구의 옛 나노 어종 이름도 그대로 번역된다
    assert c.translate("나노 어종 (네온·엠버 테트라, 보라라스 등 성체 3cm 이하)") == \
        "Nano fish (neon and ember tetras, Boraras, etc.; adults up to 3 cm)"


# ── main 병합: 터널 단면·조립형 집·장식과 어항 계약 ──────────────────────────


def test_aquarium_schema_keeps_tunnel_shape_and_path():
    """#35 터널 단면·S자 파라미터는 어항 계약에도 그대로 있다 (터널은 케이지·어항 공통)."""
    props = api_schema(AQUARIUM_TEMPLATES)["$defs"]["TunnelParams"]["properties"]
    assert {"shape", "path"} <= set(props)
    assert set(props["shape"]["enum"]) == {"pointed_arch", "round_arch", "tube", "box", "house"}


def test_aquarium_parse_rejects_house_decor_and_attach_to(rules):
    req = make_req(rules)
    ok = spec_dict(rules, req, ("cave",))
    parse_spec(json.dumps(ok), AQUARIUM_TEMPLATES)
    for bad in ({**ok["items"][0], "decor": None},
                {**ok["items"][0], "placement": {**ok["items"][0]["placement"], "attach_to": None}}):
        with pytest.raises(ValidationError):
            parse_spec(json.dumps({**ok, "items": [bad]}), AQUARIUM_TEMPLATES)
    hreq = make_req(rules, "hamster", "syrian", 1)
    with pytest.raises(ValidationError):
        parse_spec(json.dumps(spec_dict(rules, hreq, ("house",))), AQUARIUM_TEMPLATES)


def test_aquarium_user_message_mentions_shape_advice_and_no_decor(rules):
    msg = build_user_message(make_req(rules))
    head = msg.split("## 사용 가능한 템플릿")[0]
    assert "pointed_arch(기본)·house 권장" in head and "round_arch·tube·box" in head
    assert '"장식(무늬·글귀 각인)"' in head
    assert "house(집)" in head.split('"만들 수 있는 구조물"')[1].split("\n")[0]  # 만들 수 없는 목록에 집도 있다
    hmsg = build_user_message(make_req(rules, "hamster", "syrian", 1))
    assert "S자 터널 한 번 휨 최대 각도" in hmsg and "장식(무늬" not in hmsg and "어항 터널 단면" not in hmsg


@pytest.mark.parametrize("prompt,lang", [("2층 집처럼 생긴 동굴", "ko"), ("창문 있는 집", "ko"), ("경사 지붕 집", "ko"),
                                         ("a two-story house with windows", "en")])
def test_mock_house_words_mean_cave_in_aquarium(rules, prompt, lang):
    """집 키워드(2층·창문·지붕)는 어항에서 집 템플릿을 고르지 않는다: '집'·house 는 숨을 곳(물속 동굴)이다."""
    spec = mock(rules, prompt, language=lang)
    assert templates_of(spec) == ["cave"]
    assert not any("house" in n.lower() or "집" in n for n in spec.notes_ko)


def test_mock_house_shaped_tunnel_in_aquarium(rules):
    spec = mock(rules, "집 모양 터널")
    assert templates_of(spec) == ["tunnel"] and spec.items[0].params.shape == "house"
    spec = mock(rules, "a house-shaped tunnel", language="en")
    assert templates_of(spec) == ["tunnel"] and spec.items[0].params.shape == "house"
    spec = mock(rules, "S자 터널이랑 동굴")
    assert templates_of(spec) == ["tunnel", "cave"] and spec.items[0].params.path == "s_curve"


@pytest.mark.parametrize("prompt", ["줄무늬 동굴", "\"네온\" 이라고 새긴 동굴", "a cave with stripes"])
def test_mock_never_puts_decor_on_aquarium_items(rules, prompt):
    spec = mock(rules, prompt, language="en" if prompt.isascii() else "ko")
    assert templates_of(spec) == ["cave"]
    assert all(getattr(it, "decor", None) is None for it in spec.items)
    assert "decor" not in json.loads(spec.model_dump_json())["items"][0]


def test_mock_aquarium_revision_from_stored_version(rules):
    """저장된 버전은 모든 템플릿 계약(decor·attach_to: null 포함)으로 읽는다: 어항 수정 요청도 그 직전 설계로 된다."""
    v1 = mock(rules, "동굴이랑 터널")
    stored = parse_spec(v1.model_dump_json())  # DesignService._previous_spec 과 같은 읽기
    assert stored.items[0].decor is None and stored.items[0].placement.attach_to is None
    v2 = mock(rules, "터널을 더 크게", previous=stored)
    assert templates_of(v2) == ["cave", "tunnel"]
    assert v2.items[1].params.length_mm > v1.items[1].params.length_mm


def test_mock_hamster_house_and_decor_unchanged(rules):
    """케이지(햄스터)는 main 그대로: 2층 집 + 바깥 램프(attach_to), 은신처 장식."""
    spec = mock(rules, "2층 집에 바깥 램프", species="hamster", size="syrian", count=1)
    assert templates_of(spec) == ["house", "ramp"]
    assert spec.items[1].placement.attach_to.item_index == 0
    spec = mock(rules, "줄무늬 은신처", species="hamster", size="syrian", count=1)
    assert spec.items[0].decor is not None and spec.items[0].decor.pattern == "stripes"
