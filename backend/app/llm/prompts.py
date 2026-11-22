"""LLM 프롬프트.

시스템 프롬프트는 고정(캐시 친화적)이고, 사육 환경·종 규칙·요구사항처럼 바뀌는 값은 사용자 메시지에 넣는다.
종별 수치는 rules/species.yaml 에서 읽어 주입한다 (프롬프트에 하드코딩하지 않음).
시스템 프롬프트는 종과 상관없이 같고(케이지·어항 공통), 쓸 수 있는 템플릿과 한도는 사용자 메시지의 종별 기준이 정한다.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from typing import Literal, get_args, get_origin

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from app.i18n import catalog
from app.llm.base import InterpretRequest
from app.llm.spec import ASSEMBLY_KEY, assembly_enabled, composable_keys
from app.modules.structure import MAX_PARTS
from app.templates.base import RuleContext, Template
from app.templates.cave import PRINT_MIN_ROOF_SLOPE_DEG, CaveTemplate
from app.templates.registry import all_templates, primitives

# 조립 항목 예시 두 개 (시스템 프롬프트에 그대로 넣는다: 고정 문자열이라 캐시된다). 값은 작은 햄스터(드워프) 기준이지만
# 시스템 프롬프트는 종과 상관없어야 하므로 종 이름은 적지 않는다.
# tests/test_llm.py 가 두 예시가 지금 계약(parse_spec)을 통과하는지 확인한다
_PLACEMENT = {"zone": "auto", "group": None, "rotation": None, "attach_to": None}
_HIDE = {"width_mm": 140, "depth_mm": 120, "height_mm": 95, "entrance_diameter_mm": 60, "entrance_count": 1,
         "vent_count": 6, "vent_diameter_mm": 4, "wall_thickness_mm": 3}
FEW_SHOTS: tuple[tuple[str, dict], ...] = (
    ("은신처 오른쪽에 밥그릇 받침, 왼쪽에 물병 거치대를 달아 주세요", {
        "template": ASSEMBLY_KEY,
        "name_ko": "밥그릇과 물병이 달린 은신처",
        "parts": [
            {"id": "hide", "template": "hideout", "params": _HIDE},
            {"id": "bowl", "template": "bowl_holder",
             "params": {"bowl_diameter_mm": 90, "bowl_height_mm": 40, "clearance_mm": 1.0, "wall_thickness_mm": 3,
                        "collar_height_mm": 35}},
            {"id": "bottle", "template": "bottle_stand",
             "params": {"bottle_diameter_mm": 60, "cap_diameter_mm": 40, "spout_height_mm": 55, "spout_drop_mm": 60,
                        "holder_height_mm": 70, "base_width_mm": 110, "base_depth_mm": 110, "wall_thickness_mm": 3,
                        "clearance_mm": 1.0}},
        ],
        "connections": [
            {"part": "bowl", "to": "hide", "at": "right"},
            {"part": "bottle", "to": "hide", "at": "left"},
        ],
        "placement": _PLACEMENT,
        "reason_ko": "그릇 받침과 물병 거치대를 출입구가 없는 양옆에 붙였습니다.",
    }),
    ("은신처 두 개를 터널로 이어 주세요", {
        "template": ASSEMBLY_KEY,
        "name_ko": "터널로 이은 쌍둥이 은신처",
        "parts": [
            {"id": "hide", "template": "hideout", "params": {**_HIDE, "depth_mm": 110, "entrance_count": 2}},
            {"id": "tube", "template": "tunnel",
             "params": {"length_mm": 100, "inner_diameter_mm": 60, "bend_angle_deg": 0, "wall_thickness_mm": 3,
                        "shape": "round_arch", "path": "arc"}},
            {"id": "hide2", "template": "hideout", "params": {**_HIDE, "depth_mm": 110, "entrance_count": 2}},
        ],
        "connections": [
            {"part": "tube", "to": "hide", "at": "front"},
            {"part": "hide2", "to": "tube", "at": "free_end"},
        ],
        "placement": _PLACEMENT,
        "reason_ko": "같은 크기의 은신처 두 개를 앞 출입구끼리 곧은 터널로 이었습니다.",
    }),
)


def _few_shot_text() -> str:
    return "\n".join(f"예시 {i}. \"{prompt}\" → items 의 항목 하나:\n{json.dumps(item, ensure_ascii=False)}"
                     for i, (prompt, item) in enumerate(FEW_SHOTS, 1))


SYSTEM_PROMPT = """\
당신은 'NestForge'의 반려동물 사육장 구조물 설계 도우미입니다. 사육장은 소형 반려동물 케이지이거나 관상어·새우를 키우는 어항(수조)입니다.
보호자의 요구사항을 읽고, 검증된 파라메트릭 템플릿 중에서 구조물을 고른 뒤 각 파라미터 값을 정합니다.

