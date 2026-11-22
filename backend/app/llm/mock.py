"""개발·테스트용 모의 해석기 (키워드 기반).

ANTHROPIC_API_KEY 없이 전체 흐름을 개발·테스트하기 위한 것이다. 실제 서비스용이 아니다.
출력은 실제 LLM 과 같은 DesignSpec 계약을 따르고, 같은 검증(parse_spec)을 거친다.
붙이기·달기·잇기 요청은 표로 정한 조립 문법(_Composer)이 조립 항목(부품 + 연결)으로 읽고, 나머지 글은 예전처럼
키워드로 따로 놓는 구조물을 찾는다.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.i18n import catalog
from app.llm.base import InterpretRequest, InterpretResult
from app.llm.prompts import is_aquarium, pet_name_en
from app.llm.spec import (
    ASSEMBLY_KEY,
    ATTACH_TEMPLATES,
    HOST_ROLES,
    MAX_ITEMS,
    Connection,
    assembly_enabled,
    connection_problems,
    parse_spec,
)
from app.modules.structure import MAX_PARTS
from app.templates.base import RuleContext
from app.templates.registry import all_templates, primitives
from app.validation.autofix import clip_to_field_bounds

# 템플릿 키 → 한국어 키워드 (모의 해석 전용)
TEMPLATE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hideout": ("은신처", "숨숨집", "하우스", "집"),
    "tunnel": ("터널", "굴", "통로"),
    "ramp": ("계단", "램프", "경사로", "오르막"),
    "sand_bath": ("모래목욕", "모래 목욕", "모래통", "목욕통", "모래"),
    # 조립형 집: 2층·지붕 모양·창·터널 연결 요청. "집" 만 말하면 은신처다
    "house": ("2층", "이층", "복층", "경사 지붕", "뾰족 지붕", "둥근 지붕", "아치 지붕", "지붕 집", "창문", "터널 연결",
              "터널이 붙는", "터널을 붙"),
    # 시판 그릇·물병을 붙잡아 두는 받침 (그릇·물병 자체는 출력하지 않는다)
    "bowl_holder": ("그릇 받침", "밥그릇", "먹이 그릇", "먹이그릇", "밥통", "그릇"),
    "bottle_stand": ("물병 거치대", "물병", "급수기", "물통"),
}
TEMPLATE_NAMES_KO = {"hideout": "은신처", "tunnel": "터널", "ramp": "램프/계단", "sand_bath": "모래목욕통", "house": "집",
                     "cave": "물속 동굴", "bowl_holder": "그릇 받침", "bottle_stand": "물병 거치대"}
# 집 부품 키워드
HOUSE_TWO_FLOORS = ("2층", "이층", "복층")
HOUSE_EXTERNAL = ("바깥 램프", "외부 램프", "바깥 경사로", "외부 경사로", "밖에 램프", "밖에 경사로")
HOUSE_PITCHED = ("경사 지붕", "뾰족 지붕", "박공")
HOUSE_ROUNDED = ("둥근 지붕", "아치 지붕")
HOUSE_PORT = ("터널 연결", "터널이 붙는", "터널을 붙")
HOUSE_FLOOR = ("바닥판",)
# 장식: 무늬 종류 키워드와 각인 요청
PATTERN_WORDS_KO = (("stripes", ("줄무늬", "줄 무늬", "스트라이프")), ("dots", ("점무늬", "물방울", "도트")),
                    ("scales", ("비늘",)), ("brick", ("벽돌",)), ("wave", ("물결",)), ("honeycomb", ("벌집",)))
PATTERN_WORDS_EN = (("stripes", re.compile(r"\bstripe[sd]?\b")), ("dots", re.compile(r"\b(?:dots?|polka)\b")),
                    ("scales", re.compile(r"\bscales?\b")), ("brick", re.compile(r"\bbricks?\b")),
                    ("wave", re.compile(r"\bwav(?:e|es|y)\b")), ("honeycomb", re.compile(r"\bhoneycomb\b")))
ENGRAVE_KO = re.compile(r"[\"'“‘]([가-힣A-Za-z0-9 \-]{1,12})[\"'”’]\s*(?:라고|이라고|을|를|라는|이라는)?\s*(?:새겨|각인|적어|써)")
ENGRAVE_KO2 = re.compile(r"([가-힣A-Za-z0-9\-]{1,12})\s*(?:라고|이라고)\s*(?:새겨|각인|적어|써)")
ENGRAVE_EN = re.compile(r"(?:engrave|carve|write|inscribe)\s+[\"'“‘]([가-힣A-Za-z0-9 \-]{1,12})[\"'”’]")
# 장식 영역이 있는 템플릿 (Template.decor_zones 를 덮어쓴 것). 어항 템플릿(물속 동굴·터널)에는 장식을 넣지 않는다
DECOR_TEMPLATES = ("hideout", "house")

ZONE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("front_left", ("왼쪽 앞", "앞쪽 왼", "좌측 앞")),
    ("front_right", ("오른쪽 앞", "앞쪽 오른", "우측 앞")),
    ("back_left", ("왼쪽 뒤", "뒤쪽 왼", "왼쪽 구석")),
    ("back_right", ("오른쪽 뒤", "뒤쪽 오른", "오른쪽 구석")),
    ("left", ("왼쪽", "좌측")),
    ("right", ("오른쪽", "우측")),
    ("center", ("가운데", "중앙")),
    ("front", ("앞쪽", "앞에")),
    ("back", ("뒤쪽", "안쪽", "뒤에")),
    ("back_left", ("구석",)),  # 방향 없는 '구석'은 마지막에 확인
]
GROUP_WORDS = ("몰아", "모아", "붙여", "한쪽", "한 쪽", "한곳", "한 곳", "나란히")
BIGGER = ("크게", "넓게", "넉넉", "큰")
SMALLER = ("작게", "아담", "좁게", "작은")
REMOVE = ("빼", "삭제", "없애", "제거")
ADD = ("추가", "더 넣", "하나 더")

# 영어 요청용 키워드 (소문자로 바꾼 글에 단어 경계로 찾는다). 한국어 키워드와 함께 확인한다
TEMPLATE_KEYWORDS_EN: dict[str, re.Pattern[str]] = {
    "hideout": re.compile(r"\b(?:hide ?outs?|hides?|hidey(?: ?holes?)?|hiding (?:places?|spots?)|houses?|shelters?|huts?"
                          r"|nests?|dens?|igloos?)\b"),
    "tunnel": re.compile(r"\b(?:tunnels?|tubes?|burrows?|passages?)\b"),
    "ramp": re.compile(r"\b(?:ramps?|stairs?|stair ?cases?|steps?|slopes?|ladders?)\b"),
    "sand_bath": re.compile(r"\b(?:sand ?baths?|sand ?box(?:es)?|dust ?baths?|bath ?tubs?|baths?|sand)\b"),
    "house": re.compile(r"\b(?:two[ -]?stor(?:y|ey|ies)|2[ -]?stor(?:y|ey)|second floor|upper floor|lofts?|"
                        r"pitched roofs?|gabled? roofs?|peaked roofs?|rounded roofs?|arched roofs?|windows?|"
                        r"tunnel (?:port|connection|connector))\b"),
    "bowl_holder": re.compile(r"\b(?:bowl ?holders?|food ?bowls?|bowls?|food ?dish(?:es)?|feeders?)\b"),
    "bottle_stand": re.compile(r"\b(?:(?:water ?)?bottle ?(?:stands?|holders?)|water ?bottles?|bottles?|drinkers?)\b"),
}
TEMPLATE_NAMES_EN = {"hideout": "Hideout", "tunnel": "Tunnel", "ramp": "Ramp/stairs", "sand_bath": "Sand bath",
                     "house": "House", "cave": "Underwater cave", "bowl_holder": "Bowl holder",
                     "bottle_stand": "Water bottle stand"}


HOUSE_TWO_FLOORS_EN = re.compile(r"\b(?:two[ -]?stor(?:y|ey|ies)|2[ -]?stor(?:y|ey)|second floor|upper floor|lofts?)\b")
HOUSE_EXTERNAL_EN = re.compile(r"\b(?:outside|external|outer|exterior) (?:ramp|stairs?|slope)\b")
HOUSE_PITCHED_EN = re.compile(r"\b(?:pitched|gabled?|peaked) roofs?\b")
HOUSE_ROUNDED_EN = re.compile(r"\b(?:rounded|arched|round) roofs?\b")
HOUSE_PORT_EN = re.compile(r"\btunnel (?:port|connection|connector)\b")
HOUSE_FLOOR_EN = re.compile(r"\bfloor plate\b")

# 어항(habitat="aquarium") 요청용 키워드. 은신처·집처럼 숨을 곳을 뜻하는 말은 물속 동굴로 읽는다.
# 조립형 집(house) 키워드(2층·지붕·창문 …)는 넣지 않는다: 어항에 집은 없고, '2층 집'의 '집'도 숨을 곳(물속 동굴)으로 읽는다.
# 순서대로 찾고 찾은 말은 지운다: '동굴'을 먼저 지워 터널 키워드 '굴'이 다시 잡지 않게 한다.
# 어항의 '모래'는 바닥재라 모래목욕통으로 읽지 않는다 (모래목욕을 콕 집어 말했을 때만 만들 수 없다고 알린다)
AQUARIUM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cave": ("동굴", "은신처", "숨숨집", "숨을 곳", "숨는 곳", "하우스", "집"),
    "tunnel": ("터널", "통로", "파이프", "튜브", "굴"),
    "ramp": TEMPLATE_KEYWORDS["ramp"],
    "sand_bath": ("모래목욕", "모래 목욕", "목욕통"),
}
# 한 글자 '관'(파이프)은 따로 낱말일 때만 터널로 읽는다: 관상어·관찰·수족관·관리처럼 다른 낱말 속의 '관'은 뺀다.
# 뒤에 조사(을·이·과·이랑 …)가 붙는 것은 받는다
AQUARIUM_KEYWORDS_RX: dict[str, re.Pattern[str]] = {
    "tunnel": re.compile(r"(?<![가-힣])관(?:을|를|이|가|은|는|도|과|와|에|의|만|으로|로|이랑|랑|하고|처럼)?(?![가-힣])"),
}
AQUARIUM_KEYWORDS_EN: dict[str, re.Pattern[str]] = {
    "cave": re.compile(r"\b(?:caves?|caverns?|grott(?:o|os|oes)|hide ?outs?|hides?|hidey(?: ?holes?)?"
                       r"|hiding (?:places?|spots?)|shelters?|houses?|huts?|dens?|retreats?)\b"),
    # swim-through 는 이름씨(물고기가 지나가는 관)만 터널로 읽는다: 'a cave fish can swim through'의 동사는 빼고
    #   여러 개를 뜻하는 'swim throughs' 는 받는다
    "tunnel": re.compile(r"\b(?:tunnels?|tubes?|tubing|pipes?|passages?|burrows?|swim-?throughs?|swim throughs)\b"),
    "ramp": TEMPLATE_KEYWORDS_EN["ramp"],
    "sand_bath": re.compile(r"\b(?:sand ?baths?|dust ?baths?)\b"),
}
assert list(AQUARIUM_KEYWORDS) == list(AQUARIUM_KEYWORDS_EN)
assert set(AQUARIUM_KEYWORDS_RX) <= set(AQUARIUM_KEYWORDS)
# 물속 동굴 출입구 개수: 앞뒤로 뚫린(관통형) 2개 / 앞만 뚫린 1개
CAVE_THROUGH = ("앞뒤", "관통", "양쪽")
CAVE_ONE_DOOR = ("출입구 하나", "출입구가 하나", "입구 하나", "입구가 하나", "앞만 뚫린")
CAVE_DOOR_COUNT = re.compile(r"(?:출입구|입구)[^\d]{0,6}?(\d+)\s*개")

# ZONE_KEYWORDS 와 같은 순서 (구체적인 모서리 → 한쪽 → 방향 없는 구석)
ZONE_KEYWORDS_EN: list[tuple[str, re.Pattern[str]]] = [(_zone, re.compile(_rx)) for _zone, _rx in [
    ("front_left", r"\b(?:front[ -]left|left[ -]front|bottom[ -]left)\b"),
    ("front_right", r"\b(?:front[ -]right|right[ -]front|bottom[ -]right)\b"),
    ("back_left", r"\b(?:back[ -]left|left[ -]back|rear[ -]left|left[ -]rear|top[ -]left|left corner)\b"),
    ("back_right", r"\b(?:back[ -]right|right[ -]back|rear[ -]right|right[ -]rear|top[ -]right|right corner)\b"),
    ("left", r"\bleft\b"),
    ("right", r"\bright\b"),
    ("center", r"\b(?:cent(?:er|re)|middle)\b"),
    ("front", r"\bfront\b"),
    ("back", r"\b(?:back|rear|behind)\b"),
    ("back_left", r"\bcorner\b"),  # 방향 없는 corner 는 마지막에 확인 (한국어 '구석'과 같다)
]]
assert [z for z, _ in ZONE_KEYWORDS_EN] == [z for z, _ in ZONE_KEYWORDS]
GROUP_EN = re.compile(r"\b(?:together|side by side|next to each other|grouped|clustered|bunched"
                      r"|(?:in|on|to) one (?:place|spot|side|corner|area))\b")
BIGGER_EN = re.compile(r"\b(?:bigger|larger|large|big|roomier|roomy|spacious|wider|wide)\b")
SMALLER_EN = re.compile(r"\b(?:smaller|small|compact|tiny|little|narrower|narrow)\b")
REMOVE_EN = re.compile(r"\b(?:remove|delete|take (?:out|away)|get rid of|drop|without)\b")
ADD_EN = re.compile(r"\b(?:add|another|one more|an extra|extra)\b")

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                 "ten": 10, "eleven": 11, "twelve": 12}
_NUM_EN = r"(\d+|" + "|".join(_NUMBER_WORDS) + r")"
WINDOWS_EN = re.compile(_NUM_EN + r"\s*windows?\b")
STEPS_EN = re.compile(r"\b(?:stairs?|stair ?cases?|steps?)\b")
STEP_COUNT_EN = re.compile(_NUM_EN + r"[\s-]*(?:steps?|stairs?)\b")
RAMP_EN = re.compile(r"\b(?:ramps?|slopes?|sloped|inclines?)\b")
U_BEND_EN = re.compile(r"\b(?:u[ -]?(?:shaped?|turns?|bend)|uturns?)\b")
CURVE_EN = re.compile(r"\b(?:curved?|curving|curvy|bent|bends?|bendy|l[ -]?shaped?|elbow|angled)\b")
STRAIGHT_EN = re.compile(r"\bstraight\b")
# "tunnel's bend" 처럼 소유격 's 뒤의 단어는 S자가 아니다
# "house-shaped tunnel" 의 house 는 은신처가 아니라 터널 단면 모양
HOUSE_SHAPE_EN = re.compile(r"\bhouse[ -]?shaped?\b")
S_CURVE_EN = re.compile(r"(?<!['’])\b(?:s[ -]?(?:shaped?|curves?|bends?)|zig-?zag|wavy|snaking)\b")
# 터널 단면 모양 (먼저 맞는 것)
TUNNEL_SHAPES_KO = (
    ("tube", ("원통", "튜브", "파이프", "둥근 관", "원형")),
    ("box", ("네모", "사각", "직사각")),
    ("house", ("집 모양", "집모양", "삼각", "오각", "지붕 모양")),
    ("pointed_arch", ("뾰족",)),
    ("round_arch", ("둥근", "둥글게", "반원")),
)
TUNNEL_SHAPES_EN = (
    ("tube", re.compile(r"\b(?:tubes?|pipes?|cylindrical|circular)\b")),
    ("box", re.compile(r"\b(?:square|boxy|box-shaped|rectangular)\b")),
    ("house", re.compile(r"\b(?:house[ -]?shaped?|peaked|a-frame|triangular|gabled?)\b")),
    ("pointed_arch", re.compile(r"\bpointed\b")),
    ("round_arch", re.compile(r"\b(?:round(?:ed)?|semi-?circular|arched)\b")),
)
# 어항에서 파이프·튜브(pipe·tube)는 터널을 부르는 흔한 말이라(AQUARIUM_KEYWORDS) 단면 모양 요청으로 읽지 않는다.
# 둥근 관(tube) 단면은 천장 꼭대기가 둥글어 공기가 남기 쉬우니(tunnel_flat_ceiling 경고), 원통·원형처럼 모양을
# 콕 집어 말했을 때만 고른다 (어항 프롬프트의 단면 규칙과 같다). 나머지 단면 낱말은 케이지와 같다
AQUARIUM_TUNNEL_SHAPES_KO = (
    ("tube", ("원통", "둥근 관", "원형", "둥근 파이프", "둥근 튜브")),
    *TUNNEL_SHAPES_KO[1:],
)
AQUARIUM_TUNNEL_SHAPES_EN = (
    ("tube", re.compile(r"\b(?:cylindrical|(?<!semi-)circular|round (?:tubes?|tubing|pipes?))\b")),
    *TUNNEL_SHAPES_EN[1:],
)
assert [s for s, _ in AQUARIUM_TUNNEL_SHAPES_KO] == [s for s, _ in TUNNEL_SHAPES_KO]
assert [s for s, _ in AQUARIUM_TUNNEL_SHAPES_EN] == [s for s, _ in TUNNEL_SHAPES_EN]
VENTS_EN = (re.compile(_NUM_EN + r"\s*(?:air[ -]?|ventilation |vent )?(?:vents?|holes?)\b"),
            re.compile(r"\b(?:vents?|ventilation holes?|air ?holes?)\b[^\d]{0,8}?(\d+)\b(?!\s*(?:mm|cm|\.\d))"))
_DOOR_EN = r"(?:entrances?|entry|entries|doors?|doorways?|openings?)"
ENTRANCE_EN = (re.compile(r"\b" + _DOOR_EN + r"\b[^\d]{0,10}(\d+(?:\.\d+)?)\s*(mm|cm)\b"),
               re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm)\b[a-z\s-]{0,12}?\b" + _DOOR_EN + r"\b"))
CAVE_THROUGH_EN = re.compile(r"\b(?:through|front and back|both (?:ends|sides)|two[ -]way|open (?:at )?both)\b")
CAVE_DOOR_COUNT_EN = re.compile(r"\b" + _NUM_EN + r"[\s-]*" + _DOOR_EN + r"\b")


def _num(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBER_WORDS[word]


def _find_decor(text: str) -> dict | None:
    """장식 명세: 따옴표 글귀 각인, 또는 무늬 키워드. 없으면 None."""
    low = _en(text)
    m = ENGRAVE_KO.search(text) or ENGRAVE_KO2.search(text) or ENGRAVE_EN.search(text)
    if m:
        return {"kind": "text", "text": m.group(1).strip(), "face": "left", "height_mm": 15, "depth_mm": 0.6}
    for key, words in PATTERN_WORDS_KO:
        if any(w in text for w in words):
            return {"kind": "pattern", "pattern": key, "density": 2, "direction": 0, "depth_mm": 0.6,
                    "face": "walls", "mode": "engrave"}
    for key, rx in PATTERN_WORDS_EN:
        if rx.search(low):
            return {"kind": "pattern", "pattern": key, "density": 2, "direction": 0, "depth_mm": 0.6,
                    "face": "walls", "mode": "engrave"}
    return None


def _apply_house(text: str, low: str, out: dict) -> dict:
    """집 부품: 층·오르는 수단·지붕·창·연결부·바닥판 (중첩 파라미터는 사본을 고친다)."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in out.items()}
    if any(w in text for w in HOUSE_TWO_FLOORS) or HOUSE_TWO_FLOORS_EN.search(low):
        out["floors"]["count"] = 2
        if any(w in text for w in HOUSE_EXTERNAL) or HOUSE_EXTERNAL_EN.search(low):
            out["floors"]["climb"] = "external_ramp"
            out["floors"]["exit_side"] = "back"
            out["doors"]["sides"] = ["front"]
    if any(w in text for w in HOUSE_PITCHED) or HOUSE_PITCHED_EN.search(low):
        out["roof"]["kind"] = "pitched"
    elif any(w in text for w in HOUSE_ROUNDED) or HOUSE_ROUNDED_EN.search(low):
        out["roof"]["kind"] = "rounded"
    if any(w in text for w in HOUSE_PORT) or HOUSE_PORT_EN.search(low):
        out["ports"]["sides"] = ["left"]
    if any(w in text for w in HOUSE_FLOOR) or HOUSE_FLOOR_EN.search(low):
        out["floor"]["enabled"] = True
    m = re.search(r"창(?:문)?[^\d]{0,8}?(\d+)\s*개", text) or WINDOWS_EN.search(low)
    if m:
        out["windows"]["count"] = min(4, _num(m.group(1)))
    elif "창문" in text or re.search(r"\bwindows?\b", low):
        out["windows"]["count"] = max(out["windows"].get("count", 0), 2)
    return out


