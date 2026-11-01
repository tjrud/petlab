"""관리자 인증.

사이트(화면)는 누구나 열 수 있지만, 설계·내보내기 등 API 는 관리자 로그인 후에만 쓸 수 있다.
- 관리자 계정: 환경변수 ADMIN_USERNAME / ADMIN_PASSWORD
  (ADMIN_PASSWORD 가 없으면 인증이 꺼진다 — 로컬 개발용. AUTH_REQUIRED=1 이면 대신 API 를 막는다)
- 세션: HMAC-SHA256 으로 서명한 토큰을 HttpOnly 쿠키로 보낸다.
  서명 키는 SESSION_SECRET(필수)과 관리자 비밀번호로 만든다 → 둘 중 하나를 바꾸면 기존 세션이 모두 무효
- 설정이 불완전하면(비밀값 누락·짧음) 인증을 끄지 않고 503 으로 막는다 (fail closed)
- 로그인 반복 실패는 IP 별로 잠시 막는다 (인스턴스 메모리 기준)
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import logging
import threading
import time
from collections import OrderedDict, deque

from fastapi import Request

from app.config import Settings

log = logging.getLogger(__name__)

COOKIE_NAME = "kkomul_session"
MAX_TOKEN_LEN = 1024


class AuthRequiredError(RuntimeError):
    """관리자 로그인이 필요한 API 를 로그인 없이 호출했을 때 (→ 401)."""

    message_ko = "관리자 로그인이 필요해요."


class AuthUnavailableError(RuntimeError):
    """관리자 인증 설정이 불완전해 API 를 막고 있을 때 (→ 503)."""

    message_ko = "관리자 인증 설정이 끝나지 않아 지금은 사용할 수 없어요. 운영자에게 알려 주세요."


# ── 세션 토큰 ───────────────────────────────────────────────


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def signing_key(settings: Settings) -> bytes:
    """세션 서명 키 = HMAC(SESSION_SECRET, 비밀번호 해시).

    SESSION_SECRET 이 없으면 만들지 않는다: 비밀번호만으로 유도한 키는 쿠키 하나로 비밀번호를
    오프라인 대입할 수 있게 만든다. 비밀번호를 섞는 이유는 비밀번호 교체만으로 기존 세션을 끊기 위해서다."""
    if settings.auth_mode != "enabled":
        raise AuthUnavailableError()
    secret = settings.session_secret.get_secret_value().encode()  # type: ignore[union-attr]
    password = settings.admin_password.get_secret_value().encode()  # type: ignore[union-attr]
    return hmac.new(secret, b"kkomul-session-v1:" + hashlib.sha256(password).digest(), hashlib.sha256).digest()


def _sign(body: str, key: bytes) -> str:
    return _b64(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())


def issue_token(username: str, key: bytes, ttl_s: float, now: float | None = None) -> str:
    now = time.time() if now is None else now
    payload = {"sub": username, "iat": int(now), "exp": int(now + ttl_s)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(body, key)}"


def verify_token(token: str | None, key: bytes, now: float | None = None) -> str | None:
    """유효한 토큰이면 사용자 이름, 아니면 None (서명 불일치·만료·형식 오류). 어떤 입력에도 예외를 내지 않는다."""
    if not token or len(token) > MAX_TOKEN_LEN or not token.isascii() or token.count(".") != 1:
        return None
    body, sig = token.split(".")
    try:
        if not hmac.compare_digest(sig.encode("ascii"), _sign(body, key).encode("ascii")):
            return None
        payload = json.loads(_unb64(body))
        sub, exp = payload["sub"], float(payload["exp"])
    except (ValueError, KeyError, TypeError, binascii.Error):
        return None
    now = time.time() if now is None else now
    if exp < now or not isinstance(sub, str):
        return None
    return sub


def check_credentials(settings: Settings, username: str, password: str) -> bool:
    if settings.auth_mode != "enabled":
        return False
    expected_password = settings.admin_password.get_secret_value()  # type: ignore[union-attr]
    # 두 값 모두 상수 시간으로 비교한다 (어느 쪽이 틀렸는지 시간으로 드러나지 않게)
    user_ok = hmac.compare_digest(username.encode(), settings.admin_username.encode())
    pass_ok = hmac.compare_digest(password.encode(), expected_password.encode())
    return user_ok and pass_ok


def cookie_secure(settings: Settings, request: Request) -> bool:
    return settings.cookie_secure if settings.cookie_secure is not None else request.url.scheme == "https"


# ── 로그인 시도 제한 ────────────────────────────────────────


def client_key(settings: Settings, request: Request) -> str:
    """로그인 시도 제한용 클라이언트 식별자. IPv6 는 /64 단위로 묶는다 (주소를 바꿔 가며 우회하지 못하게)."""
    raw = ""
    if settings.client_ip_header:
        raw = request.headers.get(settings.client_ip_header, "").split(",")[0].strip()
    if not raw and request.client:
        raw = request.client.host
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return raw[:64] or "unknown"
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


class LoginRateLimiter:
    """키(IP) 별로 window_s 동안 max_failures 번 넘게 틀리면 잠시 막는다 (인스턴스 메모리 기준).

    기록하는 키 수는 max_keys 로 제한한다 (오래된 키부터 버림 → 메모리가 끝없이 늘지 않게)."""

    def __init__(self, max_failures: int = 10, window_s: float = 900.0, max_keys: int = 10_000):
        self.max_failures = max_failures
        self.window_s = window_s
        self.max_keys = max_keys
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> int:
        q = self._failures.get(key)
        if q is None:
            return 0
        while q and q[0] < now - self.window_s:
            q.popleft()
        if not q:
            del self._failures[key]
            return 0
        return len(q)

    def blocked(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            return self._prune(key, now) >= self.max_failures

    def record_failure(self, key: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._prune(key, now)
            q = self._failures.setdefault(key, deque())
            q.append(now)
            self._failures.move_to_end(key)
            while len(self._failures) > self.max_keys:
                self._failures.popitem(last=False)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def __len__(self) -> int:
        return len(self._failures)


# ── FastAPI 의존성 ──────────────────────────────────────────


def current_admin(request: Request) -> str | None:
    """로그인한 관리자 이름 (인증이 꺼져 있거나 설정 오류면 None)."""
    settings: Settings = request.app.state.settings
    if settings.auth_mode != "enabled":
        return None
    user = verify_token(request.cookies.get(COOKIE_NAME), signing_key(settings))
    if user is None or not hmac.compare_digest(user.encode(), settings.admin_username.encode()):
        return None
    return user


def require_admin(request: Request) -> None:
    """관리자만 쓸 수 있는 API 에 붙이는 의존성. 인증이 꺼져 있으면 통과하고, 설정 오류면 막는다."""
    settings: Settings = request.app.state.settings
    mode = settings.auth_mode
    if mode == "disabled":
        return
    if mode == "misconfigured":
        raise AuthUnavailableError()
    if current_admin(request) is None:
        raise AuthRequiredError()
