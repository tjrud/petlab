from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_service
from app.schemas import HabitatIn, HabitatOut
from app.services.design_service import DesignService

router = APIRouter(prefix="/habitats", tags=["사육 환경"])


@router.post("", response_model=HabitatOut, status_code=status.HTTP_201_CREATED, summary="사육 환경 등록")
def create_habitat(data: HabitatIn, db: Session = Depends(get_db), svc: DesignService = Depends(get_service)):
    return svc.habitat_out(svc.create_habitat(db, data))


@router.get("/{habitat_id}", response_model=HabitatOut, summary="사육 환경 조회")
def get_habitat(habitat_id: str, db: Session = Depends(get_db), svc: DesignService = Depends(get_service)):
    return svc.habitat_out(svc.get_habitat(db, habitat_id))
