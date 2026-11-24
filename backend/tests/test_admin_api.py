"""관리자 API (/admin/part-requests, /admin/library): 권한, 목록(쪽·정렬·거르기), 상태별 개수, 자세히, 정리(PATCH),
합치기, 내보내기, 부품 라이브러리 목록."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import PartRequest, PartRequestHit
from app.services import part_requests as pr
from tests.api_helpers import admin_login, signup, use
from tests.api_helpers import member_settings as settings

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


@pytest.fixture
def admin(client):
    admin_login(client)
    return client


def seed(client, name: str, designs: int = 1, users: int | None = None, size: str = "dwarf", purpose: str = "",
         prompt: str | None = None, start: datetime = T0, lang: str = "ko") -> str:
    """name 을 designs 개 설계에서 (회원 users 명이 나눠) 요청한 것으로 기록한다."""
    users = users or designs
    with client.app.state.session_factory() as db:
        for i in range(designs):
            with db.begin_nested():
                pr.record_missing(db, design_id=uuid4().hex, version_no=1,
                                  missing=[{"name_ko": name, "purpose_ko": purpose or f"{name} 쓰임새"}],
                                  prompt=prompt if prompt is not None else f"{name} 만들어줘 {i}",
                                  user_id=f"user{i % users}", species="hamster", size=size, lang=lang,
                                  now=start + timedelta(minutes=i))
        db.commit()
        return db.scalar(select(PartRequest.id).where(PartRequest.name_key == pr.normalize_name(name)))


def names(r) -> list[str]:
    assert r.status_code == 200, r.text
    return [x["name_ko"] for x in r.json()["items"]]


# ── 권한 ────────────────────────────────────────────────


@pytest.mark.parametrize("method, path", [
    ("get", "/admin/part-requests"), ("get", "/admin/part-requests/export"), ("get", "/admin/part-requests/counts"),
    ("get", "/admin/library"),
    ("get", "/admin/part-requests/" + "a" * 32), ("patch", "/admin/part-requests/" + "a" * 32),
])
def test_anonymous_401_member_403(client, method, path):
    use(client, None)
    kw = {"json": {"note": "x"}} if method == "patch" else {}
    r = getattr(client, method)(path, **kw)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "auth_required"
    signup(client, "member1")
    r = getattr(client, method)(path, **kw)
    assert r.status_code == 403 and r.json()["detail"]["message_ko"] == "관리자만 쓸 수 있어요."


def test_admin_gets_200_and_english_forbidden_message(client):
    signup(client, "member2")
    r = client.get("/admin/part-requests", headers={"X-Lang": "en"})
    assert r.status_code == 403 and r.json()["detail"]["message_ko"] == "Admins only."
    admin_login(client)
    r = client.get("/admin/part-requests")
    assert r.status_code == 200 and r.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


# ── 목록 ────────────────────────────────────────────────


def test_list_row_shape(admin):
    rid = seed(admin, "쳇바퀴", designs=5, users=3, purpose="달리기 운동")
    seed(admin, "쳇바퀴", designs=1, size="syrian", purpose="밤에 운동", start=T0 + timedelta(days=1))
    (row,) = admin.get("/admin/part-requests").json()["items"]
    assert row["id"] == rid and row["name_key"] == "쳇바퀴" and row["status"] == "open"
    assert (row["request_count"], row["user_count"]) == (6, 3)
    assert row["species_counts"] == {"hamster/dwarf": 5, "hamster/syrian": 1}
    assert row["purposes"] == ["밤에 운동", "달리기 운동"]
    assert [e["excerpt"] for e in row["examples"]] == ["쳇바퀴 만들어줘 0", "쳇바퀴 만들어줘 4", "쳇바퀴 만들어줘 3"]
    assert row["examples"][0]["lang"] == "ko" and row["examples"][0]["at"].startswith("2026-11-02T09:00:00")
    assert row["fulfilled_by"] == [] and row["published_key"] is None and row["merged_into"] is None
    assert row["first_seen_at"] == "2026-11-01T09:00:00Z" and row["last_seen_at"] == "2026-11-02T09:00:00Z"
    assert "user0" not in str(row)


def test_list_sort_filter_and_paging(admin):
    seed(admin, "쳇바퀴", designs=6, users=2)                         # users 2, count 6
    seed(admin, "해먹", designs=3, users=3)                           # users 3, count 3
    seed(admin, "그네", designs=1, start=T0 + timedelta(days=5))       # 가장 최근
    seed(admin, "시소_놀이기구", designs=2, users=1)
    assert names(admin.get("/admin/part-requests")) == ["해먹", "쳇바퀴", "시소_놀이기구", "그네"]
    assert names(admin.get("/admin/part-requests?sort=count")) == ["쳇바퀴", "해먹", "시소_놀이기구", "그네"]
    assert names(admin.get("/admin/part-requests?sort=recent"))[0] == "그네"

    r = admin.get("/admin/part-requests?page=2&page_size=3").json()
    assert (r["total"], r["page"], r["page_size"]) == (4, 2, 3) and [x["name_ko"] for x in r["items"]] == ["그네"]
    assert admin.get("/admin/part-requests?page_size=101").status_code == 422

    assert names(admin.get("/admin/part-requests", params={"q": "바퀴"})) == ["쳇바퀴"]
    assert names(admin.get("/admin/part-requests", params={"q": "시소 놀이"})) == ["시소_놀이기구"]  # 이름 열쇠로도
    assert names(admin.get("/admin/part-requests", params={"q": "_"})) == ["시소_놀이기구"]  # LIKE 와일드카드가 아님
    assert names(admin.get("/admin/part-requests", params={"q": "%"})) == []

    hid = admin.get("/admin/part-requests", params={"q": "해먹"}).json()["items"][0]["id"]
    assert admin.patch(f"/admin/part-requests/{hid}", json={"status": "planned"}).status_code == 200
    assert "해먹" not in names(admin.get("/admin/part-requests"))
    assert names(admin.get("/admin/part-requests?status=planned")) == ["해먹"]
    assert len(names(admin.get("/admin/part-requests?status=all"))) == 4
    assert admin.get("/admin/part-requests?status=bogus").status_code == 422


def test_counts_per_status_follow_the_search(admin):
    a = seed(admin, "쳇바퀴", designs=2)
    seed(admin, "해먹")
    b = seed(admin, "그네")
    c = seed(admin, "바퀴")
    admin.patch(f"/admin/part-requests/{b}", json={"status": "planned"})
    admin.patch(f"/admin/part-requests/{c}", json={"merged_into": a})
    r = admin.get("/admin/part-requests/counts")
    assert r.status_code == 200
    assert r.json() == {"counts": {"open": 2, "planned": 1, "published": 0, "rejected": 0, "merged": 1, "all": 4}}
    # 검색어가 있으면 그 이름만 (목록과 같은 조건)
    assert admin.get("/admin/part-requests/counts?q=바퀴").json()["counts"] == \
        {"open": 1, "planned": 0, "published": 0, "rejected": 0, "merged": 1, "all": 2}
    assert admin.get("/admin/part-requests/counts?q=없는이름").json()["counts"]["all"] == 0


def test_list_is_fast_for_1000_rows(admin):
    with admin.app.state.session_factory() as db:
        now = T0
        db.add_all(PartRequest(name_key=f"부품{i}", name_ko=f"부품{i}", purposes=["쓰임새"], request_count=i % 17,
                               user_count=i % 13, species_counts={"hamster/dwarf": i % 17}, status="open",
                               first_seen_at=now, last_seen_at=now + timedelta(seconds=i), updated_at=now)
                   for i in range(1000))
        db.commit()
        ids = list(db.scalars(select(PartRequest.id)))
        db.add_all(PartRequestHit(request_id=rid, design_id=uuid4().hex, version_no=1, user_id="u", species="hamster",
                                  size="dwarf", lang="ko", purpose_ko="", prompt_excerpt=f"예시 {k}",
                                  created_at=now + timedelta(seconds=k))
                   for rid in ids for k in range(4))
        db.commit()
    for sort in ("users", "count", "recent"):
        admin.get(f"/admin/part-requests?sort={sort}&page_size=100")  # 데우기
        best = float("inf")
        for _ in range(3):
            t = time.perf_counter()
            r = admin.get(f"/admin/part-requests?sort={sort}&page_size=100&page=3")
            best = min(best, time.perf_counter() - t)
        assert r.status_code == 200 and len(r.json()["items"]) == 100 and r.json()["total"] == 1000
        assert all(len(x["examples"]) == 3 for x in r.json()["items"])
        assert best <= 0.100, f"{sort}: {best * 1000:.0f} ms"


# ── 자세히 ───────────────────────────────────────────────


def test_detail_has_latest_20_hits_without_user_ids(admin):
    rid = seed(admin, "쳇바퀴", designs=25, users=4, prompt="연락은 010-1234-5678 로, 쳇바퀴")
    r = admin.get(f"/admin/part-requests/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["hits"]) == 20
    assert set(body["hits"][0]) == {"excerpt", "purpose_ko", "species", "size", "lang", "at"}
    assert body["hits"][0]["excerpt"] == "연락은 *** 로, 쳇바퀴"
    assert body["hits"][0]["at"] > body["hits"][-1]["at"]  # 최신 먼저
    text = r.text
    assert "user_id" not in text and "user0" not in text and "design_id" not in text
    assert admin.get("/admin/part-requests/" + "b" * 32).status_code == 404
    assert admin.get("/admin/part-requests/not-an-id").status_code == 422


# ── 정리 (PATCH) ─────────────────────────────────────────


def test_patch_status_note_and_clear_examples(admin):
    rid = seed(admin, "해먹", designs=2)
    r = admin.patch(f"/admin/part-requests/{rid}", json={"status": "planned", "note": " 다음 분기 "})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "planned" and r.json()["note"] == "다음 분기"
    r = admin.patch(f"/admin/part-requests/{rid}", json={"note": None})
    assert r.json()["note"] is None and r.json()["status"] == "planned"  # 보내지 않은 필드는 그대로
    assert admin.patch(f"/admin/part-requests/{rid}", json={"note": "x" * 501}).status_code == 422
    assert admin.patch(f"/admin/part-requests/{rid}", json={"bogus": 1}).status_code == 422
    assert admin.patch(f"/admin/part-requests/{rid}", json={"status": "done"}).status_code == 422

    assert admin.get(f"/admin/part-requests/{rid}").json()["examples"]
    r = admin.patch(f"/admin/part-requests/{rid}", json={"clear_examples": True})
    assert r.status_code == 200 and r.json()["examples"] == []
    assert all(h["excerpt"] == "" for h in admin.get(f"/admin/part-requests/{rid}").json()["hits"])
    assert admin.patch(f"/admin/part-requests/{rid}", json={"status": "rejected"}).json()["status"] == "rejected"


def test_patch_published_needs_a_library_key(admin, monkeypatch):
    rid = seed(admin, "갈림길")
    monkeypatch.setattr(pr, "library_keys", lambda: {"tunnel_junction@v1"})
    r = admin.patch(f"/admin/part-requests/{rid}", json={"status": "published"})
    assert r.status_code == 422 and "published" in r.json()["detail"]["message_ko"]
    r = admin.patch(f"/admin/part-requests/{rid}", json={"status": "published", "published_key": "deck_platform@v1"})
    assert r.status_code == 422 and r.json()["detail"]["message_ko"] == "부품 라이브러리에 없는 부품 키예요."
    assert admin.patch(f"/admin/part-requests/{rid}", json={"published_key": "Bad Key"}).status_code == 422
    r = admin.patch(f"/admin/part-requests/{rid}", json={"status": "published", "published_key": "tunnel_junction@v1"})
    assert r.status_code == 200 and (r.json()["status"], r.json()["published_key"]) == ("published", "tunnel_junction@v1")
    # 키를 먼저 적어 두고 나중에 상태만 바꿔도 된다
    rid2 = seed(admin, "분기")
    assert admin.patch(f"/admin/part-requests/{rid2}", json={"published_key": "tunnel_junction@v1"}).status_code == 200
    assert admin.patch(f"/admin/part-requests/{rid2}", json={"status": "published"}).json()["status"] == "published"


def test_fulfilled_by_comes_from_the_library(admin, monkeypatch):
    seed(admin, "터널 갈림길")
    monkeypatch.setattr(pr, "fulfilled_by_map", lambda: {"터널갈림길": ["tunnel_junction@v1"]})
    (row,) = admin.get("/admin/part-requests").json()["items"]
    assert row["fulfilled_by"] == ["tunnel_junction@v1"]


def test_fulfilled_by_map_reads_active_library_parts(monkeypatch):
    class FakeIndex:
        @staticmethod
        def fulfills():
            return {"tunnel_junction@v1": ["터널갈림길", "터널 분기"], "old_hub@v1": ["터널갈림길"]}

        @staticmethod
        def hidden_keys():
            return {"old_hub@v1"}

        @staticmethod
        def keys():
            return ["old_hub@v1", "tunnel_junction@v1"]

    monkeypatch.setattr(pr, "_library_index", lambda: FakeIndex)
    assert pr.fulfilled_by_map() == {"터널갈림길": ["tunnel_junction@v1"], "터널분기": ["tunnel_junction@v1"]}
    assert pr.library_keys() == {"old_hub@v1", "tunnel_junction@v1"}  # 숨긴 부품도 키는 있다
    monkeypatch.setattr(pr, "_library_index", lambda: None)
    assert pr.fulfilled_by_map() == {} and pr.library_keys() == set()


# ── 합치기 ───────────────────────────────────────────────


def test_merge_moves_hits_and_recounts(admin):
    with admin.app.state.session_factory() as db:
        shared = uuid4().hex  # 두 요청 모두에 나온 설계: 합치면 한 번만 센다
        for design, user, name, size in [(shared, "u1", "쳇바퀴", "dwarf"), (shared, "u1", "바퀴", "dwarf"),
                                         (uuid4().hex, "u2", "바퀴", "syrian"), (uuid4().hex, "u3", "쳇바퀴", "dwarf")]:
            with db.begin_nested():
                pr.record_missing(db, design_id=design, version_no=1, missing=[{"name_ko": name, "purpose_ko": name}],
                                  prompt=name, user_id=user, species="hamster", size=size, lang="ko", now=T0)
        db.commit()
        target = db.scalar(select(PartRequest.id).where(PartRequest.name_key == "쳇바퀴"))
        source = db.scalar(select(PartRequest.id).where(PartRequest.name_key == "바퀴"))

    assert admin.patch(f"/admin/part-requests/{source}", json={"merged_into": source}).status_code == 422
    assert admin.patch(f"/admin/part-requests/{source}", json={"merged_into": "c" * 32}).status_code == 422
    assert admin.patch(f"/admin/part-requests/{source}", json={"status": "merged"}).status_code == 422
    assert admin.patch(f"/admin/part-requests/{source}",
                       json={"merged_into": target, "status": "planned"}).status_code == 422

    r = admin.patch(f"/admin/part-requests/{source}", json={"merged_into": target})
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["merged_into"]) == ("merged", target)
    t = admin.get(f"/admin/part-requests/{target}").json()
    assert (t["request_count"], t["user_count"]) == (3, 3)
    assert t["species_counts"] == {"hamster/dwarf": 2, "hamster/syrian": 1}
    assert t["purposes"] == ["쳇바퀴", "바퀴"]
    assert len(t["hits"]) == 3
    assert admin.get(f"/admin/part-requests/{source}").json()["hits"] == []
    assert names(admin.get("/admin/part-requests?status=merged")) == ["바퀴"]

    # 합친 요청은 상태를 바꿀 수 없고, 합친 요청에는 합칠 수 없다
    assert admin.patch(f"/admin/part-requests/{source}", json={"status": "open"}).status_code == 409
    other = seed(admin, "해먹")
    r = admin.patch(f"/admin/part-requests/{other}", json={"merged_into": source})
    assert r.status_code == 422 and "이미" in r.json()["detail"]["message_ko"]
    assert admin.patch(f"/admin/part-requests/{source}", json={"note": "바퀴는 쳇바퀴로"}).status_code == 200


def test_merge_chain_redirects_earlier_merges(admin):
    a, b, c = seed(admin, "바퀴"), seed(admin, "쳇바퀴"), seed(admin, "운동 바퀴")
    assert admin.patch(f"/admin/part-requests/{a}", json={"merged_into": b}).status_code == 200
    assert admin.patch(f"/admin/part-requests/{b}", json={"merged_into": c}).status_code == 200
    rows = {x["id"]: x for x in admin.get("/admin/part-requests?status=all").json()["items"]}
    assert rows[a]["merged_into"] == c and rows[b]["merged_into"] == c
    assert rows[c]["request_count"] == 3
    seed(admin, "바퀴")  # 처음 합친 요청의 이름도 마지막 요청으로 센다
    assert admin.get(f"/admin/part-requests/{c}").json()["request_count"] == 4


# ── 내보내기 ─────────────────────────────────────────────


def test_export(admin):
    a = seed(admin, "쳇바퀴", designs=3, users=2, purpose="달리기 운동")
    b = seed(admin, "해먹", designs=1)
    c = seed(admin, "그네", designs=2)
    admin.patch(f"/admin/part-requests/{b}", json={"status": "planned"})
    admin.patch(f"/admin/part-requests/{c}", json={"status": "rejected"})
    r = admin.get("/admin/part-requests/export")
    assert r.status_code == 200
    body = r.json()
    assert body["exported_at"]
    assert [x["id"] for x in body["requests"]] == [a, b]  # 기본: open + planned, 회원 수 순
    first = body["requests"][0]
    assert set(first) == {"id", "name_key", "name_ko", "status", "users", "count", "species_counts", "purposes",
                          "examples", "note"}
    assert (first["users"], first["count"], first["purposes"]) == (2, 3, ["달리기 운동"])
    assert len(first["examples"]) == 3 and set(first["examples"][0]) == {"excerpt", "lang", "at"}
    assert [x["id"] for x in admin.get("/admin/part-requests/export?status=rejected").json()["requests"]] == [c]
    assert len(admin.get("/admin/part-requests/export?status=all&limit=2").json()["requests"]) == 2
    assert admin.get("/admin/part-requests/export?limit=201").status_code == 422
    assert "user0" not in r.text and "user_id" not in r.text


# ── 부품 라이브러리 목록 (/admin/library) ──────────────────


def test_library_list(admin, tmp_path, monkeypatch):
    from app.library import index
    from tests.test_library_api import DECK, JUNCTION, make_library

    run = {"verifier": "verify/1", "profile": "full", "key": JUNCTION, "result": "pass",
           "started_at": "2026-12-01T10:02:11Z", "seconds": 312.6,
           "counts": {"variants": 44, "unreachable": 0, "checks": 1312, "failed": 0},
           "schema": {"chars_added": 2210, "totals": {"hamster": 28140}, "gate_ok": {"hamster": True}}}
    root = make_library(tmp_path / "lib", {
        JUNCTION: {"request_ids": ["a" * 32]},
        DECK: {"role": "host", "status": "blocked", "verified_for": {"hamster": ["dwarf"]},
               "reason": {"ko": "안전 문제가 있습니다", "en": "There is a safety problem"}},
    }, reports={JUNCTION: [{"result": "fail", "profile": "quick"}, run]})
    (root / "parts" / "stray@v1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(index, "LIBRARY_DIR", root)
    index.clear_cache()
    try:
        r = admin.get("/admin/library")
        assert r.status_code == 200, r.text
        body = r.json()
        deck, hub = body["parts"]  # key 순
        assert hub == {
            "key": JUNCTION, "family": "tunnel_junction", "version": 1, "name_ko": index.read_part(JUNCTION)["name"]["ko"],
            "role": "room_host", "status": "active", "habitats": ["cage"],
            "verified_for": {"hamster": ["dwarf", "syrian"]}, "published_at": "2026-12-01",
            "fulfills": index.read_part(JUNCTION)["fulfills"], "superseded_by": None, "reason_ko": None,
            "request_ids": ["a" * 32],
            "report": {"result": "pass", "profile": "full", "verifier": "verify/1",
                       "started_at": "2026-12-01T10:02:11Z", "seconds": 312.6, "runs": 2, "variants": 44,
                       "checks": 1312, "failed": 0, "unreachable": 0, "schema_chars_added": 2210,
                       "gate_ok": {"hamster": True}},
        }
        assert (deck["key"], deck["status"], deck["role"]) == (DECK, "blocked", "host")
        assert deck["reason_ko"] == "안전 문제가 있습니다" and deck["report"] is None
        assert sorted(body["problems"]) == [f"{DECK}: report file missing", "stray@v1.json: not in the index"]
        # 폐기·차단 까닭은 영어 요청이면 영어로 (게시 도구가 library.json 에 넣는 짝)
        from app import i18n
        cat = i18n.Catalog(index.i18n_pairs())
        monkeypatch.setattr(i18n, "catalog", lambda: cat)
        en = admin.get("/admin/library", headers={"X-Lang": "en"}).json()["parts"]
        assert en[0]["reason_ko"] == "There is a safety problem" and en[1]["name_ko"] == index.read_part(JUNCTION)["name"]["en"]
    finally:
        index.clear_cache()


def test_library_list_when_empty(admin, tmp_path, monkeypatch):
    from app.library import index
    from tests.test_library_api import make_library

    monkeypatch.setattr(index, "LIBRARY_DIR", make_library(tmp_path / "lib", {}))
    index.clear_cache()
    try:
        assert admin.get("/admin/library").json() == {"parts": [], "problems": []}
    finally:
        index.clear_cache()
