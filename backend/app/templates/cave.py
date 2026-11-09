"""물속 동굴 템플릿 (어항용).

형상: 바닥이 열린 얇은 벽 상자 위에, 꼭대기 구멍 쪽으로 오르는 사각뿔대 지붕을 얹은 동굴.
  - 안쪽 천장(지붕 네 면)이 모두 꼭대기 구멍으로 올라가므로 물에 넣었을 때 안에 공기가 갇히지 않는다
    (바닥이 열린 상자형 은신처는 평평한 지붕 아래에 공기가 남아 뜬다).
  - 지붕 네 면은 안쪽 벽에서 꼭대기 구멍까지 같은 수평 거리(run)를 오르므로 경사가 모두 같다.
    가장 완만한 선은 모서리선(대각선)이고, 그 각도가 roof_slope_deg 다: tan(면 경사) = √2 · tan(모서리선 경사).
  - 바깥 지붕은 안쪽 지붕 면을 법선 방향으로 벽 두께만큼 옮긴 면이라 지붕 두께가 벽 두께와 같다.
  - 꼭대기 구멍 둘레는 벽 두께 높이의 수직 테두리(collar)로 끝난다. 경사 지붕을 수평으로 자르면 구멍 가장자리가
    칼날처럼 얇아지므로(두께 → 0), 수직 테두리로 받쳐 어디서나 벽 두께 이상이 되게 한다.
  - 앞(-Y)·뒤(+Y) 벽에 물방울형 아치 출입구 (터널 단면과 같은 모양: 꼭대기 직선부 오버행 40°).
  - 벽은 3.2mm 이하라 둘레선만으로 속이 꽉 찬다 (채움 비율에 따라 속에 빈 공간이 생기지 않는다).
출력: 사용 자세 그대로 (열린 바닥이 베드). 안쪽 지붕 면 오버행 = 90° − 면 경사 ≤ 약 40.1° 라 서포트가 필요 없다.
"""

from __future__ import annotations

import math

from build123d import Align, Circle, Part, Plane, Polygon, Pos, Rectangle, extrude, loft
from pydantic import Field

from app.templates.base import (
    Features,
    Opening,
    ParamConstraint,
    RuleContext,
    Side,
    Template,
    TemplateParams,
)

# 출입구 꼭대기 직선부가 시작되는 접점의 각도(꼭대기 기준). 50° 이면 직선부 오버행 = 90-50 = 40° (< 45°)
TIP_ANGLE_DEG = 50.0
# 꼭대기 구멍은 안쪽 폭보다 이만큼 이상 작아야 한다 (지붕 경사면이 한쪽에 5mm 이상 남도록)
TOP_RIM_MARGIN_MM = 10.0
# 서포트 없이 출력할 수 있는 지붕 모서리선 최소 경사 (= roof_slope_deg 필드 하한)
PRINT_MIN_ROOF_SLOPE_DEG = 40.0
MAX_WALL_MM = 3.2  # 둘레선만으로 속이 꽉 차는 벽 두께 상한 (= wall_thickness_mm 필드 상한)
MIN_WALL_FIELD_MM = 1.2  # wall_thickness_mm 필드 하한
MIN_DOOR_FIELD_MM, MAX_DOOR_FIELD_MM = 12.0, 120.0  # entrance_diameter_mm 필드 범위
MAX_ROOF_SLOPE_DEG = 65.0  # roof_slope_deg 필드 상한
MIN_HEIGHT_FIELD_MM = 30.0  # height_mm 필드 하한
MAX_TOP_OPENING_FIELD_MM = 150.0  # top_opening_mm 필드 상한
# 꼭대기 구멍을 가장 넓혔을 때(안쪽 폭 − 10mm) 지붕 면 하나의 수평 거리
MIN_ROOF_RUN_MM = TOP_RIM_MARGIN_MM / 2
_CUT = 1.0  # 불리언 연산이 면과 정확히 겹치지 않도록 잘라내는 형상을 이만큼 연장