def _en(text: str) -> str:
    return text.lower()


def _blank(m: re.Match[str]) -> str:
    return " " * len(m.group(0))


def _find_templates(text: str, aquarium: bool = False) -> list[str]:
    words_of, rx_of = (AQUARIUM_KEYWORDS, AQUARIUM_KEYWORDS_EN) if aquarium else (TEMPLATE_KEYWORDS, TEMPLATE_KEYWORDS_EN)
    found = []
    # "집 모양 터널" 의 "집" 은 은신처가 아니라 터널 단면 모양이다 (같은 길이로 바꿔 위치는 그대로)
    if "터널" in text:
        text = text.replace("집 모양", "＿ 모양").replace("집모양", "＿모양")
    low = _en(text)
    if rx_of["tunnel"].search(low):
        # "house-shaped tunnel" 의 house 는 은신처(어항은 물속 동굴)가 아니라 터널 단면 모양이다
        low = HOUSE_SHAPE_EN.sub(lambda mm: "_" * len(mm.group(0)), low)
    for key, words in words_of.items():
        positions = [text.find(w) for w in words if w in text]
        m = rx_of[key].search(low)
        if m:
            positions.append(m.start())
        ko_rx = AQUARIUM_KEYWORDS_RX.get(key) if aquarium else None
        if ko_rx is not None and (m := ko_rx.search(text)):
            positions.append(m.start())
        if positions:
            found.append((min(positions), key))
        if aquarium:  # 찾은 말을 같은 길이의 빈칸으로 지운다 (위치는 그대로)
            for w in words:
                text = text.replace(w, " " * len(w))
            if ko_rx is not None:
                text = ko_rx.sub(_blank, text)
            low = rx_of[key].sub(_blank, low)
    keys = [k for _, k in sorted(found)]
    if "house" in keys:
        # "2층 집" 의 "집"·"house with windows" 의 "house" 는 은신처가 아니라 조립형 집이다
        keys = [k for k in keys if k != "hideout"]
    return keys


