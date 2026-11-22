"""LLM 출력 계약 (DesignSpec).

LLM 은 형상을 만들지 않는다. 이 스키마로
  - 어떤 템플릿을 몇 개 쓸지
  - 각 템플릿의 파라미터 값
  - 배치 힌트(zone/group/rotation)와 설명
  - 부품끼리 붙이는 조립 항목(template "assembly"): 부품(parts)과 어느 부품의 어느 면에 붙이는지(connections)
만 낸다. 템플릿 레지스트리에서 스키마를 자동 생성하므로 템플릿을 추가하면 계약에도 반영된다.
종마다 만들 수 있는 템플릿이 다르므로(케이지: 은신처·터널·램프·모래목욕통, 어항: 물속 동굴·터널) 모델·스키마는
템플릿 키 묶음마다 따로 만들어 캐시한다.

조립 항목의 결합 방식·자식 연결 지점·맞물리는 치수는 LLM 이 적지 않는다. 조립 해석기(app/modules/compose)가
연결 표준(템플릿의 role·attach_order·연결 지점)으로 정한다. 여기서는 나무 구조(app/modules/structure.tree_problems)와
역할로 바로 알 수 있는 잘못(받침에 다른 부품을 붙이기, 터널 끝에 터널 등)만 막아 재시도 고리로 돌려보낸다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from app.domain import PlacementHint, Rotation, Zone
from app.modules import structure
from app.modules.structure import (
    MAX_PARTS,
    MIN_PARTS,
    AssemblyRequest,
    At,
    PartRequest,
    tree_problems,
)
from app.services.engine import ItemSpec
from app.templates.base import Side, Template
from app.templates.decor import DecorSpec
from app.templates.registry import all_templates, primitives

MAX_ITEMS = 8
# 조립 항목의 template 값 (템플릿 레지스트리의 키가 아니다)
ASSEMBLY_KEY = "assembly"
# 조립 항목의 기준(첫) 부품이 될 수 있는 역할. 이 역할의 템플릿이 하나라도 있는 묶음에만 조립 항목을 둔다 (어항에는 없다)
HOST_ROLES = ("host", "room_host")


class AttachTo(BaseModel):
    """다른 항목의 한 면에 맞대어 놓는 힌트 (2층 집의 바깥 램프: 램프 꼭대기가 착지판에 닿게)."""

    model_config = ConfigDict(extra="forbid")

    item_index: int = Field(ge=0, lt=MAX_ITEMS, description="붙일 대상 항목의 items 배열 인덱스 (0부터)")
    side: Side = Field(description="대상 항목의 어느 면에 붙일지 (집의 floors.exit_side 와 같게)")


# 배치 힌트 (zone·group·rotation). attach_to 를 쓸 구조물(집·램프)이 없는 묶음(어항)의 계약에 쓴다.
# 문서 문자열은 스키마 설명으로 LLM 에게 보이므로 두지 않는다 (케이지 계약을 main 과 같게, 어항 계약에 램프 말이 없게)
class LLMZonePlacement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone: Zone = Field(
        description=(
            "놓을 영역. left=왼쪽 벽, right=오른쪽 벽, front=앞쪽(관찰 면), back=뒤쪽, center=가운데, "
            "front_left 등은 모서리, auto=특별한 요청 없음"
        )
    )
    group: str | None = Field(
        description="함께 몰아서 붙여 놓을 항목끼리 같은 그룹 이름(예: 'g1'). 없으면 null"
    )
    rotation: Rotation | None = Field(
        description="회전(도). 출입구 방향을 특별히 요청한 경우만 지정하고, 보통은 null (배치기가 자동 결정)"
    )

    def to_hint(self) -> PlacementHint:
        attach_to = getattr(self, "attach_to", None)
        attach = (attach_to.item_index, attach_to.side) if attach_to is not None else None
        return PlacementHint(zone=self.zone, group=self.group, rotation=self.rotation, attach_to=attach)


# 배치 힌트 + attach_to (2층 집의 바깥 램프)
class LLMPlacement(LLMZonePlacement):
    attach_to: AttachTo | None = Field(
        default=None,
        description="다른 항목에 맞대어 놓기. 2층 집(house, floors.climb=external_ramp)의 바깥 램프(ramp)에만 "
                    "{item_index: 집 항목 인덱스, side: 집의 floors.exit_side} 로 지정하고, 그 밖에는 null",
    )


# attach_to 는 2층 집(house)의 바깥 램프(ramp)를 잇는 힌트라 두 템플릿이 모두 있는 묶음(케이지)에만 둔다
ATTACH_TEMPLATES = ("house", "ramp")


def supports_decor(template) -> bool:
    """장식 영역을 내는 템플릿인지 (Template.decor_zones 를 덮어쓴 템플릿: 은신처·집)."""
    return type(template).decor_zones is not Template.decor_zones


@lru_cache
def _item_model(template, decor: bool, attach: bool = True) -> type[BaseModel]:
    fields: dict[str, Any] = dict(
        template=(Literal[template.key], Field(description=f"{template.display_name_ko}: {template.description_ko}")),
        params=(template.Params, ...),
        placement=(LLMPlacement if attach else LLMZonePlacement, ...),
    )
    if decor:
        fields["decor"] = (DecorSpec | None, Field(  # type: ignore[valid-type]
            default=None,
            description="장식 (안전과 무관한 바깥 벽·지붕 윗면에만). 무늬(pattern) 또는 글귀 각인(text) 중 하나. "
                        "이름 새기기·무늬 요청이 없으면 null. 은신처(hideout)·집(house)에서만 쓸 수 있다",
        ))
    fields["reason_ko"] = (str, Field(description="이 구조물과 값을 고른 이유 (응답 언어로 한두 문장, 지정이 없으면 한국어)"))
    return create_model(
        f"{template.Params.__name__.removesuffix('Params')}Item",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def template_keys(templates: Iterable[str] | None = None) -> tuple[str, ...]:
    """쓸 수 있는 기본 부품 템플릿 키를 레지스트리 순서로 정리한다 (캐시 열쇠). None 이면 등록된 모든 기본 부품.

    종마다 만들 수 있는 템플릿(규칙 파일 species.<종>.templates)만 계약에 넣을 때 쓴다.
    순서·중복이 달라도 같은 집합이면 같은 모델·스키마를 쓴다. 모르는 키나 빈 목록은 ValueError.
    레지스트리에 남아 있는 고정 조립 모듈(app/modules/library)의 키는 받되 계약에 넣지 않는다: 부품을 고르고
    잇는 일은 조립 항목(template "assembly")이 맡는다."""
    prim = primitives()
    # 부품 전용(창문 등)은 LLM 이 고르지 않는다
    registered = [t.key for t in all_templates() if t.standalone and t.key in prim]
    if templates is None:
        return tuple(registered)
    wanted = set(templates)
    unknown = sorted(wanted - {t.key for t in all_templates()})
    if unknown:
        raise ValueError(f"unknown template keys: {unknown}")
    out = tuple(k for k in registered if k in wanted)
    if not out:
        raise ValueError("no templates allowed")
    return out


def assembly_enabled(keys: Iterable[str]) -> bool:
    """이 템플릿 묶음에 조립 항목을 둘지: 기준 부품이 될 수 있는 템플릿(은신처·집·모래목욕통)이 하나라도 있으면."""
    prim = primitives()
    return any(prim[k].role in HOST_ROLES for k in keys if k in prim)


def composable_keys(keys: Iterable[str]) -> tuple[str, ...]:
    """조립 항목의 부품으로 쓸 수 있는 템플릿 키 (keys 순서)."""
    prim = primitives()
    return tuple(k for k in keys if k in prim and prim[k].composable)


# ── 조립 항목 (부품 + 연결) ─────────────────────────────────


class MissingPart(BaseModel):
    """카탈로그에 없어 만들지 못한 부품 (지금은 저장만 한다)."""

    model_config = ConfigDict(extra="forbid")

    name_ko: str = Field(description="없는 부품 이름 (응답 언어로 짧게, 예: 쳇바퀴)")
    purpose_ko: str = Field(description="보호자가 그 부품으로 하려던 것 (응답 언어로 한 문장)")


class Connection(BaseModel):
    """조립 항목의 연결: part 를 to 의 at 면에 붙인다."""

    model_config = ConfigDict(extra="forbid")

    part: str = Field(description="붙일 부품 id (기준 부품 = parts 의 첫 부품은 part 로 쓰지 않는다)")
    to: str = Field(description="붙는 대상 부품 id (기준 부품이나 이미 붙인 부품)")
    at: At = Field(description="to 의 어느 면에 붙이는지. front·back·left·right = 기준 부품(첫 부품)에서 본 면, "
                               "free_end = 터널의 남은 끝 (터널에 방을 이을 때), auto = 서버가 첫 빈 면을 고른다")

    def to_request(self) -> structure.Connection:
        return structure.Connection(part=self.part, to=self.to, at=self.at)


def _names(roles: tuple[str, ...]) -> str:
    return "·".join(t.display_name_ko for t in primitives().values() if t.role in roles)


def connection_problems(parts: list[tuple[str, str]], connections: list[Connection]) -> list[str]:
    """조립 항목의 부품 (id, 템플릿 key) 목록과 연결이 잘못된 곳 (문구 목록, 없으면 빈 목록).

    나무 구조(structure.tree_problems)와 연결 표준의 역할로 바로 알 수 있는 잘못만 본다. 실제 연결 지점·결합 방식은
    조립 해석기가 정하고, 거기서 막히는 경우(빈 면이 없음 등)는 해석기가 검증 오류로 알린다."""
    out = tree_problems([pid for pid, _ in parts], [(c.part, c.to) for c in connections])
    if out:
        return out
    prim = primitives()
    tmpl = {pid: prim[key] for pid, key in parts if key in prim}
    root = parts[0][0]
    has_parent = {c.part for c in connections}
    ends_used: dict[str, int] = {}
    for c in connections:
        parent, child = tmpl.get(c.to), tmpl.get(c.part)
        if parent is None or child is None:
            continue
        where = f"{c.part} → {c.to}"
        if parent.role not in (*HOST_ROLES, "connector"):
            out.append(f"{where}: {parent.display_name_ko}에는 다른 부품을 붙일 수 없습니다. "
                       f"붙일 대상(to)은 {_names(HOST_ROLES)} 같은 기준 구조물이나 {_names(('connector',))}입니다")
            continue
        if not child.attach_order:
            out.append(f"{where}: {child.display_name_ko}은(는) 다른 부품에 붙일 수 없어 기준 부품(parts 의 첫 부품)으로만 "
                       "씁니다")
            continue
        if parent.role == "connector":
            if child.role == "connector":
                out.append(f"{where}: {parent.display_name_ko} 끝에 {child.display_name_ko}을(를) 바로 이을 수 없습니다 "
                           "(아직 지원하지 않습니다)")
            elif "passage" not in child.attach_order:
                out.append(f"{where}: {parent.display_name_ko} 끝에는 {_names(('room_host',))} 같은 방만 이을 수 "
                           f"있습니다. {child.display_name_ko}은(는) 기준 구조물 옆면에 붙입니다")
            elif c.at not in ("free_end", "auto"):
                out.append(f"{where}: {parent.display_name_ko}에 이을 때는 at 을 free_end 로 적습니다 (지금 {c.at})")
            ends_used[c.to] = ends_used.get(c.to, 0) + 1
        elif c.at == "free_end":
            out.append(f"{where}: free_end 는 {_names(('connector',))}에 이을 때만 씁니다. "
                       f"{parent.display_name_ko}에는 front·back·left·right·auto 중 하나를 적습니다")
    for pid, used in ends_used.items():
        ends = len(tmpl[pid].attach_order.get("passage", ()))
        free = ends - (1 if pid in has_parent and pid != root else 0)
        if used > free:
            out.append(f"{pid}: {tmpl[pid].display_name_ko}의 남은 끝은 {free}개인데 {used}개를 이었습니다")
    return out


class _AssemblyItemBase(BaseModel):
    """조립 항목 (부품 묶음마다 parts 의 부품 모델이 달라 create_model 로 만든다)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check_tree(self) -> _AssemblyItemBase:
        problems = connection_problems([(p.id, p.template) for p in self.parts],  # type: ignore[attr-defined]
                                       list(self.connections))  # type: ignore[attr-defined]
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def to_request(self) -> AssemblyRequest:
        """엔진 입력 (structure.AssemblyRequest)."""
        return AssemblyRequest(
            parts=[PartRequest(id=p.id, template=p.template, params=p.params.model_dump())
                   for p in self.parts],  # type: ignore[attr-defined]
            connections=[c.to_request() for c in self.connections],  # type: ignore[attr-defined]
            name_ko=self.name_ko,  # type: ignore[attr-defined]
        )


