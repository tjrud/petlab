"""가상 케이지 배치안: 케이지 치수를 정하고 기본 에셋을 놓아 본 결과를 회원 계정에 저장한다.

배치 검토(겹침·벽 밖·끼임 틈·출입구 막힘)는 화면에서 바로 계산해 보여 준다. 서버는 저장만 하므로
검토에서 문제가 있는 배치도 그대로 저장할 수 있다 (고치는 중인 배치를 잃지 않게).
"""

from __future__ import annotations

from fastapi import Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_service, make_router
from app.auth import get_current_user
from app.errors import ConflictError
from app.models import CageLayout, Pet, User
from app.schemas import ID_RE, CageIn, CageLayoutIn, CageLayoutOut, CageLayoutSummary, LayoutItemIn
from app.services.design_service import DesignService, NotFoundError

router = make_router(prefix="/layouts", tags=["가상 케이지"])

MAX_LAYOUTS = 30


def _summary_fields(svc: DesignService, lay: CageLayout) -> dict:
    sp = svc.rules.species_file.species.get(lay.species)
    size = sp.sizes.get(lay.size) if sp else None
    return dict(
        id=lay.id, name=lay.name, species=lay.species, size=lay.size,
        size_name_ko=size.display_name if size else lay.size, pet_id=lay.pet_id,
        cage=CageIn(width_mm=lay.cage_width_mm, depth_mm=lay.cage_depth_mm, height_mm=lay.cage_height_mm),
        item_count=len(lay.items or []), created_at=lay.created_at, updated_at=lay.updated_at,
    )


def layout_out(svc: DesignService, lay: CageLayout) -> CageLayoutOut:
    return CageLayoutOut(**_summary_fields(svc, lay), items=[LayoutItemIn(**i) for i in lay.items or []])


def _my_layout(db: Session, layout_id: str, user: User) -> CageLayout:
    lay = db.get(CageLayout, layout_id) if ID_RE.fullmatch(layout_id) else None
    if lay is None or lay.owner_id != user.id:
        raise NotFoundError("배치안을 찾을 수 없습니다.")
    return lay


def _apply(db: Session, svc: DesignService, lay: CageLayout, data: CageLayoutIn, user: User) -> None:
    svc.check_species(data.species, data.size)
    if data.pet_id is not None:
        pet = db.get(Pet, data.pet_id)
        if pet is None or pet.owner_id != user.id:
            # 배치안이 없는 404 와 구분해서, 화면이 반려동물 연결만 빼고 다시 저장할 수 있게 한다
            raise NotFoundError("반려동물 정보를 찾을 수 없습니다.", code="pet_not_found")
    lay.name, lay.species, lay.size, lay.pet_id = data.name, data.species, data.size, data.pet_id
    c = data.cage
    lay.cage_width_mm, lay.cage_depth_mm, lay.cage_height_mm = c.width_mm, c.depth_mm, c.height_mm
    lay.items = [i.model_dump() for i in data.items]


@router.get("", response_model=list[CageLayoutSummary], summary="내 배치안 목록 (최근 수정 순)")
def list_layouts(db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                 user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(CageLayout).where(CageLayout.owner_id == user.id)
        .order_by(CageLayout.updated_at.desc(), CageLayout.id)
    ).all()
    return [CageLayoutSummary(**_summary_fields(svc, lay)) for lay in rows]


@router.post("", response_model=CageLayoutOut, status_code=status.HTTP_201_CREATED, summary="배치안 저장")
def create_layout(data: CageLayoutIn, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                  user: User = Depends(get_current_user)):
    if (db.scalar(select(func.count(CageLayout.id)).where(CageLayout.owner_id == user.id)) or 0) >= MAX_LAYOUTS:
        raise ConflictError(f"배치안은 {MAX_LAYOUTS}개까지 저장할 수 있어요. 안 쓰는 배치안을 지워 주세요.",
                            code="too_many_layouts")
    lay = CageLayout(owner_id=user.id)
    _apply(db, svc, lay, data, user)
    db.add(lay)
    db.commit()
    return layout_out(svc, lay)


@router.get("/{layout_id}", response_model=CageLayoutOut, summary="배치안 불러오기")
def get_layout(layout_id: str, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
               user: User = Depends(get_current_user)):
    return layout_out(svc, _my_layout(db, layout_id, user))


@router.put("/{layout_id}", response_model=CageLayoutOut, summary="배치안 덮어쓰기")
def update_layout(layout_id: str, data: CageLayoutIn, db: Session = Depends(get_db),
                  svc: DesignService = Depends(get_service), user: User = Depends(get_current_user)):
    lay = _my_layout(db, layout_id, user)
    _apply(db, svc, lay, data, user)
    db.commit()
    return layout_out(svc, lay)


@router.delete("/{layout_id}", status_code=status.HTTP_204_NO_CONTENT, summary="배치안 삭제")
def delete_layout(layout_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.delete(_my_layout(db, layout_id, user))
    db.commit()
    return Response(status_code=204)
