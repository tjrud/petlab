"""build123d 형상 → trimesh 메시 변환과 메시 건전성 검사, 좌표 변환."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import trimesh
from build123d import Part


@dataclass(frozen=True)
class MeshHealth:
    watertight: bool
    winding_consistent: bool
    volume_mm3: float
    face_count: int

    @property
    def ok(self) -> bool:
        return self.watertight and self.winding_consistent and self.volume_mm3 > 0


def part_to_mesh(
    part: Part, tolerance_mm: float = 0.05, angular_tolerance_deg: float = 5.0
) -> trimesh.Trimesh:
    """B-rep 형상을 삼각형 메시로 변환한다. OCC 테셀레이션은 면 경계를 공유하므로
    정점 병합 후 닫힌(watertight) 메시가 되어야 한다."""
    verts, tris = part.tessellate(tolerance_mm, math.radians(angular_tolerance_deg))
    vertices = np.array([(v.X, v.Y, v.Z) for v in verts], dtype=np.float64)
    faces = np.array(tris, dtype=np.int64)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(mesh)  # 바깥 방향 법선으로 정렬 (닫힌 메시일 때만 의미 있음)
    return mesh


def mesh_health(mesh: trimesh.Trimesh) -> MeshHealth:
    watertight = bool(mesh.is_watertight)
    return MeshHealth(
        watertight=watertight,
        winding_consistent=bool(mesh.is_winding_consistent),
        volume_mm3=float(mesh.volume) if watertight else 0.0,
        face_count=int(len(mesh.faces)),
    )


def rotation_matrix_4x4(rot3: np.ndarray) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = rot3
    return m


def to_print_orientation(mesh: trimesh.Trimesh, rot3: np.ndarray) -> trimesh.Trimesh:
    """사용 자세 메시를 출력 자세로 회전하고, 베드(Z=0) 위 XY 중심에 놓는다."""
    m = mesh.copy()
    m.apply_transform(rotation_matrix_4x4(rot3))
    lo, hi = m.bounds
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    return m


def placement_matrix(x_mm: float, y_mm: float, rotation_deg: int) -> np.ndarray:
    """케이지 좌표계 배치 변환: Z 축 회전(rotation_deg) 후 (x, y) 로 평행 이동."""
    a = math.radians(rotation_deg)
    c, s = round(math.cos(a), 12), round(math.sin(a), 12)
    m = np.eye(4)
    m[:2, :2] = [[c, -s], [s, c]]
    m[0, 3], m[1, 3] = x_mm, y_mm
    return m
