"""부품 수요: 해석기가 카탈로그에 없다고 한 부품(DesignSpec.missing_parts)을 모아 센다.

설계를 저장할 때(DesignService._save_version) 같은 트랜잭션의 저장점(savepoint) 안에서 기록한다. 실패해도 설계는
저장된다. 같은 설계는 한 번만 센다 (고친 버전이 같은 부품을 다시 적어도). 회원 수는 서로 다른 회원으로 센다.

가벼운 모듈이다: SQLAlchemy 와 표준 라이브러리만 쓴다 (형상 커널·LLM SDK 를 불러오지 않는다).

옛 설계 버전에서 다시 모으기 (llm_spec.missing_parts, 같은 설계는 한 번만 세므로 여러 번 돌려도 같다):

    uv run python -m app.services.part_requests backfill [--db-url URL]
"""

from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Insert, delete, distinct, func, select, update
from sqlalchemy.orm import Session

from app.models import Design, DesignVersion, Habitat, PartRequest, PartRequestHit

log = logging.getLogger(__name__)

STATUSES = ("open", "planned", "published", "rejected", "merged")
MAX_NAMES = 5          # 명세 하나에서 세는 부품 이름 수
MAX_PURPOSES = 5       # 요청마다 남기는 서로 다른 쓰임새 수
NAME_KEY_LEN = 60
NAME_LEN = 80
PURPOSE_LEN = 160
EXCERPT_LEN = 200

# 이름 앞의 종 이름은 떼고 센다 ("햄스터용 쳇바퀴" = "쳇바퀴"). 긴 것부터
_NAME_PREFIXES = ("햄스터용", "햄스터", "hamster")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# 주소: 스킴(https://)·www. 로 시작하는 것, 경로가 붙은 도메인(instagram.com/…, bit.ly/…), 흔한 끝 이름의 도메인
_URL = re.compile(r"(?:https?://|www\.)\S+"
                  r"|\b[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}/\S*"
                  r"|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|kr|me|ly|io|co|gg|app|link|xyz)\b\S*", re.IGNORECASE)
# 전화번호·계좌 같은 7자리 이상 숫자 (숫자 사이에 -, ., 빈칸이 앞뒤 빈칸과 함께 끼어 있어도: "010 - 1234 - 5678")
_LONG_DIGITS = re.compile(r"\d(?:(?:\s*[-.]\s*|\s)?\d){6,}")
_SPACES = re.compile(r"\s+")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    """SQLite 는 시간대 없이 돌려준다 (저장은 UTC). 비교하기 전에 UTC 로 맞춘다."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def normalize_name(s: str) -> str:
    """수요를 묶는 열쇠: NFKC·대소문자 무시, 앞의 종 이름("햄스터용" 등)을 떼고, 글자·숫자만 남겨 60자까지.
    빈 문자열이면 세지 않는다."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKC", s).casefold().strip()
    for prefix in _NAME_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return "".join(c for c in s if c.isalnum())[:NAME_KEY_LEN]


def _scrub_text(s: str) -> str:
    s = _EMAIL.sub("***", s)
    s = _URL.sub("***", s)
    s = _LONG_DIGITS.sub("***", s)
    return _SPACES.sub(" ", s).strip()


def scrub(prompt: str) -> str:
    """관리자 화면에 보일 요청 앞부분: 이메일·주소(URL)·7자리 이상 숫자를 지우고 200자로 자른다."""
    if not isinstance(prompt, str):
        return ""
    return _scrub_text(prompt)[:EXCERPT_LEN]


def _names(missing: Iterable[Any] | None) -> list[tuple[str, str, str]]:
    """missing_parts (MissingPart 또는 저장된 dict) → [(열쇠, 이름, 쓰임새)]. 같은 열쇠는 처음 것만, 최대 5개."""
    out: dict[str, tuple[str, str, str]] = {}
    for m in missing or ():
        if isinstance(m, Mapping):
            name, purpose = m.get("name_ko"), m.get("purpose_ko")
        else:
            name, purpose = getattr(m, "name_ko", None), getattr(m, "purpose_ko", None)
        if not isinstance(name, str):
            continue
        key = normalize_name(name)
        if not key or key in out:
            continue
        name = _SPACES.sub(" ", name).strip()[:NAME_LEN]
        purpose = _scrub_text(purpose)[:PURPOSE_LEN] if isinstance(purpose, str) else ""
        out[key] = (key, name, purpose)
        if len(out) >= MAX_NAMES:
            break
    return list(out.values())