@lru_cache
def _part_model(template) -> type[BaseModel]:
    """조립 항목의 부품 하나: {id, template: 그 템플릿 key, params: 그 템플릿 Params} (Params 정의는 일반 항목과 함께 쓴다)."""
    return create_model(
        f"{template.Params.__name__.removesuffix('Params')}Part",
        __config__=ConfigDict(extra="forbid"),
        id=(str, Field(description="부품 id: 조립 항목 안에서 겹치지 않는 짧은 영문 소문자·숫자·밑줄 "
                                   "(소문자로 시작, 예: hide, bowl, bottle, tube, hide2)")),
        template=(Literal[template.key], Field(description=template.display_name_ko)),
        params=(template.Params, ...),
    )


@lru_cache
def _assembly_model(keys: tuple[str, ...], attach: bool) -> type[BaseModel]:
    by_key = primitives()
    parts = tuple(_part_model(by_key[k]) for k in composable_keys(keys))
    part = parts[0] if len(parts) == 1 else Annotated[Union[parts], Field(discriminator="template")]  # type: ignore[valid-type]
    return create_model(
        "AssemblyItem",
        __base__=_AssemblyItemBase,
        template=(Literal[ASSEMBLY_KEY], Field(description="부품 여러 개를 서로 붙여 하나로 쓰는 조립 구조물 "
                                                          "(은신처 옆면에 밥그릇 받침, 터널로 이은 은신처 등)")),
        name_ko=(str, Field(description="조립 구조물 이름 (응답 언어로 짧게)")),
        parts=(list[part], Field(description=f"부품 {MIN_PARTS}~{MAX_PARTS}개. 첫 부품이 기준 부품({_names(HOST_ROLES)})이고 "  # type: ignore[valid-type]
                                             "connections 의 front·back·left·right 는 이 부품에서 본 면이다")),
        connections=(list[Connection], Field(description="기준 부품을 뺀 부품마다 한 번씩: part 를 to 의 at 면에 붙인다. "
                                                         "결합 방식·맞물리는 치수는 서버가 정한다")),
        placement=(LLMPlacement if attach else LLMZonePlacement, ...),
        reason_ko=(str, Field(description="이 구성과 값을 고른 이유 (응답 언어로 한두 문장, 지정이 없으면 한국어)")),
    )


