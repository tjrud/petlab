"""API 통합 테스트 도우미: 설정 팩토리, 회원 로그인, 사육 환경·설계 생성.

모의 해석기 + 임시 DB + 임시 메시 캐시를 쓰고 .env 는 읽지 않는다.
"""

from __future__ import annotations

import atexit
import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth import COOKIE_NAME
from app.config import Settings

SYRIAN_CAGE = {"width_mm": 600, "depth_mm": 400, "height_mm": 300}
ADMIN = {"username": "admin", "password": "correct horse battery staple"}
AUTH_ON = {"admin_username": ADMIN["username"], "admin_password": ADMIN["password"], "session_secret": "s" * 40}
PW = "hamster-love-123"


def make_settings(tmp_path, **kw) -> Settings:
    """모의 해석기 + 임시 SQLite(test.db) + 임시 메시 캐시. .env 는 읽지 않는다."""
    base = {"llm_provider": "mock", "database_url": f"sqlite:///{tmp_path / 'test.db'}",
            "mesh_cache_dir": tmp_path / "meshes", "_env_file": None}
    return Settings(**(base | kw))


# TEST_PG_URL=postgresql+psycopg://user@host:port 를 주면 member_settings 를 쓰는 테스트는 테스트마다 새 Postgres DB 로
# 실행한다 (방언 차이 확인용)
PG_URL = os.environ.get("TEST_PG_URL")
_pg_dbs: dict[str, str] = {}


def _drop_pg_dbs() -> None:
    """테스트가 만든 Postgres DB 를 끝날 때 지운다 (쌓이면 디스크를 다 쓴다)."""
    if not _pg_dbs:
        return
    with create_engine(f"{PG_URL}/postgres", isolation_level="AUTOCOMMIT").connect() as conn:
        for url in _pg_dbs.values():
            conn.execute(text(f'DROP DATABASE IF EXISTS "{url.rsplit("/", 1)[1]}" WITH (FORCE)'))
    _pg_dbs.clear()


if PG_URL:
    atexit.register(_drop_pg_dbs)


def db_url(tmp_path) -> str:
    """회원 테스트용 DB: 기본은 임시 SQLite(m.db), TEST_PG_URL 이 있으면 tmp_path 마다 새 Postgres DB."""
    if not PG_URL:
        return f"sqlite:///{tmp_path / 'm.db'}"
    key = str(tmp_path)
    if key not in _pg_dbs:
        name = "t_" + uuid4().hex[:12]
        with create_engine(f"{PG_URL}/postgres", isolation_level="AUTOCOMMIT").connect() as conn:
            conn.execute(text(f"CREATE DATABASE {name}"))
        _pg_dbs[key] = f"{PG_URL}/{name}"
    return _pg_dbs[key]


def member_settings(tmp_path, **kw) -> Settings:
    """회원 기능용: 관리자 인증 켬 + db_url(tmp_path) + 가입 IP 제한을 사실상 끔(1000)."""
    return make_settings(tmp_path, **({"database_url": db_url(tmp_path), **AUTH_ON,
                                       "signup_per_ip_per_hour": 1000} | kw))


def signup(c: TestClient, username: str, nickname: str | None = None, password: str = PW) -> str:
    c.cookies.clear()
    r = c.post("/auth/signup", json={"username": username, "nickname": nickname or f"{username}님", "password": password})
    assert r.status_code == 201, r.text
    return r.cookies[COOKIE_NAME]


def admin_login(c: TestClient) -> str:
    c.cookies.clear()
    r = c.post("/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return r.cookies[COOKIE_NAME]


def use(c: TestClient, token: str | None) -> TestClient:
    c.cookies.clear()
    if token:
        c.cookies.set(COOKIE_NAME, token)
    return c


def habitat_body(cage: dict = SYRIAN_CAGE, size: str = "syrian", count: int = 1, **extra) -> dict:
    """POST /habitats 본문 (햄스터). extra 는 pet_id 처럼 있을 때만 넣는 필드."""
    return {"species": "hamster", "size": size, "count": count, "cage": cage, **extra}


def create_habitat(c: TestClient, cage: dict = SYRIAN_CAGE, size: str = "syrian", count: int = 1, **extra) -> str:
    """사육 환경을 만들고 id 를 돌려준다 (201 이 아니면 실패)."""
    r = c.post("/habitats", json=habitat_body(cage, size, count, **extra))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def make_design(c: TestClient, prompt: str = "은신처를 왼쪽에", pet_id: str | None = None) -> dict:
    hid = create_habitat(c, **({"pet_id": pet_id} if pet_id else {}))
    r = c.post("/designs", json={"habitat_id": hid, "prompt": prompt})
    assert r.status_code == 201, r.text
    return r.json()
