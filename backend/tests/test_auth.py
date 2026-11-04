"""인증: 세션 토큰·관리자 로그인·보호 경로·실패 처리 (회원 기능은 test_members.py)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest
from fastapi.testclient import TestClient

from app.auth import (
    COOKIE_NAME,
    AuthUnavailableError,
    LoginRateLimiter,
    client_ip,
    client_key,
    issue_token,
    signing_key,
    usage_ip_key,
    verify_token,
)
from app.config import Settings
from app.main import create_app
from tests.api_helpers import (
    ADMIN,
    AUTH_ON,
    create_habitat,
    habitat_body,
    make_settings,
)

HABITAT = habitat_body()
SECRET = AUTH_ON["session_secret"]


def settings(tmp_path, **kw) -> Settings:
    return make_settings(tmp_path, **(AUTH_ON | kw))


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


PROTECTED = "/designs"  # 로그인이 필요한 대표 경로 (내 설계 목록)


def login(c: TestClient):
    r = c.post("/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return r


def admin_token(s: Settings, ttl_s: float = 3600) -> str:
    """관리자 계정 행의 id 로 서명한 세션 토큰."""
    from app.auth import ensure_admin_user
    from app.db import init_db, make_engine, make_session_factory

    engine = make_engine(s.database_url)
    init_db(engine)
    db = make_session_factory(engine)()
    try:
        u = ensure_admin_user(db, s)
        return issue_token(u.id, signing_key(s), ttl_s, ver=u.session_version)
    finally:
        db.close()


# ── 토큰 ───────────────────────────────────────────────────


def test_token_roundtrip_and_tamper():
    key = b"k" * 32
    tok = issue_token("u1", key, ttl_s=60, now=1000, ver=3)
    assert verify_token(tok, key, now=1010) == {"sub": "u1", "ver": 3}
    assert verify_token(tok, key, now=1061) is None            # 만료
    assert verify_token(tok, b"x" * 32, now=1010) is None      # 다른 키
    body, sig = tok.split(".")
    forged_body = body[:-2] + ("AA" if body[-2:] != "AA" else "BB")
    assert verify_token(f"{forged_body}.{sig}", key, now=1010) is None  # 내용 변조
    for bad in (None, "", "abc", "a.b.c", ".", "x.y"):
        assert verify_token(bad, key) is None


def test_verify_token_never_raises():
    key = b"k" * 32
    for bad in ("é.x", "a" * 5000 + ".b", "abc.%%%", "!!!.AAAA", "\x00.\x00", "e30.é"):
        assert verify_token(bad, key) is None
    # 서명은 맞지만 내용이 JSON 이 아니거나 필드가 빠진 경우
    for raw in (b"not json", b"{}", b'{"sub":1,"exp":9999999999,"ver":1}', b'{"sub":"a","exp":"x","ver":1}',
                b'{"sub":"a","exp":9999999999}', b'{"sub":"a","exp":9999999999,"ver":"1"}'):
        body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(hmac.new(key, body.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
        assert verify_token(f"{body}.{sig}", key) is None


def test_signing_key_requires_secret_and_rotates_with_password(tmp_path):
    base = signing_key(settings(tmp_path))
    assert base != SECRET.encode()  # 비밀값을 그대로 쓰지 않는다
    assert signing_key(settings(tmp_path, admin_password="another password!")) != base  # 비밀번호 교체 → 세션 무효
    assert signing_key(settings(tmp_path, session_secret="t" * 40)) != base  # 서명 키 교체 → 세션 무효
    # SESSION_SECRET 이 없거나 짧으면 비밀번호에서 키를 유도하지 않고 거부한다
    for secret in (None, "", "short-secret"):
        with pytest.raises(AuthUnavailableError):
            signing_key(settings(tmp_path, session_secret=secret))


def test_rate_limiter():
    rl = LoginRateLimiter(max_failures=3, window_s=100)
    for t in range(3):
        assert not rl.blocked("ip", now=t)
        rl.record_failure("ip", now=t)
    assert rl.blocked("ip", now=10)
    assert not rl.blocked("ip", now=200)  # 시간이 지나면 풀림
    assert not rl.blocked("other", now=10)
    assert len(rl) == 0  # 지난 기록과 빈 키는 지운다


def test_rate_limiter_memory_is_bounded():
    rl = LoginRateLimiter(max_failures=3, window_s=100, max_keys=50)
    for i in range(1000):
        rl.record_failure(f"ip{i}", now=1)
    assert len(rl) == 50
    assert not rl.blocked("ip0", now=2)  # 가장 오래된 키부터 버림


def test_client_key(tmp_path):
    from starlette.requests import Request

    def req(headers: dict, host: str = "10.0.0.1"):
        return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
                        "client": (host, 1234)})

    s = settings(tmp_path)
    assert client_key(s, req({"x-vercel-forwarded-for": "1.2.3.4"})) == "10.0.0.1"  # 헤더를 믿도록 설정하지 않음
    s = settings(tmp_path, client_ip_header="x-vercel-forwarded-for")
    assert client_key(s, req({"x-vercel-forwarded-for": "1.2.3.4, 5.6.7.8"})) == "1.2.3.4"
    assert client_key(s, req({})) == "10.0.0.1"
    # IPv6 는 /64 로 묶는다
    a = client_key(s, req({"x-vercel-forwarded-for": "2001:db8:1:2::1"}))
    b = client_key(s, req({"x-vercel-forwarded-for": "2001:db8:1:2:ffff::9"}))
    assert a == b == "2001:db8:1:2::/64"


def test_client_ip_and_usage_ip_key(tmp_path):
    from starlette.requests import Request

    def req(headers: dict, host: str = "10.0.0.1"):
        return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
                        "client": (host, 1234)})

    s = settings(tmp_path, client_ip_header="x-vercel-forwarded-for")
    # 형식이 IP 가 아닌 값: client_ip 는 None, client_key 는 원래 문자열을 그대로 키로 쓴다
    bad = req({"x-vercel-forwarded-for": "not-an-ip"})
    assert client_ip(s, bad) is None
    assert client_key(s, bad) == "not-an-ip"
    # 클라이언트 IP 헤더를 설정하지 않으면 IP 별 사용량 상한을 쓰지 않는다
    assert usage_ip_key(settings(tmp_path), req({"x-vercel-forwarded-for": "1.2.3.4"})) is None
    # IPv6 는 /56 단위로 묶는다
    a = usage_ip_key(s, req({"x-vercel-forwarded-for": "2001:db8:1:200::1"}))
    b = usage_ip_key(s, req({"x-vercel-forwarded-for": "2001:db8:1:2ff:ffff::9"}))
    c = usage_ip_key(s, req({"x-vercel-forwarded-for": "2001:db8:1:300::1"}))
    assert a == b and a != c


# ── API 보호 ───────────────────────────────────────────────


def test_public_endpoints(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["auth_enabled"] is True and h["auth_ready"] is True
    me = client.get("/auth/me").json()
    assert me == {"auth_enabled": True, "authenticated": False, "user": None, "signup_enabled": True,
                  "email_verification": False, "captcha": None, "verification_email_sent": None}
    assert client.get("/species").status_code == 200  # 종 목록은 누구나
    assert client.get("/community/posts").status_code == 200  # 커뮤니티 읽기는 누구나


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/designs", None),
    ("GET", "/me", None),
    ("GET", "/me/pets", None),
    ("POST", "/me/pets", {"name": "a", "species": "hamster", "size": "syrian"}),
    ("POST", "/community/posts", {"title": "t", "body": "b"}),
    ("POST", "/community/posts/" + "0" * 32 + "/comments", {"body": "b"}),
    ("POST", "/habitats", HABITAT),
    ("GET", "/habitats/" + "0" * 32, None),
    ("POST", "/designs", {"habitat_id": "0" * 32, "prompt": "은신처"}),
    ("POST", "/designs/" + "0" * 32 + "/revise", {"prompt": "더 크게"}),
    ("POST", "/waitlist", {"email": "a@example.com"}),
])
def test_protected_endpoints_require_login(client, method, path, body):
    r = client.request(method, path, json=body)
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth_required"


def test_login_then_full_flow_then_logout(client):
    r = login(client)
    assert r.json()["user"]["username"] == "admin" and r.json()["user"]["role"] == "admin"
    cookie = r.headers["set-cookie"]
    assert COOKIE_NAME in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert client.get("/auth/me").json()["authenticated"] is True

    hid = create_habitat(client)
    d = client.post("/designs", json={"habitat_id": hid, "prompt": "은신처를 왼쪽에"}).json()
    assert client.get(d["current"]["items"][0]["mesh_url"]).status_code == 200
    assert client.get(f"/designs/{d['id']}/export?format=3mf").status_code == 200

    client.post("/auth/logout", json={})
    assert client.get("/auth/me").json()["authenticated"] is False
    assert client.get(PROTECTED).status_code == 401
    assert client.get(f"/designs/{d['id']}").status_code == 404  # 공유되지 않은 설계는 없는 것처럼


def test_wrong_credentials(client):
    for creds in ({"username": "admin", "password": "wrong"}, {"username": "root", "password": ADMIN["password"]}):
        r = client.post("/auth/login", json=creds)
        assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_credentials"
        assert r.json()["detail"] == {"code": "invalid_credentials", "message_ko": "아이디 또는 비밀번호가 올바르지 않아요."}
        assert COOKIE_NAME not in r.headers.get("set-cookie", "")
    assert client.get(PROTECTED).status_code == 401


def test_forged_or_expired_cookie_rejected(tmp_path):
    s = settings(tmp_path)
    with TestClient(create_app(s)) as c:
        good = admin_token(s)
        uid = verify_token(good, signing_key(s))["sub"]
        c.cookies.set(COOKIE_NAME, issue_token(uid, b"attacker-key", 3600))
        assert c.get(PROTECTED).status_code == 401
        c.cookies.set(COOKIE_NAME, admin_token(s, ttl_s=-10))
        assert c.get(PROTECTED).status_code == 401
        c.cookies.set(COOKIE_NAME, issue_token("f" * 32, signing_key(s), 3600))  # 없는 회원
        assert c.get(PROTECTED).status_code == 401
        c.cookies.set(COOKIE_NAME, issue_token(uid, signing_key(s), 3600, ver=99))  # 세션 버전 불일치
        assert c.get(PROTECTED).status_code == 401
        c.cookies.set(COOKIE_NAME, good)
        assert c.get(PROTECTED).status_code == 200


def test_login_is_rate_limited(client):
    for _ in range(10):
        assert client.post("/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    r = client.post("/auth/login", json=ADMIN)  # 맞는 비밀번호여도 잠시 막힘
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_attempts"
    assert r.json()["detail"] == {"code": "too_many_attempts",
                                  "message_ko": "로그인 시도가 너무 많아요. 15분 뒤에 다시 시도해 주세요."}
    assert r.headers["cache-control"] == "no-store"


def test_login_server_errors_are_not_counted_as_failures(tmp_path, monkeypatch):
    import app.api.auth as auth_api

    def boom(*args, **kwargs):
        raise RuntimeError("DB 장애")

    monkeypatch.setattr(auth_api, "_authenticate", boom)
    with TestClient(create_app(settings(tmp_path)), raise_server_exceptions=False) as c:
        for _ in range(c.app.state.login_limiter.max_failures + 1):
            assert c.post("/auth/login", json=ADMIN).status_code == 500
        monkeypatch.undo()
        assert c.post("/auth/login", json=ADMIN).status_code == 200  # 서버 오류는 틀린 시도로 세지 않았다


def test_failed_login_is_delayed(client, monkeypatch):
    import app.api.auth as auth_api

    monkeypatch.setattr(auth_api, "FAILED_LOGIN_DELAY_S", 0.2)
    start = time.monotonic()
    r = client.post("/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401
    assert time.monotonic() - start >= 0.2


def test_signup_closed_when_auth_disabled(tmp_path):
    with TestClient(create_app(settings(tmp_path, admin_password=None))) as c:
        r = c.post("/auth/signup", json={"username": "user1", "nickname": "닉네임", "password": "password123"})
        assert r.status_code == 403
        assert r.json()["detail"] == {"code": "signup_closed", "message_ko": "지금은 회원가입을 받지 않아요."}


def test_signup_block_reports_email_before_captcha(tmp_path):
    """메일·CAPTCHA 설정이 둘 다 잘못됐으면 메일 쪽(email_unavailable)을 먼저 알린다."""
    s = settings(tmp_path, email_provider="resend", email_from="", turnstile_site_key="site-only")
    assert s.email_mode == "misconfigured" and s.captcha_mode == "misconfigured"
    with TestClient(create_app(s)) as c:
        assert c.get("/auth/me").json()["signup_enabled"] is False
        r = c.post("/auth/signup", json={"username": "user1", "nickname": "닉네임", "password": "password123"})
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "email_unavailable"


def test_auth_disabled_without_admin_password(tmp_path):
    with TestClient(create_app(settings(tmp_path, admin_password=None))) as c:
        assert c.get("/health").json()["auth_enabled"] is False
        assert c.get(PROTECTED).status_code == 200
        me = c.get("/auth/me").json()
        assert me["auth_enabled"] is False and me["authenticated"] is True and me["signup_enabled"] is False
        assert me["user"]["username"] == "local" and me["user"]["role"] == "admin"


def test_auth_required_fails_closed(tmp_path):
    """AUTH_REQUIRED=1 (컨테이너 기본값) 에서 비밀번호·서명 키가 빠지면 인증을 끄지 않고 503 으로 막는다."""
    cases = [
        {"auth_required": True, "admin_password": None},
        {"auth_required": True, "admin_password": "   "},
        {"session_secret": None},
        {"session_secret": "too-short"},
        {"admin_password": "short"},
    ]
    for kw in cases:
        s = settings(tmp_path, **kw)
        assert s.auth_mode == "misconfigured" and s.auth_problems, kw
        with TestClient(create_app(s)) as c:
            h = c.get("/health").json()
            assert h["auth_enabled"] is True and h["auth_ready"] is False
            for path in ("/designs", "/me", "/me/pets"):
                r = c.get(path)
                assert r.status_code == 503 and r.json()["detail"]["code"] == "auth_unavailable", kw
            assert c.post("/habitats", json=HABITAT).status_code == 503
            assert c.post("/auth/login", json=ADMIN).status_code == 503
            assert c.post("/auth/signup", json={"username": "user1", "nickname": "닉네임",
                                                "password": "password123"}).status_code == 503
            assert c.get("/auth/me").json() == {"auth_enabled": True, "authenticated": False, "user": None,
                                                "signup_enabled": False, "email_verification": False,
                                                "captcha": None, "verification_email_sent": None}


def test_non_ascii_cookie_is_rejected_not_500(client):
    for raw in ("kkomul_session=\xe9.x", "kkomul_session=\xff\xfe", "kkomul_session=" + "a" * 3000 + ".b"):
        headers = {"cookie": raw.encode("latin-1")}
        assert client.get(PROTECTED, headers=headers).status_code == 401
        assert client.get("/auth/me", headers=headers).json()["authenticated"] is False


def test_cookie_secure_flag(tmp_path):
    with TestClient(create_app(settings(tmp_path, cookie_secure=True))) as c:
        r = c.post("/auth/login", json=ADMIN)
        assert r.status_code == 200 and "secure" in r.headers["set-cookie"].lower()
        assert "secure" in c.post("/auth/logout", json={}).headers["set-cookie"].lower()
    with TestClient(create_app(settings(tmp_path)), base_url="https://testserver") as c:  # 미지정 → scheme 기준
        assert "secure" in c.post("/auth/login", json=ADMIN).headers["set-cookie"].lower()


def test_protected_responses_are_not_shared_cached(client):
    login(client)
    assert client.get("/species").headers["cache-control"] == "no-store"
    # CORS 등이 이미 Vary 를 넣은 응답에도 Cookie 가 덧붙는다
    vary = client.get("/species", headers={"Origin": "http://localhost:3000"}).headers["vary"].lower()
    assert "cookie" in vary and "origin" in vary
    hid = create_habitat(client)
    d = client.post("/designs", json={"habitat_id": hid, "prompt": "은신처"}).json()
    mesh = client.get(d["current"]["items"][0]["mesh_url"])
    assert mesh.headers["cache-control"].startswith("private") and "cookie" in mesh.headers["vary"].lower()
    exp = client.get(f"/designs/{d['id']}/export?format=stl")
    assert exp.headers["cache-control"] == "no-store"


def test_password_rotation_invalidates_sessions(tmp_path):
    s = settings(tmp_path)
    token = admin_token(s)
    with TestClient(create_app(settings(tmp_path, admin_password="a brand new password"))) as c:
        c.cookies.set(COOKIE_NAME, token)
        assert c.get(PROTECTED).status_code == 401


def test_exp_must_be_integer():
    key = b"k" * 32
    for raw in (b'{"sub":"admin","exp":NaN}', b'{"sub":"admin","exp":Infinity}', b'{"sub":"admin","exp":1e999}',
                b'{"sub":"admin","exp":9999999999.5}', b'{"sub":"admin","exp":"9999999999"}',
                b'{"sub":"admin","exp":' + b"9" * 400 + b"}", b'{"sub":"admin","exp":true}'):
        body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(hmac.new(key, body.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
        assert verify_token(f"{body}.{sig}", key) is None, raw[:40]


def test_login_with_lone_surrogate_is_422_without_echo(client):
    """짝 없는 서로게이트 문자 → 500 이 아니라 422, 응답에 입력값(비밀번호)을 되돌려 보내지 않는다."""
    raw = '{"username":"admin","password":"secret-\\ud800-value"}'
    r = client.post("/auth/login", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"
    assert "secret" not in r.text and "input" not in r.text


def test_validation_errors_do_not_echo_input(client):
    login(client)
    r = client.post("/habitats", json={**HABITAT, "count": "my-private-text"})
    assert r.status_code == 422 and "my-private-text" not in r.text
    assert r.json()["detail"]["errors"][0]["loc"][-1] == "count"


def test_ipv4_mapped_addresses_are_not_bucketed_together(tmp_path):
    from starlette.requests import Request

    s = settings(tmp_path, client_ip_header="x-vercel-forwarded-for")

    def key(ip):
        return client_key(s, Request({"type": "http", "headers": [(b"x-vercel-forwarded-for", ip.encode())],
                                      "client": ("10.0.0.1", 1)}))

    assert key("::ffff:1.2.3.4") == "1.2.3.4"
    assert key("::ffff:5.6.7.8") == "5.6.7.8"


def test_rate_limiter_eviction_never_unblocks():
    rl = LoginRateLimiter(max_failures=2, window_s=100, max_keys=3)
    for _ in range(2):
        rl.record_failure("victim-blocked", now=1)
    assert rl.blocked("victim-blocked", now=2)
    for i in range(50):  # 새 키를 잔뜩 만들어도 막힌 키는 버려지지 않는다
        rl.record_failure(f"new{i}", now=2)
    assert rl.blocked("victim-blocked", now=3)
    assert len(rl) <= 3


def test_rate_limiter_saturated_with_blocked_keys_fails_closed():
    rl = LoginRateLimiter(max_failures=1, window_s=100, max_keys=2)
    rl.record_failure("a", now=1)
    rl.record_failure("b", now=1)
    assert rl.blocked("a", now=2) and rl.blocked("b", now=2)
    rl.record_failure("c", now=2)  # 표가 막힌 키로 가득 → 새 키는 잠시 모두 막힘
    assert rl.blocked("c", now=3) and rl.blocked("never-seen", now=3)
    assert not rl.blocked("never-seen", now=200)  # 시간이 지나면 풀림


def test_logout_rejects_cross_site_forms(client):
    login(client)
    for headers in ({"content-type": "application/x-www-form-urlencoded"}, {"content-type": "text/plain"}, {},
                    {"content-type": "application/json", "sec-fetch-site": "cross-site"}):
        r = client.post("/auth/logout", headers=headers, content=b"")
        assert r.status_code == 403 and r.json()["detail"]["code"] == "cross_site_request", headers
        assert COOKIE_NAME not in r.headers.get("set-cookie", "")
        assert client.get(PROTECTED).status_code == 200  # 세션 유지
    r = client.post("/auth/logout", json={}, headers={"sec-fetch-site": "same-origin"})
    assert r.status_code == 200 and client.get(PROTECTED).status_code == 401


def test_admin_username_whitespace_is_stripped(tmp_path):
    with TestClient(create_app(settings(tmp_path, admin_username="  admin \n"))) as c:
        assert c.post("/auth/login", json=ADMIN).status_code == 200


def test_padded_or_short_password_is_misconfigured(tmp_path):
    for pw in (" correct horse battery staple", "correct horse battery staple\n", "fifteen-chars!!"):
        assert settings(tmp_path, admin_password=pw).auth_mode == "misconfigured", repr(pw)


def test_session_ttl_bounds(tmp_path):
    from pydantic import ValidationError

    for bad in (0, -1, float("inf"), float("nan"), 1e300):
        with pytest.raises(ValidationError):
            settings(tmp_path, session_ttl_hours=bad)


def test_swagger_ui_disabled_when_auth_on(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 200
    with TestClient(create_app(settings(tmp_path, admin_password=None))) as c:
        assert c.get("/docs").status_code == 200
