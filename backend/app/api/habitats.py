from __future__ import annotations

from fastapi import Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_service, make_router
from app.auth import get_current_user
from app.models import User
from app.schemas import HabitatIn, HabitatOut
from app.services import usage
from app.services.design_service import DesignService

router = make_router(prefix="/habitats", tags=["사육 환경"])

HABITAT_DAILY_LIMIT = 100  # 회원 1명당 24시간 (설계마다 하나씩 만들어지므로 설계 상한보다 넉넉하게)


@router.post("", response_model=HabitatOut, status_code=status.HTTP_201_CREATED, summary="사육 환경 등록")
def create_habitat(data: HabitatIn, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                   user: User = Depends(get_current_user)):
    svc.check_habitat(data.species, data.size, data.count)
    usage.reserve_per_member(db, "habitat", user, HABITAT_DAILY_LIMIT,
                             "사육 환경 등록이 너무 많아요. 잠시 뒤 다시 시도해 주세요.", "too_many_habitats")
    return svc.habitat_out(svc.create_habitat(db, data, user))


@router.get("/{habitat_id}", response_model=HabitatOut, summary="사육 환경 조회 (내 것만)")
def get_habitat(habitat_id: str, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                user: User = Depends(get_current_user)):
    return svc.habitat_out(svc.get_habitat(db, habitat_id, user))
