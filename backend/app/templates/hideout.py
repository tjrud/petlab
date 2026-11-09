"""은신처(하우스) 템플릿.

형상: 바닥이 열린 상자. 앞면(-Y)에 바닥에서 시작하는 아치형 출입구, 지붕에 수직 환기구.
  출입구가 2개면 뒷면(+Y)에 같은 아치를 마주 보게 낸다 (여러 마리가 함께 지낼 때 막다른 곳이 없도록).
출력: 지붕을 베드에 대고 뒤집어 출력한다.
  - 지붕 아랫면은 뒤집으면 바닥이 되므로 넓은 천장 브리지가 없다.
  - 아치 꼭대기는 뒤집으면 아래쪽 반원이 되므로 오버행이 없다.
  - 환기구는 수직 관통 구멍이라 오버행이 없다.
"""

from __future__ import annotations

import math

import numpy as np
from build123d import Align, Box, Cylinder, Part, Pos, Rot
from pydantic import Field

from app.templates.base import (
    DecorZone,
    Features,
    Opening,
    ParamConstraint,
    RuleContext,
    Template,
    TemplateParams,
)

DECOR_KEEPOUT_MM = 4.0   # 장식이 출입구·모서리·지붕판에서 떨어지는 거리
DECOR_MAX_DEPTH_MM = 1.0  # 장식 홈 깊이·돌기 높이 상한

_BOTTOM = (Align.CENTER, Align.CENTER, Align.MIN)
_CUT = 1.0  # 불리언 연산이 면과 정확히 겹치지 않도록 잘라내는 형상을 이만큼 연장


class HideoutParams(TemplateParams):
    width_mm: float = Field(140, ge=60, le=350, description="외형 가로(X) mm")
    depth_mm: float = Field(110, ge=60, le=350, description="외형 세로(Y) mm")
    height_mm: float = Field(90, ge=50, le=250, description="외형 높이(Z) mm")
    entrance_diameter_mm: float = Field(
        60, ge=25, le=150, description="아치형 출입구 폭(=높이) mm. 종별 최소값 이상"
    )
    entrance_count: int = Field(
        1, ge=1, le=2,
        description="출입구 개수. 1=앞면만, 2=앞·뒷면 마주 보기. 여러 마리를 함께 키우면 2 (종별 최소 개수 이상)",
    )
    vent_count: int = Field(6, ge=0, le=30, description="지붕 환기구 개수")
    vent_diameter_mm: float = Field(
        4, ge=2, le=10, description="환기구 지름 mm. 발이 끼지 않도록 종별 안전 틈새 이하"
    )
    wall_thickness_mm: float = Field(3, ge=1.0, le=8, description="벽·지붕 두께 mm")


def _vent_spacing(p: HideoutParams) -> float:
    """환기구 간격: 지붕 크기에 비례해 고르게 퍼지도록 하되 구멍 지름의 3배 이상, 25mm 이하."""
    margin = p.wall_thickness_mm + p.vent_diameter_mm
    inner_min = min(p.width_mm, p.depth_mm) - 2 * margin
    return max(3 * p.vent_diameter_mm, min(inner_min / 4, 25.0))


