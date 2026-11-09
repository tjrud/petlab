"""층 부품: 2층 층판과 오르는 수단.

2층이면 벽 안쪽에 선반(모따기 받침)을 두고 그 위에 층판을 따로 출력해 얹는다 (층판을 본체와 한 덩어리로 만들면
아랫면이 넓은 천장 오버행이 된다). 층판은 벽 안쪽 치수에 꼭 맞아 옆으로 움직이지 않는다.
  - internal_ramp: 뒷벽을 따라 안쪽에 경사로를 둔다 (본체와 한 덩어리). 층판은 경사로 띠를 덮지 않아 위가 트여 있고,
    경사로 꼭대기 발판이 층판과 같은 높이로 맞닿는다. 램프 템플릿처럼 미끄럼 방지 턱이 있다.
  - external_ramp: 2층 벽에 출입구를 내고 그 아래 바깥으로 착지판(porch)을 붙인다. 착지판은 바닥까지 꽉 찬 덩어리라
    아래에 끼임 틈이 없고, 벽 폭 전체를 차지해 램프가 어디에 닿아도 옆 틈이 생기지 않는다. 램프는 별도 항목(ramp)을
    attach_to 힌트로 붙인다.
선반의 아랫면은 50° 모따기라 본체를 바로 세워 출력할 때 오버행이 40° 다.
"""

from __future__ import annotations

import math
from typing import Literal

from build123d import Align, Box, Part, Plane, Polygon, Pos, extrude
from pydantic import Field

from app.templates.base import ParamConstraint, RuleContext, Side, TemplateParams
from app.templates.parts.common import MARGIN_MM, TIP_ANGLE_DEG, Shell

LEDGE_W_MM = 4.0       # 선반이 벽에서 튀어나오는 폭
LEDGE_FACE_MM = 3.0    # 선반 안쪽 세로면 높이 (칼날 모서리가 생기지 않게)
LEDGE_H_MM = LEDGE_FACE_MM + LEDGE_W_MM * math.tan(math.radians(TIP_ANGLE_DEG))  # 선반 전체 높이 (모따기 포함)
LANDING_MM = 40.0      # 내부 경사로 꼭대기 발판 길이 (램프 템플릿과 같다)
TOE_MM = 4.0           # 경사로 앞끝 두께
RIDGE_SPACING_MM = 15.0
RIDGE_WIDTH_MM = 4.0
RIDGE_RISE_MM = 1.5
PORCH_MM = 30.0        # 바깥 착지판 깊이


class FloorsPart(TemplateParams):
    count: Literal[1, 2] = Field(1, description="층 수. 2 면 벽 안쪽 선반 위에 층판(따로 출력)을 얹는다")
    level_height_mm: float = Field(
        100, ge=50, le=200, description="2층 바닥(층판 윗면) 높이 mm. 종별 오르는 높이 최대 이하 (2층일 때만)"
    )
    plate_thickness_mm: float = Field(3, ge=1.0, le=8, description="층판 두께 mm (2층일 때만)")
    climb: Literal["internal_ramp", "external_ramp"] = Field(
        "internal_ramp",
        description="2층 오르는 수단. internal_ramp=집 안 뒷벽을 따라 경사로 내장(한 구조물, 경사로 길이만큼 가로가 길어진다), "
                    "external_ramp=2층 측면 출입구 + 바깥 착지판, 램프는 별도 ramp 항목을 attach_to 로 붙인다 (2층일 때만)",
    )
    ramp_width_mm: float = Field(60, ge=40, le=150, description="내부 경사로 폭 mm. 몸이 지나갈 수 있는 폭 이상 (internal_ramp)")
    slope_deg: float = Field(25, ge=10, le=45, description="내부 경사로 경사각(도). 종별 최대 경사 이하 (internal_ramp)")
    exit_side: Side = Field(
        "back", description="바깥 램프가 닿는 2층 출입구 면 (external_ramp). 1층 출입구·연결부가 없는 면"
    )


def run_length(level: float, z_floor: float, slope_deg: float) -> float:
    """내부 경사로 경사 구간의 수평 길이."""
    return (level - z_floor - TOE_MM) / math.tan(math.radians(slope_deg))


def plate_bottom(f: FloorsPart) -> float:
    return f.level_height_mm - f.plate_thickness_mm


def ledge_bottom(f: FloorsPart) -> float:
    return plate_bottom(f) - LEDGE_H_MM


