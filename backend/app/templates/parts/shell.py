"""껍데기 부품: 벽, 바닥판, 지붕.

지붕
  - flat: 1층이면 본체와 한 덩어리(은신처처럼 뒤집어 출력). 2층이면 선반 위 층판 때문에 본체를 바로 세워 출력해야 하므로
    지붕을 따로 떼어(뚜껑: 판 + 벽 바깥을 감싸는 스커트) 뒤집어 출력한다.
  - pitched: 박공 지붕(용마루 = X 축). 스커트가 벽 바깥을 감싸고 양 끝은 박공판으로 막힌다. 스커트 아랫면을 베드에 대고
    바로 세워 출력하므로 경사가 (90° − 최대 오버행) 이상이어야 안쪽 경사면이 서포트 없이 출력된다.
  - rounded: 뾰족 아치 볼트(터널 단면과 같은 티어드롭). 원 반지름은 반폭으로 고정되고(반지름이 반폭보다 크면 처마에서
    이미 45° 를 넘고, 작으면 폭을 덮지 못한다) 꼭대기 각도(tip_deg)로 뾰족한 정도를 정한다.
지붕을 따로 씌우면 외형 치수에 스커트 두께가 포함되므로 벽 고리는 외형보다 벽 두께만큼 안쪽이다.
"""

from __future__ import annotations

import math
from typing import Literal

from build123d import Align, Box, Circle, Part, Plane, Polygon, Pos, Rectangle, extrude
from pydantic import Field

from app.templates.base import ParamConstraint, TemplateParams
from app.templates.parts.common import CUT, TIP_ANGLE_DEG

# 지붕 뚜껑이 벽 바깥을 감싸는 스커트 높이
SKIRT_MM = 6.0


class WallPart(TemplateParams):
    thickness_mm: float = Field(3, ge=1.0, le=8, description="벽 두께 mm. 종별 최소 벽 두께 이상")


class FloorPart(TemplateParams):
    enabled: bool = Field(False, description="바닥판 유무. true 면 벽 안쪽에 바닥판을 깐다 (바닥재가 들어오지 않게)")
    thickness_mm: float = Field(3, ge=1.0, le=8, description="바닥판 두께 mm")


class RoofPart(TemplateParams):
    kind: Literal["flat", "pitched", "rounded"] = Field(
        "flat", description="지붕 모양. flat=평 지붕, pitched=경사(박공) 지붕, rounded=둥근(뾰족 아치) 지붕"
    )
    pitch_deg: float = Field(
        50, ge=45, le=65,
        description="경사 지붕의 경사각(도, 수평 기준). 서포트 없이 출력하려면 45° 보다 가팔라야 한다 (pitched 일 때만)",
    )
    tip_deg: float = Field(
        50, ge=50, le=70,
        description="둥근 지붕 꼭대기의 뾰족한 정도(도). 50=가장 둥글고 낮음, 70=가장 뾰족하고 높음 (rounded 일 때만)",
    )


def roof_is_cap(roof: RoofPart, floors: int) -> bool:
    """지붕을 본체와 따로 출력하는지 (뚜껑)."""
    return roof.kind != "flat" or floors == 2


def pitched_eave_lift(t: float, pitch_deg: float) -> float:
    """박공 지붕 바깥 경사면이 벽 바깥면 위치에서 처마(안쪽 경사면의 벽 꼭대기)보다 높은 양. 두께 t 의 평행 이동 결과."""
    a = math.radians(pitch_deg)
    return t * (1 - math.sin(a)) / math.cos(a)


def roof_rise(roof: RoofPart, floors: int, outer_depth: float, t: float) -> float:
    """처마(벽 꼭대기) 위로 지붕이 더하는 높이. 외형 높이 = 처마 높이 + 이 값."""
    if roof.kind == "pitched":
        return pitched_eave_lift(t, roof.pitch_deg) + (outer_depth / 2) * math.tan(math.radians(roof.pitch_deg))
    if roof.kind == "rounded":
        return (outer_depth / 2) / math.cos(math.radians(roof.tip_deg))
    return t if roof_is_cap(roof, floors) else 0.0


def roof_constraints(roof: RoofPart, printing_max_overhang_deg: float | None) -> list[ParamConstraint]:
    if roof.kind != "pitched" or printing_max_overhang_deg is None:
        return []
    # 바로 세워 출력하는 박공 지붕의 안쪽 경사면 오버행 = 90° − 경사각. 경계값(정확히 45°)은 판정이 흔들려 1° 여유
    min_pitch = 90.0 - printing_max_overhang_deg + 1.0
    return [ParamConstraint(
        "roof.pitch_deg", min=min_pitch, source="printing",
        reason_ko=f"경사 지붕을 서포트 없이 출력하려면 경사가 {min_pitch:g}° 이상이어야 합니다 (안쪽 경사면 오버행)",
    )]


# ── 2D 단면 (YZ 평면: 가로 = Y, 세로 = Z) ────────────────────


def _pitched_profile(half: float, z_eave: float, z_bottom: float, pitch_deg: float):
    """다리(±half, z_bottom~z_eave) + 경사 삼각형 (2D)."""
    rise = half * math.tan(math.radians(pitch_deg))
    return Polygon((-half, z_bottom), (half, z_bottom), (half, z_eave), (0, z_eave + rise), (-half, z_eave), align=None)


