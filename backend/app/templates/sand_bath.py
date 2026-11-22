"""모래목욕통 템플릿.

형상: 위가 열린 상자. 앞면(-Y) 가운데에 턱 높이까지 낮춘 출입 홈.
출력: 사용 자세 그대로 (바닥이 베드). 홈은 위에서 파낸 형태라 오버행이 없다.
"""

from __future__ import annotations

import math

from build123d import Align, Box, Part, Pos
from pydantic import Field

from app.templates.base import (
    Anchor,
    FaceFields,
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
    # 연결 표준: 옆면에 받침·램프를 다는 기준 구조물 (통로가 없어 터널로 잇지 않고, 다른 부품에 붙지도 않는다)
    role = "host"

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

    def anchors(self, p: SandBathParams) -> dict[str, Anchor]:
        """옆면 네 개(바닥 높이, 면 가운데)와 밑면. 위는 열려 있어 얹는 자리(top)가 없다.

        앞면(front)의 출입 홈은 위가 트인 턱이라 통로(port)로 두지 않는다: 통로 연결(passage)은 벽을 바닥부터 뚫는데,
        그러면 모래가 쏟아지고 턱의 의미가 없어진다. 같은 이유로 어느 벽도 뚫을 수 없다(wall_mm 없음).
        앞면은 출입 면이라 side="front": 여기에 램프·계단을 붙이면(턱까지 오르는 발판) 출입 면이 그 부품으로 넘어간다.
        앞면을 출입구 없는 벽으로 막으면 들어갈 수 없게 되므로 모듈에서 그렇게 잇지 않는다.

        슬라이드 결합 연결판 자리(mount): 뒤·왼쪽·오른쪽은 면 전체 (가로 전체 × 벽 높이 = 안쪽 깊이 + 바닥 두께).
        앞면은 가로 전체 × 턱 높이까지: 출입 홈은 턱 높이부터 위가 파여 있어, 연결판(경사 끝 포함)이 턱 높이 아래에서
        끝나면 홈을 덮지 않는다. 앞면에 턱 높이 램프를 슬라이드로 붙이면 연결판 경사 끝이 턱 윗면 높이에서 벽에 닿는다.
        """
        W, D = p.width_mm, p.depth_mm
        H = p.basin_depth_mm + p.wall_thickness_mm
        z, up = (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)
        return {
            "front": Anchor((0.0, -D / 2, 0.0), (0.0, -1.0, 0.0), z, side="front",
                            mount=(-W / 2, W / 2, p.lip_height_mm)),
            "back": Anchor((0.0, D / 2, 0.0), (0.0, 1.0, 0.0), z, mount=(-W / 2, W / 2, H)),
            "left": Anchor((-W / 2, 0.0, 0.0), (-1.0, 0.0, 0.0), z, mount=(-D / 2, D / 2, H)),
            "right": Anchor((W / 2, 0.0, 0.0), (1.0, 0.0, 0.0), z, mount=(-D / 2, D / 2, H)),
            "bottom": Anchor((0.0, 0.0, 0.0), (0.0, 0.0, -1.0), up),
        }

    # ── 연결 표준 (자유 조립) ──

    def face_fields(self, p: SandBathParams, anchor: str) -> FaceFields:
        """옆면 가로는 왼쪽·오른쪽 = 세로(depth), 앞·뒤 = 가로(width). 앞면 연결판 높이 = 턱 높이 (램프 꼭대기가
        여기에 맞춰진다). 나머지 면의 높이(안쪽 깊이 + 바닥)는 모래가 흩어지지 않는 깊이라 면 높이로 바꾸지 않는다.
        어느 벽도 뚫지 않으므로 벽·통로는 없다."""
        if anchor in ("left", "right"):
            return FaceFields(width="depth_mm")
        if anchor == "back":
            return FaceFields(width="width_mm")
        if anchor == "front":
            return FaceFields(width="width_mm", height="lip_height_mm")
        return FaceFields()

    def envelope(self, p: SandBathParams) -> tuple[float, float, float]:
        # 출입 홈은 앞면 가운데를 위에서 파내므로 바깥 상자의 모서리는 그대로다
        return (p.width_mm, p.depth_mm, p.basin_depth_mm + p.wall_thickness_mm)

    def features(self, p: SandBathParams) -> Features:
        return Features(
            min_wall_thickness_mm=p.wall_thickness_mm,
            openings=(Opening("passage", entry_width(p), "출입 홈"),),
            access_sides=("front",),
            step_height_mm=p.lip_height_mm,
        )
