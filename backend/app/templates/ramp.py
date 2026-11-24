"""램프/계단 템플릿.

형상: 속이 찬 측면 단면을 폭 방향으로 압출. 꼭대기에 평평한 발판(TOP_LANDING_MM)이 있다.
  - 단 수 0: 경사로. 미끄럼 방지 턱(윗면이 수평인 작은 턱)을 일정 간격으로 둔다.
  - 단 수 ≥1: 계단. 단 높이 = 높이 / 단 수 (종별 최대 턱 높이 이하).
출력: 사용 자세 그대로 (바닥면이 베드). 모든 면이 수직·위를 향하거나 경사면(위 방향)이라 서포트가 필요 없다.
로컬 좌표: 오르는 방향 = +Y (입구 = 앞쪽 -Y), 폭 = X.
"""

from __future__ import annotations

import math
from typing import ClassVar

from build123d import Part, Plane, Polygon, extrude
from pydantic import Field

from app.templates.base import (
    Anchor,
    AttachKind,
    Features,
    ParamConstraint,
    RuleContext,
    Template,
    TemplateParams,
)

TOP_LANDING_MM = 40.0   # 꼭대기 발판 깊이
MIN_TREAD_MM = 20.0     # 계단 디딤판 최소 깊이
RIDGE_SPACING_MM = 15.0  # 미끄럼 방지 턱 간격 (수평)
RIDGE_WIDTH_MM = 4.0     # 턱 폭
RIDGE_RISE_MM = 1.5      # 경사면 대비 턱이 솟은 높이
TOE_MM = 4.0             # 경사로 앞끝 두께 (칼날처럼 얇아지면 출력·내구성이 나빠지므로 수직 앞면을 둔다)
# 조립 부품일 때 따로 출력하는 램프가 출력 공간(220mm)에 들어가는 경사: slope ≥ BED_SLOPE_PER_MM × 높이 + BED_SLOPE_BASE_DEG
BED_SLOPE_PER_MM = 0.2461
BED_SLOPE_BASE_DEG = 5.0


class RampParams(TemplateParams):
    height_mm: float = Field(60, ge=20, le=200, description="꼭대기 높이 mm")
    width_mm: float = Field(80, ge=40, le=250, description="폭 mm. 몸이 지나갈 수 있는 폭 이상")
    slope_deg: float = Field(25, ge=10, le=45, description="경사각(도). 계단이면 평균 경사")
    steps: int = Field(0, ge=0, le=12, description="계단 단 수. 0 이면 미끄럼 방지 턱이 있는 경사로")


def run_length(p: RampParams) -> float:
    """경사(또는 계단) 구간의 수평 길이. 경사로는 앞끝 두께(TOE_MM)만큼 낮은 곳에서 시작한다."""
    rise = p.height_mm - (TOE_MM if p.steps == 0 else 0.0)
    return rise / math.tan(math.radians(p.slope_deg))


def profile_points(p: RampParams) -> list[tuple[float, float]]:
    """측면 단면 (u=오르는 방향, v=높이) 꼭짓점."""
    H, L = p.height_mm, run_length(p)
    total = L + TOP_LANDING_MM
    if p.steps == 0:
        tan = math.tan(math.radians(p.slope_deg))
        g = RIDGE_WIDTH_MM * tan + RIDGE_RISE_MM  # 턱 윗면이 수평이 되도록 하는 높이

        def slope_z(u: float) -> float:
            return TOE_MM + u * tan

        pts = [(0.0, 0.0), (0.0, TOE_MM)]
        x = RIDGE_SPACING_MM
        while x + RIDGE_WIDTH_MM < L - 2 and slope_z(x) + g < H - 1:
            z = slope_z(x)
            pts += [(x, z), (x, z + g), (x + RIDGE_WIDTH_MM, z + g), (x + RIDGE_WIDTH_MM, slope_z(x + RIDGE_WIDTH_MM))]
            x += RIDGE_SPACING_MM
        pts += [(L, H), (total, H), (total, 0.0)]
        return pts
    n = p.steps
    run, rise = L / n, H / n
    pts = [(0.0, 0.0), (total, 0.0), (total, H)]
    for i in range(n, 0, -1):
        x = (i - 1) * run
        pts.append((x, i * rise))
        if i > 1:
            pts.append((x, (i - 1) * rise))
    return pts