class CaveParams(TemplateParams):
    width_mm: float = Field(80, ge=50, le=300, description="외형 가로(X) mm")
    depth_mm: float = Field(70, ge=50, le=300, description="외형 세로(Y) mm")
    height_mm: float = Field(
        70, ge=MIN_HEIGHT_FIELD_MM, le=250,
        description="외형 높이(Z) mm. 바닥에서 꼭대기 구멍 테두리까지. 최소 높이 = 출입구 높이(폭의 약 1.28배) + 벽 두께 2배 + "
                    "지붕 높이이고, 지붕 높이는 (가로·세로 중 짧은 쪽 안쪽 폭 − 꼭대기 구멍 폭)에 비례한다. "
                    "얕은 수조에서는 가로·세로를 줄이거나 꼭대기 구멍을 넓힌다",
    )
    entrance_diameter_mm: float = Field(
        25, ge=MIN_DOOR_FIELD_MM, le=MAX_DOOR_FIELD_MM,
        description="출입구 폭 mm. 물방울형 아치라 전체 높이는 폭의 약 1.28배. 종별 최소값 이상",
    )
    entrance_count: int = Field(
        2, ge=1, le=2,
        description="출입구 개수. 1=앞면만, 2=앞·뒷면 관통형. 물고기는 2 (종별 최소 개수 이상)",
    )
    top_opening_mm: float = Field(
        25, ge=10, le=MAX_TOP_OPENING_FIELD_MM,
        description="꼭대기 구멍 폭 mm. 꼭대기 구멍의 짧은 변(안쪽)으로, 공기가 빠지는 길이자 위쪽 출구다. 종별 통과 폭 이상",
    )
    roof_slope_deg: float = Field(
        45, ge=PRINT_MIN_ROOF_SLOPE_DEG, le=MAX_ROOF_SLOPE_DEG,
        description="지붕 경사(도). 안쪽 천장 모서리선(가장 완만한 선)이 수평과 이루는 각. 40° 미만이면 서포트 없이 출력할 수 없다",
    )
    wall_thickness_mm: float = Field(
        3, ge=MIN_WALL_FIELD_MM, le=MAX_WALL_MM, description="벽 두께 mm. 3.2mm 이하면 둘레선만으로 속이 꽉 찬다"
    )


# ── 형상 계산 (제약·테스트가 함께 쓴다) ──────────────────────


def inner_size(p: CaveParams) -> tuple[float, float]:
    """안쪽 가로·세로 (Wi, Di)."""
    t = p.wall_thickness_mm
    return p.width_mm - 2 * t, p.depth_mm - 2 * t


def roof_run(p: CaveParams) -> float:
    """지붕 면 하나의 수평 거리: 안쪽 벽에서 꼭대기 구멍 가장자리까지 (네 면이 같다)."""
    wi, di = inner_size(p)
    return (min(wi, di) - p.top_opening_mm) / 2


def rise_per_run(roof_slope_deg: float) -> float:
    """지붕 면이 수평 1mm 에 오르는 높이 = tan(면 경사) = √2·tan(모서리선 경사)."""
    return math.sqrt(2) * math.tan(math.radians(roof_slope_deg))


def face_slope_deg(p: CaveParams) -> float:
    """지붕 면(가장 가파른 선)의 경사. 모서리선 수평 거리는 면의 √2 배라 tan(면) = √2·tan(모서리선)."""
    return math.degrees(math.atan(rise_per_run(p.roof_slope_deg)))


def roof_rise(p: CaveParams) -> float:
    """안쪽 처마(z0)에서 경사 지붕 꼭대기(꼭대기 테두리 아래)까지 높이."""
    return roof_run(p) * math.tan(math.radians(face_slope_deg(p)))


def collar_height(p: CaveParams) -> float:
    """꼭대기 구멍 둘레 수직 테두리 높이 (= 벽 두께: 테두리 윗면에서 잰 두께도 벽 두께 이상)."""
    return p.wall_thickness_mm


