"""터널 템플릿.

형상: 바닥이 열린 아치형 터널. 단면은 '세로 벽 + 반원 + 꼭대기 티어드롭'.
  - 원형 천장의 꼭대기 부분은 오버행이 45° 를 넘으므로, 꼭대기에서 TIP_ANGLE 만큼 떨어진 접점부터
    직선(접선)으로 뾰족하게 이어 서포트 없이 출력할 수 있게 한다.
  - 곡률(bend_angle_deg > 0)은 수평면(XY)에서 휘도록 단면을 수직축 기준으로 회전(revolve)해 만든다.
출력: 사용 자세 그대로 (바닥면이 베드).
"""

from __future__ import annotations

import math

from build123d import Align, Axis, Circle, Part, Plane, Polygon, Pos, Rectangle, extrude, revolve
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

# 꼭대기 직선부가 시작되는 접점의 각도(꼭대기 기준). 50° 이면 직선부 오버행 = 90-50 = 40° (< 45°)
TIP_ANGLE_DEG = 50.0
_CUT = 1.0


class TunnelParams(TemplateParams):
    length_mm: float = Field(
        200, ge=80, le=600,
        description="터널 중심선 길이 mm. 종별 최대 길이(몸길이의 2배) 이하. 일반 프린터(220mm)에 들어가려면 200mm 이하 권장",
    )
    inner_diameter_mm: float = Field(
        60, ge=12, le=130, description="터널 안쪽 폭(=내경) mm. 종별 최소 내경 이상"
    )
    bend_angle_deg: float = Field(
        0, ge=0, le=180, description="수평면에서 휘는 각도(도). 0=직선, 90=ㄱ자 곡선, 180=U자"
    )
    wall_thickness_mm: float = Field(3, ge=1.0, le=8, description="벽 두께 mm")


def _arch(rad: float, leg_top: float, bottom: float) -> object:
    """바닥(bottom)~leg_top 의 직사각형 + leg_top 높이에 중심을 둔 원 + 꼭대기 티어드롭 삼각형 (2D)."""
    a = math.radians(TIP_ANGLE_DEG)
    rect = Pos(0, bottom) * Rectangle(2 * rad, leg_top - bottom, align=(Align.CENTER, Align.MIN))
    circle = Pos(0, leg_top) * Circle(rad)
    tip = Polygon(
        (-rad * math.sin(a), leg_top + rad * math.cos(a)),
        (rad * math.sin(a), leg_top + rad * math.cos(a)),
        (0, leg_top + rad / math.cos(a)),
        align=None,
    )
    return rect + circle + tip


def profile(p: TunnelParams):
    """터널 단면 (바닥이 열린 아치). 로컬 2D 좌표: x=가로, y=높이."""
    r = p.inner_diameter_mm / 2
    ro = r + p.wall_thickness_mm
    # 바깥 원(반지름 r+t)은 높이 r 에 중심이 있어 바닥 아래로 t 만큼 내려가므로 바닥(y=0)에서 잘라낸다
    above_floor = Rectangle(4 * ro, 4 * ro, align=(Align.CENTER, Align.MIN))
    outer = _arch(ro, r, 0) & above_floor
    inner = _arch(r, r, -_CUT)
    return outer - inner


def outer_height(p: TunnelParams) -> float:
    r = p.inner_diameter_mm / 2
    return r + (r + p.wall_thickness_mm) / math.cos(math.radians(TIP_ANGLE_DEG))


def bend_radius(p: TunnelParams) -> float | None:
    if p.bend_angle_deg <= 0:
        return None
    return p.length_mm / math.radians(p.bend_angle_deg)


def end_side(bend_angle_deg: float) -> Side:
    """끝 출입구가 향하는 로컬 측면. 시작 출입구는 항상 front(-Y)."""
    if bend_angle_deg <= 45:
        return "back"
    if bend_angle_deg <= 135:
        return "left"
    return "front"


