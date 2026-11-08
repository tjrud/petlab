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
}
TEMPLATE_NAMES_KO = {"hideout": "은신처", "tunnel": "터널", "ramp": "램프/계단", "sand_bath": "모래목욕통"}

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
}
TEMPLATE_NAMES_EN = {"hideout": "Hideout", "tunnel": "Tunnel", "ramp": "Ramp/stairs", "sand_bath": "Sand bath"}

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
STEPS_EN = re.compile(r"\b(?:stairs?|stair ?cases?|steps?)\b")
STEP_COUNT_EN = re.compile(_NUM_EN + r"[\s-]*(?:steps?|stairs?)\b")
RAMP_EN = re.compile(r"\b(?:ramps?|slopes?|sloped|inclines?)\b")
U_BEND_EN = re.compile(r"\b(?:u[ -]?(?:shaped?|turns?|bend)|uturns?)\b")
CURVE_EN = re.compile(r"\b(?:curved?|curving|curvy|bent|bends?|bendy|l[ -]?shaped?|elbow|angled)\b")
STRAIGHT_EN = re.compile(r"\bstraight\b")
VENTS_EN = (re.compile(_NUM_EN + r"\s*(?:air[ -]?|ventilation |vent )?(?:vents?|holes?)\b"),
            re.compile(r"\b(?:vents?|ventilation holes?|air ?holes?)\b[^\d]{0,8}?(\d+)\b(?!\s*(?:mm|cm|\.\d))"))
_DOOR_EN = r"(?:entrances?|entry|entries|doors?|doorways?|openings?)"
ENTRANCE_EN = (re.compile(r"\b" + _DOOR_EN + r"\b[^\d]{0,10}(\d+(?:\.\d+)?)\s*(mm|cm)\b"),
               re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm)\b[a-z\s-]{0,12}?\b" + _DOOR_EN + r"\b"))


def _num(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBER_WORDS[word]


def _en(text: str) -> str:
    return text.lower()


def _find_templates(text: str) -> list[str]:
    found = []
    low = _en(text)
    for key, words in TEMPLATE_KEYWORDS.items():
        positions = [text.find(w) for w in words if w in text]
        m = TEMPLATE_KEYWORDS_EN[key].search(low)
        if m:
            positions.append(m.start())
        if positions:
            found.append((min(positions), key))
    return [k for _, k in sorted(found)]


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
        if any(w in text for w in ("U자", "유턴")) or U_BEND_EN.search(low):
            out["bend_angle_deg"] = 180
        elif any(w in text for w in ("곡선", "구부러", "휘어", "ㄱ자", "꺾")) or CURVE_EN.search(low):
            out["bend_angle_deg"] = 90
        elif "직선" in text or STRAIGHT_EN.search(low):
            out["bend_angle_deg"] = 0
    if key == "ramp":
        if "계단" in text:
            m = re.search(r"(\d+)\s*단", text)
            out["steps"] = int(m.group(1)) if m else max(out.get("steps", 0), 3)
        elif STEPS_EN.search(low):
            m = STEP_COUNT_EN.search(low)
            out["steps"] = _num(m.group(1)) if m else max(out.get("steps", 0), 3)
        elif any(w in text for w in ("경사로", "램프", "슬로프")) or RAMP_EN.search(low):
            out["steps"] = 0
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
                },
                "reason_ko": self._reason_en(req, key) if en else
                             f"요구사항에서 '{TEMPLATE_NAMES_KO[key]}'을(를) 찾아 {req.habitat.species_name_ko} "
                             f"{req.size_rules.display_name} 기준값으로 구성했습니다.",
            })

        if not items:
            t = registry["hideout"]
            items.append({
                "template": "hideout", "params": t.default_params(ctx).model_dump(),
                "placement": {"zone": "auto", "group": None, "rotation": None},
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