@lru_cache
def _item_union(keys: tuple[str, ...]) -> Any:
    by_key = {t.key: t for t in all_templates()}
    # 장식(decor) 필드는 장식 영역이 있는 템플릿(은신처·집)이 하나라도 있는 묶음에만 둔다. 케이지 묶음은 예전처럼 모든 항목에
    # decor 가 있고(없는 템플릿은 엔진이 장식을 빼고 경고), 어항 묶음(물속 동굴·터널)에는 decor 가 아예 없다:
    # 물속 동굴·터널에는 장식 면이 없고, 물속의 파인 홈에는 이끼·찌꺼기가 낀다
    decor = any(supports_decor(by_key[k]) for k in keys)
    attach = all(k in keys for k in ATTACH_TEMPLATES)
    models = tuple(_item_model(by_key[k], decor, attach) for k in keys)
    if assembly_enabled(keys):
        prim = primitives()
        models += (_assembly_model(tuple(k for k in keys if k in prim), attach),)
    if len(models) == 1:
        return models[0]
    return Annotated[Union[models], Field(discriminator="template")]  # type: ignore[valid-type]


def item_union(templates: Iterable[str] | None = None) -> Any:
    return _item_union(template_keys(templates))


@lru_cache
def _design_spec_model(keys: tuple[str, ...]) -> type[BaseModel]:
    return create_model(
        "DesignSpec",
        __config__=ConfigDict(extra="forbid"),
        summary_ko=(str, Field(description="설계 요약 (보호자에게 보여줄 2~4문장, 응답 언어로. 지정이 없으면 한국어)")),
        items=(list[_item_union(keys)], Field(min_length=1, max_length=MAX_ITEMS,  # type: ignore[valid-type]
                                              description=f"구조물 목록 (1~{MAX_ITEMS}개)")),
        notes_ko=(list[str], Field(description="주의사항·추가 안내 (응답 언어로, 없으면 빈 배열)")),
        # 옛 출력·저장된 명세에는 없다 (구조화 출력 스키마에서는 필수)
        missing_parts=(list[MissingPart], Field(
            default_factory=list,
            description="사용 가능한 템플릿에 없어 만들지 못한 부품 (notes_ko 에도 한 줄로 알린다). 없으면 빈 배열")),
    )


