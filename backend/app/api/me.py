"""내 정보: 프로필(닉네임·비밀번호·이메일)과 반려동물 정보."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar

from fastapi import Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import (
    auth_status,
    is_reserved_nickname,
    limited_attempt,
    nickname_taken,
    set_session_cookie,
    user_out,
)
from app.api.deps import get_db, get_service, make_router
from app.auth import get_current_user, usage_ip_key
from app.config import Settings
from app.errors import AppError, ConflictError, ForbiddenError, QuotaExceededError
from app.mailer import Mailer
from app.models import CageLayout, Design, Habitat, Pet, Post, User
from app.names import email_key, nickname_key
from app.passwords import hash_password, verify_password
from app.schemas import ID_RE, CageIn, EmailChangeIn, MeOut, PasswordChangeIn, PetIn, PetOut, ProfileUpdateIn
from app.services import email_verify, usage
from app.services.design_service import DesignService, NotFoundError

router = make_router(prefix="/me", tags=["내 정보"])

T = TypeVar("T")

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


async def _check_current_password(request: Request, user: User, fn: Callable[..., T | None], *args: Any) -> T:
    """현재 비밀번호를 확인하는 작업 fn(*args) 를 시도 제한 안에서 실행한다 (비밀번호 변경·이메일 변경).
    fn 이 None 을 돌려주면(현재 비밀번호가 틀림) 400 invalid_credentials, 막혔으면 429 too_many_attempts."""
    # 로그인 세션을 손에 넣은 사람이 현재 비밀번호를 마구 맞혀 보지 못하게 회원별로 제한한다
    result = await limited_attempt(request.app.state.password_limiter, f"user:{user.id}",
                                   "비밀번호 확인 시도가 너무 많아요. 15분 뒤에 다시 시도해 주세요.", fn, *args)
    if result is None:
        raise AppError("현재 비밀번호가 올바르지 않아요.", code="invalid_credentials")
    return result


def _change_password(db: Session, user: User, current: str, new: str) -> Literal[True] | None:
    """현재 비밀번호를 확인하고 바꾼다 (스레드 풀에서 실행). 현재 비밀번호가 틀리면 None, 바꾸면 True."""
    try:
        if not verify_password(current, user.password_hash):
            return None
        user.password_hash = hash_password(new)
        user.session_version += 1
        db.commit()
        return True
    except BaseException:
        db.rollback()
        raise


EMAIL_CHANGES_PER_DAY = 5  # 이메일 변경 시도 (이미 인증된 주소인지 마구 캐 보지 못하게: 결과와 관계없이 센다)


def _change_email(db: Session, settings: Settings, mailer: Mailer | None, user: User, current: str, new_email: str,
                  ip_key: str | None) -> dict | None:
    """현재 비밀번호를 확인하고 이메일을 바꾼다 (스레드 풀에서 실행). 비밀번호가 틀리면 None, 맞으면 응답 본문.
    응답도 여기서 만든다: 상한 오류 뒤 롤백으로 만료된 회원 정보를 이벤트 루프에서 다시 읽지(DB 조회) 않게."""
    try:
        if not verify_password(current, user.password_hash):
            return None
        key = email_key(new_email)
        if user.email_key == key and user.email == new_email and user.email_verified_at is not None:
            db.commit()
            return auth_status(settings, user)  # 그대로
        usage.reserve(db, "email_change", user, per_user=usage.Cap(
            EMAIL_CHANGES_PER_DAY, "이메일은 24시간에 5번까지 바꿀 수 있어요. 잠시 뒤 다시 시도해 주세요.", "too_many_attempts"))
        if email_verify.verified_email_taken(db, key, exclude_user_id=user.id):
            raise ConflictError("이미 다른 계정에서 인증한 이메일이에요.", code="email_taken")
        email_verify.set_email(db, user, new_email, key)  # 인증 표시를 지우고 예전 주소로 보낸 링크도 무효로
        db.commit()
    except BaseException:
        db.rollback()
        raise
    sent = None
    if settings.email_mode == "enabled":
        try:
            sent = email_verify.send_verification(db, settings, mailer, user, ip_key=ip_key)
        except QuotaExceededError:
            sent = False  # 주소는 바뀌었고, 나중에 다시 보낼 수 있다
    db.refresh(user)
    db.commit()
    return auth_status(settings, user, verification_email_sent=sent)


@router.patch("/email", summary="이메일 변경 (새 주소로 인증 메일을 보낸다)")
async def change_email(data: EmailChangeIn, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)) -> Response:
    settings = request.app.state.settings
    if user.is_admin:
        raise ForbiddenError("관리자 계정은 이메일을 등록하지 않아요.")
    # 비밀번호 변경과 같은 제한 (세션을 훔친 사람이 비밀번호를 맞혀 보지 못하게)
    payload = await _check_current_password(request, user, _change_email, db, settings, request.app.state.mailer, user,
                                            data.current_password, str(data.email), usage_ip_key(settings, request))
    return JSONResponse(payload)


@router.post("/password", summary="비밀번호 변경 (다른 기기의 로그인은 풀림)")
async def change_password(data: PasswordChangeIn, request: Request, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)) -> Response:
    settings = request.app.state.settings
    if user.is_admin:
        raise ForbiddenError("관리자 비밀번호는 서버 환경변수(ADMIN_PASSWORD)로만 바꿀 수 있어요.")
    if data.new_password.lower() == user.username:
        raise ConflictError("비밀번호를 아이디와 다르게 정해 주세요.", code="weak_password")
    await _check_current_password(request, user, _change_password, db, user, data.current_password, data.new_password)
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
    pet = db.get(Pet, pet_id) if ID_RE.fullmatch(pet_id) else None
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
    # 이 반려동물로 만든 사육 환경·설계·배치안은 그대로 두고 연결만 끊는다
    for h in db.scalars(select(Habitat).where(Habitat.pet_id == pet.id)):
        h.pet_id = None
    for lay in db.scalars(select(CageLayout).where(CageLayout.pet_id == pet.id)):
        lay.pet_id = None
    db.delete(pet)
    db.commit()
    return Response(status_code=204)
