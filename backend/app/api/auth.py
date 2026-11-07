"""회원가입·로그인·로그아웃·로그인 상태."""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

from fastapi import Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, make_router
from app.auth import (
    ACCOUNT_V6_PREFIX,
    COOKIE_NAME,
    LOCAL_USERNAME,
    AuthUnavailableError,
    LoginRateLimiter,
    check_admin_credentials,
    client_ip,
    client_key,
    cookie_secure,
    ensure_admin_user,
    get_current_user,
    get_optional_user,
    issue_token,
    signing_key,
    usage_ip_key,
)
from app.captcha import CaptchaUnavailableError, check_captcha
from app.config import Settings
from app.errors import AppError, ConflictError, ForbiddenError, QuotaExceededError
from app.models import UsageEvent, User
from app.names import email_key, lookalike_key, nickname_key
from app.passwords import hash_password, needs_rehash, verify_password
from app.schemas import AuthStatusOut, CaptchaOut, ResendVerificationOut, SignupIn, UserOut, VerifyEmailIn
from app.services import email_verify, usage

router = make_router(prefix="/auth", tags=["회원 인증"])
log = logging.getLogger(__name__)

T = TypeVar("T")

FAILED_LOGIN_DELAY_S = 0.5  # 실패 응답을 조금 늦춰 무차별 대입을 느리게 한다
# 계정별 로그인 실패 상한 (DB 에 기록: 서버 인스턴스·IP 를 바꿔 가며 한 계정을 계속 맞혀 보지 못하게).
# 관리자 계정은 비밀번호가 길어(16자 이상) 맞히기 어렵고, 남이 일부러 잠가 버리지 못하게 IP 제한만 쓴다
ACCOUNT_MAX_FAILURES = 20
ACCOUNT_FAILURE_WINDOW = timedelta(minutes=15)


async def limited_attempt(limiter: LoginRateLimiter, key: str, blocked_message_ko: str,
                          fn: Callable[..., T | None], *args: Any) -> T | None:
    """비밀번호 확인 시도 하나를 시도 제한 안에서 실행한다 (로그인·비밀번호 변경·이메일 변경이 함께 쓴다).

    fn(*args) 는 스레드 풀에서 실행하고(DB·scrypt 가 이벤트 루프를 막지 않게), None 을 돌려주면 틀린 시도로 센다.
    - 검사와 예약을 한 번에 한다: 비밀번호 확인을 기다리는 동안 몰려온 요청도 '진행 중인 시도'로 세어 막는다.
      막혔으면 QuotaExceededError(429, too_many_attempts, blocked_message_ko)
    - 서버 오류(예외)는 틀린 시도로 세지 않는다
    - 틀렸으면 FAILED_LOGIN_DELAY_S 만큼 이벤트 루프에서 기다린 뒤 None 을 돌려준다"""
    if not limiter.acquire(key):
        raise QuotaExceededError(blocked_message_ko, code="too_many_attempts")
    try:
        result = await run_in_threadpool(fn, *args)
    except BaseException:
        limiter.release(key, failed=False)  # 서버 오류는 틀린 시도로 세지 않는다
        raise
    limiter.release(key, failed=result is None)
    if result is None:
        await asyncio.sleep(FAILED_LOGIN_DELAY_S)  # 부를 때마다 모듈 전역을 읽는다 (테스트가 0 으로 바꾼다)
    return result


# 다른 사람(운영자)을 사칭하지 못하게 막는 이름
RESERVED_USERNAMES = {"admin", "administrator", "root", "system", "staff", "support", "manager", "nestforge",
                      "operator", LOCAL_USERNAME}
RESERVED_NICKNAME_WORDS = ("관리자", "운영자", "운영진", "운영팀", "admin", "nestforge", "공식")
SIGNUP_V6_PREFIX = ACCOUNT_V6_PREFIX  # 회원가입 시도 제한은 IPv6 /56 단위 (가정·사무실 하나가 보통 /56~/48 을 받는다)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, nickname=user.nickname, role=user.role,
                   created_at=user.created_at, email=user.email,
                   email_verified=user.is_admin or user.email_verified_at is not None)


