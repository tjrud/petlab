"""파라메트릭 템플릿 계약.

각 템플릿 모듈은 다음을 한 파일에 정의한다.
  - Params: 입력 파라미터 스키마 (필드별 기하적 허용 범위 = Field(ge, le))
  - constraints(): 종 규칙·출력 규칙·파라미터 상호 관계에서 나오는 동적 허용 범위
  - build(): build123d 형상 생성 (사용 자세, 바닥 Z=0, XY 중심 원점)
  - print_rotation(): 출력 자세 회전 (서포트 없이 출력 가능한 방향)
  - print_parts(): 출력 파트 목록 (기본은 build() 형상 하나. 한 덩어리로 서포트 없이 출력할 수 없는 조립형
    구조물은 본체·지붕·층판처럼 2~3개 파트로 나눈다)
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
    # False: 새 설계에서는 보정하지만, 이 기준이 생기기 전에 저장된 버전을 다시 검증할 때는 막지 않고 경고만 한다.
    # 나중에 더한 복지 기준(예: 터널 최대 길이)용. 끼임·통과 폭처럼 안전에 바로 닿는 기준은 True 로 둔다.
    blocking: bool = True

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
class PrintPart:
    """출력 파트 하나: 파트 자신의 좌표계 형상과 그 출력 자세 회전.

    key 는 파일 이름에 쓰는 ASCII 식별자(body, roof, floor …), name_ko 는 화면에 보이는 이름.
    조립 형상(build())과 파트 형상은 같은 치수를 써야 하며, 파트별로 메시 건전성·벽 두께 실측·오버행·출력 공간을 검사한다.
    """

    name_ko: str
    part: Part
    rotation: np.ndarray
    key: str = "body"


@dataclass(frozen=True)
class DecorZone:
    """안전과 무관한 면에서 장식(무늬·각인)을 얹을 수 있는 영역.

    면 좌표 (u, v): u 는 바깥에서 그 면을 볼 때 오른쪽, v 는 위. 원점은 면의 가로 가운데·구조물 바닥(Z=0).
    영역은 [u0, u1] × [v0, v1] 에서 obstacles(출입구·창·연결부·결합부, (u0, v0, u1, v1))를 keepout_mm 만큼 넓혀 뺀 곳이다.
    mode: engrave(파내기) 또는 relief(돋을새김). 돋을새김은 출력 자세에서 오버행이 생기지 않는 세로 벽에서만.
    지붕(face="roof")은 평면 경사면(경사 지붕)에서 각인만: 경사면을 기울어진 벽으로 보고 x_dir(용마루 방향)·z_dir(바깥 법선)을 준다.
    """

    face: Side | Literal["roof"]
    mode: Literal["engrave", "relief"]
    max_depth_mm: float
    keepout_mm: float
    u0: float
    u1: float
    v0: float
    v1: float
    obstacles: tuple[tuple[float, float, float, float], ...] = ()
    part_key: str = "body"  # 이 면이 속한 출력 파트
    print_inverted: bool = False  # 그 파트를 뒤집어 출력하는지 (파낸 홈의 천장 기울기 방향이 바뀐다)
    thickness_field: str | None = None  # 이 면의 벽 두께 파라미터 (각인 깊이만큼 두껍게 보정하는 데 쓴다)
    # 면 좌표 원점(u=0, v=0)의 월드 좌표: 바깥 표면 위의 점 (세로 벽은 바닥점, 경사면은 처마 가운데)
    surface: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # 면의 u 방향·바깥 법선 (월드). None 이면 face 에서 정한다 (세로 벽). v 방향 = z_dir × x_dir (위쪽)
    x_dir: tuple[float, float, float] | None = None
    z_dir: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class RuleContext:
    """템플릿이 동적 범위를 계산할 때 쓰는 규칙 값."""

    size: SizeRules
    min_wall_mm: float  # max(종 갉음 기준, 출력 최소 벽)
    count: int = 1  # 함께 지내는 마릿수 (마릿수에 따라 달라지는 규칙용)
    # 서포트 없이 출력할 수 있는 최대 오버행(printing.yaml). 출력 자세가 지붕 경사 같은 파라미터를 제한할 때 쓴다.
    # None 이면(옛 호출) 출력 규칙 기반 제약은 내지 않는다
    printing_max_overhang_deg: float | None = None
    # 장식의 최소 형상 크기(printing.yaml min_feature_mm). None 이면 장식을 적용하지 않는다
    min_feature_mm: float | None = None

    @property
    def hideout_min_entrances(self) -> int:
        return self.size.hideout_min_entrances.for_count(self.count)

    @property
    def default_wall_mm(self) -> float:
        """기본 파라미터의 벽 두께: 3mm 와 적용 최소 벽 중 큰 값."""
        return max(3.0, self.min_wall_mm)

    def wall_thickness_constraint(self) -> ParamConstraint:
        """벽 두께 최소 제약 (은신처·모래목욕통·터널 공통).

        종 갉음 기준이 적용 최소 벽을 정하면 출처는 species, 출력 최소 벽이 더 두꺼우면 printing.
        """
        return ParamConstraint(
            "wall_thickness_mm",
            min=self.min_wall_mm,
            source="species" if self.size.min_wall_thickness_mm >= self.min_wall_mm else "printing",
            reason_ko=f"벽 두께는 최소 {self.min_wall_mm:g}mm 이상이어야 합니다 (갉음 내구성·출력 기준)",
        )


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

    def print_parts(self, p: TemplateParams, built: Part | None = None) -> list[PrintPart]:
        """출력 파트 목록. 기본: build() 형상 하나를 print_rotation() 자세로 (built 가 있으면 다시 만들지 않는다).

        여러 파트로 나누는 템플릿은 이를 덮어쓴다. 파트는 사용 자세·조립 위치 그대로 두고 rotation 으로만 출력 자세를
        정한다. 케이지 배치·겹침·끼임·출입구 검사는 build() 의 조립 형상으로 한다."""
        return [PrintPart("본체", built if built is not None else self.build(p), self.print_rotation(p))]

    @abstractmethod
    def features(self, p: TemplateParams) -> Features:
        """검증용 설계 특징."""

    def decor_zones(self, p: TemplateParams) -> list[DecorZone]:
        """장식을 얹을 수 있는 영역 (기본: 없음). 장식은 features() 와 검사 결과를 바꾸지 않아야 한다."""
        return []

