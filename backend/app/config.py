"""환경변수 기반 설정. API 키 등 비밀값은 환경변수(.env)로만 받는다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

MIN_SESSION_SECRET_BYTES = 32
MIN_ADMIN_PASSWORD_LEN = 16
MAX_ADMIN_USERNAME_LEN = 32  # users.username 열 길이


def secret_value(s: SecretStr | None) -> str:
    """선택 비밀값의 내용 (없으면 빈 문자열)."""
    return s.get_secret_value() if s is not None else ""


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
    # 회원
    signup_enabled: bool = True
    # 한 IP(IPv6 는 /56)에서 1시간에 시도할 수 있는 회원가입 횟수. 0 이면 IP 별 제한 없음
    signup_per_ip_per_hour: int = Field(default=5, ge=0, le=1000)
    # 설계(LLM 호출) 사용량 상한, 최근 24시간 기준 (관리자는 제외). 실패한 요청도 LLM 비용이 들므로 센다.
    design_daily_limit: int = Field(default=20, ge=0, le=10_000)            # 회원 1명당
    design_ip_daily_limit: int = Field(default=40, ge=0, le=100_000)        # 한 IP(IPv6 는 /56)당 (계정 여러 개로 우회 방지)
    design_global_daily_limit: int = Field(default=300, ge=0, le=1_000_000)  # 서비스 전체
    # 커뮤니티 도배 방지: 회원 1명당 최근 24시간
    post_daily_limit: int = Field(default=20, ge=0, le=10_000)
    comment_daily_limit: int = Field(default=100, ge=0, le=100_000)

    # 이메일 인증: EMAIL_PROVIDER 를 정하면 켜진다. 가입할 때 이메일이 필수이고, 인증 전에는 설계·글쓰기·댓글을 못 한다.
    # smtp (Gmail 앱 비밀번호, 네이버 등) · resend (Resend API, 보내는 도메인 인증 필요) · file (로컬 개발·테스트: 파일로 저장)
    email_provider: Literal["", "smtp", "resend", "file"] = ""
    email_from: str = ""  # 보내는 사람. 예: "NestForge <no-reply@example.com>" (SMTP 는 로그인한 계정 주소와 같아야 하는 경우가 많다)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    resend_api_key: SecretStr | None = None
    email_outbox_dir: Path = BACKEND_DIR / "data" / "outbox"
    # 메일 속 링크에 쓰는 사이트 주소 (예: https://petlab-sage.vercel.app). 요청 헤더로 정하지 않는다 (주소 위조 방지)
    app_base_url: str = ""
    email_token_ttl_hours: float = Field(default=24.0, gt=0, le=168)
    email_daily_limit: int = Field(default=300, ge=0, le=1_000_000)  # 서비스 전체 최근 24시간 발송 상한 (메일 서비스 한도 보호)

    # CAPTCHA (Cloudflare Turnstile): 두 키가 모두 있으면 회원가입에 CAPTCHA 를 요구한다
    turnstile_site_key: str = ""
    turnstile_secret_key: SecretStr | None = None
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

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
        password = secret_value(self.admin_password)
        if not password.strip():
            return ["ADMIN_PASSWORD 가 없습니다"] if self.auth_required else []
        problems = []
        if password != password.strip():
            problems.append("ADMIN_PASSWORD 앞뒤에 공백·줄바꿈이 있습니다 (붙여 넣기 실수일 수 있음)")
        if len(password) < MIN_ADMIN_PASSWORD_LEN:
            problems.append(f"ADMIN_PASSWORD 는 {MIN_ADMIN_PASSWORD_LEN}자 이상이어야 합니다")
        if not self.admin_username.strip():
            problems.append("ADMIN_USERNAME 이 비어 있습니다")
        if len(self.admin_username) > MAX_ADMIN_USERNAME_LEN:
            problems.append(f"ADMIN_USERNAME 은 {MAX_ADMIN_USERNAME_LEN}자 이하여야 합니다")
        secret = secret_value(self.session_secret)
        if len(secret.encode()) < MIN_SESSION_SECRET_BYTES:
            problems.append(f"SESSION_SECRET 이 없거나 {MIN_SESSION_SECRET_BYTES}바이트보다 짧습니다")
        return problems

    @property
    def email_problems(self) -> list[str]:
        """이메일 인증 설정 문제 (비밀값은 담지 않는다). EMAIL_PROVIDER 가 비어 있으면 검사하지 않는다."""
        if not self.email_provider:
            return []
        problems = []
        if not self.email_from.strip():
            problems.append("EMAIL_FROM 이 없습니다")
        if self.email_provider == "smtp" and not self.smtp_host.strip():
            problems.append("SMTP_HOST 가 없습니다")
        if self.email_provider == "resend" and not secret_value(self.resend_api_key):
            problems.append("RESEND_API_KEY 가 없습니다")
        if not self.email_base_url.startswith(("https://", "http://")):
            problems.append("APP_BASE_URL(메일 속 링크 주소)이 없거나 http(s):// 로 시작하지 않습니다")
        if self.deployed:
            # 배포 환경: 링크 주소를 직접 정해야 하고(로컬 기본값으로 메일이 나가지 않게), 파일 저장 방식은 쓸 수 없다
            base = self.app_base_url.strip()
            host = urlsplit(base).hostname or ""
            if not base.startswith("https://") or host in ("localhost", "127.0.0.1", "::1"):
                problems.append("배포 환경에서는 APP_BASE_URL 을 실제 사이트 주소(https://…)로 정해야 합니다")
            if self.email_provider == "file":
                problems.append("EMAIL_PROVIDER=file 은 로컬 개발·테스트용입니다 (배포 환경에서는 smtp 또는 resend)")
        return problems

    @property
    def deployed(self) -> bool:
        """배포 환경인지 (컨테이너 이미지가 EPHEMERAL_FILESYSTEM=1, Vercel 은 API_PREFIX=/api 를 쓴다)."""
        return self.ephemeral_filesystem or bool(self.normalized_api_prefix)

    @property
    def email_mode(self) -> Literal["disabled", "enabled", "misconfigured"]:
        """disabled: 이메일 인증 없음 · enabled: 가입 시 이메일 필수, 인증 전 일부 기능 제한 · misconfigured: 가입을 막는다"""
        if not self.email_provider:
            return "disabled"
        return "misconfigured" if self.email_problems else "enabled"

    @property
    def email_base_url(self) -> str:
        """메일 속 링크의 사이트 주소. APP_BASE_URL 이 없으면 CORS 허용 출처의 첫 값 (로컬 개발)."""
        base = self.app_base_url.strip() or (self.cors_origin_list[0] if self.cors_origin_list else "")
        return base.rstrip("/")

    @property
    def captcha_mode(self) -> Literal["disabled", "enabled", "misconfigured"]:
        site = bool(self.turnstile_site_key.strip())
        secret = bool(secret_value(self.turnstile_secret_key).strip())
        if site and secret:
            return "enabled"
        return "misconfigured" if site or secret else "disabled"

    @property
    def auth_mode(self) -> Literal["disabled", "enabled", "misconfigured"]:
        """disabled: 인증 꺼짐(로컬 개발) · enabled: 관리자 로그인 필요 · misconfigured: 설정 오류로 API 차단"""
        if self.auth_problems:
            return "misconfigured"
        if secret_value(self.admin_password).strip():
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
