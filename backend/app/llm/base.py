"""해석기(Interpreter) 공용 인터페이스와 오류."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from app.rules.loader import SizeRules
from app.templates.keys import TEMPLATE_MODULES

if TYPE_CHECKING:
    from app.domain import Cage


@dataclass(frozen=True)
class HabitatInfo:
    species: str
    species_name_ko: str
    size: str
    count: int
    # 어항(habitat="aquarium")이면 cage 는 수조 안쪽 가로·세로와 물 깊이(바닥재 위~수면)
    cage: Cage
    habitat: str = "cage"  # cage / aquarium (규칙 파일 species.<종>.habitat)


@dataclass(frozen=True)
class InterpretRequest:
    prompt: str
    habitat: HabitatInfo
    size_rules: SizeRules
    min_wall_mm: float
    previous: BaseModel | None = None  # 수정 시 직전 버전의 DesignSpec
    # summary_ko·reason_ko·notes_ko 를 쓸 언어 ("ko"·"en"). 필드 이름은 언어와 상관없이 그대로다
    language: str = "ko"
    # 이 종에 만들 수 있는 템플릿 키 (규칙 파일 species.<종>.templates). 기본값은 등록된 모든 템플릿 (옛 호출·테스트용)
    allowed_templates: tuple[str, ...] = field(default_factory=lambda: tuple(TEMPLATE_MODULES))


@dataclass(frozen=True)
class InterpretResult:
    spec: BaseModel
    provider: str
    attempts: int


class LLMError(RuntimeError):
    """사용자에게 안내할 수 있는 해석 오류. user_message_ko 를 그대로 보여준다."""

    status_code = 502

    def __init__(self, user_message_ko: str, detail: str = ""):
        super().__init__(detail or user_message_ko)
        self.user_message_ko = user_message_ko
        self.detail = detail


class LLMSchemaError(LLMError):
    status_code = 422


class LLMRefusalError(LLMError):
    status_code = 422


class LLMUnavailableError(LLMError):
    status_code = 503


class LLMConfigError(LLMError):
    status_code = 500


class Interpreter(Protocol):
    name: str

    def interpret(self, req: InterpretRequest) -> InterpretResult: ...