def _without_door_phrases(text: str) -> str:
    """물속 동굴 출입구 개수를 말하는 말(앞뒤·양쪽·front and back …)을 같은 길이의 빈칸으로 지운 소문자 글.
    '출입구가 앞뒤에 있는 동굴'의 '뒤에', 'open front and back'의 front 를 배치 위치로 읽지 않게 한다."""
    low = _en(text)
    for w in CAVE_THROUGH + CAVE_ONE_DOOR:
        low = low.replace(w, " " * len(w))
    return CAVE_THROUGH_EN.sub(_blank, low)


def _find_zone(text: str) -> str | None:
    low = _en(text)
    for (zone, words), (_, rx) in zip(ZONE_KEYWORDS, ZONE_KEYWORDS_EN):
        if any(w in text for w in words) or rx.search(low):
            return zone
    return None


def _grouped(text: str) -> bool:
    return any(w in text for w in GROUP_WORDS) or bool(GROUP_EN.search(_en(text)))


def _scale_factor(text: str) -> float:
    low = _en(text)
    if any(w in text for w in BIGGER) or BIGGER_EN.search(low):
        return 1.2
    if any(w in text for w in SMALLER) or SMALLER_EN.search(low):
        return 0.85
    return 1.0


def _scaled(template, params: dict, factor: float) -> dict:
    out = dict(params)
    for f in template.size_fields:
        out[f] = round(clip_to_field_bounds(template.Params, f, out[f] * factor), 1)
    return out


def _apply_numbers(key: str, text: str, params: dict, aquarium: bool = False) -> dict:
    out = dict(params)
    low = _en(text)
    if key == "tunnel":
        shapes_ko, shapes_en = ((AQUARIUM_TUNNEL_SHAPES_KO, AQUARIUM_TUNNEL_SHAPES_EN) if aquarium
                                else (TUNNEL_SHAPES_KO, TUNNEL_SHAPES_EN))
        for shape, words in shapes_ko:
            if any(w in text for w in words):
                out["shape"] = shape
                break
        else:
            for shape, rx in shapes_en:
                if rx.search(low):
                    out["shape"] = shape
                    break
    if key == "tunnel" and (any(w in text for w in ("S자", "s자", "에스자", "지그재그")) or S_CURVE_EN.search(low)):
        out["path"] = "s_curve"
        out["bend_angle_deg"] = 60
    elif key == "tunnel":
        if any(w in text for w in ("U자", "유턴")) or U_BEND_EN.search(low):
            out["bend_angle_deg"] = 180
            out["path"] = "arc"
        elif any(w in text for w in ("곡선", "구부러", "휘어", "ㄱ자", "꺾")) or CURVE_EN.search(low):
            out["bend_angle_deg"] = 90
            out["path"] = "arc"
        elif "직선" in text or STRAIGHT_EN.search(low):
            out["bend_angle_deg"] = 0
            out["path"] = "arc"
    # 램프와 계단 단 수 파라미터가 있는 조립 모듈(경사로 달린 은신처·모래목욕통)은 같은 규칙으로 계단·경사로를 고른다
    if key == "ramp" or "steps" in out:
        if "계단" in text:
            m = re.search(r"(\d+)\s*단", text)
            out["steps"] = int(m.group(1)) if m else max(out.get("steps", 0), 3)
        elif STEPS_EN.search(low):
            m = STEP_COUNT_EN.search(low)
            out["steps"] = _num(m.group(1)) if m else max(out.get("steps", 0), 3)
        elif any(w in text for w in ("경사로", "램프", "슬로프")) or RAMP_EN.search(low):
            out["steps"] = 0
    if key == "house":
        out = _apply_house(text, low, out)
    if key == "hideout":
        m = re.search(r"환기구[^\d]{0,8}?(\d+)\s*개", text)
        if m:
            out["vent_count"] = int(m.group(1))
        else:
            m = VENTS_EN[0].search(low) or VENTS_EN[1].search(low)
            if m:
                out["vent_count"] = _num(m.group(1))
    if key == "cave":
        m = CAVE_DOOR_COUNT.search(text) or CAVE_DOOR_COUNT_EN.search(low)
        if m:
            out["entrance_count"] = min(2, max(1, _num(m.group(1))))
        elif any(w in text for w in CAVE_ONE_DOOR):
            out["entrance_count"] = 1
        elif any(w in text for w in CAVE_THROUGH) or CAVE_THROUGH_EN.search(low):
            out["entrance_count"] = 2
    if key in ("hideout", "cave"):
        m = (re.search(r"출입구[^\d]{0,10}(\d+(?:\.\d+)?)\s*(mm|cm)", text)
             or ENTRANCE_EN[0].search(low) or ENTRANCE_EN[1].search(low))
        if m:
            v = float(m.group(1)) * (10 if m.group(2) == "cm" else 1)
            out["entrance_diameter_mm"] = v
    return out


# ── 조립 문법 (붙이기·달기·잇기 → 조립 항목) ──────────────────────
# 요청을 절로 나누고, 절마다 부품 낱말·면 낱말·연결 말을 표(_PATTERNS)의 틀에 맞춰 "어느 부품을 어느 부품의 어느 면에"를
# 찾는다. 이어진 부품은 조립 항목 하나(뿌리 = 먼저 말한 기준 구조물)가 되고, 찾아 쓴 글 조각은 같은 길이의 빈칸으로 지워
# 남은 글을 예전 키워드 해석(_find_templates·_find_zone)에 넘긴다. 이어지지 않은 부품은 예전처럼 따로 놓는 항목이다.
# 결합 방식·연결 지점·맞물리는 치수는 조립 해석기(app/modules/compose)가 정하므로 여기서는 면(at)까지만 적는다.

PART_IDS = {"hideout": "hide", "tunnel": "tube", "ramp": "ramp", "sand_bath": "bath", "house": "house",
            "bowl_holder": "bowl", "bottle_stand": "bottle"}
SIDE_NAMES_KO = {"right": "오른쪽", "left": "왼쪽", "front": "앞", "back": "뒤", "free_end": "끝", "auto": "빈 면"}
SIDE_NAMES_EN = {"right": "right side", "left": "left side", "front": "front", "back": "back", "free_end": "free end",
                 "auto": "a free side"}
# 면 낱말 (한국어·영어). both = 양옆(오른쪽·왼쪽), top = 위에 얹기 (아직 지원하지 않아 안내만 한다)
SIDE_WORDS_KO: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("both", ("양옆", "양 옆", "양쪽", "양편", "좌우")),
    ("right", ("오른쪽", "오른편", "우측")),
    ("left", ("왼쪽", "왼편", "좌측")),
    ("front", ("앞쪽", "앞면", "앞편", "정면", "앞")),
    ("back", ("뒤쪽", "뒷쪽", "뒷면", "뒤편", "후면", "뒤")),
    ("auto", ("옆쪽", "옆면", "옆")),
    ("top", ("위쪽", "윗면", "꼭대기", "지붕 위", "위")),
    ("free_end", ("반대쪽 끝", "다른 끝", "끝")),
)
SIDE_WORDS_EN: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("both", ("both sides", "either side", "each side")),
    ("right", ("right",)), ("left", ("left",)), ("front", ("front",)), ("back", ("back", "rear")),
    ("top", ("top",)), ("free_end", ("other end", "far end", "end")),
)
_SIDE_OF = {w: side for side, words in SIDE_WORDS_KO + SIDE_WORDS_EN for w in words}
# 면 낱말 뒤에 이 말이 오거나 앞에 케이지가 오면 부품의 면이 아니라 케이지 안 위치다 (기존 _find_zone 이 읽는다)
_ZONE_AFTER = re.compile(r"^\s*(?:(?:hand\s+)?side\s+)?(?:구석|모서리|벽|코너|끝|공간|자리|corner|wall"
                         r"|of\s+(?:the\s+|my\s+)?(?:cage|tank|enclosure|habitat|aquarium))")
_ZONE_BEFORE = re.compile(r"(?:케이지|어항|수조|우리|cage|tank|enclosure)\s*(?:의|'s)?\s*(?:in\s+the\s+)?$")
# 부품 낱말 앞뒤의 '하나 더'·'another' (같은 템플릿 부품을 하나 더 만든다)
_MORE_AFTER = re.compile(r"^\s*(?:을|를|이|가|도|은|는)?\s*(?:하나|한\s*개|한\s*채|1\s*개)\s*더|^\s*(?:도\s*)?또\s*하나")
_MORE_BEFORE = re.compile(r"(?:또\s*(?:하나의\s*)?|다른\s*|새\s*|새로운\s*|하나\s*더\s*|\b(?:another|one\s+more|a\s+second|"
                          r"a\s+2nd|an\s+extra|a\s+new|second)\s+)$")
# 조립 문법에서는 '터널 연결'·'터널을 붙' 같은 말을 집(터널 연결부가 있는 집)으로 읽지 않는다: 터널 + 연결 말이다
_HOUSE_PORT_WORDS = set(HOUSE_PORT)
# 절 나누기: 문장 부호, 그리고·then, 동사 뒤 ' and ', 붙이고·달고·이어주고·놓고 … 뒤
_CLAUSE_CUT = re.compile(
    r"[,，;!?\n]+|(?<!\d)\.(?!\d)|\s*그리고\s*|\s*그\s*다음에?\s*|\s+and\s+then\s+|\s+then\s+|\s+plus\s+"
    r"|\s*,?\s+and\s+(?=(?:also\s+)?(?:connect|attach|put|add|place|make|give|join|link|mount|include|have|with|on|at"
    r"|in|to|use|please|let)\b)"
    r"|(?P<verb>(?:붙이|붙여주|달|달아주|이어주|이어|놓|놓아주|연결하|연결해주|넣|넣어주|두|둬주|만들|만들어주|해주)고)\s+")
# 순수 나열 절 (부품 낱말과 조사·관사·접속 말뿐): 이웃 절에 붙여 나열로 읽는다 ("밥그릇, 물병 달린 은신처")
_PURE_LEFTOVER = re.compile(r"^(?:[\s,，.;!?]|와|과|이랑|랑|하고|및|그리고|을|를|이|가|은|는|도|또|\b(?:a|an|the|some|and|also"
                            r"|too|plus|two|one)\b)*$")
_TOKEN = re.compile(r"⟦([HTX])(\d+)⟧")
_ATTACH_WORDS = re.compile(r"붙여|붙이|달아|연결|이어|끼워|\battach(?:ed)?\b|\bconnect(?:ed)?\b|\bjoin(?:ed)?\b")

_K_SIDE = "|".join(sorted((re.escape(w) for w, _ in _SIDE_OF.items() if re.match(r"[가-힣]", w)), key=len,
                          reverse=True))
_E_SIDE = "|".join(sorted((re.escape(w) for w, _ in _SIDE_OF.items() if not re.match(r"[가-힣]", w)), key=len,
                          reverse=True))