def _signup_block(settings: Settings) -> Exception | None:
    """가입을 막는 설정 문제를 이 순서로 보고 처음 걸린 오류를 돌려준다 (없으면 None).
    signup_open(가입 가능 표시)과 signup()(실제 차단)이 같은 조건을 쓰게 한 곳에 둔다."""
    if settings.auth_mode == "misconfigured":
        return AuthUnavailableError()
    if settings.auth_mode == "disabled" or not settings.signup_enabled:
        return ForbiddenError("지금은 회원가입을 받지 않아요.", code="signup_closed")
    if settings.email_mode == "misconfigured":
        return email_verify.EmailUnavailableError()
    if settings.captcha_mode == "misconfigured":
        return CaptchaUnavailableError()
    return None


def signup_open(settings: Settings) -> bool:
    """가입을 받을 수 있는지 (메일·CAPTCHA 설정이 잘못됐으면 받지 않는다: 인증 없이 계정이 생기지 않게)."""
    return _signup_block(settings) is None


def auth_status(settings: Settings, user: User | None, verification_email_sent: bool | None = None) -> dict:
    captcha = None
    if settings.captcha_mode == "enabled":
        captcha = CaptchaOut(provider="turnstile", site_key=settings.turnstile_site_key.strip())
    return AuthStatusOut(
        auth_enabled=settings.auth_enabled, authenticated=user is not None,
        user=user_out(user) if user else None,
        signup_enabled=signup_open(settings),
        email_verification=settings.email_mode == "enabled",
        captcha=captcha,
        verification_email_sent=verification_email_sent,
    ).model_dump(mode="json")


def set_session_cookie(response: Response, settings: Settings, request: Request, user: User) -> None:
    ttl_s = settings.session_ttl_hours * 3600
    response.set_cookie(
        COOKIE_NAME,
        issue_token(user.id, signing_key(settings), ttl_s, ver=user.session_version),
        max_age=int(ttl_s),
        httponly=True,
        secure=cookie_secure(settings, request),
        samesite="lax",
        path="/",
    )


def is_reserved_nickname(nickname: str, settings: Settings) -> bool:
    """운영자로 보일 수 있는 닉네임인지 (대소문자·공백·기호·숫자 닮은꼴을 무시하고 비교)."""
    key = lookalike_key(nickname)
    return any(lookalike_key(w) in key for w in RESERVED_NICKNAME_WORDS) or key == lookalike_key(settings.admin_username)


def nickname_taken(db: Session, nickname: str, exclude_user_id: str | None = None) -> bool:
    q = select(User.id).where(User.nickname_key == nickname_key(nickname))
    if exclude_user_id is not None:
        q = q.where(User.id != exclude_user_id)
    return db.scalar(q) is not None


@router.get("/me", summary="로그인 상태", response_model=AuthStatusOut)
def me(request: Request, user: User | None = Depends(get_optional_user)) -> dict:
    return auth_status(request.app.state.settings, user)


def _check_signup_fields(db: Session, settings: Settings, data: SignupIn, email_on: bool) -> str | None:
    """가입 입력값을 검사하고 정규화한 이메일 주소(없으면 None)를 돌려준다.
    순서: 이메일 필수 → 예약 아이디 → 예약 닉네임 → 약한 비밀번호 → 아이디 중복 → 닉네임 중복 → 인증된 이메일 중복."""
    if email_on and not data.email:
        raise AppError("이메일을 입력해 주세요. 그 주소로 인증 메일을 보내요.", code="email_required")
    if data.username in RESERVED_USERNAMES or data.username == settings.admin_username.lower():
        raise ConflictError("사용할 수 없는 아이디예요.", code="username_taken")
    if is_reserved_nickname(data.nickname, settings):
        raise ConflictError("사용할 수 없는 닉네임이에요.", code="nickname_taken")
    if data.password.lower() == data.username:
        raise ConflictError("비밀번호를 아이디와 다르게 정해 주세요.", code="weak_password")
    if db.scalar(select(User.id).where(User.username == data.username)):
        raise ConflictError("이미 사용 중인 아이디예요.", code="username_taken")
    if nickname_taken(db, data.nickname):
        raise ConflictError("이미 사용 중인 닉네임이에요.", code="nickname_taken")
    address = str(data.email) if data.email else None
    if address and email_verify.verified_email_taken(db, email_key(address)):
        raise ConflictError("이미 다른 계정에서 인증한 이메일이에요.", code="email_taken")
    return address