def _vent_grid_capacity(p: HideoutParams) -> tuple[int, int]:
    """지붕 안쪽 영역에 들어가는 환기구 최대 열·행 수."""
    s = _vent_spacing(p)
    margin = p.wall_thickness_mm + p.vent_diameter_mm
    lx = p.width_mm - 2 * margin
    ly = p.depth_mm - 2 * margin
    cols = int(lx // s) + 1 if lx >= 0 else 0
    rows = int(ly // s) + 1 if ly >= 0 else 0
    return cols, rows


def vent_positions(p: HideoutParams) -> list[tuple[float, float]]:
    """환기구 중심 좌표. 격자로 배치하고 마지막 행은 가운데 정렬한다."""
    n = p.vent_count
    if n == 0:
        return []
    max_cols, max_rows = _vent_grid_capacity(p)
    if max_cols * max_rows < n:
        raise ValueError("환기구 개수가 지붕 면적에 비해 많습니다")
    # 지붕 비율에 맞춰 열 수 결정
    cols = min(max_cols, max(1, math.ceil(math.sqrt(n * p.width_mm / p.depth_mm))))
    rows = math.ceil(n / cols)
    while rows > max_rows:
        cols += 1
        rows = math.ceil(n / cols)
    s = _vent_spacing(p)
    pts: list[tuple[float, float]] = []
    for r in range(rows):
        k = min(cols, n - r * cols)
        y = (r - (rows - 1) / 2) * s
        for c in range(k):
            x = (c - (k - 1) / 2) * s
            pts.append((x, y))
    return pts


class HideoutTemplate(Template):
    key = "hideout"
    display_name_ko = "은신처"
    description_ko = (
        "바닥이 열린 상자형 은신처. 앞면(과 뒷면)에 아치형 출입구, 지붕에 작은 환기구. "
        "가로·세로·높이, 출입구 폭·개수, 환기구 개수·지름, 벽 두께를 정한다."
    )
    Params = HideoutParams
    height_field = "height_mm"
    size_fields = ("width_mm", "depth_mm", "height_mm")
    # entrance_count 가 생기기 전에 저장된 은신처는 출입구가 앞면 하나였다
    legacy_defaults = {"entrance_count": 1}

    def default_params(self, ctx: RuleContext | None = None) -> HideoutParams:
        if ctx is None:
            return HideoutParams()
        s = ctx.size
        t = ctx.default_wall_mm
        d = float(math.ceil(s.entrance_min_diameter_mm + 5))
        return HideoutParams(
            width_mm=max(140.0, d + 4 * t + 50),
            depth_mm=max(110.0, d + 2 * t + 50),
            height_mm=max(90.0, d + 2 * t + 15),
            entrance_diameter_mm=d,
            entrance_count=min(2, ctx.hideout_min_entrances),
            vent_count=6,
            vent_diameter_mm=min(4.0, s.gap_trap.safe_max_mm),
            wall_thickness_mm=t,
        )

    def constraints(self, p: HideoutParams, ctx: RuleContext) -> list[ParamConstraint]:
        s = ctx.size
        t = max(p.wall_thickness_mm, ctx.min_wall_mm)
        d = max(p.entrance_diameter_mm, s.entrance_min_diameter_mm)
        cols, rows = _vent_grid_capacity(p)
        n_min = ctx.hideout_min_entrances
        group_rule = (
            [ParamConstraint(
                "entrance_count",
                min=n_min,
                source="species",
                reason_ko=f"{ctx.count}마리가 함께 지내면 서로 피할 수 있도록(막다른 곳 없이) "
                          f"은신처 출입구는 {n_min}개 이상이어야 합니다",
            )]
            if n_min > 1 else []
        )
        return group_rule + [
            ctx.wall_thickness_constraint(),
            ParamConstraint(
                "entrance_diameter_mm",
                min=s.entrance_min_diameter_mm,
                source="species",
                reason_ko=f"{s.display_name} 출입구는 최소 {s.entrance_min_diameter_mm:g}mm 이상이어야 합니다",
            ),
            ParamConstraint(
                "vent_diameter_mm",
                max=s.gap_trap.safe_max_mm,
                source="species",
                reason_ko=f"환기구 지름이 {s.gap_trap.safe_max_mm:g}mm 를 넘으면 발이 낄 수 있습니다",
            ),
            ParamConstraint(
                "width_mm",
                min=d + 4 * t,
                reason_ko="출입구 양옆에 벽이 남도록 가로가 출입구 폭보다 충분히 커야 합니다",
            ),
            ParamConstraint(
                "depth_mm",
                min=d + 2 * t,
                reason_ko="내부 공간 확보를 위해 세로가 출입구 폭보다 커야 합니다",
            ),
            ParamConstraint(
                "height_mm",
                min=d + 2 * t,
                reason_ko="출입구 아치 위로 벽이 남도록 높이가 출입구보다 커야 합니다",
            ),
            ParamConstraint(
                "vent_count",
                max=cols * rows,
                reason_ko=f"현재 지붕 크기에는 환기구를 최대 {cols * rows}개까지 낼 수 있습니다",
            ),
        ]

    def build(self, p: HideoutParams) -> Part:
        W, D, H, t = p.width_mm, p.depth_mm, p.height_mm, p.wall_thickness_mm
        r = p.entrance_diameter_mm / 2

        outer = Box(W, D, H, align=_BOTTOM)
        cavity = Pos(0, 0, -_CUT) * Box(W - 2 * t, D - 2 * t, H - t + _CUT, align=_BOTTOM)
        part = outer - cavity

        # 아치형 출입구: 바닥~반지름 높이의 직사각형 + 반지름 높이에 중심을 둔 원기둥 (전체 높이 = 지름)
        through = 2 * t + 2 * _CUT
        walls_y = (-D / 2 + t / 2, D / 2 - t / 2)[: p.entrance_count]  # 앞면, (뒷면)
        for wall_y in walls_y:
            door_rect = Pos(0, wall_y, -_CUT) * Box(2 * r, through, r + _CUT, align=_BOTTOM)
            door_arch = Pos(0, wall_y, r) * Rot(90, 0, 0) * Cylinder(r, through)
            part = part - door_rect - door_arch

        # 지붕 환기구
        for x, y in vent_positions(p):
            part = part - Pos(x, y, H - t / 2) * Cylinder(p.vent_diameter_mm / 2, t + 2 * _CUT)
        return part

    def print_rotation(self, p: HideoutParams) -> np.ndarray:
        # X 축 기준 180° 회전: 지붕이 베드에 닿도록 뒤집는다.
        return np.diag([1.0, -1.0, -1.0])

    def decor_zones(self, p: HideoutParams) -> list[DecorZone]:
        """바깥 벽 네 면 (파내기·돋을새김). 지붕 윗면은 뒤집어 출력할 때 베드에 닿는 면이라 홈 바닥이 오버행이 되어 뺀다."""
        W, D, H, t = p.width_mm, p.depth_mm, p.height_mm, p.wall_thickness_mm
        r = p.entrance_diameter_mm / 2
        door = (-r, 0.0, r, 2 * r)
        zones = []
        for face, length, surface, has_door in (
            ("front", W, (0.0, -D / 2, 0.0), True),
            ("back", W, (0.0, D / 2, 0.0), p.entrance_count >= 2),
            ("left", D, (-W / 2, 0.0, 0.0), False),
            ("right", D, (W / 2, 0.0, 0.0), False),
        ):
            zones.append(DecorZone(
                face=face, mode="relief", max_depth_mm=DECOR_MAX_DEPTH_MM, keepout_mm=DECOR_KEEPOUT_MM,
                u0=-length / 2, u1=length / 2, v0=0.0, v1=H - t, obstacles=(door,) if has_door else (),
                part_key="body", print_inverted=True, thickness_field="wall_thickness_mm", surface=surface,
            ))
        return zones

    def features(self, p: HideoutParams) -> Features:
        two = p.entrance_count >= 2
        openings = [
            Opening("passage", p.entrance_diameter_mm, "앞 출입구" if two else "출입구",
                    rule_key="entrance_min_diameter_mm"),
        ]
        if two:
            openings.append(
                Opening("passage", p.entrance_diameter_mm, "뒤 출입구", rule_key="entrance_min_diameter_mm")
            )
        if p.vent_count > 0:
            openings.append(Opening("vent", p.vent_diameter_mm, "환기구"))
        return Features(
            min_wall_thickness_mm=p.wall_thickness_mm,
            openings=tuple(openings),
            # 출입구마다 앞이 비어 있어야 한다 (벽에 붙은 뒷문은 막다른 곳이 된다)
            access_sides=("front", "back") if two else ("front",),
            entrance_count=p.entrance_count,
        )