역할의 경계:
- 형상(좌표, 메시, CAD 코드)을 직접 만들지 않습니다. 템플릿 선택, 파라미터 값, 배치 힌트, 설명만 정합니다.
- 배치 좌표는 별도의 배치 엔진이 계산합니다. 당신은 zone(영역)·group(함께 몰기)·rotation 힌트만 줍니다.
- 결과는 서버가 자동 검증하고 필요하면 보정하므로, 아래 종별 기준을 지키는 값을 고르면 됩니다.

설계 원칙:
- 사용자 메시지의 '사용 가능한 템플릿'에 있는 템플릿만 씁니다. 종마다 만들 수 있는 구조물과 한도가 다르며, 사용자 메시지의 사육 환경과 종별 기준이 이를 정합니다.
- 단위는 모두 mm 입니다. 각 파라미터의 허용 범위를 벗어나지 마세요.
- 종별 기준을 지키세요. 출입구·통로는 최소 크기 이상, 환기구 같은 작은 구멍은 끼임 안전 크기 이하, 벽 두께는 최소값 이상이어야 합니다.
- 사육장(케이지·어항) 내부 치수 안에 모든 구조물이 들어가야 합니다. 바닥 면적의 절반 이상은 비워 두는 것이 좋습니다. 높이는 케이지 높이(어항은 물 깊이)보다 충분히 낮아야 합니다.
- 보호자가 "한쪽에 몰아서", "모아서"처럼 따로 놓을 구조물을 가까이 두라고 말하면 해당 항목들에 같은 group 과 같은 zone 을
  주세요 (서로 끼워 붙이거나 터널로 잇는 요청은 아래 '조립'을 따릅니다).
- 위치 요청이 없으면 zone 은 "auto", rotation 은 null 로 두세요.
- 요구사항에 없는 구조물을 임의로 추가하지 마세요. 요청이 모호하면 숨을 곳 1개(케이지는 은신처, 어항은 물속 동굴)처럼 무난한 구성을 고르세요.
- 지원하지 않거나 이 종에 만들 수 없는 구조물을 요청받으면 notes_ko 에 그 사실을 적고 사용 가능한 템플릿으로만 설계하세요.
- 터널 단면 모양(shape)·휘는 모양(path)은 보호자가 말한 대로 고르고(둥근, 원통·관, 네모, 집 모양, S자 등), 말이 없으면 기본값을
  두세요. 휜 터널에 round_arch·tube·box 를 고르면 출력할 때 서포트가 필요하므로 notes_ko 에 알려 주세요.
- 2층·경사 지붕·둥근 지붕·창 요청은 house 템플릿의 부품(floors, roof, ports, windows, doors, floor)으로 표현하세요
  (house 가 사용 가능한 템플릿에 있을 때만. 없으면 위의 '만들 수 없는 구조물'처럼 다룹니다).
  단순한 은신처 요청은 hideout 을 그대로 씁니다. house 의 부품 값은 중첩 객체로 모두 채웁니다.
  집에 터널을 잇는 요청은 아래 '조립'으로 표현합니다 (터널 연결부 ports 는 서버가 냅니다).
- 2층 집에 바깥 램프를 두려면(floors.climb=external_ramp) ramp 항목을 하나 추가하고, 그 placement.attach_to 에
  {item_index: 집 항목의 인덱스, side: 집의 floors.exit_side} 를 적어 램프 꼭대기가 착지판에 닿게 하세요.
  램프 높이는 집의 2층 바닥 높이(floors.level_height_mm)와 같게 적습니다. 그 밖의 항목은 attach_to 를 null 로 둡니다.
