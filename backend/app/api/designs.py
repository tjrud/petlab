from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import Depends, Path, Query, Request, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_service, make_router
from app.auth import (
    ACCOUNT_V6_PREFIX,
    client_key,
    get_current_user,
    get_optional_user,
    get_verified_user,
    usage_ip_key,
)
from app.errors import QuotaExceededError
from app.models import User
from app.schemas import DesignCreateIn, DesignListOut, DesignOut, DesignReviseIn
from app.services.design_service import DesignService

router = make_router(prefix="/designs", tags=["설계"])

def _ip_key(request: Request) -> str | None:
    return usage_ip_key(request.app.state.settings, request)


@router.get("", response_model=DesignListOut, summary="내 설계 내역 (최근 수정순)")
def list_designs(page: int = Query(default=1, ge=1, le=10_000), page_size: int = Query(default=12, ge=1, le=50),
                 db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                 user: User = Depends(get_current_user)):
    return svc.list_designs(db, user, page, page_size)


@router.post("", response_model=DesignOut, status_code=status.HTTP_201_CREATED, summary="프롬프트로 설계 생성")
def create_design(data: DesignCreateIn, request: Request, db: Session = Depends(get_db),
                  svc: DesignService = Depends(get_service), user: User = Depends(get_verified_user)):
    design, version = svc.create_design(db, data.habitat_id, data.prompt, user, ip_key=_ip_key(request))
    return svc.design_out(db, design, version, user)


@router.post("/{design_id}/revise", response_model=DesignOut, status_code=status.HTTP_201_CREATED,
             summary="추가 프롬프트로 설계 수정 (새 버전 생성, 이전 버전 유지)")
def revise_design(design_id: str, data: DesignReviseIn, request: Request, db: Session = Depends(get_db),
                  svc: DesignService = Depends(get_service), user: User = Depends(get_verified_user)):
    design, version = svc.revise_design(db, design_id, data.prompt, user, data.base_version,
                                        ip_key=_ip_key(request))
    return svc.design_out(db, design, version, user)


@router.delete("/{design_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="설계 삭제 (모든 버전, 소유자만). 첨부된 커뮤니티 글·탐색 작품에서는 연결만 끊는다")
def delete_design(design_id: str, request: Request, db: Session = Depends(get_db),
                  svc: DesignService = Depends(get_service), user: User = Depends(get_current_user)):
    stored = svc.delete_design(db, design_id, user)
    storage = request.app.state.market_storage
    if stored and storage is not None:
        storage.delete(stored)  # 설계와 함께 지운 빈 탐색 작품의 대표 이미지
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# 아래 조회 API 는 커뮤니티 글에 첨부된 버전이라면 로그인 없이도 볼 수 있다 (그 밖에는 소유자·관리자만, 아니면 404)
@router.get("/{design_id}", response_model=DesignOut, summary="설계 조회 (버전 지정 가능)")
def get_design(design_id: str, version: int | None = Query(default=None, ge=1, le=2**31 - 1),
               db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
               user: User | None = Depends(get_optional_user)):
    design, allowed = svc.get_visible(db, design_id, user)
    return svc.design_out(db, design, svc.get_version(db, design, version, allowed), user)


@router.get("/{design_id}/versions/{version}/parts/{index}.stl", summary="뷰어용 구조물 메시 (케이지 좌표계)",
            response_class=FileResponse)
def part_mesh(design_id: str, version: int = Path(ge=1, le=2**31 - 1), index: int = Path(ge=0, le=1000), *,
              db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
              user: User | None = Depends(get_optional_user)):
    path = svc.part_mesh_path(db, design_id, version, index, user)
    return FileResponse(path, media_type="model/stl", headers={"Cache-Control": "private, max-age=86400", "Vary": "Cookie"})


@router.get("/{design_id}/export", summary="3D 프린팅 파일 내려받기 (STL / 3MF)")
def export_design(design_id: str, request: Request, format: Literal["stl", "3mf"] = Query(default="stl"),
                  version: int | None = Query(default=None, ge=1, le=2**31 - 1),
                  db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                  user: User | None = Depends(get_optional_user)):
    # 파일을 만들 때마다 메시를 다시 읽고 합치므로(무거움) IP 별 횟수를 묶는다
    key = client_key(request.app.state.settings, request, v6_prefix=ACCOUNT_V6_PREFIX)
    if not request.app.state.export_limiter.hit(key):
        raise QuotaExceededError("내려받기가 너무 잦아요. 잠시 후 다시 시도해 주세요.", code="too_many_exports")
    f = svc.export(db, design_id, version, format, user)
    return Response(
        content=f.content, media_type=f.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f.filename)}"},
    )