def _signed_area(pts: list[tuple[float, float]]) -> float:
    """단면 다각형의 부호 있는 넓이 (반시계 > 0). build() 의 압출 방향(±X)이 이 부호를 따른다."""
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))


class RampTemplate(Template):
    key = "ramp"
    display_name_ko = "램프/계단"
    description_ko = (
        "꼭대기 발판이 있는 경사로 또는 계단. 높이, 폭, 경사각, 단 수(0=미끄럼 방지 턱이 있는 경사로)를 정한다. "
        "앞쪽이 오르는 입구다."
    )
    Params = RampParams
    height_field = "height_mm"
    size_fields = ("height_mm", "width_mm")
    # 연결 표준: 꼭대기 발판 끝면(landing)을 기준 구조물 옆면에 대고 슬라이드로 끼운다. 오르는 길이라 출입 면에 붙어도
    # 출입을 막지 않고(passes_access), 꼭대기 높이(height_mm)를 붙는 면 높이에 맞춘다(level_field)
    role = "accessory"
    attach_order: ClassVar[dict[AttachKind, tuple[str, ...]]] = {"slide": ("landing",)}
    passes_access = True
    level_field = "height_mm"

    def default_params(self, ctx: RuleContext | None = None) -> RampParams:
        if ctx is None:
            return RampParams()
        s = ctx.size
        return RampParams(
            height_mm=min(60.0, s.max_climb_height_mm),
            width_mm=float(math.ceil(s.gap_trap.passable_min_mm + 10)),
            slope_deg=min(25.0, s.max_ramp_angle_deg),
            steps=0,
        )

    def constraints(self, p: RampParams, ctx: RuleContext) -> list[ParamConstraint]:
        s = ctx.size
        out = [
            ParamConstraint(
                "height_mm", max=s.max_climb_height_mm, source="species",
                reason_ko=f"낙상 위험 때문에 {s.display_name}이(가) 오르는 구조물은 {s.max_climb_height_mm:g}mm 이하여야 합니다",
            ),
            ParamConstraint(
                "width_mm", min=s.gap_trap.passable_min_mm, source="species",
                reason_ko=f"몸이 지나갈 수 있도록 폭은 {s.gap_trap.passable_min_mm:g}mm 이상이어야 합니다",
            ),
        ]
        if p.steps == 0:
            out.append(ParamConstraint(
                "slope_deg", max=s.max_ramp_angle_deg, source="species",
                reason_ko=f"경사로는 {s.max_ramp_angle_deg:g}° 이하로 완만해야 미끄러지지 않습니다",
            ))
        else:
            out += [
                ParamConstraint(
                    "steps", min=math.ceil(p.height_mm / s.max_step_height_mm - 1e-9), source="species",
                    reason_ko=f"한 단 높이가 {s.max_step_height_mm:g}mm 를 넘지 않도록 단 수를 늘렸습니다",
                ),
                ParamConstraint(
                    "steps", max=max(1, math.floor(run_length(p) / MIN_TREAD_MM)),
                    reason_ko=f"디딤판 깊이가 {MIN_TREAD_MM:g}mm 이상이 되도록 단 수를 줄였습니다",
                ),
            ]
        return out

    def build(self, p: RampParams) -> Part:
        # YZ 평면(로컬 x→Y, y→Z)에 단면을 두고 +X 방향으로 폭만큼 압출
        return extrude(Plane.YZ * Polygon(*profile_points(p), align=None), amount=p.width_mm)

    def anchors(self, p: RampParams) -> dict[str, Anchor]:
        """연결 지점. build() 좌표: 오르는 방향 +Y (입구 끝 Y=0, 발판 끝 Y=전체 길이), 폭 X 는 [−W, 0] 또는 [0, W]
        (단면 꼭짓점이 도는 방향에 따라 압출 방향이 바뀐다: 경사로는 −X, 계단은 +X 쪽. build() 는 바꾸지 않는다).

          - landing: 꼭대기 발판 끝면 (법선 +Y). 벽에 기대는 면이라 은신처·집 벽 연결 지점에 이으면 발판이 벽에 맞닿는다
          - entry: 오르기 시작하는 앞끝 면 (법선 −Y, 출입 면 front). 여기에 무언가를 붙이면 입구가 그 부품 쪽으로 바뀐다
          - left / right: 평평한 옆면 (법선 −X / +X), 면의 가로 가운데
          - bottom: 밑면 (README 규칙: 법선 −Z, 위쪽 +Y). 경사·계단 윗면은 평평하지 않아 위에 얹는 자리(top)는 없다
        README 의 top/bottom 은 위·아래 면 이름이라 양 끝 세로면은 landing/entry 로 부른다.
        램프는 속이 찬 덩어리라 통로(port)·뚫을 벽(wall_mm)이 없다.
        """
        W, total = p.width_mm, run_length(p) + TOP_LANDING_MM
        x0 = 0.0 if _signed_area(profile_points(p)) > 0 else -W  # 폭의 왼쪽 끝 X
        xc = x0 + W / 2
        z = (0.0, 0.0, 1.0)
        return {
            "landing": Anchor((xc, total, 0.0), (0.0, 1.0, 0.0), z),
            "entry": Anchor((xc, 0.0, 0.0), (0.0, -1.0, 0.0), z, side="front"),
            "left": Anchor((x0, total / 2, 0.0), (-1.0, 0.0, 0.0), z),
            "right": Anchor((x0 + W, total / 2, 0.0), (1.0, 0.0, 0.0), z),
            "bottom": Anchor((xc, total / 2, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
        }

    # ── 연결 표준 (자유 조립) ──

    def envelope(self, p: RampParams) -> tuple[float, float, float]:
        # 측면 단면은 [0, 경사 길이 + 발판] × [0, 높이] 안에 꼭 차고, 폭 방향으로 압출한다
        return (p.width_mm, run_length(p) + TOP_LANDING_MM, p.height_mm)

    def assembly_constraints(self, p: RampParams, ctx: RuleContext) -> list[ParamConstraint]:
        """조립 부품인 램프는 따로 출력하므로 길이가 출력 공간에 들어가도록 경사를 높이에 맞춰 가파르게 한다
        (혼자 쓰는 램프는 지금처럼 이 제약이 없다). 그 경사가 종 최대 경사를 넘지 않도록 경사로 높이도 그만큼 낮춘다:
        조립 항목에서는 램프 높이가 붙는 면 높이를 따르므로 이 상한은 부모 면 높이로 옮겨진다 (compose.derived_constraints)."""
        out = [ParamConstraint(
            "slope_deg", min=BED_SLOPE_PER_MM * p.height_mm + BED_SLOPE_BASE_DEG, source="printing",
            reason_ko="따로 출력하는 경사로가 프린터 출력 공간에 들어가도록 경사를 가파르게 했습니다",
        )]
        if p.steps == 0:
            s = ctx.size
            h_max = (s.max_ramp_angle_deg - BED_SLOPE_BASE_DEG) / BED_SLOPE_PER_MM
            out.append(ParamConstraint(
                "height_mm", max=math.floor(h_max * 10) / 10, source="printing",
                reason_ko=f"따로 출력하는 경사로가 프린터 출력 공간에 들어가면서 {s.max_ramp_angle_deg:g}° 이하로 "
                          f"완만하려면 높이가 {math.floor(h_max * 10) / 10:g}mm 이하여야 합니다",
            ))
        return out

    def features(self, p: RampParams) -> Features:
        return Features(
            min_wall_thickness_mm=RIDGE_WIDTH_MM if p.steps == 0 else p.width_mm,
            access_sides=("front",),
            climb_height_mm=p.height_mm,
            slope_deg=p.slope_deg if p.steps == 0 else None,
            step_height_mm=p.height_mm / p.steps if p.steps > 0 else None,
        )
