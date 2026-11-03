"""모래목욕통 템플릿.

형상: 위가 열린 상자. 앞면(-Y) 가운데에 턱 높이까지 낮춘 출입 홈.
출력: 사용 자세 그대로 (바닥이 베드). 홈은 위에서 파낸 형태라 오버행이 없다.
"""

from __future__ import annotations

import math

from build123d import Align, Box, Part, Pos
from pydantic import Field

from app.templates.base import (
    Features,
    Opening,
    ParamConstraint,
    RuleContext,
    Template,
    TemplateParams,
)

ENTRY_RATIO = 0.5  # 출입 홈 폭 = 안쪽 가로의 비율
_BOTTOM = (Align.CENTER, Align.CENTER, Align.MIN)
_CUT = 1.0


class SandBathParams(TemplateParams):
    width_mm: float = Field(216, ge=100, le=350, description="외형 가로(X) mm")
    depth_mm: float = Field(216, ge=80, le=300, description="외형 세로(Y) mm")
    basin_depth_mm: float = Field(55, ge=20, le=120, description="안쪽 깊이 mm (바닥판 위 벽 높이)")
    lip_height_mm: float = Field(
        30, ge=8, le=100, description="출입 홈의 턱 높이 mm (바깥 바닥 기준). 종별 최대 턱 높이 이하"
    )
    wall_thickness_mm: float = Field(3, ge=1.0, le=8, description="벽·바닥 두께 mm")


def entry_width(p: SandBathParams) -> float:
    return ENTRY_RATIO * (p.width_mm - 2 * p.wall_thickness_mm)


class SandBathTemplate(Template):
    key = "sand_bath"
    display_name_ko = "모래목욕통"
    description_ko = (
        "위가 열린 상자형 모래목욕통. 앞면 가운데에 넘어 들어가는 낮은 턱(출입 홈)이 있다. "
        "가로·세로, 안쪽 깊이, 턱 높이, 벽 두께를 정한다."
    )
    Params = SandBathParams
    height_field = None
    size_fields = ("width_mm", "depth_mm")

    def default_params(self, ctx: RuleContext | None = None) -> SandBathParams:
        if ctx is None:
            return SandBathParams()
        s = ctx.size
        t = ctx.default_wall_mm
        iw, il = s.sand_bath_min_inner_mm
        return SandBathParams(
            width_mm=float(math.ceil(iw + 10 + 2 * t)),
            depth_mm=float(math.ceil(il + 10 + 2 * t)),
            basin_depth_mm=float(math.ceil(s.sand_bath_min_depth_mm + 10)),
            lip_height_mm=min(s.max_step_height_mm, t + 25),
            wall_thickness_mm=t,
        )

    def constraints(self, p: SandBathParams, ctx: RuleContext) -> list[ParamConstraint]:
        s = ctx.size
        t = max(p.wall_thickness_mm, ctx.min_wall_mm)
        iw, il = s.sand_bath_min_inner_mm
        P = s.gap_trap.passable_min_mm
        return [
            ctx.wall_thickness_constraint(),
            ParamConstraint(
                "width_mm", min=max(iw, P / ENTRY_RATIO) + 2 * t, source="species",
                reason_ko=f"{s.display_name}이(가) 뒹굴 수 있도록 안쪽 가로를 {iw:g}mm 이상, 출입 홈을 {P:g}mm 이상으로 맞췄습니다",
            ),
            ParamConstraint(
                "depth_mm", min=il + 2 * t, source="species",
                reason_ko=f"{s.display_name}이(가) 뒹굴 수 있도록 안쪽 세로는 {il:g}mm 이상이어야 합니다",
            ),
            ParamConstraint(
                "basin_depth_mm", min=s.sand_bath_min_depth_mm, source="species",
                reason_ko=f"모래가 흩어지지 않도록 안쪽 깊이는 {s.sand_bath_min_depth_mm:g}mm 이상이어야 합니다",
            ),
            ParamConstraint(
                "lip_height_mm", max=s.max_step_height_mm, source="species",
                reason_ko=f"{s.display_name}이(가) 넘어 들어갈 수 있도록 턱 높이는 {s.max_step_height_mm:g}mm 이하여야 합니다",
            ),
            ParamConstraint(
                "lip_height_mm", min=t + 5,
                reason_ko="모래가 쏟아지지 않도록 턱은 바닥판보다 5mm 이상 높아야 합니다",
            ),
            ParamConstraint(
                "lip_height_mm", max=p.basin_depth_mm + t,
                reason_ko="턱 높이는 벽 높이를 넘을 수 없습니다",
            ),
        ]

    def build(self, p: SandBathParams) -> Part:
        W, D, t = p.width_mm, p.depth_mm, p.wall_thickness_mm
        H = p.basin_depth_mm + t
        part = Box(W, D, H, align=_BOTTOM)
        part = part - Pos(0, 0, t) * Box(W - 2 * t, D - 2 * t, H, align=_BOTTOM)
        # 앞면 출입 홈: 턱 높이부터 위쪽을 파낸다
        notch_h = H - p.lip_height_mm
        if notch_h > 0:
            part = part - Pos(0, -D / 2 + t / 2, p.lip_height_mm) * Box(
                entry_width(p), t + 2 * _CUT, notch_h + _CUT, align=_BOTTOM
            )
        return part

    def features(self, p: SandBathParams) -> Features:
        return Features(
            min_wall_thickness_mm=p.wall_thickness_mm,
            openings=(Opening("passage", entry_width(p), "출입 홈"),),
            access_sides=("front",),
            step_height_mm=p.lip_height_mm,
        )
