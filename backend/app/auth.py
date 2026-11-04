"""회원·관리자 인증.

- 회원: 회원가입(아이디·닉네임·비밀번호, scrypt 해시)으로 만든 계정. 관리자: 환경변수 ADMIN_USERNAME / ADMIN_PASSWORD
  (ADMIN_PASSWORD 가 없으면 인증이 꺼지고 모든 요청이 로컬 개발용 관리자로 처리된다. AUTH_REQUIRED=1 이면 대신 API 를 막는다)
- 세션: HMAC-SHA256 으로 서명한 토큰(sub=회원 id, ver=세션 버전)을 HttpOnly 쿠키로 보낸다.
  서명 키는 SESSION_SECRET(필수)과 관리자 비밀번호로 만든다 → 둘 중 하나를 바꾸면 모든 세션이 무효.
  회원이 비밀번호를 바꾸면 세션 버전이 올라가 그 회원의 다른 세션이 끊긴다.
- 설정이 불완전하면(비밀값 누락·짧음) 인증을 끄지 않고 503 으로 막는다 (fail closed)
- 로그인 반복 실패·회원가입은 IP 별로 제한한다 (인스턴스 메모리 기준)
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

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import Settings
from app.models import User
from app.names import nickname_key

log = logging.getLogger(__name__)

COOKIE_NAME = "kkomul_session"
MAX_TOKEN_LEN = 1024
MAX_TOKEN_LIFETIME_S = 720 * 3600 + 60  # SESSION_TTL_HOURS 상한(30일) + 시계 오차


LOCAL_USERNAME = "local"  # 인증이 꺼진 로컬 개발 환경의 가상 관리자
ADMIN_NICKNAME = "NestForge 운영팀"  # 화면에는 "관리자" 배지와 함께 보인다
_ID_RE = __import__("re").compile(r"[0-9a-f]{32}")


class AuthRequiredError(RuntimeError):
    """로그인이 필요한 API 를 로그인 없이 호출했을 때 (→ 401)."""

    message_ko = "로그인이 필요해요."


class AuthUnavailableError(RuntimeError):
    """인증 설정이 불완전해 API 를 막고 있을 때 (→ 503)."""

    message_ko = "로그인 설정이 끝나지 않아 지금은 사용할 수 없어요. 운영자에게 알려 주세요."


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


def issue_token(subject: str, key: bytes, ttl_s: float, now: float | None = None, ver: int = 1) -> str:
    now = time.time() if now is None else now
    payload = {"sub": subject, "ver": ver, "iat": int(now), "exp": int(now + ttl_s)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(body, key)}"


def verify_token(token: str | None, key: bytes, now: float | None = None) -> dict | None:
    """유효한 토큰이면 {"sub": 회원 id, "ver": 세션 버전}, 아니면 None (서명 불일치·만료·형식 오류).
    어떤 입력에도 예외를 내지 않는다."""
    if not token or len(token) > MAX_TOKEN_LEN or not token.isascii() or token.count(".") != 1:
        return None
    body, sig = token.split(".")
    try:
        if not hmac.compare_digest(sig.encode("ascii"), _sign(body, key).encode("ascii")):
            return None
        payload = json.loads(_unb64(body))
        sub, exp, ver = payload["sub"], payload["exp"], payload["ver"]
    except (ValueError, KeyError, TypeError, binascii.Error):
        return None
    # issue_token 은 항상 정수 exp·ver 를 쓴다 (NaN·Infinity·거대한 수는 거부)
    if not isinstance(sub, str) or type(exp) is not int or type(ver) is not int:
        return None
    now = time.time() if now is None else now
    if exp < now or exp > now + MAX_TOKEN_LIFETIME_S:
        return None
    return {"sub": sub, "ver": ver}


def check_admin_credentials(settings: Settings, username: str, password: str) -> bool:
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

# 계정을 여러 개 만드는 일(회원가입·설계 등 사용량 상한)은 IPv6 를 /56 단위로 묶는다
# (가정·사무실 하나가 보통 /56~/48 을 받으므로 /64 로는 주소를 바꿔 가며 우회할 수 있다)
ACCOUNT_V6_PREFIX = 56


def _raw_client_ip(settings: Settings, request: Request) -> str:
    """검사하기 전의 클라이언트 IP 문자열. CLIENT_IP_HEADER 를 설정했으면 그 헤더의 첫 값,
    비어 있으면 연결 주소(request.client.host). 둘 다 없으면 빈 문자열."""
    raw = ""
    if settings.client_ip_header:
        raw = request.headers.get(settings.client_ip_header, "").split(",")[0].strip()
    if not raw and request.client:
        raw = request.client.host
    return raw


def client_ip(settings: Settings, request: Request) -> str | None:
    """클라이언트 IP (CAPTCHA 확인에 함께 보낸다). 형식이 IP 가 아니면 None."""
    try:
        return str(ipaddress.ip_address(_raw_client_ip(settings, request)))
    except ValueError:
        return None


def usage_ip_key(settings: Settings, request: Request) -> str | None:
    """IP 별 사용량 상한의 키 (IPv6 는 /56). 플랫폼이 넣는 클라이언트 IP 헤더(CLIENT_IP_HEADER)가 없으면 None
    (프록시 주소로 모든 사람이 하나로 묶이지 않게)."""
    return client_key(settings, request, v6_prefix=ACCOUNT_V6_PREFIX) if settings.client_ip_header else None


def client_key(settings: Settings, request: Request, v6_prefix: int = 64) -> str:
    """시도 제한용 클라이언트 식별자. IPv6 는 v6_prefix 단위로 묶는다 (주소를 바꿔 가며 우회하지 못하게).
    계정을 여러 개 만드는 일(회원가입·설계 사용량)은 더 넓게(ACCOUNT_V6_PREFIX, /56) 묶는다.
    형식이 IP 가 아니면 client_ip 와 달리 None 이 아니라 그 문자열(앞 64자, 비었으면 'unknown')을 키로 쓴다."""
    raw = _raw_client_ip(settings, request)
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return raw[:64] or "unknown"
    if ip.version == 6 and ip.ipv4_mapped is not None:  # ::ffff:a.b.c.d → a.b.c.d
        ip = ip.ipv4_mapped
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/{v6_prefix}", strict=False))
    return str(ip)


class LoginRateLimiter:
    """키(IP) 별로 window_s 동안 max_failures 번 넘게 틀리면 잠시 막는다 (인스턴스 메모리 기준).

    기록하는 키 수는 max_keys 로 제한한다. 넘치면 막히지 않은 가장 오래된 키부터 버리고,
    막힌 키는 버리지 않는다 (키를 대량으로 바꿔 가며 차단을 풀지 못하게).
    fail_closed 이면 표가 막힌 키로만 가득 찼을 때 window_s 동안 새 키도 막는다 (관리자 로그인 보호).
    fail_closed 가 아니면 가장 오래된 키를 버린다 (회원가입: 누군가 표를 채워 모든 신규 가입을 막지 못하게).

    비밀번호 확인처럼 결과가 나오기까지 기다리는(await) 시도는 acquire()/release() 로 감싼다.
    진행 중인 시도를 미리 실패로 세므로, 한꺼번에 몰린 요청이 실패가 기록되기 전에 모두 통과하지 못한다."""

    def __init__(self, max_failures: int = 10, window_s: float = 900.0, max_keys: int = 10_000,
                 fail_closed: bool = True, max_inflight: int = 3):
        self.max_failures = max_failures
        self.window_s = window_s
        self.max_keys = max_keys
        self.fail_closed = fail_closed
        self.max_inflight = max_inflight
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        self._inflight: dict[str, int] = {}
        self._saturated_until = 0.0
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

    def _blocked_locked(self, key: str, now: float, pending: int = 0) -> bool:
        if self._prune(key, now) + pending >= self.max_failures:
            return True
        return key not in self._failures and now < self._saturated_until

    def blocked(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            return self._blocked_locked(key, now)

    def _record_locked(self, key: str, now: float) -> None:
        self._prune(key, now)
        q = self._failures.setdefault(key, deque())
        q.append(now)
        self._failures.move_to_end(key)
        if len(self._failures) > self.max_keys:
            self._evict(keep=key, now=now)

    def record_failure(self, key: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._record_locked(key, now)

    def hit(self, key: str, now: float | None = None) -> bool:
        """검사와 기록을 한 번에: 막혔으면 False, 아니면 시도 1회를 기록하고 True (결과와 관계없이 세는 시도용)."""
        now = time.time() if now is None else now
        with self._lock:
            if self._blocked_locked(key, now):
                return False
            self._record_locked(key, now)
            return True

    def acquire(self, key: str, now: float | None = None) -> bool:
        """시도 하나를 시작한다. 막혔거나(진행 중인 시도 포함) 동시에 진행 중인 시도가 많으면 False.
        True 이면 반드시 release() 를 불러야 한다."""
        now = time.time() if now is None else now
        with self._lock:
            pending = self._inflight.get(key, 0)
            if pending >= self.max_inflight or self._blocked_locked(key, now, pending):
                return False
            self._inflight[key] = pending + 1
            return True

    def release(self, key: str, failed: bool, now: float | None = None) -> None:
        """acquire() 로 시작한 시도를 끝낸다. failed 면 실패를 기록한다 (진행 중 표시를 지우는 것과 한 번에)."""
        now = time.time() if now is None else now
        with self._lock:
            pending = self._inflight.get(key, 0) - 1
            if pending > 0:
                self._inflight[key] = pending
            else:
                self._inflight.pop(key, None)
            if failed:
                self._record_locked(key, now)

    def _evict(self, keep: str, now: float) -> None:
        for k in list(self._failures):
            if k != keep and self._prune(k, now) < self.max_failures:
                self._failures.pop(k, None)
                if len(self._failures) <= self.max_keys:
                    return
        if not self.fail_closed:
            while len(self._failures) > self.max_keys:
                oldest = next(k for k in self._failures if k != keep)
                self._failures.pop(oldest)
            return
        # 남은 키가 모두 차단 중: 새 키 기록을 버리는 대신 새 키 전체를 잠시 막는다
        self._failures.pop(keep, None)
        self._saturated_until = now + self.window_s
        log.error("로그인 실패 기록이 가득 찼습니다 (차단된 키 %d개). 새 접속의 로그인을 잠시 막습니다.", len(self._failures))

    def __len__(self) -> int:
        return len(self._failures)


# ── 관리자·로컬 계정 행 ─────────────────────────────────────


def _insert_admin_row(db: Session, username: str, nickname: str) -> User | None:
    """관리자 행을 넣는다. 아이디·닉네임이 이미 있으면(다른 요청·인스턴스가 먼저 만든 경우 등) None."""
    user = User(username=username, nickname=nickname, nickname_key=nickname_key(nickname), role="admin",
                password_hash=None)
    db.add(user)
    try:
        db.commit()
        return user
    except IntegrityError:
        db.rollback()
        return None


def _ensure_user_row(db: Session, username: str, nickname: str) -> User:
    """관리자(또는 로컬 개발용) 계정 행을 찾거나 만든다. 비밀번호는 환경변수로만 확인하므로 해시는 비워 둔다."""
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        # 닉네임이 겹치면(ADMIN_USERNAME 을 바꿔 예전 관리자 행이 남은 경우) 아이디를 붙인 닉네임으로 만든다.
        # 동시에 여러 곳에서 만들면 한쪽은 실패하므로 매번 아이디로 다시 찾는다.
        for nick in (nickname, f"{nickname}-{username}"[:40]):
            user = _insert_admin_row(db, username, nick) or db.scalar(select(User).where(User.username == username))
            if user is not None:
                break
        if user is None:
            raise RuntimeError("관리자 계정 행을 만들 수 없습니다 (닉네임 충돌)")
    elif user.role != "admin" or user.password_hash is not None:
        # 운영자가 ADMIN_USERNAME 을 기존 회원 아이디로 바꾼 경우: 그 계정을 관리자 계정으로 넘긴다
        log.error("ADMIN_USERNAME(%s)과 같은 아이디의 회원 계정을 관리자 계정으로 전환합니다.", username)
        user.role, user.password_hash = "admin", None
        user.session_version += 1
        db.commit()
    return user


def ensure_admin_user(db: Session, settings: Settings) -> User:
    return _ensure_user_row(db, settings.admin_username, ADMIN_NICKNAME)


# ── FastAPI 의존성 ──────────────────────────────────────────


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """로그인한 회원 (없거나 세션이 무효면 None). 인증이 꺼진 로컬 개발 환경에서는 가상 관리자."""
    settings: Settings = request.app.state.settings
    mode = settings.auth_mode
    if mode == "disabled":
        user = _ensure_user_row(db, LOCAL_USERNAME, "로컬 개발자")
        db.commit()
        return user
    if mode == "misconfigured":
        return None
    claims = verify_token(request.cookies.get(COOKIE_NAME), signing_key(settings))
    if claims is None or not _ID_RE.fullmatch(claims["sub"]):
        return None
    user = db.get(User, claims["sub"])
    # 읽기 트랜잭션을 끝내 DB 연결을 풀에 돌려준다. 이 의존성과 API 함수는 서로 다른 스레드 작업으로 실행되므로,
    # 연결을 쥔 채 다음 스레드를 기다리면 동시 요청이 몰릴 때 풀과 스레드가 서로를 기다리며 멈춘다.
    db.commit()
    if user is None or user.session_version != claims["ver"]:
        return None
    # ADMIN_USERNAME 을 바꾸면 예전 관리자 행의 세션은 더 이상 관리자가 아니다
    if user.is_admin and not hmac.compare_digest(user.username.encode(), settings.admin_username.encode()):
        return None
    return user


def get_current_user(request: Request, user: User | None = Depends(get_optional_user)) -> User:
    """로그인이 필요한 API 에 붙이는 의존성 (설정 오류면 503, 로그인 안 했으면 401)."""
    if user is None:
        if request.app.state.settings.auth_mode == "misconfigured":
            raise AuthUnavailableError()
        raise AuthRequiredError()
    return user


def get_verified_user(request: Request, user: User = Depends(get_current_user)) -> User:
    """이메일 인증이 켜져 있으면 인증을 마친 회원만 (설계·글쓰기·댓글·대기 신청: 비용·스팸이 드는 기능)."""
    from app.services.email_verify import EmailUnverifiedError, needs_verification

    if needs_verification(request.app.state.settings, user):
        raise EmailUnverifiedError()
    return user
