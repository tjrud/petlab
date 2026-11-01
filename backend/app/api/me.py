"""내 정보: 프로필(닉네임·비밀번호)과 반려동물 정보."""

from __future__ import annotations

import asyncio

from fastapi import Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import (
    FAILED_LOGIN_DELAY_S,
    auth_status,
    is_reserved_nickname,
    nickname_taken,
    set_session_cookie,
    user_out,
)
from app.api.deps import get_db, get_service, make_router
from app.auth import get_current_user
from app.errors import AppError, ConflictError, ForbiddenError, QuotaExceededError
from app.models import Design, Habitat, Pet, Post, User
from app.names import nickname_key
from app.passwords import hash_password, verify_password
from app.schemas import CageIn, MeOut, PasswordChangeIn, PetIn, PetOut, ProfileUpdateIn
from app.services.design_service import _ID_RE, DesignService, NotFoundError

router = make_router(prefix="/me", tags=["내 정보"])

MAX_PETS = 20


@router.get("", response_model=MeOut, summary="내 정보 (프로필·통계·설계 사용량)")
def get_me(db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
           user: User = Depends(get_current_user)):
    count = lambda model, col: db.scalar(select(func.count()).select_from(model).where(col == user.id)) or 0
    return MeOut(
        user=user_out(user),
        stats={"pets": count(Pet, Pet.owner_id), "designs": count(Design, Design.owner_id),
               "posts": count(Post, Post.author_id)},
        design_quota=svc.quota(db, user),
    )


@router.patch("", summary="닉네임 변경")
def update_profile(data: ProfileUpdateIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    settings = request.app.state.settings
    if user.is_admin:
        raise ForbiddenError("관리자 계정의 닉네임은 바꿀 수 없어요.")
    if is_reserved_nickname(data.nickname, settings):
        raise ConflictError("사용할 수 없는 닉네임이에요.", code="nickname_taken")
    if nickname_taken(db, data.nickname, exclude_user_id=user.id):
        raise ConflictError("이미 사용 중인 닉네임이에요.", code="nickname_taken")
    user.nickname, user.nickname_key = data.nickname, nickname_key(data.nickname)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("이미 사용 중인 닉네임이에요.", code="nickname_taken") from None
    return auth_status(settings, user)


def _change_password(db: Session, user: User, current: str, new: str) -> bool:
    """현재 비밀번호를 확인하고 바꾼다 (스레드 풀에서 실행). 현재 비밀번호가 틀리면 False."""
    try:
        if not verify_password(current, user.password_hash):
            return False
        user.password_hash = hash_password(new)
        user.session_version += 1
        db.commit()
        return True
    except BaseException:
        db.rollback()
        raise


@router.post("/password", summary="비밀번호 변경 (다른 기기의 로그인은 풀림)")
async def change_password(data: PasswordChangeIn, request: Request, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)) -> Response:
    settings = request.app.state.settings
    if user.is_admin:
        raise ForbiddenError("관리자 비밀번호는 서버 환경변수(ADMIN_PASSWORD)로만 바꿀 수 있어요.")
    if data.new_password.lower() == user.username:
        raise ConflictError("비밀번호를 아이디와 다르게 정해 주세요.", code="weak_password")
    # 로그인 세션을 손에 넣은 사람이 현재 비밀번호를 마구 맞혀 보지 못하게 회원별로 제한한다
    limiter = request.app.state.password_limiter
    key = f"user:{user.id}"
    if limiter.blocked(key):
        raise QuotaExceededError("비밀번호 확인 시도가 너무 많아요. 15분 뒤에 다시 시도해 주세요.",
                                 code="too_many_attempts")
    if not await run_in_threadpool(_change_password, db, user, data.current_password, data.new_password):
        limiter.record_failure(key)
        await asyncio.sleep(FAILED_LOGIN_DELAY_S)
        raise AppError("현재 비밀번호가 올바르지 않아요.", code="invalid_credentials")
    response = JSONResponse(auth_status(settings, user))
    set_session_cookie(response, settings, request, user)  # 이 기기는 로그인 유지
    return response


