"""마주 보는 면 사이 틈(assembly.slot_gaps) 검사.

상자 사이 거리(internal_gaps)는 은신처 앞 열린 모서리를 사이에 둔 그릇 받침·물병 거치대와 터널을 끼임 틈으로 잘못 센다.
slot_gaps 는 겉면에서 바깥으로 쏜 광선이 상대 부품의 마주 보는 면에 끼임 위험 구간 거리로 닿을 때만 틈으로 본다."""

from __future__ import annotations

import time

import numpy as np
import pytest
import trimesh

from app.modules.assembly import JoinSpec, PartSpec, part_meshes, slot_gaps
from app.rules.loader import GapTrapRule
from app.templates.registry import primitives

P = primitives()


def _part(pid: str, key: str, **kw: object) -> PartSpec:
    t = P[key]
    return PartSpec(pid, t, t.Params.model_validate({**t.default_params().model_dump(), **kw}))


def _gap(rules, size: str = "dwarf") -> GapTrapRule:
    return rules.size_rules("hamster", size).gap_trap


def _box_parts(*ids: str) -> list[PartSpec]:
    """합성 상자 메시용 자리 표시 부품 (slot_gaps 는 부품 id 와 연결만 본다)."""
    return [_part(pid, "hideout") for pid in ids]


def _box_gaps(meshes: dict[str, trimesh.Trimesh], joins: list[JoinSpec]) -> dict[frozenset, float]:
    """예전 검사(상자 사이 거리)가 재던 값: 잇지 않은 쌍마다 축 정렬 상자 사이 거리."""
    joined = {frozenset((j.parent, j.child)) for j in joins}
    ids = list(meshes)
    out = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if frozenset((a, b)) not in joined:
                (alo, ahi), (blo, bhi) = meshes[a].bounds, meshes[b].bounds
                out[frozenset((a, b))] = float(np.linalg.norm(np.maximum(0.0, np.maximum(blo - ahi, alo - bhi))))
    return out


def _box(lo: tuple[float, float, float], hi: tuple[float, float, float]) -> trimesh.Trimesh:
    lo_, hi_ = np.asarray(lo, float), np.asarray(hi, float)
    return trimesh.creation.box(extents=hi_ - lo_, transform=trimesh.transformations.translation_matrix((lo_ + hi_) / 2))


# ── 설계 예시: 은신처 + 오른쪽 그릇 받침 + 왼쪽 물병 거치대 + 앞 터널(끼움) + 터널 끝 은신처 ──

@pytest.fixture(scope="module")
def combo() -> tuple[list[PartSpec], list[JoinSpec], dict[str, trimesh.Trimesh]]:
    parts = [
        _part("hide", "hideout", width_mm=140, depth_mm=120, height_mm=95, entrance_diameter_mm=60, entrance_count=2),
        _part("bowl", "bowl_holder", bowl_diameter_mm=90, bowl_height_mm=40, collar_height_mm=35),
        _part("bottle", "bottle_stand", base_width_mm=110, base_depth_mm=110),
        _part("tube", "tunnel", length_mm=100, inner_diameter_mm=60, shape="round_arch", bend_angle_deg=0),
        _part("hide2", "hideout", width_mm=140, depth_mm=120, height_mm=95, entrance_diameter_mm=60, entrance_count=2),
    ]
    joins = [
        JoinSpec("hide", "right", "bowl", "back", mount="slide"),
        JoinSpec("hide", "left", "bottle", "back", mount="slide"),
        JoinSpec("hide", "front", "tube", "end_b", passage=True, mount="plug"),
        JoinSpec("tube", "end_a", "hide2", "front", passage=True, mount="plug", reverse=True),
    ]
    return parts, joins, part_meshes(parts, joins)


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_combo_example_has_no_slot_gap(rules, combo, size: str) -> None:
    parts, joins, meshes = combo
    gt = _gap(rules, size)
    assert slot_gaps(parts, joins, meshes, gt) == []
    # 상자 거리로는 열린 모서리 너머 거리(약 42mm·41mm)를 틈으로 잘못 센다
    boxed = {k: round(g, 1) for k, g in _box_gaps(meshes, joins).items() if gt.is_trap(g)}
    assert boxed == {frozenset(("bowl", "tube")): 42.2, frozenset(("bottle", "tube")): 41.0}


def test_combo_example_within_budget(rules, combo) -> None:
    parts, joins, meshes = combo
    gt = _gap(rules)
    slot_gaps(parts, joins, meshes, gt)  # 첫 호출 준비(가져오기 등)는 빼고 잰다
    t0 = time.perf_counter()
    slot_gaps(parts, joins, meshes, gt)
    assert time.perf_counter() - t0 < 1.5


def test_deterministic(rules) -> None:
    gt = _gap(rules)
    parts2 = [_part("hide", "hideout", depth_mm=200), _part("b1", "bowl_holder", bowl_diameter_mm=60),
              _part("b2", "bowl_holder", bowl_diameter_mm=60)]
    joins2 = [JoinSpec("hide", "right", "b1", "back", mount="slide", shift=-40),
              JoinSpec("hide", "right", "b2", "back", mount="slide", shift=40)]
    meshes2 = part_meshes(parts2, joins2)
    assert slot_gaps(parts2, joins2, meshes2, gt) == slot_gaps(parts2, joins2, meshes2, gt)


# ── 합성 상자 ──

