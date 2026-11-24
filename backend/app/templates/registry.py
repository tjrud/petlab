"""템플릿 레지스트리. 여기에 등록된 템플릿만 LLM 스키마·형상 생성에 쓰인다.

등록되는 것은 부품 템플릿이다: 코드로 만든 부품(지금 순서 그대로) 다음에 부품 라이브러리(app/library)의 게시된 DSL 부품
(app.library.template.load_library, key 순; 활성·폐기·차단 모두. 폐기·차단은 새 설계에 내놓지 않을 뿐 다시 만들기·검증에는
남는다). 라이브러리 부품은 늘 코드 부품 뒤에 온다. 라이브러리 파일이 색인과 맞지 않으면 import 할 때 멈춘다 (fail fast).

부품 여럿을 이은 자유 조립 항목(template "assembly")은 요청마다 조립 해석기(app/modules/compose)가 구조를 정하고,
그 구조로 만든 템플릿(app/modules/composed.ComposedTemplate)을 쓴다.
저장된 항목은 template_for 로 템플릿을 얻는다 (조립 항목이면 저장된 구조로, 해석기를 다시 돌리지 않는다).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from app.library.template import load_library
from app.templates.base import Template
from app.templates.bottle_stand import BottleStandTemplate
from app.templates.bowl_holder import BowlHolderTemplate
from app.templates.cave import CaveTemplate
from app.templates.hideout import HideoutTemplate
from app.templates.house import HouseTemplate
from app.templates.ramp import RampTemplate
from app.templates.sand_bath import SandBathTemplate
from app.templates.tunnel import TunnelTemplate

# 자유 조립 항목의 템플릿 키 (레지스트리에는 없다: 구조가 요청마다 다르다)
ASSEMBLY_KEY = "assembly"

_CODE_PRIMITIVES: dict[str, Template] = {
    t.key: t
    for t in (
        HideoutTemplate(),
        TunnelTemplate(),
        RampTemplate(),
        SandBathTemplate(),
        HouseTemplate(),
        CaveTemplate(),
        BowlHolderTemplate(),
        BottleStandTemplate(),
    )
}

# 코드 부품 다음에 라이브러리 부품 (조립 해석기는 터널을 key 로 찾으므로 순서에 기대지 않는다)
_PRIMITIVES: dict[str, Template] = {**_CODE_PRIMITIVES, **load_library()}

_TEMPLATES: dict[str, Template] = dict(_PRIMITIVES)

# overlay 가 비우는 app.llm.spec 의 lru_cache 함수 (템플릿 인스턴스·key 목록으로 기억한다).
# tests/test_library_template.py 가 이 목록이 그 모듈의 lru_cache 함수 전부와 같은지 확인한다
SPEC_CACHES: tuple[str, ...] = (
    "_item_model", "_part_model", "_assembly_model", "_item_union", "_design_spec_model", "_api_schema_cached",
)


def get_template(key: str) -> Template:
    try:
        return _TEMPLATES[key]
    except KeyError as e:
        raise KeyError(f"알 수 없는 템플릿입니다: {key}") from e


def all_templates() -> list[Template]:
    return list(_TEMPLATES.values())


def primitives() -> dict[str, Template]:
    """부품 템플릿 (코드 부품, 그다음 라이브러리 부품)."""
    return dict(_PRIMITIVES)


def template_for(it: Mapping[str, Any]) -> Template:
    """저장된 항목(DesignVersion.items 의 항목 또는 effective_spec 의 항목)의 템플릿.

    "assembly" 키(저장된 ResolvedAssembly)가 있으면 그 구조의 조립 항목 템플릿(같은 구조면 같은 인스턴스),
    없으면 template 키의 등록 템플릿. 알 수 없으면 KeyError, 저장된 구조가 잘못되었으면 ValueError."""
    raw = it.get("assembly")
    if raw is not None:
        from app.modules.compose import composed_template
        from app.modules.structure import ResolvedAssembly

        resolved = ResolvedAssembly.from_stored(raw)
        return composed_template(resolved.canonical(), it.get("name_ko"))
    return get_template(it["template"])


def code_keys() -> tuple[str, ...]:
    """코드로 만든 부품의 key (등록 순서)."""
    return tuple(_CODE_PRIMITIVES)


def _clear_caches() -> None:
    """등록 템플릿으로 기억한 것을 비운다: 조립 항목 템플릿(compose.composed_template)과 LLM 스키마 모델들.
    순환 import 를 피해 여기서 불러온다."""
    from app.llm import spec
    from app.modules import compose

    compose.composed_template.cache_clear()
    for name in SPEC_CACHES:
        getattr(spec, name).cache_clear()


@contextmanager
def overlay(extra: Mapping[str, Template]) -> Iterator[None]:
    """Temporarily register draft templates (verifier and tests only; never in the server).

    초안 부품을 잠시 등록한다 (검증기·시험 전용, 서버에서는 쓰지 않는다). 이미 있는 key 와 겹치면 ValueError.
    들어갈 때와 나올 때 기억(_clear_caches)을 비워, 같은 key 의 다른 초안이 기억된 모델·조립 템플릿과 섞이지 않게 한다."""
    clash = set(extra) & set(_TEMPLATES)
    if clash:
        raise ValueError(f"already registered: {sorted(clash)}")
    _PRIMITIVES.update(extra)
    _TEMPLATES.update(extra)
    _clear_caches()
    try:
        yield
    finally:
        for k in extra:
            _PRIMITIVES.pop(k, None)
            _TEMPLATES.pop(k, None)
        _clear_caches()
