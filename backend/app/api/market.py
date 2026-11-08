"""탐색: 회원이 만든 구조물(완성 파일 SKP·3MF·STL, NestForge 설계)을 공유하는 곳.

파일은 배포 플랫폼의 요청 크기 한도(약 4.5MB) 때문에 3MB 조각으로 받아 DB 에 잠시 모았다가,
다 모이면 내용이 확장자와 맞는지 확인하고 저장소(Vercel Blob / 로컬 디스크)에 한 번에 올린다.
내려받기는 Blob 공개 주소로 넘겨 응답 크기 한도를 피한다.

작품을 올리면 커뮤니티에 소개 글을 함께 올릴 수 있다 (댓글은 그 글에서). NestForge 설계를 붙이면
소개 글에 그 설계 버전을 첨부하므로, 커뮤니티 공유와 같은 규칙으로 누구나 보고 내려받을 수 있다.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import Depends, Query, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import get_db, get_service, make_router
from app.api.layouts import ensure_layout_capacity
from app.auth import ACCOUNT_V6_PREFIX, client_key, get_current_user, get_optional_user, get_verified_user
from app.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.market_formats import (
    CONTENT_TYPES,
    FILE_ASSET_PREFIX,
    IMAGE_FORMATS,
    MAX_IMAGE_BYTES,
    MAX_MODEL_BYTES,
    MESH_FORMATS,
    MODEL_FORMATS,
    content_matches,
    format_of,
)
from app.lookup import get_or_404
from app.mesh_preview import PREVIEW_CONTENT_TYPE, build_preview, measure_and_preview, preview_key
from app.models import CageLayout, MarketEvent, MarketFile, MarketItem, MarketUpload, MarketUploadChunk, Post, User
from app.schemas import (
    ID_RE,
    MARKET_CATEGORIES,
    AuthorOut,
    MarketFileOut,
    MarketItemIn,
    MarketItemOut,
    MarketItemSummary,
    MarketItemUpdateIn,
    LayoutSnapshot,
    MarketListOut,
    UploadStartIn,
    UploadStartOut,
)
from app.services import recommend, usage
from app.services.market_view import file_out, item_formats, item_image, item_models, stored_blobs
from app.services.design_service import DesignService
from app.storage import LocalStorage, Storage, StorageError, Stored

router = make_router(prefix="/market", tags=["탐색"])
log = logging.getLogger(__name__)

CHUNK_BYTES = 3 * 1024 * 1024
UPLOAD_TTL = timedelta(hours=6)
MAX_PAGE = 1000
STALE_SWEEP_BATCH = 50  # 한 번에 정리하는 오래된 업로드 수 (요청 하나가 오래 걸리지 않게)
# 같은 작품을 다시 보거나 내려받은 기록은 이 시간 안이면 한 번으로 센다
EVENT_DEDUPE = {"view": timedelta(hours=1), "download": timedelta(hours=24), "copy": timedelta(hours=24)}


class StorageUnavailableError(AppError):
    status_code = 503
    code = "storage_unavailable"


def _storage(request: Request) -> Storage:
    s = request.app.state.market_storage
    if s is None:
        raise StorageUnavailableError("지금은 파일을 올릴 수 없어요. 파일 저장소가 아직 준비되지 않았어요.")
    return s


def _author(u: User) -> AuthorOut:
    return AuthorOut(nickname=u.nickname, role="admin" if u.is_admin else "member")


def _chunk_count(size: int) -> int:
    return -(-size // CHUNK_BYTES)


def _summary_fields(item: MarketItem) -> dict:
    img = item_image(item)
    return dict(
        id=item.id, title=item.title, category=item.category,
        category_name_ko=MARKET_CATEGORIES.get(item.category, item.category), author=_author(item.owner),
        formats=item_formats(item), image=file_out(img) if img else None, has_design=item.design_id is not None,
        has_layout=bool(item.layout),
        download_count=item.download_count, created_at=item.created_at,
    )


def _shared_design(db: Session, svc: DesignService, item: MarketItem):
    """붙인 설계 (그 버전이 아직 커뮤니티 글로 공개되어 있을 때만)."""
    if not item.design_id or item.design_version is None:
        return None
    if item.design_version not in svc.shared_versions(db, item.design_id):
        return None
    d = svc.get_design(db, item.design_id)
    return svc.shared_design_out(d, svc.get_version(db, d, item.design_version))


def _layout_out(svc: DesignService, item: MarketItem) -> LayoutSnapshot | None:
    lay = item.layout
    if not lay:
        return None
    sp = svc.rules.species_file.species.get(lay.get("species", ""))
    size = sp.sizes.get(lay.get("size", "")) if sp else None
    return LayoutSnapshot(**lay, size_name_ko=size.display_name if size else lay.get("size", ""))


def _item_out(db: Session, svc: DesignService, item: MarketItem, user: User | None) -> MarketItemOut:
    owner = user is not None and user.id == item.owner_id
    post_id = item.post_id if item.post_id and db.get(Post, item.post_id) is not None else None
    return MarketItemOut(
        **_summary_fields(item), description=item.description, files=[file_out(f) for f in item_models(item)],
        design=_shared_design(db, svc, item), layout=_layout_out(svc, item), post_id=post_id,
        updated_at=item.updated_at,
        can_edit=owner, can_delete=owner or (user is not None and user.is_admin),
    )


def _get_item(db: Session, item_id: str) -> MarketItem:
    return get_or_404(db, MarketItem, item_id, "작품을 찾을 수 없어요.")


def _limits(kind: str) -> tuple[set[str], int]:
    return (MODEL_FORMATS, MAX_MODEL_BYTES) if kind == "model" else (IMAGE_FORMATS, MAX_IMAGE_BYTES)


def _discard_uploads(db: Session, upload_ids: list[str]) -> None:
    """올리던 파일(조각 포함)을 지운다 (커밋은 부르는 쪽에서)."""
    if upload_ids:
        db.execute(delete(MarketUploadChunk).where(MarketUploadChunk.upload_id.in_(upload_ids)))
        db.execute(delete(MarketUpload).where(MarketUpload.id.in_(upload_ids)))


def _sweep_stale_uploads(db: Session) -> None:
    """오래된 미완성 업로드를 지운다. 누가 올리던 것이든 함께 정리한다 (조각이 DB 에 쌓이지 않게)."""
    cutoff = datetime.now(timezone.utc) - UPLOAD_TTL
    _discard_uploads(db, list(db.scalars(select(MarketUpload.id).where(MarketUpload.created_at < cutoff)
                                         .limit(STALE_SWEEP_BATCH))))


def _check_storage_quota(db: Session, user: User, size: int, limit_mb: int) -> None:
    """회원 1명이 올려 둔 파일(올리는 중인 것 포함)의 합계 상한."""
    stored = db.scalar(select(func.coalesce(func.sum(MarketFile.size), 0)).where(MarketFile.owner_id == user.id)) or 0
    pending = db.scalar(select(func.coalesce(func.sum(MarketUpload.size), 0))
                        .where(MarketUpload.owner_id == user.id)) or 0
    if stored + pending + size > limit_mb * 1024 * 1024:
        raise AppError(f"올려 둔 파일이 {limit_mb}MB를 넘어요. 안 쓰는 파일을 지운 뒤 다시 올려 주세요.",
                       code="storage_quota_exceeded")


# ── 설정 ──

@router.get("/config", summary="올리기 설정 (누구나)")
def market_config(request: Request) -> dict:
    return {
        "uploads_enabled": request.app.state.market_storage is not None,
        "chunk_bytes": CHUNK_BYTES,
        "max_model_bytes": MAX_MODEL_BYTES,
        "max_image_bytes": MAX_IMAGE_BYTES,
        "model_formats": sorted(MODEL_FORMATS),
        "image_formats": sorted(IMAGE_FORMATS),
        "categories": [{"key": k, "name_ko": v} for k, v in MARKET_CATEGORIES.items()],
    }


# ── 파일 올리기 (조각) ──

@router.post("/uploads", response_model=UploadStartOut, status_code=status.HTTP_201_CREATED, summary="파일 올리기 시작")
def start_upload(data: UploadStartIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_verified_user)):
    _storage(request)
    fmt = format_of(data.filename)
    allowed, max_bytes = _limits(data.kind)
    if fmt not in allowed:
        names = "·".join(sorted(f.upper() for f in allowed))
        raise AppError(f"{names} 파일만 올릴 수 있어요.", code="unsupported_format")
    if data.size > max_bytes:
        raise AppError(f"파일은 {max_bytes // (1024 * 1024)}MB까지 올릴 수 있어요.", code="file_too_large")
    settings = request.app.state.settings
    _sweep_stale_uploads(db)
    _check_storage_quota(db, user, data.size, settings.market_storage_per_user_mb)
    limit = settings.market_upload_daily_limit
    usage.reserve_per_member(db, "market_upload", user, limit, f"파일은 24시간에 {limit}개까지 올릴 수 있어요.",
                             "too_many_uploads")
    up = MarketUpload(owner_id=user.id, kind=data.kind, filename=data.filename, format=fmt, size=data.size)
    db.add(up)
    db.commit()
    return UploadStartOut(id=up.id, chunk_bytes=CHUNK_BYTES, chunks=_chunk_count(data.size))


def _my_upload(db: Session, upload_id: str, user: User) -> MarketUpload:
    return get_or_404(db, MarketUpload, upload_id, "올리던 파일을 찾을 수 없어요. 처음부터 다시 올려 주세요.",
                      owner_id=user.id)


@router.put("/uploads/{upload_id}/chunks/{n}", status_code=status.HTTP_204_NO_CONTENT, summary="파일 조각 올리기")
async def put_chunk(upload_id: str, n: int, request: Request, user: User = Depends(get_verified_user)):
    # 조각 크기보다 큰 본문은 읽기 전에 거절한다
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError:
        declared = 0
    if declared > CHUNK_BYTES:
        raise AppError("조각이 너무 커요.", code="bad_chunk")
    # Content-Length 가 없는(chunked) 요청도 조각 크기를 넘으면 읽다가 멈춘다
    buf = bytearray()
    async for part in request.stream():
        buf += part
        if len(buf) > CHUNK_BYTES:
            raise AppError("조각이 너무 커요.", code="bad_chunk")
    body = bytes(buf)
    # 본문을 다 받은 뒤에 짧게 DB 에 쓴다
    factory = request.app.state.session_factory
    with factory() as db:
        up = _my_upload(db, upload_id, user)
        chunks = _chunk_count(up.size)
        if not 0 <= n < chunks:
            raise AppError("조각 번호가 맞지 않아요.", code="bad_chunk")
        expected = CHUNK_BYTES if n < chunks - 1 else up.size - CHUNK_BYTES * (chunks - 1)
        if len(body) != expected:
            raise AppError("조각 크기가 맞지 않아요. 다시 올려 주세요.", code="bad_chunk")
        db.merge(MarketUploadChunk(upload_id=up.id, n=n, data=body))
        db.commit()
    return Response(status_code=204)


@router.post("/uploads/{upload_id}/complete", response_model=MarketFileOut, summary="파일 올리기 마치기")
def complete_upload(upload_id: str, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_verified_user)):
    storage = _storage(request)
    up = _my_upload(db, upload_id, user)
    chunks = _chunk_count(up.size)
    have = db.scalar(select(func.count()).select_from(MarketUploadChunk)
                     .where(MarketUploadChunk.upload_id == up.id)) or 0
    if have != chunks:
        raise AppError("아직 다 올라오지 않았어요. 다시 올려 주세요.", code="upload_incomplete")
    # 조각 행을 객체로 불러오지 않고 내용만 이어 붙인다 (메모리에 파일이 두 벌 생기지 않게)
    data = b"".join(db.scalars(select(MarketUploadChunk.data).where(MarketUploadChunk.upload_id == up.id)
                               .order_by(MarketUploadChunk.n)))
    if len(data) != up.size:
        raise AppError("파일 크기가 맞지 않아요. 다시 올려 주세요.", code="upload_incomplete")
    if not content_matches(up.format, data):
        _discard_uploads(db, [up.id])
        db.commit()
        raise AppError(f"{up.format.upper()} 파일이 아니거나 손상된 파일이에요.", code="bad_file_content")
    f = MarketFile(owner_id=user.id, kind=up.kind, filename=up.filename, format=up.format, size=up.size,
                   sha256=hashlib.sha256(data).hexdigest(), storage_key="")
    f.id = up.id  # 저장 키와 파일 ID 를 같게 (추측하기 어려운 무작위 값)
    # 저장하기 전에 잰다: 읽다가 실패해도 저장소에 주인 없는 파일이 남지 않게
    f.dims_mm, preview_blob = measure_and_preview(f.format, data)
    try:
        stored = storage.put(f"market/{f.id}/{f.id}.{f.format}", data, CONTENT_TYPES[up.format])
    except StorageError as e:
        raise StorageUnavailableError("파일을 저장하지 못했어요. 잠시 후 다시 올려 주세요.") from e
    f.storage_key, f.url = stored.key, stored.url
    _store_preview(storage, f, preview_blob)
    _discard_uploads(db, [up.id])
    db.add(f)
    try:
        db.commit()
    except (IntegrityError, StaleDataError) as e:
        # 같은 업로드를 동시에 마친 요청이 먼저 끝났다 (저장 키가 같으므로 저장소 파일은 그대로 둔다)
        db.rollback()
        raise ConflictError("이미 올라간 파일이에요. 목록을 새로 고쳐 주세요.", code="upload_completed") from e
    return file_out(f)


def _store_preview(storage: Storage, f: MarketFile, blob: bytes | None) -> bool:
    """3D 미리보기용 가벼운 메시(mesh_preview.py)를 원본 옆에 저장한다. 없거나 못 저장하면 화면이 원본을 쓴다"""
    if blob is None or f.format not in MESH_FORMATS:
        return False
    try:
        stored = storage.put(preview_key(f.id), blob, PREVIEW_CONTENT_TYPE)
    except StorageError:
        log.warning("3D 미리보기 메시를 저장하지 못했습니다 (%s)", f.id, exc_info=True)
        return False
    f.preview_url, f.preview_size = stored.url, len(blob)
    return True


# ── 작품 ──

@router.get("/items", response_model=MarketListOut, summary="작품 목록 (최신순, 누구나)")
def list_items(page: int = Query(default=1, ge=1, le=MAX_PAGE), page_size: int = Query(default=24, ge=1, le=48),
               category: str | None = Query(default=None, max_length=32), db: Session = Depends(get_db)):
    cond = MarketItem.category == category if category in MARKET_CATEGORIES else True
    total = db.scalar(select(func.count(MarketItem.id)).where(cond)) or 0
    rows = db.scalars(
        select(MarketItem).where(cond).options(selectinload(MarketItem.owner), selectinload(MarketItem.files))
        .order_by(MarketItem.created_at.desc(), MarketItem.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return MarketListOut(items=[MarketItemSummary(**_summary_fields(i)) for i in rows], total=total,
                         page=page, page_size=page_size)


@router.post("/items", response_model=MarketItemOut, status_code=status.HTTP_201_CREATED, summary="작품 올리기")
def create_item(data: MarketItemIn, request: Request, db: Session = Depends(get_db),
                svc: DesignService = Depends(get_service), user: User = Depends(get_verified_user)):
    if not data.file_ids and data.design_id is None and data.layout_id is None:
        raise AppError("파일을 올리거나 NestForge 설계·가상 케이지 배치안을 하나 골라 주세요.", code="empty_item")
    if len(set(data.file_ids)) != len(data.file_ids):
        raise AppError("같은 파일을 두 번 넣었어요.", code="duplicate_file")
    files = []
    for fid in [*data.file_ids, *([data.image_file_id] if data.image_file_id else [])]:
        f = db.get(MarketFile, fid)
        if f is None or f.owner_id != user.id or f.item_id is not None:
            raise NotFoundError("올린 파일을 찾을 수 없어요. 다시 올려 주세요.")
        files.append(f)
    if any(f.kind != "model" for f in files[: len(data.file_ids)]) or (
        data.image_file_id and files[-1].kind != "image"
    ):
        raise AppError("작품 파일과 미리보기 이미지를 맞는 칸에 넣어 주세요.", code="wrong_file_kind")
    version = None
    if data.design_id is not None:
        design = svc.get_editable_design(db, data.design_id, user)  # 내 설계만
        version = svc.get_version(db, design, data.design_version).version
    snapshot, layout_files = None, []
    if data.layout_id is not None:
        lay = get_or_404(db, CageLayout, data.layout_id, "배치안을 찾을 수 없어요.", owner_id=user.id)
        snapshot = _layout_snapshot(lay)
        # 배치에 넣은 내 파일은 이 배치를 보는 사람도 3D 로 볼 수 있게 공개한다 (작품에 붙은 파일은 이미 공개)
        layout_files = [f for f in _owned_files(db, _layout_file_ids(snapshot), user.id) if f.item_id is None]
    settings = request.app.state.settings
    limit = settings.market_item_daily_limit
    usage.reserve_per_member(db, "market_item", user, limit, f"작품은 24시간에 {limit}개까지 올릴 수 있어요.",
                             "too_many_items")
    # 설계를 붙이면 소개 글이 있어야 공개된다 (커뮤니티 공유와 같은 규칙)
    with_post = data.post_to_community or data.design_id is not None
    if with_post:
        plimit = settings.post_daily_limit
        usage.reserve_per_member(db, "post", user, plimit, f"글은 24시간에 {plimit}개까지 쓸 수 있어요.",
                                 "too_many_posts")
    item = MarketItem(owner_id=user.id, title=data.title, description=data.description, category=data.category,
                      design_id=data.design_id, design_version=version, layout=snapshot)
    for f in layout_files:
        f.shared = True
    db.add(item)
    db.flush()
    for f in files:
        f.item_id = item.id
    if with_post:
        post = Post(author_id=user.id, title=f"[탐색] {data.title}"[:100], body=data.description,
                    design_id=data.design_id, design_version=version)
        db.add(post)
        db.flush()
        item.post_id = post.id
    db.commit()
    db.refresh(item)
    return _item_out(db, svc, item, user)


def _layout_snapshot(lay: CageLayout) -> dict:
    """배치안을 작품에 담아 둘 모양으로 (원본 배치안을 고치거나 지워도 공유한 배치는 그대로)."""
    return {"name": lay.name, "species": lay.species, "size": lay.size,
            "cage": {"width_mm": lay.cage_width_mm, "depth_mm": lay.cage_depth_mm, "height_mm": lay.cage_height_mm},
            "items": list(lay.items or [])}


def _layout_from_snapshot(snap: dict, owner: User) -> CageLayout:
    cage = snap["cage"]
    return CageLayout(owner_id=owner.id, name=f"{snap['name']} (탐색)"[:40], species=snap["species"],
                      size=snap["size"], cage_width_mm=cage["width_mm"], cage_depth_mm=cage["depth_mm"],
                      cage_height_mm=cage["height_mm"], items=list(snap["items"]))


def _layout_file_ids(snapshot: dict | None) -> set[str]:
    """배치에 놓은 '내 파일' 의 ID"""
    keys = (it.get("asset", "") for it in (snapshot or {}).get("items", []))
    return {k[len(FILE_ASSET_PREFIX):] for k in keys if k.startswith(FILE_ASSET_PREFIX)}


def _owned_files(db: Session, ids: set[str], owner_id: str) -> list[MarketFile]:
    ids = {i for i in ids if ID_RE.fullmatch(i)}
    if not ids:
        return []
    return list(db.scalars(select(MarketFile).where(MarketFile.id.in_(ids), MarketFile.owner_id == owner_id)))


def _unshare_layout_files(db: Session, item: MarketItem) -> None:
    """지우는 작품의 배치에만 들어 있던 파일을 다시 올린 사람만 볼 수 있게 한다."""
    ids = _layout_file_ids(item.layout)
    if not ids:
        return
    others = db.scalars(select(MarketItem.layout).where(MarketItem.owner_id == item.owner_id,
                                                        MarketItem.id != item.id, MarketItem.layout.is_not(None)))
    still = set().union(*(_layout_file_ids(lay) for lay in others))
    for f in _owned_files(db, ids - still, item.owner_id):
        f.shared = None


def _record(db: Session, user: User | None, item: MarketItem, kind: str) -> bool:
    """맞춤 추천용 기록 (로그인한 회원, 남의 작품만). 같은 작품을 EVENT_DEDUPE 안에 다시 하면 한 번으로 센다.
    새로 기록했으면 True"""
    if user is None or user.id == item.owner_id:
        return False
    since = datetime.now(timezone.utc) - EVENT_DEDUPE[kind]
    if db.scalar(select(MarketEvent.id).where(MarketEvent.user_id == user.id, MarketEvent.item_id == item.id,
                                              MarketEvent.kind == kind, MarketEvent.created_at >= since).limit(1)):
        return False
    db.add(MarketEvent(user_id=user.id, item_id=item.id, kind=kind))
    db.commit()
    return True


@router.get("/recommended", response_model=list[MarketItemSummary], summary="맞춤 추천 (로그인하면 내 설계·배치안·반려동물·본 작품 기준)")
def recommended(limit: int = Query(default=12, ge=1, le=48), db: Session = Depends(get_db),
                user: User | None = Depends(get_optional_user)):
    return [MarketItemSummary(**_summary_fields(it), reason_ko=reason)
            for it, reason in recommend.recommend(db, user, limit)]


@router.get("/items/{item_id}", response_model=MarketItemOut, summary="작품 보기 (누구나)")
def get_item(item_id: str, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
             user: User | None = Depends(get_optional_user)):
    item = _get_item(db, item_id)
    _record(db, user, item, "view")
    return _item_out(db, svc, item, user)


@router.patch("/items/{item_id}", response_model=MarketItemOut, summary="작품 고치기 (올린 사람만)")
def update_item(item_id: str, data: MarketItemUpdateIn, request: Request, db: Session = Depends(get_db),
                svc: DesignService = Depends(get_service), user: User = Depends(get_current_user)):
    item = _get_item(db, item_id)
    if item.owner_id != user.id:
        raise ForbiddenError("내가 올린 작품만 고칠 수 있어요.")
    for k in ("title", "description", "category"):
        v = getattr(data, k)
        if v is not None:
            setattr(item, k, v)
    old: list[Stored] = []
    if data.image_file_id is not None:
        img = get_or_404(db, MarketFile, data.image_file_id, "올린 이미지를 찾을 수 없어요. 다시 올려 주세요.",
                         owner_id=user.id)
        if img.kind != "image" or img.item_id is not None:
            raise AppError("미리보기에는 아직 붙이지 않은 이미지 파일만 쓸 수 있어요.", code="wrong_file_kind")
        prev = item_image(item)
        if prev is not None:
            old.append(Stored(key=prev.storage_key, url=prev.url))
            db.delete(prev)
        img.item_id = item.id
    db.commit()
    storage = request.app.state.market_storage
    if old and storage is not None:
        storage.delete(old)
    db.refresh(item)
    return _item_out(db, svc, item, user)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="작품 지우기 (올린 사람·관리자)")
def delete_item(item_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = _get_item(db, item_id)
    if not (user.id == item.owner_id or user.is_admin):
        raise ForbiddenError("내가 올린 작품만 지울 수 있어요.")
    stored = [s for f in item.files for s in stored_blobs(f)]
    for f in list(item.files):
        db.delete(f)
    _unshare_layout_files(db, item)
    db.execute(delete(MarketEvent).where(MarketEvent.item_id == item.id))
    db.delete(item)  # 커뮤니티 소개 글은 남긴다 (댓글이 있을 수 있다). 글의 작품 카드는 사라진다
    db.commit()
    storage = request.app.state.market_storage
    if storage is not None:
        storage.delete(stored)
    return Response(status_code=204)


@router.post("/items/{item_id}/copy-layout", status_code=status.HTTP_201_CREATED,
             summary="배치 예시를 내 가상 케이지 배치안으로 담기")
def copy_layout(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    item = _get_item(db, item_id)
    if not item.layout:
        raise AppError("이 작품에는 가상 케이지 배치가 없어요.", code="no_layout")
    ensure_layout_capacity(db, user)
    copy = _layout_from_snapshot(item.layout, user)
    db.add(copy)
    db.commit()
    _record(db, user, item, "copy")
    return {"layout_id": copy.id}


# ── 내려받기 ──

def _visible_file(db: Session, file_id: str, user: User | None) -> MarketFile:
    f = db.get(MarketFile, file_id) if ID_RE.fullmatch(file_id) else None
    # 작품에 붙었거나 공유한 배치에 들어 있는 파일은 누구나, 그 밖에는 올린 사람만
    if f is None or (f.item_id is None and not f.shared and (user is None or user.id != f.owner_id)):
        raise NotFoundError("파일을 찾을 수 없어요.")
    return f


def _serve(request: Request, f: MarketFile, attachment: bool):
    if f.url:
        # Blob 공개 주소. ?download=1 이면 Blob 이 내려받기(attachment)로 보낸다
        return RedirectResponse(f.url + ("?download=1" if attachment else ""), status_code=302)
    storage = request.app.state.market_storage
    if not isinstance(storage, LocalStorage):
        raise NotFoundError("파일을 찾을 수 없어요.")
    path = storage.path(f.storage_key)
    if not path.exists():
        raise NotFoundError("파일을 찾을 수 없어요.")
    headers = {"Content-Disposition": f"{'attachment' if attachment else 'inline'}; filename*=UTF-8''{quote(f.filename)}"}
    return FileResponse(path, media_type=CONTENT_TYPES.get(f.format, "application/octet-stream"), headers=headers)


@router.get("/files/{file_id}/download", summary="파일 내려받기 (작품에 붙은 파일은 누구나)")
def download_file(file_id: str, request: Request, db: Session = Depends(get_db),
                  user: User | None = Depends(get_optional_user)):
    f = _visible_file(db, file_id, user)
    item = db.get(MarketItem, f.item_id) if f.item_id and f.kind == "model" else None
    if item is not None and _counts_as_download(request, db, user, item):
        db.execute(update(MarketItem).where(MarketItem.id == item.id)
                   .values(download_count=MarketItem.download_count + 1))
        db.commit()
    return _serve(request, f, attachment=True)


def _counts_as_download(request: Request, db: Session, user: User | None, item: MarketItem) -> bool:
    """올린 사람이 아니고, 같은 사람(회원은 24시간, 로그인 안 했으면 같은 IP 1시간)이 처음 받을 때만 센다"""
    if user is not None:
        return _record(db, user, item, "download")
    ip = client_key(request.app.state.settings, request, v6_prefix=ACCOUNT_V6_PREFIX)
    return request.app.state.download_counter.hit(f"{ip}|{item.id}")


@router.get("/files/mine", response_model=list[MarketFileOut], summary="내가 올린 3D 파일 (가상 케이지에 놓기)")
def my_files(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(MarketFile).where(MarketFile.owner_id == user.id, MarketFile.kind == "model")
                      .order_by(MarketFile.created_at.desc()).limit(100)).all()
    return [file_out(f) for f in rows]


@router.get("/files/{file_id}", response_model=MarketFileOut, summary="파일 정보 (볼 수 있는 파일만)")
def file_info(file_id: str, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    return file_out(_visible_file(db, file_id, user))


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="올린 파일 지우기 (작품에 붙지 않은 내 파일만)")
def delete_file(file_id: str, request: Request, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    f = get_or_404(db, MarketFile, file_id, "파일을 찾을 수 없어요.", owner_id=user.id)
    if f.item_id is not None or f.shared:
        raise ConflictError("탐색에 올린 작품이나 공유한 배치에 들어 있는 파일이에요. 그 작품을 먼저 지워 주세요.",
                            code="file_in_use")
    stored = stored_blobs(f)
    db.delete(f)
    db.commit()
    storage = request.app.state.market_storage
    if storage is not None:
        storage.delete(stored)
    return Response(status_code=204)


@router.post("/files/previews/backfill", summary="3D 미리보기 메시가 없는 예전 파일에 만들어 넣기 (관리자)")
def backfill_previews(request: Request, limit: int = Query(default=1, ge=1, le=3), db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> dict:
    if not user.is_admin:
        raise ForbiddenError("관리자만 쓸 수 있어요.")
    storage = _storage(request)
    rows = db.scalars(select(MarketFile).where(MarketFile.format.in_(MESH_FORMATS), MarketFile.preview_size.is_(None))
                      .order_by(MarketFile.created_at).limit(limit)).all()
    done = failed = 0
    for f in rows:
        # 먼저 '시도함'(0)으로 적어 둔다: 이 파일 때문에 요청이 죽어도 다음 백필이 같은 파일에서 막히지 않게
        f.preview_size = 0
        db.commit()
        data = _read_original(storage, f)
        blob = build_preview(f.format, data) if data is not None else None
        if _store_preview(storage, f, blob):
            done += 1
        else:
            failed += 1  # 0 으로 남는다 (화면은 원본을 쓴다)
        db.commit()
    remaining = db.scalar(select(func.count(MarketFile.id)).where(MarketFile.format.in_(MESH_FORMATS),
                                                                  MarketFile.preview_size.is_(None))) or 0
    return {"done": done, "failed": failed, "remaining": remaining}


def _read_original(storage: Storage, f: MarketFile) -> bytes | None:
    try:
        if f.url:
            import httpx

            if not f.url.startswith("https://") or ".blob.vercel-storage.com/" not in f.url:
                return None  # 우리 Blob 저장소의 주소만 받는다
            r = httpx.get(f.url, timeout=httpx.Timeout(60, connect=10), follow_redirects=False)
            r.raise_for_status()
            return r.content
        if isinstance(storage, LocalStorage):
            return storage.path(f.storage_key).read_bytes()
    except Exception:  # noqa: BLE001 - 못 읽으면 건너뛴다
        log.warning("원본 파일을 읽지 못했습니다 (%s)", f.id, exc_info=True)
    return None


@router.get("/files/{file_id}/mesh", summary="3D 로 불러올 파일 (가상 케이지, 내려받기 횟수에 넣지 않음)")
def mesh_file(file_id: str, request: Request, db: Session = Depends(get_db),
              user: User | None = Depends(get_optional_user)):
    f = _visible_file(db, file_id, user)
    if f.format not in MESH_FORMATS:
        raise NotFoundError("파일을 찾을 수 없어요.")
    return _serve(request, f, attachment=False)


@router.get("/files/{file_id}/preview", summary="3D 미리보기 메시 (NFM1, 로컬 저장소일 때)")
def preview_file(file_id: str, request: Request, db: Session = Depends(get_db),
                 user: User | None = Depends(get_optional_user)):
    f = _visible_file(db, file_id, user)
    storage = request.app.state.market_storage
    if not f.preview_size:
        raise NotFoundError("미리보기가 없어요.")
    if f.preview_url:
        return RedirectResponse(f.preview_url, status_code=302)
    if not isinstance(storage, LocalStorage):
        raise NotFoundError("미리보기가 없어요.")
    path = storage.path(preview_key(f.id))
    if not path.exists():
        raise NotFoundError("미리보기가 없어요.")
    return FileResponse(path, media_type=PREVIEW_CONTENT_TYPE)


@router.get("/files/{file_id}/view", summary="미리보기 이미지 (로컬 저장소일 때)")
def view_file(file_id: str, request: Request, db: Session = Depends(get_db),
              user: User | None = Depends(get_optional_user)):
    f = _visible_file(db, file_id, user)
    if f.kind != "image":
        raise NotFoundError("파일을 찾을 수 없어요.")
    return _serve(request, f, attachment=False)

