"""해석기(Interpreter) 공용 인터페이스와 오류."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from app.domain import Cage
from app.rules.loader import SizeRules


@dataclass(frozen=True)
class HabitatInfo:
    species: str
    species_name_ko: str
    size: str
    count: int
    cage: Cage


@dataclass(frozen=True)
class InterpretRequest:
    prompt: str
    habitat: HabitatInfo
    size_rules: SizeRules
    min_wall_mm: float
    previous: BaseModel | None = None  # 수정 시 직전 버전의 DesignSpec


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
