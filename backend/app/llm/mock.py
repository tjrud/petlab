"""개발·테스트용 모의 해석기 (키워드 기반).

ANTHROPIC_API_KEY 없이 전체 흐름을 개발·테스트하기 위한 것이다. 실제 서비스용이 아니다.
출력은 실제 LLM 과 같은 DesignSpec 계약을 따르고, 같은 검증(parse_spec)을 거친다.
"""

from __future__ import annotations

import json
import re

from app.llm.base import InterpretRequest, InterpretResult
from app.llm.spec import MAX_ITEMS, parse_spec
from app.templates.base import RuleContext
from app.templates.registry import all_templates
from app.validation.autofix import field_bounds

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
    ("back_left", ("왼쪽 뒤", "뒤쪽 왼", "왼쪽 구석", "구석")),
    ("back_right", ("오른쪽 뒤", "뒤쪽 오른", "오른쪽 구석")),
    ("left", ("왼쪽", "좌측")),
    ("right", ("오른쪽", "우측")),
    ("center", ("가운데", "중앙")),
    ("front", ("앞쪽", "앞에")),
    ("back", ("뒤쪽", "안쪽", "뒤에")),
]
GROUP_WORDS = ("몰아", "모아", "붙여", "한쪽", "한 쪽", "한곳", "한 곳", "나란히")
BIGGER = ("크게", "넓게", "넉넉", "큰")
SMALLER = ("작게", "아담", "좁게", "작은")
REMOVE = ("빼", "삭제", "없애", "제거")
ADD = ("추가", "더 넣", "하나 더")


def _find_templates(text: str) -> list[str]:
    found = []
    for key, words in TEMPLATE_KEYWORDS.items():
        positions = [text.find(w) for w in words if w in text]
        if positions:
            found.append((min(positions), key))
    return [k for _, k in sorted(found)]


def _find_zone(text: str) -> str | None:
    for zone, words in ZONE_KEYWORDS:
        if any(w in text for w in words):
            return zone
    return None


def _scale_factor(text: str) -> float:
    if any(w in text for w in BIGGER):
        return 1.2
    if any(w in text for w in SMALLER):
        return 0.85
    return 1.0


def _scaled(template, params: dict, factor: float) -> dict:
    out = dict(params)
    for f in template.size_fields:
        lo, hi = field_bounds(template.Params, f)
        v = out[f] * factor
        if lo is not None:
            v = max(v, lo)
        if hi is not None:
            v = min(v, hi)
        out[f] = round(v, 1)
    return out


def _apply_numbers(key: str, text: str, params: dict) -> dict:
    out = dict(params)
    if key == "hideout":
        m = re.search(r"환기구\s*(\d+)\s*개", text)
        if m:
            out["vent_count"] = int(m.group(1))
        m = re.search(r"출입구[^\d]{0,10}(\d+(?:\.\d+)?)\s*(mm|cm)", text)
        if m:
            v = float(m.group(1)) * (10 if m.group(2) == "cm" else 1)
            out["entrance_diameter_mm"] = v
    return out


class MockInterpreter:
    name = "mock"

    def interpret(self, req: InterpretRequest) -> InterpretResult:
        text = req.prompt
        registry = {t.key: t for t in all_templates()}
        ctx = RuleContext(req.size_rules, req.min_wall_mm)
        notes: list[str] = []

        requested = _find_templates(text)
        unsupported = [k for k in requested if k not in registry]
        if unsupported:
            names = ", ".join(TEMPLATE_NAMES_KO[k] for k in unsupported)
            notes.append(f"아직 지원하지 않는 구조물이라 제외했습니다: {names}")
        requested = [k for k in requested if k in registry]

        zone = _find_zone(text)
        grouped = any(w in text for w in GROUP_WORDS)
        factor = _scale_factor(text)

        items: list[dict] = []
        if req.previous is not None:
            items = json.loads(req.previous.model_dump_json())["items"]
            if any(w in text for w in REMOVE) and requested:
                items = [it for it in items if it["template"] not in requested]
                requested = []
            elif any(w in text for w in ADD):
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
            notes.append("구체적인 구조물 언급이 없어 기본 은신처 1개로 설계했습니다.")

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
                "reason_ko": f"요구사항에서 '{TEMPLATE_NAMES_KO[key]}'을(를) 찾아 {req.habitat.species_name_ko} "
                             f"{req.size_rules.display_name} 기준값으로 구성했습니다.",
            })

        if not items:
            t = registry["hideout"]
            items.append({
                "template": "hideout", "params": t.default_params(ctx).model_dump(),
                "placement": {"zone": "auto", "group": None, "rotation": None},
                "reason_ko": "구조물이 모두 제외되어 기본 은신처를 남겼습니다.",
            })
        items = items[:MAX_ITEMS]
        names = ", ".join(TEMPLATE_NAMES_KO.get(it["template"], it["template"]) for it in items)
        spec_json = json.dumps({
            "summary_ko": f"[개발용 모의 해석기] 요구사항을 키워드로 해석해 {names}을(를) 설계했습니다.",
            "items": items,
            "notes_ko": notes,
        }, ensure_ascii=False)
        return InterpretResult(spec=parse_spec(spec_json), provider=self.name, attempts=1)
