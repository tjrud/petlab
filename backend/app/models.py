"""DB 모델: 회원, 반려동물, 사육 환경, 설계, 설계 버전, 커뮤니티, 제작·배송 대기 신청."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
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

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    nickname: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # member | admin
    # 비밀번호를 바꾸면 올려서 다른 기기의 세션을 끊는다
    session_version: Mapped[int] = mapped_column(Integer, default=1)
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
