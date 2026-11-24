"""부품 수요 기록 (app/services/part_requests.py): 이름 묶기, 연락처 지우기, 설계별 한 번 세기, 저장점, 다시 모으기."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from app.db import Base, init_db, make_engine, make_session_factory
from app.main import create_app
from app.models import DesignVersion, PartRequest, PartRequestHit
from app.services import part_requests as pr
from tests.api_helpers import PG_URL, make_design, signup, use
from tests.api_helpers import member_settings as settings

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'demand.db'}")
    init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def wheel(purpose: str = "달리기 운동", name: str = "쳇바퀴") -> dict:
    return {"name_ko": name, "purpose_ko": purpose}


def record(db, missing, *, design_id: str | None = None, version_no: int = 1, user_id: str | None = "u1",
           species: str = "hamster", size: str = "dwarf", prompt: str = "은신처랑 쳇바퀴", now=T0, lang: str = "ko"):
    with db.begin_nested():
        out = pr.record_missing(db, design_id=design_id or uuid4().hex, version_no=version_no, missing=missing,
                                prompt=prompt, user_id=user_id, species=species, size=size, lang=lang, now=now)
    db.commit()
    return out


def row(db, key: str = "쳇바퀴") -> PartRequest:
    db.expire_all()
    return db.scalar(select(PartRequest).where(PartRequest.name_key == key))


# ── 이름 묶기·연락처 지우기 ──────────────────────────────────


@pytest.mark.parametrize("raw, key", [
    ("쳇바퀴", "쳇바퀴"),
    (" 쳇 바퀴 ", "쳇바퀴"),
    ("햄스터용 쳇바퀴", "쳇바퀴"),
    ("햄스터 쳇바퀴!", "쳇바퀴"),
    ("Hamster Wheel", "wheel"),
    ("Exercise-Wheel", "exercisewheel"),
    ("ＷＨＥＥＬ", "wheel"),                    # NFKC (전각 글자)
    ("STRASSE", "strasse"), ("Straße", "strasse"),  # casefold
    ("해먹 (매달린 것)", "해먹매달린것"),
    ("2층 침대", "2층침대"),
    ("햄스터", ""), ("hamster", ""), ("!!!", ""), ("", ""),
    ("가" * 100, "가" * 60),
])
def test_normalize_name(raw, key):
    assert pr.normalize_name(raw) == key


def test_normalize_name_is_idempotent():
    for s in ("햄스터용 쳇바퀴", "Big Wheel", "해먹 (매달린 것)"):
        k = pr.normalize_name(s)
        assert pr.normalize_name(k) == k


@pytest.mark.parametrize("prompt, want", [
    ("은신처랑 쳇바퀴 만들어줘", "은신처랑 쳇바퀴 만들어줘"),
    ("메일은 kim.hamster+1@example.co.kr 로", "메일은 *** 로"),
    ("참고 https://example.com/a?b=1 사진처럼", "참고 *** 사진처럼"),
    ("www.example.com 처럼", "*** 처럼"),
    ("전화 010-1234-5678 주세요", "전화 *** 주세요"),
    ("01012345678", "***"),
    ("가로 300 세로 200 높이 15 로", "가로 300 세로 200 높이 15 로"),  # 짧은 숫자는 그대로
    ("줄\n바꿈\t탭", "줄 바꿈 탭"),
])
def test_scrub(prompt, want):
    assert pr.scrub(prompt) == want


def test_scrub_truncates_to_200():
    assert len(pr.scrub("가" * 500)) == 200


# ── 기록 ────────────────────────────────────────────────


def test_first_insert_and_increment(db):
    (rid,) = record(db, [wheel()], design_id="d" * 32, user_id="u1", size="dwarf")
    r = row(db)
    assert r.id == rid and r.name_ko == "쳇바퀴" and r.status == "open"
    assert (r.request_count, r.user_count) == (1, 1)
    assert r.species_counts == {"hamster/dwarf": 1} and r.purposes == ["달리기 운동"]

    later = T0 + timedelta(days=2)
    record(db, [wheel("밤에 운동할 수 있게", name="햄스터용 쳇바퀴")], user_id="u2", size="syrian", now=later)
    r = row(db)
    assert (r.request_count, r.user_count) == (2, 2)
    assert r.name_ko == "쳇바퀴"  # 처음 본 표기
    assert r.species_counts == {"hamster/dwarf": 1, "hamster/syrian": 1}
    assert r.purposes == ["밤에 운동할 수 있게", "달리기 운동"]  # 최신 먼저
    assert pr._aware(r.last_seen_at) == later and pr._aware(r.first_seen_at) == T0
    hits = db.scalars(select(PartRequestHit).where(PartRequestHit.request_id == r.id)).all()
    assert {h.size for h in hits} == {"dwarf", "syrian"} and all(h.prompt_excerpt for h in hits)


def test_revision_of_the_same_design_is_not_recounted(db):
    d = uuid4().hex
    assert record(db, [wheel()], design_id=d, version_no=1)
    assert record(db, [wheel("다른 쓰임새")], design_id=d, version_no=2) == []
    r = row(db)
    assert r.request_count == 1 and r.purposes == ["달리기 운동"]
    assert db.query(PartRequestHit).count() == 1


def test_users_are_counted_distinct(db):
    for user in ("u1", "u1", "u2", None):
        record(db, [wheel()], user_id=user)
    r = row(db)
    assert r.request_count == 4 and r.user_count == 2  # 같은 회원은 한 번, 회원 없는 기록은 세지 않는다


def test_at_most_five_names_and_duplicates_collapse(db):
    names = [wheel(name="쳇바퀴"), wheel(name="햄스터용 쳇바퀴"), wheel(name="쳇 바퀴")] + [
        {"name_ko": f"부품{i}", "purpose_ko": ""} for i in range(8)]
    counted = record(db, names)
    assert len(counted) == 5
    keys = set(db.scalars(select(PartRequest.name_key)))
    assert keys == {"쳇바퀴", "부품0", "부품1", "부품2", "부품3"}
    assert row(db).request_count == 1


def test_bad_entries_are_skipped(db):
    class Obj:  # MissingPart 처럼 속성으로 읽는 항목도 받는다
        name_ko, purpose_ko = "해먹", None

    counted = record(db, [{"name_ko": None}, {"purpose_ko": "x"}, "쳇바퀴", {"name_ko": "!!!"}, Obj()])
    assert len(counted) == 1 and row(db, "해먹").purposes == []
    assert record(db, []) == [] and record(db, None) == []


def test_purposes_keep_five_distinct(db):
    for i in range(8):
        record(db, [wheel(f"쓰임새 {i}")])
    record(db, [wheel("쓰임새 7")])
    assert row(db).purposes == [f"쓰임새 {i}" for i in (7, 6, 5, 4, 3)]


def test_merged_request_is_followed_once(db):
    record(db, [wheel()])
    record(db, [{"name_ko": "바퀴", "purpose_ko": "운동"}])
    target, source = row(db), row(db, "바퀴")
    pr.merge(db, source, target)
    db.commit()
    record(db, [{"name_ko": "바퀴", "purpose_ko": "운동"}], user_id="u9")
    t, s = row(db), row(db, "바퀴")
    assert s.status == "merged" and s.merged_into == t.id
    assert t.request_count == 3 and t.user_count == 2
    assert db.query(PartRequestHit).filter(PartRequestHit.request_id == s.id).count() == 0


def test_recording_stays_fast_on_sqlite(db):
    record(db, [wheel()])  # 표·연결 데우기
    best = float("inf")
    for _ in range(5):
        t = time.perf_counter()
        record(db, [wheel()])
        best = min(best, time.perf_counter() - t)
    assert best <= 0.020, f"{best * 1000:.1f} ms"


# ── 설계 저장과 함께 (API) ─────────────────────────────────


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


def test_design_records_demand_once_per_design_and_shows_the_notice(client):
    signup(client, "wheelfan")
    d = make_design(client, prompt="은신처랑 쳇바퀴 만들어줘")
    assert d["current"]["missing_parts"] == [{"name_ko": "쳇바퀴", "purpose_ko": "달리기 운동"}]
    r = client.post(f"/designs/{d['id']}/revise", json={"prompt": "쳇바퀴도 꼭 넣어 주세요"})
    assert r.status_code == 201, r.text
    assert r.json()["current"]["missing_parts"][0]["name_ko"] == "쳇바퀴"
    with client.app.state.session_factory() as db:
        req = db.scalar(select(PartRequest).where(PartRequest.name_key == "쳇바퀴"))
        assert (req.request_count, req.user_count) == (1, 1)
        hit = db.scalar(select(PartRequestHit))
        assert (hit.design_id, hit.version_no, hit.species, hit.size, hit.lang) == (d["id"], 1, "hamster", "syrian", "ko")
        assert hit.prompt_excerpt == "은신처랑 쳇바퀴 만들어줘"
    # 설계를 지워도 수요는 남는다 (외래 키 없음)
    assert client.delete(f"/designs/{d['id']}").status_code == 204
    with client.app.state.session_factory() as db:
        assert db.query(PartRequestHit).count() == 1


def test_old_versions_without_missing_parts_show_an_empty_list(client):
    signup(client, "plainuser")
    d = make_design(client, prompt="은신처")
    assert d["current"]["missing_parts"] == []
    with client.app.state.session_factory() as db:
        v = db.scalar(select(DesignVersion))
        spec = dict(v.llm_spec)
        spec.pop("missing_parts", None)
        v.llm_spec = spec
        db.commit()
    assert client.get(f"/designs/{d['id']}").json()["current"]["missing_parts"] == []


def test_forced_failure_inside_the_savepoint_still_saves_the_design(client, monkeypatch):
    real = pr.record_missing

    def broken(db, **kw):
        real(db, **kw)  # 행을 넣은 뒤 실패한다: 저장점이 넣은 것까지 되돌린다
        raise RuntimeError("boom")

    monkeypatch.setattr(pr, "record_missing", broken)
    signup(client, "unlucky")
    d = make_design(client, prompt="은신처랑 쳇바퀴")
    assert d["current"]["version"] == 1
    with client.app.state.session_factory() as db:
        assert db.query(DesignVersion).count() == 1
        assert db.query(PartRequest).count() == 0 and db.query(PartRequestHit).count() == 0


def test_backfill_is_idempotent(client, tmp_path):
    signup(client, "fill1")
    make_design(client, prompt="은신처랑 쳇바퀴")
    tok2 = signup(client, "fill2")
    d2 = make_design(client, prompt="해먹이랑 쳇바퀴")
    use(client, tok2)
    assert client.post(f"/designs/{d2['id']}/revise", json={"prompt": "쳇바퀴"}).status_code == 201

    def snapshot(db):
        db.expire_all()
        return sorted((r.name_key, r.request_count, r.user_count, tuple(sorted(r.species_counts.items())))
                      for r in db.scalars(select(PartRequest)))

    with client.app.state.session_factory() as db:
        live = snapshot(db)
        assert live == [("쳇바퀴", 2, 2, (("hamster/syrian", 2),)), ("해먹", 1, 1, (("hamster/syrian", 1),))]
        db.query(PartRequestHit).delete()
        db.query(PartRequest).delete()
        db.commit()
        assert pr.backfill(db) == 3
        assert snapshot(db) == live
        assert pr.backfill(db) == 0
        assert snapshot(db) == live


def test_backfill_cli(client, capsys):
    signup(client, "clifan")
    make_design(client, prompt="그네 만들어줘")
    url = client.app.state.settings.database_url
    with client.app.state.session_factory() as db:
        db.query(PartRequestHit).delete()
        db.query(PartRequest).delete()
        db.commit()
    assert pr.main(["backfill", "--db-url", url]) == 0
    assert "counted 1" in capsys.readouterr().out
    with client.app.state.session_factory() as db:
        assert db.scalar(select(PartRequest.name_key)) == "그네"


# ── 스키마 ──────────────────────────────────────────────


def test_create_all_on_an_old_schema_db_creates_both_tables(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    old = [t for name, t in Base.metadata.tables.items() if name not in ("part_requests", "part_request_hits")]
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=old)
    assert "part_requests" not in inspect(engine).get_table_names()
    engine.dispose()

    engine = make_engine(url)
    init_db(engine)
    insp = inspect(engine)
    assert {"part_requests", "part_request_hits"} <= set(insp.get_table_names())
    assert {i["name"] for i in insp.get_indexes("part_requests")} >= {"ix_part_requests_status_users",
                                                                       "ix_part_requests_last_seen"}
    assert "ix_part_request_hits_request_created" in {i["name"] for i in insp.get_indexes("part_request_hits")}
    engine.dispose()


# ── Postgres 동시 기록 (TEST_PG_URL 이 있을 때만) ───────────────


@pytest.mark.skipif(not PG_URL, reason="TEST_PG_URL 이 없으면 Postgres 동시성 확인을 건너뛴다")
def test_postgres_concurrent_same_name_gives_one_row(tmp_path):
    from tests.api_helpers import db_url

    engine = make_engine(db_url(tmp_path))
    init_db(engine)
    factory = make_session_factory(engine)
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []

    def work(i: int) -> None:
        db = factory()
        try:
            barrier.wait()
            with db.begin_nested():
                pr.record_missing(db, design_id=uuid4().hex, version_no=1, missing=[wheel()], prompt="쳇바퀴",
                                  user_id=f"u{i}", species="hamster", size="dwarf", lang="ko")
            db.commit()
        except Exception as e:  # noqa: BLE001 - 실패는 아래에서 보여 준다
            errors.append(e)
        finally:
            db.close()

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    with factory() as db:
        rows = db.scalars(select(PartRequest)).all()
        assert len(rows) == 1 and (rows[0].request_count, rows[0].user_count) == (8, 8)
        assert rows[0].species_counts == {"hamster/dwarf": 8}
    engine.dispose()
