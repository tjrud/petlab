"""자동 검증: 의도적으로 나쁜 입력을 넣어 각 검사가 실제로 잡아내는지 확인한다."""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh
import yaml
from build123d import Align, Box, Pos

from app.domain import Cage, Placement
from app.geometry.mesh import part_to_mesh
from app.rules.loader import load_rules
from app.services.engine import build_item
from app.domain import PlacementHint
from app.templates.base import Features, Opening
from app.templates.hideout import HideoutParams, HideoutTemplate
from app.validation import checks
from tests.helpers import box_item, make_item

CAGE = Cage(600, 400, 300)


@pytest.fixture(scope="module")
def syrian(rules):
    return rules.size_rules("hamster", "syrian")


def codes(issues):
    return [i.code for i in issues]


# ── 케이지 적합 / 겹침 ─────────────────────────────────────


def test_out_of_cage_detected():
    it = box_item(0, 100, 100, 50, x=30, y=200)  # 왼쪽으로 20mm 삐져나옴
    assert "out_of_cage" in codes(checks.check_fit([it], CAGE))


def test_inside_cage_ok():
    it = box_item(0, 100, 100, 50, x=50, y=50)
    assert checks.check_fit([it], CAGE) == []


def test_too_tall_detected():
    it = box_item(0, 100, 100, 350, x=100, y=100)
    assert "too_tall" in codes(checks.check_fit([it], CAGE))


def test_unplaced_item_reported():
    it = box_item(0, 100, 100, 50)  # placement 없음
    assert "cannot_place" in codes(checks.check_fit([it], CAGE))


def test_overlap_detected():
    a = box_item(0, 100, 100, 50, x=100, y=100)
    b = box_item(1, 100, 100, 50, x=150, y=100)  # 50mm 겹침
    issues = checks.check_overlap([a, b])
    assert codes(issues) == ["overlap"]
    assert issues[0].details["area_mm2"] == pytest.approx(5000, rel=1e-3)


def test_touching_is_not_overlap():
    a = box_item(0, 100, 100, 50, x=100, y=100)
    b = box_item(1, 100, 100, 50, x=200, y=100)
    assert checks.check_overlap([a, b]) == []


# ── 끼임 틈새 ──────────────────────────────────────────────


@pytest.mark.parametrize("gap,trap", [(0, False), (3, False), (20, True), (69, True), (80, False)])
def test_gap_between_items(syrian, gap, trap):
    # 시리안 임시 기준: safe_max 5mm, passable_min 70mm
    a = box_item(0, 100, 100, 50, x=200, y=200)
    b = box_item(1, 100, 100, 50, x=300 + gap, y=200)
    issues = [i for i in checks.check_gaps([a, b], CAGE, syrian) if i.code == "gap_trap"]
    assert bool(issues) is trap


def test_gap_to_wall(syrian):
    it = box_item(0, 100, 100, 50, x=70, y=50)  # 왼쪽 벽과 20mm, 앞 벽과 0mm
    issues = checks.check_gaps([it], CAGE, syrian)
    walls = [i.details["wall"] for i in issues if i.code == "gap_trap_wall"]
    assert walls == ["왼쪽"]


def test_gap_to_ceiling(syrian):
    it = box_item(0, 100, 100, CAGE.height_mm - 30, x=50, y=50)
    assert "gap_trap_ceiling" in codes(checks.check_gaps([it], CAGE, syrian))


def test_species_file_swap_changes_gap_verdict(rules_copy, syrian):
    """전문가 검수로 species.yaml 의 passable_min 이 바뀌면 같은 배치의 판정이 달라진다."""
    a = box_item(0, 100, 100, 50, x=200, y=200)
    b = box_item(1, 100, 100, 50, x=340, y=200)  # 틈 40mm
    assert "gap_trap" in codes(checks.check_gaps([a, b], CAGE, syrian))

    p = rules_copy / "species.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data["species"]["hamster"]["sizes"]["syrian"]["gap_trap"]["passable_min_mm"] = 35
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    swapped = load_rules(rules_copy).size_rules("hamster", "syrian")
    assert "gap_trap" not in codes(checks.check_gaps([a, b], CAGE, swapped))


