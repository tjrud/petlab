"""개발·테스트용 모의 해석기 (키워드 기반).

ANTHROPIC_API_KEY 없이 전체 흐름을 개발·테스트하기 위한 것이다. 실제 서비스용이 아니다.
출력은 실제 LLM 과 같은 DesignSpec 계약을 따르고, 같은 검증(parse_spec)을 거친다.
"""

from __future__ import annotations

import json
import re

from app.i18n import catalog
from app.llm.base import InterpretRequest, InterpretResult
from app.llm.spec import MAX_ITEMS, parse_spec
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
TEMPLATE_NAMES_KO = {"hideout": "은신처", "tunnel": "터널", "ramp": "램프/계단", "sand_bath": "모래목욕통", "house": "집"}
# 집 부품 키워드
HOUSE_TWO_FLOORS = ("2층", "이층", "복층")
HOUSE_EXTERNAL = ("바깥 램프", "외부 램프", "바깥 경사로", "외부 경사로", "밖에 램프", "밖에 경사로")
HOUSE_PITCHED = ("경사 지붕", "뾰족 지붕", "박공")
HOUSE_ROUNDED = ("둥근 지붕", "아치 지붕")
HOUSE_PORT = ("터널 연결", "터널이 붙는", "터널을 붙")
HOUSE_FLOOR = ("바닥판",)

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
                     "house": "House"}
HOUSE_TWO_FLOORS_EN = re.compile(r"\b(?:two[ -]?stor(?:y|ey|ies)|2[ -]?stor(?:y|ey)|second floor|upper floor|lofts?)\b")
HOUSE_EXTERNAL_EN = re.compile(r"\b(?:outside|external|outer|exterior) (?:ramp|stairs?|slope)\b")
HOUSE_PITCHED_EN = re.compile(r"\b(?:pitched|gabled?|peaked) roofs?\b")
HOUSE_ROUNDED_EN = re.compile(r"\b(?:rounded|arched|round) roofs?\b")
HOUSE_PORT_EN = re.compile(r"\btunnel (?:port|connection|connector)\b")
HOUSE_FLOOR_EN = re.compile(r"\bfloor plate\b")

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
VENTS_EN = (re.compile(_NUM_EN + r"\s*(?:air[ -]?|ventilation |vent )?(?:vents?|holes?)\b"),
            re.compile(r"\b(?:vents?|ventilation holes?|air ?holes?)\b[^\d]{0,8}?(\d+)\b(?!\s*(?:mm|cm|\.\d))"))
_DOOR_EN = r"(?:entrances?|entry|entries|doors?|doorways?|openings?)"
ENTRANCE_EN = (re.compile(r"\b" + _DOOR_EN + r"\b[^\d]{0,10}(\d+(?:\.\d+)?)\s*(mm|cm)\b"),
               re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm)\b[a-z\s-]{0,12}?\b" + _DOOR_EN + r"\b"))


