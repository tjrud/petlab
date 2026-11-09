"""설계 엔진 공용 도메인 타입 (DB 모델과 별개)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

from app.templates.base import Features, Side, Template, TemplateParams

Zone = Literal[
    "auto", "left", "right", "front", "back", "center",
    "front_left", "front_right", "back_left", "back_right",
]
ZONES: tuple[str, ...] = Zone.__args__  # type: ignore[attr-defined]
Rotation = Literal[0, 90, 180, 270]


@dataclass(frozen=True)
class Cage:
    """케이지 내부 치수. 좌표: X=가로(왼→오), Y=세로(앞→뒤), Z=높이. 원점은 앞-왼쪽 바닥 모서리."""

    width_mm: float
    depth_mm: float
    height_mm: float


@dataclass(frozen=True)
class PlacementHint:
    zone: Zone = "auto"
    group: str | None = None
    rotation: Rotation | None = None
    # (대상 항목 인덱스, 대상의 측면): 이 항목의 뒷면(back, 램프라면 꼭대기 쪽)을 대상 항목의 그 측면에 맞대어 놓는다.
    # 2층 집의 바깥 램프처럼 두 구조물을 잇는 힌트. 붙일 자리가 없으면 배치기가 일반 방식으로 놓고 경고한다
    attach_to: tuple[int, Side] | None = None


@dataclass(frozen=True)
class Placement:
    x_mm: float  # 외곽 AABB 중심
    y_mm: float
    rotation_deg: Rotation


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def intersects(self, o: "Rect", eps: float = 1e-6) -> bool:
        return (
            self.x0 < o.x1 - eps and o.x0 < self.x1 - eps
            and self.y0 < o.y1 - eps and o.y0 < self.y1 - eps
        )

    def distance(self, o: "Rect") -> float:
        dx = max(0.0, o.x0 - self.x1, self.x0 - o.x1)
        dy = max(0.0, o.y0 - self.y1, self.y0 - o.y1)
        return math.hypot(dx, dy)


# 로컬 측면의 바깥 방향 벡터 (회전 0°)
_SIDE_VEC: dict[str, tuple[int, int]] = {
    "front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0),
}


def world_direction(side: Side, rotation_deg: int) -> tuple[int, int]:
    """로컬 측면이 회전 후 가리키는 월드 방향 (축 단위 벡터)."""
    vx, vy = _SIDE_VEC[side]
    a = math.radians(rotation_deg)
    c, s = round(math.cos(a)), round(math.sin(a))
    return (c * vx - s * vy, s * vx + c * vy)


def access_strip(rect: Rect, direction: tuple[int, int], depth: float) -> Rect:
    """rect 의 direction 쪽 면 앞에 depth 만큼 비워 둬야 하는 영역."""
    dx, dy = direction
    if dx == 1:
        return Rect(rect.x1, rect.y0, rect.x1 + depth, rect.y1)
    if dx == -1:
        return Rect(rect.x0 - depth, rect.y0, rect.x0, rect.y1)
    if dy == 1:
        return Rect(rect.x0, rect.y1, rect.x1, rect.y1 + depth)
    return Rect(rect.x0, rect.y0 - depth, rect.x1, rect.y0)


def mesh_footprint(mesh: trimesh.Trimesh) -> Polygon:
    """메시를 XY 평면에 투영한 외곽 폴리곤 (내부 구멍은 채움)."""
    mask = np.abs(mesh.face_normals[:, 2]) > 1e-6
    polys = [Polygon(tri[:, :2]) for tri in mesh.triangles[mask]]
    merged = unary_union([p for p in polys if p.area > 1e-9]).buffer(0)
    if merged.geom_type == "MultiPolygon":
        # 투영한 삼각형이 맞닿은 이음매(거리 0)인데 부동소수점 때문에 합쳐지지 않고 조각으로 갈라질 때가 있다
        # (예: 내경 20·벽 3mm 둥근 관 터널의 옆면 띠 2mm 가 떨어져 바닥 윤곽이 좁아지고, 벽과의 틈 검사가 없는 틈을 잰다).
        # 아주 작게 닫아(팽창 후 수축) 이음매만 붙인다. 하나로 합쳐지던 윤곽은 이 경로를 지나지 않아 그대로다
        eps = 1e-4
        merged = merged.buffer(eps, join_style="mitre").buffer(-eps, join_style="mitre")
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda g: g.area)  # 파트는 하나의 연결 형상
    return Polygon(merged.exterior).simplify(0.05)


@dataclass
class BuiltPart:
    """출력 파트 하나의 메시 (파트 단위 검사·내보내기용)."""

    key: str  # 파일 이름에 쓰는 ASCII 식별자 (본체는 "body")
    name_ko: str
    mesh: trimesh.Trimesh  # 파트 형상 (검사용. 자세는 상관없다)
    print_mesh: trimesh.Trimesh  # 출력 자세 (베드 Z=0)


@dataclass
class BuiltItem:
    """형상까지 생성된 설계 항목."""

    index: int
    key: str
    features: Features
    mesh: trimesh.Trimesh  # 사용 자세, 로컬 좌표 (XY AABB 중심 = 원점, 바닥 Z=0). 여러 파트면 조립 형상
    print_mesh: trimesh.Trimesh  # 출력 자세 (베드 Z=0). 여러 파트면 첫 파트(본체)
    footprint: Polygon  # 로컬 XY 발자국
    hint: PlacementHint = field(default_factory=PlacementHint)
    template: Template | None = None
    params: TemplateParams | None = None
    placement: Placement | None = None
    # 출력 파트 목록 (비어 있으면 본체 하나 = print_mesh). 메시 건전성·벽 두께 실측·오버행·출력 공간은 파트 단위로 본다
    parts: list[BuiltPart] = field(default_factory=list)
    # 장식 명세(JSON)와 장식을 얹으며 난 경고 (줄임·뺌). 형상에는 이미 반영되어 있다
    decor: dict | None = None
    decor_issues: list = field(default_factory=list)

    @property
    def print_parts(self) -> list[BuiltPart]:
        """검사·내보내기용 파트 목록. 파트가 따로 없으면 본체 하나."""
        return self.parts or [BuiltPart("body", "본체", self.mesh, self.print_mesh)]

    def part_label_ko(self, part: BuiltPart) -> str:
        """이슈 문구용 파트 이름. 파트가 하나뿐이면 항목 이름 그대로 (기존 문구가 바뀌지 않게)."""
        return f"{self.label_ko} ({part.name_ko})" if len(self.parts) > 1 else self.label_ko

    @property
    def label_ko(self) -> str:
        name = self.template.display_name_ko if self.template else self.key
        return f"{name} #{self.index + 1}"

    @property
    def height_mm(self) -> float:
        return float(self.mesh.bounds[1][2])

    def size_xy(self, rotation_deg: int) -> tuple[float, float]:
        lo, hi = self.mesh.bounds
        w, d = float(hi[0] - lo[0]), float(hi[1] - lo[1])
        return (d, w) if rotation_deg in (90, 270) else (w, d)

    def rect_at(self, x: float, y: float, rotation_deg: int) -> Rect:
        w, d = self.size_xy(rotation_deg)
        return Rect(x - w / 2, y - d / 2, x + w / 2, y + d / 2)

    @property
    def world_rect(self) -> Rect:
        assert self.placement is not None
        p = self.placement
        return self.rect_at(p.x_mm, p.y_mm, p.rotation_deg)

    @property
    def world_footprint(self) -> Polygon:
        assert self.placement is not None
        p = self.placement
        poly = affinity.rotate(self.footprint, p.rotation_deg, origin=(0, 0))
        return affinity.translate(poly, p.x_mm, p.y_mm)

    def world_mesh(self) -> trimesh.Trimesh:
        from app.geometry.mesh import placement_matrix

        assert self.placement is not None
        p = self.placement
        m = self.mesh.copy()
        m.apply_transform(placement_matrix(p.x_mm, p.y_mm, p.rotation_deg))
        return m

    def access_directions(self, rotation_deg: int) -> list[tuple[int, int]]:
        return [world_direction(s, rotation_deg) for s in self.features.access_sides]
