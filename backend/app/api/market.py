"""탐색: 회원이 만든 구조물(완성 파일 SKP·3MF·STL, NestForge 설계)을 공유하는 곳.

파일은 배포 플랫폼의 요청 크기 한도(약 4.5MB) 때문에 3MB 조각으로 받아 DB 에 잠시 모았다가,
다 모이면 내용이 확장자와 맞는지 확인하고 저장소(Vercel Blob / 로컬 디스크)에 한 번에 올린다.
내려받기는 Blob 공개 주소로 넘겨 응답 크기 한도를 피한다.

작품을 올리면 커뮤니티에 소개 글을 함께 올릴 수 있다 (댓글은 그 글에서). NestForge 설계를 붙이면
소개 글에 그 설계 버전을 첨부하므로, 커뮤니티 공유와 같은 규칙으로 누구나 보고 내려받을 수 있다.
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import Depends, Query, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, get_service, make_router
from app.auth import get_current_user, get_optional_user, get_verified_user
from app.errors import AppError, ConflictError, ForbiddenError
from app.market_formats import (
    CONTENT_TYPES,
    IMAGE_FORMATS,
    MAX_IMAGE_BYTES,
    MAX_MODEL_BYTES,
    MODEL_FORMATS,
    content_matches,
    format_of,
)
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
    SharedDesignOut,
    UploadStartIn,
    UploadStartOut,
)
from app.services import recommend, usage
from app.services.design_service import DesignService, NotFoundError
from app.storage import LocalStorage, Storage, StorageError, Stored

router = make_router(prefix="/market", tags=["탐색"])

CHUNK_BYTES = 3 * 1024 * 1024
UPLOAD_TTL = timedelta(hours=6)
MAX_PAGE = 1000


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


def _file_out(f: MarketFile) -> MarketFileOut:
    download = f"/market/files/{f.id}/download"
    view = (f.url or f"/market/files/{f.id}/view") if f.kind == "image" else None
    # 3D 로 불러올 주소: Blob 공개 주소(쿠키 없이 받는다) 또는 API 경로(로컬 저장소)
    mesh = (f.url or f"/market/files/{f.id}/mesh") if f.format in MESH_FORMATS else None
    return MarketFileOut(id=f.id, kind=f.kind, filename=f.filename, format=f.format, size=f.size,
                         sha256=f.sha256, download_url=download, view_url=view, dims_mm=f.dims_mm,
                         mesh_url=mesh, attached=f.item_id is not None or bool(f.shared))


MESH_FORMATS = {"stl", "3mf"}
FILE_ASSET_PREFIX = "file_"  # 가상 케이지 배치안에서 내가 올린 파일을 가리키는 에셋 키: file_<파일 ID>


def mesh_dims(fmt: str, data: bytes) -> list[float] | None:
    """STL·3MF 외곽 크기 [x, y, z] mm (못 읽으면 None)"""
    if fmt not in MESH_FORMATS:
        return None
    try:
        import trimesh

        loaded = trimesh.load(io.BytesIO(data), file_type=fmt, force="mesh")
        ext = [float(round(v, 2)) for v in loaded.extents]
    except Exception:  # noqa: BLE001 - 형식은 이미 확인했고, 크기를 못 읽어도 올리기는 막지 않는다
        return None
    return ext if len(ext) == 3 and all(0 < v < 10_000 for v in ext) else None


def _models(item: MarketItem) -> list[MarketFile]:
    return [f for f in item.files if f.kind == "model"]


def _image(item: MarketItem) -> MarketFile | None:
    return next((f for f in item.files if f.kind == "image"), None)


def _formats(item: MarketItem) -> list[str]:
    fmts = sorted({f.format for f in _models(item)})
    return fmts + (["nestforge"] if item.design_id else []) + (["layout"] if item.layout else [])


def _summary_fields(item: MarketItem) -> dict:
    img = _image(item)
    return dict(
        id=item.id, title=item.title, category=item.category,
        category_name_ko=MARKET_CATEGORIES.get(item.category, item.category), author=_author(item.owner),
        formats=_formats(item), image=_file_out(img) if img else None, has_design=item.design_id is not None,
        has_layout=bool(item.layout),
        download_count=item.download_count, created_at=item.created_at,
    )


def _shared_design(db: Session, svc: DesignService, item: MarketItem) -> SharedDesignOut | None:
    """붙인 설계 (그 버전이 아직 커뮤니티 글로 공개되어 있을 때만)."""
    if not item.design_id or item.design_version is None:
        return None
    if item.design_version not in svc.shared_versions(db, item.design_id):
        return None
    d = svc.get_design(db, item.design_id)
    v = svc.get_version(db, d, item.design_version)
    return SharedDesignOut(
        id=d.id, version=v.version, title=svc.title_of(d), summary_ko=v.llm_spec.get("summary_ko", ""),
        item_labels=[it["label_ko"] for it in v.items], passed=v.passed, habitat=svc.habitat_out(d.habitat),
    )


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
        **_summary_fields(item), description=item.description, files=[_file_out(f) for f in _models(item)],
        design=_shared_design(db, svc, item), layout=_layout_out(svc, item), post_id=post_id,
        updated_at=item.updated_at,
        can_edit=owner, can_delete=owner or (user is not None and user.is_admin),
    )


def _get_item(db: Session, item_id: str) -> MarketItem:
    item = db.get(MarketItem, item_id) if ID_RE.fullmatch(item_id) else None
    if item is None:
        raise NotFoundError("작품을 찾을 수 없어요.")
    return item


def _limits(kind: str) -> tuple[set[str], int]:
    return (MODEL_FORMATS, MAX_MODEL_BYTES) if kind == "model" else (IMAGE_FORMATS, MAX_IMAGE_BYTES)


def _cleanup_stale(db: Session, user: User) -> None:
    """오래된 미완성 업로드를 지운다 (조각이 DB 에 쌓이지 않게)."""
    cutoff = datetime.now(timezone.utc) - UPLOAD_TTL
    stale = db.scalars(select(MarketUpload.id).where(MarketUpload.owner_id == user.id,
                                                     MarketUpload.created_at < cutoff)).all()
    if stale:
        db.execute(delete(MarketUploadChunk).where(MarketUploadChunk.upload_id.in_(stale)))
        db.execute(delete(MarketUpload).where(MarketUpload.id.in_(stale)))


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
    limit = request.app.state.settings.market_upload_daily_limit
    usage.reserve_per_member(db, "market_upload", user, limit, f"파일은 24시간에 {limit}개까지 올릴 수 있어요.",
                             "too_many_uploads")
    _cleanup_stale(db, user)
    up = MarketUpload(owner_id=user.id, kind=data.kind, filename=data.filename, format=fmt, size=data.size)
    db.add(up)
    db.commit()
    return UploadStartOut(id=up.id, chunk_bytes=CHUNK_BYTES, chunks=-(-data.size // CHUNK_BYTES))


def _my_upload(db: Session, upload_id: str, user: User) -> MarketUpload:
    up = db.get(MarketUpload, upload_id) if ID_RE.fullmatch(upload_id) else None
    if up is None or up.owner_id != user.id:
        raise NotFoundError("올리던 파일을 찾을 수 없어요. 처음부터 다시 올려 주세요.")
    return up


@router.put("/uploads/{upload_id}/chunks/{n}", status_code=status.HTTP_204_NO_CONTENT, summary="파일 조각 올리기")
async def put_chunk(upload_id: str, n: int, request: Request, user: User = Depends(get_verified_user)):
    # 조각 크기보다 큰 본문은 읽기 전에 거절한다
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError:
        declared = 0
    if declared > CHUNK_BYTES:
        raise AppError("조각이 너무 커요.", code="bad_chunk")
    body = await request.body()
    if len(body) > CHUNK_BYTES:
        raise AppError("조각이 너무 커요.", code="bad_chunk")
    # 본문을 다 받은 뒤에 짧게 DB 에 쓴다
    factory = request.app.state.session_factory
    with factory() as db:
        up = _my_upload(db, upload_id, user)
        chunks = -(-up.size // CHUNK_BYTES)
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
    chunks = -(-up.size // CHUNK_BYTES)
    have = db.scalar(select(func.count()).select_from(MarketUploadChunk)
                     .where(MarketUploadChunk.upload_id == up.id)) or 0
    if have != chunks:
        raise AppError("아직 다 올라오지 않았어요. 다시 올려 주세요.", code="upload_incomplete")
    data = b"".join(c.data for c in db.scalars(select(MarketUploadChunk)
                                               .where(MarketUploadChunk.upload_id == up.id)
                                               .order_by(MarketUploadChunk.n)))
    if len(data) != up.size:
        raise AppError("파일 크기가 맞지 않아요. 다시 올려 주세요.", code="upload_incomplete")
    if not content_matches(up.format, data):
        db.execute(delete(MarketUploadChunk).where(MarketUploadChunk.upload_id == up.id))
        db.delete(up)
        db.commit()
        raise AppError(f"{up.format.upper()} 파일이 아니거나 손상된 파일이에요.", code="bad_file_content")
    f = MarketFile(owner_id=user.id, kind=up.kind, filename=up.filename, format=up.format, size=up.size,
                   sha256=hashlib.sha256(data).hexdigest(), storage_key="")
    f.id = up.id  # 저장 키와 파일 ID 를 같게 (추측하기 어려운 무작위 값)
    key = f"market/{f.id}/{f.id}.{f.format}"
    try:
        stored = storage.put(key, data, CONTENT_TYPES[up.format])
    except StorageError as e:
        raise StorageUnavailableError("파일을 저장하지 못했어요. 잠시 후 다시 올려 주세요.") from e
    f.storage_key, f.url = stored.key, stored.url
    f.dims_mm = mesh_dims(f.format, data)
    db.execute(delete(MarketUploadChunk).where(MarketUploadChunk.upload_id == up.id))
    db.delete(up)
    db.add(f)
    db.commit()
    return _file_out(f)


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
        lay = db.get(CageLayout, data.layout_id)
        if lay is None or lay.owner_id != user.id:
            raise NotFoundError("배치안을 찾을 수 없어요.")
        snapshot = {"name": lay.name, "species": lay.species, "size": lay.size,
                    "cage": {"width_mm": lay.cage_width_mm, "depth_mm": lay.cage_depth_mm, "height_mm": lay.cage_height_mm},
                    "items": list(lay.items or [])}
        # 배치에 넣은 내 파일은 이 배치를 보는 사람도 3D 로 볼 수 있게 공개한다
        for it in snapshot["items"]:
            key = it.get("asset", "")
            if key.startswith(FILE_ASSET_PREFIX):
                f = db.get(MarketFile, key[len(FILE_ASSET_PREFIX):])
                if f is not None and f.owner_id == user.id:
                    layout_files.append(f)
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


def _record(db: Session, user: User | None, item: MarketItem, kind: str) -> None:
    """맞춤 추천용 기록 (로그인한 회원, 남의 작품만). 같은 작품을 1시간 안에 다시 보면 한 번으로 센다"""
    if user is None or user.id == item.owner_id:
        return
    if kind == "view":
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        if db.scalar(select(MarketEvent.id).where(MarketEvent.user_id == user.id, MarketEvent.item_id == item.id,
                                                  MarketEvent.kind == "view", MarketEvent.created_at >= since).limit(1)):
            return
    db.add(MarketEvent(user_id=user.id, item_id=item.id, kind=kind))
    db.commit()


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
def update_item(item_id: str, data: MarketItemUpdateIn, db: Session = Depends(get_db),
                svc: DesignService = Depends(get_service), user: User = Depends(get_current_user)):
    item = _get_item(db, item_id)
    if item.owner_id != user.id:
        raise ForbiddenError("내가 올린 작품만 고칠 수 있어요.")
    for k in ("title", "description", "category"):
        v = getattr(data, k)
        if v is not None:
            setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return _item_out(db, svc, item, user)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="작품 지우기 (올린 사람·관리자)")
def delete_item(item_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = _get_item(db, item_id)
    if not (user.id == item.owner_id or user.is_admin):
        raise ForbiddenError("내가 올린 작품만 지울 수 있어요.")
    stored = [Stored(key=f.storage_key, url=f.url) for f in item.files]
    for f in list(item.files):
        db.delete(f)
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
    from app.api.layouts import MAX_LAYOUTS

    item = _get_item(db, item_id)
    lay = item.layout
    if not lay:
        raise AppError("이 작품에는 가상 케이지 배치가 없어요.", code="no_layout")
    if (db.scalar(select(func.count(CageLayout.id)).where(CageLayout.owner_id == user.id)) or 0) >= MAX_LAYOUTS:
        raise ConflictError(f"배치안은 {MAX_LAYOUTS}개까지 저장할 수 있어요. 안 쓰는 배치안을 지워 주세요.",
                            code="too_many_layouts")
    cage = lay["cage"]
    copy = CageLayout(owner_id=user.id, name=f"{lay['name']} (탐색)"[:40], species=lay["species"], size=lay["size"],
                      cage_width_mm=cage["width_mm"], cage_depth_mm=cage["depth_mm"], cage_height_mm=cage["height_mm"],
                      items=list(lay["items"]))
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
    if f.item_id and f.kind == "model":
        db.execute(update(MarketItem).where(MarketItem.id == f.item_id)
                   .values(download_count=MarketItem.download_count + 1))
        db.commit()
        item = db.get(MarketItem, f.item_id)
        if item is not None:
            _record(db, user, item, "download")
    return _serve(request, f, attachment=True)


@router.get("/files/mine", response_model=list[MarketFileOut], summary="내가 올린 3D 파일 (가상 케이지에 놓기)")
def my_files(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(MarketFile).where(MarketFile.owner_id == user.id, MarketFile.kind == "model")
                      .order_by(MarketFile.created_at.desc()).limit(100)).all()
    return [_file_out(f) for f in rows]


@router.get("/files/{file_id}", response_model=MarketFileOut, summary="파일 정보 (볼 수 있는 파일만)")
def file_info(file_id: str, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    return _file_out(_visible_file(db, file_id, user))


@router.get("/files/{file_id}/mesh", summary="3D 로 불러올 파일 (가상 케이지, 내려받기 횟수에 넣지 않음)")
def mesh_file(file_id: str, request: Request, db: Session = Depends(get_db),
              user: User | None = Depends(get_optional_user)):
    f = _visible_file(db, file_id, user)
    if f.format not in MESH_FORMATS:
        raise NotFoundError("파일을 찾을 수 없어요.")
    return _serve(request, f, attachment=False)


@router.get("/files/{file_id}/view", summary="미리보기 이미지 (로컬 저장소일 때)")
def view_file(file_id: str, request: Request, db: Session = Depends(get_db),
              user: User | None = Depends(get_optional_user)):
    f = _visible_file(db, file_id, user)
    if f.kind != "image":
        raise NotFoundError("파일을 찾을 수 없어요.")
    return _serve(request, f, attachment=False)