@router.post("/signup", summary="회원가입 (가입 후 바로 로그인)", status_code=status.HTTP_201_CREATED,
             response_model=AuthStatusOut)
def signup(data: SignupIn, request: Request, db: Session = Depends(get_db)) -> Response:
    settings: Settings = request.app.state.settings
    if (err := _signup_block(settings)) is not None:
        raise err
    limiter = request.app.state.signup_limiter  # SIGNUP_PER_IP_PER_HOUR=0 이면 None (IP 별 제한 없음)
    if limiter is not None:
        key = client_key(settings, request, v6_prefix=SIGNUP_V6_PREFIX)
        # 성공·실패와 관계없이 시도 횟수를 센다 (아이디 존재 여부를 마구 묻지 못하게). 검사와 기록은 한 번에
        if not limiter.hit(key):
            raise QuotaExceededError("회원가입 요청이 너무 많아요. 잠시 뒤 다시 시도해 주세요.", code="too_many_signups")
    # 로봇 확인은 아이디·닉네임 중복 확인보다 먼저 (자동으로 가입 가능 여부를 캐 보지 못하게). DB 를 쓰기 전이다
    check_captcha(request.app.state.captcha_verifier, data.captcha_token, client_ip(settings, request))
    email_on = settings.email_mode == "enabled"
    address = _check_signup_fields(db, settings, data, email_on)
    db.commit()  # 해시 계산(수십 ms) 동안 DB 연결을 쥐고 있지 않게 읽기 트랜잭션을 끝낸다
    user = User(username=data.username, nickname=data.nickname, nickname_key=nickname_key(data.nickname),
                password_hash=hash_password(data.password), role="member",
                email=address, email_key=email_key(address) if address else None)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # 같은 아이디·닉네임으로 동시에 가입한 경우
        db.rollback()
        raise ConflictError("이미 사용 중인 아이디 또는 닉네임이에요.", code="username_taken") from None
    sent = None
    if email_on:
        try:
            sent = email_verify.send_verification(db, settings, request.app.state.mailer, user,
                                                  ip_key=usage_ip_key(settings, request), first=True)
        except QuotaExceededError as e:  # 서비스 전체 발송 상한: 가입은 됐고, 나중에 다시 보낼 수 있다
            log.warning("가입 인증 메일을 보내지 않았습니다 (%s)", e.code)
            sent = False
    response = JSONResponse(status_code=201, content=auth_status(settings, user, verification_email_sent=sent))
    set_session_cookie(response, settings, request, user)
    return response


def _authenticate(db: Session, settings: Settings, username: str, password: str) -> User | None:
    """아이디·비밀번호 확인 (스레드 풀에서 실행). 끝나면 DB 연결을 풀에 돌려준다."""
    try:
        if hmac.compare_digest(username.encode(), settings.admin_username.encode()):
            verify_password(password, None)  # 회원 로그인과 같은 시간이 걸리게
            return ensure_admin_user(db, settings) if check_admin_credentials(settings, username, password) else None
        row = db.scalar(select(User).where(User.username == username.lower()))
        member = row if row is not None and not row.is_admin else None
        if member is not None and usage.count(db, "login_fail", user_id=member.id,
                                              window=ACCOUNT_FAILURE_WINDOW) >= ACCOUNT_MAX_FAILURES:
            raise QuotaExceededError("이 계정에 틀린 로그인이 많아 잠시 막았어요. 15분 뒤에 다시 시도해 주세요.",
                                     code="too_many_attempts")
        db.commit()  # 해시 비교 동안 DB 연결을 쥐고 있지 않게
        stored = member.password_hash if member is not None else None
        if not verify_password(password, stored):
            if member is not None:
                db.add(UsageEvent(user_id=member.id, kind="login_fail"))
            return None
        if needs_rehash(stored):
            member.password_hash = hash_password(password)
        return member
    except BaseException:
        db.rollback()
        raise
    finally:
        db.commit()


