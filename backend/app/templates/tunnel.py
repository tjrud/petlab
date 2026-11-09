"""터널 템플릿.

단면(shape): 안쪽 폭 = 내경(inner_diameter_mm), 안쪽 높이 ≥ 내경. 모두 좌우 대칭.
  - pointed_arch (기본): 바닥이 열린 아치. '세로 벽 + 반원 + 꼭대기 티어드롭'. 원형 천장의 꼭대기는 오버행이 45° 를
    넘으므로, 꼭대기에서 TIP_ANGLE 만큼 떨어진 접점부터 직선(접선)으로 뾰족하게 이어 서포트 없이 출력한다.
  - round_arch: 바닥이 열린 둥근 아치 (세로 벽 + 반원).
  - tube: 둥근 관 (바닥까지 막힌 원형. 바깥 바닥을 조금 깎아 굴러가지 않게).
  - box: 바닥이 열린 네모 (평평한 지붕).
  - house: 바닥이 열린 집 모양 (세로 벽 + 50° 경사 지붕). 서포트 없이 출력.
경로(path): 곡률(bend_angle_deg > 0)은 수평면(XY)에서 휘도록 단면을 수직축 기준으로 회전(revolve)해 만든다.
  - arc (기본): 한 방향으로 휜다 (90° = ㄱ자, 180° = U자).
  - s_curve: 반씩 반대 방향으로 휘어 S자로 (끝 출입구는 시작과 같은 방향을 본다).
출력: 서포트 없이 출력할 수 있는 자세. 둥근 아치·관·네모는 곧은 터널이면 세워서(단면이 베드와 나란히) 출력하고,
휜 터널이면 세울 수 없어 사용 자세로 출력하며 지붕 안쪽에 서포트가 필요하다고 경고한다.
"""

from __future__ import annotations

import math

from typing import Literal

import numpy as np
from build123d import Align, Axis, Circle, Part, Plane, Polygon, Pos, Rectangle, Rot, extrude, revolve
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
        60, ge=35, le=130, description="터널 안쪽 폭(=내경) mm. 종별 최소 내경 이상"
    )
    bend_angle_deg: float = Field(
        0, ge=0, le=180, description="수평면에서 휘는 각도(도). 0=직선, 90=ㄱ자 곡선, 180=U자. S자 경로에서는 한 번 휘는 각도"
    )
    wall_thickness_mm: float = Field(3, ge=1.0, le=8, description="벽 두께 mm")
    shape: Literal["pointed_arch", "round_arch", "tube", "box", "house"] = Field(
        "pointed_arch",
        description=("단면 모양. pointed_arch=끝이 뾰족한 아치(기본, 서포트 없이 출력), round_arch=둥근 아치, "
                     "tube=둥근 관(바닥까지 막힘), box=네모, house=집 모양(경사 지붕, 서포트 없이 출력). "
                     "둥근 아치·관·네모는 곧은 터널이면 세워서 서포트 없이 출력하지만 휘면 서포트가 필요하다"),
    )
    path: Literal["arc", "s_curve"] = Field(
        "arc", description="휘는 모양 (bend_angle_deg > 0 일 때). arc=한 방향으로 휨, s_curve=S자 (반씩 반대로 휨)"
    )


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


# 서포트 없이 출력할 수 없는 단면 (곧은 터널이면 세워서 출력한다)
NEEDS_STANDING = frozenset({"round_arch", "tube", "box"})
# 관(tube) 바닥에 붙이는 받침의 폭: 바깥 지름의 이 비율 (굴러가지 않고 베드에 잘 붙게)
_TUBE_FOOT = 0.5
# S자 경로에서 한 번 휘는 최대 각도
S_CURVE_MAX_DEG = 90.0


def _round_arch(rad: float, leg_top: float, bottom: float) -> object:
    """바닥(bottom)~leg_top 의 직사각형 + leg_top 높이에 중심을 둔 원 (2D)."""
    rect = Pos(0, bottom) * Rectangle(2 * rad, leg_top - bottom, align=(Align.CENTER, Align.MIN))
    return rect + Pos(0, leg_top) * Circle(rad)


def _house(half: float, wall_top: float, bottom: float) -> object:
    """바닥(bottom)~wall_top 의 세로 벽 + 꼭대기로 TIP_ANGLE 만큼 기운 경사 지붕 (2D 오각형)."""
    rise = half * math.tan(math.radians(TIP_ANGLE_DEG))
    return Polygon(
        (-half, bottom), (half, bottom), (half, wall_top), (0, wall_top + rise), (-half, wall_top),
        align=None,
    )


