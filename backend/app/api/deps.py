"""라우터 공용 의존성."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
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
