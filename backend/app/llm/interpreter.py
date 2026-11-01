"""설정에 따라 해석기를 고른다."""

from __future__ import annotations

from app.config import Settings
from app.llm.anthropic_client import AnthropicInterpreter
from app.llm.base import Interpreter, LLMConfigError
from app.llm.mock import MockInterpreter


def make_interpreter(settings: Settings) -> Interpreter:
    provider = settings.resolved_llm_provider
    if provider == "mock":
        return MockInterpreter()
    if not settings.anthropic_api_key:
        raise LLMConfigError(
            "AI 설계 기능 설정이 완료되지 않았습니다. 관리자에게 문의해 주세요.",
            "LLM_PROVIDER=anthropic 이지만 ANTHROPIC_API_KEY 가 없습니다.",
        )
    return AnthropicInterpreter.from_settings(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.anthropic_model,
        max_retries=settings.llm_max_retries,
        timeout_s=settings.llm_timeout_s,
        deadline_s=settings.llm_deadline_s,
    )