_FRAG = {
    "A": r"⟦[HT](?P<a>\d+)⟧",
    "AH": r"⟦H(?P<a>\d+)⟧",
    "B": r"⟦[HTX](?P<b>\d+)⟧",
    "BH": r"⟦H(?P<b>\d+)⟧",
    "R": r"⟦H(?P<r>\d+)⟧",
    "T": r"⟦T(?P<t>\d+)⟧",
    # 나열: 와·과·쉼표·and 로 잇거나, 띄어 쓰기만 한 받침·터널 ('그릇 물병 달린 은신처')
    "BL": r"(?P<bl>⟦[HTX]\d+⟧(?:(?:\s*(?:,|，|와|과|이랑|랑|하고|및|그리고|&|\+)\s*|\s*,?\s*\b(?:and|plus)\s+)"
          r"(?:(?:a|an|the|some|another)\s+)?(?:[^\s⟦⟧,，]{1,12}\s+)?⟦[HTX]\d+⟧|\s+⟦[TX]\d+⟧)*)",
    "SIDE": rf"(?:(?<![가-힣])|(?<=의))(?P<side>{_K_SIDE})(?:\s*(?:쪽|편|면))?"
            r"(?=\s|$|[⟦,，]|에|엔|으로|로|의|은|는|도|까지)",
    "SPART": r"\s*(?:에다가|에다|에는|에도|에선|에|엔|으로는|으로|로|은|는|까지)?",
    "ESIDE": rf"(?:on|at|to|onto|against|along)\s+(?:the\s+|its\s+|their\s+)?(?P<side>{_E_SIDE})"
             r"(?:(?:\s+hand)?\s+sides?)?",
    "ART": r"(?:(?:a|an|the|some|my|its|another|one\s+more|a\s+second|an\s+extra)\s+)?(?:[a-z][\w-]*\s+){0,2}?",
    "ATTV": r"(?:붙여|붙이|붙인|붙|달아|달고|달기|달린|달려|달|연결|이어|잇|끼워|끼우|장착|\battach|\bconnect|\bjoin"
            r"|\blink|\bmount|\bclip)",
    "LINKV": r"(?:이어|이은|이을|잇|연결|붙여|달아)",
    "LINKP": r"(?:이은|이어진|이어지는|연결된|연결한|연결되는|잇는|이어\s*놓은|이어준)",
    "PART": r"(?:달려\s*있는|붙어\s*있는|달린|붙은|붙인|딸린|있는|연결된|연결되는|이어진|이어지는|장착된|갖춘|곁들인)",
    "CNT": r"(?:\s*(?P<cnt>두|둘|2)\s*(?:개|채)?)",
    "ECNT": r"(?P<cnt>two|2|twin|a\s+pair\s+of|pair\s+of)\s+",
}


def _expand(template: str) -> re.Pattern[str]:
    """틀 글의 {A}·{SIDE}… 를 정규식 조각으로 바꾼다. {F}·{FE}(사이에 끼는 말)는 지우지 않을 조각이라 번호 붙은 그룹이다."""
    n = 0

    def sub(m: re.Match[str]) -> str:
        nonlocal n
        name = m.group(1)
        if name in ("F", "FE"):
            n += 1
            return rf"(?P<f{n}>[^⟦⟧,，]{{0,{12 if name == 'F' else 30}}}?)"
        return _FRAG[name]

    return re.compile(re.sub(r"\{([A-Z]+)\}", sub, template))


# (종류, 틀) — 절마다 이 순서로 찾고 먼저 찾은 곳과 겹치는 곳은 건너뛴다. 종류:
#   twin   {R} 두 개를 터널로 이어          → R, 터널, R 사본 (P6)
#   chain  {A}와 {B}를 터널로 이어          → A ← 터널 ← B (P5)
#   tunnel (SIDE에) 터널로 {R} (하나 더) 이어 → 기준·A 의 SIDE ← 새 터널 ← R (P4)
#   side   {A} SIDE에 {B…} / {B}를 {A} SIDE에 / SIDE에 {B} (주어) → B → A.SIDE (P1·P2)
#   head   {B…}(이) 달린 {A}               → B → A.auto (P3; A 는 다른 '달린 A' 와 다른 부품)
#   roof   {A} 지붕으로 올라가는 {램프}      → 램프 → A.auto
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple((kind, _expand(t)) for kind, t in (
    # P6 쌍둥이
    ("twin", r"(?P<twin>쌍둥이\s*)?{R}{CNT}?(?:를|을|가|이|는|은)?{F}{T}(?:으로|로)(?:{F}{LINKV})?"),
    ("twin", r"(?P<cnt>두|2)\s*(?:개의|채의|개|채)?\s*{R}(?:를|을|가|이|는|은)?{F}{T}(?:으로|로)(?:{F}{LINKV})?"),
    ("twin", r"{T}(?:으로|로)\s*{LINKP}{F}(?P<twin>쌍둥이\s*)?{R}{CNT}?"),
    ("twin", r"(?:connect|join|link)\s+{ECNT}{R}\s+(?:together\s+)?(?:with|via|through|by|using)\s+{ART}{T}"),
    ("twin", r"{ECNT}{R}{FE}(?:joined|connected|linked|attached)\s+(?:together\s+)?(?:by|with|via|through|using)\s+{ART}{T}"),
    ("twin", r"{T}\s+(?:connecting|joining|linking)\s+{ECNT}{R}"),
    # P5 사슬
    ("chain", r"{AH}\s*(?:와|과|랑|이랑|하고|및)\s*{BH}(?:을|를|도)?{F}(?:사이를|사이에)?{F}{T}(?:으로|로){F}{LINKV}"),
    ("chain", r"{T}(?:으로|로)\s*{LINKP}\s*{AH}\s*(?:와|과|랑|이랑|하고)\s*{BH}"),
    ("chain", r"(?:connect|join|link)\s+{ART}{AH}\s+(?:and|to|with)\s+{ART}{BH}\s+(?:with|via|through|by|using)\s+{ART}{T}"),
    ("chain", r"{AH}\s+and\s+{ART}{BH}\s+(?:joined|connected|linked)\s+(?:together\s+)?(?:by|with|via|through)\s+{ART}{T}"),
    # P4 터널로 방 잇기
    # (면을 말한 틀을 먼저: 면이 없는 틀이 왼쪽부터 찾으면 면 낱말을 사이 말로 넘긴다)
    ("tunnel", r"(?:{A}(?:의)?\s*)?{SIDE}{SPART}{F}{T}(?:으로|로){F}{R}(?:을|를|도|이|가)?{F}{LINKV}"),
    ("tunnel", r"(?:{A}(?:의)?\s*)?{SIDE}{SPART}{F}{T}(?:으로|로)\s*{LINKP}{F}{R}"),
    ("tunnel", r"{T}(?:으로|로){F}{R}(?:을|를|도|이|가)?{F}{LINKV}"),
    ("tunnel", r"{T}(?:으로|로)\s*{LINKP}{F}{R}"),
    ("tunnel", r"(?:connect|join|link|add|attach)\s+{ART}{R}\s+(?:with|via|through|by|using)\s+{ART}{T}(?:\s+{ESIDE}(?:\s+of\s+{ART}{A})?)?"),
    ("tunnel", r"{R}\s+(?:connected|joined|linked)\s+(?:by|with|via|through)\s+{ART}{T}(?:\s+{ESIDE}(?:\s+of\s+{ART}{A})?)?"),
    # 지붕으로 올라가는 램프 (위에 얹기가 아니라 옆면에 붙여 지붕 높이까지 오른다)
    ("roof", r"{A}(?:의)?\s*(?:지붕|꼭대기|위)(?:으로|로|까지|에)?\s*(?:올라가는|오르는|올라갈|이어지는|닿는){F}{B}"),
    ("roof", r"{B}{FE}(?:up\s+)?to\s+the\s+(?:roof|top)\s+of\s+{ART}{A}"),
    # {a} with {b…} (on the SIDE): 영어 면 틀보다 먼저 ('a hideout with a bowl on the right')
    ("head", r"{A}{FE}\b(?:with|that\s+has|having)\s+{ART}{BL}(?:\s+(?:attached|on\s+it|on\s+the\s+side))?(?:\s+{ESIDE})?"),
    # P1 {A} SIDE에 {B…}
    ("side", r"{A}(?:의)?\s*{SIDE}{SPART}{F}{BL}"),
    # P1b {B…}를 {A} SIDE에
    ("side", r"{BL}(?:을|를|은|는|도|이|가)\s*{A}(?:의)?\s*{SIDE}{SPART}"),
    # {A}에 {B…} (붙여) / {B…}를 {A}에 붙여 (면 없이: 빈 면)
    ("side", r"{A}(?:에다가|에다|에는|에도|에)\s*{F}{BL}"),
    ("side", r"{BL}(?:을|를|은|는|도)\s*{A}(?:에다가|에다|에)\s*{F}{ATTV}"),
    # 영어: {b…} on the SIDE (of the {a}) / in front of / behind / next to / attach {b} to {a}
    ("side", r"{BL}\s+(?:(?:attached|mounted|fixed|placed|clipped|slid|fitted)\s+)?{ESIDE}(?:\s+of\s+{ART}{A})?"),
    ("side", r"{ESIDE}(?:\s+of\s+{ART}{A})?,?\s+(?:(?:put|add|place|attach|mount|there\s+is|have)\s+)?{ART}{BL}"),
    ("side", r"{BL}\s+(?P<side>in\s+front)\s+of\s+{ART}{A}"),
    ("side", r"{BL}\s+(?P<side>behind)\s+{ART}{A}"),
    ("side", r"{BL}\s+(?P<side>next\s+to|beside)\s+{ART}{A}"),
    ("side", r"(?:attach|add|mount|put|connect|fix|clip)\s+{ART}{BL}\s+(?:to|on|onto)\s+{ART}{A}"),
    ("side", r"{BL}\s+(?:attached|connected|mounted|fixed)\s+to\s+{ART}{A}"),
    ("side", r"{BL}\s+(?:(?:leading|going|climbing)\s+)?(?:up\s+)?(?:to|into|onto)\s+{ART}{A}"),
    # P3 {B…}(이) 달린 {A} / {a} with {b…}
    ("head", r"{BL}(?:이|가|을|를|와|과|이랑|랑|하고)?\s*(?:{SIDE}{SPART}\s*)?{PART}\s*{F}{A}"),
    # P2 SIDE에 {B…} (부품 낱말 없이 면만: 지금 말하는 기준 구조물, 끝이면 마지막 터널)
    ("side", r"{SIDE}{SPART}{F}{BL}"),
))
_EXTRA_SIDES = {"in front": "front", "behind": "back", "next to": "auto", "beside": "auto"}


@dataclass
class _Mention:
    start: int  # 원문 위치
    end: int
    key: str
    word: str
    clause: int = -1
    more: bool = False  # '하나 더'·'another'
    inst: str | None = None  # 가리키는 부품 id


@dataclass
class _Part:
    id: str
    key: str
    order: int  # 만든 순서
    item: int | None = None  # 직전 설계의 항목 번호 (새 부품은 None)
    copy_of: str | None = None  # '하나 더': 이 부품의 값을 그대로 쓴다
    clauses: list[int] = field(default_factory=list)  # 이 부품을 말한 절 (값은 그 절에서만 읽는다)
    head_of: bool = False  # '…달린 {A}' 의 A 로 쓰였는지
    ext: str | None = None  # 직전 설계의 부품 id (조립 항목마다 따로라 여러 항목에 같은 id 가 있을 수 있다)


