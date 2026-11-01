"""테스트용 합성 항목 생성 도우미."""

from __future__ import annotations

import numpy as np
import trimesh

from app.domain import BuiltItem, Placement, PlacementHint, mesh_footprint
from app.geometry.mesh import to_print_orientation
from app.templates.base import Features


def make_item(
    index: int,
    mesh: trimesh.Trimesh,
    features: Features | None = None,
    placement: Placement | None = None,
    hint: PlacementHint | None = None,
    print_mesh: trimesh.Trimesh | None = None,
) -> BuiltItem:
    lo, hi = mesh.bounds
    mesh = mesh.copy()
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    return BuiltItem(
        index=index,
        key="test",
        features=features or Features(min_wall_thickness_mm=5.0),
        mesh=mesh,
        print_mesh=print_mesh if print_mesh is not None else to_print_orientation(mesh, np.eye(3)),
        footprint=mesh_footprint(mesh),
        hint=hint or PlacementHint(),
        placement=placement,
    )


def box_item(index: int, w: float, d: float, h: float, x: float | None = None, y: float | None = None,
             rot: int = 0, **kw) -> BuiltItem:
    placement = Placement(x, y, rot) if x is not None and y is not None else None
    return make_item(index, trimesh.creation.box((w, d, h)), placement=placement, **kw)
