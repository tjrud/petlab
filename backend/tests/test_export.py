from __future__ import annotations

import io
import zipfile

import pytest
import trimesh

from app.geometry.export import ExportPart, arrange_on_plate, export_parts
from app.geometry.mesh import part_to_mesh, to_print_orientation
from app.templates.hideout import HideoutParams, HideoutTemplate

T = HideoutTemplate()


@pytest.fixture(scope="module")
def print_meshes():
    out = []
    for i, p in enumerate([HideoutParams(), HideoutParams(width_mm=100, depth_mm=90, vent_count=2)]):
        m = to_print_orientation(part_to_mesh(T.build(p)), T.print_rotation(p))
        out.append(ExportPart(f"part{i + 1}_hideout", m))
    return out


def test_single_stl_roundtrip(print_meshes):
    f = export_parts(print_meshes[:1], "stl", "design")
    assert f.filename == "design.stl"
    loaded = trimesh.load(io.BytesIO(f.content), file_type="stl")
    assert loaded.is_watertight
    assert loaded.volume == pytest.approx(print_meshes[0].mesh.volume, rel=1e-6)


def test_multi_stl_is_zip(print_meshes):
    f = export_parts(print_meshes, "stl", "design")
    assert f.filename.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(f.content)) as zf:
        names = sorted(zf.namelist())
        assert names == ["part1_hideout.stl", "part2_hideout.stl"]
        for n in names:
            m = trimesh.load(io.BytesIO(zf.read(n)), file_type="stl")
            assert m.is_watertight


def test_3mf_roundtrip_has_all_parts(print_meshes):
    f = export_parts(print_meshes, "3mf", "design")
    assert f.filename == "design.3mf"
    scene = trimesh.load(io.BytesIO(f.content), file_type="3mf")
    geoms = list(scene.geometry.values())
    assert len(geoms) == 2
    assert all(g.is_watertight for g in geoms)
    total = sum(g.volume for g in geoms)
    assert total == pytest.approx(sum(p.mesh.volume for p in print_meshes), rel=1e-4)


def test_plate_arrangement_does_not_overlap(print_meshes):
    placed = arrange_on_plate(print_meshes, spacing_mm=10)
    (lo1, hi1), (lo2, hi2) = placed[0].mesh.bounds, placed[1].mesh.bounds
    assert lo2[0] - hi1[0] == pytest.approx(10)
    assert lo1[2] == pytest.approx(0) and lo2[2] == pytest.approx(0)


def test_unknown_format_and_empty(print_meshes):
    with pytest.raises(ValueError):
        export_parts(print_meshes, "obj", "x")
    with pytest.raises(ValueError):
        export_parts([], "stl", "x")
