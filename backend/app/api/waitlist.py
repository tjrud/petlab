"""제작·배송 신청 (MVP: 이메일만 수집하는 대기 등록)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_service
from app.auth import get_current_user
from app.models import User, WaitlistEntry
from app.schemas import WaitlistIn, WaitlistOut
from app.services.design_service import DesignService

router = APIRouter(prefix="/waitlist", tags=["제작·배송 대기"])


@router.post("", response_model=WaitlistOut, status_code=status.HTTP_201_CREATED, summary="제작·배송 대기 등록")
def join_waitlist(data: WaitlistIn, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                  user: User = Depends(get_current_user)):
    if data.design_id:
        design = svc.get_visible_design(db, data.design_id, user)
        if data.version is not None:
            svc.get_version(db, design, data.version)
    db.add(WaitlistEntry(email=str(data.email), design_id=data.design_id, version=data.version))
    db.commit()
    return WaitlistOut(
        ok=True,
        message_ko="제작·배송 서비스 대기 명단에 등록했어요. 서비스가 열리면 이메일로 가장 먼저 알려드릴게요.",
    )
