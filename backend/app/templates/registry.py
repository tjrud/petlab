"""템플릿 레지스트리. 여기에 등록된 템플릿만 LLM 스키마·형상 생성에 쓰인다."""

from __future__ import annotations

from app.templates.base import Template
from app.templates.hideout import HideoutTemplate
from app.templates.ramp import RampTemplate
from app.templates.sand_bath import SandBathTemplate
from app.templates.tunnel import TunnelTemplate

_TEMPLATES: dict[str, Template] = {
    t.key: t for t in (HideoutTemplate(), TunnelTemplate(), RampTemplate(), SandBathTemplate())
}


def get_template(key: str) -> Template:
    try:
        return _TEMPLATES[key]
    except KeyError as e:
        raise KeyError(f"알 수 없는 템플릿입니다: {key}") from e


def all_templates() -> list[Template]:
    return list(_TEMPLATES.values())