def roof_top_height(p: CaveParams) -> float:
    """경사 지붕이 끝나고 수직 테두리가 시작되는 높이."""
    return p.height_mm - collar_height(p)


def eave_height(p: CaveParams) -> float:
    """안쪽 처마 높이 z0: 안쪽 수직 벽이 끝나고 경사 천장이 시작되는 높이."""
    return roof_top_height(p) - roof_rise(p)


def outer_eave_height(p: CaveParams) -> float:
    """바깥 처마 높이: 안쪽 지붕 면을 법선 방향으로 t 만큼 옮긴 면이 바깥 벽과 만나는 높이."""
    b = math.radians(face_slope_deg(p))
    return eave_height(p) + p.wall_thickness_mm * (1 - math.sin(b)) / math.cos(b)


def top_opening_inner(p: CaveParams) -> tuple[float, float]:
    """꼭대기 구멍(안쪽) 가로·세로. 짧은 변 = top_opening_mm. 수직 테두리라 높이에 따라 바뀌지 않는다."""
    wi, di = inner_size(p)
    run = roof_run(p)
    return wi - 2 * run, di - 2 * run


def top_outer(p: CaveParams) -> tuple[float, float]:
    """꼭대기 바깥 테두리 가로·세로 (바깥 지붕 면이 수직 테두리와 만나는 곳)."""
    ai, bi = top_opening_inner(p)
    k = 2 * p.wall_thickness_mm / math.sin(math.radians(face_slope_deg(p)))
    return ai + k, bi + k


def door_top(d: float) -> float:
    """물방울형 출입구 꼭대기 높이 (바닥 기준) = r(1 + 1/cos 50°) ≈ 폭 × 1.28."""
    r = d / 2
    return r * (1 + 1 / math.cos(math.radians(TIP_ANGLE_DEG)))


def min_height(p: CaveParams) -> float:
    """출입구 위로 벽 두께만큼 수직 벽이 남고 지붕 경사·꼭대기 테두리가 들어가는 최소 외형 높이."""
    return roof_rise(p) + collar_height(p) + door_top(p.entrance_diameter_mm) + p.wall_thickness_mm


def max_top_opening(p: CaveParams) -> float:
    return min(p.width_mm, p.depth_mm) - 2 * p.wall_thickness_mm - TOP_RIM_MARGIN_MM


def lowest_height(entrance_diameter_mm: float, wall_thickness_mm: float, roof_slope_deg: float) -> float:
    """이 출입구 폭·벽 두께·지붕 경사로 만들 수 있는 가장 낮은 외형 높이.
    꼭대기 구멍을 가장 넓혀(안쪽 폭 − 10mm) 지붕 면 수평 거리가 5mm 만 남을 때다 (가로·세로와 상관없다)."""
    return (MIN_ROOF_RUN_MM * rise_per_run(roof_slope_deg) + 2 * wall_thickness_mm
            + door_top(entrance_diameter_mm))


def door_wall_ys(p: CaveParams) -> tuple[float, ...]:
    """출입구가 뚫린 벽의 중심 Y (앞, 뒤)."""
    half = p.depth_mm / 2 - p.wall_thickness_mm / 2
    return (-half, half)[: p.entrance_count]


def _ceil1(x: float) -> float:
    """0.1mm 단위로 올림 (부동소수 오차로 한 칸 더 올라가지 않게 조금 깎고 올린다)."""
    return math.ceil(x * 10 - 1e-6) / 10


def _floor1(x: float) -> float:
    """0.1 단위로 내림 (부동소수 오차로 한 칸 더 내려가지 않게 조금 더하고 내린다)."""
    return math.floor(x * 10 + 1e-6) / 10


def _species_slope(ctx: RuleContext) -> float | None:
    return ctx.size.aquatic.ceiling_min_slope_deg if ctx.size.aquatic is not None else None


