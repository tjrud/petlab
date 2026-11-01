"""회원·반려동물·설계 소유권/공유·사용량 제한·커뮤니티·DB 마이그레이션."""

from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.auth import COOKIE_NAME
from app.config import Settings
from app.db import init_db
from app.main import create_app

CAGE = {"width_mm": 600, "depth_mm": 400, "height_mm": 300}
ADMIN = {"username": "admin", "password": "correct horse battery staple"}
PW = "hamster-love-123"


# TEST_PG_URL=postgresql+psycopg://user@host:port 를 주면 테스트마다 새 Postgres DB 로 실행한다 (방언 차이 확인용)
PG_URL = os.environ.get("TEST_PG_URL")
_pg_dbs: dict[str, str] = {}


def _db_url(tmp_path) -> str:
    if not PG_URL:
        return f"sqlite:///{tmp_path / 'm.db'}"
    key = str(tmp_path)
    if key not in _pg_dbs:
        name = "t_" + uuid4().hex[:12]
        with create_engine(f"{PG_URL}/postgres", isolation_level="AUTOCOMMIT").connect() as conn:
            conn.execute(text(f"CREATE DATABASE {name}"))
        _pg_dbs[key] = f"{PG_URL}/{name}"
    return _pg_dbs[key]


def settings(tmp_path, **kw) -> Settings:
    base = dict(llm_provider="mock", database_url=_db_url(tmp_path),
                mesh_cache_dir=tmp_path / "meshes", admin_username=ADMIN["username"],
                admin_password=ADMIN["password"], session_secret="s" * 40, signup_per_ip_per_hour=1000,
                _env_file=None)
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


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


def make_design(c: TestClient, prompt: str = "은신처를 왼쪽에", pet_id: str | None = None) -> dict:
    hab = {"species": "hamster", "size": "syrian", "count": 1, "cage": CAGE}
    if pet_id:
        hab["pet_id"] = pet_id
    r = c.post("/habitats", json=hab)
    assert r.status_code == 201, r.text
    r = c.post("/designs", json={"habitat_id": r.json()["id"], "prompt": prompt})
    assert r.status_code == 201, r.text
    return r.json()


# ── 회원가입·로그인 ─────────────────────────────────────────


def test_signup_logs_in_and_me(client):
    signup(client, "Kim_01", " 햄찌맘 ")
    me = client.get("/auth/me").json()
    assert me["authenticated"] and me["user"]["username"] == "kim_01" and me["user"]["nickname"] == "햄찌맘"
    assert me["user"]["role"] == "member"
    info = client.get("/me").json()
    assert info["stats"] == {"pets": 0, "designs": 0, "posts": 0}
    assert info["design_quota"] == {"used": 0, "limit": 20, "remaining": 20}