- 이름 새기기·무늬 요청은 항목의 decor(무늬 pattern 또는 글귀 text)로 표현하고, 안전 치수(출입구·창·벽 두께 기준)는 바꾸지
  마세요. 장식은 은신처·집의 바깥 벽과 경사·둥근 지붕 윗면에만 들어가며, 파내기 각인은 벽을 깊이만큼 더 두껍게 적으면 좋습니다.
  요청이 없으면 decor 는 null 입니다. 항목에 decor 필드가 없으면(장식을 넣을 수 없는 사육 환경) notes_ko 에 그 사실을 적습니다.
- 설계 수정 요청이면 직전 설계를 바탕으로, 요청된 부분만 바꾼 전체 설계를 다시 출력하세요.
- summary_ko, reason_ko, notes_ko 는 보호자가 읽기 쉬운 한국어로 씁니다. 단, 사용자 메시지에 "응답 언어" 지시가 있으면
  그 언어로 씁니다 (필드 이름은 언어와 상관없이 그대로 둡니다). 조립 항목의 name_ko 도 같습니다.
- 사용 가능한 템플릿에 없는 부품(쳇바퀴 등)을 요청받으면 missing_parts 에 {name_ko, purpose_ko} 로 적고 notes_ko 에도
  한 줄로 알립니다. 없으면 missing_parts 는 빈 배열입니다.

조립 (사용 가능한 템플릿에 '연결' 설명이 있을 때만):
- 붙이기·달기·잇기 요청은 template "assembly" 항목 하나로 냅니다. parts 에 부품(id 는 짧은 영문 소문자: hide, bowl,
  tube, hide2 등)을, connections 에 {part, to, at} 를 기준 부품을 뺀 부품마다 한 번씩 적습니다.
- parts 의 첫 부품이 기준 부품(은신처·집·모래목욕통)입니다. at 의 front·back·left·right 는 기준 부품에서 본 면이고,
  터널에 잇는 방은 at=free_end, 어느 면이든 괜찮으면 auto 입니다.
- 결합 방식·통로 뚫기·맞물리는 치수(터널 내경과 단면 = 출입구, 붙이는 면 크기, 램프 높이, 출입구 개수)는 서버가 정하므로
  연결 관계만 적습니다. 부품마다 params 는 그 템플릿 범위 안에서 평소처럼 모두 채웁니다.
