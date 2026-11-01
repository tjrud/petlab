"""회원가입·로그인·로그아웃·로그인 상태."""

from __future__ import annotations

import asyncio
import hmac

from fastapi import Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, make_router
from app.auth import (
    COOKIE_NAME,
    LOCAL_USERNAME,
    AuthUnavailableError,
    check_admin_credentials,
    client_key,
    cookie_secure,
    ensure_admin_user,
    get_optional_user,
    issue_token,
    signing_key,
)
from app.config import Settings
from app.errors import ConflictError, ForbiddenError, QuotaExceededError
from app.models import User
from app.names import lookalike_key, nickname_key
from app.passwords import hash_password, verify_password
from app.schemas import AuthStatusOut, SignupIn, UserOut

router = make_router(prefix="/auth", tags=["회원 인증"])

FAILED_LOGIN_DELAY_S = 0.5  # 실패 응답을 조금 늦춰 무차별 대입을 느리게 한다

# 다른 사람(운영자)을 사칭하지 못하게 막는 이름
RESERVED_USERNAMES = {"admin", "administrator", "root", "system", "staff", "support", "manager", "nestforge",
                      "operator", LOCAL_USERNAME}
RESERVED_NICKNAME_WORDS = ("관리자", "운영자", "운영진", "운영팀", "admin", "nestforge", "공식")
SIGNUP_V6_PREFIX = 56  # 회원가입 시도 제한은 IPv6 /56 단위 (가정·사무실 하나가 보통 /56~/48 을 받는다)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, nickname=user.nickname, role=user.role,
                   created_at=user.created_at)


def auth_status(settings: Settings, user: User | None) -> dict:
    return AuthStatusOut(
        auth_enabled=settings.auth_enabled, authenticated=user is not None,
        user=user_out(user) if user else None,
        signup_enabled=settings.signup_enabled and settings.auth_mode == "enabled",
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


@router.post("/signup", summary="회원가입 (가입 후 바로 로그인)", status_code=status.HTTP_201_CREATED,
             response_model=AuthStatusOut)
def signup(data: SignupIn, request: Request, db: Session = Depends(get_db)) -> Response:
    settings: Settings = request.app.state.settings
    if settings.auth_mode == "misconfigured":
        raise AuthUnavailableError()
    if settings.auth_mode == "disabled" or not settings.signup_enabled:
        raise ForbiddenError("지금은 회원가입을 받지 않아요.", code="signup_closed")
    limiter = request.app.state.signup_limiter  # SIGNUP_PER_IP_PER_HOUR=0 이면 None (IP 별 제한 없음)
    if limiter is not None:
        key = client_key(settings, request, v6_prefix=SIGNUP_V6_PREFIX)
        if limiter.blocked(key):
            raise QuotaExceededError("회원가입 요청이 너무 많아요. 잠시 뒤 다시 시도해 주세요.", code="too_many_signups")
        limiter.record_failure(key)  # 성공·실패와 관계없이 시도 횟수를 센다 (아이디 존재 여부를 마구 묻지 못하게)
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
    db.commit()  # 해시 계산(수십 ms) 동안 DB 연결을 쥐고 있지 않게 읽기 트랜잭션을 끝낸다
    user = User(username=data.username, nickname=data.nickname, nickname_key=nickname_key(data.nickname),
                password_hash=hash_password(data.password), role="member")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # 같은 아이디·닉네임으로 동시에 가입한 경우
        db.rollback()
        raise ConflictError("이미 사용 중인 아이디 또는 닉네임이에요.", code="username_taken") from None
    response = JSONResponse(status_code=201, content=auth_status(settings, user))
    set_session_cookie(response, settings, request, user)
    return response


def _authenticate(db: Session, settings: Settings, username: str, password: str) -> User | None:
    """아이디·비밀번호 확인 (스레드 풀에서 실행). 끝나면 DB 연결을 풀에 돌려준다."""
    try:
        if hmac.compare_digest(username.encode(), settings.admin_username.encode()):
            verify_password(password, None)  # 회원 로그인과 같은 시간이 걸리게
            return ensure_admin_user(db, settings) if check_admin_credentials(settings, username, password) else None
        row = db.scalar(select(User).where(User.username == username.lower()))
        db.commit()  # 해시 비교 동안 DB 연결을 쥐고 있지 않게
        stored = row.password_hash if row is not None and not row.is_admin else None
        return row if verify_password(password, stored) else None
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
    key = client_key(settings, request)
    if limiter.blocked(key):
        return JSONResponse(status_code=429, content={"detail": {
            "code": "too_many_attempts",
            "message_ko": "로그인 시도가 너무 많아요. 15분 뒤에 다시 시도해 주세요.",
        }})
    user = await run_in_threadpool(_authenticate, db, settings, data.username.strip(), data.password)
    if user is None:
        limiter.record_failure(key)
        await asyncio.sleep(FAILED_LOGIN_DELAY_S)
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