# ── 출입구 ────────────────────────────────────────────────


def _hideout(rules, index=0, rot=0, x=None, y=None, **kw):
    t = HideoutTemplate()
    it = build_item(index, t, HideoutParams(**kw), PlacementHint(), rules.printing)
    if x is not None:
        it.placement = Placement(x, y, rot)
    return it


def test_entrance_facing_wall_is_blocked(rules, syrian):
    # 회전 0° → 출입구가 앞(-Y)을 향함. 앞 벽에 붙이면 막힘.
    it = _hideout(rules, x=300, y=55, width_mm=140, depth_mm=110, entrance_diameter_mm=75)
    assert "access_blocked" in codes(checks.check_access([it], CAGE, syrian))


def test_entrance_facing_open_space_ok(rules, syrian):
    # 출입구 1개, 회전 180° → 출입구가 뒤(+Y)를 향함. 앞 벽에 붙여도 출입구 앞은 비어 있음.
    it = _hideout(rules, rot=180, x=300, y=55, width_mm=140, depth_mm=110, entrance_diameter_mm=75,
                  entrance_count=1)
    assert checks.check_access([it], CAGE, syrian) == []


def test_entrance_blocked_by_other_item(rules, syrian):
    it = _hideout(rules, rot=180, x=300, y=55, width_mm=140, depth_mm=110, entrance_diameter_mm=75,
                  entrance_count=1)
    blocker = box_item(1, 140, 40, 50, x=300, y=130)
    issues = checks.check_access([it, blocker], CAGE, syrian)
    assert codes(issues) == ["access_blocked"]


# ── 개구부 / 오르기 / 마릿수 ────────────────────────────────


def test_small_entrance_and_large_vent(rules, syrian):
    it = _hideout(rules, entrance_diameter_mm=50, vent_diameter_mm=8, vent_count=4)
    assert set(codes(checks.check_openings([it], syrian))) == {"opening_too_small", "vent_too_large"}


def test_climb_rules(syrian):
    f = Features(min_wall_thickness_mm=5, climb_height_mm=500, slope_deg=50, step_height_mm=100)
    it = box_item(0, 50, 50, 50, x=100, y=100, features=f)
    assert set(codes(checks.check_climb([it], syrian))) == {"climb_too_high", "slope_too_steep", "step_too_high"}


def test_count_warning(syrian):
    assert checks.check_count(1, syrian) == []
    issues = checks.check_count(2, syrian)
    assert issues[0].severity == "warning" and syrian.count_warning_ko in issues[0].message_ko


def test_single_entrance_hideout_flagged(rules, syrian):
    """DTSchB 근거: 출입구가 하나뿐인 은신처는 막다른 곳이 되므로 오류."""
    one = _hideout(rules, entrance_diameter_mm=75, entrance_count=1)
    two = _hideout(rules, entrance_diameter_mm=75, entrance_count=2)
    assert codes(checks.check_openings([one], syrian)) == ["too_few_entrances"]
    assert checks.check_openings([two], syrian) == []


def test_two_entrance_hideout_prints_without_support(rules):
    it = _hideout(rules, x=300, y=200, entrance_diameter_mm=75, entrance_count=2)
    assert checks.check_overhang([it], rules.printing) == []


@pytest.mark.parametrize("w,d,warn", [(1000, 500, False), (500, 1000, False), (1200, 600, False),
                                      (999, 500, True), (1000, 499, True), (600, 400, True)])
def test_cage_below_recommended_warning(syrian, w, d, warn):
    """TVT 근거: 사육장 바닥 최소 100×50cm. 방향과 무관하게 긴 변·짧은 변끼리 비교하고 경고만 한다."""
    issues = checks.check_enclosure(Cage(w, d, 300), syrian)
    assert codes(issues) == (["cage_below_recommended"] if warn else [])
    assert all(i.severity == "warning" for i in issues)


