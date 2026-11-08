"""DB 모델: 회원, 반려동물, 사육 환경, 설계, 설계 버전, 커뮤니티, 제작·배송 대기 신청."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uid() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """회원. 관리자는 환경변수(ADMIN_USERNAME/ADMIN_PASSWORD)로 로그인하며 password_hash 가 비어 있다."""

    __tablename__ = "users"
    # 같은 이메일은 한 계정만 인증할 수 있다 (인증 전 주소는 겹칠 수 있다: 남의 주소를 먼저 적어 가입을 막지 못하게).
    # 기존 DB 에는 db.py MIGRATION_INDEXES 가 같은 이름으로 만든다.
    __table_args__ = (
        Index("ix_users_email_key", "email_key"),
        Index("ux_users_email_key_verified", "email_key", unique=True,
              sqlite_where=text("email_verified_at IS NOT NULL"),
              postgresql_where=text("email_verified_at IS NOT NULL")),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    nickname: Mapped[str] = mapped_column(String(40), unique=True)
    # 닉네임 비교용 정규화 키 (대소문자·공백 무시). 보기에 같은 닉네임으로 다른 회원을 사칭하지 못하게 유일하게 둔다
    nickname_key: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # member | admin
    # 비밀번호를 바꾸면 올려서 다른 기기의 세션을 끊는다
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    # 이메일 인증 (아래 세 열은 기존 DB 에 마이그레이션으로 추가된다). email_key 는 비교용 정규화 주소
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_key: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Pet(Base):
    """내 반려동물 정보 (설계할 때 종·크기·케이지 치수를 채우는 데 쓴다)."""

    __tablename__ = "pets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    species: Mapped[str] = mapped_column(String(32))
    size: Mapped[str] = mapped_column(String(32))
    sex: Mapped[str] = mapped_column(String(16), default="unknown")  # male | female | unknown
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cage_width_mm: Mapped[float | None] = mapped_column(nullable=True)
    cage_depth_mm: Mapped[float | None] = mapped_column(nullable=True)
    cage_height_mm: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Habitat(Base):
    __tablename__ = "habitats"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    # 아래 두 열은 기존 DB 에 마이그레이션으로 추가된다 (db.py MIGRATION_COLUMNS). 옛 행은 비어 있다.
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    pet_id: Mapped[str | None] = mapped_column(ForeignKey("pets.id"), nullable=True)
    species: Mapped[str] = mapped_column(String(32))
    size: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(Integer)
    cage_width_mm: Mapped[float]
    cage_depth_mm: Mapped[float]
    cage_height_mm: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Design(Base):
    __tablename__ = "designs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    habitat_id: Mapped[str] = mapped_column(ForeignKey("habitats.id"))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)  # 옛 행은 비어 있음
    title: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    habitat: Mapped[Habitat] = relationship()
    owner: Mapped[User | None] = relationship()
    versions: Mapped[list["DesignVersion"]] = relationship(
        back_populates="design", order_by="DesignVersion.version", cascade="all, delete-orphan"
    )


class DesignVersion(Base):
    """설계 버전. 수정할 때마다 새 버전을 만들고 이전 버전은 그대로 둔다."""

    __tablename__ = "design_versions"
    __table_args__ = (UniqueConstraint("design_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    design_id: Mapped[str] = mapped_column(ForeignKey("designs.id"))
    version: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32))
    llm_attempts: Mapped[int] = mapped_column(Integer, default=1)
    llm_spec: Mapped[dict] = mapped_column(JSON)        # LLM 이 낸 원본 명세
    effective_spec: Mapped[dict] = mapped_column(JSON)  # 자동 보정이 반영된 최종 명세 (다음 수정의 기준)
    items: Mapped[list] = mapped_column(JSON)           # 항목별 최종 파라미터·배치·치수
    report: Mapped[dict] = mapped_column(JSON)          # 검증 보고서
    passed: Mapped[bool]
    # 검증한 형상의 지문: {"fingerprint": 형상 코드·설정 지문, "files": {"print_0.stl": SHA-256, ...}}.
    # 메시 캐시를 다시 만들 때 바이트 단위로 같은지 확인하고, 다르면 내보내기 전에 다시 검증한다.
    # 기존 DB 에는 마이그레이션으로 추가된다 (db.py MIGRATION_COLUMNS). 옛 행은 비어 있어 항상 다시 검증한다.
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)  # 사용량 집계
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    design: Mapped[Design] = relationship(back_populates="versions")


class WaitlistEntry(Base):
    __tablename__ = "waitlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320))
    design_id: Mapped[str | None] = mapped_column(ForeignKey("designs.id"), nullable=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Post(Base):
    """커뮤니티 글. 내 설계를 첨부하면 그 설계는 누구나 볼 수 있게 된다(공유)."""

    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    design_id: Mapped[str | None] = mapped_column(ForeignKey("designs.id"), nullable=True, index=True)
    design_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 운영팀 글의 사진 [{src, alt, width, height, credit, license, source_url}] (기존 DB 에는 마이그레이션으로 추가)
    images: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    author: Mapped[User] = relationship()
    design: Mapped[Design | None] = relationship()
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post", order_by="Comment.created_at", cascade="all, delete-orphan"
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    post: Mapped[Post] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()


class UsageEvent(Base):
    """사용량 기록 (설계 요청·글·댓글·사육 환경·대기 신청). 상한 확인에 쓰며 지우지 않는다.

    결과(설계 버전·글)와 따로 두는 이유: 실패한 설계 요청도 LLM 비용이 들고, 글을 지우고 다시 써서
    상한을 피하지 못하게 하려면 '시도'를 세야 한다. 상한 확인과 기록은 한 트랜잭션에서 잠금을 잡고 한다
    (services/usage.py)."""

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_kind_created", "kind", "created_at"),
        Index("ix_usage_events_user_kind_created", "user_id", "kind", "created_at"),
        Index("ix_usage_events_ip_kind_created", "ip_key", "kind", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(16))  # design | post | comment | habitat | waitlist
    ip_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EmailToken(Base):
    """이메일 인증 링크 토큰. 토큰 자체는 저장하지 않고 SHA-256 해시만 둔다 (DB 가 새어도 링크를 쓸 수 없게).
    한 번 쓰면 used_at 을 채운다. email 은 토큰을 보낸 주소 (그 뒤 주소를 바꿨으면 이 토큰으로 인증되지 않는다)."""

    __tablename__ = "email_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(16), default="verify")
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CageLayout(Base):
    """가상 케이지 배치안. 케이지 치수와 기본 에셋(쳇바퀴·은신처 등)의 위치·회전만 저장한다.
    에셋 형상·치수는 프론트엔드 카탈로그(frontend/src/lib/cageAssets.ts)가 정하고, 서버는 키만 보관한다."""

    __tablename__ = "cage_layouts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    pet_id: Mapped[str | None] = mapped_column(ForeignKey("pets.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(40))
    species: Mapped[str] = mapped_column(String(32))
    size: Mapped[str] = mapped_column(String(32))
    cage_width_mm: Mapped[float]
    cage_depth_mm: Mapped[float]
    cage_height_mm: Mapped[float]
    items: Mapped[list] = mapped_column(JSON)  # [{id, asset, x_mm, y_mm, rotation_deg}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class MarketItem(Base):
    """공유 작품: 회원이 올린 완성 파일(SKP·3MF·STL)이나 NestForge 설계를 공유한다.
    소개 글(post_id)을 커뮤니티에 함께 올리면 댓글은 그 글에서 받는다. 설계를 첨부하면 그 글로 설계가 공개된다."""

    __tablename__ = "market_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32))
    design_id: Mapped[str | None] = mapped_column(ForeignKey("designs.id"), nullable=True)
    design_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"), nullable=True, index=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    # 가상 케이지 배치 예시 (공유할 때의 배치안 사본: name·species·size·cage·items). 기존 DB 에는 마이그레이션으로 추가
    layout: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    owner: Mapped[User] = relationship()
    files: Mapped[list["MarketFile"]] = relationship(order_by="MarketFile.created_at")


class MarketFile(Base):
    """올린 파일. 작품에 붙기 전(item_id 없음)에는 올린 사람만 쓴다. 내용은 저장소(Vercel Blob 또는 로컬 디스크)에 있다."""

    __tablename__ = "market_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("market_items.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(8))     # model | image
    filename: Mapped[str] = mapped_column(String(120))
    format: Mapped[str] = mapped_column(String(8))   # skp | 3mf | stl | png | jpg | webp
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Vercel Blob 공개 주소 (로컬 저장이면 없음)
    # STL·3MF 의 외곽 크기 [x, y, z] mm (가상 케이지에 놓을 때). SKP·이미지는 없음
    dims_mm: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 3D 미리보기용 가벼운 메시 (mesh_preview.py, NFM1). preview_size 가 있으면 만들어 둔 것.
    # preview_url 은 Blob 공개 주소 (로컬 저장이면 없음 → API 경로로 내보낸다)
    preview_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 공유한 배치 예시에 들어 있어 누구나 볼 수 있는 파일 (작품에 붙지 않았어도)
    shared: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MarketUpload(Base):
    """나눠 올리는 중인 파일 (배포 플랫폼의 요청 크기 한도 때문에 3MB 조각으로 받는다)."""

    __tablename__ = "market_uploads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    filename: Mapped[str] = mapped_column(String(120))
    format: Mapped[str] = mapped_column(String(8))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class MarketUploadChunk(Base):
    __tablename__ = "market_upload_chunks"

    upload_id: Mapped[str] = mapped_column(ForeignKey("market_uploads.id", ondelete="CASCADE"), primary_key=True)
    n: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class MarketEvent(Base):
    """탐색 작품을 본 기록·내려받은 기록 (로그인한 회원만). 맞춤 추천에 쓴다."""

    __tablename__ = "market_events"
    __table_args__ = (Index("ix_market_events_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    item_id: Mapped[str] = mapped_column(ForeignKey("market_items.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # view | download | copy
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
