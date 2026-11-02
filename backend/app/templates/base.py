"""파라메트릭 템플릿 계약.

각 템플릿 모듈은 다음을 한 파일에 정의한다.
  - Params: 입력 파라미터 스키마 (필드별 기하적 허용 범위 = Field(ge, le))
  - constraints(): 종 규칙·출력 규칙·파라미터 상호 관계에서 나오는 동적 허용 범위
  - build(): build123d 형상 생성 (사용 자세, 바닥 Z=0, XY 중심 원점)
  - print_rotation(): 출력 자세 회전 (서포트 없이 출력 가능한 방향)
  - features(): 검증에 쓰는 설계 특징 (벽 두께, 개구부, 출입 방향 등)

LLM 은 Params 값만 결정한다. 형상은 오직 build() 가 만든다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Literal

import numpy as np
from build123d import Part
from pydantic import BaseModel, ConfigDict

from app.rules.loader import SizeRules

# 로컬 좌표계에서 구조물의 측면. 회전 0° 일 때 front = -Y 방향.
Side = Literal["front", "back", "left", "right"]


class TemplateParams(BaseModel):
    """모든 템플릿 파라미터의 기반. 알 수 없는 키는 거부한다."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ParamConstraint:
    """파라미터 하나에 대한 동적 허용 범위."""

    field: str
    min: float | None = None
    max: float | None = None
    source: Literal["species", "printing", "geometry"] = "geometry"
    reason_ko: str = ""

    def violates(self, value: float, eps: float = 1e-6) -> bool:
        return (self.min is not None and value < self.min - eps) or (
            self.max is not None and value > self.max + eps
        )


@dataclass(frozen=True)
class Opening:
    """구조물의 개구부.

    kind:
      - "passage": 동물이 통과하는 개구부 (출입구, 터널 내부). 크기 ≥ 통과 기준이어야 함
      - "vent": 통과용이 아닌 구멍 (환기구). 크기 ≤ 끼임 안전 기준이어야 함
    """

    kind: Literal["passage", "vent"]
    size_mm: float
    label_ko: str
    # passage 의 최소 크기를 정하는 species.yaml 키 (예: "entrance_min_diameter_mm").
    # 없으면 gap_trap.passable_min_mm 를 적용한다. 수치는 항상 규칙 파일에서 읽는다.
    rule_key: str | None = None


@dataclass(frozen=True)
class Features:
    min_wall_thickness_mm: float
    openings: tuple[Opening, ...] = ()
    # 출입을 위해 비워 둬야 하는 측면 (로컬 좌표). 배치·검증에서 막히지 않았는지 확인한다.
    access_sides: tuple[Side, ...] = ()
    # 동물이 올라가는 구조물의 높이·경사·단 높이 (해당 시)
    climb_height_mm: float | None = None
    slope_deg: float | None = None
    step_height_mm: float | None = None
    # 은신처처럼 드나드는 구조물의 출입구 개수 (해당 시). 종별 최소 개수와 비교한다
    entrance_count: int | None = None
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RuleContext:
    """템플릿이 동적 범위를 계산할 때 쓰는 규칙 값."""

    size: SizeRules
    min_wall_mm: float  # max(종 갉음 기준, 출력 최소 벽)
    count: int = 1  # 함께 지내는 마릿수 (마릿수에 따라 달라지는 규칙용)

    @property
    def hideout_min_entrances(self) -> int:
        return self.size.hideout_min_entrances.for_count(self.count)


class Template(ABC):
    key: ClassVar[str]
    display_name_ko: ClassVar[str]
    description_ko: ClassVar[str]  # LLM 카탈로그용 설명
    Params: ClassVar[type[TemplateParams]]
    # 케이지 높이에 맞춰 제한할 높이 파라미터 (없으면 None)
    height_field: ClassVar[str | None] = None
    # 공간이 부족할 때 줄일 수 있는 크기 파라미터
    size_fields: ClassVar[tuple[str, ...]] = ()
    # 나중에 추가된 Params 필드 중, 새 기본값이 예전 형상과 다른 필드의 "예전 값".
    # 저장된 설계를 다시 만들 때(메시 캐시가 비었을 때) 저장 당시와 같은 형상이 나오게 한다.
    legacy_defaults: ClassVar[dict[str, object]] = {}

    def load_stored_params(self, raw: dict) -> TemplateParams:
        """DB 에 저장된 최종 파라미터를 읽는다. 저장 당시 없던 필드는 legacy_defaults 로 채운다."""
        return self.Params.model_validate({**self.legacy_defaults, **raw})

    def default_params(self, ctx: RuleContext | None = None) -> TemplateParams:
        return self.Params()

    @abstractmethod
    def constraints(self, p: TemplateParams, ctx: RuleContext) -> list[ParamConstraint]:
        """종·출력 규칙과 파라미터 상호 관계에서 나오는 허용 범위 목록."""

    @abstractmethod
    def build(self, p: TemplateParams) -> Part:
        """사용 자세 형상. 바닥 Z=0, XY 는 외곽 중심이 원점."""

    def print_rotation(self, p: TemplateParams) -> np.ndarray:
        """사용 자세 → 출력 자세 회전 행렬(3x3). 기본: 그대로 출력."""
        return np.eye(3)

    @abstractmethod
    def features(self, p: TemplateParams) -> Features:
        """검증용 설계 특징."""
