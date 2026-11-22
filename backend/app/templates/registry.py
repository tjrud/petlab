"""템플릿 레지스트리. 여기에 등록된 템플릿만 LLM 스키마·형상 생성에 쓰인다.

기본 부품(코드 템플릿) 뒤에 모듈 라이브러리(app/modules/library/*.json)의 조립 모듈을 템플릿으로 감싸 더한다.
"""

from __future__ import annotations

from app.templates.base import Template
from app.templates.cave import CaveTemplate
from app.templates.hideout import HideoutTemplate
from app.templates.house import HouseTemplate
from app.templates.ramp import RampTemplate
from app.templates.sand_bath import SandBathTemplate
from app.templates.tunnel import TunnelTemplate

_PRIMITIVES: dict[str, Template] = {
    t.key: t
    for t in (
        HideoutTemplate(),
        TunnelTemplate(),
        RampTemplate(),
        SandBathTemplate(),
        HouseTemplate(),
        CaveTemplate(),
    )
}


def _with_modules() -> dict[str, Template]:
    from app.modules.definition import library
    from app.modules.module_template import ModuleTemplate

    out = dict(_PRIMITIVES)
    for defn in library():
        if defn.key in out:
            raise ValueError(f"모듈 key 가 다른 템플릿과 겹칩니다: {defn.key}")
        out[defn.key] = ModuleTemplate(defn, _PRIMITIVES)
    return out


_TEMPLATES: dict[str, Template] = _with_modules()


def get_template(key: str) -> Template:
    try:
        return _TEMPLATES[key]
    except KeyError as e:
        raise KeyError(f"알 수 없는 템플릿입니다: {key}") from e


def all_templates() -> list[Template]:
    return list(_TEMPLATES.values())


def primitives() -> dict[str, Template]:
    """코드로 만든 기본 부품 템플릿 (조립 모듈 제외)."""
    return dict(_PRIMITIVES)
