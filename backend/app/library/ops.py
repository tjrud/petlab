"""Part DSL v1 형상 연산 → build123d (설계 §5.5, §5.6, §5.8).

좌표는 사용 자세의 mm: Z 위, 바닥 Z = 0, X 오른쪽, Y 뒤 (앞은 -Y). 여기 함수는 이미 계산한 수(식이 아니라 값)만 받는다.
식 계산과 단계 순서(add·cut, when, repeat)는 app.library.template 이 맡는다.

연산은 네 가지뿐이다 (box, cylinder, prism, passage). 모깎기·모따기·셸·오프셋·로프트·스윕·회전체·회전·글자는 v1 에 없다:
OCC 결과가 비다양체(non-manifold)가 되거나 오버행이 생기는 주된 원인이고, 해석적 외형(envelope)과 축 정렬 슬라이드 가정이
그것들이 없다는 데 기대기 때문이다.

무거운 모듈이다 (build123d, shapely, numpy).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from build123d import Align, Box, Cylinder, Part, Plane, Polygon, Pos, Rot, extrude

from app.library.errors import DslError
from app.templates.base import Anchor, cutter_at
from app.templates.tunnel import TunnelParams, inner_profile

Vec = tuple[float, float, float]

# 출력 자세: 사용 자세 → 출력 자세 회전 R (v' = R v, app.geometry.mesh.to_print_orientation 과 같다).
# 이름은 베드에 닿는 면. R @ (그 면의 바깥 법선) == (0, 0, -1) (tests/test_library_template.py 가 확인)
ROTATIONS: dict[str, np.ndarray] = {
    "upright": np.eye(3),
    "inverted": np.diag([1.0, -1.0, -1.0]),
    "front_down": np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]),
    "back_down": np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]),
    "left_down": np.array([[0.0, 0.0, -1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]]),
    "right_down": np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]),
}
# 각 출력 자세에서 베드에 닿는 면의 바깥 법선 (사용 자세)
BED_FACE_NORMALS: dict[str, Vec] = {
    "upright": (0.0, 0.0, -1.0),
    "inverted": (0.0, 0.0, 1.0),
    "front_down": (0.0, -1.0, 0.0),
    "back_down": (0.0, 1.0, 0.0),
    "left_down": (-1.0, 0.0, 0.0),
    "right_down": (1.0, 0.0, 0.0),
}
# 축 이름 → 단위 벡터 (연결 지점의 normal·up)
AXES: dict[str, Vec] = {
    "+X": (1.0, 0.0, 0.0), "-X": (-1.0, 0.0, 0.0),
    "+Y": (0.0, 1.0, 0.0), "-Y": (0.0, -1.0, 0.0),
    "+Z": (0.0, 0.0, 1.0), "-Z": (0.0, 0.0, -1.0),
}

_BOTTOM = (Align.CENTER, Align.CENTER, Align.MIN)
_CENTER = (Align.CENTER, Align.CENTER, Align.CENTER)
# 출입구 자르기: 면 바깥 1mm 에서 벽 안쪽 (wall + 1.5)mm 까지 (cutter_at 은 기준점에서 0.5mm 안쪽부터 시작한다, F5)
DOOR_OUTSIDE_MM = 1.0
DOOR_EXTRA_DEPTH_MM = 2.0


def _positive(value: float, what: str, path: str) -> float:
    v = float(value)
    if not (math.isfinite(v) and v > 0):
        raise DslError("DSL006", path, f"{what} must be a positive number, got {value!r}",
                       "check the expression at this step for the current params")
    return v


def _plane(name: str, at: Sequence[float]) -> Plane:
    """2D 단면을 놓을 평면 (원점 = at). xz: (x, z), 법선 -Y / yz: (y, z), 법선 +X / xy: (x, y), 법선 +Z."""
    origin = tuple(float(v) for v in at)
    if name == "xz":
        return Plane(origin=origin, x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    if name == "yz":
        return Plane(origin=origin, x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    return Plane(origin=origin, x_dir=(1, 0, 0), z_dir=(0, 0, 1))


def box(size: Sequence[float], at: Sequence[float], align: str, path: str = "") -> Part:
    """bottom: XY 는 at 에 가운데, Z 는 at.z 부터 / center: at 에 가운데."""
    x, y, z = (_positive(v, f"box size[{k}]", f"{path}/size/{k}") for k, v in enumerate(size))
    return Pos(*(float(v) for v in at)) * Box(x, y, z, align=_BOTTOM if align == "bottom" else _CENTER)


def cylinder(r: float, h: float, axis: str, at: Sequence[float], align: str, path: str = "") -> Part:
    """축 정렬 원기둥. bottom: 가장 낮은 점이 at.z, 나머지 두 축은 at 에 가운데 (축 z 면 원이 at.xy 에 가운데, z 는 at.z 부터).
    center: at 에 가운데."""
    r = _positive(r, "cylinder r", f"{path}/r")
    h = _positive(h, "cylinder h", f"{path}/h")
    ax, ay, az = (float(v) for v in at)
    if axis == "z":
        return Pos(ax, ay, az) * Cylinder(r, h, align=_BOTTOM if align == "bottom" else _CENTER)
    cz = az + r if align == "bottom" else az
    rot = Rot(0, 90, 0) if axis == "x" else Rot(90, 0, 0)
    return Pos(ax, ay, cz) * rot * Cylinder(r, h)


def _simple_polygon(points: Sequence[tuple[float, float]], path: str) -> list[tuple[float, float]]:
    """단순 다각형인지 확인하고(자기 교차·넓이 0 이면 DSL006) 반시계 방향으로 맞춘다."""
    from shapely.geometry import LinearRing
    from shapely.geometry import Polygon as ShapelyPolygon
    from shapely.geometry.polygon import orient

    pts = [(float(a), float(b)) for a, b in points]
    if any(not (math.isfinite(a) and math.isfinite(b)) for a, b in pts):
        raise DslError("DSL006", f"{path}/points", "a prism point is not a finite number")
    if len(pts) < 3 or not LinearRing(pts).is_simple:
        raise DslError("DSL006", f"{path}/points", "prism points must form a simple polygon (no self-intersection, "
                                                   "no repeated points)", "order the points around the outline")
    poly = ShapelyPolygon(pts)
    if not poly.is_valid or poly.area <= 1e-9:
        raise DslError("DSL006", f"{path}/points", "prism points must enclose a non-zero area")
    ring = list(orient(poly, sign=1.0).exterior.coords)[:-1]
    return [(float(a), float(b)) for a, b in ring]


def prism(plane: str, points: Sequence[tuple[float, float]], depth: float, at: Sequence[float],
          path: str = "") -> Part:
    """평면 위 다각형(at 기준 좌표)을 평면 법선 방향으로 at 에 대칭이 되게 depth 만큼 밀어낸다."""
    d = _positive(depth, "prism depth", f"{path}/depth")
    ring = _simple_polygon(points, path)
    face = _plane(plane, at) * Polygon(*ring, align=None)
    return extrude(face, amount=d / 2, both=True)


def passage_profile(shape: str, width: float, wall: float = 0.0):
    """통로·출입구 단면 = 터널 안쪽 단면 (바닥 y=0 아래 1mm 까지, x=가로, y=위). 터널과 같은 곳에서 만든다."""
    return inner_profile(TunnelParams.model_construct(inner_diameter_mm=float(width), shape=shape,
                                                      wall_thickness_mm=float(wall)))


def passage(shape: str, width: float, axis: str, length: float, at: Sequence[float], path: str = "") -> Part:
    """방 안쪽 통로 자르기: 터널 안쪽 단면(바닥 = at.z, 1mm 아래까지)을 axis 방향으로 at 에 대칭이 되게 length 만큼."""
    w = _positive(width, "passage width", f"{path}/width")
    n = _positive(length, "passage length", f"{path}/length")
    if shape == "tube":
        raise DslError("DSL003", f"{path}/shape", "a passage cannot be a tube (it is a closed ring, not a doorway)",
                       "use round_arch, pointed_arch, box or house")
    return extrude(_plane("xz" if axis == "y" else "yz", at) * passage_profile(shape, w), amount=n / 2, both=True)


def door_cutter(anchor: Anchor, profile: str, width: float, wall: float) -> Part:
    """출입구 자르기 (§5.6): 기준점을 법선 반대로 (wall + 1) 옮긴 자리에서 cutter_at 으로 (wall + 2) 만큼.
    면 바깥 1mm 부터 벽 안쪽 (wall + 1.5)mm 까지 덮어, 출입구가 늘 그 부품의 벽을 뚫는다."""
    n = np.asarray(anchor.normal, dtype=float)
    o = np.asarray(anchor.origin, dtype=float)
    shifted = Anchor(tuple(float(v) for v in o - n * (wall + DOOR_OUTSIDE_MM)), tuple(float(v) for v in n),
                     tuple(float(v) for v in anchor.up))
    return cutter_at(shifted, passage_profile(profile, width, wall), wall + DOOR_EXTRA_DEPTH_MM)


def make(op: str, args: dict, path: str = "") -> Part:
    """계산을 마친 단계 하나의 형상. args 는 그 연산의 인자 (수와 이름만)."""
    at = args.get("at") or (0.0, 0.0, 0.0)
    if op == "box":
        return box(args["size"], at, args.get("align", "bottom"), path)
    if op == "cylinder":
        return cylinder(args["r"], args["h"], args["axis"], at, args.get("align", "bottom"), path)
    if op == "prism":
        return prism(args["plane"], args["points"], args["depth"], at, path)
    if op == "passage":
        return passage(args["shape"], args["width"], args["axis"], args["length"], at, path)
    raise DslError("DSL010", f"{path}/op", f"unknown op {op!r}")
