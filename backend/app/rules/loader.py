"""규칙 파일(rules/*.yaml) 로더.

종별 치수 기준과 출력 기준은 코드에 하드코딩하지 않고 YAML 파일에서 읽는다.
pydantic 으로 엄격하게 검증하므로(키 오타·누락·범위 오류 → 예외) 잘못된 파일로는 서버가 기동하지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# 템플릿 키 목록만 담은 모듈 (다른 모듈을 import 하지 않아 순환이 생기지 않는다)
from app.templates.keys import TEMPLATE_MODULES

PositiveMM = Annotated[float, Field(gt=0)]
NonNegativeMM = Annotated[float, Field(ge=0)]
Degrees = Annotated[float, Field(gt=0, lt=90)]
Count = Annotated[int, Field(ge=1)]

Habitat = Literal["cage", "aquarium"]
# 사육 환경별로 만들 수 있는 구조물. 종이 templates 를 적지 않으면 케이지 기본값을 쓴다
CAGE_TEMPLATES: tuple[str, ...] = ("hideout", "tunnel", "ramp", "sand_bath")
# 어항: 바닥이 열린 상자형 은신처는 물속에서 지붕 아래 공기가 갇혀 뜨고, 램프·모래목욕통은 어항에 맞지 않는다
AQUARIUM_TEMPLATES: tuple[str, ...] = ("cave", "tunnel")
HABITAT_TEMPLATES: dict[str, tuple[str, ...]] = {"cage": CAGE_TEMPLATES, "aquarium": AQUARIUM_TEMPLATES}

# 터널 템플릿 length_mm 의 하한 (app/templates/tunnel.py TunnelParams). 템플릿을 import 하면 순환하므로 값만 둔다.
# 둘이 같은지는 tests/test_rules.py 가 확인한다
TUNNEL_LENGTH_FIELD_MIN_MM = 80.0
# 템플릿 필드 상한 (app/templates/cave.py CaveParams, tunnel.py TunnelParams). 위와 같은 까닭으로 값만 두고
# tests/test_rules.py 가 같은지 확인한다. 규칙 값이 이를 넘으면 그 크기 구분의 구조물을 하나도 만들 수 없다
CAVE_WALL_FIELD_MAX_MM = 3.2
CAVE_ENTRANCE_COUNT_FIELD_MAX = 2
CAVE_ROOF_SLOPE_FIELD_MAX_DEG = 65.0
CAVE_ENTRANCE_FIELD_MAX_MM = 120.0
CAVE_TOP_OPENING_FIELD_MAX_MM = 150.0
TUNNEL_INNER_FIELD_MAX_MM = 130.0
TUNNEL_WALL_FIELD_MAX_MM = 8.0
# 기본 파라미터는 종별 최소 출입구·통과 폭·터널 내경에 이만큼 더해 올린다 (cave/tunnel default_params)
DEFAULT_SIZE_MARGIN_MM = 5.0
# 입력할 수 있는 마릿수의 전체 상한 (API HabitatIn.count). 종별 max_count 는 이 값을 넘을 수 없다
MAX_HABITAT_COUNT = 200


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


class HideoutEntranceRule(_Strict):
    """은신처 출입구 최소 개수. 혼자 키울 때와 여러 마리를 함께 키울 때를 따로 둔다."""

    single: Annotated[int, Field(ge=1)]
    group: Annotated[int, Field(ge=1)]

    def for_count(self, count: int) -> int:
        return self.group if count >= 2 else self.single


class AquaticRules(_Strict):
    """어항(물속) 크기 구분에만 있는 기준. 키는 모두 있어야 한다 (volume_l_per_animal 만 null 가능).
    volume_note_ko·volume_note_below_l 은 적지 않아도 된다 (둘 다 적거나 둘 다 뺀다)."""

    # 동굴 안쪽 천장(모서리선)이 꼭대기 구멍 쪽으로 오르는 최소 경사 (공기가 갇히지 않게)
    ceiling_min_slope_deg: Degrees
    # 구조물 꼭대기 위로 남길 최소 물 깊이
    structure_top_clearance_mm: PositiveMM
    # 수조 전체 부피를 어림할 때 쓰는 바닥재 두께·수면 위 여유
    substrate_depth_assumed_mm: NonNegativeMM
    air_gap_mm: NonNegativeMM
    # 수조 유리 두께 어림. 입력 가로·세로는 수조 안쪽인데 바닥·부피 기준(예: 60×30cm, 54L)은 겉 크기라,
    # 바닥·부피를 비교할 때 안쪽 치수에 이 두께를 더해 겉 크기로 바꾼다 (배치·틈 검사는 안쪽 치수 그대로)
    glass_thickness_assumed_mm: NonNegativeMM
    # 수조 최소 부피 (L), 마리당 부피 (L, 없으면 null)
    min_volume_l: Annotated[float, Field(gt=0)]
    volume_l_per_animal: Annotated[float, Field(gt=0)] | None
    # 구조물 높이 ÷ 바닥 짧은 변 상한 (물속에서 넘어지지 않게)
    max_height_to_base_ratio: Annotated[float, Field(gt=0)]
    # 최소 부피(min_volume_l)는 하한일 뿐이라 종마다 더 큰 권장 부피가 있을 때의 안내 문구와,
    # 수조가 이 부피(L)보다 작으면 그 안내를 띄운다 (설계는 막지 않는 참고). 없으면 안내하지 않는다
    volume_note_ko: str | None = None
    volume_note_below_l: Annotated[float, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def _check_volume_note(self) -> "AquaticRules":
        if (self.volume_note_ko is None) != (self.volume_note_below_l is None):
            raise ValueError("aquatic.volume_note_ko 와 volume_note_below_l 은 둘 다 적거나 둘 다 null 이어야 합니다")
        if self.volume_note_below_l is not None and self.volume_note_below_l <= self.min_volume_l:
            raise ValueError("aquatic.volume_note_below_l 은 min_volume_l 보다 커야 합니다 "
                             "(최소 부피보다 큰 권장 부피를 안내하는 값)")
        return self


class BuoyancyRules(_Strict):
    """물속 무게(부력) 계산용 밀도 (g/cm³)."""

    material_density_g_cm3: PositiveMM
    water_density_g_cm3: PositiveMM

    @model_validator(mode="after")
    def _check_order(self) -> "BuoyancyRules":
        if self.material_density_g_cm3 <= self.water_density_g_cm3:
            raise ValueError("buoyancy.material_density_g_cm3 는 water_density_g_cm3 보다 커야 합니다 "
                             "(물보다 가벼운 소재는 가라앉지 않는다)")
        return self


class SizeRules(_Strict):
    display_name: str
    entrance_min_diameter_mm: PositiveMM
    tunnel_min_inner_diameter_mm: PositiveMM
    gap_trap: GapTrapRule
    min_wall_thickness_mm: PositiveMM
    # 은신처 출입구 최소 개수 (여러 마리가 함께 지낼 때 막다른 곳 방지)
    hideout_min_entrances: HideoutEntranceRule
    # ── 아래는 사육 환경·만들 수 있는 구조물에 따라 필요한 값 (없으면 null). 종 단위 검증(SpeciesEntry)이 필수 여부를 정한다
    # 터널(플라스틱 튜브) 최대 길이: 몸길이의 2배 이하 (DTSchB). null 이면 길이 상한 없음 (어항)
    tunnel_max_length_mm: PositiveMM | None = None
    max_ramp_angle_deg: Degrees | None = None
    max_climb_height_mm: PositiveMM | None = None
    max_step_height_mm: PositiveMM | None = None
    sand_bath_min_inner_mm: tuple[PositiveMM, PositiveMM] | None = None
    sand_bath_min_depth_mm: PositiveMM | None = None
    # 사육장 최소 바닥 기준 [긴 변, 짧은 변]. 작으면 경고만 한다 (설계는 막지 않음). null 이면 검사하지 않음
    enclosure_min_floor_mm: tuple[PositiveMM, PositiveMM] | None = None
    # 권장 최대·최소 마릿수와 그때 띄울 경고 (둘 다 있거나 둘 다 null)
    max_recommended_count: Count | None = None
    count_warning_ko: str | None = None
    min_recommended_count: Count | None = None
    min_count_warning_ko: str | None = None
    # 어항(물속) 기준. 케이지 종은 null
    aquatic: AquaticRules | None = None

    @model_validator(mode="after")
    def _check_floor_order(self) -> "SizeRules":
        if self.enclosure_min_floor_mm is None:
            return self
        long_side, short_side = self.enclosure_min_floor_mm
        if long_side < short_side:
            raise ValueError("enclosure_min_floor_mm 는 [긴 변, 짧은 변] 순서여야 합니다")
        return self

    @model_validator(mode="after")
    def _check_tunnel_length(self) -> "SizeRules":
        # 최소 내경보다 짧은 터널은 터널이 아니고, 템플릿 길이 하한보다 짧으면 만들 수 없다 (값 오타를 기동 때 잡는다)
        if self.tunnel_max_length_mm is None:
            return self
        floor = max(self.tunnel_min_inner_diameter_mm, TUNNEL_LENGTH_FIELD_MIN_MM)
        if self.tunnel_max_length_mm < floor:
            raise ValueError(f"tunnel_max_length_mm 는 {floor:g} 이상이어야 합니다 "
                             "(터널 최소 내경과 템플릿 길이 하한 중 큰 값)")
        return self

    @model_validator(mode="after")
    def _check_count_pairs(self) -> "SizeRules":
        # 마릿수 기준과 경고 문구는 함께 있어야 한다 (기준만 있으면 빈 경고, 문구만 있으면 쓰이지 않는 값)
        for count_key, text_key in (("max_recommended_count", "count_warning_ko"),
                                    ("min_recommended_count", "min_count_warning_ko")):
            if (getattr(self, count_key) is None) != (getattr(self, text_key) is None):
                raise ValueError(f"{count_key} 와 {text_key} 는 둘 다 적거나 둘 다 null 이어야 합니다")
        if (self.max_recommended_count is not None and self.min_recommended_count is not None
                and self.min_recommended_count > self.max_recommended_count):
            raise ValueError("min_recommended_count 는 max_recommended_count 이하여야 합니다")
        return self


# 사육 환경별로 크기 구분마다 있어야 하는 값
_CAGE_REQUIRED_FIELDS: tuple[str, ...] = ("enclosure_min_floor_mm", "max_recommended_count", "count_warning_ko")
# 구조물별로 크기 구분마다 있어야 하는 값 (케이지)
_TEMPLATE_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "tunnel": ("tunnel_max_length_mm",),
    "ramp": ("max_ramp_angle_deg", "max_climb_height_mm", "max_step_height_mm"),
    "sand_bath": ("sand_bath_min_inner_mm", "sand_bath_min_depth_mm", "max_step_height_mm"),
}
# 어항 크기 구분에는 없어야 하는 값 (램프·모래목욕통·오르기 기준)
_AQUARIUM_FORBIDDEN_FIELDS: tuple[str, ...] = (
    "max_ramp_angle_deg", "max_climb_height_mm", "max_step_height_mm", "sand_bath_min_inner_mm", "sand_bath_min_depth_mm",
)


class SpeciesEntry(_Strict):
    display_name: str
    # 사육 환경: cage(케이지) / aquarium(어항). 화면 문구·검사·만들 수 있는 구조물이 달라진다
    habitat: Habitat = "cage"
    # 이 종에 만들 수 있는 구조물 (템플릿 키). 없으면 케이지 기본값 (어항은 반드시 적는다)
    templates: tuple[str, ...] | None = None
    # 입력할 수 있는 최대 마릿수 (API 전체 상한 MAX_HABITAT_COUNT 이하)
    max_count: Annotated[int, Field(ge=1, le=MAX_HABITAT_COUNT)] = 10
    # 출력·설치 안내 문구 (어항 소재·세척 조건 등)
    print_notes_ko: tuple[str, ...] = ()
    # 크기 구분을 고를 때 함께 보일 안내 (어항: 몸길이를 재는 기준, 어느 구분에도 맞지 않는 아주 작은 종). 없으면 null
    size_hint_ko: str | None = None
    # 물속 무게 계산용 밀도 (어항은 필수)
    buoyancy: BuoyancyRules | None = None
    sizes: dict[str, SizeRules] = Field(min_length=1)

    @property
    def allowed_templates(self) -> tuple[str, ...]:
        return self.templates if self.templates is not None else CAGE_TEMPLATES

    @model_validator(mode="after")
    def _check_habitat(self) -> "SpeciesEntry":
        # 오류 메시지에 종 이름·크기 키·필드 이름을 넣는다 (pydantic 위치 정보 species.<키> 와 함께 RuleFileError 로 보인다)
        where = f"{self.display_name}({self.habitat})"
        if self.templates is not None:
            if not self.templates:
                raise ValueError(f"{where}: templates 가 비어 있습니다")
            unknown = [k for k in self.templates if k not in TEMPLATE_MODULES]
            if unknown:
                raise ValueError(f"{where}: templates 에 알 수 없는 템플릿 키가 있습니다: {unknown} "
                                 f"(가능한 키: {sorted(TEMPLATE_MODULES)})")
            if len(set(self.templates)) != len(self.templates):
                raise ValueError(f"{where}: templates 에 같은 키가 두 번 있습니다: {list(self.templates)}")
        elif self.habitat != "cage":
            raise ValueError(f"{where}: habitat 이 cage 가 아니면 templates 를 적어야 합니다")
        allowed = HABITAT_TEMPLATES[self.habitat]
        bad = [k for k in self.allowed_templates if k not in allowed]
        if bad:
            raise ValueError(f"{where}: templates 의 {bad} 는 habitat {self.habitat} 에서 만들 수 없습니다 "
                             f"(가능한 키: {list(allowed)})")
        if self.habitat == "cage":
            self._check_cage(where)
        else:
            self._check_aquarium(where)
        self._check_template_bounds(where)
        return self

    def _check_template_bounds(self, where: str) -> None:
        """규칙 값이 템플릿 필드 범위를 넘으면 그 크기 구분의 구조물을 하나도 만들 수 없다 (모든 설계가 보정 충돌로 막힌다).
        기본 파라미터는 최소값에 DEFAULT_SIZE_MARGIN_MM 를 더하므로 그만큼 여유를 둔다."""
        m = DEFAULT_SIZE_MARGIN_MM
        allowed = self.allowed_templates
        for skey, s in self.sizes.items():
            checks: list[tuple[str, float, float]] = []  # (규칙 키, 값, 상한)
            if "cave" in allowed:
                checks += [
                    ("min_wall_thickness_mm", s.min_wall_thickness_mm, CAVE_WALL_FIELD_MAX_MM),
                    ("hideout_min_entrances.single", s.hideout_min_entrances.single, CAVE_ENTRANCE_COUNT_FIELD_MAX),
                    ("hideout_min_entrances.group", s.hideout_min_entrances.group, CAVE_ENTRANCE_COUNT_FIELD_MAX),
                    ("entrance_min_diameter_mm", s.entrance_min_diameter_mm, CAVE_ENTRANCE_FIELD_MAX_MM - m),
                    ("gap_trap.passable_min_mm", s.gap_trap.passable_min_mm, CAVE_TOP_OPENING_FIELD_MAX_MM - m),
                ]
                if s.aquatic is not None:
                    checks.append(("aquatic.ceiling_min_slope_deg", s.aquatic.ceiling_min_slope_deg,
                                   CAVE_ROOF_SLOPE_FIELD_MAX_DEG))
            if "tunnel" in allowed:
                checks += [
                    ("min_wall_thickness_mm", s.min_wall_thickness_mm, TUNNEL_WALL_FIELD_MAX_MM),
                    ("tunnel_min_inner_diameter_mm", s.tunnel_min_inner_diameter_mm, TUNNEL_INNER_FIELD_MAX_MM - m),
                ]
            for key, value, limit in checks:
                if value > limit + 1e-9:
                    raise ValueError(f"{where} 크기 구분 '{skey}': {key} {value:g} 이(가) 만들 수 있는 구조물의 "
                                     f"범위를 넘습니다 (최대 {limit:g})")

    def _check_cage(self, where: str) -> None:
        if self.buoyancy is not None:
            raise ValueError(f"{where}: buoyancy 는 habitat aquarium 에만 적습니다")
        required = list(_CAGE_REQUIRED_FIELDS)
        for key in self.allowed_templates:
            required += [f for f in _TEMPLATE_REQUIRED_FIELDS.get(key, ()) if f not in required]
        for skey, s in self.sizes.items():
            if s.aquatic is not None:
                raise ValueError(f"{where} 크기 구분 '{skey}': aquatic 은 habitat aquarium 에만 적습니다")
            missing = [f for f in required if getattr(s, f) is None]
            if missing:
                raise ValueError(f"{where} 크기 구분 '{skey}': {', '.join(missing)} 이(가) 필요합니다 "
                                 f"(만들 수 있는 구조물: {list(self.allowed_templates)})")

    def _check_aquarium(self, where: str) -> None:
        if self.buoyancy is None:
            raise ValueError(f"{where}: habitat aquarium 에는 buoyancy 가 필요합니다")
        for skey, s in self.sizes.items():
            if s.aquatic is None:
                raise ValueError(f"{where} 크기 구분 '{skey}': habitat aquarium 에는 aquatic 이 필요합니다")
            extra = [f for f in _AQUARIUM_FORBIDDEN_FIELDS if getattr(s, f) is not None]
            if extra:
                raise ValueError(f"{where} 크기 구분 '{skey}': {', '.join(extra)} 은(는) 어항에 쓰지 않으니 "
                                 "null 로 두거나 지워 주세요")


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

    def species_entry(self, species: str) -> SpeciesEntry:
        try:
            return self.species_file.species[species]
        except KeyError as e:
            raise KeyError(f"규칙이 정의되지 않은 종입니다: {species}") from e

    def habitat(self, species: str) -> Habitat:
        """사육 환경 (cage / aquarium). 모르는 종이면 KeyError."""
        return self.species_entry(species).habitat

    def allowed_templates(self, species: str) -> tuple[str, ...]:
        """이 종에 만들 수 있는 템플릿 키 (templates 를 적지 않은 케이지 종은 케이지 기본값)."""
        return self.species_entry(species).allowed_templates

    def buoyancy(self, species: str) -> BuoyancyRules | None:
        """물속 무게 계산용 밀도 (어항 종만). 모르는 종이면 KeyError."""
        return self.species_entry(species).buoyancy

    def min_wall_for(self, species: str, size: str) -> float:
        """적용 최소 벽 두께 = max(종 갉음 기준, 출력 최소 벽)."""
        return max(self.size_rules(species, size).min_wall_thickness_mm, self.printing.min_wall_mm)

    def display_names(self, species: str, size: str) -> tuple[str, str]:
        """화면에 보일 (종 이름, 크기 이름). 규칙 파일에서 빠진 종·크기(옛 행)는 키를 그대로 돌려준다 (500 이 나지 않게)."""
        sp = self.species_file.species.get(species)
        sz = sp.sizes.get(size) if sp is not None else None
        return (sp.display_name if sp is not None else species, sz.display_name if sz is not None else size)


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
    _check_printing_wall(species_file, printing)
    return RuleBook(species_file=species_file, printing=printing, source_dir=str(rules_dir))


def _check_printing_wall(species_file: SpeciesFile, printing: PrintingRules) -> None:
    """적용 최소 벽 = max(종 기준, 출력 최소 벽) 이 템플릿 벽 두께 상한을 넘으면 그 구조물을 만들 수 없다.
    종 기준은 SpeciesEntry 가 확인하므로 여기서는 출력 최소 벽(printing.yaml)이 넘는 경우를 잡는다."""
    limits = {"cave": CAVE_WALL_FIELD_MAX_MM, "tunnel": TUNNEL_WALL_FIELD_MAX_MM}
    for key, sp in species_file.species.items():
        for template, limit in limits.items():
            if template in sp.allowed_templates and printing.min_wall_mm > limit + 1e-9:
                raise RuleFileError(f"printing.yaml 검증 실패: min_wall_mm {printing.min_wall_mm:g} 이(가) "
                                    f"{sp.display_name}({key}) 의 {template} 벽 두께 상한 {limit:g} 을(를) 넘습니다")
