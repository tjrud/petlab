from __future__ import annotations

import itertools

import pytest

from app.domain import Cage, PlacementHint
from app.layout.placer import place_all
from app.services.engine import build_item
from app.templates.hideout import HideoutParams, HideoutTemplate
from app.validation import checks
from tests.helpers import box_item

CAGE = Cage(600, 400, 300)


@pytest.fixture(scope="module")
def syrian(rules):
    return rules.size_rules("hamster", "syrian")


def _hideout(rules, index, hint, **kw):
    return build_item(index, HideoutTemplate(), HideoutParams(**kw), hint, rules.printing)


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
