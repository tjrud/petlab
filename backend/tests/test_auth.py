"""관리자 인증: 사이트는 공개, API 는 관리자 로그인 후에만."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import COOKIE_NAME, LoginRateLimiter, issue_token, signing_key, verify_token
from app.config import Settings
from app.main import create_app

CAGE = {"width_mm": 600, "depth_mm": 400, "height_mm": 300}
HABITAT = {"species": "hamster", "size": "syrian", "count": 1, "cage": CAGE}
ADMIN = {"username": "admin", "password": "correct horse battery staple"}


def settings(tmp_path, **kw) -> Settings:
    base = dict(llm_provider="mock", database_url=f"sqlite:///{tmp_path / 'test.db'}",
                mesh_cache_dir=tmp_path / "meshes", admin_username=ADMIN["username"],
                admin_password=ADMIN["password"], session_secret="test-secret", _env_file=None)
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


def login(c: TestClient):
    r = c.post("/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return r


# ── 토큰 ───────────────────────────────────────────────────


def test_token_roundtrip_and_tamper():
    key = b"k" * 32
    tok = issue_token("admin", key, ttl_s=60, now=1000)
    assert verify_token(tok, key, now=1010) == "admin"
    assert verify_token(tok, key, now=1061) is None            # 만료
    assert verify_token(tok, b"x" * 32, now=1010) is None      # 다른 키
    body, sig = tok.split(".")
    forged_body = body[:-2] + ("AA" if body[-2:] != "AA" else "BB")
    assert verify_token(f"{forged_body}.{sig}", key, now=1010) is None  # 내용 변조
    for bad in (None, "", "abc", "a.b.c", ".", "x.y"):
        assert verify_token(bad, key) is None


def test_signing_key_falls_back_to_password_and_rotates(tmp_path):
    s1 = settings(tmp_path, session_secret=None)
    s2 = settings(tmp_path, session_secret=None, admin_password="another")
    assert signing_key(s1) != signing_key(s2)  # 비밀번호를 바꾸면 기존 세션 무효
    assert signing_key(settings(tmp_path)) == b"test-secret"


def test_rate_limiter():
    rl = LoginRateLimiter(max_failures=3, window_s=100)
    for t in range(3):
        assert not rl.blocked("ip", now=t)
        rl.record_failure("ip", now=t)
    assert rl.blocked("ip", now=10)
    assert not rl.blocked("ip", now=200)  # 시간이 지나면 풀림
    assert not rl.blocked("other", now=10)


# ── API 보호 ───────────────────────────────────────────────


def test_public_endpoints(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["auth_enabled"] is True
    me = client.get("/auth/me").json()
    assert me == {"auth_enabled": True, "authenticated": False, "username": None}


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/species", None),
    ("POST", "/habitats", HABITAT),
    ("GET", "/habitats/" + "0" * 32, None),
    ("POST", "/designs", {"habitat_id": "0" * 32, "prompt": "은신처"}),
    ("GET", "/designs/" + "0" * 32, None),
    ("POST", "/designs/" + "0" * 32 + "/revise", {"prompt": "더 크게"}),
    ("GET", "/designs/" + "0" * 32 + "/export?format=stl", None),
    ("GET", "/designs/" + "0" * 32 + "/versions/1/parts/0.stl", None),
    ("POST", "/waitlist", {"email": "a@example.com"}),
])
def test_protected_endpoints_require_login(client, method, path, body):
    r = client.request(method, path, json=body)
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth_required"


def test_login_then_full_flow_then_logout(client):
    r = login(client)
    assert r.json()["username"] == "admin"
    cookie = r.headers["set-cookie"]
    assert COOKIE_NAME in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert client.get("/auth/me").json()["authenticated"] is True

    hid = client.post("/habitats", json=HABITAT).json()["id"]
    d = client.post("/designs", json={"habitat_id": hid, "prompt": "은신처를 왼쪽에"}).json()
    assert client.get(d["current"]["items"][0]["mesh_url"]).status_code == 200
    assert client.get(f"/designs/{d['id']}/export?format=3mf").status_code == 200

    client.post("/auth/logout")
    assert client.get("/auth/me").json()["authenticated"] is False
    assert client.get(f"/designs/{d['id']}").status_code == 401


def test_wrong_credentials(client):
    for creds in ({"username": "admin", "password": "wrong"}, {"username": "root", "password": ADMIN["password"]}):
        r = client.post("/auth/login", json=creds)
        assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_credentials"
        assert COOKIE_NAME not in r.headers.get("set-cookie", "")
    assert client.get("/species").status_code == 401


def test_forged_or_expired_cookie_rejected(tmp_path):
    s = settings(tmp_path)
    with TestClient(create_app(s)) as c:
        c.cookies.set(COOKIE_NAME, issue_token("admin", b"attacker-key", 3600))
        assert c.get("/species").status_code == 401
        c.cookies.set(COOKIE_NAME, issue_token("admin", signing_key(s), ttl_s=-10))
        assert c.get("/species").status_code == 401
        c.cookies.set(COOKIE_NAME, issue_token("someone", signing_key(s), 3600))  # 관리자가 아닌 이름
        assert c.get("/species").status_code == 401
        c.cookies.set(COOKIE_NAME, issue_token("admin", signing_key(s), 3600))
        assert c.get("/species").status_code == 200


def test_login_is_rate_limited(client):
    for _ in range(10):
        assert client.post("/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    r = client.post("/auth/login", json=ADMIN)  # 맞는 비밀번호여도 잠시 막힘
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_attempts"


def test_auth_disabled_without_admin_password(tmp_path):
    with TestClient(create_app(settings(tmp_path, admin_password=None))) as c:
        assert c.get("/health").json()["auth_enabled"] is False
        assert c.get("/species").status_code == 200
        assert c.get("/auth/me").json() == {"auth_enabled": False, "authenticated": True, "username": None}