def _num(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBER_WORDS[word]


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


def _find_templates(text: str) -> list[str]:
    found = []
    # "집 모양 터널" 의 "집" 은 은신처가 아니라 터널 단면 모양이다 (같은 길이로 바꿔 위치는 그대로)
    if "터널" in text:
        text = text.replace("집 모양", "＿ 모양").replace("집모양", "＿모양")
    low = _en(text)
    if TEMPLATE_KEYWORDS_EN["tunnel"].search(low):
        low = HOUSE_SHAPE_EN.sub(lambda mm: "_" * len(mm.group(0)), low)
    for key, words in TEMPLATE_KEYWORDS.items():
        positions = [text.find(w) for w in words if w in text]
        m = TEMPLATE_KEYWORDS_EN[key].search(low)
        if m:
            positions.append(m.start())
        if positions:
            found.append((min(positions), key))
    keys = [k for _, k in sorted(found)]
    if "house" in keys:
        # "2층 집" 의 "집"·"house with windows" 의 "house" 는 은신처가 아니라 조립형 집이다
        keys = [k for k in keys if k != "hideout"]
    return keys


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


def _apply_numbers(key: str, text: str, params: dict) -> dict:
    out = dict(params)
    low = _en(text)
    if key == "tunnel":
        for shape, words in TUNNEL_SHAPES_KO:
            if any(w in text for w in words):
                out["shape"] = shape
                break
        else:
            for shape, rx in TUNNEL_SHAPES_EN:
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
        cat = catalog()  # 종·크기 이름은 규칙 파일의 한국어 이름을 카탈로그로 바꾼다
        pet = f"{cat.translate(req.size_rules.display_name)} {cat.translate(req.habitat.species_name_ko).lower()}"
        return f"Found '{TEMPLATE_NAMES_EN[key]}' in your request and used the standard values for a {pet}."

    def interpret(self, req: InterpretRequest) -> InterpretResult:
        text = req.prompt
        en = req.language == "en"
        names_of = TEMPLATE_NAMES_EN if en else TEMPLATE_NAMES_KO
        registry = {t.key: t for t in all_templates()}
        ctx = RuleContext(req.size_rules, req.min_wall_mm, req.habitat.count)
        notes: list[str] = []

        requested = _find_templates(text)
        unsupported = [k for k in requested if k not in registry]
        if unsupported:
            names = ", ".join(names_of[k] for k in unsupported)
            notes.append(f"Left out because they aren't supported yet: {names}" if en
                         else f"아직 지원하지 않는 구조물이라 제외했습니다: {names}")
        requested = [k for k in requested if k in registry]
        if "house" in requested and (any(w in text for w in HOUSE_EXTERNAL) or HOUSE_EXTERNAL_EN.search(_en(text))):
            requested = [k for k in requested if k != "ramp"]  # 바깥 램프는 아래에서 attach_to 로 붙인다

        zone = _find_zone(text)
        grouped = _grouped(text)
        factor = _scale_factor(text)

        items: list[dict] = []
        if req.previous is not None:
            items = json.loads(req.previous.model_dump_json())["items"]
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
                        it["params"] = _apply_numbers(t.key, text, _scaled(t, it["params"], factor))
                        if zone:
                            it["placement"]["zone"] = zone
                        if grouped:
                            it["placement"]["group"] = "g1"
                requested = [k for k in requested if k not in existing]
        elif not requested:
            requested = ["hideout"]
            notes.append("No specific structure was mentioned, so I designed one standard hideout." if en
                         else "구체적인 구조물 언급이 없어 기본 은신처 1개로 설계했습니다.")

        for key in requested:
            t = registry[key]
            params = _apply_numbers(key, text, _scaled(t, t.default_params(ctx).model_dump(), factor))
            items.append({
                "template": key,
                "params": params,
                "placement": {
                    "zone": zone or ("left" if grouped else "auto"),
                    "group": "g1" if grouped else None,
                    "rotation": None,
                    "attach_to": None,
                },
                "reason_ko": self._reason_en(req, key) if en else
                             f"요구사항에서 '{TEMPLATE_NAMES_KO[key]}'을(를) 찾아 {req.habitat.species_name_ko} "
                             f"{req.size_rules.display_name} 기준값으로 구성했습니다.",
            })

        # 2층 집에 바깥 램프: 램프 항목을 더하고 attach_to 로 잇는다 (램프 높이 = 2층 바닥 높이)
        for idx, it in enumerate(items):
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
            t = registry["hideout"]
            items.append({
                "template": "hideout", "params": t.default_params(ctx).model_dump(),
                "placement": {"zone": "auto", "group": None, "rotation": None, "attach_to": None},
                "reason_ko": "Every structure was removed, so I kept the standard hideout." if en
                             else "구조물이 모두 제외되어 기본 은신처를 남겼습니다.",
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
        return InterpretResult(spec=parse_spec(spec_json), provider=self.name, attempts=1)
