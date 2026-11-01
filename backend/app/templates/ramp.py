"""램프/계단 템플릿.

형상: 속이 찬 측면 단면을 폭 방향으로 압출. 꼭대기에 평평한 발판(TOP_LANDING_MM)이 있다.
  - 단 수 0: 경사로. 미끄럼 방지 턱(윗면이 수평인 작은 턱)을 일정 간격으로 둔다.
  - 단 수 ≥1: 계단. 단 높이 = 높이 / 단 수 (종별 최대 턱 높이 이하).
출력: 사용 자세 그대로 (바닥면이 베드). 모든 면이 수직·위를 향하거나 경사면(위 방향)이라 서포트가 필요 없다.
로컬 좌표: 오르는 방향 = +Y (입구 = 앞쪽 -Y), 폭 = X.
"""

from __future__ import annotations

import math

from build123d import Part, Plane, Polygon, extrude
from pydantic import Field

from app.templates.base import Features, ParamConstraint, RuleContext, Template, TemplateParams

TOP_LANDING_MM = 40.0   # 꼭대기 발판 깊이
MIN_TREAD_MM = 20.0     # 계단 디딤판 최소 깊이
RIDGE_SPACING_MM = 15.0  # 미끄럼 방지 턱 간격 (수평)
RIDGE_WIDTH_MM = 4.0     # 턱 폭
RIDGE_RISE_MM = 1.5      # 경사면 대비 턱이 솟은 높이
TOE_MM = 4.0             # 경사로 앞끝 두께 (칼날처럼 얇아지면 출력·내구성이 나빠지므로 수직 앞면을 둔다)


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

    def features(self, p: RampParams) -> Features:
        return Features(
            min_wall_thickness_mm=RIDGE_WIDTH_MM if p.steps == 0 else p.width_mm,
            access_sides=("front",),
            climb_height_mm=p.height_mm,
            slope_deg=p.slope_deg if p.steps == 0 else None,
            step_height_mm=p.height_mm / p.steps if p.steps > 0 else None,
        )
