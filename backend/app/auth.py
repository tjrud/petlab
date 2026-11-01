"""관리자 인증.

사이트(화면)는 누구나 열 수 있지만, 설계·내보내기 등 API 는 관리자 로그인 후에만 쓸 수 있다.
- 관리자 계정: 환경변수 ADMIN_USERNAME / ADMIN_PASSWORD (ADMIN_PASSWORD 가 없으면 인증이 꺼진다 — 로컬 개발용)
- 세션: HMAC-SHA256 으로 서명한 토큰을 HttpOnly 쿠키로 보낸다 (서명 키 SESSION_SECRET)
- 로그인 반복 실패는 IP 별로 잠시 막는다 (인스턴스 메모리 기준)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from collections import deque

from fastapi import Request

from app.config import Settings

log = logging.getLogger(__name__)

COOKIE_NAME = "kkomul_session"


class AuthRequiredError(RuntimeError):
    """관리자 로그인이 필요한 API 를 로그인 없이 호출했을 때 (→ 401)."""

    message_ko = "관리자 로그인이 필요해요."


# ── 세션 토큰 ───────────────────────────────────────────────


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def signing_key(settings: Settings) -> bytes:
    """세션 서명 키. SESSION_SECRET 이 없으면 관리자 비밀번호에서 유도한다
    (모든 인스턴스에서 같은 값이고, 비밀번호를 바꾸면 기존 세션이 무효가 된다)."""
    if settings.session_secret and settings.session_secret.get_secret_value():
        return settings.session_secret.get_secret_value().encode()
    password = settings.admin_password.get_secret_value() if settings.admin_password else ""
    return hashlib.sha256(b"kkomul-session-v1:" + password.encode()).digest()


def _sign(body: str, key: bytes) -> str:
    return _b64(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())


def issue_token(username: str, key: bytes, ttl_s: float, now: float | None = None) -> str:
    now = time.time() if now is None else now
    payload = json.dumps({"sub": username, "exp": int(now + ttl_s)}, separators=(",", ":")).encode()
    body = _b64(payload)
    return f"{body}.{_sign(body, key)}"


def verify_token(token: str | None, key: bytes, now: float | None = None) -> str | None:
    """유효한 토큰이면 사용자 이름, 아니면 None (서명 불일치·만료·형식 오류)."""
    if not token or token.count(".") != 1:
        return None
    body, sig = token.split(".")
    if not hmac.compare_digest(sig, _sign(body, key)):
        return None
    try:
        payload = json.loads(_unb64(body))
        sub, exp = payload["sub"], float(payload["exp"])
    except (ValueError, KeyError, TypeError):
        return None
    now = time.time() if now is None else now
    if exp < now or not isinstance(sub, str):
        return None
    return sub


def check_credentials(settings: Settings, username: str, password: str) -> bool:
    if not settings.auth_enabled:
        return False
    expected_password = settings.admin_password.get_secret_value()  # type: ignore[union-attr]
    # 두 값 모두 상수 시간으로 비교한다 (어느 쪽이 틀렸는지 시간으로 드러나지 않게)
    user_ok = hmac.compare_digest(username.encode(), settings.admin_username.encode())
    pass_ok = hmac.compare_digest(password.encode(), expected_password.encode())
    return user_ok and pass_ok


# ── 로그인 시도 제한 ────────────────────────────────────────


class LoginRateLimiter:
    """IP 별로 window_s 동안 max_failures 번 넘게 틀리면 잠시 막는다 (인스턴스 메모리 기준)."""

    def __init__(self, max_failures: int = 10, window_s: float = 900.0):
        self.max_failures = max_failures
        self.window_s = window_s
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        q = self._failures.setdefault(key, deque())
        while q and q[0] < now - self.window_s:
            q.popleft()
        return q

    def blocked(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            return len(self._recent(key, now)) >= self.max_failures

    def record_failure(self, key: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._recent(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


# ── FastAPI 의존성 ──────────────────────────────────────────


def current_admin(request: Request) -> str | None:
    """로그인한 관리자 이름 (인증이 꺼져 있으면 None)."""
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        return None
    user = verify_token(request.cookies.get(COOKIE_NAME), signing_key(settings))
    if user is None or not hmac.compare_digest(user.encode(), settings.admin_username.encode()):
        return None
    return user


def require_admin(request: Request) -> None:
    """관리자만 쓸 수 있는 API 에 붙이는 의존성. 인증이 꺼져 있으면 통과한다."""
    settings: Settings = request.app.state.settings
    if settings.auth_enabled and current_admin(request) is None:
        raise AuthRequiredError()