# ── 제약 ───────────────────────────────────────────────────


def floors_constraints(f: FloorsPart, ctx: RuleContext, shell_inset: float, t: float, z_floor: float,
                       ground_top: float, width_field_max: float) -> list[ParamConstraint]:
    """종 규칙(오르는 높이·경사·폭) + 부품 상호 제약(선반이 1층 개구부 위에 오도록, 경사로가 들어가도록)."""
    if f.count != 2:
        return []
    s = ctx.size
    P = s.gap_trap.passable_min_mm
    out = [
        ParamConstraint(
            "floors.level_height_mm", max=s.max_climb_height_mm, source="species",
            reason_ko=f"낙상 위험 때문에 {s.display_name}이(가) 오르는 2층 바닥은 {s.max_climb_height_mm:g}mm 이하여야 합니다",
        ),
        ParamConstraint(
            "floors.level_height_mm", min=ground_top + MARGIN_MM + LEDGE_H_MM + f.plate_thickness_mm,
            reason_ko="층판 선반이 1층 출입구·연결부 아치 위에 오도록 2층 바닥이 충분히 높아야 합니다",
        ),
    ]
    if f.climb == "internal_ramp":
        rise = max(f.level_height_mm - z_floor - TOE_MM, 1.0)
        out += [
            ParamConstraint(
                "floors.slope_deg", max=s.max_ramp_angle_deg, source="species",
                reason_ko=f"내부 경사로는 {s.max_ramp_angle_deg:g}° 이하로 완만해야 미끄러지지 않습니다",
            ),
            ParamConstraint(
                "floors.ramp_width_mm", min=P, source="species",
                reason_ko=f"몸이 지나갈 수 있도록 경사로 폭은 {P:g}mm 이상이어야 합니다",
            ),
            ParamConstraint(
                "width_mm", min=2 * (shell_inset + t) + run_length(f.level_height_mm, z_floor, f.slope_deg) + LANDING_MM,
                reason_ko="내부 경사로와 꼭대기 발판이 뒷벽을 따라 들어가도록 가로가 충분히 커야 합니다",
            ),
            ParamConstraint(
                # 가로를 최대로 늘려도 들어가지 않을 때만 경사를 세운다 (가로 보정이 먼저)
                "floors.slope_deg",
                min=math.degrees(math.atan(rise / max(width_field_max - 2 * (shell_inset + t) - LANDING_MM, 1.0))),
                reason_ko="가로를 최대로 해도 경사로가 들어가지 않아 경사를 더 세웠습니다",
            ),
            ParamConstraint(
                "depth_mm", min=2 * (shell_inset + t) + f.ramp_width_mm + P,
                reason_ko="경사로 앞 1층 바닥과 2층 층판에 몸이 지나갈 공간이 남도록 세로가 충분히 커야 합니다",
            ),
        ]
    return out


# ── 형상 ───────────────────────────────────────────────────


def _ledge_profile(z_top: float, tall: float = 0.0):
    """선반 단면 (가로 = 벽에서 안쪽으로, 세로 = Z). 윗면 수평, 안쪽 세로면, 아랫면 50° 모따기."""
    return Polygon(
        (0, z_top + tall), (LEDGE_W_MM, z_top + tall), (LEDGE_W_MM, z_top - LEDGE_FACE_MM), (0, z_top - LEDGE_H_MM),
        align=None,
    )


def _ledge(shell: Shell, side: Side, z_top: float, a0: float, a1: float) -> Part:
    """측면 벽 안쪽 면에 붙는 선반. a0~a1 은 벽에 평행한 축의 구간."""
    prof = _ledge_profile(z_top)
    if side in ("left", "right"):
        # 단면을 XZ 평면에 두고(가로=X) Y 방향으로 압출. 왼쪽 벽은 안쪽이 +X, 오른쪽 벽은 −X
        sign = 1.0 if side == "left" else -1.0
        solid = extrude(Plane.XZ * prof, amount=(a1 - a0) / 2, both=True)
        if sign < 0:
            solid = solid.mirror(Plane.YZ)
        return Pos(sign * -(shell.wx / 2 - shell.t), (a0 + a1) / 2, 0) * solid
    sign = 1.0 if side == "front" else -1.0
    solid = extrude(Plane.YZ * prof, amount=(a1 - a0) / 2, both=True)
    if sign < 0:
        solid = solid.mirror(Plane.XZ)
    return Pos((a0 + a1) / 2, sign * -(shell.wy / 2 - shell.t), 0) * solid


