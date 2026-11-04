from __future__ import annotations

import dataclasses
import itertools

import pytest

from app.domain import Cage, Placement, PlacementHint, access_strip
from app.layout.placer import _placed_at, place_all
from app.services.engine import build_item
from app.templates.base import Features
from app.templates.hideout import HideoutParams, HideoutTemplate
from app.validation import checks
from tests.helpers import box_item

CAGE = Cage(600, 400, 300)


@pytest.fixture(scope="module")
def syrian(rules):
    return rules.size_rules("hamster", "syrian")


def _hideout(rules, index, hint, **kw):
    return build_item(index, HideoutTemplate(), HideoutParams(**kw), hint, rules.printing)


def _placements(items):
    return {it.index: it.placement for it in items}


def _features(*sides):
    return Features(min_wall_thickness_mm=3, access_sides=sides)


def _safety_issues(items, size, cage=CAGE):
    return (checks.check_fit(items, cage) + checks.check_overlap(items)
            + checks.check_gaps(items, cage, size) + checks.check_access(items, cage, size))


def test_zone_left_touches_left_wall_and_entrance_is_clear(rules, syrian):
    it = _hideout(rules, 0, PlacementHint(zone="left"), entrance_diameter_mm=75, width_mm=170)
    assert place_all([it], CAGE, syrian.gap_trap) == []
    x0, y0, x1, y1 = it.world_footprint.bounds
    assert x0 == pytest.approx(0)
    assert _safety_issues([it], syrian) == []


@pytest.mark.parametrize("zone", ["right", "back", "front_left", "back_right", "center"])
def test_zones_move_items_toward_target(rules, syrian, zone):
    it = _hideout(rules, 0, PlacementHint(zone=zone), entrance_diameter_mm=75, width_mm=170)
    place_all([it], CAGE, syrian.gap_trap)
    cx, cy = it.placement.x_mm, it.placement.y_mm
    if "right" in zone:
        assert cx > CAGE.width_mm / 2
    if "left" in zone:
        assert cx < CAGE.width_mm / 2
    if "back" in zone:
        assert cy > CAGE.depth_mm / 2
    if "front" in zone:
        assert cy < CAGE.depth_mm / 2
    assert _safety_issues([it], syrian) == []


def test_group_items_are_adjacent(rules, syrian):
    a = _hideout(rules, 0, PlacementHint(zone="left", group="g"), entrance_diameter_mm=75, width_mm=170)
    b = box_item(1, 120, 80, 60, hint=PlacementHint(zone="left", group="g"))
    assert place_all([a, b], CAGE, syrian.gap_trap) == []
    assert a.world_rect.distance(b.world_rect) == pytest.approx(0, abs=1e-6)
    assert _safety_issues([a, b], syrian) == []


def test_many_items_never_create_trap_gaps(rules, syrian):
    items = [
        box_item(0, 150, 100, 60),
        box_item(1, 90, 90, 60, hint=PlacementHint(zone="right")),
        box_item(2, 120, 60, 40, hint=PlacementHint(zone="back")),
        _hideout(rules, 3, PlacementHint(zone="front_left"), entrance_diameter_mm=75, width_mm=170),
    ]
    failed = place_all(items, CAGE, syrian.gap_trap)
    assert failed == []
    assert _safety_issues(items, syrian) == []
    for a, b in itertools.combinations(items, 2):
        assert not a.world_rect.intersects(b.world_rect)


def test_rotation_hint_is_respected(rules, syrian):
    it = _hideout(rules, 0, PlacementHint(zone="center", rotation=90), entrance_diameter_mm=75, width_mm=170)
    place_all([it], CAGE, syrian.gap_trap)
    assert it.placement.rotation_deg == 90


def test_too_large_item_cannot_be_placed(syrian):
    it = box_item(0, 700, 100, 50)
    assert place_all([it], CAGE, syrian.gap_trap) == [it]
    assert it.placement is None


def test_placement_is_deterministic(rules, syrian):
    def run():
        items = [
            _hideout(rules, 0, PlacementHint(zone="left", group="g"), entrance_diameter_mm=75, width_mm=170),
            box_item(1, 120, 80, 60, hint=PlacementHint(group="g")),
            box_item(2, 100, 100, 60),
        ]
        place_all(items, CAGE, syrian.gap_trap)
        return [it.placement for it in items]

    assert run() == run()


# ── 배치 결과 고정 (골든) ──────────────────────────────────
# 배치기 내부를 바꿔도 결과 좌표가 그대로인지 Placement 를 정확히(==) 비교한다.