@router.post("/login", summary="로그인 (세션 쿠키 발급)", response_model=AuthStatusOut)
async def login(data: LoginIn, request: Request, db: Session = Depends(get_db)) -> Response:
    # DB·scrypt 는 한 번의 스레드 작업으로 처리하고(이벤트 루프를 막지 않게), 실패 지연은 루프에서 기다린다
    settings: Settings = request.app.state.settings
    if settings.auth_mode == "disabled":
        return JSONResponse(auth_status(settings, None) | {"authenticated": True})
    if settings.auth_mode == "misconfigured":
        raise AuthUnavailableError()
    limiter = request.app.state.login_limiter
    key = client_key(settings, request, v6_prefix=ACCOUNT_V6_PREFIX)
    user = await limited_attempt(limiter, key, "로그인 시도가 너무 많아요. 15분 뒤에 다시 시도해 주세요.",
                                 _authenticate, db, settings, data.username.strip(), data.password)
    if user is None:  # 실패 지연은 limited_attempt 가 이미 기다렸다
        return JSONResponse(status_code=401, content={"detail": {
            "code": "invalid_credentials", "message_ko": "아이디 또는 비밀번호가 올바르지 않아요.",
        }})
    # 성공해도 이 IP 의 실패 기록은 지우지 않는다: 내 계정으로 로그인해 기록을 지워 가며
    # 다른 계정의 비밀번호를 계속 맞혀 보는 우회를 막는다 (실패가 적으면 15분 안에 저절로 사라진다)
    response = JSONResponse(auth_status(settings, user))
    set_session_cookie(response, settings, request, user)
    return response


def _is_cross_site_form(request: Request) -> bool:
    """다른 사이트의 폼 전송으로 온 요청인지. 폼은 application/json 을 보낼 수 없고(보내려면 CORS 사전 요청 필요),
    브라우저는 Sec-Fetch-Site 로 출처를 알려 준다."""
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    return media != "application/json" or request.headers.get("sec-fetch-site") == "cross-site"


@router.post("/logout", summary="로그아웃 (이 브라우저의 세션 쿠키 삭제)", response_model=AuthStatusOut)
def logout(request: Request) -> Response:
    settings = request.app.state.settings
    if _is_cross_site_form(request):  # 다른 사이트에서 강제로 로그아웃시키는 요청(CSRF) 차단
        return JSONResponse(status_code=403, content={"detail": {
            "code": "cross_site_request", "message_ko": "이 요청은 처리할 수 없어요. 화면의 로그아웃 버튼을 이용해 주세요.",
        }})
    response = JSONResponse(auth_status(settings, None))
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax",
                           secure=cookie_secure(settings, request))
    return response


# ── 이메일 인증 ────────────────────────────────────────────


@router.post("/verify-email", summary="이메일 인증 (메일 속 링크의 토큰, 로그인 없이도)")
def verify_email(data: VerifyEmailIn, db: Session = Depends(get_db)) -> dict:
    email_verify.verify(db, data.token)
    return {"ok": True, "message_ko": "이메일 인증을 마쳤어요. 이제 설계·글쓰기·댓글을 쓸 수 있어요."}


@router.post("/verify-email/resend", response_model=ResendVerificationOut, summary="인증 메일 다시 보내기")
def resend_verification(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    settings: Settings = request.app.state.settings
    if settings.email_mode != "enabled":
        raise ForbiddenError("지금은 이메일 인증을 쓰지 않아요.", code="email_verification_disabled")
    if user.is_admin:
        raise ForbiddenError("관리자 계정은 이메일 인증이 필요 없어요.")
    if user.email_verified_at is not None:
        return ResendVerificationOut(sent=False, email=user.email, message_ko="이미 인증한 이메일이에요.")
    sent = email_verify.send_verification(db, settings, request.app.state.mailer, user,
                                          ip_key=usage_ip_key(settings, request))
    return ResendVerificationOut(
        sent=sent, email=user.email,
        message_ko=f"{user.email} 로 인증 메일을 보냈어요. 메일의 링크를 눌러 주세요." if sent
        else "인증 메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.",
    )