def plate_extent(f: FloorsPart, shell: Shell) -> tuple[float, float, float, float]:
    """층판의 (x0, x1, y0, y1). 내부 경사로면 뒷벽 쪽 경사로 띠는 덮지 않는다."""
    x0, x1 = -(shell.wx / 2 - shell.t), shell.wx / 2 - shell.t
    y0, y1 = -(shell.wy / 2 - shell.t), shell.wy / 2 - shell.t
    if f.climb == "internal_ramp":
        y1 -= f.ramp_width_mm
    return x0, x1, y0, y1


def ledges(f: FloorsPart, shell: Shell) -> Part:
    """층판을 받치는 선반: 왼쪽·오른쪽·앞 벽 (바깥 램프면 뒷벽도)."""
    x0, x1, y0, y1 = plate_extent(f, shell)
    zb = plate_bottom(f)
    out = _ledge(shell, "left", zb, y0, y1) + _ledge(shell, "right", zb, y0, y1) + _ledge(shell, "front", zb, x0, x1)
    if f.climb == "external_ramp":
        out = out + _ledge(shell, "back", zb, x0, x1)
    return out


def upper_plate(f: FloorsPart, shell: Shell) -> Part:
    x0, x1, y0, y1 = plate_extent(f, shell)
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, plate_bottom(f)) * Box(
        x1 - x0, y1 - y0, f.plate_thickness_mm, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )


def _ramp_profile(x0: float, x_top: float, x1: float, z_floor: float, level: float, slope_deg: float):
    """경사로 측면 단면 (가로 = X, 세로 = Z). 앞끝(x0) 에서 오르기 시작해 x_top 에서 발판 높이, x1 까지 발판."""
    tan = math.tan(math.radians(slope_deg))
    g = RIDGE_WIDTH_MM * tan + RIDGE_RISE_MM

    def slope_z(u: float) -> float:
        return z_floor + TOE_MM + (u - x0) * tan

    pts = [(x0, z_floor), (x0, z_floor + TOE_MM)]
    x = x0 + RIDGE_SPACING_MM
    while x + RIDGE_WIDTH_MM < x_top - 2 and slope_z(x) + g < level - 1:
        z = slope_z(x)
        pts += [(x, z), (x, z + g), (x + RIDGE_WIDTH_MM, z + g), (x + RIDGE_WIDTH_MM, slope_z(x + RIDGE_WIDTH_MM))]
        x += RIDGE_SPACING_MM
    pts += [(x_top, level), (x1, level), (x1, z_floor)]
    return Polygon(*pts, align=None)


def internal_ramp(f: FloorsPart, shell: Shell) -> Part:
    """뒷벽 안쪽을 따라 왼쪽에서 오른쪽으로 오르는 경사로 (오른쪽 벽에 닿는 발판까지). 바닥에 꽉 찬 쐐기."""
    x1 = shell.wx / 2 - shell.t
    x_top = x1 - LANDING_MM
    x0 = x_top - run_length(f.level_height_mm, shell.z_floor, f.slope_deg)
    prof = _ramp_profile(x0, x_top, x1, shell.z_floor, f.level_height_mm, f.slope_deg)
    # XZ 단면을 Y 방향으로 ramp_width 만큼 압출해 뒷벽 안쪽 면에 붙인다
    solid = extrude(Plane.XZ * prof, amount=f.ramp_width_mm / 2, both=True)
    return Pos(0, shell.wy / 2 - shell.t - f.ramp_width_mm / 2, 0) * solid


def porch(f: FloorsPart, shell: Shell) -> Part:
    """바깥 착지판: 2층 출입구 면 바깥에 벽 폭 전체·PORCH_MM 깊이·2층 바닥 높이의 꽉 찬 덩어리 (벽 안으로 조금 겹친다)."""
    side = f.exit_side
    length = shell.wall_length(side)
    depth = PORCH_MM + 0.5
    cx, cy = shell.wall_center(side)
    ox, oy = shell.outward(side)
    off = shell.t / 2 + depth / 2 - 0.5
    if side in ("front", "back"):
        box = Box(length, depth, f.level_height_mm, align=(Align.CENTER, Align.CENTER, Align.MIN))
    else:
        box = Box(depth, length, f.level_height_mm, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return Pos(cx + ox * off, cy + oy * off, 0) * box
