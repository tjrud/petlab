"""회원·반려동물·설계 소유권/공유·사용량 제한·커뮤니티·DB 마이그레이션."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text

from app.auth import COOKIE_NAME
from app.db import init_db
from app.main import create_app
from app.models import CageLayout, Comment, Design, DesignVersion, Habitat, Pet, Post, User
from tests.api_helpers import (
    PG_URL,
    PW,
    admin_login,
    create_habitat,
    habitat_body,
    make_design,
    signup,
    use,
)
from tests.api_helpers import SYRIAN_CAGE as CAGE
from tests.api_helpers import member_settings as settings


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


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


WRONG_CURRENT = {"code": "invalid_credentials", "message_ko": "현재 비밀번호가 올바르지 않아요."}


def test_password_change_wrong_current_then_limited(client):
    c = use(client, signup(client, "user_1"))
    wrong = {"current_password": "wrong", "new_password": "new-password-1"}
    limit = client.app.state.password_limiter.max_failures
    for _ in range(limit):
        r = c.post("/me/password", json=wrong)
        assert r.status_code == 400 and r.json()["detail"] == WRONG_CURRENT
    # 상한까지 틀린 뒤에는 맞는 비밀번호여도 잠시 막힌다
    r = c.post("/me/password", json={"current_password": PW, "new_password": "new-password-1"})
    assert r.status_code == 429
    assert r.json()["detail"] == {"code": "too_many_attempts",
                                  "message_ko": "비밀번호 확인 시도가 너무 많아요. 15분 뒤에 다시 시도해 주세요."}


def test_email_change_wrong_password(client):
    c = use(client, signup(client, "user_1"))
    r = c.patch("/me/email", json={"email": "new@example.com", "current_password": "wrong"})
    assert r.status_code == 400 and r.json()["detail"] == WRONG_CURRENT


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


def test_rows_whose_species_or_size_left_the_rules_show_raw_keys(client):
    """규칙 파일(species.yaml)에서 빠진 종·크기로 저장된 옛 행도 500 없이 키를 이름 자리에 보여 준다."""
    signup(client, "user_a")
    with client.app.state.session_factory() as db:
        uid = db.scalar(select(User.id).where(User.username == "user_a"))
        pet = Pet(owner_id=uid, name="콩이", species="ghost", size="tiny")
        hab = Habitat(owner_id=uid, species="hamster", size="ghost", count=1,
                      cage_width_mm=600, cage_depth_mm=400, cage_height_mm=300)
        lay = CageLayout(owner_id=uid, name="옛 배치", species="ghost", size="tiny",
                         cage_width_mm=600, cage_depth_mm=400, cage_height_mm=300, items=[])
        db.add_all([pet, hab, lay])
        db.commit()
        pid, hid, lid = pet.id, hab.id, lay.id
    got = client.get(f"/me/pets/{pid}").json()
    assert (got["species_name_ko"], got["size_name_ko"]) == ("ghost", "tiny")
    got = client.get(f"/habitats/{hid}").json()
    assert (got["species_name_ko"], got["size_name_ko"]) == ("햄스터", "ghost")
    assert client.get(f"/layouts/{lid}").json()["size_name_ko"] == "tiny"
    assert client.get("/layouts").json()[0]["size_name_ko"] == "tiny"
    # 규칙에 있는 종·크기는 한국어 이름
    p = client.post("/me/pets", json={"name": "두부", "species": "hamster", "size": "syrian"}).json()
    assert (p["species_name_ko"], p["size_name_ko"]) == ("햄스터", "골든 (시리안)")


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
    assert client.post("/habitats", json=habitat_body(pet_id=pet["id"])).status_code == 404  # 남의 반려동물로 등록 불가
    assert use(client, None).get(f"/designs/{d['id']}").status_code == 404

    # 관리자는 모든 설계를 볼 수 있지만(운영) 소유자는 아니다: 대신 수정·공유하지 못하고, 내역 목록에는 자기 것만
    admin_login(client)
    got = client.get(f"/designs/{d['id']}")
    assert got.status_code == 200 and got.json()["is_owner"] is False
    assert client.post(f"/designs/{d['id']}/revise", json={"prompt": "더 크게"}).status_code == 404
    r = client.post("/community/posts", json={"title": "대신 공유", "body": "x", "design_id": d["id"]})
    assert r.status_code == 404
    assert use(client, None).get(f"/designs/{d['id']}").status_code == 404  # 여전히 비공개
    admin_login(client)
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
        r = c.post("/designs", json={"habitat_id": create_habitat(c), "prompt": "넷째"})
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


# 대문자·끝 줄바꿈 id: 경로의 id 는 소문자 16진수 32자리 전체가 맞아야(fullmatch) 찾는다.
# Postgres 의 VARCHAR(32) 에는 33자(끝 줄바꿈) id 행을 넣을 수 없으므로 그 경우는 SQLite 에서만 넣는다.
MALFORMED_IDS = ("A" * 32,) if PG_URL else ("A" * 32, "c" * 32 + "\n")


def test_rows_under_malformed_ids_are_not_reachable(client):
    """그런 id 로 저장된 행이 있어도(내 것이라도) 경로로는 닿지 않는다: 404."""
    signup(client, "user_a")
    real = make_design(client)
    with client.app.state.session_factory() as db:
        uid = db.scalar(select(User.id).where(User.username == "user_a"))
        # 설계는 버전이 있어야 형식 검사 말고는 막는 것이 없다 (버전이 없으면 다른 이유로 404)
        v = db.scalar(select(DesignVersion).where(DesignVersion.design_id == real["id"]))
        version_cols = {k: getattr(v, k) for k in DesignVersion.__table__.columns.keys() if k not in ("id", "design_id")}
        for bad in MALFORMED_IDS:
            hab = Habitat(id=bad, owner_id=uid, species="hamster", size="syrian", count=1,
                          cage_width_mm=600, cage_depth_mm=400, cage_height_mm=300)
            db.add_all([
                Pet(id=bad, owner_id=uid, name="콩이", species="hamster", size="syrian"), hab,
                CageLayout(id=bad, owner_id=uid, name="x", species="hamster", size="syrian",
                           cage_width_mm=600, cage_depth_mm=400, cage_height_mm=300, items=[]),
                Design(id=bad, habitat=hab, owner_id=uid),
                Post(id=bad, author_id=uid, title="t", body="b"),
            ])
            db.flush()
            db.add_all([Comment(id=bad, post_id=bad, author_id=uid, body="c"),
                        DesignVersion(design_id=bad, **version_cols)])
        db.commit()
    for bad in MALFORMED_IDS:
        q = bad.replace("\n", "%0A")
        for path in (f"/me/pets/{q}", f"/habitats/{q}", f"/layouts/{q}", f"/community/posts/{q}", f"/designs/{q}"):
            assert client.get(path).status_code == 404, path
        assert client.delete(f"/community/comments/{q}").status_code == 404, q


def test_body_ids_reject_trailing_newline(client):
    """요청 본문의 id 는 pydantic(rust regex) 이 검사해 끝 줄바꿈도 422. OpenAPI 의 pattern 은 그대로다."""
    signup(client, "user_a")
    pet = client.post("/me/pets", json={"name": "콩이", "species": "hamster", "size": "syrian"}).json()
    assert client.post("/habitats", json=habitat_body(pet_id=pet["id"] + "\n")).status_code == 422
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert schemas["HabitatIn"]["properties"]["pet_id"]["anyOf"][0]["pattern"] == "^[0-9a-f]{32}$"


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
        assert {"created_by", "geometry"} <= cols["design_versions"]
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
