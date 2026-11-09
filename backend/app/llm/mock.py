"""개발·테스트용 모의 해석기 (키워드 기반).

ANTHROPIC_API_KEY 없이 전체 흐름을 개발·테스트하기 위한 것이다. 실제 서비스용이 아니다.
출력은 실제 LLM 과 같은 DesignSpec 계약을 따르고, 같은 검증(parse_spec)을 거친다.
"""

from __future__ import annotations

import json
import re

from app.i18n import catalog
from app.llm.base import InterpretRequest, InterpretResult
from app.llm.prompts import is_aquarium, pet_name_en
from app.llm.spec import ATTACH_TEMPLATES, MAX_ITEMS, parse_spec
from app.templates.base import RuleContext
from app.templates.registry import all_templates
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
}
TEMPLATE_NAMES_KO = {"hideout": "은신처", "tunnel": "터널", "ramp": "램프/계단", "sand_bath": "모래목욕통", "house": "집",
                     "cave": "물속 동굴"}
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
}
TEMPLATE_NAMES_EN = {"hideout": "Hideout", "tunnel": "Tunnel", "ramp": "Ramp/stairs", "sand_bath": "Sand bath",
                     "house": "House", "cave": "Underwater cave"}
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
    if key == "ramp":
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
        allowed = [k for k in req.allowed_templates if k in registry]  # 이 종에 만들 수 있는 구조물
        # 아무것도 말하지 않았을 때 만들 기본 구조물: 케이지는 은신처, 어항은 물속 동굴(허용 목록의 첫 템플릿)
        default_key = "hideout" if "hideout" in allowed or not allowed else allowed[0]

        requested = _find_templates(text, aquarium=is_aquarium(req))
        unsupported = [k for k in requested if k not in registry]
        if unsupported:
            names = ", ".join(names_of[k] for k in unsupported)
            notes.append(f"Left out because they aren't supported yet: {names}" if en
                         else f"아직 지원하지 않는 구조물이라 제외했습니다: {names}")
        if "house" in requested and (any(w in text for w in HOUSE_EXTERNAL) or HOUSE_EXTERNAL_EN.search(_en(text))):
            requested = [k for k in requested if k != "ramp"]  # 바깥 램프는 아래에서 attach_to 로 붙인다
        # 장식은 장식 영역이 있는 템플릿에만. 그런 템플릿이 허용 목록에 없으면(어항) 계약에 decor 필드도 없다 (spec._item_union)
        decor_field = any(k in DECOR_TEMPLATES for k in allowed)
        decor = _find_decor(text) if decor_field else None

        items: list[dict] = []
        # attach_to 도 집·램프가 모두 있는 묶음(케이지)의 계약에만 있다
        attach_field = all(k in allowed for k in ATTACH_TEMPLATES)
        if req.previous is not None:
            items = json.loads(req.previous.model_dump_json())["items"]
            for it in items:  # 저장된 버전은 모든 템플릿 계약으로 읽어 decor·attach_to 가 null 로 들어 있다
                if not decor_field:
                    it.pop("decor", None)
                if not attach_field:
                    it["placement"].pop("attach_to", None)
        # 직전 설계에 이 종이 만들 수 없는 구조물이 있으면(규칙 파일이 바뀐 경우) 실제 LLM 처럼 빼고 알린다
        dropped = [it["template"] for it in items if it["template"] not in allowed]
        items = [it for it in items if it["template"] in allowed]
        not_allowed = list(dict.fromkeys([k for k in requested if k in registry and k not in allowed] + dropped))
        if not_allowed:
            names = ", ".join(names_of[k] for k in not_allowed)
            species = req.habitat.species_name_ko
            notes.append(f"Left out because they can't be made for {catalog().translate(species).lower()}: {names}"
                         if en else f"{species}에는 만들 수 없는 구조물이라 제외했습니다: {names}")
        requested = [k for k in requested if k in registry and k in allowed]

        # 어항: 동굴 출입구 개수를 말하는 말(앞뒤·front and back)은 위치 요청이 아니다
        zone = _find_zone(_without_door_phrases(text) if is_aquarium(req) else text)
        grouped = _grouped(text)
        factor = _scale_factor(text)

        if req.previous is not None:
            low = _en(text)
            if (any(w in text for w in REMOVE) or REMOVE_EN.search(low)) and requested:
                items = [it for it in items if it["template"] not in requested]
                requested = []
            elif any(w in text for w in ADD) or ADD_EN.search(low):
                pass  # 아래에서 requested 를 새로 추가
            else:
                # 이미 있는 템플릿은 수정 대상, 없는 템플릿만 새로 추가
                existing = {it["template"] for it in items}
                targets = [k for k in requested if k in existing] or [it["template"] for it in items]
                for it in items:
                    if it["template"] in targets:
                        t = registry[it["template"]]
                        it["params"] = _apply_numbers(t.key, text, _scaled(t, it["params"], factor),
                                                      aquarium=is_aquarium(req))
                        if zone:
                            it["placement"]["zone"] = zone
                        if grouped:
                            it["placement"]["group"] = "g1"
                        if decor and it["template"] in DECOR_TEMPLATES:
                            it["decor"] = decor
                requested = [k for k in requested if k not in existing]
        elif not requested:
            requested = [default_key]
            if default_key == "hideout":
                notes.append("No specific structure was mentioned, so I designed one standard hideout." if en
                             else "구체적인 구조물 언급이 없어 기본 은신처 1개로 설계했습니다.")
            else:
                notes.append(f"No specific structure was mentioned, so I designed one standard "
                             f"{TEMPLATE_NAMES_EN[default_key].lower()}." if en
                             else f"구체적인 구조물 언급이 없어 기본 {TEMPLATE_NAMES_KO[default_key]} 1개로 설계했습니다.")

        for key in requested:
            t = registry[key]
            params = _apply_numbers(key, text, _scaled(t, t.default_params(ctx).model_dump(), factor),
                                    aquarium=is_aquarium(req))
            items.append({
                "template": key,
                "params": params,
                "placement": {
                    "zone": zone or ("left" if grouped else "auto"),
                    "group": "g1" if grouped else None,
                    "rotation": None,
                    **({"attach_to": None} if attach_field else {}),
                },
                **({"decor": decor if key in DECOR_TEMPLATES else None} if decor_field else {}),
                "reason_ko": self._reason_en(req, key) if en else self._reason_ko(req, key),
            })

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
        names = ", ".join(names_of.get(it["template"], it["template"]) for it in items)
        summary = (f"[Dev mock interpreter] Read your request by keywords and designed: {names}." if en
                   else f"[개발용 모의 해석기] 요구사항을 키워드로 해석해 {names}을(를) 설계했습니다.")
        spec_json = json.dumps({
            "summary_ko": summary,
            "items": items,
            "notes_ko": notes,
        }, ensure_ascii=False)
        # 실제 LLM 과 같은 계약: 이 종에 만들 수 있는 템플릿만 받는다
        return InterpretResult(spec=parse_spec(spec_json, allowed or None), provider=self.name, attempts=1)
