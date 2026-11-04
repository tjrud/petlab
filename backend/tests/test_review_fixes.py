"""회원·커뮤니티 적대적 리뷰에서 확인된 문제의 회귀 테스트.

공유 범위(첨부한 버전만), 관리자 권한 분리, 사용량 상한(동시 요청·실패 요청·삭제 후 재작성), 닉네임 위장,
로그인·비밀번호 시도 제한, DB 연결 반환, 마이그레이션 잠금, 관리자 아이디 길이."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_serializer
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

from app.api.deps import make_router
from app.auth import COOKIE_NAME, LoginRateLimiter, _ensure_user_row
from app.db import init_db, make_engine, make_session_factory
from app.llm.base import LLMSchemaError
from app.llm.mock import MockInterpreter
from app.main import create_app
from app.models import UsageEvent, User, WaitlistEntry
from tests.api_helpers import PG_URL, PW, admin_login, create_habitat, habitat_body, make_design, signup, use
from tests.api_helpers import member_settings as settings


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


# ── 공유 범위: 첨부한 버전만 공개 ───────────────────────────


def test_only_attached_versions_are_public(client):
    signup(client, "user_a", "에이")
    d = make_design(client, "v1 은신처")
    assert client.post(f"/designs/{d['id']}/revise", json={"prompt": "PRIVATE v2"}).status_code == 201
    r = client.post("/community/posts", json={"title": "v1 공유", "body": "x", "design_id": d["id"], "design_version": 1})
    assert r.status_code == 201 and r.json()["design"]["version"] == 1
    assert client.post(f"/designs/{d['id']}/revise", json={"prompt": "PRIVATE v3 (공유 후)"}).status_code == 201
    owner = client.get(f"/designs/{d['id']}").json()
    assert [v["version"] for v in owner["versions"]] == [1, 2, 3] and owner["shared_versions"] == [1]
    assert owner["current"]["version"] == 3

    for token in (None, signup(client, "user_b")):
        use(client, token)
        got = client.get(f"/designs/{d['id']}").json()
        assert got["current"]["version"] == 1 and [v["version"] for v in got["versions"]] == [1]
        assert "PRIVATE" not in str(got)
        for v in (2, 3):
            assert client.get(f"/designs/{d['id']}?version={v}").status_code == 404
            assert client.get(f"/designs/{d['id']}/export?format=stl&version={v}").status_code == 404
            assert client.get(f"/designs/{d['id']}/versions/{v}/parts/0.stl").status_code == 404
        assert client.get(f"/designs/{d['id']}/export?format=stl").status_code == 200  # 기본은 공유한 버전
        assert client.get(d["current"]["items"][0]["mesh_url"]).status_code == 200

    # 두 번째 글로 v3 를 공유하면 v3 도 보인다. 글을 지우면 다시 비공개
    use(client, None)
    assert client.post("/auth/login", json={"username": "user_a", "password": PW}).status_code == 200
    p3 = client.post("/community/posts", json={"title": "v3", "body": "x", "design_id": d["id"], "design_version": 3})
    use(client, None)
    assert [v["version"] for v in client.get(f"/designs/{d['id']}").json()["versions"]] == [1, 3]
    client.post("/auth/login", json={"username": "user_a", "password": PW})
    assert client.delete(f"/community/posts/{p3.json()['id']}").status_code == 204
    assert client.delete(f"/community/posts/{r.json()['id']}").status_code == 204
    use(client, None)
    assert client.get(f"/designs/{d['id']}").status_code == 404


def test_admin_views_but_does_not_own_member_designs(client):
    signup(client, "user_a", "에이")
    d = make_design(client)
    assert client.post(f"/designs/{d['id']}/revise", json={"prompt": "v2"}).status_code == 201
    admin_login(client)
    got = client.get(f"/designs/{d['id']}").json()
    assert got["is_owner"] is False and [v["version"] for v in got["versions"]] == [1, 2]  # 운영 확인용으로 전부 본다
    assert client.get(f"/designs/{d['id']}/export?format=stl&version=1").status_code == 200
    assert client.post(f"/designs/{d['id']}/revise", json={"prompt": "관리자 수정"}).status_code == 404
    assert client.post("/community/posts", json={"title": "x", "body": "x", "design_id": d["id"]}).status_code == 404


# ── 사용량 상한 ────────────────────────────────────────────


class _SlowMock(MockInterpreter):
    def __init__(self, delay: float):
        self.delay = delay
        self.calls = 0
        self._lock = threading.Lock()

    def interpret(self, req):
        with self._lock:
            self.calls += 1
        time.sleep(self.delay)
        return super().interpret(req)


def test_parallel_design_requests_cannot_exceed_quota(tmp_path):
    llm = _SlowMock(0.3)
    app = create_app(settings(tmp_path, design_daily_limit=3, design_global_daily_limit=100), interpreter=llm)
    with TestClient(app) as c:
        signup(c, "user_a")
        hid = create_habitat(c)
        with ThreadPoolExecutor(10) as pool:
            codes = list(pool.map(lambda _: c.post("/designs", json={"habitat_id": hid, "prompt": "은신처"}).status_code,
                                  range(10)))
        assert sorted(codes) == [201] * 3 + [429] * 7
        assert llm.calls == 3
        assert c.get("/me").json()["design_quota"] == {"used": 3, "limit": 3, "remaining": 0}


def test_failed_interpretations_count_toward_quota(tmp_path):
    class Failing(MockInterpreter):
        def interpret(self, req):
            raise LLMSchemaError("요구사항을 해석하지 못했어요.")

    with TestClient(create_app(settings(tmp_path, design_daily_limit=2), interpreter=Failing())) as c:
        signup(c, "user_a")
        hid = create_habitat(c)
        assert [c.post("/designs", json={"habitat_id": hid, "prompt": "x"}).status_code for _ in range(3)] == [422, 422, 429]
        assert c.get("/me").json()["design_quota"]["used"] == 2


def test_design_quota_per_ip_when_client_ip_header_is_set(tmp_path):
    s = settings(tmp_path, design_daily_limit=10, design_ip_daily_limit=2, client_ip_header="x-test-ip")
    with TestClient(create_app(s)) as c:
        def design(ip: str) -> int:
            hid = create_habitat(c)
            return c.post("/designs", json={"habitat_id": hid, "prompt": "은신처"},
                          headers={"x-test-ip": ip}).status_code
        signup(c, "user_a")
        assert design("203.0.113.5") == 201
        signup(c, "user_b")  # 같은 IP 의 다른 계정
        assert design("203.0.113.5") == 201
        assert design("203.0.113.5") == 429
        assert design("2001:db8:1:2::1") == 201
        assert design("2001:db8:1:2:ffff::1") == 201   # 같은 /56
        assert design("2001:db8:1:2a::1") == 429        # 같은 /56 (2001:db8:1:0::/56)
        assert design("2001:db8:1:200::1") == 201       # 다른 /56


def test_deleting_posts_does_not_reset_post_limit(tmp_path):
    with TestClient(create_app(settings(tmp_path, post_daily_limit=2, comment_daily_limit=1))) as c:
        signup(c, "user_a")
        for i in range(2):
            pid = c.post("/community/posts", json={"title": f"글{i}", "body": "x"}).json()["id"]
            assert c.delete(f"/community/posts/{pid}").status_code == 204
        r = c.post("/community/posts", json={"title": "셋째", "body": "x"})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_posts"
        admin_login(c)
        pid = c.post("/community/posts", json={"title": "공지", "body": "x"}).json()["id"]
        signup(c, "user_b")
        cid = c.post(f"/community/posts/{pid}/comments", json={"body": "첫 댓글"}).json()["id"]
        assert c.delete(f"/community/comments/{cid}").status_code == 204
        assert c.post(f"/community/posts/{pid}/comments", json={"body": "다시"}).status_code == 429


def test_parallel_posts_cannot_exceed_limit(tmp_path):
    with TestClient(create_app(settings(tmp_path, post_daily_limit=3))) as c:
        signup(c, "user_a")
        with ThreadPoolExecutor(10) as pool:
            codes = list(pool.map(lambda i: c.post("/community/posts", json={"title": f"글{i}", "body": "x"}).status_code,
                                  range(10)))
        assert sorted(codes) == [201] * 3 + [429] * 7


def test_post_detail_shows_latest_comments_without_blocking_new_ones(client, monkeypatch):
    from app.api import community
    monkeypatch.setattr(community, "COMMENTS_SHOWN", 2)
    admin_login(client)
    pid = client.post("/community/posts", json={"title": "공지", "body": "x"}).json()["id"]
    for i in range(4):
        assert client.post(f"/community/posts/{pid}/comments", json={"body": f"댓글{i}"}).status_code == 201
    post = client.get(f"/community/posts/{pid}").json()
    assert post["comment_total"] == 4 and [c["body"] for c in post["comments"]] == ["댓글2", "댓글3"]
    assert client.get("/community/posts").json()["items"][0]["comment_count"] == 4


def test_waitlist_dedupes_and_is_limited(client, monkeypatch):
    from app.api import waitlist
    monkeypatch.setattr(waitlist, "WAITLIST_DAILY_LIMIT", 2)
    signup(client, "user_a")
    for _ in range(2):
        assert client.post("/waitlist", json={"email": "me@example.com"}).status_code == 201
    db = client.app.state.session_factory()
    assert db.scalar(select(func.count(WaitlistEntry.id))) == 1  # 같은 이메일은 한 번만 저장
    db.close()
    # 이미 있는 이메일도 횟수를 세므로, 상한 뒤에는 있든 없든 같은 응답 (명단에 있는지 알아낼 수 없다)
    for email in ("me@example.com", "unknown@example.com"):
        r = client.post("/waitlist", json={"email": email})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_waitlist"


def test_habitat_creation_is_limited(client, monkeypatch):
    from app.api import habitats
    monkeypatch.setattr(habitats, "HABITAT_DAILY_LIMIT", 2)
    signup(client, "user_a")
    assert [client.post("/habitats", json=habitat_body()).status_code for _ in range(3)] == [201, 201, 429]


def test_admin_is_exempt_from_member_caps_and_records_nothing(tmp_path, monkeypatch):
    """회원별 24시간 상한(사육 환경·대기 신청·글·댓글)은 관리자를 세지도 기록하지도 않는다. 회원은 상한 0 이면 바로 막힌다."""
    from app.api import habitats, waitlist
    monkeypatch.setattr(habitats, "HABITAT_DAILY_LIMIT", 0)
    monkeypatch.setattr(waitlist, "WAITLIST_DAILY_LIMIT", 0)
    with TestClient(create_app(settings(tmp_path, post_daily_limit=0, comment_daily_limit=0))) as c:
        admin_login(c)
        for _ in range(2):
            assert c.post("/habitats", json=habitat_body()).status_code == 201
            assert c.post("/waitlist", json={"email": "me@example.com"}).status_code == 201
            pid = c.post("/community/posts", json={"title": "공지", "body": "x"}).json()["id"]
            assert c.post(f"/community/posts/{pid}/comments", json={"body": "댓글"}).status_code == 201
        with c.app.state.session_factory() as db:
            assert db.scalars(select(UsageEvent.kind)).all() == []
        signup(c, "user_a")
        for path, body, code in [("/habitats", habitat_body(), "too_many_habitats"),
                                 ("/waitlist", {"email": "me@example.com"}, "too_many_waitlist"),
                                 ("/community/posts", {"title": "t", "body": "x"}, "too_many_posts"),
                                 (f"/community/posts/{pid}/comments", {"body": "댓글"}, "too_many_comments")]:
            r = c.post(path, json=body)
            assert r.status_code == 429 and r.json()["detail"]["code"] == code, path


# ── 닉네임 위장 ────────────────────────────────────────────


@pytest.mark.parametrize("nickname,status", [
    ("관​리자", 422),                 # 폭 없는 공백
    ("관리ㅤ자", 422),                 # 한글 채움 문자
    ("‮자리관", 422),                 # 방향 바꾸기
    ("NestFоrge 팬", 422),            # 키릴 문자 о
    ("ＮｅｓｔＦｏｒｇｅ 운영팀", 409),     # 전각 → NFKC 로 같은 글자
    ("Nest Forge 운영팀", 409),       # NBSP → 공백
    ("NestF0rge", 409),                    # 숫자 닮은꼴
    ("관리자", 409),
    ("운영팀장", 409),
    ("햄찌맘", 409),                       # 이미 있음
    ("햄찌맘", 409),  # 같은 닉네임의 결합형(NFD)
    ("햄 찌 맘", 409),                     # 공백만 다름
    ("햄찌-맘", 409),                      # 구분 기호만 다름
    ("콩이 아빠", 201),
    ("Kong_2.0", 201),
    ("ㅋㅋ맘", 201),                       # 한글 낱자는 그대로 쓸 수 있다
    ("\uffa1\uffa1맘", 422),                # 반각 한글 자모 → NFKC 가 조합용 자모로 바꿈 (허용 안 함)
])
def test_lookalike_nicknames_are_rejected(client, nickname, status):
    signup(client, "victim_1", "햄찌맘")
    client.cookies.clear()
    r = client.post("/auth/signup", json={"username": "copycat_1", "nickname": nickname, "password": PW})
    assert r.status_code == status, r.text


def test_compat_jamo_nickname_is_stored_as_typed(client):
    signup(client, "user_a", "ㅋㅋ 햄찌")
    assert client.get("/auth/me").json()["user"]["nickname"] == "ㅋㅋ 햄찌"


def test_nickname_change_uses_normalized_key(client):
    signup(client, "victim_1", "햄찌맘")
    signup(client, "user_b", "비비")
    assert client.patch("/me", json={"nickname": "햄찌 맘"}).status_code == 409
    assert client.patch("/me", json={"nickname": "관​리자"}).status_code == 422
    r = client.patch("/me", json={"nickname": "Ｂｉｂｉ"})
    assert r.status_code == 200 and r.json()["user"]["nickname"] == "Bibi"


def test_bidi_controls_rejected_in_posts(client):
    signup(client, "user_a")
    assert client.post("/community/posts", json={"title": "‮목제", "body": "x"}).status_code == 422


# ── 로그인·비밀번호 시도 제한 ──────────────────────────────


def test_successful_login_does_not_reset_ip_failures(client):
    signup(client, "user_a")
    signup(client, "victim_1")
    client.cookies.clear()
    for i in range(9):
        assert client.post("/auth/login", json={"username": "victim_1", "password": f"guess-{i}xx"}).status_code == 401
    assert client.post("/auth/login", json={"username": "user_a", "password": PW}).status_code == 200
    assert client.post("/auth/login", json={"username": "victim_1", "password": "guess-9xx"}).status_code == 401
    assert client.post("/auth/login", json={"username": "victim_1", "password": PW}).status_code == 429


def test_password_change_attempts_are_limited(client):
    signup(client, "user_a")
    body = {"current_password": "wrong-password", "new_password": "new-password-123"}
    assert [client.post("/me/password", json=body).status_code for _ in range(6)] == [400] * 5 + [429]
    ok = {"current_password": PW, "new_password": "new-password-123"}
    assert client.post("/me/password", json=ok).status_code == 429  # 맞는 비밀번호도 잠시 막힌다


def test_concurrent_login_burst_is_limited(tmp_path):
    """비밀번호 확인을 기다리는 동안 몰려온 요청도 '진행 중인 시도'로 세어, 한꺼번에 보내도 10번 넘게 맞혀 볼 수 없다."""
    import asyncio

    import httpx

    s = settings(tmp_path, client_ip_header="x-test-ip")
    app = create_app(s)

    async def burst(n: int, body: dict) -> list[int]:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
                ok = await ac.post("/auth/signup", json={"username": "victim_1", "nickname": "피해자", "password": PW})
                assert ok.status_code == 201
                ac.cookies.clear()
                rs = await asyncio.gather(*[ac.post("/auth/login", json=body, headers={"x-test-ip": "198.51.100.9"})
                                            for _ in range(n)])
                return [r.status_code for r in rs]

    codes = asyncio.run(burst(60, {"username": "victim_1", "password": "wrong-guess"}))
    assert codes.count(401) <= 10 and codes.count(429) == 60 - codes.count(401)


def test_limiter_acquire_counts_inflight_attempts():
    lim = LoginRateLimiter(max_failures=3, window_s=900, max_inflight=10)
    assert [lim.acquire("k") for _ in range(5)] == [True, True, True, False, False]
    lim.release("k", failed=False)          # 성공한 시도는 기록하지 않는다
    assert lim.acquire("k")
    for _ in range(3):
        lim.release("k", failed=True)
    assert not lim.acquire("k") and lim.blocked("k")
    busy = LoginRateLimiter(max_failures=100, max_inflight=2)
    assert [busy.acquire("k") for _ in range(3)] == [True, True, False]


def test_signup_limiter_fails_open_when_full():
    lim = LoginRateLimiter(max_failures=1, window_s=3600, max_keys=3, fail_closed=False)
    for k in ("a", "b", "c", "d"):
        lim.record_failure(k)
    assert len(lim) == 3 and not lim.blocked("new-key")
    closed = LoginRateLimiter(max_failures=1, window_s=3600, max_keys=3)
    for k in ("a", "b", "c", "d"):
        closed.record_failure(k)
    assert closed.blocked("new-key")


def test_signup_per_ip_zero_means_unlimited(tmp_path):
    with TestClient(create_app(settings(tmp_path, signup_per_ip_per_hour=0))) as c:
        for i in range(8):
            signup(c, f"user_{i:02d}")
        assert c.get("/auth/me").json()["signup_enabled"] is True


# ── 설정·관리자 행 ─────────────────────────────────────────


def test_long_admin_username_is_misconfigured_not_crash(tmp_path):
    s = settings(tmp_path, admin_username="a" * 33)
    assert s.auth_mode == "misconfigured"
    with TestClient(create_app(s)) as c:
        assert c.get("/designs").status_code == 503


def test_admin_row_fallback_when_nickname_taken(tmp_path):
    s = settings(tmp_path)
    eng = make_engine(s.database_url)
    init_db(eng)
    factory = make_session_factory(eng)
    db = factory()
    _ensure_user_row(db, "oldadmin", "NestForge 운영팀")
    user = _ensure_user_row(db, "newadmin", "NestForge 운영팀")
    assert user.username == "newadmin" and user.nickname == "NestForge 운영팀-newadmin" and user.role == "admin"
    assert _ensure_user_row(db, "newadmin", "NestForge 운영팀").id == user.id
    db.close()
    eng.dispose()


def test_second_init_db_issues_no_ddl(tmp_path):
    eng = make_engine(settings(tmp_path).database_url)
    init_db(eng)
    seen: list[str] = []
    event.listen(eng, "before_cursor_execute", lambda *a: seen.append(a[2]))
    assert init_db(eng) == []
    assert not [q for q in seen if q.lstrip().upper().startswith(("CREATE", "ALTER"))]
    eng.dispose()


# ── DB 연결 반환 (동시 요청이 몰려도 풀이 막히지 않는다) ────────


@pytest.mark.skipif(not PG_URL, reason="TEST_PG_URL(Postgres) 에서만: 운영과 같은 연결 풀로 확인")
def test_burst_of_requests_does_not_exhaust_pool(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        member = signup(c, "user_a")
        c.post("/community/posts", json={"title": "글", "body": "x"})
        pid = c.get("/community/posts").json()["items"][0]["id"]
        c.cookies.clear()

        def get(job):
            path, token = job
            headers = {"cookie": f"{COOKIE_NAME}={token}"} if token else {}
            return c.get(path, headers=headers).status_code

        jobs = ([("/community/posts", None)] * 60 + [(f"/community/posts/{pid}", None)] * 60
                + [("/auth/me", member)] * 60 + [("/designs", member)] * 30)
        start = time.monotonic()
        with ThreadPoolExecutor(120) as pool:
            codes = list(pool.map(get, jobs))
        assert codes == [200] * len(jobs)
        assert time.monotonic() - start < 9  # pool_timeout(10초)까지 멈추지 않는다


@pytest.mark.parametrize("releasing", [True, False])
def test_connection_is_returned_before_response_serialization(tmp_path, releasing):
    """make_router 의 API 함수는 끝나자마자 연결을 풀에 돌려준다 (응답 직렬화는 다른 스레드 작업이다).
    releasing=False 는 비교용: 보통 APIRouter 는 직렬화 동안 연결을 쥐고 있다."""
    eng = create_engine(f"sqlite:///{tmp_path / 'p.db'}", pool_size=1, max_overflow=0)
    factory = make_session_factory(eng)
    seen: list[int] = []

    class Out(BaseModel):
        n: int

        @field_serializer("n")
        def _record(self, v: int) -> int:
            seen.append(eng.pool.checkedout())
            return v

    def get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    router = make_router() if releasing else APIRouter()

    @router.get("/x", response_model=Out)
    def x(db: Session = Depends(get_db)):
        return Out(n=db.scalar(text("SELECT 1")))

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        assert c.get("/x").json() == {"n": 1}
    assert seen and seen[-1] == (0 if releasing else 1)
    eng.dispose()


def test_users_have_nickname_keys(client):
    signup(client, "user_a", "Kong Ee")
    admin_login(client)
    db = client.app.state.session_factory()
    keys = dict(db.execute(select(User.username, User.nickname_key)).all())
    db.close()
    assert keys["user_a"] == "kongee" and keys["admin"] == "nestforge운영팀"