def _insert(db: Session, model: type) -> Insert:
    """INSERT … ON CONFLICT DO NOTHING 을 쓸 수 있는 방언별 insert (SQLite·Postgres)."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover - 지원하는 DB 는 둘뿐이다
        raise RuntimeError(f"unsupported database dialect: {dialect}")
    return insert(model)


def lock_request(db: Session, *where: Any) -> PartRequest | None:
    """행 잠금(Postgres)을 잡고 DB 의 최신 값으로 읽는다 (세션에 이미 있는 객체도 새로 채운다)."""
    stmt = select(PartRequest).where(*where).with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def _species_key(species: str, size: str) -> str:
    return f"{species}/{size}"


def _with_purpose(purposes: list | None, purpose: str) -> list[str]:
    old = [p for p in (purposes or []) if isinstance(p, str)]
    if not purpose or purpose in old:
        return old[:MAX_PURPOSES]
    return [purpose, *old][:MAX_PURPOSES]


def record_missing(db: Session, *, design_id: str, version_no: int, missing: Iterable[Any] | None, prompt: str,
                   user_id: str | None, species: str, size: str, lang: str, now: datetime | None = None) -> list[str]:
    """설계 버전 하나의 missing_parts 를 센다. 새로 센 요청의 id 목록을 돌려준다.

    부르는 쪽이 짧은 트랜잭션(또는 저장점)으로 감싸 커밋한다. 이름마다 문장 3~4개:
    요청 행 넣기(이미 있으면 그대로) → 잠그고 읽기 → 설계별 기록 넣기(이미 있으면 그만) → 횟수 갱신.
    행 잠금은 열쇠(name_key) 순서로 잡는다: 두 설계가 같은 두 이름을 반대 순서로 적어도 서로 기다리지 않는다
    (Postgres 교착 상태가 나면 한쪽 수요가 사라진다)."""
    names = sorted(_names(missing))
    if not names:
        return []
    now = now or _now()
    excerpt = scrub(prompt)
    lang = (lang or "ko")[:2]
    counted: list[str] = []
    for key, name, purpose in names:
        db.execute(_insert(db, PartRequest).values(
            id=uuid4().hex, name_key=key, name_ko=name, purposes=[], request_count=0, user_count=0,
            species_counts={}, status="open", first_seen_at=now, last_seen_at=now, updated_at=now,
        ).on_conflict_do_nothing(index_elements=["name_key"]))
        req = lock_request(db, PartRequest.name_key == key)
        if req is None:  # pragma: no cover - 바로 위에서 넣었거나 이미 있다
            continue
        if req.status == "merged" and req.merged_into:  # 합친 요청은 합쳐진 쪽으로 센다 (한 번만 따라간다)
            req = lock_request(db, PartRequest.id == req.merged_into) or req
        # 넣었는지는 RETURNING 으로 본다 (psycopg 는 ON CONFLICT DO NOTHING 의 rowcount 를 -1 로 준다)
        inserted = db.execute(_insert(db, PartRequestHit).values(
            id=uuid4().hex, request_id=req.id, design_id=design_id, version_no=version_no, user_id=user_id,
            species=species[:32], size=size[:32], lang=lang, purpose_ko=purpose, prompt_excerpt=excerpt,
            created_at=now,
        ).on_conflict_do_nothing(index_elements=["request_id", "design_id"]).returning(PartRequestHit.id))
        if inserted.scalar_one_or_none() is None:
            continue  # 같은 설계의 다른 버전에서 이미 셌다
        req.request_count = (req.request_count or 0) + 1
        req.user_count = db.scalar(select(func.count(distinct(PartRequestHit.user_id)))
                                   .where(PartRequestHit.request_id == req.id)) or 0
        sk = _species_key(species, size)
        counts = dict(req.species_counts or {})
        counts[sk] = int(counts.get(sk, 0)) + 1
        req.species_counts = counts
        req.purposes = _with_purpose(req.purposes, purpose)
        req.last_seen_at = max(_aware(req.last_seen_at), _aware(now)) if req.last_seen_at else now
        req.first_seen_at = min(_aware(req.first_seen_at), _aware(now)) if req.first_seen_at else now
        req.updated_at = now
        counted.append(req.id)
    db.flush()  # 실패가 저장점 안에서 드러나게
    return counted


# ── 관리 (app/api/admin.py) ──────────────────────────────────


def recount(db: Session, req: PartRequest) -> None:
    """설계별 기록에서 횟수·회원 수·종별 횟수를 다시 센다 (합친 뒤)."""
    hits = PartRequestHit.request_id == req.id
    req.request_count = db.scalar(select(func.count(PartRequestHit.id)).where(hits)) or 0
    req.user_count = db.scalar(select(func.count(distinct(PartRequestHit.user_id))).where(hits)) or 0
    rows = db.execute(select(PartRequestHit.species, PartRequestHit.size, func.count(PartRequestHit.id))
                      .where(hits).group_by(PartRequestHit.species, PartRequestHit.size))
    req.species_counts = {_species_key(sp, sz): n for sp, sz, n in sorted(rows, key=lambda r: (r[0], r[1]))}


def merge(db: Session, source: PartRequest, target: PartRequest, now: datetime | None = None) -> None:
    """source 를 target 에 합친다: 설계별 기록을 target 으로 옮기고(같은 설계가 이미 있으면 지운다) target 을 다시 센다.
    source 는 merged 가 되고, 예전에 source 로 합친 요청도 target 을 가리키게 한다 (새 수요가 한 번만 따라가도 되게).
    부르는 쪽이 두 행을 잠그고(lock_request) 조건(자기 자신·이미 합친 요청이 아님)을 확인한다."""
    now = now or _now()
    already = select(PartRequestHit.design_id).where(PartRequestHit.request_id == target.id)
    db.execute(delete(PartRequestHit).where(PartRequestHit.request_id == source.id,
                                            PartRequestHit.design_id.in_(already)))
    db.execute(update(PartRequestHit).where(PartRequestHit.request_id == source.id).values(request_id=target.id))
    db.execute(update(PartRequest).where(PartRequest.merged_into == source.id)
               .values(merged_into=target.id, updated_at=now))
    recount(db, target)
    purposes = [p for p in (target.purposes or []) if isinstance(p, str)]
    for p in source.purposes or []:
        if isinstance(p, str) and p not in purposes:
            purposes.append(p)
    target.purposes = purposes[:MAX_PURPOSES]
    target.first_seen_at = min(_aware(target.first_seen_at), _aware(source.first_seen_at))
    target.last_seen_at = max(_aware(target.last_seen_at), _aware(source.last_seen_at))
    target.updated_at = now
    source.status, source.merged_into, source.updated_at = "merged", target.id, now
    db.flush()


def clear_examples(db: Session, req: PartRequest) -> None:
    db.execute(update(PartRequestHit).where(PartRequestHit.request_id == req.id).values(prompt_excerpt=""))


# ── 부품 라이브러리 (app.library.index, 가볍다) ───────────────


def _library_index() -> Any | None:
    try:
        from app.library import index
    except ImportError:  # 부품 라이브러리가 없는 배포
        return None
    return index


def library_keys() -> set[str]:
    """부품 라이브러리에 있는 키 (상태와 상관없이). 요청을 published 로 바꿀 때 확인한다."""
    index = _library_index()
    return set(index.keys()) if index is not None else set()


def fulfilled_by_map() -> dict[str, list[str]]:
    """수요 열쇠(normalize_name) → 그 수요를 채우는 쓰는 중인(active) 라이브러리 부품 키 (부품 파일의 fulfills)."""
    index = _library_index()
    if index is None:
        return {}
    hidden = set(index.hidden_keys())
    out: dict[str, list[str]] = {}
    for key, names in sorted(index.fulfills().items()):
        if key in hidden:
            continue
        for name in names:
            k = normalize_name(name)
            if k and key not in out.get(k, []):
                out.setdefault(k, []).append(key)
    return out


# ── 옛 설계 버전에서 다시 모으기 ───────────────────────────────


def _guess_lang(prompt: str) -> str:
    """옛 버전에는 요청 언어가 없다: 한글이 있으면 한국어, 라틴 글자만 있으면 영어."""
    if re.search(r"[가-힣]", prompt or ""):
        return "ko"
    return "en" if re.search(r"[A-Za-z]", prompt or "") else "ko"


def backfill(db: Session, batch: int = 500) -> int:
    """모든 설계 버전을 오래된 것부터 다시 센다. 새로 센 (요청, 설계) 수를 돌려준다. 여러 번 돌려도 같다."""
    counted, last_id = 0, 0
    while True:
        rows = db.execute(
            select(DesignVersion, Design.owner_id, Habitat.species, Habitat.size)
            .join(Design, Design.id == DesignVersion.design_id)
            .join(Habitat, Habitat.id == Design.habitat_id)
            .where(DesignVersion.id > last_id)
            .order_by(DesignVersion.id)
            .limit(batch)
        ).all()
        if not rows:
            return counted
        for v, owner_id, species, size in rows:
            last_id = v.id
            spec = v.llm_spec if isinstance(v.llm_spec, dict) else {}
            missing = spec.get("missing_parts")
            if not isinstance(missing, list) or not missing:
                continue
            try:
                with db.begin_nested():
                    counted += len(record_missing(
                        db, design_id=v.design_id, version_no=v.version, missing=missing, prompt=v.prompt,
                        user_id=v.created_by or owner_id, species=species, size=size,
                        lang=_guess_lang(v.prompt), now=_aware(v.created_at) if v.created_at else None))
            except Exception:
                log.warning("part request backfill skipped version %s", v.id, exc_info=True)
        db.commit()
        db.expunge_all()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.services.part_requests")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill", help="rebuild part demand from stored design versions (idempotent)")
    b.add_argument("--db-url", help="database URL (default: DATABASE_URL from the settings)")
    args = parser.parse_args(argv)

    from app.config import get_settings
    from app.db import init_db, make_engine, make_session_factory

    engine = make_engine(args.db_url or get_settings().database_url)
    init_db(engine)  # 수요 테이블이 없으면 만든다
    db = make_session_factory(engine)()
    try:
        n = backfill(db)
    finally:
        db.close()
        engine.dispose()
    print(f"counted {n} new part request hits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