def _legacy_module_keys(templates: Iterable[str] | None) -> tuple[str, ...]:
    """레지스트리에 아직 남은 고정 조립 모듈 중 templates 에 든 키 (None: 모두). 옮겨 가는 동안 모의 해석기가 내는 모듈
    항목을 읽기만 한다 (LLM 스키마·카탈로그에는 넣지 않는다). 레지스트리에서 모듈을 빼면 늘 빈 튜플이다."""
    prim = primitives()
    wanted = None if templates is None else set(templates)
    return tuple(t.key for t in all_templates()
                 if t.key not in prim and t.standalone and (wanted is None or t.key in wanted))


def design_spec_model(templates: Iterable[str] | None = None) -> type[BaseModel]:
    """DesignSpec 모델 (검증용). templates 를 주면 그 템플릿만 받는다 (None: 등록된 모든 템플릿 — 저장된 버전 읽기용)."""
    templates = None if templates is None else tuple(templates)
    return _design_spec_model(template_keys(templates) + _legacy_module_keys(templates))


def parse_spec(text: str, templates: Iterable[str] | None = None) -> BaseModel:
    """LLM 출력 JSON 을 검증한다. 실패 시 pydantic.ValidationError.

    templates: 이 종에 만들 수 있는 템플릿 키 (InterpretRequest.allowed_templates). 다른 템플릿은 스키마 위반이다.
    None 이면 등록된 모든 템플릿 (저장된 버전을 다시 읽을 때)."""
    return design_spec_model(templates).model_validate_json(text)


