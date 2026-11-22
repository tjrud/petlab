"""템플릿 레지스트리. 여기에 등록된 템플릿만 LLM 스키마·형상 생성에 쓰인다.

등록되는 것은 코드로 만든 부품 템플릿뿐이다. 부품 여럿을 이은 자유 조립 항목(template "assembly")은 요청마다
조립 해석기(app/modules/compose)가 구조를 정하고, 그 구조로 만든 템플릿(app/modules/composed.ComposedTemplate)을 쓴다.
저장된 항목은 template_for 로 템플릿을 얻는다 (조립 항목이면 저장된 구조로, 해석기를 다시 돌리지 않는다).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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

_PRIMITIVES: dict[str, Template] = {
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

_TEMPLATES: dict[str, Template] = dict(_PRIMITIVES)


def get_template(key: str) -> Template:
    try:
        return _TEMPLATES[key]
    except KeyError as e:
        raise KeyError(f"알 수 없는 템플릿입니다: {key}") from e


def all_templates() -> list[Template]:
    return list(_TEMPLATES.values())


def primitives() -> dict[str, Template]:
    """코드로 만든 부품 템플릿."""
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