def _house_wall_top(r: float) -> float:
    """집 모양 안쪽 벽 높이: 지름 2r 인 원(통과 기준)이 경사 지붕에 닿지 않을 만큼 (꼭대기 높이는 뾰족 아치와 같다)."""
    a = math.radians(TIP_ANGLE_DEG)
    return r * (1 + 1 / math.cos(a) - math.tan(a))


def profile(p: TunnelParams):
    """터널 단면. 로컬 2D 좌표: x=가로, y=높이 (바닥 y=0)."""
    r = p.inner_diameter_mm / 2
    t = p.wall_thickness_mm
    ro = r + t
    above_floor = Rectangle(4 * ro, 4 * ro, align=(Align.CENTER, Align.MIN))
    if p.shape == "round_arch":
        return (_round_arch(ro, r, 0) & above_floor) - _round_arch(r, r, -_CUT)
    if p.shape == "box":
        outer = Rectangle(2 * ro, 2 * r + t, align=(Align.CENTER, Align.MIN))
        inner = Pos(0, -_CUT) * Rectangle(2 * r, 2 * r + _CUT, align=(Align.CENTER, Align.MIN))
        return outer - inner
    if p.shape == "house":
        wi = _house_wall_top(r)
        # 바깥 지붕은 안쪽 지붕과 벽 두께만큼 떨어지게 (경사면에 수직으로 t)
        a = math.radians(TIP_ANGLE_DEG)
        lift = t / math.cos(a) - t * math.tan(a)
        return _house(ro, wi + lift, 0) - _house(r, wi, -_CUT)
    if p.shape == "tube":
        # 바닥까지 막힌 둥근 관 (어디나 벽 두께 t). 바깥 아래에 평평한 받침을 붙여 굴러가지 않게 놓인다
        cy = ro
        foot = Rectangle(_TUBE_FOOT * 2 * ro, cy, align=(Align.CENTER, Align.MIN))
        return (Pos(0, cy) * Circle(ro) + foot) - Pos(0, cy) * Circle(r)
    # pointed_arch (기본): 바깥 원(반지름 r+t)은 높이 r 에 중심이 있어 바닥 아래로 t 만큼 내려가므로 바닥(y=0)에서 잘라낸다
    outer = _arch(ro, r, 0) & above_floor
    inner = _arch(r, r, -_CUT)
    return outer - inner


def outer_height(p: TunnelParams) -> float:
    r = p.inner_diameter_mm / 2
    t = p.wall_thickness_mm
    if p.shape == "round_arch":
        return 2 * r + t
    if p.shape == "box":
        return 2 * r + t
    if p.shape == "house":
        a = math.radians(TIP_ANGLE_DEG)
        return _house_wall_top(r) + t / math.cos(a) - t * math.tan(a) + (r + t) * math.tan(a)
    if p.shape == "tube":
        return 2 * (r + t)
    return r + (r + t) / math.cos(math.radians(TIP_ANGLE_DEG))


def is_s_curve(p: TunnelParams) -> bool:
    return p.path == "s_curve" and p.bend_angle_deg > 0


def bend_radius(p: TunnelParams) -> float | None:
    """중심선 굽힘 반경. S자는 반씩 휘므로 한 번 휘는 구간의 길이(전체의 절반)로 계산한다."""
    if p.bend_angle_deg <= 0:
        return None
    length = p.length_mm / 2 if is_s_curve(p) else p.length_mm
    return length / math.radians(p.bend_angle_deg)


def needs_support(p: TunnelParams) -> bool:
    """서포트가 필요한지: 세워서 출력해야 하는 단면인데 휘어서 세울 수 없을 때."""
    return p.shape in NEEDS_STANDING and p.bend_angle_deg > 0


