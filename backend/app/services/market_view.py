"""탐색 작품·파일을 화면용 모양으로 바꾸는 함수 (탐색 API 와 커뮤니티 글의 작품 카드가 함께 쓴다)."""

from __future__ import annotations

from app.market_formats import MESH_FORMATS
from app.mesh_preview import preview_key
from app.models import MarketFile, MarketItem
from app.schemas import MarketFileOut
from app.storage import Stored


def stored_blobs(f: MarketFile) -> list[Stored]:
    """파일을 지울 때 저장소에서 함께 지울 것 (원본과 3D 미리보기 메시)"""
    out = [Stored(key=f.storage_key, url=f.url)]
    if f.preview_size:
        out.append(Stored(key=preview_key(f.id), url=f.preview_url))
    return out


def file_out(f: MarketFile) -> MarketFileOut:
    download = f"/market/files/{f.id}/download"
    view = (f.url or f"/market/files/{f.id}/view") if f.kind == "image" else None
    # 3D 로 불러올 주소: Blob 공개 주소(쿠키 없이 받는다) 또는 API 경로(로컬 저장소)
    mesh = (f.url or f"/market/files/{f.id}/mesh") if f.format in MESH_FORMATS else None
    preview = (f.preview_url or f"/market/files/{f.id}/preview") if mesh and f.preview_size else None
    return MarketFileOut(id=f.id, kind=f.kind, filename=f.filename, format=f.format, size=f.size,
                         sha256=f.sha256, download_url=download, view_url=view, dims_mm=f.dims_mm,
                         mesh_url=mesh, preview_url=preview, preview_size=f.preview_size if preview else None,
                         attached=f.item_id is not None or bool(f.shared))


def item_models(item: MarketItem) -> list[MarketFile]:
    return [f for f in item.files if f.kind == "model"]


def item_image(item: MarketItem) -> MarketFile | None:
    return next((f for f in item.files if f.kind == "image"), None)


def item_formats(item: MarketItem) -> list[str]:
    fmts = sorted({f.format for f in item_models(item)})
    return fmts + (["nestforge"] if item.design_id else []) + (["layout"] if item.layout else [])