def _rounded_profile(half: float, z_spring: float, z_bottom: float, tip_deg: float, chamfer_t: float = 0.0):
    """다리(±half, z_bottom~z_spring) + 반지름 half 의 원 + 꼭대기 티어드롭 (2D). 바닥 아래는 잘라낸다.

    chamfer_t > 0 이면(지붕 안쪽 공간) 처마에서 벽 두께만큼 안쪽까지 50° 모따기로 올라간 뒤 원호를 만난다:
    평평한 벽 꼭대기와 원호 사이의 쐐기 틈을 메우면서, 뚜껑을 세워 출력할 때 아랫면 오버행이 40° 를 넘지 않는다."""
    a = math.radians(tip_deg)
    legs = Pos(0, z_bottom) * Rectangle(2 * half, z_spring - z_bottom, align=(Align.CENTER, Align.MIN))
    tip = Polygon(
        (-half * math.sin(a), z_spring + half * math.cos(a)),
        (half * math.sin(a), z_spring + half * math.cos(a)),
        (0, z_spring + half / math.cos(a)),
        align=None,
    )
    above = Pos(0, z_bottom) * Rectangle(4 * half, 4 * half + z_spring - z_bottom, align=(Align.CENTER, Align.MIN))
    prof = legs + ((Pos(0, z_spring) * Circle(half) + tip) & above)
    if chamfer_t > 0:
        c = chamfer_t * math.tan(math.radians(TIP_ANGLE_DEG))
        inner = half - chamfer_t
        arc_z = z_spring + math.sqrt(max(half**2 - inner**2, 0.0))
        for sgn in (1.0, -1.0):
            # 벽 두께 위 영역(처마 높이~원호)에서 모따기 선 아래쪽을 잘라낸다
            prof = prof - Polygon((sgn * half, z_spring), (sgn * inner, z_spring + c), (sgn * inner, arc_z + CUT),
                                  (sgn * half, arc_z + CUT), align=None)
    return prof


def cavity_profile(roof: RoofPart, half: float, z_eave: float, z_bottom: float, t: float):
    """지붕 뚜껑 안쪽 공간의 단면 (벽 고리 바깥면 = ±half, 벽 두께 t). 벽 꼭대기는 처마 높이로 평평하다."""
    if roof.kind == "pitched":
        return _pitched_profile(half, z_eave, z_bottom, roof.pitch_deg)
    return _rounded_profile(half, z_eave, z_bottom, roof.tip_deg, chamfer_t=t)


def _extrude_x(profile, x0: float, x1: float) -> Part:
    """YZ 단면을 X 축 방향 [x0, x1] 로 압출."""
    return Pos(x0, 0, 0) * extrude(Plane.YZ * profile, amount=x1 - x0)


def wall_ring(wx: float, wy: float, t: float, z_top: float) -> Part:
    """위가 열린 벽 고리 (바닥 Z=0 ~ 처마 z_top, 꼭대기 평평). 경사·둥근 지붕이면 뚜껑이 그 위를 덮고 박공판으로 양 끝을 막는다.
    (벽이 지붕 안쪽 곡면을 따라 올라가면 안쪽 위 모서리가 칼날처럼 얇아지므로 벽은 평평하게 끝낸다)"""
    outer = Box(wx, wy, z_top, align=(Align.CENTER, Align.CENTER, Align.MIN))
    inner = Pos(0, 0, -CUT) * Box(wx - 2 * t, wy - 2 * t, z_top + 2 * CUT, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return outer - inner


def flat_roof_body(W: float, D: float, H: float, t: float) -> Part:
    """1층 평 지붕: 바닥이 열린 상자 (벽 + 지붕 한 덩어리, 은신처처럼 뒤집어 출력)."""
    outer = Box(W, D, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    cavity = Pos(0, 0, -CUT) * Box(W - 2 * t, D - 2 * t, H - t + CUT, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return outer - cavity


def roof_cap(roof: RoofPart, W: float, D: float, t: float, z_eave: float) -> Part:
    """따로 출력하는 지붕 뚜껑. 벽 바깥을 SKIRT_MM 만큼 감싼다. 바깥 치수 W×D, 벽 고리는 (W−2t)×(D−2t)."""
    wx, wy = W - 2 * t, D - 2 * t
    z_skirt = z_eave - SKIRT_MM
    if roof.kind == "flat":
        plate = Pos(0, 0, z_eave) * Box(W, D, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
        skirt = Pos(0, 0, z_skirt) * Box(W, D, SKIRT_MM, align=(Align.CENTER, Align.CENTER, Align.MIN))
        hole = Pos(0, 0, z_skirt - CUT) * Box(wx, wy, SKIRT_MM + 2 * CUT, align=(Align.CENTER, Align.CENTER, Align.MIN))
        return plate + (skirt - hole)
    if roof.kind == "pitched":
        outer = _pitched_profile(D / 2, z_eave + pitched_eave_lift(t, roof.pitch_deg), z_skirt, roof.pitch_deg)
    else:
        outer = _rounded_profile(D / 2, z_eave, z_skirt, roof.tip_deg)
    inner = cavity_profile(roof, wy / 2, z_eave, z_skirt - CUT, t)
    return _extrude_x(outer, -W / 2, W / 2) - _extrude_x(inner, -wx / 2, wx / 2)


def floor_plate(wx: float, wy: float, t: float, tf: float) -> Part:
    """벽 안쪽에 깔리는 바닥판 (바닥 Z=0)."""
    return Box(wx - 2 * t, wy - 2 * t, tf, align=(Align.CENTER, Align.CENTER, Align.MIN))
