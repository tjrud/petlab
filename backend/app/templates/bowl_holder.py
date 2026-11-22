"""그릇 받침 템플릿 (모듈 라이브러리 부품).

시중 사기·스테인리스 밥그릇을 끼워 두는 받침. 3D 출력한 그릇은 적층 틈에 음식 찌꺼기가 끼어 위생에 좋지 않으므로
그릇은 사서 쓰고, 받침은 그릇이 엎어지거나 밀려나지 않게 잡아 준다. 모듈에서는 은신처 옆에 그릇 자리를 붙이는 데 쓴다.

형상 (사용 자세, 바닥 Z=0, 그릇 중심 = XY 원점):
  - 'D' 모양 바닥: 앞(-Y)은 반원, 뒤(+Y)는 직사각형이라 평평한 뒷면(+Y)을 다른 부품 벽에 틈 없이 맞댈 수 있다.
    뒤쪽 세로 모서리는 작게 둥글린다 (BACK_CORNER_R, 벽에 맞댔을 때 생기는 쐐기 틈이 끼임 안전 기준보다 작게).
  - 그릇 자리: 바닥판(두께 = 벽 두께) 위에 그릇 지름 + 틈새(clearance) 의 원형 홈. 홈 바닥이 평평해 그릇이 수평으로 앉는다.
  - 턱(collar): 그릇을 둘러싸는 벽. 그릇 높이보다 낮아 그릇 테두리를 높이지 않는다 (동물은 그릇 테두리 너머로 먹는다).
  - 윗모서리: 바깥은 둥글게(TOP_OUTER_R), 안쪽은 아주 작게(TOP_INNER_R) 둥글린다. 안쪽 둥글림은 그릇과의 틈을
    위쪽에서 그만큼 넓힌다.
  - 그릇은 홈 안에서 움직이므로 한쪽 벽에 밀리면 반대쪽 틈은 틈새의 두 배가 된다. 그래서 가장 넓은 틈
    2 × 틈새 + TOP_INNER_R 이 끼임 안전 기준 이하가 되도록 제약한다 (bowl_gap_top_mm).
그릇과 턱 사이 틈새가 유일한 틈이며, 닫힌 빈 공간은 없다.
그릇 지름은 턱 꼭대기 높이에서 잰다. 아래가 넓은 그릇(바닥이 퍼진 무거운 사기 그릇 등)은 가장 넓은 곳에 맞춘 홈이
턱 꼭대기에서 그릇보다 훨씬 넓어 끼임 틈이 생기므로 쓸 수 없다 (형상이 그릇 모양을 모르므로 설명으로만 막는다).
출력: 사용 자세 그대로 (바닥판이 베드). 세로 벽·위로 볼록한 둥글림뿐이라 오버행이 없다.
연결 지점: back(평평한 뒷면), bottom(밑면). 옆면은 뒤쪽 절반만 평평하고 앞쪽은 반원이라, 옆면에 붙이면 반원과 상대 벽
사이에 0에서 시작해 넓어지는 쐐기 틈(끼임 위험)이 생기므로 left/right 는 두지 않는다.
"""

from __future__ import annotations

import numpy as np
from build123d import (
    Align,
    Axis,
    Circle,
    Cylinder,
    Part,
    Pos,
    Rectangle,
    extrude,
    fillet,
)
from pydantic import Field

from app.templates.base import (
    Anchor,
    Features,
    ParamConstraint,
    RuleContext,
    Template,
    TemplateParams,
)

_CUT = 1.0
BACK_CORNER_R = 2.5  # 뒤쪽 세로 모서리 둥글림 (벽에 맞댄 쐐기 틈 최대 폭)
TOP_OUTER_R = 1.5    # 윗면 바깥 모서리 둥글림 상한
TOP_INNER_R = 0.5    # 윗면 안쪽(그릇 쪽) 모서리 둥글림. 그릇과의 틈이 위에서 이만큼 넓어진다
COLLAR_BELOW_RIM_MM = 5.0  # 턱 꼭대기가 그릇 테두리보다 최소 이만큼 낮아야 한다
COLLAR_DEFAULT_RATIO = 0.6  # 기본 턱 높이 = 그릇 높이 × 이 비율


class BowlHolderParams(TemplateParams):
    bowl_diameter_mm: float = Field(
        90, ge=60, le=160,
        description="그릇 바깥 지름 mm. 턱 꼭대기 높이에서 잰 지름 (곧은 그릇은 테두리 지름). 그 아래에 이보다 넓은 곳이 있는 그릇(아래가 넓은 그릇)은 턱 위쪽 틈이 넓어져 쓸 수 없다",
    )
    bowl_height_mm: float = Field(45, ge=35, le=80, description="그릇 높이 mm (바닥~테두리)")
    clearance_mm: float = Field(
        1.0, ge=0.5, le=2.0,
        description="그릇과 받침 벽 사이 한쪽 틈새 mm. 그릇이 한쪽으로 밀리면 반대쪽 틈은 두 배가 되므로 종별 안전 틈새의 절반 이하",
    )
    wall_thickness_mm: float = Field(3, ge=1.0, le=8, description="벽·바닥판 두께 mm")
    collar_height_mm: float = Field(
        27, ge=10, le=75,
        description="그릇을 둘러싸는 턱 높이 mm (바닥판 위). 그릇 테두리보다 5mm 이상 낮게",
    )


def seat_radius(p: BowlHolderParams) -> float:
    """그릇 자리(홈) 반지름."""
    return p.bowl_diameter_mm / 2 + p.clearance_mm


def outer_radius(p: BowlHolderParams) -> float:
    """바깥 반원 반지름 = 외형 가로의 절반 = 그릇 중심에서 뒷면까지 거리."""
    return seat_radius(p) + p.wall_thickness_mm