@pytest.mark.parametrize("size,cage,failed,expected", [
    ("syrian", Cage(600, 400, 300), [4], {
        0: Placement(85.0, 200.0, 0), 1: Placement(230.0, 110.0, 0), 2: Placement(460.0, 355.0, 90),
        3: Placement(410.0, 50.0, 0), 4: None}),
    ("dwarf", Cage(537.3, 401.7, 300), [], {
        0: Placement(85.0, 200.85, 0), 1: Placement(60.0, 300.85, 0), 2: Placement(417.3, 356.7, 90),
        3: Placement(220.0, 301.7, 0), 4: Placement(295.0, 125.0, 0)}),
])
def test_golden_box_placements(rules, size, cage, failed, expected):
    """zone·group·회전 힌트, 출입 방향, 정수가 아닌 케이지 크기, 배치 실패를 한 번에 거친다."""
    gap = rules.size_rules("hamster", size).gap_trap
    items = [
        box_item(0, 170, 120, 60, hint=PlacementHint(zone="left", group="g"), features=_features("front")),
        box_item(1, 120, 80, 60, hint=PlacementHint(group="g"), features=_features("right")),
        box_item(2, 90, 140, 40, hint=PlacementHint(zone="back_right", rotation=90),
                 features=_features("front", "back")),
        box_item(3, 100, 100, 60),
        box_item(4, 250, 250, 60),
    ]
    assert [it.index for it in place_all(items, cage, gap)] == failed
    assert _placements(items) == expected


def test_golden_template_placements(rules, syrian):
    """은신처 템플릿이 섞인 배치. 값은 uv.lock 의 OCP 테셀레이션에 따른 것이라
    템플릿 build() 를 의도적으로 바꾸면 다시 뽑아야 한다."""
    grouped = [
        _hideout(rules, 0, PlacementHint(zone="left", group="g"), entrance_diameter_mm=75, width_mm=170),
        box_item(1, 120, 80, 60, hint=PlacementHint(group="g")),
        box_item(2, 100, 100, 60),
    ]
    assert place_all(grouped, CAGE, syrian.gap_trap) == []
    assert _placements(grouped) == {
        0: Placement(85.0, 200.0, 0), 1: Placement(230.0, 110.0, 0), 2: Placement(290.0, 350.0, 0)}
    many = [
        box_item(0, 150, 100, 60),
        box_item(1, 90, 90, 60, hint=PlacementHint(zone="right")),
        box_item(2, 120, 60, 40, hint=PlacementHint(zone="back")),
        _hideout(rules, 3, PlacementHint(zone="front_left"), entrance_diameter_mm=75, width_mm=170),
    ]
    assert place_all(many, CAGE, syrian.gap_trap) == []
    assert _placements(many) == {
        0: Placement(75.0, 220.0, 0), 1: Placement(555.0, 200.0, 0),
        2: Placement(300.0, 370.0, 0), 3: Placement(55.0, 85.0, 90)}


def test_place_all_overwrites_prior_placements(syrian):
    """이미 위치가 있는 항목도 새 결과로 덮어쓰고, 놓지 못한 항목은 None 이 된다."""
    items = [box_item(0, 170, 120, 60, x=1, y=1, hint=PlacementHint(zone="left")),
             box_item(1, 700, 100, 50, x=1, y=1)]
    assert place_all(items, CAGE, syrian.gap_trap) == [items[1]]
    assert _placements(items) == {0: Placement(85.0, 200.0, 0), 1: None}


@pytest.mark.parametrize("placement", [
    Placement(85.0, 200.85, 0), Placement(417.3, 356.7, 90),
    Placement(0.1, 0.2, 180), Placement(300.0000002367581, 47.08098861837907, 270),
])
def test_placed_at_matches_world_rect_exactly(syrian, placement):
    """후보 탐색용 사각형·출입 공간이 실제로 그 위치에 둔 world_rect 와 비트 단위로 같고,
    item.placement 는 건드리지 않는다 (골든 테스트의 허용 오차로는 1 ulp 차이를 볼 수 없다)."""
    P = syrian.gap_trap.passable_min_mm
    prior = Placement(1, 1, 0)
    it = box_item(0, 90.3, 140.7, 40, x=prior.x_mm, y=prior.y_mm, features=_features("front", "left"))
    got = _placed_at(it, placement, P)
    rect = dataclasses.replace(it, placement=placement).world_rect
    assert got.rect == rect
    assert got.strips == tuple(access_strip(rect, dv, P) for dv in it.access_directions(placement.rotation_deg))
    assert len(got.strips) == 2
    assert it.placement == prior
