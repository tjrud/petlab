"""꼬물공방 FastAPI 앱 진입점."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.rules.loader import load_rules


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 규칙 파일이 잘못되면 여기서 예외가 나며 서버가 기동하지 않는다.
        app.state.settings = settings
        app.state.rules = load_rules(settings.rules_dir)
        yield

    app = FastAPI(title="꼬물공방 API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    @app.get("/health")
    def health(request: Request) -> dict:
        rules = request.app.state.rules
        return {
            "status": "ok",
            "llm_provider": settings.resolved_llm_provider,
            "rules": {
                "species_version": rules.species_file.version,
                "species_reviewed": rules.species_file.reviewed,
                "printing_version": rules.printing.version,
            },
        }

    return app


app = create_app()
