"""API 요청·응답 스키마."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width_mm: float = Field(ge=200, le=2000, description="케이지 내부 가로 mm")
    depth_mm: float = Field(ge=200, le=2000, description="케이지 내부 세로 mm")
    height_mm: float = Field(ge=100, le=1000, description="케이지 내부 높이 mm")


class HabitatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    species: str = Field(examples=["hamster"])
    size: str = Field(examples=["syrian"])
    count: int = Field(ge=1, le=10)
    cage: CageIn


class HabitatOut(BaseModel):
    id: str
    species: str
    species_name_ko: str
    size: str
    size_name_ko: str
    count: int
    cage: CageIn
    created_at: datetime


class DesignCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    habitat_id: str
    prompt: str = Field(min_length=1, max_length=2000)


class DesignReviseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=2000)
    base_version: int | None = Field(default=None, description="수정의 기준 버전 (기본: 최신)")


class PlacementOut(BaseModel):
    x_mm: float
    y_mm: float
    rotation_deg: int


class ItemOut(BaseModel):
    index: int
    template: str
    label_ko: str
    params: dict
    reason_ko: str
    placement: PlacementOut | None
    size_mm: list[float]           # 사용 자세 [가로, 세로, 높이]
    print_size_mm: list[float]     # 출력 자세 [X, Y, Z]
    mesh_url: str | None           # 케이지 좌표계로 배치된 STL (배치 실패 시 null)


class VersionSummary(BaseModel):
    version: int
    prompt: str
    passed: bool
    provider: str
    created_at: datetime


class VersionOut(BaseModel):
    version: int
    prompt: str
    provider: str
    summary_ko: str
    notes_ko: list[str]
    items: list[ItemOut]
    validation: dict
    export_allowed: bool
    created_at: datetime


class DesignOut(BaseModel):
    id: str
    habitat: HabitatOut
    versions: list[VersionSummary]
    current: VersionOut


class WaitlistIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    design_id: str | None = None
    version: int | None = None


class WaitlistOut(BaseModel):
    ok: bool
    message_ko: str