@dataclass
class _Relation:
    kind: str
    start: int  # 절 안 위치 (토큰 글)
    groups: dict[str, Any]
    spans: list[tuple[int, int]]  # 지울 곳 (토큰 글 위치)


def _hangul_batchim(word: str) -> bool:
    c = word.strip()[-1:] or " "
    return "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 != 0


def _josa(word: str, with_batchim: str, without: str) -> str:
    """받침에 맞는 조사를 붙인다 (은신처는 · 그릇 받침은)."""
    return word + (with_batchim if _hangul_batchim(word) else without)


class _Composer:
    """요청 글 → 부품(인스턴스)·연결. 직전 설계의 부품도 인스턴스로 올려 두고 새 연결을 더한다 (수정 요청)."""

    def __init__(self, text: str, allowed: list[str], previous: list[dict], en: bool):
        self.text = text
        self.en = en
        self.keys = [k for k in allowed if k in primitives() and primitives()[k].composable]
        self.parts: dict[str, _Part] = {}
        self.edges: dict[str, tuple[str, str]] = {}  # 자식 → (부모, at)
        self.latest: dict[str, str] = {}  # 템플릿 → 마지막으로 말한 부품
        self.subject: str | None = None  # 마지막으로 말한 기준 구조물
        self.active: set[str] = set()  # 연결에 쓰인 부품 (면만 말하는 P2 의 주어가 될 수 있다)
        self.notes: list[str] = []
        self.blank: list[tuple[int, int]] = []  # 지울 원문 위치
        self.clause_text: list[str] = []
        self.orphans: dict[int, str | None] = {}  # 부품 낱말 없는 절 → 그 절의 주어
        self.decor_dropped = False  # 장식이 있던 직전 항목을 조립 항목에 넣었는지 (조립 항목에는 아직 장식이 없다)
        self._seed(previous)

    # ── 부품 ──

    def _new_id(self, key: str) -> str:
        base = PART_IDS.get(key, key)
        taken = set(self.parts)
        if base not in taken:
            return base
        n = 2
        while f"{base}{n}" in taken:
            n += 1
        return f"{base}{n}"

    def _add(self, key: str, *, item: int | None = None, pid: str | None = None, copy_of: str | None = None) -> str:
        pid = pid if pid is not None and pid not in self.parts else self._new_id(key)
        self.parts[pid] = _Part(pid, key, len(self.parts), item=item, copy_of=copy_of)
        self._touch(pid)
        return pid

    def _touch(self, pid: str) -> None:
        key = self.parts[pid].key
        self.latest[key] = pid
        if self._role(pid) in HOST_ROLES:
            self.subject = pid

    def _role(self, pid: str) -> str:
        return primitives()[self.parts[pid].key].role

    def _seed(self, previous: list[dict]) -> None:
        for idx, it in enumerate(previous):
            if it["template"] == ASSEMBLY_KEY:
                local: dict[str, str] = {}
                for p in it["parts"]:
                    if p["template"] in self.keys:
                        local[p["id"]] = self._add(p["template"], item=idx, pid=p["id"])
                        self.parts[local[p["id"]]].ext = p["id"]
                for c in it["connections"]:
                    if c["part"] in local and c["to"] in local:
                        self.edges[local[c["part"]]] = (local[c["to"]], c["at"])
            elif it["template"] in self.keys:
                self._add(it["template"], item=idx)
        # 직전 설계의 부품 낱말은 그 템플릿이 든 마지막 항목의 첫 부품(조립 항목이면 뿌리 쪽)을 가리키고, 주어는 마지막
        # 항목의 첫 기준 구조물이다 ('은신처 오른쪽에 …'·'왼쪽에 물병도 달아줘'). 연결에 쓰인 부품(active)은 이번 요청에서 정한다
        self.latest, self.subject = {}, None
        for idx in range(len(previous)):
            first: dict[str, str] = {}
            for pid, part in self.parts.items():
                if part.item == idx:
                    first.setdefault(part.key, pid)
            self.latest.update(first)
            hosts = [pid for pid in first.values() if self._role(pid) in HOST_ROLES]
            if hosts:
                self.subject = hosts[0]
        self.active = set()

    def _resolve(self, m: _Mention, *, new: bool = False, distinct: tuple[str | None, ...] = ()) -> str:
        """부품 낱말이 가리키는 부품: 이미 정했으면 그대로, '하나 더'·new 면 새 부품(같은 템플릿 부품의 사본),
        아니면 같은 템플릿의 마지막 부품 (distinct 에 든 부품이면 새 부품)."""
        if m.inst is None:
            last = self.latest.get(m.key)
            if new or m.more or last is None or last in distinct:
                m.inst = self._add(m.key, copy_of=last if (m.more or last in distinct) else None)
            else:
                m.inst = last
                self._touch(last)
        part = self.parts[m.inst]
        if m.clause not in part.clauses:
            part.clauses.append(m.clause)
        return m.inst

    def _descendant(self, pid: str, of: str) -> bool:
        cur: str | None = pid
        while cur is not None:
            if cur == of:
                return True
            cur = self.edges.get(cur, (None, ""))[0]
        return False

    def _ancestors(self, pid: str) -> tuple[str, ...]:
        """pid 와 그 위로 뿌리까지의 부품."""
        out = [pid]
        while out[-1] in self.edges:
            out.append(self.edges[out[-1]][0])
        return tuple(out)

    def _root(self, pid: str) -> str:
        while pid in self.edges:
            pid = self.edges[pid][0]
        return pid

    def _group(self, root: str) -> list[str]:
        """root 부터 너비 우선 (같은 부모의 자식은 연결한 순서)."""
        out, queue = [], [root]
        while queue:
            pid = queue.pop(0)
            out.append(pid)
            queue += [c for c, (p, _) in self.edges.items() if p == pid]
        return out

    def _free_tunnel(self) -> str | None:
        """끝이 남은 마지막 터널 (끝에 방을 잇는 '그 끝에')."""
        for pid in sorted(self.parts, key=lambda p: self.parts[p].order, reverse=True):
            if self.parts[pid].key == "tunnel" and self._ends_used(pid) < 2:
                return pid
        return None

    def _ends_used(self, pid: str) -> int:
        return (1 if pid in self.edges else 0) + sum(1 for p, _ in self.edges.values() if p == pid)

    @staticmethod
    def _passable(key: str) -> bool:
        """터널 끝에 이을 수 있는 방 (연결 표준: attach_order 에 passage 가 있고 터널이 아닌 부품)."""
        t = primitives()[key]
        return t.role != "connector" and "passage" in t.attach_order

    def _name(self, pid: str) -> str:
        names = TEMPLATE_NAMES_EN if self.en else TEMPLATE_NAMES_KO
        return names[self.parts[pid].key]

    def _note(self, ko: str, en: str) -> None:
        msg = en if self.en else ko
        if msg not in self.notes:
            self.notes.append(msg)

    # ── 연결 ──

    def link(self, child: str, parent: str, at: str) -> bool:
        """child 를 parent 의 at 면에 붙인다. 연결 표준으로 안 되는 연결은 안내만 하고 False."""
        pt, ct = primitives()[self.parts[parent].key], primitives()[self.parts[child].key]
        cn, pn = self._name(child), self._name(parent)
        if at == "top":
            self._note(f"위에 얹기는 아직 지원하지 않아 {_josa(cn, '은', '는')} {pn} 위에 올리지 않고 따로 두었습니다.",
                       f"Stacking on top isn't supported yet, so the {cn.lower()} stands on its own instead of on the "
                       f"{pn.lower()}.")
            return False
        if child == parent or self._descendant(parent, child):
            return False
        problem = None
        if pt.role not in (*HOST_ROLES, "connector"):
            problem = "accessory"
        elif not ct.attach_order or (pt.role == "connector" and (ct.role == "connector"
                                                                  or "passage" not in ct.attach_order)):
            problem = "child"
        elif pt.role == "connector" and self._ends_used(parent) >= 2 and self.edges.get(child, ("",))[0] != parent:
            problem = "ends"
        if problem:
            self._note(f"{_josa(cn, '은', '는')} {pn}에 붙일 수 없어 따로 두었습니다.",
                       f"The {cn.lower()} can't be attached to the {pn.lower()}, so it stands on its own.")
            return False
        if pt.role == "connector":
            at = "free_end"
        elif at == "free_end":
            at = "auto"
        if at == "auto" and pt.key == "sand_bath" and ct.key == "ramp":
            at = "front"  # 모래목욕통의 램프는 출입 면(앞 턱)에 걸친다
        # 부품 수 (방을 방의 출입구에 바로 붙이면 해석기가 터널을 하나 끼운다)
        size = len(set(self._group(self._root(parent))) | set(self._group(self._root(child))))
        if pt.role != "connector" and "passage" in ct.attach_order:
            size += 1
        old = self.edges.get(child)
        if old is None and size > MAX_PARTS:
            self._note(f"한 구조물에 부품은 {MAX_PARTS}개까지라 {_josa(cn, '은', '는')} 따로 두었습니다.",
                       f"One structure can have at most {MAX_PARTS} parts, so the {cn.lower()} stands on its own.")
            return False
        if old is not None and old[0] == parent and at == "auto":
            at = old[1]  # 같은 연결을 면 없이 다시 말하면 면은 그대로
        self.edges.pop(child, None)
        self.edges[child] = (parent, at)
        self.active |= {child, parent}
        return True

    # ── 글 읽기 ──

    def _mentions(self, low: str) -> list[_Mention]:
        """부품 낱말: 긴 것부터 겹치지 않게. 같은 템플릿 낱말이 겹치면 합친다 ("밥그릇 받침" = 밥그릇 + 그릇 받침)."""
        text = low
        if "터널" in text:  # "집 모양 터널" 의 집은 터널 단면 모양
            text = text.replace("집 모양", "＿ 모양").replace("집모양", "＿모양")
        if TEMPLATE_KEYWORDS_EN["tunnel"].search(text):
            text = HOUSE_SHAPE_EN.sub(lambda mm: "_" * len(mm.group(0)), text)
        # '바깥 램프'·'outside ramp' 는 2층 집의 오르는 수단이다 (attach_to 로 잇는 따로 놓는 램프, 아래 interpret)
        for w in HOUSE_EXTERNAL:
            text = text.replace(w, "＿" * len(w))
        text = HOUSE_EXTERNAL_EN.sub(lambda mm: "_" * len(mm.group(0)), text)
        hits: list[tuple[int, int, str]] = []
        for key in self.keys:
            for w in TEMPLATE_KEYWORDS.get(key, ()):
                if w in _HOUSE_PORT_WORDS:
                    continue
                hits += [(m.start(), m.end(), key) for m in re.finditer(re.escape(w), text)]
            if key in TEMPLATE_KEYWORDS_EN:
                hits += [(m.start(), m.end(), key) for m in TEMPLATE_KEYWORDS_EN[key].finditer(text)]
        merged: list[list[Any]] = []
        for s, e, key in sorted(hits):
            if merged and merged[-1][2] == key and s < merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e, key])
        taken: list[list[Any]] = []
        for s, e, key in sorted(merged, key=lambda h: (h[0] - h[1], h[0])):
            if all(e <= ts or te <= s for ts, te, _ in taken):
                taken.append([s, e, key])
        taken.sort()
        # "2층 집"·"창문 있는 집": 집 부품 낱말이 있으면 '집'·'하우스'·house 는 은신처가 아니라 그 집이다
        if any(k == "house" for _, _, k in taken):
            for h in taken:
                if h[2] == "hideout" and (text[h[0]:h[1]] in ("집", "하우스") or text[h[0]:h[1]].startswith("house")):
                    h[2] = "house"
        out: list[list[Any]] = []
        for h in taken:  # 공백만 사이에 둔 같은 템플릿 낱말은 한 부품 ("경사 지붕 집")
            if out and out[-1][2] == h[2] and not text[out[-1][1]:h[0]].strip():
                out[-1][1] = h[1]
            else:
                out.append(list(h))
        return [_Mention(s, e, key, low[s:e]) for s, e, key in out]

    def _clauses(self, low: str, mentions: list[_Mention]) -> list[tuple[int, int]]:
        spans, pos = [], 0
        for m in _CLAUSE_CUT.finditer(low):
            cut = m.end("verb") if m.group("verb") else m.start()  # 동사(…고)는 앞 절에 남긴다
            if cut > pos:
                spans.append((pos, cut))
            pos = m.end()
        if pos < len(low):
            spans.append((pos, len(low)))
        # 앞뒤 공백은 뺀다 (틀은 절 첫머리부터 찾는다)
        spans = [(s + len(low[s:e]) - len(low[s:e].lstrip()), e - len(low[s:e]) + len(low[s:e].rstrip()))
                 for s, e in spans if low[s:e].strip()]

        def pure(span: tuple[int, int]) -> bool:
            inside = [m for m in mentions if span[0] <= m.start < span[1]]
            if not inside:
                return False
            rest = low[span[0]:span[1]]
            for m in sorted(inside, key=lambda m: -m.start):
                rest = rest[:m.start - span[0]] + " " + rest[m.end - span[0]:]
            return bool(_PURE_LEFTOVER.match(rest))

        # 순수 나열 절은 이웃 절과 합친다 (첫 절이면 다음 절, 아니면 앞 절)
        out: list[tuple[int, int]] = []
        carry: tuple[int, int] | None = None
        for span in spans:
            if carry is not None:
                span, carry = (carry[0], span[1]), None
            if pure(span) and len(spans) > 1:
                if out:
                    out[-1] = (out[-1][0], span[1])
                else:
                    carry = span
                continue
            out.append(span)
        if carry is not None:
            out.append(carry)
        return out

    def _tokenize(self, low: str, span: tuple[int, int], ms: list[_Mention]) -> tuple[str, list[int]]:
        """절 글의 부품 낱말을 ⟦역할번호⟧ 토큰으로 바꾼 글과, 토큰 글 위치 → 원문 위치 표."""
        out, where, pos = [], [], span[0]
        for i, m in ms:
            out.append(low[pos:m.start])
            where += list(range(pos, m.start))
            role = primitives()[m.key].role
            tok = f"⟦{'H' if role in HOST_ROLES else 'T' if role == 'connector' else 'X'}{i}⟧"
            out.append(tok)
            where += [m.start] * (len(tok) - 1) + [m.end - 1]
            pos = m.end
        out.append(low[pos:span[1]])
        where += list(range(pos, span[1]))
        where.append(span[1])
        return "".join(out), where

    def run(self) -> str:
        """연결을 찾고, 찾아 쓴 곳을 빈칸으로 지운 글을 돌려준다 (예전 키워드 해석에 넘긴다)."""
        low = self.text.lower()
        mentions = self._mentions(low)
        clauses = self._clauses(low, mentions)
        for ci, span in enumerate(clauses):
            self.clause_text.append(self.text[span[0]:span[1]])
            ms = [(i, m) for i, m in enumerate(mentions) if span[0] <= m.start < span[1]]
            for _, m in ms:
                m.clause = ci
                before, after = low[span[0]:m.start], low[m.end:span[1]]
                m.more = bool(_MORE_AFTER.match(after) or _MORE_BEFORE.search(before))
            if not ms:  # 부품 낱말 없는 절 ('환기구 8개로')은 그 때의 주어 부품 값에 쓴다 (주어가 아직 없으면 다음 주어)
                self.orphans[ci] = self.subject
                continue
            tok, where = self._tokenize(low, span, ms)
            blank_before = len(self.blank)
            rels = self._find_relations(tok)
            pending = sorted((m for _, m in ms), key=lambda m: m.start)
            for rel in rels:
                rel_start = where[rel.start]
                for m in [m for m in pending if m.start < rel_start and not self._in_rel(m, mentions, rels)]:
                    self._resolve(m)
                if self._apply(rel, mentions, tok):
                    for s, e in rel.spans:
                        self.blank.append((where[s], where[e - 1] + 1))
            for m in pending:
                self._resolve(m)
            if len(self.blank) > blank_before:
                # 붙이는 말(붙여·달아·연결 …)도 지운다: '붙여'는 몰아 놓기(_grouped) 말이기도 하다
                for v in _ATTACH_WORDS.finditer(low, span[0], span[1]):
                    self.blank.append(v.span())
        first_subject = next((m.inst for m in mentions if m.inst and self._role(m.inst) in HOST_ROLES), self.subject)
        self.orphans = {ci: (s if s is not None else first_subject) for ci, s in self.orphans.items()}
        # 이어진 부품을 말한 낱말은 모두 지운다. 연결 글 안의 이어지지 않은 부품 낱말은 남긴다 (따로 놓는 항목)
        joined = {c for c in self.edges} | {p for p, _ in self.edges.values()}
        chars = list(self.text)
        for s, e in self.blank:
            for i in range(s, e):
                chars[i] = " "
        for m in mentions:
            if m.inst in joined:
                for i in range(m.start, m.end):
                    chars[i] = " "
            elif m.inst is not None:
                for i in range(m.start, m.end):
                    chars[i] = self.text[i]
        rest = "".join(chars)
        if any(m.key == "tunnel" and m.inst in joined for m in mentions):
            # 지운 터널의 단면 모양 말('집 모양'·'house-shaped')을 남은 글에서 은신처로 읽지 않게 함께 지운다
            for rx in (re.compile(r"집\s?모양"), re.compile(HOUSE_SHAPE_EN.pattern, re.IGNORECASE)):
                rest = rx.sub(lambda mm: " " * len(mm.group(0)), rest)
        return rest

    @staticmethod
    def _in_rel(m: _Mention, mentions: list[_Mention], rels: list[_Relation]) -> bool:
        idx = mentions.index(m)
        return any(idx in r.groups["ids"] for r in rels)

    def _find_relations(self, tok: str) -> list[_Relation]:
        found: list[_Relation] = []
        claimed: list[tuple[int, int]] = []
        for kind, rx in _PATTERNS:
            for m in rx.finditer(tok):
                if any(m.start() < e and s < m.end() for s, e in claimed):
                    continue
                g = {k: v for k, v in m.groupdict().items() if v is not None}
                side = g.get("side")
                if side is not None:
                    side_word = re.sub(r"\s+", " ", side)
                    g["side"] = _EXTRA_SIDES.get(side_word) or _SIDE_OF.get(side_word, "auto")
                    s0, e0 = m.span("side")
                    if _ZONE_AFTER.match(tok[e0:]) or _ZONE_BEFORE.search(tok[:s0]):
                        continue  # 케이지 안 위치 (구석·벽·케이지 왼쪽 …)
                if kind == "twin" and "twin" not in g and "cnt" not in g:
                    continue  # 하나만 말한 방은 P4 (터널로 이은 은신처)
                g["ids"] = [int(i) for _, i in _TOKEN.findall(m.group(0))]
                g["bl"] = [int(i) for _, i in _TOKEN.findall(g["bl"])] if "bl" in g else []
                fills = [m.span(k) for k in m.groupdict() if k.startswith("f") and m.group(k) is not None]
                spans = _subtract(m.span(), fills)
                found.append(_Relation(kind, m.start(), g, spans))
                claimed.append(m.span())
        return sorted(found, key=lambda r: r.start)

    def _apply(self, rel: _Relation, mentions: list[_Mention], tok: str) -> bool:
        g = rel.groups

        def get(k: str) -> _Mention:
            return mentions[int(g[k])]

        side = g.get("side")
        ok = False
        if rel.kind in ("twin", "chain", "tunnel"):
            rooms = [get(k) for k in ("r", "b") if k in g]
            if not all(self._passable(m.key) for m in rooms):
                self._note("터널 끝에는 은신처·집 같은 방만 이을 수 있어 따로 두었습니다.",
                           "Only rooms such as a hideout or house can sit at a tunnel end, so the parts stand on their own.")
                return False
        if rel.kind == "twin":
            r, t = get("r"), get("t")
            a = self._resolve(r)
            tube = self._resolve(t, new=True)
            b = self._add(r.key, copy_of=a)
            self.parts[b].clauses.append(r.clause)
            ok = self.link(tube, a, "auto") and self.link(b, tube, "free_end")
        elif rel.kind == "chain":
            a = self._resolve(get("a"))
            tube = self._resolve(get("t"), new=True)
            b = self._resolve(get("b"), distinct=(a,))
            ok = self.link(tube, a, "auto") and self.link(b, tube, "free_end")
        elif rel.kind == "tunnel":
            if "a" in g:
                parent: str | None = self._resolve(get("a"))
            else:
                parent = self.subject
            t = get("t")
            reuse = None if (side or "a" in g) else self._free_tunnel()
            if reuse is not None and reuse in self.edges and t.inst is None:
                t.inst = reuse
                self.parts[reuse].clauses.append(t.clause)
                tube = reuse
            else:
                tube = self._resolve(t, new=True)
            room = self._resolve(get("r"), distinct=(parent,))
            if reuse is not None and tube == reuse:
                ok = self.link(room, tube, "free_end")
            elif parent is None or parent == room:
                ok = self.link(tube, room, side or "auto")  # 이을 기준이 없으면 그 방에 터널을 단다
            else:
                ok = self.link(tube, parent, side or "auto") and self.link(room, tube, "free_end")
        elif rel.kind in ("side", "head", "roof"):
            children = [mentions[i] for i in g["bl"]] or ([get("b")] if "b" in g else [])
            if rel.kind == "head":
                kids = [self._resolve(c) for c in children]
                am = get("a")
                head_used = self.latest.get(am.key)
                fresh = am.inst is None and head_used is not None and self.parts[head_used].head_of
                parent = self._resolve(am, new=fresh)
                self.parts[parent].head_of = True
            elif "a" in g:
                parent = self._resolve(get("a"))
                # 터널 끝에 다는 방은 그 터널이 달린 방과 다른 부품이다 ("은신처 앞에 터널, 터널 끝에 은신처")
                above = self._ancestors(parent) if self.parts[parent].key == "tunnel" else ()
                kids = [self._resolve(c, distinct=above) for c in children]
            else:  # P2: 부품 없이 면만 — 마지막 터널의 끝, 또는 연결에 쓰인(또는 붙이는 말이 있는) 기준 구조물
                if side == "free_end":
                    parent = self._free_tunnel()
                else:
                    parent = self.subject
                    attach_word = re.search(_FRAG["ATTV"], tok) is not None
                    if parent is None or not (parent in self.active or attach_word):
                        return False
                    if any(primitives()[c.key].role in HOST_ROLES and not c.more for c in children):
                        return False
                if parent is None:
                    return False
                # 터널 끝에 다는 방은 그 터널이 달린 방과 다른 부품이다 ("집 오른쪽에 터널 달고 그 끝에 은신처")
                above = self._ancestors(parent) if side == "free_end" else ()
                kids = [self._resolve(c, distinct=above) for c in children]
            if rel.kind == "roof":
                side = "auto" if self.parts[kids[0]].key == "ramp" else "top"
            sides = [side or "auto"] * len(kids)
            if side == "both":
                if len(kids) == 1:
                    copy = self._add(self.parts[kids[0]].key, copy_of=kids[0])
                    self.parts[copy].clauses += self.parts[kids[0]].clauses
                    kids.append(copy)
                sides = ["right", "left"] + ["auto"] * (len(kids) - 2)
            for kid, at in zip(kids, sides):
                ok = self.link(kid, parent, at) or ok
        return ok

    # ── 결과 ──

    def groups(self) -> list[list[str]]:
        """부품이 둘 이상인 조립 묶음 (뿌리부터 너비 우선)."""
        roots = sorted({self._root(c) for c in self.edges}, key=lambda p: self.parts[p].order)
        return [self._group(r) for r in roots]

    def part_text(self, pid: str) -> str:
        part = self.parts[pid]
        cl = list(part.clauses) + [ci for ci, s in self.orphans.items() if s == pid]
        return " ".join(self.clause_text[ci] for ci in sorted(set(cl)) if 0 <= ci < len(self.clause_text))

    def out_ids(self, group: list[str]) -> dict[str, str]:
        """내보낼 부품 id: 직전 설계의 id 를 그대로 쓰고 (항목 안에서 겹치면 내부 id), 새 부품은 내부 id."""
        out: dict[str, str] = {}
        for pid in group:
            ext = self.parts[pid].ext
            out[pid] = ext if ext is not None and ext not in out.values() and ext not in set(group) - {pid} else pid
        return out

    def connections(self, group: list[str]) -> list[dict]:
        ids = self.out_ids(group)
        return [{"part": ids[c], "to": ids[self.edges[c][0]], "at": self.edges[c][1]} for c in group[1:]]

    def describe(self, group: list[str]) -> tuple[str, str]:
        """조립 항목 이름과 연결 설명 (응답 언어)."""
        name = _assembly_name([self.parts[p].key for p in group], self.en)
        if self.en:
            links = "; ".join(f"{self._name(c).lower()} → {self._name(p).lower()} {SIDE_NAMES_EN[at]}"
                              for c, p, at in ((c, *self.edges[c]) for c in group[1:]))
        else:
            links = ", ".join(f"{self._name(c)} → {self._name(p)} {SIDE_NAMES_KO[at]}"
                              for c, p, at in ((c, *self.edges[c]) for c in group[1:]))
        return name, links


