"""관리자 로그인·로그아웃."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.auth import COOKIE_NAME, check_credentials, current_admin, issue_token, signing_key

router = APIRouter(prefix="/auth", tags=["관리자 인증"])

FAILED_LOGIN_DELAY_S = 0.5  # 실패 응답을 조금 늦춰 무차별 대입을 느리게 한다


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _status(request: Request) -> dict:
    settings = request.app.state.settings
    user = current_admin(request)
    return {
        "auth_enabled": settings.auth_enabled,
        "authenticated": (not settings.auth_enabled) or user is not None,
        "username": user,
    }


@router.get("/me", summary="로그인 상태")
def me(request: Request) -> dict:
    return _status(request)


@router.post("/login", summary="관리자 로그인 (세션 쿠키 발급)")
async def login(data: LoginIn, request: Request) -> Response:
    settings = request.app.state.settings
    if not settings.auth_enabled:
        return JSONResponse({"auth_enabled": False, "authenticated": True, "username": None})
    limiter = request.app.state.login_limiter
    key = _client_key(request)
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
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout", summary="로그아웃 (세션 쿠키 삭제)")
def logout(request: Request) -> Response:
    response = JSONResponse({"auth_enabled": request.app.state.settings.auth_enabled, "authenticated": False,
                             "username": None})
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax",
                           secure=request.url.scheme == "https")
    return response