- 출입구 면에는 터널만 잇고, 그릇 받침·물병 거치대·램프는 옆면에 붙입니다. 받침·거치대·램프에는 다른 부품을 붙이지 않습니다.
- "하나 더"는 같은 값으로 같은 부품을 하나 더 넣는 것입니다.
- 따로 놓을 구조물은 지금처럼 개별 항목으로 냅니다 (붙이거나 잇는다는 말이 없으면 개별 항목).
- 위에 얹기(쌓기)는 아직 안 됩니다. 옆에 붙이거나 터널로 잇고 notes_ko 에 알려 주세요.
- 한 조립 항목의 부품은 최대 """ + str(MAX_PARTS) + """개입니다.
조립 예시 (형식을 보이는 예시 값입니다. 실제 값은 사용자 메시지의 종별 기준과 사육 환경 치수에 맞춥니다):
""" + _few_shot_text() + "\n"


def is_aquarium(req: InterpretRequest) -> bool:
    """어항 요청인지 (사육 환경 종류나 크기 구분의 어항 규칙으로 판단)."""
    return req.habitat.habitat == "aquarium" or req.size_rules.aquatic is not None


def _field_catalog(model: type[BaseModel]) -> dict:
    """모델 필드 → {설명, 범위|선택지, 기본값}. 중첩 모델(조립형 템플릿의 부품)은 재귀로 펼친다."""
    fields = {}
    for name, f in model.model_fields.items():
        ann = f.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            fields[name] = {"설명": f.description, "부품": _field_catalog(ann)}
            continue
        lo = hi = None
        for m in f.metadata:
            lo = getattr(m, "ge", lo)
            hi = getattr(m, "le", hi)
        default = f.default if f.default is not PydanticUndefined else None
        if get_origin(ann) is Literal:
            fields[name] = {"설명": f.description, "선택지": list(get_args(ann)), "기본값": default}
        elif get_origin(ann) is list:
            item = get_args(ann)[0]
            choices = list(get_args(item)) if get_origin(item) is Literal else []
            fields[name] = {"설명": f.description, "목록 선택지": choices, "기본값": default}
        else:
            fields[name] = {"설명": f.description, "범위": [lo, hi], "기본값": default}
    return fields


_SIDES = ("front", "back", "left", "right")


def _join_names(templates: Iterable[Template]) -> str:
    return "·".join(t.display_name_ko for t in templates)


def _obj(word: str) -> str:
    """목적격 조사를 붙인다 (받침이 있으면 을, 없으면 를)."""
    last = word[-1:] if word else ""
    batchim = "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 != 0
    return f"{word}{'을' if batchim else '를'}"


def _face_texts(t: Template, keys: tuple[str, ...]) -> dict[str, str]:
    """부모로서 면마다 받는 부품 (연결 지점 종류로 만든다: 기본 파라미터의 port·mount·side, open_port)."""
    prim = primitives()
    pool = [prim[k] for k in composable_keys(keys)]
    slide = [c for c in pool if "slide" in c.attach_order]
    access = [c for c in slide if c.passes_access]
    tunnels = [c for c in pool if c.role == "connector"]
    p = t.default_params()
    anchors = t.anchors(p)
    access_sides = set(t.features(p).access_sides)
    out: dict[str, str] = {}
    for side in _SIDES:
        a = anchors.get(side)
        if a is None:
            continue
        opened = None
        if a.port is None and tunnels:
            q = t.open_port(p, side)
            b = t.anchors(q).get(side) if q is not None else None
            opened = b is not None and b.port is not None
        if a.port is not None:
            text = f"출입구({_join_names(tunnels)}만)" if tunnels else "출입구"
        elif a.mount is not None:
            names = access if side in access_sides else slide
            text = f"{'출입 면' if side in access_sides else '옆면'}({_join_names(names)})" if names else ""
            if opened:
                text = f"{text} 또는 " if text else ""
                text += f"{_obj(_join_names(tunnels))} 이으면 출입구를 낸다"
        elif opened:
            text = f"벽({_obj(_join_names(tunnels))} 이으면 출입구를 낸다)"
        else:
            text = ""
        if text:
            out[side] = text
    return out


def connection_text(t: Template, keys: tuple[str, ...]) -> str | None:
    """카탈로그의 "연결" 설명 (template_metadata: role·attach_order·연결 지점 종류에서 만든다). 조립 부품이 아니면 None.

    예 (은신처): "기준 부품(parts 의 첫 부품)이 될 수 있다. front: 출입구(터널만), back/left/right: 옆면(램프/계단·그릇 받침·
    물병 거치대)…, 터널 끝에 이을 수 있다 (to=터널, at=free_end)". 면 이름은 그 부품 자신의 면이다."""
    if not t.composable:
        return None
    prim = primitives()
    pool = [prim[k] for k in composable_keys(keys)]
    tunnels = [c for c in pool if c.role == "connector"]
    rooms = [c for c in pool if c.role == "room_host" and "passage" in c.attach_order]
    parts: list[str] = []
    if t.role in ("host", "room_host"):
        faces = _face_texts(t, keys)
        grouped: dict[str, list[str]] = {}
        for side, text in faces.items():
            grouped.setdefault(text, []).append(side)
        listed = ", ".join(f"{'/'.join(sides)}: {text}" for text, sides in grouped.items())
        parts.append("기준 부품(parts 의 첫 부품)이 될 수 있다" + (f". {listed}" if listed else ""))
        if "passage" in t.attach_order and tunnels:
            parts.append(f"{_join_names(tunnels)} 끝에 이을 수 있다 (to={_join_names(tunnels)}, at=free_end)")
        elif not t.attach_order:
            parts.append("다른 부품에 붙이지 않는다 (기준 부품으로만)")
    elif t.role == "connector":
        ends = len(t.attach_order.get("passage", ()))
        parts.append(f"방의 출입구 면에 붙인다 (to=방, at=그 면). 끝은 {ends}개라 남은 끝(at=free_end)에 "
                     f"{_obj(_join_names(rooms) or '방')} 하나 이을 수 있다. 끝에 {_obj(t.display_name_ko)} 바로 잇지는 "
                     "않는다")
    elif t.role == "accessory":
        text = "기준 구조물 옆면에 붙인다 (to=기준 구조물, at=right·left·back·front·auto). 다른 부품을 붙이지 않는다"
        if t.passes_access:
            text += ". 출입 면에도 붙일 수 있다"
        if t.level_field:
            text += f". {t.level_field} 는 서버가 붙는 면 높이에 맞춘다"
        parts.append(text)
    return ". ".join(parts)