def end_side(bend_angle_deg: float, path: str = "arc") -> Side:
    """끝 출입구가 향하는 로컬 측면. 시작 출입구는 항상 front(-Y). S자는 시작과 같은 방향으로 나간다."""
    if path == "s_curve" and bend_angle_deg > 0:
        return "back"
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
        return TunnelParams(
            # 기본 200mm. 종별 최대 길이(몸길이 2배)가 더 짧으면 그 값
            length_mm=min(200.0, ctx.size.tunnel_max_length_mm),
            inner_diameter_mm=float(math.ceil(ctx.size.tunnel_min_inner_diameter_mm + 5)),
            bend_angle_deg=0,
            wall_thickness_mm=ctx.default_wall_mm,
        )

    def constraints(self, p: TunnelParams, ctx: RuleContext) -> list[ParamConstraint]:
        s = ctx.size
        d = max(p.inner_diameter_mm, s.tunnel_min_inner_diameter_mm)
        max_len = s.tunnel_max_length_mm
        shape_min = 1.5 * d
        if shape_min > max_len:
            min_reason = (f"터널 길이는 내경의 1.5배 이상이 좋지만 최대 길이 {max_len:g}mm 를 넘을 수 없어 "
                          f"{max_len:g}mm 까지만 요구합니다")
        else:
            min_reason = "터널 길이는 내경의 1.5배 이상이어야 합니다"
        # S자는 반씩 휘므로 한 번 휘는 구간 길이가 절반이다 (굽힘 반경 ≥ 내경)
        seg = 0.5 if p.path == "s_curve" else 1.0
        bend_max = math.degrees(seg * p.length_mm / d)
        bend_at_max = math.degrees(seg * max_len / d)  # 최대 길이까지 늘렸을 때의 휨 한계
        if p.bend_angle_deg > bend_at_max + 1e-6:
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
        if p.path == "s_curve" and bend_max > S_CURVE_MAX_DEG:
            bend_max = S_CURVE_MAX_DEG
            bend_reason = "S자 터널은 한 번에 90° 까지만 휠 수 있어 휘는 각도를 줄였습니다"
        return [
            ctx.wall_thickness_constraint(),
            ParamConstraint(
                "inner_diameter_mm", min=s.tunnel_min_inner_diameter_mm, source="species",
                reason_ko=f"{s.display_name} 터널 내경은 최소 {s.tunnel_min_inner_diameter_mm:g}mm 이상이어야 합니다",
            ),
            ParamConstraint(
                # 모양 기준(내경의 1.5배)보다 종별 최대 길이(동물 복지 기준)를 앞세운다: 둘이 부딪히면 최대 길이까지만 요구한다
                "length_mm", min=min(shape_min, max_len), reason_ko=min_reason,
            ),
            ParamConstraint(
                # [근거] DTSchB: 플라스틱 튜브는 몸길이의 2배 이하일 때만 받아들일 수 있다 (환기·사용 설명 조건과 함께).
                # 값(mm)은 species.yaml 이 이 크기 구분에서 가장 작은 개체 몸길이로 정한다.
                # 나중에 더한 기준이라 그 전에 저장된 버전은 막지 않고 경고만 한다 (blocking=False)
                "length_mm", max=max_len, source="species", blocking=False,
                reason_ko=(f"터널 최대 길이는 {max_len:g}mm 입니다 (독일 동물보호연맹: 플라스틱 튜브는 몸길이의 2배 이하. "
                           "이 크기 구분에서 가장 작은 개체 기준)"),
            ),
            ParamConstraint(
                # 중심선 굽힘 반경 ≥ 내경 → 안쪽 벽이 겹치지 않고 몸이 돌아 나갈 수 있음
                "bend_angle_deg", max=bend_max, reason_ko=bend_reason,
            ),
        ]

    def build(self, p: TunnelParams) -> Part:
        R = bend_radius(p)
        prof = profile(p)
        if R is None:
            # XZ 평면(로컬 y=Z)에서 -Y 방향으로 압출 → 터널이 Y 축을 따라 놓임
            return extrude(Plane.XZ * prof, amount=p.length_mm)
        # 단면을 x=R 에 두고 Z 축 기준 회전 → 수평면에서 휘는 터널
        first = revolve(Plane.XZ * (Pos(R, 0) * prof), axis=Axis.Z, revolution_arc=p.bend_angle_deg)
        if not is_s_curve(p):
            return first
        # S자: 첫 구간 끝 단면의 중심을 지나는 수직축으로 180° 돌린 사본을 잇는다 (단면이 좌우 대칭이라 그대로 맞물린다)
        a = math.radians(p.bend_angle_deg)
        ex, ey = R * math.cos(a), R * math.sin(a)
        second = Pos(ex, ey, 0) * Rot(0, 0, 180) * Pos(-ex, -ey, 0) * first
        return first + second

    def print_rotation(self, p: TunnelParams) -> np.ndarray:
        # 곧은 둥근 아치·관·네모: 세워서(터널 축 = Z) 출력하면 단면이 베드와 나란해 서포트가 필요 없다.
        # 터널은 Y 축을 따라 놓이므로 X 축 기준 90° 회전
        if p.shape in NEEDS_STANDING and p.bend_angle_deg <= 0:
            return np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
        return np.eye(3)

    def features(self, p: TunnelParams) -> Features:
        sides: tuple[Side, ...] = ("front", end_side(p.bend_angle_deg, p.path))
        return Features(
            min_wall_thickness_mm=p.wall_thickness_mm,
            openings=(Opening("passage", p.inner_diameter_mm, "터널 내경", rule_key="tunnel_min_inner_diameter_mm"),),
            access_sides=tuple(dict.fromkeys(sides)),
            extra={"outer_height_mm": outer_height(p), "bent_needs_support": needs_support(p)},
        )