def _assembly_name(keys: list[str], en: bool) -> str:
    """조립 항목 이름: '그릇 받침·물병 거치대가 달린 은신처' / 'Hideout with bowl holder and water bottle stand'."""
    names = TEMPLATE_NAMES_EN if en else TEMPLATE_NAMES_KO
    kids = list(dict.fromkeys(names[k] for k in keys[1:]))
    if en:
        low = [k.lower() for k in kids]
        listed = low[0] if len(low) == 1 else ", ".join(low[:-1]) + " and " + low[-1]
        return f"{names[keys[0]]} with {listed}"
    return f"{_josa('·'.join(kids), '이', '가')} 달린 {names[keys[0]]}"


def _subtract(span: tuple[int, int], holes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out, pos = [], span[0]
    for s, e in sorted(holes):
        if s > pos:
            out.append((pos, s))
        pos = max(pos, e)
    if pos < span[1]:
        out.append((pos, span[1]))
    return [(s, e) for s, e in out if e > s]


def _strip_locatives(text: str) -> str:
    """빼기 요청에서 '은신처에서'·'from the hideout' 처럼 어디서 빼는지 말한 부품 낱말을 지운다 (그 부품은 빼지 않는다)."""
    out = re.sub(r"\S+?(?:에서는|에서|에선)(?=\s|$)", lambda m: " " * len(m.group(0)), text)
    return re.sub(r"\bfrom\s+(?:(?:the|a|an|my|its)\s+)?[A-Za-z]+(?:\s+[A-Za-z]+)?",
                  lambda m: " " * len(m.group(0)), out, flags=re.IGNORECASE)


def _remove_parts(it: dict, keys: set[str], en: bool = False) -> dict | None:
    """조립 항목에서 keys 템플릿 부품과 그 아래 부품을 뺀다. 뿌리가 빠지면 None, 하나만 남으면 일반 항목."""
    drop = {p["id"] for p in it["parts"] if p["template"] in keys}
    changed = True
    while changed:
        changed = False
        for c in it["connections"]:
            if c["to"] in drop and c["part"] not in drop:
                drop.add(c["part"])
                changed = True
    parts = [p for p in it["parts"] if p["id"] not in drop]
    if not parts or parts[0]["id"] != it["parts"][0]["id"]:
        return None
    if len(parts) == 1:
        return _plain_from_part(it, parts[0])
    if len(parts) == len(it["parts"]):
        return it
    return {**it, "parts": parts, "connections": [c for c in it["connections"] if c["part"] not in drop],
            "name_ko": _assembly_name([p["template"] for p in parts], en)}


def _templates_of(it: dict) -> list[str]:
    return [p["template"] for p in it["parts"]] if it["template"] == ASSEMBLY_KEY else [it["template"]]


def _plain_from_part(it: dict, part: dict) -> dict:
    return {"template": part["template"], "params": part["params"], "placement": dict(it["placement"]),
            "reason_ko": it["reason_ko"]}


class MockInterpreter:
    name = "mock"

    @staticmethod
    def _reason_en(req: InterpretRequest, key: str) -> str:
        if is_aquarium(req):  # 크기 구분 이름은 규칙 파일의 한국어 이름을 카탈로그로 바꾼다
            group = catalog().translate(req.size_rules.display_name)
            return (f"Found '{TEMPLATE_NAMES_EN[key]}' in your request and used the standard tank values "
                    f"for the {group}.")
        return (f"Found '{TEMPLATE_NAMES_EN[key]}' in your request and used the standard values "
                f"for a {pet_name_en(req)}.")

    @staticmethod
    def _reason_ko(req: InterpretRequest, key: str) -> str:
        if is_aquarium(req):
            return (f"요구사항에서 '{TEMPLATE_NAMES_KO[key]}'을(를) 찾아 {req.size_rules.display_name} "
                    "수조 기준에 맞춰 구성했습니다.")
        return (f"요구사항에서 '{TEMPLATE_NAMES_KO[key]}'을(를) 찾아 {req.habitat.species_name_ko} "
                f"{req.size_rules.display_name} 기준값으로 구성했습니다.")

    def interpret(self, req: InterpretRequest) -> InterpretResult:
        text = req.prompt
        en = req.language == "en"
        names_of = TEMPLATE_NAMES_EN if en else TEMPLATE_NAMES_KO
        registry = {t.key: t for t in all_templates()}
        ctx = RuleContext(req.size_rules, req.min_wall_mm, req.habitat.count)
        notes: list[str] = []
        aquarium = is_aquarium(req)
        allowed = [k for k in req.allowed_templates if k in registry]  # 이 종에 만들 수 있는 구조물
        # 아무것도 말하지 않았을 때 만들 기본 구조물: 케이지는 은신처, 어항은 물속 동굴(허용 목록의 첫 템플릿)
        default_key = "hideout" if "hideout" in allowed or not allowed else allowed[0]
        # 조립 항목은 기준 구조물(은신처·집·모래목욕통)이 있는 묶음의 계약에만 있다 (spec._item_union)
        compose_on = not aquarium and assembly_enabled(allowed)

        # 장식은 장식 영역이 있는 템플릿에만. 그런 템플릿이 허용 목록에 없으면(어항) 계약에 decor 필드도 없다 (spec._item_union)
        decor_field = any(k in DECOR_TEMPLATES for k in allowed)
        decor = _find_decor(text) if decor_field else None

        items: list[dict] = []
        # attach_to 도 집·램프가 모두 있는 묶음(케이지)의 계약에만 있다
        attach_field = all(k in allowed for k in ATTACH_TEMPLATES)
        dropped: list[str] = []
        if req.previous is not None:
            items = json.loads(req.previous.model_dump_json())["items"]
            for it in items:  # 저장된 버전은 모든 템플릿 계약으로 읽어 decor·attach_to 가 null 로 들어 있다
                if not decor_field:
                    it.pop("decor", None)
                if not attach_field:
                    it["placement"].pop("attach_to", None)
            # 직전 설계에 이 종이 만들 수 없는 구조물이 있으면(규칙 파일이 바뀐 경우) 실제 LLM 처럼 빼고 알린다
            kept = []
            for it in items:
                if it["template"] != ASSEMBLY_KEY:
                    (kept.append(it) if it["template"] in allowed else dropped.append(it["template"]))
                    continue
                bad = {p["template"] for p in it["parts"]} - set(allowed)
                dropped += [p["template"] for p in it["parts"] if p["template"] in bad]
                if not compose_on:  # 조립 항목이 없는 계약이면 기준 부품만 일반 항목으로 남긴다
                    root = it["parts"][0]
                    if root["template"] in allowed:
                        kept.append(_plain_from_part(it, root))
                    continue
                rest = _remove_parts(it, bad, en) if bad else it
                if rest is not None:
                    kept.append(rest)
            items = kept
        low = _en(text)
        removing = req.previous is not None and (any(w in text for w in REMOVE) or bool(REMOVE_EN.search(low)))
        remove_keys = [k for k in _find_templates(_strip_locatives(text), aquarium=aquarium) if k in registry] \
            if removing else []

        # 조립 문법: 붙이기·달기·잇기를 찾아 조립 항목으로 묶고, 쓴 글 조각은 지운다 (빼기 요청에는 쓰지 않는다)
        composer = None
        rest_text = text
        if compose_on and not remove_keys:
            composer = _Composer(text, allowed, items, en)
            rest_text = composer.run()
            notes += composer.notes

        requested = _find_templates(rest_text, aquarium=aquarium)
        unsupported = [k for k in requested if k not in registry]
        if unsupported:
            names = ", ".join(names_of[k] for k in unsupported)
            notes.append(f"Left out because they aren't supported yet: {names}" if en
                         else f"아직 지원하지 않는 구조물이라 제외했습니다: {names}")
        if "house" in requested and (any(w in text for w in HOUSE_EXTERNAL) or HOUSE_EXTERNAL_EN.search(low)):
            requested = [k for k in requested if k != "ramp"]  # 바깥 램프는 아래에서 attach_to 로 붙인다
        not_allowed = list(dict.fromkeys([k for k in requested if k in registry and k not in allowed] + dropped))
        if not_allowed:
            names = ", ".join(names_of[k] for k in not_allowed)
            species = req.habitat.species_name_ko
            notes.append(f"Left out because they can't be made for {catalog().translate(species).lower()}: {names}"
                         if en else f"{species}에는 만들 수 없는 구조물이라 제외했습니다: {names}")
        requested = [k for k in requested if k in registry and k in allowed]

        # 어항: 동굴 출입구 개수를 말하는 말(앞뒤·front and back)은 위치 요청이 아니다
        zone = _find_zone(_without_door_phrases(rest_text) if aquarium else rest_text)
        grouped = _grouped(rest_text)
        factor = _scale_factor(text)

        if remove_keys:
            keys = set(remove_keys)
            out = []
            for it in items:
                if it["template"] == ASSEMBLY_KEY:
                    rest = _remove_parts(it, keys, en)
                    if rest is not None:
                        out.append(rest)
                elif it["template"] not in keys:
                    out.append(it)
            items = out
            requested = []
        elif composer is not None:
            items = self._compose_items(composer, items, req, ctx, factor, zone, grouped, attach_field)

        if req.previous is not None and not remove_keys:
            if any(w in text for w in ADD) or ADD_EN.search(low):
                pass  # 아래에서 requested 를 새로 추가
            else:
                # 이미 있는 템플릿은 수정 대상, 없는 템플릿만 새로 추가
                existing = {k for it in items for k in _templates_of(it)}
                explicit = [k for k in requested if k in existing]
                targets = explicit or list(existing)
                for it in items:
                    if it.pop("_new", False):
                        continue  # 이번 요청으로 만든 조립 항목은 이미 그 절의 값으로 만들었다
                    if it["template"] == ASSEMBLY_KEY:
                        for p in it["parts"]:
                            t = registry[p["template"]]
                            # 크기 말은 기준 구조물(이름을 말했으면 그 부품)만 키우고 줄인다
                            if p["template"] in targets and (explicit or t.role in HOST_ROLES):
                                p["params"] = _scaled(t, p["params"], factor)
                            if p["template"] in targets:
                                p["params"] = _apply_numbers(t.key, text, p["params"])
                    elif it["template"] in targets:
                        t = registry[it["template"]]
                        it["params"] = _apply_numbers(t.key, text, _scaled(t, it["params"], factor),
                                                      aquarium=aquarium)
                        if decor and it["template"] in DECOR_TEMPLATES:
                            it["decor"] = decor
                    if any(k in targets for k in _templates_of(it)):
                        if zone:
                            it["placement"]["zone"] = zone
                        if grouped:
                            it["placement"]["group"] = "g1"
                requested = [k for k in requested if k not in existing]
        elif req.previous is None and not requested and not items:
            requested = [default_key]
            if default_key == "hideout":
                notes.append("No specific structure was mentioned, so I designed one standard hideout." if en
                             else "구체적인 구조물 언급이 없어 기본 은신처 1개로 설계했습니다.")
            else:
                notes.append(f"No specific structure was mentioned, so I designed one standard "
                             f"{TEMPLATE_NAMES_EN[default_key].lower()}." if en
                             else f"구체적인 구조물 언급이 없어 기본 {TEMPLATE_NAMES_KO[default_key]} 1개로 설계했습니다.")
        for it in items:
            it.pop("_new", None)

        for key in requested:
            t = registry[key]
            params = _apply_numbers(key, text, _scaled(t, t.default_params(ctx).model_dump(), factor),
                                    aquarium=aquarium)
            items.append({
                "template": key,
                "params": params,
                "placement": self._placement(zone, grouped, attach_field),
                **({"decor": decor if key in DECOR_TEMPLATES else None} if decor_field else {}),
                "reason_ko": self._reason_en(req, key) if en else self._reason_ko(req, key),
            })
        lost_decor = (decor and any(it["template"] == ASSEMBLY_KEY for it in items)
                      and not any(it.get("decor") for it in items))
        if lost_decor or (composer is not None and composer.decor_dropped):
            notes.append("Decorations can't go on connected structures yet, so I left the decoration out." if en
                         else "조립 구조물에는 아직 장식을 넣을 수 없어 장식은 뺐습니다.")

        # 2층 집에 바깥 램프: 램프 항목을 더하고 attach_to 로 잇는다 (램프 높이 = 2층 바닥 높이). 집·램프가 모두 있는 종만
        for idx, it in enumerate(items if attach_field else []):
            if it["template"] != "house" or it["params"]["floors"]["count"] != 2:
                continue
            if it["params"]["floors"]["climb"] != "external_ramp":
                continue
            already = any(x["template"] == "ramp" and (x["placement"].get("attach_to") or {}).get("item_index") == idx
                          for x in items)
            if already or len(items) >= MAX_ITEMS:
                continue
            ramp = registry["ramp"]
            rp = ramp.default_params(ctx).model_dump()
            rp["height_mm"] = it["params"]["floors"]["level_height_mm"]
            items.append({
                "template": "ramp", "params": rp,
                "placement": {"zone": "auto", "group": None, "rotation": None,
                              "attach_to": {"item_index": idx, "side": it["params"]["floors"]["exit_side"]}},
                "reason_ko": ("A ramp attached to the house's second-floor landing." if en
                              else "2층 집의 바깥 착지판에 닿는 램프입니다."),
            })

        if not items:
            t = registry[default_key]
            if default_key == "hideout":
                reason = ("Every structure was removed, so I kept the standard hideout." if en
                          else "구조물이 모두 제외되어 기본 은신처를 남겼습니다.")
            else:
                reason = (f"Every structure was removed, so I kept the standard {TEMPLATE_NAMES_EN[default_key].lower()}."
                          if en else f"구조물이 모두 제외되어 기본 {TEMPLATE_NAMES_KO[default_key]}을(를) 남겼습니다.")
            items.append({
                "template": default_key, "params": t.default_params(ctx).model_dump(),
                "placement": {"zone": "auto", "group": None, "rotation": None,
                              **({"attach_to": None} if attach_field else {})},
                "reason_ko": reason,
            })
        items = items[:MAX_ITEMS]
        for it in items:  # 조립 항목에는 decor 필드가 없고, 일반 항목은 계약에 decor 가 있으면 늘 적는다
            if it["template"] == ASSEMBLY_KEY:
                it.pop("decor", None)
            elif decor_field:
                it.setdefault("decor", None)
        names = ", ".join(it["name_ko"] if it["template"] == ASSEMBLY_KEY else names_of.get(it["template"], it["template"])
                          for it in items)
        summary = (f"[Dev mock interpreter] Read your request by keywords and designed: {names}." if en
                   else f"[개발용 모의 해석기] 요구사항을 키워드로 해석해 {names}을(를) 설계했습니다.")
        spec_json = json.dumps({
            "summary_ko": summary,
            "items": items,
            "notes_ko": notes,
            "missing_parts": [],
        }, ensure_ascii=False)
        # 실제 LLM 과 같은 계약: 이 종에 만들 수 있는 템플릿만 받는다
        return InterpretResult(spec=parse_spec(spec_json, allowed or None), provider=self.name, attempts=1)

    @staticmethod
    def _placement(zone: str | None, grouped: bool, attach_field: bool) -> dict:
        return {"zone": zone or ("left" if grouped else "auto"), "group": "g1" if grouped else None, "rotation": None,
                **({"attach_to": None} if attach_field else {})}

    def _compose_items(self, comp: _Composer, items: list[dict], req: InterpretRequest, ctx: RuleContext,
                       factor: float, zone: str | None, grouped: bool, attach_field: bool) -> list[dict]:
        """조립 묶음을 항목으로: 직전 항목 자리에 (그 항목의 배치 그대로) 두고, 새 묶음은 뒤에 붙인다.
        새 부품의 값 = 기본값 → 크기 말 → 그 부품을 말한 절의 숫자 ('하나 더' 는 원래 부품 값의 사본)."""
        en = req.language == "en"
        groups = comp.groups()
        in_group = {pid: g for g in groups for pid in g}
        params: dict[str, dict] = {}

        def stored(pid: str) -> dict | None:
            part = comp.parts[pid]
            if part.item is None:
                return None
            it = items[part.item]
            if it["template"] == ASSEMBLY_KEY:
                return next(p["params"] for p in it["parts"] if p["id"] == part.ext)
            return it["params"]

        for pid in sorted(comp.parts, key=lambda p: comp.parts[p].order):
            if pid not in in_group:
                continue
            part = comp.parts[pid]
            t = primitives()[part.key]
            own = comp.part_text(pid)
            if (old := stored(pid)) is not None:
                params[pid] = old
            elif part.copy_of is not None and part.copy_of in params:
                params[pid] = _apply_numbers(part.key, own, copy.deepcopy(params[part.copy_of]))
            elif part.copy_of is not None and (src := stored(part.copy_of)) is not None:
                params[pid] = _apply_numbers(part.key, own, copy.deepcopy(src))
            else:
                base = t.default_params(ctx).model_dump()
                params[pid] = _apply_numbers(part.key, own, _scaled(t, base, _scale_factor(own) if own else factor))

        def assembly_item(group: list[str]) -> dict:
            origin = next((comp.parts[p].item for p in group if comp.parts[p].item is not None), None)
            prev = items[origin] if origin is not None else None
            conns = comp.connections(group)
            ids = comp.out_ids(group)
            parts = [{"id": ids[p], "template": comp.parts[p].key, "params": params[p]} for p in group]
            same = (prev is not None and prev["template"] == ASSEMBLY_KEY
                    and [p["id"] for p in prev["parts"]] == [ids[p] for p in group] and prev["connections"] == conns)
            if same:
                return {**prev, "parts": parts}
            name, links = comp.describe(group)
            if en:
                reason = (f"Found how the parts connect in your request ({links}) and used the standard values "
                          f"for a {pet_name_en(req)}. The server picks the joints and matching sizes.")
            else:
                reason = (f"요구사항에서 부품 연결({links})을 찾아 {req.habitat.species_name_ko} "
                          f"{req.size_rules.display_name} 기준값으로 구성했습니다. 결합 방식과 맞물리는 치수는 서버가 정합니다.")
            placement = dict(prev["placement"]) if prev is not None else self._placement(zone, grouped, attach_field)
            item = {"template": ASSEMBLY_KEY, "name_ko": name, "parts": parts, "connections": conns,
                    "placement": placement, "reason_ko": reason}
            problems = connection_problems([(ids[p], comp.parts[p].key) for p in group], [Connection(**c) for c in conns])
            if problems:  # 연결 표준 검사를 빠져나간 경우: 부품을 따로 놓는다 (실제 LLM 이면 재시도할 오류)
                return {"_split": [{"template": comp.parts[p].key, "params": params[p], "placement": dict(placement),
                                    "reason_ko": reason} for p in group]}
            return item

        out: list[dict] = []
        emitted: set[str] = set()
        for idx, it in enumerate(items):
            pids = [pid for pid, part in comp.parts.items() if part.item == idx]
            if not pids:  # 조립 문법이 모르는 항목 (허용 안 된 부품 등)은 그대로
                out.append(it)
                continue
            for pid in pids:
                if pid in in_group:
                    comp.decor_dropped |= bool(it.get("decor"))
                    r = in_group[pid][0]
                    if r not in emitted:
                        emitted.add(r)
                        out.append(assembly_item(in_group[r]))
                elif it["template"] != ASSEMBLY_KEY:
                    out.append(it)  # 이어지지 않은 일반 항목은 그대로
                elif pid == pids[0]:
                    out.append(_plain_from_part(it, it["parts"][0]))  # 자식이 모두 다른 묶음으로 옮겨 가 뿌리만 남았다
        for g in groups:
            if g[0] not in emitted:
                emitted.add(g[0])
                out.append({**assembly_item(g), "_new": True})
        flat: list[dict] = []
        for it in out:
            flat += it.pop("_split") if "_split" in it else [it]
        return flat
