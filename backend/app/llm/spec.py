"""LLM 출력 계약 (DesignSpec).

LLM 은 형상을 만들지 않는다. 이 스키마로
  - 어떤 템플릿을 몇 개 쓸지
  - 각 템플릿의 파라미터 값
  - 배치 힌트(zone/group/rotation)와 설명
만 낸다. 템플릿 레지스트리에서 스키마를 자동 생성하므로 템플릿을 추가하면 계약에도 반영된다.
종마다 만들 수 있는 템플릿이 다르므로(케이지: 은신처·터널·램프·모래목욕통, 어항: 물속 동굴·터널) 모델·스키마는
템플릿 키 묶음마다 따로 만들어 캐시한다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.domain import PlacementHint, Rotation, Zone
from app.services.engine import ItemSpec
from app.templates.registry import all_templates

MAX_ITEMS = 8


class LLMPlacement(BaseModel):
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
        return PlacementHint(zone=self.zone, group=self.group, rotation=self.rotation)


def _item_model(template) -> type[BaseModel]:
    return create_model(
        f"{template.Params.__name__.removesuffix('Params')}Item",
        __config__=ConfigDict(extra="forbid"),
        template=(Literal[template.key], Field(description=f"{template.display_name_ko}: {template.description_ko}")),
        params=(template.Params, ...),
        placement=(LLMPlacement, ...),
        reason_ko=(str, Field(description="이 구조물과 값을 고른 이유 (응답 언어로 한두 문장, 지정이 없으면 한국어)")),
    )


def template_keys(templates: Iterable[str] | None = None) -> tuple[str, ...]:
    """쓸 수 있는 템플릿 키를 레지스트리 순서로 정리한다 (캐시 열쇠). None 이면 등록된 모든 템플릿.

    종마다 만들 수 있는 템플릿(규칙 파일 species.<종>.templates)만 계약에 넣을 때 쓴다.
    순서·중복이 달라도 같은 집합이면 같은 모델·스키마를 쓴다. 모르는 키나 빈 목록은 ValueError."""
    registered = [t.key for t in all_templates()]
    if templates is None:
        return tuple(registered)
    wanted = set(templates)
    unknown = sorted(wanted - set(registered))
    if unknown:
        raise ValueError(f"unknown template keys: {unknown}")
    out = tuple(k for k in registered if k in wanted)
    if not out:
        raise ValueError("no templates allowed")
    return out


@lru_cache
def _item_union(keys: tuple[str, ...]) -> Any:
    by_key = {t.key: t for t in all_templates()}
    models = tuple(_item_model(by_key[k]) for k in keys)
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
    )


def design_spec_model(templates: Iterable[str] | None = None) -> type[BaseModel]:
    """DesignSpec 모델. templates 를 주면 그 템플릿만 받는다 (None: 등록된 모든 템플릿 — 저장된 버전 읽기용)."""
    return _design_spec_model(template_keys(templates))


def parse_spec(text: str, templates: Iterable[str] | None = None) -> BaseModel:
    """LLM 출력 JSON 을 검증한다. 실패 시 pydantic.ValidationError.

    templates: 이 종에 만들 수 있는 템플릿 키 (InterpretRequest.allowed_templates). 다른 템플릿은 스키마 위반이다.
    None 이면 등록된 모든 템플릿 (저장된 버전을 다시 읽을 때)."""
    return design_spec_model(templates).model_validate_json(text)


def to_item_specs(spec: BaseModel) -> list[ItemSpec]:
    return [
        ItemSpec(template=it.template, params=it.params.model_dump(), hint=it.placement.to_hint())
        for it in spec.items  # type: ignore[attr-defined]
    ]


# ── Anthropic 구조화 출력용 JSON Schema ─────────────────────────
# 구조화 출력은 minimum/maximum, minLength, 배열 길이 제약, oneOf 등을 지원하지 않는다.
# 범위는 설명(description)에 적어 모델에 알리고, 실제 검증은 위 pydantic 모델이 엄격하게 한다.

_UNSUPPORTED = {
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "minItems", "maxItems", "default", "discriminator", "title",
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
    out = {k: _sanitize(v) for k, v in node.items()}
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
