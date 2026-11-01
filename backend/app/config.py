"""환경변수 기반 설정. API 키 등 비밀값은 환경변수(.env)로만 받는다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # LLM
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str | None = None
    llm_provider: Literal["auto", "anthropic", "mock"] = "auto"
    llm_max_retries: int = 2
    llm_timeout_s: float = 60.0
    # 설계 요청 1건에서 LLM 에 쓰는 전체 시간 상한(초). 배포 플랫폼 요청 한도보다 작게 (Vercel Hobby: 300초)
    llm_deadline_s: float = 240.0

    # 저장소
    # 로컬 디스크가 인스턴스마다 사라지는 환경인지 (컨테이너 이미지에서 1). 이때 SQLite 는 임시 저장소로 표시된다.
    ephemeral_filesystem: bool = False
    # DATABASE_URL (Neon 등) 이 없으면 POSTGRES_URL (Vercel Marketplace Supabase 연동이 주입하는 이름) 을 쓴다
    database_url: str = Field(
        default=f"sqlite:///{BACKEND_DIR / 'data' / 'kkomul.db'}",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"),
    )
    mesh_cache_dir: Path = BACKEND_DIR / "data" / "meshes"

    # 규칙 파일 디렉터리 (species.yaml, printing.yaml)
    rules_dir: Path = BACKEND_DIR / "rules"

    # API 경로 접두사. 로컬은 "" (http://localhost:8000/designs),
    # Vercel Services 에서는 "/api" (프론트엔드와 같은 출처의 /api/* 가 백엔드로 전달되며 경로는 그대로 유지됨)
    api_prefix: str = ""

    # CORS 허용 출처 (쉼표 구분)
    cors_origins: str = "http://localhost:3000"

    # 관리자 인증: ADMIN_PASSWORD 가 있으면 켜진다. 사이트는 공개, API 는 관리자 로그인 후 사용.
    admin_username: str = "admin"
    admin_password: SecretStr | None = None
    session_secret: SecretStr | None = None  # 세션 쿠키 서명 키 (없으면 비밀번호에서 유도)
    session_ttl_hours: float = 168.0

    @property
    def auth_enabled(self) -> bool:
        return bool(self.admin_password and self.admin_password.get_secret_value())

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
