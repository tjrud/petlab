"""Anthropic API 해석기.

구조화 출력(output_config.format = json_schema)으로 응답을 DesignSpec 스키마에 맞추고,
pydantic 으로 다시 엄격하게 검증한다(허용 범위 등 API 스키마가 표현하지 못하는 제약 포함).
검증에 실패하면 오류 내용을 대화에 덧붙여 재시도하고, 그래도 실패하면 LLMSchemaError 를 낸다.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import anthropic
from pydantic import ValidationError

from app.llm.base import (
    InterpretRequest,
    InterpretResult,
    LLMConfigError,
    LLMRefusalError,
    LLMSchemaError,
    LLMUnavailableError,
)
from app.llm.prompts import SYSTEM_PROMPT, build_retry_message, build_user_message
from app.llm.spec import api_schema, parse_spec

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
SDK_MAX_RETRIES = 1        # 연결 오류·429·5xx 는 SDK 가 1회 재시도. 스키마 위반 재시도는 interpret() 가 담당
MIN_ATTEMPT_BUDGET_S = 15  # 남은 시간이 이보다 적으면 새 시도를 시작하지 않는다


def format_validation_errors(e: ValidationError | json.JSONDecodeError, limit: int = 12) -> str:
    if isinstance(e, json.JSONDecodeError):
        return f"- JSON 파싱 실패: {e.msg} (위치 {e.pos})"
    lines = []
    for err in e.errors(include_url=False)[:limit]:
        loc = ".".join(str(p) for p in err["loc"])
        lines.append(f"- {loc}: {err['msg']} (입력값: {err.get('input')!r})")
    return "\n".join(lines)


class AnthropicInterpreter:
    name = "anthropic"

    def __init__(
        self,
        client: Any,
        model: str,
        max_retries: int = 2,
        timeout_s: float = 60.0,
        deadline_s: float = 240.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not model:
            raise LLMConfigError(
                "AI 설계 기능 설정이 완료되지 않았습니다. 관리자에게 문의해 주세요.",
                "ANTHROPIC_MODEL 환경변수가 설정되지 않았습니다.",
            )
        self.client = client
        self.model = model
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        # 요청 전체(모든 재시도 포함)의 LLM 시간 상한. 배포 플랫폼의 요청 한도(Vercel Hobby 300초)보다 작아야
        # 시간 초과 시 플랫폼 504 대신 사용자 안내 메시지를 돌려줄 수 있다.
        self.deadline_s = deadline_s
        self._clock = clock

    @classmethod
    def from_settings(
        cls, api_key: str, model: str | None, max_retries: int, timeout_s: float, deadline_s: float = 240.0
    ) -> "AnthropicInterpreter":
        client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=SDK_MAX_RETRIES)
        return cls(client, model or "", max_retries, timeout_s=timeout_s, deadline_s=deadline_s)

    def _call(self, messages: list[dict], timeout_s: float) -> Any:
        try:
            return self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=messages,
                output_config={"format": {"type": "json_schema", "schema": api_schema()}},
                timeout=timeout_s,
            )
        except anthropic.AuthenticationError as e:
            raise LLMConfigError("AI 설계 기능 인증에 실패했습니다. 관리자에게 문의해 주세요.", str(e)) from e
        except anthropic.RateLimitError as e:
            raise LLMUnavailableError("요청이 많아 AI 설계가 잠시 지연되고 있어요. 잠시 후 다시 시도해 주세요.", str(e)) from e
        except anthropic.APIStatusError as e:
            if e.status_code == 400:
                raise LLMConfigError("AI 설계 요청 형식에 문제가 있습니다. 관리자에게 문의해 주세요.", str(e)) from e
            raise LLMUnavailableError("AI 설계 서버가 응답하지 않아요. 잠시 후 다시 시도해 주세요.", str(e)) from e
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            raise LLMUnavailableError("AI 설계 서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.", str(e)) from e

    def interpret(self, req: InterpretRequest) -> InterpretResult:
        messages: list[dict] = [{"role": "user", "content": build_user_message(req)}]
        last_errors = ""
        attempts = 0
        deadline = self._clock() + self.deadline_s
        for attempt in range(1, self.max_retries + 2):
            remaining = deadline - self._clock()
            if remaining < MIN_ATTEMPT_BUDGET_S:
                log.warning("LLM 시간 상한(%ss) 도달 — %d회 시도 후 중단", self.deadline_s, attempts)
                if attempts == 0:
                    raise LLMUnavailableError("AI 설계 시간이 너무 오래 걸려요. 잠시 후 다시 시도해 주세요.", "deadline")
                break
            attempts = attempt
            # SDK 재시도(1회)까지 포함해도 남은 시간을 넘지 않도록 시도당 타임아웃을 나눈다
            per_try = min(self.timeout_s, remaining / (SDK_MAX_RETRIES + 1))
            resp = self._call(messages, per_try)
            if resp.stop_reason == "refusal":
                raise LLMRefusalError(
                    "요청하신 내용으로는 설계를 진행할 수 없어요. 케이지 구조물에 관한 요구사항으로 다시 입력해 주세요.",
                    f"refusal: {getattr(resp, 'stop_details', None)}",
                )
            text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
            try:
                spec = parse_spec(text)
                return InterpretResult(spec=spec, provider=self.name, attempts=attempts)
            except (ValidationError, json.JSONDecodeError) as e:
                last_errors = format_validation_errors(e)
                if resp.stop_reason == "max_tokens":
                    last_errors = "- 출력이 길이 한도에서 잘렸습니다. 더 간결하게 출력하세요.\n" + last_errors
                log.warning("LLM 출력 스키마 위반 (시도 %d): %s", attempt, last_errors)
                # 응답 블록을 그대로 덧붙이고(사고 블록 보존) 오류를 알려 재시도한다.
                messages = messages + [
                    {"role": "assistant", "content": resp.content},
                    {"role": "user", "content": build_retry_message(last_errors)},
                ]
        raise LLMSchemaError(
            "요구사항을 설계로 바꾸는 데 실패했어요. 표현을 조금 바꾸거나 더 구체적으로 적어 다시 시도해 주세요.",
            f"{attempts}회 시도 모두 스키마 검증 실패:\n{last_errors}",
        )
