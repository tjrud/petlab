"""설정에 따라 해석기를 고른다."""

from __future__ import annotations

import threading
from collections.abc import Callable

from app.config import Settings
from app.llm.base import Interpreter, InterpretRequest, InterpretResult, LLMConfigError

_CONFIG_MESSAGE_KO = "AI 설계 기능 설정이 완료되지 않았습니다. 관리자에게 문의해 주세요."


class LazyInterpreter:
    """설정 검사는 기동 때 하고, 실제 해석기(anthropic SDK·템플릿 모듈)는 첫 설계 요청 때 만든다."""

    def __init__(self, name: str, factory: Callable[[], Interpreter]):
        self.name = name
        self._factory = factory
        self._lock = threading.Lock()
        self._real: Interpreter | None = None

    def _get(self) -> Interpreter:
        if self._real is None:
            with self._lock:
                if self._real is None:
                    self._real = self._factory()
        return self._real

    def interpret(self, req: InterpretRequest) -> InterpretResult:
        return self._get().interpret(req)


def make_interpreter(settings: Settings) -> Interpreter:
    provider = settings.resolved_llm_provider
    if provider == "mock":
        def mock() -> Interpreter:
            from app.llm.mock import MockInterpreter
            return MockInterpreter()
        return LazyInterpreter("mock", mock)
    if not settings.anthropic_api_key:
        raise LLMConfigError(_CONFIG_MESSAGE_KO, "LLM_PROVIDER=anthropic 이지만 ANTHROPIC_API_KEY 가 없습니다.")
    if not settings.anthropic_model:  # AnthropicInterpreter.__init__ 과 같은 검사를 기동 때 한다
        raise LLMConfigError(_CONFIG_MESSAGE_KO, "ANTHROPIC_MODEL 환경변수가 설정되지 않았습니다.")

    def anthropic_interp() -> Interpreter:
        from app.llm.anthropic_client import AnthropicInterpreter
        return AnthropicInterpreter.from_settings(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=settings.anthropic_model,
            max_retries=settings.llm_max_retries,
            timeout_s=settings.llm_timeout_s,
            deadline_s=settings.llm_deadline_s,
        )
    return LazyInterpreter("anthropic", anthropic_interp)
