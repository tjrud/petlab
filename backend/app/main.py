"""꼬물공방 FastAPI 앱 진입점."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError

from app.api import designs, habitats, meta, waitlist
from app.config import Settings, get_settings
from app.db import init_db, is_ephemeral_database, make_engine, make_session_factory
from app.llm.base import Interpreter, LLMConfigError, LLMError
from app.llm.interpreter import make_interpreter
from app.rules.loader import load_rules
from app.services.design_service import (
    DesignService,
    ExportBlockedError,
    InvalidInputError,
    MeshRegenerationError,
    NotFoundError,
)

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, interpreter: Interpreter | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 규칙 파일이 잘못되면 여기서 예외가 나며 서버가 기동하지 않는다.
        rules = load_rules(settings.rules_dir)
        engine = make_engine(settings.database_url)
        init_db(engine)

        app.state.settings = settings
        app.state.rules = rules
        app.state.session_factory = make_session_factory(engine)
        app.state.llm_config_error = None
        app.state.db_dialect = engine.dialect.name
        app.state.db_ephemeral = is_ephemeral_database(settings.database_url, settings.ephemeral_filesystem)
        if app.state.db_ephemeral:
            log.error(
                "임시 데이터베이스(%s)를 사용 중입니다. 인스턴스가 바뀌거나 재배포되면 데이터가 사라집니다. "
                "배포 환경에서는 DATABASE_URL(Postgres)을 설정하세요.", engine.url.render_as_string(hide_password=True)
            )

        resolved: Interpreter | None = interpreter
        if resolved is None:
            try:
                resolved = make_interpreter(settings)
            except LLMConfigError as e:
                # 설정 오류가 있어도 서버는 뜨게 하고, 설계 요청 시 안내한다.
                log.error("LLM 설정 오류: %s", e.detail)
                app.state.llm_config_error = e

        def get_interpreter() -> Interpreter:
            if resolved is None:
                raise app.state.llm_config_error
            return resolved

        app.state.design_service = DesignService(rules, get_interpreter, settings.mesh_cache_dir)
        yield
        engine.dispose()

    prefix = settings.normalized_api_prefix
    app = FastAPI(
        title="꼬물공방 API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{prefix}/docs",
        redoc_url=None,
        openapi_url=f"{prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    @app.exception_handler(LLMError)
    async def _llm_error(_: Request, e: LLMError):
        log.warning("LLM 오류 (%s): %s", type(e).__name__, e.detail)
        return JSONResponse(status_code=e.status_code,
                            content={"detail": {"code": type(e).__name__, "message_ko": e.user_message_ko}})

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, e: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": {"code": "not_found", "message_ko": e.message_ko}})

    @app.exception_handler(InvalidInputError)
    async def _invalid(_: Request, e: InvalidInputError):
        return JSONResponse(status_code=422, content={"detail": {"code": "invalid_input", "message_ko": e.message_ko}})

    @app.exception_handler(MeshRegenerationError)
    async def _regen(_: Request, e: MeshRegenerationError):
        return JSONResponse(status_code=409, content={"detail": {"code": "mesh_unavailable", "message_ko": e.message_ko}})

    @app.exception_handler(DataError)
    async def _data_error(_: Request, e: DataError):
        # 입력 검증을 통과했지만 DB 가 거부한 값 (예: Postgres 범위·문자 제약) — 500 대신 422
        log.warning("DB DataError: %s", e.orig)
        return JSONResponse(status_code=422, content={"detail": {
            "code": "invalid_input", "message_ko": "입력값을 처리할 수 없어요. 내용을 확인해 주세요.",
        }})

    @app.exception_handler(ExportBlockedError)
    async def _blocked(_: Request, e: ExportBlockedError):
        return JSONResponse(status_code=409, content={"detail": {
            "code": e.code, "message_ko": e.message_ko, "errors": e.errors,
        }})

    # 응답의 mesh_url 등은 API 루트 기준 경로(/designs/...)이고, 프론트엔드가 API_BASE(/api)를 앞에 붙인다.
    for router in (meta.router, habitats.router, designs.router, waitlist.router):
        app.include_router(router, prefix=prefix)
    return app


app = create_app()
