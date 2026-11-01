from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_service
from app.schemas import DesignCreateIn, DesignOut, DesignReviseIn
from app.services.design_service import DesignService

router = APIRouter(prefix="/designs", tags=["설계"])


@router.post("", response_model=DesignOut, status_code=status.HTTP_201_CREATED, summary="프롬프트로 설계 생성")
def create_design(data: DesignCreateIn, db: Session = Depends(get_db), svc: DesignService = Depends(get_service)):
    design, version = svc.create_design(db, data.habitat_id, data.prompt)
    return svc.design_out(design, version)


@router.post("/{design_id}/revise", response_model=DesignOut, status_code=status.HTTP_201_CREATED,
             summary="추가 프롬프트로 설계 수정 (새 버전 생성, 이전 버전 유지)")
def revise_design(design_id: str, data: DesignReviseIn, db: Session = Depends(get_db),
                  svc: DesignService = Depends(get_service)):
    design, version = svc.revise_design(db, design_id, data.prompt, data.base_version)
    return svc.design_out(design, version)


@router.get("/{design_id}", response_model=DesignOut, summary="설계 조회 (버전 지정 가능)")
def get_design(design_id: str, version: int | None = Query(default=None, ge=1, le=2**31 - 1),
               db: Session = Depends(get_db), svc: DesignService = Depends(get_service)):
    design = svc.get_design(db, design_id)
    # 메시 캐시가 없으면(새 인스턴스·재배포) 여기서 다시 만들고, 형상이 검증 당시와 다르면 다시 검증한 결과를 돌려준다
    return svc.design_out(design, svc.get_version(db, design, version), verify=True)


@router.get("/{design_id}/versions/{version}/parts/{index}.stl", summary="뷰어용 구조물 메시 (케이지 좌표계)",
            response_class=FileResponse)
def part_mesh(design_id: str, version: int = Path(ge=1, le=2**31 - 1), index: int = Path(ge=0, le=1000), *,
              g: str | None = Query(default=None, max_length=64, description="형상 키 (응답의 mesh_url 에 포함됨)"),
              db: Session = Depends(get_db), svc: DesignService = Depends(get_service)):
    path, key = svc.part_mesh(db, design_id, version, index)
    # URL 의 형상 키가 지금 형상과 같을 때만 오래 캐시한다. 형상이 바뀌면 mesh_url 의 키도 바뀌어 캐시가 섞이지 않는다.
    cache = "public, max-age=86400" if g == key else "no-cache"
    return FileResponse(path, media_type="model/stl", headers={"Cache-Control": cache})


@router.get("/{design_id}/export", summary="3D 프린팅 파일 내려받기 (STL / 3MF)")
def export_design(design_id: str, format: Literal["stl", "3mf"] = Query(default="stl"),
                  version: int | None = Query(default=None, ge=1, le=2**31 - 1),
                  db: Session = Depends(get_db), svc: DesignService = Depends(get_service)):
    f = svc.export(db, design_id, version, format)
    return Response(
        content=f.content, media_type=f.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f.filename)}"},
    )