def template_catalog(allowed: Iterable[str] | None = None) -> list[dict]:
    """LLM 에게 보일 템플릿 목록 (기본 부품만). allowed 를 주면 그 템플릿만 (None: 등록된 모든 기본 부품).

    조립 항목을 쓸 수 있는 묶음(기준 부품이 될 템플릿이 있는 케이지)이면 조립 부품마다 "연결" 설명을 더한다."""
    prim = primitives()
    wanted = None if allowed is None else set(allowed)
    shown = [t for t in all_templates() if t.key in prim and (wanted is None or t.key in wanted)]
    keys = tuple(t.key for t in shown)
    compose = assembly_enabled(keys)
    out = []
    for t in shown:
        entry: dict = {"template": t.key, "이름": t.display_name_ko, "설명": t.description_ko}
        link = connection_text(t, keys) if compose else None
        if link:
            entry["연결"] = link
        entry["파라미터"] = _field_catalog(t.Params)
        out.append(entry)
    return out


def _size_rules(req: InterpretRequest, aquarium: bool) -> dict[str, object]:
    """종별 기준 표. 규칙 파일에 없는 값(None)은 줄을 넣지 않는다 (어항에는 램프·모래목욕통·터널 최대 길이가 없다)."""
    h, s = req.habitat, req.size_rules
    allowed = set(req.allowed_templates)
    rules: dict[str, object] = {
        "크기 구분": s.display_name,
        "출입구 최소 폭(mm)": s.entrance_min_diameter_mm,
        "터널 최소 내경(mm)": s.tunnel_min_inner_diameter_mm,
    }
    tmax, tmin = s.tunnel_max_length_mm, s.tunnel_min_inner_diameter_mm
    if tmax is not None:
        rules["터널 최대 길이(mm) — 이 크기 구분에서 가장 작은 개체 몸길이의 2배"] = tmax
        rules["터널 최대 휨 각도(도) — 최대 길이·최소 내경일 때 (굽힘 반경 ≥ 내경)"] = round(
            min(180.0, math.degrees(tmax / tmin)), 1)
        rules["S자 터널 한 번 휨 최대 각도(도) — 최대 길이·최소 내경일 때 (반 길이로 휨, 90° 까지)"] = round(
            min(90.0, math.degrees(0.5 * tmax / tmin)), 1)
    elif "tunnel" in allowed:
        rules["터널 최대 길이(mm)"] = ("없음 — 이 크기 구분은 터널 길이 제한이 없습니다 (터널 파라미터 설명의 '종별 최대 길이'는 "
                                 "해당하지 않음). 일반 프린터에 들어가도록 200mm 이하 권장")
    if aquarium:
        rules["끼임 안전 틈 최대(mm) — 구조물 사이·벽과의 틈은 이 값 이하이거나 몸이 통과하는 폭 이상"] = s.gap_trap.safe_max_mm
    else:
        rules["끼임 안전 틈 최대(mm) — 환기구 지름 상한"] = s.gap_trap.safe_max_mm
    rules["몸이 통과하는 최소 폭(mm)"] = s.gap_trap.passable_min_mm
    rules["최소 벽 두께(mm)"] = req.min_wall_mm
    optional = [
        ("램프 최대 경사(도)", s.max_ramp_angle_deg),
        ("오르는 구조물 최대 높이(mm)", s.max_climb_height_mm),
        ("최대 턱(단) 높이(mm)", s.max_step_height_mm),
        ("모래목욕통 최소 내부 [가로, 세로](mm)",
         list(s.sand_bath_min_inner_mm) if s.sand_bath_min_inner_mm is not None else None),
        ("모래목욕통 최소 깊이(mm)", s.sand_bath_min_depth_mm),
    ]
    rules.update({k: v for k, v in optional if v is not None})
    entrances = s.hideout_min_entrances.for_count(h.count)
    if not aquarium:
        rules["은신처 최소 출입구 개수 (이 마릿수 기준)"] = entrances
        return rules

    aq = s.aquatic
    if aq is not None:
        rules["물 깊이(mm) — 사육 환경의 높이(Z)는 바닥재 위~수면"] = h.cage.height_mm
        rules["구조물 위 최소 물 깊이(mm) — 생물이 구조물 위로 지나가고 수면에서 숨 쉴 수 있게"] = aq.structure_top_clearance_mm
        rules["구조물 최대 높이(mm) — 물 깊이 − 구조물 위 최소 물 깊이"] = round(
            h.cage.height_mm - aq.structure_top_clearance_mm, 1)
        rules["높이 ÷ 바닥 짧은 변 최대 — 출력물은 물속에서 가벼워 쉽게 넘어진다"] = aq.max_height_to_base_ratio
        if "tunnel" in allowed:
            rules["터널 높이 — 단면 모양(shape)·내경·벽 두께로 정해진다 (높이 파라미터가 따로 없다). 뾰족 아치·집 모양은 "
                  "내경 × 약 1.28 + 벽 두께 × 약 1.56, 둥근 아치·네모는 내경 + 벽 두께, 관은 내경 + 벽 두께 × 2. "
                  "구조물 최대 높이를 넘으면 내경을 줄인다"] = "단면 모양·내경·벽 두께로 정해짐"
    if "tunnel" in allowed:
        # 물속 동굴이 천장 경사를 요구하는 것과 같은 까닭: 꼭대기가 기울지 않은 천장 아래에는 공기가 넓게 남는다
        rules["어항 터널 단면(shape)"] = ("pointed_arch(기본)·house 권장 — 천장 꼭대기가 뾰족해 공기가 적게 남는다. "
                                     "round_arch·tube·box 는 천장 꼭대기가 둥글거나 평평해 공기가 더 남아 뜨기 쉬우니 "
                                     "보호자가 그 모양을 콕 집어 말할 때만 고르고 notes_ko 에 알려 주세요")
    if "cave" in allowed:
        slope = max(PRINT_MIN_ROOF_SLOPE_DEG, aq.ceiling_min_slope_deg if aq is not None else 0.0)
        rules["물속 동굴 지붕 경사 최소(도) — 안쪽 천장에 공기가 남지 않고 서포트 없이 출력되도록"] = slope
        rules["물속 동굴 꼭대기 구멍 최소 폭(mm) — 공기가 빠지는 구멍이자 몸이 끼지 않는 통과 폭"] = s.gap_trap.passable_min_mm
        rules["물속 동굴 최소 출입구 개수 (이 마릿수 기준) — 2개면 앞뒤로 뚫린 관통형"] = entrances
        # 동굴 최소 높이는 가로·세로와 꼭대기 구멍에 따라 달라진다: 얕은 수조에서 큰 동굴을 고르지 않게 알려 준다
        rules["물속 동굴 최소 높이 — 출입구 높이(폭의 약 1.28배) + 벽 두께 2배 + 지붕 높이. 지붕 높이는 "
              "(가로·세로 중 짧은 쪽 안쪽 폭 − 꼭대기 구멍 폭)에 비례하므로, 구조물 최대 높이에 맞추려면 가로·세로를 줄이거나 "
              "꼭대기 구멍을 넓힌다. 가장 작게 만든 동굴의 높이(mm)"] = CaveTemplate().min_height_mm(
            RuleContext(s, req.min_wall_mm, h.count))
    names = {t.key: t.display_name_ko for t in all_templates()}
    can = [f"{k}({names[k]})" for k in dict.fromkeys(req.allowed_templates) if k in names]
    cannot = [f"{k}({names[k]})" for k in names if k not in allowed]
    rules["만들 수 있는 구조물"] = ", ".join(can) + "만" + (f" — {', '.join(cannot)}은(는) 어항에 만들 수 없습니다"
                                                       if cannot else "")
    rules["속이 빈 닫힌 공간"] = ("금지 — 물이 돌지 않는 닫힌 빈 공간은 물을 썩게 하고 공기가 갇혀 뜨게 합니다. "
                            "템플릿 형상이 이를 보장하므로 템플릿 밖의 형상(덮개·막힌 방 등)을 제안하지 마세요")
    rules["장식(무늬·글귀 각인)"] = ("어항 구조물에는 넣지 않습니다 (물속 동굴·터널에는 장식 면이 없고, 물속의 파인 홈에는 이끼·찌꺼기가 "
                              "낍니다). 보호자가 요청하면 notes_ko 에 넣을 수 없다고 적으세요")
    # 소재 안전은 서버가 화면에 따로 보이는 출력·설치 안내(print_notes_ko, 커뮤니티 글10 과 같은 조건)가 정한다.
    # 모델이 일반 상식("PLA 는 무독성이라 안전")으로 그 안내와 어긋나는 말을 쓰지 않게 막는다
    rules[MATERIAL_RULE_KEY] = MATERIAL_RULE
    return rules


