"""환경변수 기반 설정. API 키 등 비밀값은 환경변수(.env)로만 받는다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

MIN_SESSION_SECRET_BYTES = 32
MIN_ADMIN_PASSWORD_LEN = 16


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
    # AUTH_REQUIRED=1 (컨테이너 이미지 기본값) 이면 설정이 빠졌을 때 인증을 끄지 않고 API 를 막는다(503).
    auth_required: bool = False
    admin_username: str = "admin"
    admin_password: SecretStr | None = None
    session_secret: SecretStr | None = None  # 세션 쿠키 서명 키 (32바이트 이상 무작위 문자열, 필수)
    session_ttl_hours: float = Field(default=24.0, gt=0, le=720)  # 최대 30일
    # 세션 쿠키 Secure 속성. 비우면 요청 scheme(https)으로 판단하고, 컨테이너 이미지는 1 로 고정한다.
    cookie_secure: bool | None = None
    # 로그인 시도 제한에 쓸 클라이언트 IP 헤더 (플랫폼이 덮어써 위조할 수 없는 헤더만. 예: x-vercel-forwarded-for)
    client_ip_header: str | None = None

    @field_validator("admin_username", mode="after")
    @classmethod
    def _strip_admin_username(cls, v: str) -> str:
        # 붙여 넣기로 섞인 앞뒤 공백 때문에 로그인이 영영 안 되는 일을 막는다 (아이디는 비밀값이 아님)
        return v.strip()

    @property
    def auth_problems(self) -> list[str]:
        """관리자 인증 설정 문제 (비밀값 자체는 담지 않는다). 비어 있으면 정상 또는 인증 꺼짐."""
        password = self.admin_password.get_secret_value() if self.admin_password else ""
        if not password.strip():
            return ["ADMIN_PASSWORD 가 없습니다"] if self.auth_required else []
        problems = []
        if password != password.strip():
            problems.append("ADMIN_PASSWORD 앞뒤에 공백·줄바꿈이 있습니다 (붙여 넣기 실수일 수 있음)")
        if len(password) < MIN_ADMIN_PASSWORD_LEN:
            problems.append(f"ADMIN_PASSWORD 는 {MIN_ADMIN_PASSWORD_LEN}자 이상이어야 합니다")
        if not self.admin_username.strip():
            problems.append("ADMIN_USERNAME 이 비어 있습니다")
        secret = self.session_secret.get_secret_value() if self.session_secret else ""
        if len(secret.encode()) < MIN_SESSION_SECRET_BYTES:
            problems.append(f"SESSION_SECRET 이 없거나 {MIN_SESSION_SECRET_BYTES}바이트보다 짧습니다")
        return problems

    @property
    def auth_mode(self) -> Literal["disabled", "enabled", "misconfigured"]:
        """disabled: 인증 꺼짐(로컬 개발) · enabled: 관리자 로그인 필요 · misconfigured: 설정 오류로 API 차단"""
        if self.auth_problems:
            return "misconfigured"
        if self.admin_password and self.admin_password.get_secret_value().strip():
            return "enabled"
        return "disabled"

    @property
    def auth_enabled(self) -> bool:
        """API 가 관리자 인증으로 보호되는지 (설정 오류로 막힌 경우도 포함)."""
        return self.auth_mode != "disabled"

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