@pytest.mark.parametrize("body,code", [
    ({"username": "kim_01", "nickname": "다른닉", "password": PW}, "username_taken"),
    ({"username": "lee_02", "nickname": "햄찌맘", "password": PW}, "nickname_taken"),
    ({"username": "admin", "nickname": "어드민", "password": PW}, "username_taken"),
    ({"username": "local", "nickname": "로컬", "password": PW}, "username_taken"),
    ({"username": "park_03", "nickname": "관리자", "password": PW}, "nickname_taken"),
    ({"username": "park_03", "nickname": "NestForge공식", "password": PW}, "nickname_taken"),
    ({"username": "park_003", "nickname": "박씨", "password": "PARK_003"}, "weak_password"),
])
def test_signup_conflicts(client, body, code):
    signup(client, "kim_01", "햄찌맘")
    client.cookies.clear()
    r = client.post("/auth/signup", json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == code, r.text


def test_nickname_unique_case_insensitive(client):
    signup(client, "user_a", "Hammy")
    client.cookies.clear()
    r = client.post("/auth/signup", json={"username": "user_b", "nickname": "hammy", "password": PW})
    assert r.status_code == 409


@pytest.mark.parametrize("body", [
    {"username": "ab", "nickname": "닉네임", "password": PW},            # 아이디 너무 짧음
    {"username": "한글아이디", "nickname": "닉네임", "password": PW},     # 허용 문자 아님
    {"username": "user_c", "nickname": "닉", "password": PW},            # 닉네임 너무 짧음
    {"username": "user_c", "nickname": "닉네임\n둘째줄", "password": PW},
    {"username": "user_c", "nickname": "닉네임", "password": "short"},   # 비밀번호 8자 미만
    {"username": "user_c", "nickname": "닉네임", "password": PW, "role": "admin"},  # 역할 지정 불가
])
def test_signup_validation(client, body):
    assert client.post("/auth/signup", json=body).status_code == 422


def test_signup_rate_limited_per_ip(tmp_path):
    with TestClient(create_app(settings(tmp_path, signup_per_ip_per_hour=2))) as c:
        signup(c, "user_1")
        signup(c, "user_2")
        c.cookies.clear()
        r = c.post("/auth/signup", json={"username": "user_3", "nickname": "셋째", "password": PW})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_signups"


def test_signup_disabled(tmp_path):
    with TestClient(create_app(settings(tmp_path, signup_enabled=False))) as c:
        r = c.post("/auth/signup", json={"username": "user_1", "nickname": "첫째", "password": PW})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "signup_closed"
        assert c.get("/auth/me").json()["signup_enabled"] is False


def test_member_login_logout(client):
    signup(client, "user_1")
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": "user_1", "password": "wrong-pass"}).status_code == 401
    assert client.post("/auth/login", json={"username": "nobody", "password": PW}).status_code == 401
    r = client.post("/auth/login", json={"username": " USER_1 ", "password": PW})  # 대소문자·공백 무시
    assert r.status_code == 200 and r.json()["user"]["username"] == "user_1"
    assert client.get("/designs").status_code == 200
    client.post("/auth/logout", json={})
    assert client.get("/designs").status_code == 401


def test_admin_cannot_login_with_member_style_password(client):
    """관리자 행에는 비밀번호 해시가 없어 회원 경로로는 로그인할 수 없다."""
    admin_login(client)
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": "admin", "password": PW}).status_code == 401


def test_password_change_revokes_other_sessions(client):
    old = signup(client, "user_1")
    other_device = old
    r = use(client, old).post("/me/password", json={"current_password": "wrong", "new_password": "new-password-1"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_credentials"
    r = use(client, old).post("/me/password", json={"current_password": PW, "new_password": "new-password-1"})
    assert r.status_code == 200
    new = r.cookies[COOKIE_NAME]
    assert use(client, other_device).get("/designs").status_code == 401  # 다른 기기 로그아웃
    assert use(client, new).get("/designs").status_code == 200           # 이 기기는 유지
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": "user_1", "password": PW}).status_code == 401
    assert client.post("/auth/login", json={"username": "user_1", "password": "new-password-1"}).status_code == 200


def test_admin_profile_and_password_are_env_managed(client):
    admin_login(client)
    assert client.post("/me/password", json={"current_password": "x", "new_password": "y" * 10}).status_code == 403
    assert client.patch("/me", json={"nickname": "새이름"}).status_code == 403


def test_nickname_change(client):
    signup(client, "user_a", "에이")
    signup(client, "user_b", "비이")
    assert client.patch("/me", json={"nickname": "에이"}).status_code == 409
    assert client.patch("/me", json={"nickname": "운영자입니다"}).status_code == 409
    r = client.patch("/me", json={"nickname": "새비이"})
    assert r.status_code == 200 and r.json()["user"]["nickname"] == "새비이"


# ── 반려동물 ───────────────────────────────────────────────


def test_pet_crud_and_isolation(client):
    a = signup(client, "user_a")
    r = client.post("/me/pets", json={"name": "콩이", "species": "hamster", "size": "dwarf", "sex": "female",
                                      "birth_date": "2025-03-01", "notes": "겁이 많아요", "cage": CAGE})
    assert r.status_code == 201, r.text
    pet = r.json()
    assert pet["size_name_ko"] and pet["cage"]["width_mm"] == 600 and pet["sex"] == "female"
    assert len(client.get("/me/pets").json()) == 1
    r = client.put(f"/me/pets/{pet['id']}", json={"name": "콩순이", "species": "hamster", "size": "syrian"})
    assert r.status_code == 200 and r.json()["name"] == "콩순이" and r.json()["cage"] is None

    b = signup(client, "user_b")
    assert use(client, b).get(f"/me/pets/{pet['id']}").status_code == 404
    assert client.put(f"/me/pets/{pet['id']}", json={"name": "x", "species": "hamster", "size": "syrian"}).status_code == 404
    assert client.delete(f"/me/pets/{pet['id']}").status_code == 404
    assert client.get("/me/pets").json() == []

    assert use(client, a).delete(f"/me/pets/{pet['id']}").status_code == 204
    assert client.get("/me/pets").json() == []


@pytest.mark.parametrize("body", [
    {"name": "", "species": "hamster", "size": "dwarf"},
    {"name": "콩이", "species": "hamster", "size": "dwarf", "birth_date": (date.today() + timedelta(days=1)).isoformat()},
    {"name": "콩이", "species": "hamster", "size": "dwarf", "sex": "other"},
    {"name": "콩이", "species": "hamster", "size": "dwarf", "notes": "x" * 501},
    {"name": "콩이", "species": "hamster", "size": "dwarf", "cage": {"width_mm": 10, "depth_mm": 400, "height_mm": 300}},
])
def test_pet_validation(client, body):
    signup(client, "user_a")
    assert client.post("/me/pets", json=body).status_code == 422


def test_pet_unknown_species_and_limit(client):
    signup(client, "user_a")
    r = client.post("/me/pets", json={"name": "토끼", "species": "rabbit", "size": "x"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_input"
    for i in range(20):
        assert client.post("/me/pets", json={"name": f"p{i}", "species": "hamster", "size": "dwarf"}).status_code == 201
    r = client.post("/me/pets", json={"name": "p21", "species": "hamster", "size": "dwarf"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "too_many_pets"


# ── 설계 소유권·내역·공유 ────────────────────────────────────


def test_design_ownership_and_history(client):
    a = signup(client, "user_a", "에이")
    pet = client.post("/me/pets", json={"name": "콩이", "species": "hamster", "size": "syrian"}).json()
    d = make_design(client, pet_id=pet["id"])
    assert d["is_owner"] and not d["shared"] and d["owner_nickname"] == "에이" and d["title"]
    lst = client.get("/designs").json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == d["id"] and lst["items"][0]["pet_name"] == "콩이"
    mesh = d["current"]["items"][0]["mesh_url"]

    b = signup(client, "user_b")
    assert use(client, b).get("/designs").json()["total"] == 0
    for path in (f"/designs/{d['id']}", mesh, f"/designs/{d['id']}/export?format=stl",
                 f"/habitats/{d['habitat']['id']}"):
        assert client.get(path).status_code == 404, path
    assert client.post(f"/designs/{d['id']}/revise", json={"prompt": "더 크게"}).status_code == 404
    assert client.post("/designs", json={"habitat_id": d["habitat"]["id"], "prompt": "남의 환경"}).status_code == 404
    assert client.post("/waitlist", json={"email": "b@example.com", "design_id": d["id"]}).status_code == 404
    hab = {"species": "hamster", "size": "syrian", "count": 1, "cage": CAGE, "pet_id": pet["id"]}
    assert client.post("/habitats", json=hab).status_code == 404  # 남의 반려동물로 등록 불가
    assert use(client, None).get(f"/designs/{d['id']}").status_code == 404

    # 관리자는 모든 설계를 볼 수 있지만 내역 목록에는 자기 것(과 소유자 없는 옛 설계)만
    admin_login(client)
    assert client.get(f"/designs/{d['id']}").json()["is_owner"] is True
    assert client.get("/designs").json()["total"] == 0

    # 반려동물을 지워도 설계는 남는다
    use(client, a).delete(f"/me/pets/{pet['id']}")
    item = client.get("/designs").json()["items"][0]
    assert item["id"] == d["id"] and item["pet_name"] is None


def test_shared_design_is_viewable_read_only(client):
    a = signup(client, "user_a", "에이")
    d = make_design(client)
    r = client.post("/community/posts", json={"title": "제 설계 공유해요", "body": "어떤가요?", "design_id": d["id"]})
    assert r.status_code == 201, r.text
    post = r.json()
    assert post["design"]["id"] == d["id"] and post["design"]["version"] == 1 and post["design"]["item_labels"]
    assert client.get(f"/designs/{d['id']}").json()["shared"] is True
    assert client.get("/designs").json()["items"][0]["shared"] is True

    for token in (None, signup(client, "user_b")):
        use(client, token)
        got = client.get(f"/designs/{d['id']}")
        assert got.status_code == 200 and got.json()["is_owner"] is False
        assert client.get(d["current"]["items"][0]["mesh_url"]).status_code == 200
        assert client.get(f"/designs/{d['id']}/export?format=stl").status_code == 200
    # 공유돼도 수정·재공유는 소유자만
    assert client.post(f"/designs/{d['id']}/revise", json={"prompt": "더 크게"}).status_code == 404
    r = client.post("/community/posts", json={"title": "남의 설계", "body": "x", "design_id": d["id"]})
    assert r.status_code == 404

    # 글을 지우면 다시 비공개
    assert use(client, a).delete(f"/community/posts/{post['id']}").status_code == 204
    assert use(client, None).get(f"/designs/{d['id']}").status_code == 404


def test_design_quota(tmp_path):
    with TestClient(create_app(settings(tmp_path, design_daily_limit=2, design_global_daily_limit=3))) as c:
        signup(c, "user_a")
        d = make_design(c)
        assert c.post(f"/designs/{d['id']}/revise", json={"prompt": "더 크게"}).status_code == 201
        assert c.get("/me").json()["design_quota"] == {"used": 2, "limit": 2, "remaining": 0}
        r = c.post(f"/designs/{d['id']}/revise", json={"prompt": "또"})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "design_quota_exceeded"
        hid = d["habitat"]["id"]
        assert c.post("/designs", json={"habitat_id": hid, "prompt": "새로"}).status_code == 429

        signup(c, "user_b")
        make_design(c)  # 전체 3번째
        hab = c.post("/habitats", json={"species": "hamster", "size": "syrian", "count": 1, "cage": CAGE}).json()
        r = c.post("/designs", json={"habitat_id": hab["id"], "prompt": "넷째"})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "design_capacity_exceeded"

        admin_login(c)  # 관리자는 상한 없음
        make_design(c)
        assert c.get("/me").json()["design_quota"]["limit"] is None


# ── 커뮤니티 ───────────────────────────────────────────────


def test_community_flow_and_permissions(client):
    a = signup(client, "user_a", "에이")
    r = client.post("/community/posts", json={"title": "  첫 글  ", "body": "<script>alert(1)</script>\n안녕하세요"})
    assert r.status_code == 201
    post = r.json()
    assert post["title"] == "첫 글" and post["body"].startswith("<script>")  # 그대로 저장, 화면에서 글자로 표시
    assert post["can_edit"] and post["can_delete"] and post["author"] == {"nickname": "에이", "role": "member"}

    b = signup(client, "user_b", "비이")
    c1 = client.post(f"/community/posts/{post['id']}/comments", json={"body": "반가워요"}).json()
    assert c1["can_delete"] and c1["author"]["nickname"] == "비이"
    assert client.patch(f"/community/posts/{post['id']}", json={"title": "해킹"}).status_code == 403
    assert client.delete(f"/community/posts/{post['id']}").status_code == 403

    use(client, None)
    lst = client.get("/community/posts").json()
    assert lst["total"] == 1 and lst["items"][0]["comment_count"] == 1 and lst["items"][0]["has_design"] is False
    detail = client.get(f"/community/posts/{post['id']}").json()
    assert detail["can_edit"] is False and detail["comments"][0]["can_delete"] is False

    use(client, a)
    assert client.delete(f"/community/comments/{c1['id']}").status_code == 403  # 남의 댓글
    r = client.patch(f"/community/posts/{post['id']}", json={"body": "수정했어요"})
    assert r.status_code == 200 and r.json()["body"] == "수정했어요"
    use(client, b)
    assert client.delete(f"/community/comments/{c1['id']}").status_code == 204

    admin_login(client)  # 관리자는 남의 글을 지울 수 있다
    assert client.get(f"/community/posts/{post['id']}").json()["can_delete"] is True
    assert client.delete(f"/community/posts/{post['id']}").status_code == 204
    assert client.get(f"/community/posts/{post['id']}").status_code == 404


@pytest.mark.parametrize("body", [
    {"title": "", "body": "x"},
    {"title": "제목\n둘째줄", "body": "x"},
    {"title": "x" * 101, "body": "x"},
    {"title": "t", "body": "x" * 5001},
    {"title": "t", "body": "   "},
])
def test_post_validation(client, body):
    signup(client, "user_a")
    assert client.post("/community/posts", json=body).status_code == 422


def test_post_and_comment_limits_and_pagination(tmp_path):
    with TestClient(create_app(settings(tmp_path, post_daily_limit=3, comment_daily_limit=2))) as c:
        signup(c, "user_a")
        ids = [c.post("/community/posts", json={"title": f"글{i}", "body": "본문"}).json()["id"] for i in range(3)]
        r = c.post("/community/posts", json={"title": "넷째", "body": "본문"})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_posts"
        for _ in range(2):
            assert c.post(f"/community/posts/{ids[0]}/comments", json={"body": "댓글"}).status_code == 201
        assert c.post(f"/community/posts/{ids[0]}/comments", json={"body": "댓글"}).status_code == 429
        page = c.get("/community/posts?page=1&page_size=2").json()
        assert page["total"] == 3 and [p["title"] for p in page["items"]] == ["글2", "글1"]
        assert [p["title"] for p in c.get("/community/posts?page=2&page_size=2").json()["items"]] == ["글0"]


def test_unknown_ids_are_404_not_500(client):
    signup(client, "user_a")
    for path in ("/community/posts/nope", "/community/posts/" + "0" * 32, "/me/pets/nope", "/designs/nope"):
        assert client.get(path).status_code == 404, path
    assert client.delete("/community/comments/" + "0" * 32).status_code == 404


# ── 마이그레이션 ───────────────────────────────────────────


OLD_SCHEMA = [
    """CREATE TABLE habitats (id VARCHAR(32) PRIMARY KEY, species VARCHAR(32), size VARCHAR(32), count INTEGER,
       cage_width_mm FLOAT, cage_depth_mm FLOAT, cage_height_mm FLOAT, created_at DATETIME)""",
    """CREATE TABLE designs (id VARCHAR(32) PRIMARY KEY, habitat_id VARCHAR(32) REFERENCES habitats(id),
       created_at DATETIME)""",
    """CREATE TABLE design_versions (id INTEGER PRIMARY KEY AUTOINCREMENT, design_id VARCHAR(32), version INTEGER,
       prompt TEXT, provider VARCHAR(32), llm_attempts INTEGER, llm_spec JSON, effective_spec JSON, items JSON,
       report JSON, passed BOOLEAN, created_at DATETIME)""",
    """CREATE TABLE waitlist (id INTEGER PRIMARY KEY AUTOINCREMENT, email VARCHAR(320), design_id VARCHAR(32),
       version INTEGER, created_at DATETIME)""",
]


@pytest.mark.skipif(bool(PG_URL), reason="SQLite 전용 DDL (Postgres 마이그레이션은 별도 스크립트로 확인)")
def test_migration_from_previous_schema(tmp_path):
    """이전 버전 DB(소유자 열 없음)에 새 열·테이블이 추가되고, 옛 설계는 관리자만 본다."""
    url = f"sqlite:///{tmp_path / 'm.db'}"
    eng = create_engine(url)
    with eng.begin() as conn:
        for ddl in OLD_SCHEMA:
            conn.execute(text(ddl))
    eng.dispose()
    # 옛 설계를 하나 만든 것처럼 하기 위해: 새 앱으로 만들고 소유자 열을 비운다
    with TestClient(create_app(settings(tmp_path))) as c:
        cols = {t: {col["name"] for col in inspect(create_engine(url)).get_columns(t)}
                for t in ("habitats", "designs", "design_versions")}
        assert {"owner_id", "pet_id"} <= cols["habitats"] and {"owner_id", "title"} <= cols["designs"]
        assert "created_by" in cols["design_versions"]
        assert {"users", "pets", "posts", "comments"} <= set(inspect(create_engine(url)).get_table_names())
        signup(c, "user_a")
        d = make_design(c)
        with create_engine(url).begin() as conn:
            conn.execute(text("UPDATE designs SET owner_id = NULL, title = NULL"))
        assert c.get(f"/designs/{d['id']}").status_code == 404  # 소유자 없는 옛 설계 → 회원은 못 봄
        admin_login(c)
        got = c.get(f"/designs/{d['id']}").json()
        assert got["is_owner"] is True and got["title"]  # 제목은 첫 버전 요약에서
        assert c.get("/designs").json()["total"] == 1      # 관리자 내역에 옛 설계 포함
    assert init_db(create_engine(url)) == []  # 두 번째 실행은 아무것도 바꾸지 않는다


def test_design_title_from_prompt():
    from app.services.design_service import make_title

    assert make_title("  은신처를 왼쪽에  \n환기구 8개") == "은신처를 왼쪽에"
    long = "가" * 60
    assert make_title(long) == "가" * 39 + "…" and len(make_title(long)) == 40
    assert make_title("\n\n") == "맞춤 설계"


def test_explicit_nulls_are_accepted(client):
    """화면은 빈 선택 항목을 null 로 보낸다 (제약이 null 에 걸려 500 이 나던 문제)."""
    signup(client, "user_a")
    body = {"name": "콩이", "species": "hamster", "size": "syrian", "sex": "female", "birth_date": None,
            "notes": None, "cage": CAGE}
    r = client.post("/me/pets", json=body)
    assert r.status_code == 201, r.text
    assert client.put(f"/me/pets/{r.json()['id']}", json={**body, "cage": None}).status_code == 200
    post = client.post("/community/posts", json={"title": "t", "body": "b", "design_id": None,
                                                 "design_version": None}).json()
    r = client.patch(f"/community/posts/{post['id']}", json={"title": "새 제목", "body": None})
    assert r.status_code == 200 and r.json()["title"] == "새 제목" and r.json()["body"] == "b"
    assert client.post("/me/pets", json={**body, "notes": "x" * 501}).status_code == 422
