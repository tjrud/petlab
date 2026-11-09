"""부품 공통: 좌표 틀, 뾰족 아치·렌즈 단면, 상수.

집 템플릿의 출입구·창·연결부는 모두 뾰족 아치(꼭대기 TIP_ANGLE_DEG 티어드롭, 터널과 같다)다.
뾰족 아치는 본체를 바로 세워 출력해도, 뒤집어 출력해도 오버행이 45° 를 넘지 않는다
(둥근 아치는 세워 출력할 때 꼭대기가 수평에 가까워 서포트가 필요하다).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Align, Circle, Part, Plane, Polygon, Pos, Rectangle, extrude

from app.templates.base import Side

# 뾰족 아치 꼭대기 직선부가 시작되는 접점 각도(꼭대기 기준). 50° → 직선부 오버행 40° (< 45°). 터널과 같은 값
TIP_ANGLE_DEG = 50.0
# 불리언 연산이 면과 정확히 겹치지 않도록 잘라내는 형상을 이만큼 연장
CUT = 1.0
# 개구부와 다른 요소(벽 모서리·선반·지붕) 사이에 남기는 최소 여유
MARGIN_MM = 3.0

SIDES: tuple[Side, ...] = ("front", "back", "left", "right")
SIDE_KO: dict[str, str] = {"front": "앞", "back": "뒤", "left": "왼쪽", "right": "오른쪽"}
OPPOSITE: dict[str, Side] = {"front": "back", "back": "front", "left": "right", "right": "left"}


def arch_height(width_mm: float) -> float:
    """뾰족 아치 개구부의 높이 (바닥에서 꼭대기까지): 반지름 r 의 세로 벽 + 티어드롭."""
    r = width_mm / 2
    return r + r / math.cos(math.radians(TIP_ANGLE_DEG))


def lens_height(diameter_mm: float) -> float:
    """위아래가 모두 뾰족한 렌즈형 창의 높이."""
    r = diameter_mm / 2
    return 2 * r / math.cos(math.radians(TIP_ANGLE_DEG))


def _tip(rad: float, cy: float, up: bool):
    """중심 (0, cy) 반지름 rad 원의 꼭대기(또는 바닥) 티어드롭 삼각형 (2D)."""
    a = math.radians(TIP_ANGLE_DEG)
    s = 1.0 if up else -1.0
    return Polygon(
        (-rad * math.sin(a), cy + s * rad * math.cos(a)),
        (rad * math.sin(a), cy + s * rad * math.cos(a)),
        (0, cy + s * rad / math.cos(a)),
        align=None,
    )


def pointed_arch(rad: float, bottom: float):
    """바닥(bottom)에서 시작하는 뾰족 아치 (2D): 높이 rad 의 직사각형 + 원 + 꼭대기 티어드롭. 폭 = 2·rad."""
    rect = Pos(0, bottom) * Rectangle(2 * rad, rad, align=(Align.CENTER, Align.MIN))
    return rect + Pos(0, bottom + rad) * Circle(rad) + _tip(rad, bottom + rad, up=True)


def lens(rad: float, center: float):
    """위아래가 뾰족한 렌즈형 구멍 (2D). 어느 자세로 출력해도 구멍 천장이 45° 를 넘지 않는다."""
    return Pos(0, center) * Circle(rad) + _tip(rad, center, up=True) + _tip(rad, center, up=False)


@dataclass(frozen=True)
class Shell:
    """벽 고리의 치수 (조립형 템플릿 공통 좌표).

    wx, wy: 벽 고리 바깥 치수 (지붕을 따로 씌우면 외형보다 벽 두께만큼 안쪽), t: 벽 두께,
    z_floor: 실내 바닥 높이 (바닥판이 있으면 그 두께), wall_top: 처마 높이 (벽 꼭대기 중 가장 낮은 곳)
    """

    wx: float
    wy: float
    t: float
    z_floor: float
    wall_top: float

    def wall_center(self, side: Side) -> tuple[float, float]:
        """측면 벽 두께 중심의 (x, y). 벽에 평행한 축 좌표는 0."""
        if side == "front":
            return (0.0, -(self.wy / 2 - self.t / 2))
        if side == "back":
            return (0.0, self.wy / 2 - self.t / 2)
        if side == "left":
            return (-(self.wx / 2 - self.t / 2), 0.0)
        return (self.wx / 2 - self.t / 2, 0.0)

    def outward(self, side: Side) -> tuple[int, int]:
        return {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}[side]

    def wall_length(self, side: Side) -> float:
        """측면 벽의 바깥 길이."""
        return self.wx if side in ("front", "back") else self.wy

    def inner_length(self, side: Side) -> float:
        return self.wall_length(side) - 2 * self.t


def through_wall(profile, side: Side, shell: Shell, depth: float, offset: float = 0.0) -> Part:
    """벽에 수직으로 뚫는(또는 덧붙이는) 형상. profile 은 벽 평면 2D(가로 = 벽 방향, 세로 = Z, 벽 가운데가 가로 0).

    depth 두께로 벽 두께 중심에 대칭으로 만든 뒤, offset 만큼 바깥 방향으로 옮긴다."""
    plane = Plane.XZ if side in ("front", "back") else Plane.YZ
    solid = extrude(plane * profile, amount=depth / 2, both=True)
    cx, cy = shell.wall_center(side)
    ox, oy = shell.outward(side)
    return Pos(cx + ox * offset, cy + oy * offset, 0) * solid