# ── 반려동물 ───────────────────────────────────────────────


def pet_out(svc: DesignService, p: Pet) -> PetOut:
    sp = svc.rules.species_file.species.get(p.species)
    size = sp.sizes.get(p.size) if sp else None
    cage = None
    if p.cage_width_mm and p.cage_depth_mm and p.cage_height_mm:
        cage = CageIn(width_mm=p.cage_width_mm, depth_mm=p.cage_depth_mm, height_mm=p.cage_height_mm)
    return PetOut(
        id=p.id, name=p.name, species=p.species, species_name_ko=sp.display_name if sp else p.species,
        size=p.size, size_name_ko=size.display_name if size else p.size, sex=p.sex, birth_date=p.birth_date,
        notes=p.notes or None, cage=cage, created_at=p.created_at, updated_at=p.updated_at,
    )


def _my_pet(db: Session, pet_id: str, user: User) -> Pet:
    pet = db.get(Pet, pet_id) if _ID_RE.fullmatch(pet_id) else None
    if pet is None or pet.owner_id != user.id:
        raise NotFoundError("반려동물 정보를 찾을 수 없습니다.")
    return pet


def _apply(pet: Pet, data: PetIn) -> None:
    pet.name, pet.species, pet.size, pet.sex = data.name, data.species, data.size, data.sex
    pet.birth_date, pet.notes = data.birth_date, data.notes or None
    c = data.cage
    pet.cage_width_mm, pet.cage_depth_mm, pet.cage_height_mm = (
        (c.width_mm, c.depth_mm, c.height_mm) if c else (None, None, None))


@router.get("/pets", response_model=list[PetOut], summary="내 반려동물 목록")
def list_pets(db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
              user: User = Depends(get_current_user)):
    pets = db.scalars(select(Pet).where(Pet.owner_id == user.id).order_by(Pet.created_at, Pet.id)).all()
    return [pet_out(svc, p) for p in pets]


@router.post("/pets", response_model=PetOut, status_code=status.HTTP_201_CREATED, summary="반려동물 등록")
def create_pet(data: PetIn, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
               user: User = Depends(get_current_user)):
    svc.check_species(data.species, data.size)
    if (db.scalar(select(func.count(Pet.id)).where(Pet.owner_id == user.id)) or 0) >= MAX_PETS:
        raise ConflictError(f"반려동물은 {MAX_PETS}마리까지 등록할 수 있어요.", code="too_many_pets")
    pet = Pet(owner_id=user.id)
    _apply(pet, data)
    db.add(pet)
    db.commit()
    return pet_out(svc, pet)


@router.get("/pets/{pet_id}", response_model=PetOut, summary="반려동물 정보")
def get_pet(pet_id: str, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
            user: User = Depends(get_current_user)):
    return pet_out(svc, _my_pet(db, pet_id, user))


@router.put("/pets/{pet_id}", response_model=PetOut, summary="반려동물 정보 수정")
def update_pet(pet_id: str, data: PetIn, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
               user: User = Depends(get_current_user)):
    pet = _my_pet(db, pet_id, user)
    svc.check_species(data.species, data.size)
    _apply(pet, data)
    db.commit()
    return pet_out(svc, pet)


@router.delete("/pets/{pet_id}", status_code=status.HTTP_204_NO_CONTENT, summary="반려동물 정보 삭제")
def delete_pet(pet_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pet = _my_pet(db, pet_id, user)
    # 이 반려동물로 만든 사육 환경·설계는 그대로 두고 연결만 끊는다
    for h in db.scalars(select(Habitat).where(Habitat.pet_id == pet.id)):
        h.pet_id = None
    db.delete(pet)
    db.commit()
    return Response(status_code=204)