class TunnelTemplate(Template):
    key = "tunnel"
    display_name_ko = "터널"
    description_ko = (
        "바닥이 열린 아치형 터널. 길이, 안쪽 폭(내경), 수평으로 휘는 각도(0=직선), 벽 두께를 정한다. "
        "양쪽 끝이 출입구다."
    )
    Params = TunnelParams
    height_field = None
    size_fields = ("length_mm",)

    def default_params(self, ctx: RuleContext | None = None) -> TunnelParams:
        if ctx is None:
            return TunnelParams()
        inner = float(math.ceil(ctx.size.tunnel_min_inner_diameter_mm + 5))
        max_len = ctx.size.tunnel_max_length_mm
        if max_len is None:
            # 길이 상한이 없는 종(어항): 파는 양쪽 열린 관처럼 내경의 6배 (80~200mm). 안전 기준이 아니라 기본 모양이다
            length = min(200.0, max(80.0, 6 * inner))
        else:
            # 기본 200mm. 종별 최대 길이(몸길이 2배)가 더 짧으면 그 값
            length = min(200.0, max_len)
        return TunnelParams(
            length_mm=length,
            inner_diameter_mm=inner,
            bend_angle_deg=0,
            wall_thickness_mm=ctx.default_wall_mm,
        )

    def constraints(self, p: TunnelParams, ctx: RuleContext) -> list[ParamConstraint]:
        s = ctx.size
        d = max(p.inner_diameter_mm, s.tunnel_min_inner_diameter_mm)
        max_len = s.tunnel_max_length_mm  # None: 길이 상한 없음 (어항)
        shape_min = 1.5 * d
        if max_len is not None and shape_min > max_len:
            min_reason = (f"터널 길이는 내경의 1.5배 이상이 좋지만 최대 길이 {max_len:g}mm 를 넘을 수 없어 "
                          f"{max_len:g}mm 까지만 요구합니다")
        else:
            min_reason = "터널 길이는 내경의 1.5배 이상이어야 합니다"
        bend_max = math.degrees(p.length_mm / d)
        # 최대 길이까지 늘렸을 때의 휨 한계 (길이 상한이 없으면 지금 길이 기준 한계뿐)
        bend_at_max = math.degrees(max_len / d) if max_len is not None else math.inf
        if max_len is not None and p.bend_angle_deg > bend_at_max + 1e-6:
            # 최대 길이로 늘려도 닿지 않는 각도: 까닭(최대 길이)을 밝힌다
            # 영어 카탈로그가 문장 단위로 찾을 수 있게 두 문장을 따로 둔다 (한국어 결과는 같다)
            limit = min(180.0, bend_at_max)
            if p.length_mm >= max_len - 1e-6:
                bend_reason = (f"{s.display_name} 터널은 최대 {max_len:g}mm 라 이 내경으로는 {limit:.0f}° "
                               "까지만 휠 수 있습니다 (U자는 만들 수 없어 끝 출입구 방향이 바뀔 수 있습니다)")
            else:
                bend_reason = (f"지금 길이로는 {bend_max:.0f}°, {s.display_name} 터널은 최대 {max_len:g}mm 라 이 내경으로는 "
                               f"{limit:.0f}° 까지만 휠 수 있습니다 (U자는 만들 수 없어 끝 출입구 방향이 바뀔 수 있습니다)")
        else:
            bend_reason = "굽힘이 너무 급하면 몸이 돌아 나가기 어려워 휘는 각도를 줄였습니다"
        out = [
            ctx.wall_thickness_constraint(),
            ParamConstraint(
                "inner_diameter_mm", min=s.tunnel_min_inner_diameter_mm, source="species",
                reason_ko=f"{s.display_name} 터널 내경은 최소 {s.tunnel_min_inner_diameter_mm:g}mm 이상이어야 합니다",
            ),
            ParamConstraint(
                # 모양 기준(내경의 1.5배)보다 종별 최대 길이(동물 복지 기준)를 앞세운다: 둘이 부딪히면 최대 길이까지만 요구한다
                "length_mm", min=min(shape_min, max_len) if max_len is not None else shape_min, reason_ko=min_reason,
            ),
        ]
        if max_len is not None:
            out.append(ParamConstraint(
                # [근거] DTSchB: 플라스틱 튜브는 몸길이의 2배 이하일 때만 받아들일 수 있다 (환기·사용 설명 조건과 함께).
                # 값(mm)은 species.yaml 이 이 크기 구분에서 가장 작은 개체 몸길이로 정한다.
                # 나중에 더한 기준이라 그 전에 저장된 버전은 막지 않고 경고만 한다 (blocking=False)
                "length_mm", max=max_len, source="species", blocking=False,
                reason_ko=(f"터널 최대 길이는 {max_len:g}mm 입니다 (독일 동물보호연맹: 플라스틱 튜브는 몸길이의 2배 이하. "
                           "이 크기 구분에서 가장 작은 개체 기준)"),
            ))
        out.append(ParamConstraint(
            # 중심선 굽힘 반경 ≥ 내경 → 안쪽 벽이 겹치지 않고 몸이 돌아 나갈 수 있음
            "bend_angle_deg", max=bend_max, reason_ko=bend_reason,
        ))
        return out

    def build(self, p: TunnelParams) -> Part:
        R = bend_radius(p)
        prof = profile(p)
        if R is None:
            # XZ 평면(로컬 y=Z)에서 -Y 방향으로 압출 → 터널이 Y 축을 따라 놓임
            return extrude(Plane.XZ * prof, amount=p.length_mm)
        # 단면을 x=R 에 두고 Z 축 기준 회전 → 수평면에서 휘는 터널
        return revolve(Plane.XZ * (Pos(R, 0) * prof), axis=Axis.Z, revolution_arc=p.bend_angle_deg)

    def features(self, p: TunnelParams) -> Features:
        sides: tuple[Side, ...] = ("front", end_side(p.bend_angle_deg))
        return Features(
            min_wall_thickness_mm=p.wall_thickness_mm,
            openings=(Opening("passage", p.inner_diameter_mm, "터널 내경", rule_key="tunnel_min_inner_diameter_mm"),),
            access_sides=tuple(dict.fromkeys(sides)),
            extra={"outer_height_mm": outer_height(p)},
        )
