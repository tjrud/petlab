"""DB 모델: 사육 환경, 설계, 설계 버전, 제작·배송 대기 신청."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uid() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Habitat(Base):
    __tablename__ = "habitats"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    habitat: Mapped[Habitat] = relationship()
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    design: Mapped[Design] = relationship(back_populates="versions")


class WaitlistEntry(Base):
    __tablename__ = "waitlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320))
    design_id: Mapped[str | None] = mapped_column(ForeignKey("designs.id"), nullable=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
