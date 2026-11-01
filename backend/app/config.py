"""환경변수 기반 설정. API 키 등 비밀값은 환경변수(.env)로만 받는다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str | None = None
    llm_provider: Literal["auto", "anthropic", "mock"] = "auto"
    llm_max_retries: int = 2
    llm_timeout_s: float = 60.0

    # 저장소
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'kkomul.db'}"
    mesh_cache_dir: Path = BACKEND_DIR / "data" / "meshes"

    # 규칙 파일 디렉터리 (species.yaml, printing.yaml)
    rules_dir: Path = BACKEND_DIR / "rules"

    # API 경로 접두사. 로컬은 "" (http://localhost:8000/designs),
    # Vercel Services 에서는 "/api" (프론트엔드와 같은 출처의 /api/* 가 백엔드로 전달되며 경로는 그대로 유지됨)
    api_prefix: str = ""

    # CORS 허용 출처 (쉼표 구분)
    cors_origins: str = "http://localhost:3000"

    @property
    def normalized_api_prefix(self) -> str:
        """"/api/" → "/api", "api" → "/api", "" 또는 "/" → "" """
        p = self.api_prefix.strip().strip("/")
        return f"/{p}" if p else ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_llm_provider(self) -> Literal["anthropic", "mock"]:
        """auto: API 키가 있으면 anthropic, 없으면 개발용 mock."""
        if self.llm_provider == "auto":
            return "anthropic" if self.anthropic_api_key else "mock"
        return self.llm_provider


@lru_cache
def get_settings() -> Settings:
    return Settings()
