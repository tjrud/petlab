"""DB 연결 (SQLAlchemy 2.x). 로컬은 SQLite, 배포는 Postgres(Neon 등)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Vercel/Neon 이 주는 postgres://, postgresql:// 를 psycopg3 드라이버 URL 로 바꾼다."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
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


# 기존 테이블에 나중에 추가한 열 (테이블, 열). create_all 은 없는 테이블만 만들므로 이미 있는 DB 에는
# init_db 가 ALTER TABLE ... ADD COLUMN 으로 채운다. 마이그레이션 도구를 들이기 전까지의 최소 장치라
# nullable 열 추가만 다룬다 (열 변경·삭제·데이터 이전이 필요해지면 Alembic 을 도입할 것).
ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("design_versions", "geometry_fingerprint"),
)


def _add_missing_columns(conn: Connection) -> list[str]:
    """ADDED_COLUMNS 중 기존 테이블에 없는 열을 추가한다. 반환: 추가한 '테이블.열' 목록."""
    insp = inspect(conn)
    tables = set(insp.get_table_names())
    quote = conn.dialect.identifier_preparer.quote
    added = []
    for table_name, column_name in ADDED_COLUMNS:
        if table_name not in tables:
            continue
        if column_name in {c["name"] for c in insp.get_columns(table_name)}:
            continue
        column = Base.metadata.tables[table_name].c[column_name]
        if not column.nullable:
            raise RuntimeError(f"추가 열은 nullable 이어야 합니다: {table_name}.{column_name}")
        ddl_type = column.type.compile(dialect=conn.dialect)
        conn.execute(text(f"ALTER TABLE {quote(table_name)} ADD COLUMN {quote(column_name)} {ddl_type}"))
        added.append(f"{table_name}.{column_name}")
    return added


def init_db(engine: Engine) -> None:
    from app import models  # noqa: F401 - 테이블 등록

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # 여러 인스턴스가 동시에 기동해도 CREATE TABLE / ALTER TABLE 이 충돌하지 않도록 직렬화
            conn.execute(text("SELECT pg_advisory_xact_lock(727274)"))
        Base.metadata.create_all(conn)
        _add_missing_columns(conn)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    db = factory()
    try:
        yield db
    finally:
        db.close()
