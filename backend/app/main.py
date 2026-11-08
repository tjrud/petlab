"""NestForge FastAPI 앱 진입점."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import DataError

from app.api import auth as auth_api
from app.api import community, designs, habitats, layouts, market, me, meta, waitlist
from app.auth import (
    AuthRequiredError,
    AuthUnavailableError,
    LoginRateLimiter,
    ensure_admin_user,
)
from app.captcha import CaptchaVerifier, turnstile_verifier
from app.config import Settings, get_settings
from app.db import init_db, is_ephemeral_database, make_engine, make_session_factory
from app.errors import AppError
from app.i18n import LANG_COOKIE, LANG_HEADER, parse_lang, reset_lang, set_lang, translate_json
from app.llm.base import Interpreter, LLMConfigError, LLMError
from app.llm.interpreter import make_interpreter
from app.mailer import Mailer, make_mailer
from app.rules.loader import load_rules
from app.storage import make_storage
from app.services.design_service import (
    DesignLimits,
    DesignService,
    ExportBlockedError,
    GeometryChangedError,
    MeshRegenerationError,
)

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, interpreter: Interpreter | None = None,
               mailer: Mailer | None = None, captcha_verifier: CaptchaVerifier | None = None) -> FastAPI:
    """mailer·captcha_verifier 는 테스트에서 바꿔 끼울 때만 준다 (주지 않으면 설정으로 만든다)."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 규칙 파일이 잘못되면 여기서 예외가 나며 서버가 기동하지 않는다.
        rules = load_rules(settings.rules_dir)
        engine = make_engine(settings.database_url)
        added = init_db(engine)
        if added:
            log.warning("DB 마이그레이션: 열·인덱스 추가 %s", ", ".join(added))

        app.state.settings = settings
        app.state.rules = rules
        app.state.session_factory = make_session_factory(engine)
        app.state.llm_config_error = None
        # 로그인: IP 별 15분 10번. 표가 가득 차도 새 접속 전체를 막지 않는다 (계정별 상한은 DB 에서 따로 센다)
        app.state.login_limiter = LoginRateLimiter(fail_closed=False)
        # 회원가입: IP 별 1시간 시도 수 (0 이면 제한 없음). 표가 차도 신규 가입 전체를 막지 않는다 (fail open)
        app.state.signup_limiter = (
            LoginRateLimiter(max_failures=settings.signup_per_ip_per_hour, window_s=3600.0, fail_closed=False)
            if settings.signup_per_ip_per_hour > 0 else None
        )
        # 이메일 인증·CAPTCHA (설정이 잘못됐으면 신규 가입을 막는다: 인증 없이 계정이 생기지 않게)
        app.state.mailer = mailer if mailer is not None else make_mailer(settings)
        app.state.captcha_verifier = None
        if settings.captcha_mode == "enabled":
            app.state.captcha_verifier = captcha_verifier or turnstile_verifier(settings)
        if settings.email_mode == "misconfigured":
            log.error("이메일 인증 설정 오류로 회원가입을 막습니다: %s", "; ".join(settings.email_problems))
        elif settings.email_mode == "enabled":
            log.info("이메일 인증 사용 (%s)", settings.email_provider)
        if settings.captcha_mode == "misconfigured":
            log.error("CAPTCHA 설정 오류로 회원가입을 막습니다: TURNSTILE_SITE_KEY 와 TURNSTILE_SECRET_KEY 를 함께 설정하세요.")
        # 비밀번호 변경 시 현재 비밀번호 확인: 회원별 15분에 5번까지 틀릴 수 있다
        app.state.password_limiter = LoginRateLimiter(max_failures=5, window_s=900.0, fail_closed=False)
        if settings.auth_mode == "misconfigured":
            # 비밀값은 기록하지 않는다. API 는 503 으로 막힌 채 기동한다 (인증을 끄지 않음)
            log.error("관리자 인증 설정 오류로 API 를 막습니다: %s", "; ".join(settings.auth_problems))
        elif settings.auth_mode == "disabled" and (settings.ephemeral_filesystem or settings.normalized_api_prefix):
            log.error("관리자 인증이 꺼져 있습니다 (ADMIN_PASSWORD 없음). 배포 환경이라면 API 가 공개 상태입니다.")
        app.state.market_storage = make_storage(settings)  # 탐색 파일 (없으면 올리기를 막는다)
        # 탐색 내려받기 횟수: 같은 IP·작품은 1시간에 한 번만 센다 (횟수 부풀리기로 인기 순위를 바꾸지 못하게)
        # 설계 3D 프린팅 파일 만들기: IP 별 10분에 30번
        app.state.export_limiter = LoginRateLimiter(max_failures=30, window_s=600.0, fail_closed=False)
        app.state.download_counter = LoginRateLimiter(max_failures=1, window_s=3600.0, max_keys=50_000,
                                                      fail_closed=False)
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

        app.state.design_service = DesignService(
            rules, get_interpreter, settings.mesh_cache_dir,
            DesignLimits(per_user=settings.design_daily_limit, global_=settings.design_global_daily_limit,
                         per_ip=settings.design_ip_daily_limit),
        )
        if settings.auth_mode == "enabled":
            db = app.state.session_factory()
            try:
                ensure_admin_user(db, settings)  # 관리자 계정 행 (글·설계의 소유자로 쓰인다)
            finally:
                db.close()
        yield
        engine.dispose()

    prefix = settings.normalized_api_prefix
    app = FastAPI(
        title="NestForge API",
        version="0.1.0",
        lifespan=lifespan,
        # 인증이 켜지면 Swagger UI 페이지(외부 CDN 스크립트를 세션 쿠키와 같은 출처에서 실행)는 끈다. JSON 스키마는 유지
        docs_url=None if settings.auth_enabled else f"{prefix}/docs",
        redoc_url=None,
        openapi_url=f"{prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,  # 로컬 개발(프론트 :3000 ↔ 백엔드 :8000)에서 세션 쿠키 전달
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def _no_shared_cache(request: Request, call_next):
        # 관리자 세션으로 받은 응답이 CDN·공유 캐시에 남지 않게 한다 (따로 지정한 응답은 그대로)
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.add_vary_header("Cookie")  # 기존 Vary(Origin 등)에 덧붙인다
        # API 응답(파일 내려받기 포함)을 브라우저가 HTML 로 해석하거나 다른 사이트가 틀에 넣지 못하게 한다
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if not request.url.path.endswith("/docs"):  # 개발용 Swagger UI 는 외부 스크립트를 쓴다
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; sandbox")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.middleware("http")
    async def _language(request: Request, call_next):
        # 요청 언어: X-Lang 헤더(프론트엔드 API 호출), 없으면 lang 쿠키(내려받기 링크 등). 영어면 응답 JSON 의
        # 서버 문구(…_ko 열쇠 등)를 카탈로그로 바꾼다 (app/i18n)
        lang = parse_lang(request.headers.get(LANG_HEADER), request.cookies.get(LANG_COOKIE))
        token = set_lang(lang)
        try:
            response = await call_next(request)
        finally:
            reset_lang(token)
        response.headers.add_vary_header("X-Lang")
        if lang == "ko" or not response.headers.get("content-type", "").startswith("application/json"):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            data = json.loads(body)
        except ValueError:
            new = body
        else:
            new = json.dumps(translate_json(data), ensure_ascii=False, separators=(",", ":")).encode()
        out = Response(content=new, status_code=response.status_code)
        out.raw_headers = [(k, v) for k, v in response.raw_headers if k.lower() != b"content-length"]
        out.raw_headers.append((b"content-length", str(len(new)).encode()))
        return out

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, e: RequestValidationError):
        # 기본 처리기는 입력값(비밀번호 포함)을 그대로 되돌려 보내고, 짝 없는 서로게이트 문자가 섞이면 500 이 난다.
        # 위치·종류·메시지만 돌려준다.
        errors = [{"loc": list(err.get("loc", ())), "type": err.get("type"), "msg": err.get("msg")} for err in e.errors()]
        return JSONResponse(status_code=422, content={"detail": {
            "code": "validation_error", "message_ko": "입력값을 확인해 주세요.", "errors": errors,
        }})

    @app.exception_handler(LLMError)
    async def _llm_error(_: Request, e: LLMError):
        log.warning("LLM 오류 (%s): %s", type(e).__name__, e.detail)
        return JSONResponse(status_code=e.status_code,
                            content={"detail": {"code": type(e).__name__, "message_ko": e.user_message_ko}})

    @app.exception_handler(AppError)
    async def _app_error(_: Request, e: AppError):
        return JSONResponse(status_code=e.status_code, content={"detail": {"code": e.code, "message_ko": e.message_ko}})

    @app.exception_handler(AuthRequiredError)
    async def _auth_required(_: Request, e: AuthRequiredError):
        return JSONResponse(status_code=401, content={"detail": {"code": "auth_required", "message_ko": e.message_ko}})

    @app.exception_handler(AuthUnavailableError)
    async def _auth_unavailable(_: Request, e: AuthUnavailableError):
        return JSONResponse(status_code=503, content={"detail": {"code": "auth_unavailable", "message_ko": e.message_ko}})

    @app.exception_handler(MeshRegenerationError)
    async def _regen(_: Request, e: MeshRegenerationError):
        return JSONResponse(status_code=409, content={"detail": {"code": "mesh_unavailable", "message_ko": e.message_ko}})

    @app.exception_handler(GeometryChangedError)
    async def _geometry_changed(_: Request, e: GeometryChangedError):
        # 배포 사이 형상이 바뀌었고 다시 검증해도 통과하지 못한 옛 버전 (MeshRegenerationError 보다 먼저 잡힌다)
        return JSONResponse(status_code=409, content={"detail": {
            "code": "geometry_changed", "message_ko": e.message_ko, "errors": e.errors,
        }})

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
            "code": "validation_failed", "message_ko": e.message_ko, "errors": e.errors,
        }})

    # 응답의 mesh_url 등은 API 루트 기준 경로(/designs/...)이고, 프론트엔드가 API_BASE(/api)를 앞에 붙인다.
    # 권한은 엔드포인트마다 의존성으로 정한다:
    #  - 누구나: 상태 확인, 종 목록, 회원가입·로그인, 커뮤니티 읽기, 공유된 설계 보기
    #  - 회원: 설계 만들기·수정·내역, 내 정보·반려동물, 가상 케이지 배치안, 글·댓글 쓰기, 제작 신청
    for router in (meta.router, auth_api.router, me.router, habitats.router, designs.router, layouts.router,
                   community.router, market.router, waitlist.router):
        app.include_router(router, prefix=prefix)
    return app


app = create_app()
