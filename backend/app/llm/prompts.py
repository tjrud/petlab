"""LLM 프롬프트.

시스템 프롬프트는 고정(캐시 친화적)이고, 사육 환경·종 규칙·요구사항처럼 바뀌는 값은 사용자 메시지에 넣는다.
종별 수치는 rules/species.yaml 에서 읽어 주입한다 (프롬프트에 하드코딩하지 않음).
"""

from __future__ import annotations

import json
import math

from app.i18n import catalog
from app.llm.base import InterpretRequest
from app.templates.registry import all_templates

SYSTEM_PROMPT = """\
당신은 'NestForge'의 소형 반려동물 케이지 구조물 설계 도우미입니다.
보호자의 요구사항을 읽고, 검증된 파라메트릭 템플릿 중에서 구조물을 고른 뒤 각 파라미터 값을 정합니다.

역할의 경계:
- 형상(좌표, 메시, CAD 코드)을 직접 만들지 않습니다. 템플릿 선택, 파라미터 값, 배치 힌트, 설명만 정합니다.
- 배치 좌표는 별도의 배치 엔진이 계산합니다. 당신은 zone(영역)·group(함께 몰기)·rotation 힌트만 줍니다.
- 결과는 서버가 자동 검증하고 필요하면 보정하므로, 아래 종별 기준을 지키는 값을 고르면 됩니다.

설계 원칙:
- 단위는 모두 mm 입니다. 각 파라미터의 허용 범위를 벗어나지 마세요.
- 종별 기준을 지키세요. 출입구·통로는 최소 크기 이상, 환기구 같은 작은 구멍은 끼임 안전 크기 이하, 벽 두께는 최소값 이상이어야 합니다.
- 케이지 내부 치수 안에 모든 구조물이 들어가야 합니다. 바닥 면적의 절반 이상은 비워 두는 것이 좋습니다. 높이는 케이지 높이보다 충분히 낮아야 합니다.
- 보호자가 "한쪽에 몰아서", "붙여서"처럼 말하면 해당 항목들에 같은 group 과 같은 zone 을 주세요.
- 위치 요청이 없으면 zone 은 "auto", rotation 은 null 로 두세요.
- 요구사항에 없는 구조물을 임의로 추가하지 마세요. 요청이 모호하면 은신처 1개처럼 무난한 구성을 고르세요.
- 지원하지 않는 구조물을 요청받으면 notes_ko 에 그 사실을 적고 가능한 템플릿으로만 설계하세요.
- 설계 수정 요청이면 직전 설계를 바탕으로, 요청된 부분만 바꾼 전체 설계를 다시 출력하세요.
- summary_ko, reason_ko, notes_ko 는 보호자가 읽기 쉬운 한국어로 씁니다. 단, 사용자 메시지에 "응답 언어" 지시가 있으면
  그 언어로 씁니다 (필드 이름은 언어와 상관없이 그대로 둡니다).
"""


def template_catalog() -> list[dict]:
    out = []
    for t in all_templates():
        fields = {}
        for name, f in t.Params.model_fields.items():
            lo = hi = None
            for m in f.metadata:
                lo = getattr(m, "ge", lo)
                hi = getattr(m, "le", hi)
            fields[name] = {"설명": f.description, "범위": [lo, hi], "기본값": f.default}
        out.append({"template": t.key, "이름": t.display_name_ko, "설명": t.description_ko, "파라미터": fields})
    return out


def build_user_message(req: InterpretRequest) -> str:
    h, s = req.habitat, req.size_rules
    rules = {
        "크기 구분": s.display_name,
        "출입구 최소 폭(mm)": s.entrance_min_diameter_mm,
        "터널 최소 내경(mm)": s.tunnel_min_inner_diameter_mm,
        "터널 최대 길이(mm) — 이 크기 구분에서 가장 작은 개체 몸길이의 2배": s.tunnel_max_length_mm,
        "터널 최대 휨 각도(도) — 최대 길이·최소 내경일 때 (굽힘 반경 ≥ 내경)": round(
            min(180.0, math.degrees(s.tunnel_max_length_mm / s.tunnel_min_inner_diameter_mm)), 1),
        "끼임 안전 틈 최대(mm) — 환기구 지름 상한": s.gap_trap.safe_max_mm,
        "몸이 통과하는 최소 폭(mm)": s.gap_trap.passable_min_mm,
        "최소 벽 두께(mm)": req.min_wall_mm,
        "램프 최대 경사(도)": s.max_ramp_angle_deg,
        "오르는 구조물 최대 높이(mm)": s.max_climb_height_mm,
        "최대 턱(단) 높이(mm)": s.max_step_height_mm,
        "모래목욕통 최소 내부 [가로, 세로](mm)": list(s.sand_bath_min_inner_mm),
        "모래목욕통 최소 깊이(mm)": s.sand_bath_min_depth_mm,
        "은신처 최소 출입구 개수 (이 마릿수 기준)": s.hideout_min_entrances.for_count(h.count),
    }
    habitat = {
        "종": h.species_name_ko,
        "크기": s.display_name,
        "마릿수": h.count,
        "케이지 내부 치수(mm)": {"가로(X)": h.cage.width_mm, "세로(Y)": h.cage.depth_mm, "높이(Z)": h.cage.height_mm},
    }
    parts = [
        "## 사육 환경",
        json.dumps(habitat, ensure_ascii=False, indent=2),
        "## 종별 기준 (반드시 지킬 것)",
        json.dumps(rules, ensure_ascii=False, indent=2),
        "## 사용 가능한 템플릿",
        json.dumps(template_catalog(), ensure_ascii=False, indent=2),
    ]
    if req.previous is not None:
        parts += [
            "## 직전 설계 (이것을 수정합니다)",
            req.previous.model_dump_json(indent=2),
            "## 수정 요청",
            req.prompt,
        ]
    else:
        parts += ["## 보호자 요구사항", req.prompt]
    if req.language == "en":
        parts += ["## 응답 언어 (Output language)", english_instruction(req)]
    parts.append("위 내용을 바탕으로 설계 JSON 을 출력하세요.")
    return "\n\n".join(parts)


# 영어 설명에 쓸 용어 (사이트 영어 화면과 같은 말)
ENGLISH_TERMS = "cage, hideout, tunnel, ramp, stairs, sand bath, wheel, bedding, food bowl, water bottle, layout, design"


def english_instruction(req: InterpretRequest) -> str:
    """영어 페이지에서 온 요청: 설명 필드를 영어로 쓰게 한다. 시스템 프롬프트는 고정(캐시)이라 사용자 메시지에 넣는다."""
    cat = catalog()
    pet = f"{cat.translate(req.size_rules.display_name)} {cat.translate(req.habitat.species_name_ko).lower()}"
    return (
        "The owner is using the English site. Write summary_ko, every reason_ko and every notes_ko entry in natural, "
        "concise US English for hamster owners (friendly, not chatty). Do not write Korean in these fields. "
        "Keep every JSON field name exactly as defined (summary_ko, reason_ko, notes_ko stay as they are). "
        "The owner's request may be in English or Korean; follow it either way.\n"
        f"Preferred terms: {ENGLISH_TERMS}. Use mm for sizes and ° for angles. "
        f"Call the pet a {pet}."
    )


def build_retry_message(errors: str) -> str:
    return (
        "출력이 스키마 검증에 실패했습니다. 아래 오류를 고쳐 같은 요구사항에 대한 전체 설계 JSON 을 다시 출력하세요.\n"
        f"{errors}"
    )