def to_item_specs(spec: BaseModel) -> list[ItemSpec]:
    """엔진 입력. 조립 항목은 template "assembly", params = {부품 id: 그 부품 파라미터}, assembly = 부품·연결 요청."""
    out: list[ItemSpec] = []
    for it in spec.items:  # type: ignore[attr-defined]
        hint = it.placement.to_hint()
        if it.template == ASSEMBLY_KEY:
            out.append(ItemSpec(template=ASSEMBLY_KEY, params={p.id: p.params.model_dump() for p in it.parts},
                                hint=hint, assembly=it.to_request()))
            continue
        out.append(ItemSpec(template=it.template, params=it.params.model_dump(), hint=hint,
                            decor=it.decor.model_dump(mode="json") if getattr(it, "decor", None) is not None else None))
    return out


# ── Anthropic 구조화 출력용 JSON Schema ─────────────────────────
# 구조화 출력은 minimum/maximum, minLength, 배열 길이 제약, oneOf 등을 지원하지 않는다.
# 범위는 설명(description)에 적어 모델에 알리고, 실제 검증은 위 pydantic 모델이 엄격하게 한다.

_UNSUPPORTED = {
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "minItems", "maxItems", "default", "discriminator", "title", "pattern",
}


def _range_text(node: dict) -> str:
    lo = node.get("minimum", node.get("exclusiveMinimum"))
    hi = node.get("maximum", node.get("exclusiveMaximum"))
    if lo is None and hi is None:
        return ""
    return f" (허용 범위: {lo if lo is not None else ''}~{hi if hi is not None else ''})"


def _sanitize(node: Any) -> Any:
    if isinstance(node, list):
        return [_sanitize(n) for n in node]
    if not isinstance(node, dict):
        return node
    node = dict(node)
    rng = _range_text(node)
    if rng:
        node["description"] = (node.get("description", "") + rng).strip()
    if "oneOf" in node:
        node["anyOf"] = node.pop("oneOf")
    for k in _UNSUPPORTED:
        node.pop(k, None)
    out = {}
    for k, v in node.items():
        if k in ("properties", "$defs") and isinstance(v, dict):
            # 속성·정의 이름은 스키마 키워드가 아니다 ("pattern" 이라는 속성을 지우지 않게) → 값만 정리한다
            out[k] = {name: _sanitize(sub) for name, sub in v.items()}
        else:
            out[k] = _sanitize(v)
    if out.get("type") == "object" and "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out["properties"].keys())  # 모든 값을 LLM 이 명시적으로 고르게 한다
    return out


@lru_cache
def _api_schema_cached(keys: tuple[str, ...]) -> str:
    return json.dumps(_sanitize(_design_spec_model(keys).model_json_schema()), ensure_ascii=False)


def api_schema(templates: Iterable[str] | None = None) -> dict:
    """구조화 출력용 JSON Schema. templates 를 주면 그 템플릿만 담는다 (None: 등록된 모든 템플릿).

    호출할 때마다 새 dict 를 돌려준다 (호출 측이 바꿔도 캐시 문자열은 그대로)."""
    return json.loads(_api_schema_cached(template_keys(templates)))
