"""규칙 파일(rules/*.yaml) 로더.

종별 치수 기준과 출력 기준은 코드에 하드코딩하지 않고 YAML 파일에서 읽는다.
pydantic 으로 엄격하게 검증하므로(키 오타·누락·범위 오류 → 예외) 잘못된 파일로는 서버가 기동하지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PositiveMM = Annotated[float, Field(gt=0)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GapTrapRule(_Strict):
    safe_max_mm: PositiveMM
    passable_min_mm: PositiveMM

    @model_validator(mode="after")
    def _check_order(self) -> "GapTrapRule":
        if self.safe_max_mm >= self.passable_min_mm:
            raise ValueError("gap_trap.safe_max_mm 는 passable_min_mm 보다 작아야 합니다")
        return self

    def is_trap(self, gap_mm: float, eps: float = 0.05) -> bool:
        """틈이 끼임 위험 구간(safe_max < gap < passable_min)에 있는지."""
        return self.safe_max_mm + eps < gap_mm < self.passable_min_mm - eps


class SizeRules(_Strict):
    display_name: str
    entrance_min_diameter_mm: PositiveMM
    tunnel_min_inner_diameter_mm: PositiveMM
    gap_trap: GapTrapRule
    min_wall_thickness_mm: PositiveMM
    max_ramp_angle_deg: Annotated[float, Field(gt=0, lt=90)]
    max_climb_height_mm: PositiveMM
    max_step_height_mm: PositiveMM
    sand_bath_min_inner_mm: tuple[PositiveMM, PositiveMM]
    sand_bath_min_depth_mm: PositiveMM
    # 은신처 출입구 최소 개수 (막다른 곳 방지)
    hideout_min_entrances: Annotated[int, Field(ge=1)]
    # 권장 최소 사육장 바닥 [긴 변, 짧은 변]. 작으면 경고만 한다 (설계는 막지 않음)
    enclosure_min_floor_mm: tuple[PositiveMM, PositiveMM]
    max_recommended_count: Annotated[int, Field(ge=1)]
    count_warning_ko: str

    @model_validator(mode="after")
    def _check_floor_order(self) -> "SizeRules":
        long_side, short_side = self.enclosure_min_floor_mm
        if long_side < short_side:
            raise ValueError("enclosure_min_floor_mm 는 [긴 변, 짧은 변] 순서여야 합니다")
        return self


class SpeciesEntry(_Strict):
    display_name: str
    sizes: dict[str, SizeRules] = Field(min_length=1)


class SpeciesFile(_Strict):
    version: str
    reviewed: bool = False
    species: dict[str, SpeciesEntry] = Field(min_length=1)


class PrintingRules(_Strict):
    version: str
    nozzle_diameter_mm: PositiveMM
    min_wall_mm: PositiveMM
    max_overhang_deg: Annotated[float, Field(gt=0, lt=90)]
    overhang_area_tolerance_mm2: Annotated[float, Field(ge=0)]
    build_volume_mm: tuple[PositiveMM, PositiveMM, PositiveMM]
    plate_spacing_mm: Annotated[float, Field(ge=0)]
    tessellation_tolerance_mm: PositiveMM
    tessellation_angular_tolerance_deg: PositiveMM


class RuleFileError(RuntimeError):
    """규칙 파일을 읽거나 검증하지 못했을 때."""


class RuleBook(BaseModel):
    """로딩된 전체 규칙. 서비스 전역에서 읽기 전용으로 쓴다."""

    model_config = ConfigDict(frozen=True)

    species_file: SpeciesFile
    printing: PrintingRules
    source_dir: str

    def size_rules(self, species: str, size: str) -> SizeRules:
        try:
            return self.species_file.species[species].sizes[size]
        except KeyError as e:
            raise KeyError(f"규칙이 정의되지 않은 종/크기입니다: {species}/{size}") from e

    def min_wall_for(self, species: str, size: str) -> float:
        """적용 최소 벽 두께 = max(종 갉음 기준, 출력 최소 벽)."""
        return max(self.size_rules(species, size).min_wall_thickness_mm, self.printing.min_wall_mm)


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise RuleFileError(f"규칙 파일이 없습니다: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise RuleFileError(f"YAML 구문 오류 ({path.name}): {e}") from e
    if not isinstance(data, dict):
        raise RuleFileError(f"규칙 파일 최상위는 매핑이어야 합니다: {path}")
    return data


def load_rules(rules_dir: Path) -> RuleBook:
    rules_dir = Path(rules_dir)
    species_path = rules_dir / "species.yaml"
    printing_path = rules_dir / "printing.yaml"
    try:
        species_file = SpeciesFile.model_validate(_read_yaml(species_path))
    except ValidationError as e:
        raise RuleFileError(f"species.yaml 검증 실패:\n{e}") from e
    try:
        printing = PrintingRules.model_validate(_read_yaml(printing_path))
    except ValidationError as e:
        raise RuleFileError(f"printing.yaml 검증 실패:\n{e}") from e
    return RuleBook(species_file=species_file, printing=printing, source_dir=str(rules_dir))
