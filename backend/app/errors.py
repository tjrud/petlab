"""API 오류 (상태 코드 + 코드 + 사용자에게 그대로 보여줄 한국어 메시지)."""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message_ko: str, code: str | None = None):
        super().__init__(message_ko)
        self.message_ko = message_ko
        if code:
            self.code = code


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class QuotaExceededError(AppError):
    status_code = 429
    code = "quota_exceeded"
