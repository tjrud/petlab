"""물병 거치대 템플릿 (모듈 라이브러리 부품).

시중 햄스터 급수기(급수관이 달린 물병)를 똑바로 세워 두는 받침. 철망에 걸 수 없는 케이지(유리 수조형 등)에서 쓰고,
모듈에서는 은신처 옆면에 붙인다. 물병은 마개(급수관)를 아래로 하여 위에서 컵에 꽂는다.

형상 (사용 자세, 바닥 Z=0, 바닥판 중심 = XY 원점, 앞 = -Y 가 마시는 쪽):
  - 바닥판: base_width × base_depth, 두께 max(벽 두께, BASE_MIN_MM). 앞 세로 모서리는 둥글게, 윗모서리는 모따기.
  - 뒤판: 바닥판 뒤 끝(+Y)에 서는 판 (폭 = 컵 바깥 지름, 두께 max(벽 두께, BACK_MIN_MM)). 뒷면은 평평해 다른 부품 벽에
    맞댄다. 뒤쪽 세로 모서리는 BACK_CORNER_R 로 둥글린다 (벽에 맞댔을 때 생기는 쐐기 틈이 끼임 안전 기준보다 작게).
  - 컵: 뒤판 앞에 붙은 'D' 모양 기둥에 물병 자리(지름 + 틈새)를 판 것. 밑은 깔때기(원뿔)로 좁아지며 마개 지름 + 틈새의
    구멍으로 끝난다. 물병 어깨가 깔때기에 앉고 마개·급수관은 구멍 아래로 나온다. 컵은 물병 몸통을 360° 감싸며
    (틈 = 틈새), 마개와 구멍 사이 틈도 틈새와 같다. 물병이 한쪽으로 밀리면 반대쪽 틈은 틈새의 2배가 되므로
    틈새 상한은 (안전 틈새 − 입구·구멍 모따기) ÷ 2 다. 앞 슬롯은 두지 않는다 (급수관 폭의 슬롯은 끼임 위험 폭이다).
    컵 밑 끝은 벽 두께 폭의 평평한 고리와 벽 두께 높이의 세로 구멍 벽 (날이 서지 않게).
    급수관이 휜 물병은 급수관 끝부터 비스듬히 구멍에 넣고 세운다 (안 되면 마개를 풀고 컵 아래에서 다시 끼운다).
    물병을 뺀 빈 컵은 동물이 들어갈 수 있는 고리라 물병을 늘 꽂아 둔다 (물을 갈 때만 잠깐 뺀다).
  - 컵 바깥 밑면은 원뿔(깔때기와 나란히)이고, 뒤판 옆 'D' 모서리는 원뿔이 뒤판에 닿는 높이에서 평평하다.
  - 컵 아래는 비워 둔다: 급수관 앞·아래에 아무것도 없어 동물이 바닥판 위에 서서 급수관 끝에 입을 댈 수 있다.
    바닥판 윗면 ~ 컵 밑 높이는 통과 기준(passable_min) 이상으로 제약해 끼임 위험 높이의 선반 틈이 생기지 않게 한다.
출력: 두 파트를 따로 출력해 끼운다 (결합부는 설계상 밀착, 집 템플릿과 같은 방식).
  - 받침판: 바닥판 + 뒤판 발을 끼우는 'U' 소켓 (앞·양옆 벽, 뒤는 트여 뒷면이 평평하게 이어진다). 사용 자세 그대로.
  - 물병 컵: 뒤판 + 컵. 뒤집어 컵 입구·뒤판 꼭대기를 베드에 댄다. 바깥 원뿔·밑 고리는 위를 보고, 안쪽 깔때기는
    수직에서 90 − FUNNEL_DEG 기운 면이라 서포트가 필요 없다. 한 덩어리로 세워 출력하면 컵 밑 고리가 뒤판에 닿기 전
    허공에서 시작하는 섬이 되어 서포트 없이는 출력할 수 없다 (면 기울기만 보는 오버행 검사에는 걸리지 않는다).
연결 지점: back(뒤판 뒷면, 바닥 높이), bottom(밑면). 통로·출입구는 없다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from build123d import (
    Align,
    Axis,
    Box,
    Circle,
    Part,
    Plane,
    Polygon,
    Pos,
    Rectangle,
    chamfer,
    extrude,
    fillet,
    revolve,
)
from pydantic import Field

from app.templates.base import (
    Anchor,
    Features,
    ParamConstraint,
    PrintPart,
    RuleContext,
    Template,
    TemplateParams,
)

_BOTTOM = (Align.CENTER, Align.CENTER, Align.MIN)
_CUT = 1.0
FUNNEL_DEG = 55.0       # 깔때기 면의 수평 기준 경사 (출력 최대 오버행 45° 보다 가파르게: 90 − 55 = 35° 오버행)
BASE_MIN_MM = 4.0       # 바닥판 최소 두께
BACK_MIN_MM = 5.0       # 뒤판 최소 두께 (높이가 높아 휘지 않게)
BACK_CORNER_R = 2.5     # 뒤쪽 세로 모서리 둥글림 (벽에 맞댄 쐐기 틈 최대 폭)
FRONT_CORNER_R = 8.0    # 바닥판 앞 세로 모서리 둥글림 상한
TOP_OUTER_CH = 0.5      # 윗면 바깥 모서리 모따기 가로 길이 상한 (세로는 TOP_CH_RISE 배)
TOP_INNER_CH = 0.5      # 컵 입구 안쪽 모따기. 물병과의 틈이 위에서 이만큼 넓어진다
HOLE_CH = 0.5           # 컵 밑 구멍 아래 안쪽 모서리 모따기. 마개와의 틈이 밑에서 이만큼 넓어진다
SEAT_LIP_MIN_MM = 5.0   # 물병 어깨가 앉도록 컵 반지름이 구멍 반지름보다 큰 최소 차이 (마개 지름 ≤ 물병 지름 − 2배)
SLEEVE_MIN_MM = 25.0    # 깔때기 위로 물병 몸통을 감싸는 최소 높이 (물병이 기울지 않게)
FRONT_MARGIN_MM = 10.0  # 바닥판이 컵 앞으로 더 나오는 최소 길이 (서서 마실 자리)
STABILITY_RATIO = 0.5   # 바닥판 가로·세로 ≥ 전체 높이 × 이 비율 (넘어지지 않게)
BASE_SIDE_MARGIN_MM = 5.0  # 바닥판이 뒤판·컵 옆으로 더 나오는 최소 길이
TOP_CH_RISE = 2.0       # 윗면 모따기의 세로 길이 ÷ 가로 길이 (뒤집어 출력할 때 오버행이 되지 않게)
SOCKET_DEPTH_MM = 12.0  # 받침판 소켓 높이 (바닥판 윗면 위). 뒤판 발이 이만큼 끼워진다
SOCKET_WALL_MIN_MM = 4.0  # 소켓 벽 최소 두께
_FLIP = np.diag([1.0, -1.0, -1.0])  # X 축 기준 180°: 컵 기둥을 뒤집어 컵 입구·뒤판 꼭대기가 베드에 닿게


class BottleStandParams(TemplateParams):
    bottle_diameter_mm: float = Field(
        60, ge=40, le=90, description="물병 몸통 바깥 지름 mm (컵에 들어가는 부분의 가장 넓은 곳)",
    )
    cap_diameter_mm: float = Field(
        40, ge=15, le=80,
        description="물병 마개(급수관이 달린 뚜껑) 바깥 지름 mm. 컵 밑 구멍 = 마개 지름 + 틈새. 물병 지름보다 10mm 이상 작게",
    )
    spout_height_mm: float = Field(
        55, ge=30, le=120, description="바닥에서 급수관 끝까지 높이 mm (동물이 서서 입이 닿는 높이)",
    )
    spout_drop_mm: float = Field(
        60, ge=20, le=120,
        description="컵 밑(마개가 나오는 구멍)에서 급수관 끝까지 세로 길이 mm. 보통 마개 높이 + 급수관 길이",
    )
    holder_height_mm: float = Field(
        70, ge=30, le=150, description="물병을 감싸는 컵 높이 mm (컵 밑 ~ 컵 입구). 물병 몸통 높이의 절반쯤",
    )
    base_width_mm: float = Field(110, ge=60, le=220, description="바닥판 가로(X) mm. 넘어지지 않게 전체 높이의 절반 이상")
    base_depth_mm: float = Field(110, ge=60, le=220, description="바닥판 세로(Y) mm. 넘어지지 않게 전체 높이의 절반 이상")
    wall_thickness_mm: float = Field(3, ge=1.0, le=8, description="컵 벽 두께 mm (바닥판·뒤판은 이보다 두꺼울 수 있다)")
    clearance_mm: float = Field(
        1.0, ge=0.5, le=2.0,
        description="물병·마개와 컵 사이 틈새 mm (한쪽). 물병이 한쪽으로 밀려도 발가락이 끼지 않도록 종별 안전 틈새의 절반보다 작게",
    )


@dataclass(frozen=True)
class _Geom:
    t: float        # 컵 벽 두께
    ri: float       # 컵 안 반지름 (물병 + 틈새)
    ro: float       # 컵 바깥 반지름
    rh: float       # 밑 구멍 반지름 (마개 + 틈새)
    z0: float       # 컵 밑(깔때기 끝) 높이
    height: float   # 전체 높이
    base_t: float   # 바닥판 두께
    back_t: float   # 뒤판 두께
    y_back: float   # 뒷면 Y
    y_front_plate: float  # 뒤판 앞면 Y
    y_axis: float   # 물병 축 Y
    r_tip: float    # 컵 밑 끝 바깥 반지름: rh ~ r_tip 은 평평한 밑 고리 (폭 = 벽 두께)
    lip_top: float  # 구멍 세로 벽 위 끝 높이 (안쪽 깔때기가 시작하는 곳)
    seat_top: float  # 안쪽 깔때기가 컵 안 반지름에 닿는 높이


_TAN = math.tan(math.radians(FUNNEL_DEG))
_COS = math.cos(math.radians(FUNNEL_DEG))


def socket_wall(p: BottleStandParams) -> float:
    return max(p.wall_thickness_mm, SOCKET_WALL_MIN_MM)


def base_thickness(p: BottleStandParams) -> float:
    return max(p.wall_thickness_mm, BASE_MIN_MM)


def back_thickness(p: BottleStandParams) -> float:
    return max(p.wall_thickness_mm, BACK_MIN_MM)


def cup_inner_radius(p: BottleStandParams) -> float:
    return p.bottle_diameter_mm / 2 + p.clearance_mm


def cup_outer_radius(p: BottleStandParams) -> float:
    return cup_inner_radius(p) + p.wall_thickness_mm


def hole_radius(p: BottleStandParams) -> float:
    return p.cap_diameter_mm / 2 + p.clearance_mm


def holder_bottom(p: BottleStandParams) -> float:
    """컵 밑(깔때기 끝) 높이 = 급수관 끝 높이 + 컵 밑에서 급수관 끝까지 길이."""
    return p.spout_height_mm + p.spout_drop_mm


def total_height(p: BottleStandParams) -> float:
    return holder_bottom(p) + p.holder_height_mm


def seat_rise(p: BottleStandParams) -> float:
    """컵 밑에서 안쪽 깔때기가 물병 몸통 반지름(컵 안 반지름)에 닿는 높이까지 (구멍 세로 벽 높이 = 벽 두께)."""
    return p.wall_thickness_mm + (cup_inner_radius(p) - hole_radius(p)) * _TAN


def gap_widening(p: BottleStandParams | None = None) -> float:
    """물병·마개와 컵 사이 틈이 입구·밑 구멍 모따기로 틈새보다 넓어지는 최대 폭."""
    return max(TOP_INNER_CH, HOLE_CH)


def max_clearance(p: BottleStandParams, safe_max_mm: float) -> float:
    """틈새 상한. 물병이 컵 안에서 한쪽으로 밀려 붙으면 반대쪽 틈 = 2 × 틈새 (+ 입구·밑 구멍 모따기).
    그 가장 넓은 틈이 안전 틈새(safe_max) 이하가 되게 한다."""
    return (safe_max_mm - gap_widening(p)) / 2


def _geom(p: BottleStandParams) -> _Geom:
    t = p.wall_thickness_mm
    ri, ro, rh = cup_inner_radius(p), cup_outer_radius(p), hole_radius(p)
    z0 = holder_bottom(p)
    y_back = p.base_depth_mm / 2
    back_t = back_thickness(p)
    y_front_plate = y_back - back_t
    # 밑 끝: 반지름 rh ~ rh + t 의 평평한 고리, 그 위로 높이 t 의 세로 구멍 벽, 다시 그 위로 깔때기.
    # 바깥 원뿔(r_tip 에서 FUNNEL_DEG)과 깔때기 사이 두께 = t (1 + tan) cos ≈ 1.4 t
    lip_top = z0 + t
    return _Geom(
        t=t, ri=ri, ro=ro, rh=rh, z0=z0, height=total_height(p), base_t=base_thickness(p), back_t=back_t,
        y_back=y_back, y_front_plate=y_front_plate, y_axis=y_front_plate - ro,
        r_tip=rh + t, lip_top=lip_top, seat_top=lip_top + (ri - rh) * _TAN,
    )


def _revolve_rz(points: list[tuple[float, float]]) -> Part:
    """(r, z) 단면 다각형을 Z 축 둘레로 360° 돌린 회전체."""
    return revolve(Plane.XZ * Polygon(*points, align=None), axis=Axis.Z)


class BottleStandTemplate(Template):
    key = "bottle_stand"
    display_name_ko = "물병 거치대"
    description_ko = (
        "시중 햄스터 급수기(급수관이 달린 물병)를 마개를 아래로 하여 똑바로 세워 두는 거치대. 철망에 걸 수 없는 "
        "유리 수조형 케이지 등에서 쓴다. 뒤판에 물병을 감싸는 컵이 붙고, 컵 밑 깔때기에 물병 어깨가 앉으며 "
        "급수관 끝은 앞이 트인 컵 아래에 온다. 받침판과 물병 컵 두 파트로 출력해 뒤판 발을 받침판 소켓에 끼운다. "
        "뒷면이 평평해 은신처 벽 등에 붙일 수 있다. 물병·마개 지름, 급수관 끝 높이, "
        "컵 밑에서 급수관 끝까지 길이, 컵 높이, 바닥판 크기, 벽 두께, 틈새를 정한다."
    )
    Params = BottleStandParams
    height_field = None  # 높이는 급수관 높이·물병 길이로 정해진다 (줄이면 물을 마실 수 없다)
    size_fields = ()     # 크기는 실제 물병에 맞춰야 하므로 공간이 부족해도 줄이지 않는다
    color = None

    def default_params(self, ctx: RuleContext | None = None) -> BottleStandParams:
        if ctx is None:
            return BottleStandParams()
        p = BottleStandParams(
            wall_thickness_mm=ctx.default_wall_mm,
            clearance_mm=max(0.5, min(1.0, (ctx.size.gap_trap.safe_max_mm - gap_widening()) / 2)),
        )
        # 컵 아래 공간이 통과 기준 이상이 되도록 컵 밑을 올리고, 바닥판을 높이에 맞춰 넓힌다
        drop = max(p.spout_drop_mm, ctx.size.gap_trap.passable_min_mm + base_thickness(p) - p.spout_height_mm)
        p = p.model_copy(update={"spout_drop_mm": float(math.ceil(drop))})
        p = p.model_copy(update={"holder_height_mm": max(p.holder_height_mm, math.ceil(_min_holder(p)))})
        need = math.ceil(max(STABILITY_RATIO * total_height(p), _min_base_depth(p)))
        return p.model_copy(update={
            "base_width_mm": float(max(p.base_width_mm, need, math.ceil(_min_base_width(p)))),
            "base_depth_mm": float(max(p.base_depth_mm, need)),
        })

    def constraints(self, p: BottleStandParams, ctx: RuleContext) -> list[ParamConstraint]:
        gt = ctx.size.gap_trap
        h = total_height(p)
        return [
            ctx.wall_thickness_constraint(),
            ParamConstraint(
                "clearance_mm",
                max=max_clearance(p, gt.safe_max_mm),
                source="species",
                reason_ko=f"물병이 한쪽으로 밀려도 반대쪽 틈(틈새의 2배)이 {gt.safe_max_mm:g}mm 를 넘지 않아야 "
                          "발가락이 끼지 않습니다",
            ),
            ParamConstraint(
                "cap_diameter_mm",
                max=p.bottle_diameter_mm - 2 * SEAT_LIP_MIN_MM,
                reason_ko=f"물병 어깨가 컵 밑 깔때기에 앉도록 마개 지름이 물병 지름보다 "
                          f"{2 * SEAT_LIP_MIN_MM:g}mm 이상 작아야 합니다",
            ),
            ParamConstraint(
                "spout_drop_mm",
                min=gt.passable_min_mm + base_thickness(p) - p.spout_height_mm,
                source="species",
                reason_ko=f"컵 아래 공간에 끼이지 않도록 바닥판 위에서 컵 밑까지 {gt.passable_min_mm:g}mm 이상 "
                          "비워야 합니다 (급수관 끝 높이 + 컵 밑에서 급수관 끝까지 길이)",
            ),
            ParamConstraint(
                "holder_height_mm",
                min=_min_holder(p),
                reason_ko=f"물병이 기울지 않도록 컵이 깔때기 위로 물병 몸통을 {SLEEVE_MIN_MM:g}mm 이상 감싸야 합니다",
            ),
            ParamConstraint(
                "base_depth_mm",
                min=max(STABILITY_RATIO * h, _min_base_depth(p)),
                reason_ko=f"넘어지지 않도록 바닥판 세로는 전체 높이({h:g}mm)의 절반 이상이고 "
                          f"컵 앞으로 {FRONT_MARGIN_MM:g}mm 이상 나와야 합니다",
            ),
            ParamConstraint(
                "base_width_mm",
                min=max(STABILITY_RATIO * h, _min_base_width(p)),
                reason_ko=f"넘어지지 않도록 바닥판 가로는 전체 높이({h:g}mm)의 절반 이상이고 컵보다 넓어야 합니다",
            ),
        ]

    def build(self, p: BottleStandParams) -> Part:
        """조립 형상 = 받침판 + 컵 기둥 (소켓에 밀착해 끼운 상태)."""
        base, holder = (pp.part for pp in self.print_parts(p))
        return base + holder

    def print_parts(self, p: BottleStandParams, built: Part | None = None) -> list[PrintPart]:
        """받침판(사용 자세 그대로)과 컵 기둥(뒤집어 컵 입구가 베드) 두 파트.

        한 덩어리로 세워 출력하면 컵 밑 고리(깔때기 끝)가 뒤판에 닿기 전 허공에서 시작하는 섬이 되어 서포트 없이는
        출력되지 않는다 (면 기울기로 재는 오버행 검사에는 걸리지 않는다). 컵 기둥만 뒤집으면 바깥 원뿔은 위를 보고 안쪽
        깔때기는 수직에서 90 − FUNNEL_DEG 기운 면이라 서포트가 필요 없다. 결합부는 집 템플릿처럼 설계상 밀착이다."""
        g = _geom(p)
        return [
            PrintPart("받침판", self._base_part(p, g), np.eye(3), key="base"),
            PrintPart("물병 컵", self._holder_part(p, g), _FLIP, key="holder"),
        ]

    def _base_part(self, p: BottleStandParams, g: _Geom) -> Part:
        """바닥판 + 뒤판 발을 끼우는 'U' 소켓 (앞·양옆 벽, 뒤는 트여 뒷면이 평평하게 이어진다).

        옆벽은 뒷면에서 BACK_CORNER_R 앞에서 끝난다: 뒤판 뒤 모서리 둥글림과 옆벽 사이에 두께 0 으로 가늘어지는 조각이
        남지 않게. 벽에 맞대면 옆벽 뒤에 깊이 BACK_CORNER_R(끼임 안전 기준보다 작은) 홈이 남는다."""
        base = Box(p.base_width_mm, p.base_depth_mm, g.base_t, align=_BOTTOM)
        verticals = base.edges().filter_by(Axis.Z)
        front_r = min(FRONT_CORNER_R, p.base_width_mm / 2 - 1, p.base_depth_mm / 2 - 1)
        base = fillet(verticals.filter_by(lambda e: e.center().Y < 0), front_r)
        base = fillet(base.edges().filter_by(Axis.Z).filter_by(lambda e: e.center().Y > 0), BACK_CORNER_R)
        top = base.faces().sort_by(Axis.Z)[-1]
        base = chamfer(top.edges(), min(1.5, g.base_t / 3))

        # 뒤판 발 아래: 바닥판 뒤 윗모서리 모따기를 메워 발 밑에 홈이 없게
        base = base + Pos(0, g.y_back - g.back_t / 2, 0) * Box(2 * g.ro, g.back_t, g.base_t, align=_BOTTOM)

        s = socket_wall(p)
        z_top = g.base_t + SOCKET_DEPTH_MM
        y_end = g.y_back - BACK_CORNER_R
        y_start = g.y_front_plate - s
        boss = Pos(0, (y_start + y_end) / 2, 0) * Box(2 * (g.ro + s), y_end - y_start, z_top, align=_BOTTOM)
        verticals = boss.edges().filter_by(Axis.Z)
        boss = fillet(verticals.filter_by(lambda e: e.center().Y < y_start + 1e-3), s / 2)
        boss = fillet(boss.edges().filter_by(Axis.Z).filter_by(lambda e: e.center().Y > y_end - 1e-3), 1.5)
        btop = boss.faces().sort_by(Axis.Z)[-1]
        boss = chamfer(btop.edges(), 0.8)
        return base + boss - self._back_plate(g, g.base_t, z_top + _CUT)

    @staticmethod
    def _back_plate(g: _Geom, z_lo: float, z_hi: float) -> Part:
        """뒤판 단면 기둥: 뒤쪽 세로 모서리 둥글림, 앞 세로 모서리 작은 모따기."""
        back = Pos(0, g.y_back - g.back_t / 2, z_lo) * Box(2 * g.ro, g.back_t, z_hi - z_lo, align=_BOTTOM)
        back = fillet(back.edges().filter_by(Axis.Z).filter_by(lambda e: e.center().Y > g.y_back - 1e-3), BACK_CORNER_R)
        return chamfer(back.edges().filter_by(Axis.Z).filter_by(lambda e: e.center().Y < g.y_front_plate + 1e-3), 0.8)

    def _holder_part(self, p: BottleStandParams, g: _Geom) -> Part:
        H = g.height
        # 뒤판: 소켓 바닥(바닥판 윗면)에 서서 꼭대기까지
        back = self._back_plate(g, g.base_t, H)

        # 컵 기둥: 'D' (앞 반원 + 뒤판까지 이어지는 직사각형). 뒤판 속으로 _CUT 만큼 파묻는다
        reach = g.y_front_plate + _CUT - g.y_axis
        outline = Circle(g.ro) + Pos(0, reach / 2) * Rectangle(2 * g.ro, reach)
        column = Pos(0, g.y_axis, g.z0) * extrude(outline, amount=H - g.z0)
        # 바깥 밑면: 밑 고리 바깥(반지름 r_tip)에서 FUNNEL_DEG 로 올라가는 원뿔이 컵 바깥 반지름(= 뒤판 앞면에 닿는 곳)에
        # 이르면 그 높이에서 평평해진다. 'D' 뒤쪽 모서리(뒤판 옆)는 평평한 밑면이 뒤판과 직각으로 만나 원뿔과 뒤판 사이의
        # 좁은 쐐기 틈이 생기지 않고, 원뿔이 컵 입구 높이까지 모서리를 깎아 먹지도 않는다. 뒤집어 출력하므로 위를 보는 면
        r_tip = g.r_tip
        r_big = math.hypot(g.ro, reach) + 2.0
        z_flat = g.z0 + (g.ro - r_tip) * _TAN
        top_z = max(H, z_flat) + _CUT
        above_cone = _revolve_rz([(0, g.z0), (r_tip, g.z0), (g.ro, z_flat), (r_big, z_flat), (r_big, top_z), (0, top_z)])
        cup = column & Pos(0, g.y_axis, 0) * above_cone
        # 안쪽: 마개 구멍(세로 벽) → 깔때기 → 물병 자리
        cavity = _revolve_rz([
            (0, g.z0 - _CUT), (g.rh, g.z0 - _CUT), (g.rh, g.lip_top), (g.ri, g.seat_top), (g.ri, H + _CUT), (0, H + _CUT),
        ])
        part = back + cup - Pos(0, g.y_axis, 0) * cavity
        # 밑 구멍 아래 안쪽 모서리 모따기 (마개·급수관이 지나가는 곳. 뒤집어 출력하면 위를 보는 면)
        ring = [f for f in part.faces() if abs(f.center().Z - g.z0) < 1e-6 and f.normal_at().Z < -0.99]
        part = chamfer([e for f in ring for w in f.inner_wires() for e in w.edges()], HOLE_CH)

        # 윗면 모서리: 바깥은 모따기, 컵 입구 안쪽은 작은 모따기 (물병을 꽂기 쉽게). 이 면이 베드에 닿도록 뒤집어
        # 출력하므로 45° 모따기는 오버행이 된다: 세로로 TOP_CH_RISE 배 길게 (수직에서 약 27°) 깎는다
        top = part.faces().sort_by(Axis.Z)[-1]
        ch = min(TOP_OUTER_CH, g.t / 3)
        part = chamfer(top.outer_wire().edges(), ch, ch * TOP_CH_RISE, reference=top)
        top = part.faces().sort_by(Axis.Z)[-1]
        inner = [e for w in top.inner_wires() for e in w.edges()]
        if inner:
            part = chamfer(inner, TOP_INNER_CH, TOP_INNER_CH * TOP_CH_RISE, reference=top)
        return part

    def anchors(self, p: BottleStandParams) -> dict[str, Anchor]:
        g = _geom(p)
        return {
            # 뒤판 뒷면: 바닥 높이의 면 가운데. 뚫을 수 없는 면 (통로로 잇지 않는다)
            "back": Anchor((0, g.y_back, 0), (0, 1, 0), (0, 0, 1)),
            "bottom": Anchor((0, 0, 0), (0, 0, -1), (0, 1, 0)),
        }

    def features(self, p: BottleStandParams) -> Features:
        return Features(
            min_wall_thickness_mm=p.wall_thickness_mm,
            openings=(),
            # 마시는 쪽(급수관이 있는 앞)은 비워 둬야 한다
            access_sides=("front",),
            extra={"spout_height_mm": p.spout_height_mm},
        )


def _min_holder(p: BottleStandParams) -> float:
    return seat_rise(p) + SLEEVE_MIN_MM


def _min_base_depth(p: BottleStandParams) -> float:
    """컵이 바닥판 안에 들고 앞으로 FRONT_MARGIN_MM 이상 바닥판이 나오는 세로."""
    return back_thickness(p) + 2 * cup_outer_radius(p) + FRONT_MARGIN_MM


def _min_base_width(p: BottleStandParams) -> float:
    return 2 * cup_outer_radius(p) + 2 * BASE_SIDE_MARGIN_MM