# 어항 사용자 메시지의 소재 안내 줄 (테스트가 이 줄이 들어가는지 본다)
MATERIAL_RULE_KEY = "출력 소재·코팅·접착제"
MATERIAL_RULE = (
    "단정 금지 — 서버가 화면에 출력·설치 안전 안내를 따로 보여 줍니다(어항 수질에 안전하다고 증명된 3D 출력 소재는 없다는 "
    "입장). summary_ko·reason_ko·notes_ko 에서 어떤 소재(PLA·PETG 등)가 어항에 '안전하다'·'무독성이다'·'생분해되니 괜찮다'·"
    "'물에 녹는다'고 단정하지 말고, 코팅·레진·에폭시·일반 실리콘·접착제를 권하지 마세요. 보호자가 소재·출력·세척·접착을 물으면 "
    "화면의 출력·설치 안내를 따르라고만 짧게 적으세요(응답 언어로)")


def build_user_message(req: InterpretRequest) -> str:
    h, s = req.habitat, req.size_rules
    aquarium = is_aquarium(req)
    rules = _size_rules(req, aquarium)
    if aquarium:
        habitat = {
            "종": h.species_name_ko,
            "크기": s.display_name,
            "마릿수": h.count,
            "사육 환경": "어항(수조) — 구조물은 물속 바닥재 위에 놓입니다",
            "어항 내부 치수(mm)": {"가로(X)": h.cage.width_mm, "세로(Y)": h.cage.depth_mm,
                              "물 깊이(Z) — 바닥재 위~수면": h.cage.height_mm},
        }
    else:
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
        json.dumps(template_catalog(req.allowed_templates), ensure_ascii=False, indent=2),
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
ENGLISH_TERMS_AQUARIUM = ("aquarium, tank, underwater cave, tunnel, entrance, top opening, roof slope, water depth, "
                          "substrate, plants, layout, design")