def test_parallel_slot_flagged(rules) -> None:
    gt = _gap(rules)
    meshes = {"a": _box((0, 0, 0), (100, 100, 60)), "b": _box((120, 0, 0), (220, 100, 60))}
    out = slot_gaps(_box_parts("a", "b"), [], meshes, gt)
    assert len(out) == 1
    a, b, g = out[0]
    assert {a, b} == {"a", "b"}
    assert g == pytest.approx(20.0, abs=0.05)


def test_joined_pair_not_flagged(rules) -> None:
    meshes = {"a": _box((0, 0, 0), (100, 100, 60)), "b": _box((120, 0, 0), (220, 100, 60))}
    joins = [JoinSpec("a", "right", "b", "left")]
    assert slot_gaps(_box_parts("a", "b"), joins, meshes, _gap(rules)) == []


@pytest.mark.parametrize("width", [2.0, 55.0])
def test_slot_outside_trap_band_not_flagged(rules, width: float) -> None:
    # 2mm: 다리가 들어가지 않는 틈, 55mm: 몸이 지나가는 틈 (쇠 햄스터 4~50mm)
    gt = _gap(rules)
    assert not gt.is_trap(width)
    meshes = {"a": _box((0, 0, 0), (100, 100, 60)), "b": _box((100 + width, 0, 0), (200 + width, 100, 60))}
    assert slot_gaps(_box_parts("a", "b"), [], meshes, gt) == []


def test_corners_40mm_apart_not_flagged(rules) -> None:
    gt = _gap(rules)
    d = 40 / np.sqrt(2)
    meshes = {"a": _box((0, 0, 0), (100, 100, 60)), "b": _box((100 + d, 100 + d, 0), (200 + d, 200 + d, 60))}
    parts = _box_parts("a", "b")
    # 상자 거리로는 40mm 끼임 틈이지만 마주 보는 면이 없다
    assert [round(g, 1) for g in _box_gaps(meshes, []).values()] == [40.0]
    assert slot_gaps(parts, [], meshes, gt) == []


def test_filled_slot_not_flagged(rules) -> None:
    """처음 닿는 부품이 상대가 아니면 세지 않는다: 두 상자 사이를 다른 부품이 메우면 틈이 아니다."""
    gt = _gap(rules)
    meshes = {"a": _box((0, 0, 0), (100, 100, 60)), "b": _box((120, 0, 0), (220, 100, 60)),
              "fill": _box((100, 0, 0), (120, 100, 60))}
    joins = [JoinSpec("a", "right", "fill", "left"), JoinSpec("fill", "right", "b", "left")]
    assert slot_gaps(_box_parts("a", "b", "fill"), joins, meshes, gt) == []


def test_parts_without_mesh_skipped(rules) -> None:
    gt = _gap(rules)
    meshes = {"a": _box((0, 0, 0), (100, 100, 60)), "b": _box((120, 0, 0), (220, 100, 60))}
    out = slot_gaps(_box_parts("a", "b", "cut"), [], meshes, gt)
    assert [(a, b) for a, b, _ in out] == [("a", "b")]


# ── 한 면에 나란히 붙인 그릇 받침 둘 ──

def _twin_bowls(gap_mm: float) -> tuple[list[PartSpec], list[JoinSpec]]:
    parts = [_part("hide", "hideout", width_mm=140, depth_mm=200, height_mm=95),
             _part("b1", "bowl_holder", bowl_diameter_mm=60, bowl_height_mm=40, collar_height_mm=35),
             _part("b2", "bowl_holder", bowl_diameter_mm=60, bowl_height_mm=40, collar_height_mm=35)]
    width = part_meshes(parts[1:2], [])["b1"].extents[0]
    s = (width + gap_mm) / 2
    joins = [JoinSpec("hide", "right", "b1", "back", mount="slide", shift=-s),
             JoinSpec("hide", "right", "b2", "back", mount="slide", shift=s)]
    return parts, joins


def test_two_bowls_12mm_apart_flagged(rules) -> None:
    parts, joins = _twin_bowls(12.0)
    out = slot_gaps(parts, joins, part_meshes(parts, joins), _gap(rules))
    assert len(out) == 1
    a, b, g = out[0]
    assert {a, b} == {"b1", "b2"}
    assert g == pytest.approx(12.0, abs=0.5)


def test_two_bowls_60mm_apart_not_flagged(rules) -> None:
    parts, joins = _twin_bowls(60.0)
    assert slot_gaps(parts, joins, part_meshes(parts, joins), _gap(rules)) == []


def test_overlapping_filler_not_flagged(rules) -> None:
    """이은 부품이 겉면을 OVERLAP 만큼 덮어 묻으면 묻힌 면에서 쏜 광선은 세지 않는다."""
    meshes = {"a": _box((0, 0, 0), (100, 100, 60)), "b": _box((120, 0, 0), (220, 100, 60)),
              "fill": _box((99.7, 0, 0), (120.3, 100, 60))}
    joins = [JoinSpec("a", "right", "fill", "left"), JoinSpec("fill", "right", "b", "left")]
    assert slot_gaps(_box_parts("a", "b", "fill"), joins, meshes, _gap(rules)) == []


def test_first_hit_must_be_partner(rules) -> None:
    """두 상자 사이에 다른 판이 서 있으면 상자끼리가 아니라 상자와 판 사이가 틈이다."""
    meshes = {"a": _box((0, 0, 0), (100, 100, 60)), "b": _box((130, 0, 0), (230, 100, 60)),
              "plate": _box((110, -20, 0), (120, 120, 80))}
    out = slot_gaps(_box_parts("a", "b", "plate"), [], meshes, _gap(rules))
    assert sorted((a, b, round(g, 1)) for a, b, g in out) == [("a", "plate", 10.0), ("b", "plate", 10.0)]
