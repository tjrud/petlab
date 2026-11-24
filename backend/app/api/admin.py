"""관리자 API: 부품 수요(해석기가 카탈로그에 없다고 한 부품) 보기·정리·내보내기.

가벼운 요청이다 (형상 커널·LLM SDK 를 불러오지 않는다). 회원 id 는 내보내지 않는다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Literal

from fastapi import Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, make_router
from app.auth import get_current_user
from app.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from app.models import PartRequest, PartRequestHit, User
from app.schemas import (
    EntityId,
    PartRequestDetailOut,
    PartRequestExample,
    PartRequestExportOut,
    PartRequestExportRow,
    PartRequestHitOut,
    PartRequestListOut,
    PartRequestOut,
    PartRequestPatchIn,
)
from app.services import part_requests as pr

router = make_router(prefix="/admin", tags=["관리"])

StatusFilter = Literal["open", "planned", "published", "rejected", "merged", "all"]
Sort = Literal["users", "count", "recent"]

LIST_EXAMPLES = 3
EXPORT_EXAMPLES = 5
DETAIL_HITS = 20


def require_admin(user: User = Depends(get_current_user)) -> User:
    """로그인하지 않았으면 401, 관리자가 아니면 403."""
    if not user.is_admin:
        raise ForbiddenError("관리자만 쓸 수 있어요.")
    return user


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _examples(db: Session, ids: list[str], per: int) -> dict[str, list[PartRequestExample]]:
    """요청마다 최근 예시(지우지 않은 요청 앞부분) per 개. 한 번의 질의로 (창 함수)."""
    if not ids:
        return {}
    rn = func.row_number().over(partition_by=PartRequestHit.request_id,
                                order_by=(PartRequestHit.created_at.desc(), PartRequestHit.id.desc())).label("rn")
    sub = (select(PartRequestHit.request_id, PartRequestHit.prompt_excerpt, PartRequestHit.lang,
                  PartRequestHit.created_at, rn)
           .where(PartRequestHit.request_id.in_(ids), PartRequestHit.prompt_excerpt != "")
           .subquery())
    out: dict[str, list[PartRequestExample]] = defaultdict(list)
    for rid, excerpt, lang, at, _ in db.execute(select(sub).where(sub.c.rn <= per).order_by(sub.c.request_id, sub.c.rn)):
        out[rid].append(PartRequestExample(excerpt=excerpt, lang=lang, at=_utc(at)))
    return out


def _out(r: PartRequest, examples: list[PartRequestExample], fulfilled: dict[str, list[str]]) -> PartRequestOut:
    return PartRequestOut(
        id=r.id, name_key=r.name_key, name_ko=r.name_ko, status=r.status,
        request_count=r.request_count, user_count=r.user_count,
        species_counts={str(k): int(v) for k, v in (r.species_counts or {}).items()},
        purposes=[p for p in (r.purposes or []) if isinstance(p, str)], examples=examples,
        published_key=r.published_key, fulfilled_by=fulfilled.get(r.name_key, []), merged_into=r.merged_into,
        note=r.note, first_seen_at=_utc(r.first_seen_at), last_seen_at=_utc(r.last_seen_at),
        updated_at=_utc(r.updated_at),
    )


def _ordered(stmt, sort: Sort):
    if sort == "count":
        keys = (PartRequest.request_count.desc(), PartRequest.user_count.desc(), PartRequest.last_seen_at.desc())
    elif sort == "recent":
        keys = (PartRequest.last_seen_at.desc(),)
    else:
        keys = (PartRequest.user_count.desc(), PartRequest.request_count.desc(), PartRequest.last_seen_at.desc())
    return stmt.order_by(*keys, PartRequest.id)


def _get(db: Session, request_id: str, lock: bool = False) -> PartRequest:
    r = pr.lock_request(db, PartRequest.id == request_id) if lock else db.get(PartRequest, request_id)
    if r is None:
        raise NotFoundError("부품 요청을 찾을 수 없어요.")
    return r


@router.get("/part-requests", response_model=PartRequestListOut, summary="부품 요청 목록 (관리자)")
def list_part_requests(status: StatusFilter = Query(default="open"), sort: Sort = Query(default="users"),
                       q: str | None = Query(default=None, max_length=80),
                       page: int = Query(default=1, ge=1, le=10_000), page_size: int = Query(default=20, ge=1, le=100),
                       db: Session = Depends(get_db), _: User = Depends(require_admin)):
    stmt = select(PartRequest)
    if status != "all":
        stmt = stmt.where(PartRequest.status == status)
    text = (q or "").strip()
    if text:
        conds = [PartRequest.name_ko.icontains(text, autoescape=True)]
        key = pr.normalize_name(text)
        if key:
            conds.append(PartRequest.name_key.contains(key, autoescape=True))
        stmt = stmt.where(or_(*conds))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(_ordered(stmt, sort).offset((page - 1) * page_size).limit(page_size)))
    examples = _examples(db, [r.id for r in rows], LIST_EXAMPLES)
    fulfilled = pr.fulfilled_by_map()
    return PartRequestListOut(items=[_out(r, examples.get(r.id, []), fulfilled) for r in rows],
                              total=total, page=page, page_size=page_size)


# /{id} 보다 먼저 둔다
@router.get("/part-requests/export", response_model=PartRequestExportOut,
            summary="부품 요청 내보내기 (관리자, 부품 만들기용 JSON)")
def export_part_requests(status: StatusFilter | None = Query(default=None), limit: int = Query(default=100, ge=1, le=200),
                         db: Session = Depends(get_db), _: User = Depends(require_admin)):
    stmt = select(PartRequest)
    if status is None:
        stmt = stmt.where(PartRequest.status.in_(("open", "planned")))
    elif status != "all":
        stmt = stmt.where(PartRequest.status == status)
    rows = list(db.scalars(_ordered(stmt, "users").limit(limit)))
    examples = _examples(db, [r.id for r in rows], EXPORT_EXAMPLES)
    return PartRequestExportOut(
        exported_at=datetime.now(UTC),
        requests=[PartRequestExportRow(
            id=r.id, name_key=r.name_key, name_ko=r.name_ko, status=r.status, users=r.user_count,
            count=r.request_count, species_counts={str(k): int(v) for k, v in (r.species_counts or {}).items()},
            purposes=[p for p in (r.purposes or []) if isinstance(p, str)], examples=examples.get(r.id, []),
            note=r.note,
        ) for r in rows],
    )


def _detail(db: Session, r: PartRequest) -> PartRequestDetailOut:
    hits = db.scalars(select(PartRequestHit).where(PartRequestHit.request_id == r.id)
                      .order_by(PartRequestHit.created_at.desc(), PartRequestHit.id.desc()).limit(DETAIL_HITS))
    base = _out(r, _examples(db, [r.id], LIST_EXAMPLES).get(r.id, []), pr.fulfilled_by_map())
    return PartRequestDetailOut(**base.model_dump(), hits=[
        PartRequestHitOut(excerpt=h.prompt_excerpt, purpose_ko=h.purpose_ko, species=h.species, size=h.size,
                          lang=h.lang, at=_utc(h.created_at))
        for h in hits])


@router.get("/part-requests/{request_id}", response_model=PartRequestDetailOut,
            summary="부품 요청 자세히 (관리자, 최근 20개 설계)")
def get_part_request(request_id: EntityId, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _detail(db, _get(db, request_id))


@router.patch("/part-requests/{request_id}", response_model=PartRequestOut,
              summary="부품 요청 정리 (관리자: 상태·메모·부품 키·합치기·예시 지우기)")
def update_part_request(request_id: EntityId, data: PartRequestPatchIn, db: Session = Depends(get_db),
                        _: User = Depends(require_admin)):
    sent = data.model_fields_set
    now = datetime.now(UTC)
    r = _get(db, request_id, lock=True)
    if r.status == "merged" and ({"status", "merged_into", "published_key"} & sent):
        raise ConflictError("다른 요청에 합친 요청은 상태를 바꿀 수 없어요.")
    if data.merged_into is not None:
        if data.status not in (None, "merged"):
            raise InvalidInputError("다른 요청에 합칠 때는 상태를 따로 정할 수 없어요.")
        if data.merged_into == r.id:
            raise InvalidInputError("요청을 자기 자신에 합칠 수 없어요.")
        target = pr.lock_request(db, PartRequest.id == data.merged_into)
        if target is None:
            raise InvalidInputError("합칠 부품 요청을 찾을 수 없어요.")
        if target.status == "merged":
            raise InvalidInputError("이미 다른 요청에 합친 요청에는 합칠 수 없어요.")
    elif data.status == "merged":
        raise InvalidInputError("merged 상태로 바꾸려면 합칠 요청을 함께 골라 주세요.")

    if "published_key" in sent and data.published_key is not None and data.published_key not in pr.library_keys():
        raise InvalidInputError("부품 라이브러리에 없는 부품 키예요.")
    key = data.published_key if "published_key" in sent else r.published_key
    if data.status == "published" and not key:
        raise InvalidInputError("published 상태로 바꾸려면 부품 라이브러리의 부품 키를 함께 적어 주세요.")
    if data.status == "published" and "published_key" not in sent and key not in pr.library_keys():
        raise InvalidInputError("부품 라이브러리에 없는 부품 키예요.")

    if "published_key" in sent:
        r.published_key = data.published_key
    if "note" in sent:
        r.note = data.note or None
    if data.status is not None and data.status != "merged":
        r.status = data.status
    if data.clear_examples:
        pr.clear_examples(db, r)
    r.updated_at = now
    if data.merged_into is not None:
        pr.merge(db, r, target, now)
    db.flush()
    return _out(r, _examples(db, [r.id], LIST_EXAMPLES).get(r.id, []), pr.fulfilled_by_map())
