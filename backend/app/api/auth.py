"""관리자 로그인·로그아웃."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.auth import (
    COOKIE_NAME,
    AuthUnavailableError,
    check_credentials,
    client_key,
    cookie_secure,
    current_admin,
    issue_token,
    signing_key,
)

router = APIRouter(prefix="/auth", tags=["관리자 인증"])

FAILED_LOGIN_DELAY_S = 0.5  # 실패 응답을 조금 늦춰 무차별 대입을 느리게 한다


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def _status(request: Request) -> dict:
    settings = request.app.state.settings
    user = current_admin(request)
    return {
        "auth_enabled": settings.auth_enabled,
        "authenticated": settings.auth_mode == "disabled" or user is not None,
        "username": user,
    }


@router.get("/me", summary="로그인 상태")
def me(request: Request) -> dict:
    return _status(request)


@router.post("/login", summary="관리자 로그인 (세션 쿠키 발급)")
async def login(data: LoginIn, request: Request) -> Response:
    settings = request.app.state.settings
    if settings.auth_mode == "disabled":
        return JSONResponse({"auth_enabled": False, "authenticated": True, "username": None})
    if settings.auth_mode == "misconfigured":
        raise AuthUnavailableError()
    limiter = request.app.state.login_limiter
    key = client_key(settings, request)
    if limiter.blocked(key):
        return JSONResponse(status_code=429, content={"detail": {
            "code": "too_many_attempts",
            "message_ko": "로그인 시도가 너무 많아요. 15분 뒤에 다시 시도해 주세요.",
        }})
    if not check_credentials(settings, data.username, data.password):
        limiter.record_failure(key)
        await asyncio.sleep(FAILED_LOGIN_DELAY_S)
        return JSONResponse(status_code=401, content={"detail": {
            "code": "invalid_credentials", "message_ko": "아이디 또는 비밀번호가 올바르지 않아요.",
        }})
    limiter.reset(key)
    ttl_s = settings.session_ttl_hours * 3600
    response = JSONResponse({"auth_enabled": True, "authenticated": True, "username": settings.admin_username})
    response.set_cookie(
        COOKIE_NAME,
        issue_token(settings.admin_username, signing_key(settings), ttl_s),
        max_age=int(ttl_s),
        httponly=True,
        secure=cookie_secure(settings, request),
        samesite="lax",
        path="/",
    )
    return response


def _is_cross_site_form(request: Request) -> bool:
    """다른 사이트의 폼 전송으로 온 요청인지. 폼은 application/json 을 보낼 수 없고(보내려면 CORS 사전 요청 필요),
    브라우저는 Sec-Fetch-Site 로 출처를 알려 준다."""
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    return media != "application/json" or request.headers.get("sec-fetch-site") == "cross-site"


@router.post("/logout", summary="로그아웃 (이 브라우저의 세션 쿠키 삭제)")
def logout(request: Request) -> Response:
    settings = request.app.state.settings
    if _is_cross_site_form(request):  # 다른 사이트에서 강제로 로그아웃시키는 요청(CSRF) 차단
        return JSONResponse(status_code=403, content={"detail": {
            "code": "cross_site_request", "message_ko": "이 요청은 처리할 수 없어요. 화면의 로그아웃 버튼을 이용해 주세요.",
        }})
    response = JSONResponse({"auth_enabled": settings.auth_enabled, "authenticated": False, "username": None})
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax",
                           secure=cookie_secure(settings, request))
    return response
