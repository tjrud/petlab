"""DB 연결 (SQLAlchemy 2.x). 로컬은 SQLite, 배포는 Postgres(Neon 등)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


log = logging.getLogger(__name__)

# libpq(psycopg) 가 이해하는 연결 옵션. 공급자가 붙이는 그 밖의 파라미터
# (예: Supabase 의 supa=base-pooler.x, Prisma 용 pgbouncer=true)는 libpq 가 거부하므로 제거한다.
_LIBPQ_PARAMS = {
    "sslmode", "sslrootcert", "sslcert", "sslkey", "sslcrl", "sslnegotiation", "channel_binding",
    "connect_timeout", "application_name", "options", "target_session_attrs", "gssencmode",
    "keepalives", "keepalives_idle", "keepalives_interval", "keepalives_count", "tcp_user_timeout",
}


def normalize_database_url(url: str) -> str:
    """Vercel Marketplace(Neon·Supabase)가 주는 postgres://, postgresql:// URL 을 psycopg3 드라이버 URL 로 바꾸고,
    libpq 가 모르는 쿼리 파라미터를 제거한다."""
    for prefix in ("postgres://", "postgresql://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            parts = urlsplit("postgresql+psycopg://" + url[len(prefix):])
            query = parse_qsl(parts.query, keep_blank_values=True)
            kept = [(k, v) for k, v in query if k in _LIBPQ_PARAMS]
            dropped = [k for k, _ in query if k not in _LIBPQ_PARAMS]
            if dropped:
                log.info("DB URL 에서 지원하지 않는 파라미터를 제거했습니다: %s", ", ".join(dropped))
            return urlunsplit(parts._replace(query=urlencode(kept)))
    return url


def is_ephemeral_database(database_url: str, ephemeral_filesystem: bool = False) -> bool:
    """데이터가 유지되지 않는 저장소인지. 메모리 DB 는 항상, SQLite 파일은 로컬 디스크가 휘발성인
    환경(컨테이너 이미지가 EPHEMERAL_FILESYSTEM=1 로 표시)에서만 해당한다. 배포 환경 경고 표시에 쓴다."""
    url = normalize_database_url(database_url)
    if not url.startswith("sqlite"):
        return False
    path = url.split("///", 1)[1] if "///" in url else ""
    return path in ("", ":memory:") or ephemeral_filesystem


def make_engine(database_url: str) -> Engine:
    url = normalize_database_url(database_url)
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(
        url,
        pool_pre_ping=True,   # 유휴 후 끊긴 연결(Neon scale-to-zero, 풀러 idle timeout) 감지
        pool_size=2,
        max_overflow=3,
        pool_recycle=300,     # 5분 넘은 연결은 재생성
        connect_args={
            "prepare_threshold": None,  # PgBouncer(Neon -pooler) 트랜잭션 모드에서 서버측 prepared statement 비활성화
            "connect_timeout": 15,      # Neon compute 콜드 스타트 여유
        },
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    from app import models  # noqa: F401 - 테이블 등록

    if engine.dialect.name == "postgresql":
        # 여러 인스턴스가 동시에 기동해도 CREATE TABLE 이 충돌하지 않도록 직렬화
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(727274)"))
            Base.metadata.create_all(conn)
    else:
        Base.metadata.create_all(engine)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    db = factory()
    try:
        yield db
    finally:
        db.close()
