"""DB 연결 (SQLAlchemy 2.x). 로컬은 SQLite, 배포는 Postgres(Neon 등)."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, inspect, text
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
        pool_size=3,
        max_overflow=7,
        # 연결을 기다리다 막힌 요청이 오래 쌓이지 않게 짧게 (API 는 요청이 끝나기 전 연결을 바로 돌려준다: deps.py)
        pool_timeout=10,
        pool_recycle=300,     # 5분 넘은 연결은 재생성
        connect_args={
            "prepare_threshold": None,  # PgBouncer(Neon -pooler) 트랜잭션 모드에서 서버측 prepared statement 비활성화
            "connect_timeout": 15,      # Neon compute 콜드 스타트 여유
        },
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# 기존 DB(이미 만들어진 테이블)에 나중에 추가한 열. create_all 은 기존 테이블을 바꾸지 않으므로 직접 추가한다.
# 모두 NULL 허용이라 이전 버전 코드가 같은 DB 를 써도 문제가 없다 (추가만 하고 지우거나 바꾸지 않는다).
MIGRATION_COLUMNS: list[tuple[str, str, str]] = [
    ("habitats", "owner_id", "VARCHAR(32)"),
    ("habitats", "pet_id", "VARCHAR(32)"),
    ("designs", "owner_id", "VARCHAR(32)"),
    ("designs", "title", "VARCHAR(80)"),
    ("design_versions", "created_by", "VARCHAR(32)"),
    ("users", "email", "VARCHAR(320)"),
    ("users", "email_key", "VARCHAR(320)"),
    ("users", "email_verified_at", "TIMESTAMP WITH TIME ZONE"),
    ("posts", "images", "JSON"),
    ("design_versions", "geometry", "JSON"),
    ("market_items", "layout", "JSON"),
    ("market_files", "dims_mm", "JSON"),
    ("market_files", "shared", "BOOLEAN"),
]
# (인덱스 이름, 테이블, 인덱스 정의). 정의는 Postgres·SQLite 공통 문법만 쓴다
MIGRATION_INDEXES: list[tuple[str, str, str]] = [
    ("ix_habitats_owner_id", "habitats", "INDEX {name} ON habitats (owner_id)"),
    ("ix_designs_owner_id", "designs", "INDEX {name} ON designs (owner_id)"),
    ("ix_design_versions_created_by", "design_versions", "INDEX {name} ON design_versions (created_by)"),
    ("ix_design_versions_created_at", "design_versions", "INDEX {name} ON design_versions (created_at)"),
    ("ix_users_email_key", "users", "INDEX {name} ON users (email_key)"),
    # 인증한 주소끼리만 겹치지 않게 (부분 유일 인덱스)
    ("ux_users_email_key_verified", "users",
     "UNIQUE INDEX {name} ON users (email_key) WHERE email_verified_at IS NOT NULL"),
]


def _migrate(conn) -> list[str]:
    """빠진 열·인덱스를 추가한다. 추가한 항목 이름을 돌려준다 (멱등)."""
    insp = inspect(conn)
    added = []
    tables = set(insp.get_table_names())
    for table, column, ddl in MIGRATION_COLUMNS:
        if table in tables and column not in {c["name"] for c in insp.get_columns(table)}:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            added.append(f"{table}.{column}")
    for name, table, definition in MIGRATION_INDEXES:
        # 이미 있으면 DDL 을 보내지 않는다 (CREATE INDEX IF NOT EXISTS 도 테이블 잠금을 먼저 잡아 쓰기를 막는다)
        if table in tables and name not in {i["name"] for i in insp.get_indexes(table)}:
            kind, rest = definition.split(" {name} ", 1)
            conn.execute(text(f"CREATE {kind} IF NOT EXISTS {name} {rest}"))
            added.append(name)
    return added


def init_db(engine: Engine) -> list[str]:
    from app import models  # noqa: F401 - 테이블 등록

    if engine.dialect.name == "postgresql":
        # 여러 인스턴스가 동시에 기동해도 CREATE TABLE/ALTER TABLE 이 충돌하지 않도록 직렬화
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(727274)"))
            Base.metadata.create_all(conn)
            return _migrate(conn)
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        return _migrate(conn)
