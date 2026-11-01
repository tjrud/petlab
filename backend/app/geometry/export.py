"""STL / 3MF 내보내기.

- STL: 파트 1개면 단일 .stl, 여러 개면 파트별 STL 을 묶은 .zip
- 3MF: 파일 하나에 파트별 오브젝트, 출력 자세로 판 위에 나란히 배치
모든 메시는 mm 단위.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import trimesh


@dataclass(frozen=True)
class ExportPart:
    name: str  # 파일·오브젝트 이름 (ASCII 권장)
    mesh: trimesh.Trimesh  # 출력 자세 메시 (Z=0 베드 위)


@dataclass(frozen=True)
class ExportFile:
    filename: str
    media_type: str
    content: bytes


def stl_bytes(mesh: trimesh.Trimesh) -> bytes:
    return mesh.export(file_type="stl")


def arrange_on_plate(parts: list[ExportPart], spacing_mm: float) -> list[ExportPart]:
    """출력 자세 파트들을 X 방향으로 나란히 배치한다 (겹치지 않게)."""
    placed: list[ExportPart] = []
    cursor = 0.0
    for part in parts:
        m = part.mesh.copy()
        lo, hi = m.bounds
        m.apply_translation([cursor - lo[0], -(lo[1] + hi[1]) / 2, -lo[2]])
        cursor += (hi[0] - lo[0]) + spacing_mm
        placed.append(ExportPart(part.name, m))
    return placed


def threemf_bytes(parts: list[ExportPart], spacing_mm: float = 10.0) -> bytes:
    scene = trimesh.Scene()
    for part in arrange_on_plate(parts, spacing_mm):
        scene.add_geometry(part.mesh, node_name=part.name, geom_name=part.name)
    return trimesh.exchange.threemf.export_3MF(scene)


def export_parts(
    parts: list[ExportPart], fmt: str, base_name: str, spacing_mm: float = 10.0
) -> ExportFile:
    if not parts:
        raise ValueError("내보낼 파트가 없습니다")
    if fmt == "stl":
        if len(parts) == 1:
            return ExportFile(f"{base_name}.stl", "model/stl", stl_bytes(parts[0].mesh))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for part in parts:
                zf.writestr(f"{part.name}.stl", stl_bytes(part.mesh))
        return ExportFile(f"{base_name}_stl.zip", "application/zip", buf.getvalue())
    if fmt == "3mf":
        return ExportFile(
            f"{base_name}.3mf",
            "model/3mf",
            threemf_bytes(parts, spacing_mm),
        )
    raise ValueError(f"지원하지 않는 형식입니다: {fmt}")