def _lowest_values(ctx: RuleContext) -> tuple[float, float, float]:
    """규칙이 허용하는 가장 작은 (출입구 폭, 벽 두께, 지붕 경사). 필드 범위 안으로 자른다."""
    d = min(MAX_DOOR_FIELD_MM, max(MIN_DOOR_FIELD_MM, ctx.size.entrance_min_diameter_mm))
    t = min(MAX_WALL_MM, max(MIN_WALL_FIELD_MM, ctx.min_wall_mm))
    slope = min(MAX_ROOF_SLOPE_DEG, max(PRINT_MIN_ROOF_SLOPE_DEG, _species_slope(ctx) or 0.0))
    return d, t, slope


def _door_profile(d: float, bottom: float):
    """물방울형 아치 (2D, x=가로, y=높이): 바닥~r 직사각형 + 높이 r 에 중심을 둔 원 + 꼭대기 삼각형."""
    r = d / 2
    a = math.radians(TIP_ANGLE_DEG)
    rect = Pos(0, bottom) * Rectangle(2 * r, r - bottom, align=(Align.CENTER, Align.MIN))
    circle = Pos(0, r) * Circle(r)
    tip = Polygon(
        (-r * math.sin(a), r + r * math.cos(a)),
        (r * math.sin(a), r + r * math.cos(a)),
        (0, r + r / math.cos(a)),
        align=None,
    )
    return rect + circle + tip


def _rect_at(w: float, d: float, z: float):
    return Pos(0, 0, z) * Rectangle(w, d)