def total_height(p: BowlHolderParams) -> float:
    return p.wall_thickness_mm + p.collar_height_mm


def _top_outer_r(p: BowlHolderParams) -> float:
    return max(0.2, min(TOP_OUTER_R, p.wall_thickness_mm - TOP_INNER_R - 0.3))


class BowlHolderTemplate(Template):
    key = "bowl_holder"
    display_name_ko = "그릇 받침"
    description_ko = (
        "시중 사기·스테인리스 밥그릇을 끼워 두는 받침. 3D 출력한 그릇은 적층 틈에 음식 찌꺼기가 끼어 위생에 좋지 않아 "
        "그릇은 사서 쓰고, 받침은 그릇이 엎어지거나 밀려나지 않게 잡아 준다. 뒷면이 평평해 은신처 벽 등에 붙일 수 있다. "
        "곧은 그릇이나 위가 넓은 그릇용이다 (아래가 넓은 그릇은 턱 위쪽 틈이 넓어진다). "
        "그릇 지름·높이, 틈새, 턱 높이, 벽 두께를 정한다."
    )
    Params = BowlHolderParams
    height_field = None  # 높이는 턱 높이로 정해지며 낮다 (그릇 자체는 형상에 없다)
    size_fields = ()     # 크기는 실제 그릇에 맞춰야 하므로 공간이 부족해도 줄이지 않는다
    color = None

    def default_params(self, ctx: RuleContext | None = None) -> BowlHolderParams:
        if ctx is None:
            return BowlHolderParams()
        safe = ctx.size.gap_trap.safe_max_mm
        return BowlHolderParams(
            clearance_mm=max(0.5, min(1.0, max_clearance_mm(safe))),
            wall_thickness_mm=ctx.default_wall_mm,
            collar_height_mm=round(COLLAR_DEFAULT_RATIO * 45.0),
        )

    def constraints(self, p: BowlHolderParams, ctx: RuleContext) -> list[ParamConstraint]:
        safe = ctx.size.gap_trap.safe_max_mm
        return [
            ctx.wall_thickness_constraint(),
            ParamConstraint(
                "clearance_mm",
                max=max_clearance_mm(safe),
                source="species",
                reason_ko=f"그릇이 한쪽으로 밀리면 반대쪽 틈이 틈새의 두 배가 됩니다. 그 틈이 {safe:g}mm 를 넘으면 발가락이 낄 수 있습니다",
            ),
            ParamConstraint(
                "collar_height_mm",
                max=p.bowl_height_mm - COLLAR_BELOW_RIM_MM,
                reason_ko=f"받침 턱이 그릇 테두리보다 {COLLAR_BELOW_RIM_MM:g}mm 이상 낮아야 그릇 안의 먹이에 닿기 쉽습니다",
            ),
        ]

    def build(self, p: BowlHolderParams) -> Part:
        Ro, Rs, t = outer_radius(p), seat_radius(p), p.wall_thickness_mm
        H = total_height(p)
        # 'D' 바닥: 반원(앞) + 직사각형(뒤, y = 0 ~ Ro)
        outline = Circle(Ro) + Pos(0, Ro / 2) * Rectangle(2 * Ro, Ro)
        part = extrude(outline, amount=H)
        back_corners = part.edges().filter_by(Axis.Z).filter_by(lambda e: e.center().Y > Ro - 1e-3)
        part = fillet(back_corners, BACK_CORNER_R)
        # 그릇 자리
        part = part - Pos(0, 0, t) * Cylinder(Rs, H - t + _CUT, align=(Align.CENTER, Align.CENTER, Align.MIN))
        # 윗모서리 둥글림 (바깥·안쪽 따로)
        top = part.faces().sort_by(Axis.Z)[-1]
        part = fillet(top.outer_wire().edges(), _top_outer_r(p))
        top = part.faces().sort_by(Axis.Z)[-1]
        inner = [e for w in top.inner_wires() for e in w.edges()]
        part = fillet(inner, TOP_INNER_R)
        return part

    def anchors(self, p: BowlHolderParams) -> dict[str, Anchor]:
        Ro = outer_radius(p)
        return {
            # 평평한 뒷면(+Y)의 아래쪽 가운데. 벽 쪽으로 붙이는 자리 (뚫을 수 없는 면, 통로 아님)
            "back": Anchor((0.0, Ro, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            "bottom": Anchor((0.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
        }

    def print_rotation(self, p: BowlHolderParams) -> np.ndarray:
        return np.eye(3)  # 바닥판이 베드에 닿는 사용 자세 그대로

    def features(self, p: BowlHolderParams) -> Features:
        return Features(
            min_wall_thickness_mm=p.wall_thickness_mm,
            # 동물이 앞(-Y, 반원 쪽)에서 그릇에 다가가므로 앞을 비워 둔다. 뒷면은 벽에 붙이는 면
            access_sides=("front",),
            extra={
                "bowl_diameter_mm": p.bowl_diameter_mm,
                "bowl_height_mm": p.bowl_height_mm,
                "seat_diameter_mm": 2 * seat_radius(p),
            },
        )


def bowl_gap_top_mm(p: BowlHolderParams) -> float:
    """턱 꼭대기에서 그릇과 받침 사이 가장 넓은 틈: 그릇이 한쪽 벽에 밀렸을 때 반대쪽 (안쪽 둥글림 포함)."""
    return 2 * p.clearance_mm + TOP_INNER_R


def max_clearance_mm(safe_max_mm: float) -> float:
    """가장 넓은 틈(bowl_gap_top_mm)이 끼임 안전 기준 safe_max_mm 이하가 되는 최대 틈새."""
    return (safe_max_mm - TOP_INNER_R) / 2

