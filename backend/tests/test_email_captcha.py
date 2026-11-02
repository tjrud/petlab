"""이메일 인증과 CAPTCHA(Turnstile).

메일은 MemoryMailer 로, CAPTCHA 확인은 가짜 verifier 로 바꿔 끼워 네트워크 없이 확인한다.
Turnstile·SMTP·Resend 연동부는 httpx·smtplib 를 가짜로 바꿔 요청 형식만 확인한다."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text, update
from sqlalchemy.exc import IntegrityError

from app import captcha as captcha_mod
from app import mailer as mailer_mod
from app.auth import COOKIE_NAME
from app.captcha import CaptchaUnavailableError
from app.config import Settings
from app.db import init_db, make_engine, make_session_factory
from app.mailer import FileMailer, Mail, MailError, MemoryMailer, ResendMailer, SmtpMailer
from app.main import create_app
from app.models import EmailToken, UsageEvent, User
from app.names import email_key
from tests.test_members import CAGE, PG_URL, PW, _db_url, admin_login, settings, use

HAB = {"species": "hamster", "size": "syrian", "count": 1, "cage": CAGE}
EMAIL_ON = {"email_provider": "file", "email_from": "NestForge <no-reply@nestforge.test>",
            "app_base_url": "https://nestforge.test"}
TOKEN_RE = re.compile(r"https://nestforge\.test/verify-email\?token=([A-Za-z0-9_\-]+)")


def app_with(tmp_path, mailer=None, verifier=None, **kw):
    return create_app(settings(tmp_path, **kw), mailer=mailer, captcha_verifier=verifier)


def signup(c: TestClient, username: str, email: str | None, nickname: str | None = None, **extra) -> dict:
    c.cookies.clear()
    body = {"username": username, "nickname": nickname or f"{username}님", "password": PW, **extra}
    if email is not None:
        body["email"] = email
    r = c.post("/auth/signup", json=body)
    assert r.status_code == 201, r.text
    return r.json() | {"_token": r.cookies[COOKIE_NAME]}


def last_token(mailer: MemoryMailer, to: str) -> str:
    mail = next(m for m in reversed(mailer.sent) if m.to == to)
    return TOKEN_RE.search(mail.text).group(1)


def age_usage(c: TestClient, seconds: int = 120) -> None:
    """보내기 간격 확인을 지나가게 기록 시각을 앞당긴다."""
    db = c.app.state.session_factory()
    for e in db.query(UsageEvent).all():  # SQLite 는 날짜 산술을 SQL 로 못 하므로 파이썬에서 바꾼다
        e.created_at = e.created_at - timedelta(seconds=seconds)
    db.commit()
    db.close()


@pytest.fixture
def mailer():
    return MemoryMailer()


@pytest.fixture
def client(tmp_path, mailer):
    with TestClient(app_with(tmp_path, mailer=mailer, **EMAIL_ON)) as c:
        yield c


# ── 이메일 인증 ────────────────────────────────────────────


def test_signup_sends_verification_and_gates_costly_actions(client, mailer):
    st = client.get("/auth/me").json()
    assert st["email_verification"] is True and st["captcha"] is None and st["signup_enabled"] is True

    r = client.post("/auth/signup", json={"username": "kong_01", "nickname": "콩이맘", "password": PW})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "email_required"

    out = signup(client, "kong_01", "Kong@Example.com", "콩이맘")
    assert out["verification_email_sent"] is True
    assert out["user"]["email"] == "Kong@example.com" and out["user"]["email_verified"] is False
    mail = mailer.sent[-1]
    assert mail.to == "Kong@example.com" and "인증" in mail.subject and TOKEN_RE.search(mail.text)
    assert TOKEN_RE.search(mail.html.replace("&amp;", "&"))

    # 인증 전: 비용·스팸이 드는 기능은 막고, 사육 환경·반려동물·내 정보는 된다
    hab = client.post("/habitats", json=HAB)
    assert hab.status_code == 201
    hid = hab.json()["id"]
    for path, body in (("/designs", {"habitat_id": hid, "prompt": "은신처"}),
                       ("/community/posts", {"title": "글", "body": "x"}),
                       ("/waitlist", {"email": "kong@example.com"})):
        r = client.post(path, json=body)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "email_unverified", path
    assert client.post("/me/pets", json={"name": "콩이", "species": "hamster", "size": "syrian"}).status_code == 201

    # 링크로 인증 (다른 브라우저에서 열어도 된다: 로그인 없이)
    token = last_token(mailer, "Kong@example.com")
    use(client, None)
    r = client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 200 and r.json()["ok"] is True
    use(client, out["_token"])
    assert client.get("/auth/me").json()["user"]["email_verified"] is True
    assert client.post("/designs", json={"habitat_id": hid, "prompt": "은신처"}).status_code == 201
    assert client.post("/community/posts", json={"title": "글", "body": "x"}).status_code == 201

    # 한 번 쓴 링크는 다시 못 쓴다
    r = client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_token"


@pytest.mark.parametrize("token", ["", "x" * 200, "없는토큰", "a" * 43])
def test_bogus_tokens_are_rejected(client, token):
    r = client.post("/auth/verify-email", json={"token": token})
    assert r.status_code in (400, 422)
    if r.status_code == 400:
        assert r.json()["detail"]["code"] == "invalid_token"


def test_expired_token_is_rejected(client, mailer):
    signup(client, "kong_01", "kong@example.com")
    token = last_token(mailer, "kong@example.com")
    db = client.app.state.session_factory()
    db.execute(update(EmailToken).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    db.commit()
    db.close()
    r = client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_token"


def test_tokens_are_stored_hashed(client, mailer):
    signup(client, "kong_01", "kong@example.com")
    token = last_token(mailer, "kong@example.com")
    db = client.app.state.session_factory()
    hashes = [t.token_hash for t in db.query(EmailToken).all()]
    db.close()
    assert len(hashes) == 1 and token not in hashes and len(hashes[0]) == 64


def test_resend_cooldown_and_daily_limit(client, mailer):
    signup(client, "kong_01", "kong@example.com")
    r = client.post("/auth/verify-email/resend")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "email_cooldown"
    for _ in range(4):  # 가입 메일 1 + 다시 보내기 4 = 24시간 5통
        age_usage(client)
        r = client.post("/auth/verify-email/resend")
        assert r.status_code == 200 and r.json()["sent"] is True, r.text
    age_usage(client)
    r = client.post("/auth/verify-email/resend")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_emails"
    assert len(mailer.sent) == 5
    # 예전 링크도 만료 전까지는 쓸 수 있다 (메일이 늦게 와도 혼란이 없게)
    first = TOKEN_RE.search(mailer.sent[0].text).group(1)
    assert client.post("/auth/verify-email", json={"token": first}).status_code == 200
    r = client.post("/auth/verify-email/resend")
    assert r.status_code == 200 and r.json()["sent"] is False  # 이미 인증


def test_service_wide_email_cap(tmp_path, mailer):
    with TestClient(app_with(tmp_path, mailer=mailer, email_daily_limit=1, **EMAIL_ON)) as c:
        assert signup(c, "user_a", "a@example.com")["verification_email_sent"] is True
        out = signup(c, "user_b", "b@example.com")
        assert out["verification_email_sent"] is False and len(mailer.sent) == 1  # 가입은 되고 메일만 못 보냄


def test_mail_failure_still_creates_account(tmp_path):
    failing = MemoryMailer(fail=True)
    with TestClient(app_with(tmp_path, mailer=failing, **EMAIL_ON)) as c:
        out = signup(c, "user_a", "a@example.com")
        assert out["verification_email_sent"] is False and out["authenticated"] is True
        age_usage(c)
        r = c.post("/auth/verify-email/resend")
        assert r.status_code == 200 and r.json()["sent"] is False


def test_email_change_rebinds_verification(client, mailer):
    out = signup(client, "kong_01", "old@example.com")
    old_token = last_token(mailer, "old@example.com")
    bad = client.patch("/me/email", json={"email": "new@example.com", "current_password": "wrong-password"})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid_credentials"
    age_usage(client)
    r = client.patch("/me/email", json={"email": "new@example.com", "current_password": PW})
    assert r.status_code == 200 and r.json()["verification_email_sent"] is True
    assert r.json()["user"]["email"] == "new@example.com" and r.json()["user"]["email_verified"] is False
    # 예전 주소로 보낸 링크로는 새 주소가 인증되지 않는다
    assert client.post("/auth/verify-email", json={"token": old_token}).status_code == 400
    assert client.post("/auth/verify-email", json={"token": last_token(mailer, "new@example.com")}).status_code == 200
    use(client, out["_token"])
    assert client.get("/auth/me").json()["user"]["email_verified"] is True
    # 인증한 뒤 다른 주소로 바꾸면 다시 인증 전이 된다
    age_usage(client)
    r = client.patch("/me/email", json={"email": "third@example.com", "current_password": PW})
    assert r.json()["user"]["email_verified"] is False


def test_email_change_password_attempts_are_limited(client):
    signup(client, "kong_01", "kong@example.com")
    body = {"email": "new@example.com", "current_password": "wrong-password"}
    assert [client.patch("/me/email", json=body).status_code for _ in range(6)] == [400] * 5 + [429]


def test_only_one_account_can_verify_an_address(client, mailer):
    squatter = signup(client, "squat_01", "Vic.Tim+x@gmail.com")  # 남의 주소를 먼저 적어 둔 계정
    victim = signup(client, "victim_1", "victim@gmail.com")      # 같은 주소로 가입할 수 있다 (인증 전 주소는 겹쳐도 된다)
    assert client.post("/auth/verify-email", json={"token": last_token(mailer, "victim@gmail.com")}).status_code == 200
    r = client.post("/auth/verify-email", json={"token": last_token(mailer, "Vic.Tim+x@gmail.com")})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "email_taken"
    client.cookies.clear()
    r = client.post("/auth/signup", json={"username": "third_01", "nickname": "셋째", "password": PW,
                                          "email": "v.i.c.t.i.m@googlemail.com"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "email_taken"
    use(client, squatter["_token"])
    age_usage(client)
    r = client.patch("/me/email", json={"email": "victim+2@gmail.com", "current_password": PW})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "email_taken"
    assert victim["user"]["email"] == "victim@gmail.com"


def test_verified_email_unique_index(client):
    db = client.app.state.session_factory()
    now = datetime.now(timezone.utc)
    for i, verified in enumerate((now, None, None)):  # 인증 전 주소는 겹쳐도 된다
        db.add(User(username=f"dup_{i}", nickname=f"중복{i}", nickname_key=f"중복{i}", role="member",
                    email="dup@example.com", email_key="dup@example.com", email_verified_at=verified))
    db.commit()
    db.add(User(username="dup_9", nickname="중복9", nickname_key="중복9", role="member",
                email="dup@example.com", email_key="dup@example.com", email_verified_at=now))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()


def test_admin_and_members_without_email(client, mailer):
    admin_login(client)
    me = client.get("/auth/me").json()["user"]
    assert me["email_verified"] is True and me["email"] is None
    hid = client.post("/habitats", json=HAB).json()["id"]
    assert client.post("/designs", json={"habitat_id": hid, "prompt": "은신처"}).status_code == 201
    assert client.post("/auth/verify-email/resend").status_code == 403
    assert client.patch("/me/email", json={"email": "a@example.com", "current_password": "x"}).status_code == 403

    # 이메일 기능 전에 가입한 회원 (이메일 없음): 막히고, 내 정보에서 이메일을 등록하면 인증 메일을 받는다
    db = client.app.state.session_factory()
    from app.passwords import hash_password
    db.add(User(username="legacy_1", nickname="예전회원", nickname_key="예전회원", role="member",
                password_hash=hash_password(PW)))
    db.commit()
    db.close()
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": "legacy_1", "password": PW}).status_code == 200
    assert client.post("/community/posts", json={"title": "x", "body": "x"}).status_code == 403
    r = client.post("/auth/verify-email/resend")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "email_required"
    r = client.patch("/me/email", json={"email": "legacy@example.com", "current_password": PW})
    assert r.status_code == 200 and r.json()["verification_email_sent"] is True


def test_email_disabled_keeps_previous_behavior(tmp_path):
    with TestClient(app_with(tmp_path)) as c:
        st = c.get("/auth/me").json()
        assert st["email_verification"] is False
        out = signup(c, "user_a", None)
        assert out["verification_email_sent"] is None and out["user"]["email_verified"] is False
        hid = c.post("/habitats", json=HAB).json()["id"]
        assert c.post("/designs", json={"habitat_id": hid, "prompt": "은신처"}).status_code == 201
        assert c.post("/auth/verify-email/resend").status_code == 403


def test_misconfigured_email_closes_signup_but_not_existing_members(tmp_path):
    with TestClient(app_with(tmp_path)) as c:  # 먼저 회원 하나
        token = signup(c, "user_a", None)["_token"]
    with TestClient(app_with(tmp_path, email_provider="smtp", email_from="x@example.com")) as c:  # SMTP_HOST 없음
        assert c.get("/health").json()["email_verification"] == "misconfigured"
        assert c.get("/auth/me").json()["signup_enabled"] is False
        r = c.post("/auth/signup", json={"username": "user_b", "nickname": "비비", "password": PW,
                                         "email": "b@example.com"})
        assert r.status_code == 503 and r.json()["detail"]["code"] == "email_unavailable"
        use(c, token)
        hid = c.post("/habitats", json=HAB).json()["id"]
        assert c.post("/designs", json={"habitat_id": hid, "prompt": "은신처"}).status_code == 201


# ── CAPTCHA ────────────────────────────────────────────────


class FakeVerifier:
    def __init__(self, ok_token="pass", raise_unavailable=False):
        self.ok_token, self.raise_unavailable, self.calls = ok_token, raise_unavailable, []

    def __call__(self, token, ip):
        self.calls.append((token, ip))
        if self.raise_unavailable:
            raise CaptchaUnavailableError()
        return token == self.ok_token


CAPTCHA_ON = {"turnstile_site_key": "site-key-123", "turnstile_secret_key": "secret-xyz",
              "client_ip_header": "x-test-ip"}


def test_signup_requires_captcha(tmp_path):
    v = FakeVerifier()
    with TestClient(app_with(tmp_path, verifier=v, **CAPTCHA_ON)) as c:
        assert c.get("/auth/me").json()["captcha"] == {"provider": "turnstile", "site_key": "site-key-123"}
        assert c.get("/health").json()["captcha"] == "enabled"
        body = {"username": "user_a", "nickname": "에이", "password": PW}
        for extra in ({}, {"captcha_token": "fail"}, {"captcha_token": "토큰"}, {"captcha_token": "x" * 2049}):
            r = c.post("/auth/signup", json=body | extra)
            assert r.status_code in (400, 422), extra
            if r.status_code == 400:
                assert r.json()["detail"]["code"] == "captcha_failed"
        r = c.post("/auth/signup", json=body | {"captcha_token": "pass"}, headers={"x-test-ip": "203.0.113.7"})
        assert r.status_code == 201
        assert ("pass", "203.0.113.7") in v.calls
        # 로봇 확인이 아이디 중복 확인보다 먼저 (자동으로 가입 여부를 캐 보지 못하게)
        c.cookies.clear()
        r = c.post("/auth/signup", json=body | {"captcha_token": "fail"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "captcha_failed"


def test_captcha_provider_outage_is_503(tmp_path):
    with TestClient(app_with(tmp_path, verifier=FakeVerifier(raise_unavailable=True), **CAPTCHA_ON)) as c:
        r = c.post("/auth/signup", json={"username": "user_a", "nickname": "에이", "password": PW,
                                         "captcha_token": "pass"})
        assert r.status_code == 503 and r.json()["detail"]["code"] == "captcha_unavailable"


def test_half_configured_captcha_closes_signup(tmp_path):
    with TestClient(app_with(tmp_path, turnstile_site_key="only-site")) as c:
        assert c.get("/auth/me").json()["signup_enabled"] is False
        r = c.post("/auth/signup", json={"username": "user_a", "nickname": "에이", "password": PW})
        assert r.status_code == 503 and r.json()["detail"]["code"] == "captcha_unavailable"


def test_captcha_and_email_together(tmp_path, mailer):
    with TestClient(app_with(tmp_path, mailer=mailer, verifier=FakeVerifier(), **EMAIL_ON, **CAPTCHA_ON)) as c:
        r = c.post("/auth/signup", json={"username": "user_a", "nickname": "에이", "password": PW,
                                         "email": "a@example.com", "captcha_token": "pass"})
        assert r.status_code == 201 and r.json()["verification_email_sent"] is True


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = str(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def test_turnstile_verifier_request_and_errors(monkeypatch):
    s = Settings(_env_file=None, **CAPTCHA_ON)
    sent = []

    def fake_post(url, data=None, timeout=None, **kw):
        sent.append((url, data))
        return responses.pop(0)

    monkeypatch.setattr(captcha_mod.httpx, "post", fake_post)
    verify = captcha_mod.turnstile_verifier(s)
    responses = [_Resp(200, {"success": True}), _Resp(200, {"success": False, "error-codes": ["timeout-or-duplicate"]})]
    assert verify("tok", "198.51.100.1") is True
    assert sent[0] == (s.turnstile_verify_url, {"secret": "secret-xyz", "response": "tok", "remoteip": "198.51.100.1"})
    assert verify("tok", None) is False and "remoteip" not in sent[1][1]
    responses = [_Resp(200, {"success": False, "error-codes": ["invalid-input-secret"]})]
    with pytest.raises(CaptchaUnavailableError):
        verify("tok", None)
    responses = [_Resp(502, ValueError("not json"))]
    with pytest.raises(CaptchaUnavailableError):
        verify("tok", None)

    def boom(*a, **kw):
        raise captcha_mod.httpx.ConnectError("down")

    monkeypatch.setattr(captcha_mod.httpx, "post", boom)
    with pytest.raises(CaptchaUnavailableError):
        verify("tok", None)


# ── 메일 공급자 ────────────────────────────────────────────


MAIL = Mail(to="kong@example.com", subject="[NestForge] 인증", text="본문 https://x/verify-email?token=abc",
            html="<p>본문</p>")


def test_file_mailer_writes_json(tmp_path):
    FileMailer(tmp_path / "outbox").send(MAIL)
    files = list((tmp_path / "outbox").glob("*.json"))
    assert len(files) == 1 and json.loads(files[0].read_text(encoding="utf-8"))["to"] == "kong@example.com"


def test_smtp_mailer(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, **kw):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            calls.append(("starttls",))

        def login(self, u, p):
            calls.append(("login", u, p))

        def send_message(self, msg):
            calls.append(("send", msg["From"], msg["To"], msg["Subject"], msg.get_content_type(),
                          [p.get_content_type() for p in msg.iter_parts()]))

    monkeypatch.setattr(mailer_mod.smtplib, "SMTP", FakeSMTP)
    s = Settings(_env_file=None, email_provider="smtp", email_from="NestForge <bot@example.com>",
                 smtp_host="smtp.example.com", smtp_username="bot@example.com", smtp_password="app-pass",
                 app_base_url="https://x")
    SmtpMailer(s).send(MAIL)
    assert calls[0] == ("connect", "smtp.example.com", 587) and ("starttls",) in calls
    assert ("login", "bot@example.com", "app-pass") in calls
    send = calls[-1]
    assert send[1] == "NestForge <bot@example.com>" and send[2] == "kong@example.com"
    assert send[4] == "multipart/alternative" and send[5] == ["text/plain", "text/html"]

    class Broken(FakeSMTP):
        def login(self, u, p):
            raise mailer_mod.smtplib.SMTPAuthenticationError(535, b"bad")

    monkeypatch.setattr(mailer_mod.smtplib, "SMTP", Broken)
    with pytest.raises(MailError) as e:
        SmtpMailer(s).send(MAIL)
    assert "app-pass" not in str(e.value)


def test_resend_mailer(monkeypatch):
    got = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        got.update(url=url, headers=headers, json=json)
        return _Resp(200, {"id": "1"})

    monkeypatch.setattr(mailer_mod.httpx, "post", fake_post)
    s = Settings(_env_file=None, email_provider="resend", email_from="NestForge <no-reply@nestforge.app>",
                 resend_api_key="re_test", app_base_url="https://x")
    ResendMailer(s).send(MAIL)
    assert got["url"] == ResendMailer.API_URL and got["headers"]["Authorization"] == "Bearer re_test"
    assert got["json"]["to"] == ["kong@example.com"] and got["json"]["from"] == "NestForge <no-reply@nestforge.app>"
    monkeypatch.setattr(mailer_mod.httpx, "post", lambda *a, **k: _Resp(403, {"message": "domain not verified"}))
    with pytest.raises(MailError):
        ResendMailer(s).send(MAIL)


@pytest.mark.parametrize("kw,problems", [
    ({"email_provider": "smtp"}, ["EMAIL_FROM", "SMTP_HOST"]),
    ({"email_provider": "resend", "email_from": "a@b.c"}, ["RESEND_API_KEY"]),
    ({"email_provider": "file", "email_from": "a@b.c", "cors_origins": ""}, ["APP_BASE_URL"]),
    ({"email_provider": "file", "email_from": "a@b.c"}, []),  # 로컬: CORS 첫 출처를 링크 주소로
])
def test_email_settings_problems(kw, problems):
    s = Settings(_env_file=None, **kw)
    assert [p.split(" ")[0].split("(")[0] for p in s.email_problems] == problems


@pytest.mark.parametrize("a,b,same", [
    ("Kong@Example.com", "kong@example.com", True),
    ("kong+spam@example.com", "kong@example.com", True),
    ("k.o.n.g@gmail.com", "KONG@googlemail.com", True),
    ("k.ong@naver.com", "kong@naver.com", False),  # 점 무시는 Gmail 만
])
def test_email_key(a, b, same):
    assert (email_key(a) == email_key(b)) is same


# ── 마이그레이션 (이메일 열이 없던 운영 DB) ────────────────────


def test_migration_adds_email_columns_and_indexes(tmp_path):
    url = _db_url(tmp_path)
    eng = make_engine(url)
    ts = "TIMESTAMP WITH TIME ZONE"
    with eng.begin() as conn:  # 직전 배포(회원 기능)의 users 테이블
        conn.execute(text(f"""CREATE TABLE users (
            id VARCHAR(32) PRIMARY KEY, username VARCHAR(32) NOT NULL UNIQUE, nickname VARCHAR(40) NOT NULL UNIQUE,
            nickname_key VARCHAR(40) NOT NULL UNIQUE, password_hash VARCHAR(255), role VARCHAR(16) NOT NULL,
            session_version INTEGER NOT NULL, created_at {ts} NOT NULL)"""))
        conn.execute(text("INSERT INTO users VALUES ('u1', 'old_member', '예전', '예전', NULL, 'member', 1, "
                          "CURRENT_TIMESTAMP)"))
    added = init_db(eng)
    assert {"users.email", "users.email_key", "users.email_verified_at", "ix_users_email_key",
            "ux_users_email_key_verified"} <= set(added)
    assert "email_tokens" in inspect(eng).get_table_names()
    assert init_db(eng) == []
    factory = make_session_factory(eng)
    db = factory()
    u = db.get(User, "u1")
    assert u.email is None and u.email_verified_at is None
    now = datetime.now(timezone.utc)
    u.email, u.email_key, u.email_verified_at = "a@example.com", "a@example.com", now
    db.add(User(id="u2", username="other_1", nickname="다른", nickname_key="다른", role="member",
                email="a@example.com", email_key="a@example.com"))
    db.commit()  # 인증 전 주소는 겹쳐도 된다
    db.get(User, "u2").email_verified_at = now
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()
    eng.dispose()


@pytest.mark.skipif(not PG_URL, reason="TEST_PG_URL(Postgres) 에서만")
def test_concurrent_verification_of_same_address_on_postgres(tmp_path, mailer):
    """같은 주소를 두 계정이 동시에 인증하면 한쪽만 된다 (부분 유일 인덱스). 메일 사용량 잠금도 Postgres 에서 동작."""
    from concurrent.futures import ThreadPoolExecutor

    with TestClient(app_with(tmp_path, mailer=mailer, **EMAIL_ON)) as c:
        signup(c, "user_a", "a@example.com")
        signup(c, "user_b", "A+b@Example.com")
        tokens = [TOKEN_RE.search(m.text).group(1) for m in mailer.sent]
        c.cookies.clear()
        with ThreadPoolExecutor(2) as pool:
            codes = sorted(pool.map(lambda t: c.post("/auth/verify-email", json={"token": t}).status_code, tokens))
        assert codes == [200, 409]
