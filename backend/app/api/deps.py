"""라우터 공용 의존성과 라우트 클래스."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.services.design_service import DesignService


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_service(request: Request) -> DesignService:
    return request.app.state.design_service


def _release_db(endpoint: Callable[..., Any]) -> Callable[..., Any]:
    """동기 API 함수가 끝나면 열린 트랜잭션을 끝내 DB 연결을 풀에 바로 돌려준다.

    FastAPI 는 동기 API 함수와 응답 직렬화를 서로 다른 스레드 작업으로 실행한다. 연결을 쥔 채 다음 스레드를
    기다리는 요청이 풀 크기만큼 쌓이고 나머지 스레드가 모두 연결을 기다리면, 서로를 기다리며 pool_timeout 까지
    인스턴스 전체가 멈춘다. 응답은 함수 안에서 이미 만들어지므로(expire_on_commit=False) 커밋해도 안전하다."""
    if inspect.iscoroutinefunction(endpoint):
        return endpoint
    # FastAPI 는 시그니처의 문자열 주석을 래퍼의 __globals__ 로 풀므로, 원래 모듈 기준으로 미리 풀어 둔다
    signature = inspect.signature(endpoint, eval_str=True)

    @functools.wraps(endpoint)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        sessions = [v for v in kwargs.values() if isinstance(v, Session)]
        try:
            result = endpoint(*args, **kwargs)
        except BaseException:
            for db in sessions:
                db.rollback()
            raise
        for db in sessions:
            db.commit()
        return result

    wrapper.__signature__ = signature  # type: ignore[attr-defined]
    return wrapper


class DBReleasingRoute(APIRoute):
    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        super().__init__(path, _release_db(endpoint), **kwargs)


def make_router(**kwargs: Any) -> APIRouter:
    return APIRouter(route_class=DBReleasingRoute, **kwargs)