# ── 벽 두께 ────────────────────────────────────────────────


def test_thin_designed_wall_detected(rules):
    it = _hideout(rules, wall_thickness_mm=1.0)
    issues = checks.check_wall_thickness([it], rules.min_wall_for("hamster", "syrian"))
    assert codes(issues) == ["wall_too_thin"]


def test_measured_thin_mesh_detected():
    """설계값은 5mm 라고 주장하지만 실제 메시는 1mm 판인 경우 측정으로 잡아낸다."""
    plate = box_item(0, 100, 100, 1, x=100, y=100, features=Features(min_wall_thickness_mm=5))
    issues = checks.check_wall_thickness([plate], 3.0)
    assert codes(issues) == ["wall_thin_measured"]
    assert issues[0].details["measured_p1_mm"] == pytest.approx(1.0, abs=0.05)


def test_hideout_measured_thickness_matches_design(rules):
    it = _hideout(rules, wall_thickness_mm=3.0)
    t = checks.measure_thickness(it.mesh)
    assert np.percentile(t, 1) == pytest.approx(3.0, abs=0.05)
    assert checks.check_wall_thickness([it], 3.0) == []


# ── 오버행 / 서포트 ─────────────────────────────────────────


def _frustum(top_offset: float, h: float = 20.0) -> trimesh.Trimesh:
    """아래 20×20, 위로 갈수록 top_offset 만큼 벌어지는 역사다리꼴 (옆면 오버행)."""
    b, t = 10.0, 10.0 + top_offset
    pts = [(-b, -b, 0), (b, -b, 0), (b, b, 0), (-b, b, 0), (-t, -t, h), (t, -t, h), (t, t, h), (-t, t, h)]
    return trimesh.convex.convex_hull(np.array(pts))


@pytest.mark.parametrize("angle,flag", [(30, False), (44, False), (60, True)])
def test_overhang_angle_threshold(rules, angle, flag):
    h = 20.0
    m = _frustum(h * math.tan(math.radians(angle)), h)
    it = make_item(0, m, placement=Placement(100, 100, 0))
    assert bool(checks.check_overhang([it], rules.printing)) is flag


def test_t_shape_needs_support(rules):
    stem = Box(10, 10, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))
    plate = Pos(0, 0, 30) * Box(60, 60, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
    m = part_to_mesh(stem + plate)
    it = make_item(0, m)
    issues = checks.check_overhang([it], rules.printing)
    assert codes(issues) == ["support_needed"]
    assert issues[0].details["overhang_area_mm2"] == pytest.approx(60 * 60 - 10 * 10, rel=1e-3)


def test_hideout_print_orientation_needs_no_support(rules):
    it = _hideout(rules)
    assert checks.check_overhang([it], rules.printing) == []
    # 뒤집지 않고 그대로 출력하면 지붕 안쪽 천장이 오버행 → 출력 자세 설계가 의미 있음을 확인
    upright = make_item(0, it.mesh, print_mesh=it.mesh)
    assert codes(checks.check_overhang([upright], rules.printing)) == ["support_needed"]


def test_build_volume(rules):
    big = box_item(0, 300, 100, 50, x=200, y=100)
    assert codes(checks.check_build_volume([big], rules.printing)) == ["exceeds_build_volume"]
    rotated_fits = box_item(0, 100, 215, 50, x=200, y=200)
    assert checks.check_build_volume([rotated_fits], rules.printing) == []


# ── 메시 건전성 ─────────────────────────────────────────────


def test_open_mesh_detected():
    m = trimesh.creation.box((50, 50, 50))
    holed = trimesh.Trimesh(m.vertices, m.faces[1:], process=False)  # 삼각형 하나 제거
    it = make_item(0, holed, placement=Placement(100, 100, 0))
    issues = checks.check_mesh([it])
    assert codes(issues) == ["mesh_invalid"]
    assert issues[0].details["watertight"] is False


def test_good_mesh_passes(rules):
    assert checks.check_mesh([_hideout(rules)]) == []