def pet_name_en(req: InterpretRequest) -> str:
    """케이지 동물의 영어 이름 (예: "Golden (Syrian) hamster").

    크기 구분의 영어 이름에 동물 이름이 들어 있으면 그대로 쓰고, 없으면 종 이름을 뒤에 붙인다."""
    cat = catalog()
    group = cat.translate(req.size_rules.display_name)
    species = cat.translate(req.habitat.species_name_ko).lower()
    return group if species in group.lower() else f"{group} {species}"


def english_instruction(req: InterpretRequest) -> str:
    """영어 페이지에서 온 요청: 설명 필드를 영어로 쓰게 한다. 시스템 프롬프트는 고정(캐시)이라 사용자 메시지에 넣는다."""
    if is_aquarium(req):
        terms = ENGLISH_TERMS_AQUARIUM
        # 어항 크기 구분의 영어 이름 (예: "Nano fish (neon and ember tetras, ...)")
        group = catalog().translate(req.size_rules.display_name)
        who = (f"The tank is set up for this size group: {group}. Refer to the animals by that group "
               "or by the species the owner names.")
    else:
        terms = ENGLISH_TERMS
        who = f"Call the pet a {pet_name_en(req)}."
    return (
        "The owner is using the English site. Write summary_ko, every reason_ko and every notes_ko entry in natural, "
        "concise US English for pet owners (friendly, not chatty). Do not write Korean in these fields. "
        "Keep every JSON field name exactly as defined (summary_ko, reason_ko, notes_ko stay as they are). "
        "The owner's request may be in English or Korean; follow it either way.\n"
        f"Preferred terms: {terms}. Use mm for sizes and ° for angles. "
        f"{who}"
    )


def build_retry_message(errors: str) -> str:
    return (
        "출력이 스키마 검증에 실패했습니다. 아래 오류를 고쳐 같은 요구사항에 대한 전체 설계 JSON 을 다시 출력하세요.\n"
        f"{errors}"
    )