class CaveTemplate(Template):
    key = "cave"
    display_name_ko = "물속 동굴"
    description_ko = (
        "어항(수조)용 물속 동굴. 바닥이 열린 얇은 벽 상자 위에 꼭대기 구멍 쪽으로 오르는 경사 지붕을 얹어, "
        "물에 넣어도 안에 공기가 갇히지 않고 꼭대기 구멍이 위쪽 출구도 된다. 앞·뒤에 물방울형 출입구 (물고기는 앞뒤로 뚫린 관통형 2개). "
        "가로·세로·높이, 출입구 폭·개수, 꼭대기 구멍 폭, 지붕 경사, 벽 두께를 정한다. 서포트 없이 바로 세워 출력한다."
    )
    Params = CaveParams
    height_field = "height_mm"
    size_fields = ("width_mm", "depth_mm", "height_mm")
    legacy_defaults: dict[str, object] = {}

    def default_params(self, ctx: RuleContext | None = None) -> CaveParams:
        if ctx is None:
            return CaveParams()
        s = ctx.size
        t = min(MAX_WALL_MM, ctx.default_wall_mm)
        d = float(math.ceil(s.entrance_min_diameter_mm + 5))
        o = float(math.ceil(s.gap_trap.passable_min_mm + 5))
        slope = max(45.0, s.aquatic.ceiling_min_slope_deg if s.aquatic is not None else 45.0)
        w = max(80.0, d + 4 * t + 40)
        depth = max(70.0, d + 2 * t + 30, o + 2 * t + 30)
        p = CaveParams(width_mm=w, depth_mm=depth, height_mm=70, entrance_diameter_mm=d, entrance_count=2,
                       top_opening_mm=o, roof_slope_deg=slope, wall_thickness_mm=t)
        return p.model_copy(update={"height_mm": max(30.0, float(math.ceil(min_height(p) - 1e-9)))})

    def min_height_mm(self, ctx: RuleContext) -> float:
        """규칙이 허용하는 가장 낮은 동굴: 종별 최소 출입구 폭·최소 벽 두께·최소 지붕 경사에 꼭대기 구멍을 가장 넓힌 것."""
        return max(MIN_HEIGHT_FIELD_MM, _ceil1(lowest_height(*_lowest_values(ctx))))

    def constraints(self, p: CaveParams, ctx: RuleContext) -> list[ParamConstraint]:
        s = ctx.size
        P = s.gap_trap.passable_min_mm
        # 다른 제약이 보정할 값을 미리 반영해 계산한다 (보정 반복 횟수를 줄이고, 보정 순서에 따라 결과가 달라지지 않게)
        t = max(p.wall_thickness_mm, ctx.min_wall_mm)
        d = max(p.entrance_diameter_mm, s.entrance_min_diameter_mm)
        species_slope = _species_slope(ctx)
        # 꼭대기 구멍 최소 폭 둘레에 지붕 경사면이 남는 가로·세로 (모자라면 구멍을 줄일 수 없어 상자를 키운다)
        roof_min = P + 2 * t + TOP_RIM_MARGIN_MM
        width = max(p.width_mm, d + 4 * t, roof_min)
        depth = max(p.depth_mm, d + 2 * t, roof_min)
        # 꼭대기 구멍 상한은 아래 제약이 키울 가로·세로로 계산한다 (지금 값으로 계산하면 구멍을 필요 이상으로 줄인다)
        top_max = min(width, depth) - 2 * t - TOP_RIM_MARGIN_MM
        effective = p.model_copy(update={
            "wall_thickness_mm": t,
            "entrance_diameter_mm": d,
            "width_mm": width,
            "depth_mm": depth,
            "top_opening_mm": min(max(p.top_opening_mm, P), top_max),
            "roof_slope_deg": max(p.roof_slope_deg, species_slope or 0.0),
        })
        # 얕은 수조: 높이 한도 안에 들어가도록 지붕을 낮추는 제약 (한도가 없거나 이미 들어가면 없음)
        fit, fitted = self._fit_height_limit(effective, ctx)
        effective = effective.model_copy(update=fitted)
        n_min = ctx.hideout_min_entrances
        out = [ctx.wall_thickness_constraint()]
        out.append(ParamConstraint(
            "entrance_diameter_mm", min=s.entrance_min_diameter_mm, source="species",
            reason_ko=f"{s.display_name} 출입구는 최소 {s.entrance_min_diameter_mm:g}mm 이상이어야 합니다",
        ))
        if n_min > 1:
            out.append(ParamConstraint(
                "entrance_count", min=n_min, source="species",
                reason_ko=f"물고기는 좁은 곳에서 뒤로 잘 빠져나오지 못해 동굴 출입구는 {n_min}개 이상"
                          "(앞뒤로 뚫린 관통형)이어야 합니다",
            ))
        out += [
            ParamConstraint(
                "top_opening_mm", min=P, source="species",
                reason_ko=f"물속에서 공기가 빠지고 몸이 끼지 않도록 꼭대기 구멍은 최소 {P:g}mm 이상이어야 합니다",
            ),
            ParamConstraint(
                "top_opening_mm", max=top_max,
                reason_ko="지붕 경사면이 남도록 꼭대기 구멍은 안쪽 폭보다 10mm 이상 작아야 합니다",
            ),
        ]
        if species_slope is not None and species_slope > PRINT_MIN_ROOF_SLOPE_DEG:
            out.append(ParamConstraint(
                "roof_slope_deg", min=species_slope, source="species",
                reason_ko=f"안쪽 천장에 공기가 남지 않도록 지붕 경사는 {species_slope:g}° 이상이어야 합니다",
            ))
        roof_reason = f"꼭대기 구멍(최소 {P:g}mm) 둘레에 지붕 경사면이 남도록 가로·세로는 {roof_min:g}mm 이상이어야 합니다"
        h_min = _ceil1(min_height(effective))
        out += [
            ParamConstraint(
                "width_mm", min=d + 4 * t,
                reason_ko="출입구 양옆에 벽이 남도록 가로가 출입구 폭보다 충분히 커야 합니다",
            ),
            ParamConstraint(
                "depth_mm", min=d + 2 * t,
                reason_ko="내부 공간 확보를 위해 세로가 출입구 폭보다 커야 합니다",
            ),
            ParamConstraint("width_mm", min=roof_min, reason_ko=roof_reason),
            ParamConstraint("depth_mm", min=roof_min, reason_ko=roof_reason),
            *fit,
            ParamConstraint(
                "height_mm", min=h_min,
                reason_ko=f"출입구 위로 벽이 남고 지붕 경사가 들어가도록 높이는 {h_min:g}mm 이상이어야 합니다",
            ),
        ]
        return out

    def _fit_height_limit(self, e: CaveParams, ctx: RuleContext) -> tuple[list[ParamConstraint], dict[str, float]]:
        """얕은 수조: 높이 한도(ctx.height_limit_mm) 안에 들어가도록 지붕을 낮추는 제약과 그 값.

        e 는 다른 제약이 보정할 값을 미리 반영한 파라미터다. 한도가 없거나 이미 들어가면 아무것도 바꾸지 않는다.
        지붕 높이는 지붕 면 수평 거리 (짧은 쪽 안쪽 폭 − 꼭대기 구멍 폭)/2 에 비례하므로, 모양이 덜 바뀌는 것부터 바꾼다:
          1) 꼭대기 구멍을 넓힌다 (구멍 필드 상한에 걸리면 가로·세로 중 짧은 변을 줄인다)
          2) 구멍을 가장 넓혀도(지붕 면 5mm) 높으면 지붕 경사 → 벽 두께 → 출입구 폭 순서로 종 기준까지 줄인다
        가장 작게 만들어도 들어가지 않으면 아무것도 바꾸지 않는다 (엔진이 물 깊이가 모자란다고 따로 알린다)."""
        limit = ctx.height_limit_mm
        # 높이 하한은 0.1mm 단위로 올려 쓰므로(아래 h_min) 올린 값으로 비교하고, 맞출 때도 0.1mm 단위로 내린 한도에 맞춘다
        if limit is None or _ceil1(min_height(e)) <= limit + 1e-9:
            return [], {}
        cap = _floor1(limit)
        d_min, t_min, slope_min = _lowest_values(ctx)
        if self.min_height_mm(ctx) > cap + 1e-9:
            return [], {}
        aq = ctx.size.aquatic
        clearance = aq.structure_top_clearance_mm if aq is not None else 0.0
        reason = f"물이 얕아 동굴을 높이 {limit:g}mm(물 깊이 − {clearance:g}mm) 안에 맞추려고 함께 조정했습니다"
        out: list[ParamConstraint] = []
        fitted: dict[str, float] = {}

        def lower(field: str, value: float) -> float:
            out.append(ParamConstraint(field, max=value, source="geometry", reason_ko=reason))
            fitted[field] = value
            return value

        d, t, slope = e.entrance_diameter_mm, e.wall_thickness_mm, e.roof_slope_deg
        run_max = (cap - 2 * t - door_top(d)) / rise_per_run(slope)
        if run_max < MIN_ROOF_RUN_MM - 1e-9:
            # 꼭대기 구멍을 가장 넓혀도 높다: 지붕 면은 5mm 만 남기고 지붕 경사 → 벽 두께 → 출입구 폭 순서로 줄인다
            run_max = MIN_ROOF_RUN_MM
            room = cap - 2 * t - door_top(d)  # 지붕이 쓸 수 있는 높이
            if room >= MIN_ROOF_RUN_MM * rise_per_run(slope_min) - 1e-9:
                tan_slope = room / (MIN_ROOF_RUN_MM * math.sqrt(2))
                slope = lower("roof_slope_deg", max(slope_min, _floor1(math.degrees(math.atan(tan_slope)))))
            else:
                if slope > slope_min:
                    slope = lower("roof_slope_deg", slope_min)
                room = cap - MIN_ROOF_RUN_MM * rise_per_run(slope) - door_top(d)  # 벽 두께 2배가 쓸 수 있는 높이
                if room >= 2 * t_min - 1e-9:
                    t = lower("wall_thickness_mm", max(t_min, _floor1(room / 2)))
                else:
                    if t > t_min:
                        t = lower("wall_thickness_mm", t_min)
                    room = cap - MIN_ROOF_RUN_MM * rise_per_run(slope) - 2 * t  # 출입구가 쓸 수 있는 높이
                    per_width = door_top(1.0)  # 출입구 높이 ÷ 폭
                    d = lower("entrance_diameter_mm", max(d_min, _floor1(room / per_width)))
        inner_short = min(e.width_mm, e.depth_mm) - 2 * t
        top_need = inner_short - 2 * run_max
        if top_need > MAX_TOP_OPENING_FIELD_MM + 1e-9:
            # 꼭대기 구멍은 필드 상한까지만 넓힐 수 있다: 짧은 변을 줄여 지붕 면 수평 거리를 맞춘다
            side = _floor1(MAX_TOP_OPENING_FIELD_MM + 2 * run_max + 2 * t)
            lower("width_mm" if e.width_mm <= e.depth_mm else "depth_mm", side)
            inner_short = side - 2 * t
            top_need = inner_short - 2 * run_max
        top = min(_ceil1(top_need), inner_short - TOP_RIM_MARGIN_MM)
        if top > e.top_opening_mm + 1e-9:
            out.append(ParamConstraint("top_opening_mm", min=top, source="geometry", reason_ko=reason))
            fitted["top_opening_mm"] = top
        return out, fitted

    def build(self, p: CaveParams) -> Part:
        W, D, H, t = p.width_mm, p.depth_mm, p.height_mm, p.wall_thickness_mm
        wi, di = inner_size(p)
        ai, bi = top_opening_inner(p)
        ao, bo = top_outer(p)
        z0, zt = eave_height(p), roof_top_height(p)

        # 바깥: 수직 벽(0 ~ 바깥 처마) + 사각뿔대 지붕(~ zt) + 수직 테두리(~ H). 단면을 직선으로 이어 한 덩어리로 만든다
        outer = loft([_rect_at(W, D, 0), _rect_at(W, D, outer_eave_height(p)), _rect_at(ao, bo, zt), _rect_at(ao, bo, H)],
                     ruled=True)
        # 안쪽: 바닥 아래(-CUT) ~ 처마 z0 수직, z0 ~ zt 경사 천장, zt ~ H+CUT 꼭대기 구멍 (위로 뚫린다)
        cavity = loft([_rect_at(wi, di, -_CUT), _rect_at(wi, di, z0), _rect_at(ai, bi, zt), _rect_at(ai, bi, H + _CUT)],
                      ruled=True)
        part = outer - cavity

        through = 2 * t + 2 * _CUT
        door = extrude(Plane.XZ * _door_profile(p.entrance_diameter_mm, -_CUT), amount=through / 2, both=True)
        for wall_y in door_wall_ys(p):
            part = part - Pos(0, wall_y, 0) * door
        return part

    def features(self, p: CaveParams) -> Features:
        two = p.entrance_count >= 2
        openings = [
            Opening("passage", p.entrance_diameter_mm, "앞 출입구" if two else "출입구",
                    rule_key="entrance_min_diameter_mm"),
        ]
        if two:
            openings.append(
                Opening("passage", p.entrance_diameter_mm, "뒤 출입구", rule_key="entrance_min_diameter_mm")
            )
        # 꼭대기 구멍도 몸이 드나들 수 있는 통로다: 끼임 구간을 피하도록 통과 폭(passable_min) 이상
        openings.append(Opening("passage", p.top_opening_mm, "꼭대기 구멍"))
        sides: tuple[Side, ...] = ("front", "back") if two else ("front",)
        return Features(
            min_wall_thickness_mm=p.wall_thickness_mm,
            openings=tuple(openings),
            access_sides=sides,
            entrance_count=p.entrance_count,
            extra={"air_release": "top_opening"},
        )
