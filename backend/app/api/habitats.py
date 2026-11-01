from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_service
from app.auth import get_current_user
from app.models import User
from app.schemas import HabitatIn, HabitatOut
from app.services.design_service import DesignService

router = APIRouter(prefix="/habitats", tags=["사육 환경"])


@router.post("", response_model=HabitatOut, status_code=status.HTTP_201_CREATED, summary="사육 환경 등록")
def create_habitat(data: HabitatIn, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                   user: User = Depends(get_current_user)):
    return svc.habitat_out(svc.create_habitat(db, data, user))


@router.get("/{habitat_id}", response_model=HabitatOut, summary="사육 환경 조회 (내 것만)")
def get_habitat(habitat_id: str, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                user: User = Depends(get_current_user)):
    return svc.habitat_out(svc.get_habitat(db, habitat_id, user))
