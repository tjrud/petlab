"""제작·배송 신청 (MVP: 이메일만 수집하는 대기 등록)."""

from __future__ import annotations

from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_service, make_router
from app.auth import get_verified_user
from app.models import User, WaitlistEntry
from app.schemas import WaitlistIn, WaitlistOut
from app.services import usage
from app.services.design_service import DesignService

router = make_router(prefix="/waitlist", tags=["제작·배송 대기"])

WAITLIST_DAILY_LIMIT = 10  # 회원 1명당 24시간 (남의 이메일을 대량으로 올리지 못하게)
DONE_MESSAGE = "제작·배송 서비스 대기 명단에 등록했어요. 서비스가 열리면 이메일로 가장 먼저 알려드릴게요."


@router.post("", response_model=WaitlistOut, status_code=status.HTTP_201_CREATED, summary="제작·배송 대기 등록")
def join_waitlist(data: WaitlistIn, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
                  user: User = Depends(get_verified_user)):
    if data.design_id:
        design, allowed = svc.get_visible(db, data.design_id, user)
        if data.version is not None:
            svc.get_version(db, design, data.version, allowed)
    # 신청은 이미 있든 없든 횟수를 센다 (응답으로 남의 이메일이 명단에 있는지 알아낼 수 없게)
    usage.reserve_per_member(db, "waitlist", user, WAITLIST_DAILY_LIMIT,
                             "대기 신청이 너무 많아요. 잠시 뒤 다시 시도해 주세요.", "too_many_waitlist")
    email = str(data.email)
    exists = db.scalar(select(WaitlistEntry.id).where(
        WaitlistEntry.email == email,
        WaitlistEntry.design_id.is_(None) if data.design_id is None else WaitlistEntry.design_id == data.design_id,
    ).limit(1))
    if exists is None:  # 같은 이메일·설계로 이미 신청했으면 다시 넣지 않는다
        db.add(WaitlistEntry(email=email, design_id=data.design_id, version=data.version))
        db.commit()
    return WaitlistOut(ok=True, message_ko=DONE_MESSAGE)
