from __future__ import annotations

import dataclasses
import itertools

import pytest

from app.domain import Cage, Placement, PlacementHint, Rect, access_strip
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


# ── attach_to: 다른 구조물의 한 면에 맞대어 놓기 (2층 집의 바깥 램프) ──


def _house_with_landing(rules, index, hint=PlacementHint()):
    from app.templates.house import HouseTemplate
    t = HouseTemplate()
    p = t.Params(width_mm=160, depth_mm=130, height_mm=220,
                 floors={"count": 2, "climb": "external_ramp", "exit_side": "back", "level_height_mm": 110})
    return build_item(index, t, p, hint, rules.printing)


def _ramp(rules, index, attach_to, height=110.0):
    from app.templates.ramp import RampTemplate
    t = RampTemplate()
    return build_item(index, t, t.Params(height_mm=height, width_mm=80, slope_deg=30), PlacementHint(attach_to=attach_to),
                      rules.printing)


def test_attach_to_puts_ramp_top_against_landing(rules, syrian):
    from app.layout.placer import attach_satisfied

    cage = Cage(900, 500, 400)
    house = _house_with_landing(rules, 0, PlacementHint(zone="left"))
    ramp = _ramp(rules, 1, (0, "back"))
    assert place_all([house, ramp], cage, syrian.gap_trap) == []
    assert attach_satisfied(ramp, house, "back")
    # 램프의 뒷면(꼭대기)이 집의 뒷면(착지판 바깥면)에 닿고, 램프 앞(오르는 입구) 공간은 비어 있다
    assert ramp.world_rect.distance(house.world_rect) == pytest.approx(0, abs=1e-6)
    assert _safety_issues([house, ramp], syrian, cage) == []
    # 대상이 램프 자리를 남겨 두고 놓인다: 램프 전체가 케이지 안에 있다
    r = ramp.world_rect
    assert r.x0 >= -1e-6 and r.y0 >= -1e-6 and r.x1 <= cage.width_mm + 1e-6 and r.y1 <= cage.depth_mm + 1e-6


def test_attach_to_falls_back_when_there_is_no_room(rules, syrian):
    """붙일 자리가 없으면(케이지가 좁아 램프가 들어가지 않음) 일반 배치로 놓고 엔진이 경고를 낸다."""
    from app.layout.placer import attach_satisfied
    from app.services.engine import _attach_issues

    cage = Cage(300, 240, 400)
    house = _house_with_landing(rules, 0)
    ramp = _ramp(rules, 1, (0, "back"))
    failed = place_all([house, ramp], cage, syrian.gap_trap)
    assert house.placement is not None
    if ramp.placement is not None:
        assert not attach_satisfied(ramp, house, "back")
        [issue] = _attach_issues([house, ramp])
        assert issue.code == "attach_fallback" and issue.severity == "warning" and issue.item_index == 1
        assert issue.related_index == 0 and "붙일 자리가 없어" in issue.message_ko
    else:
        assert failed == [ramp]


def test_attach_to_missing_target_uses_normal_placement(rules, syrian):
    ramp = _ramp(rules, 1, (7, "back"))
    assert place_all([ramp], CAGE, syrian.gap_trap) == []
    assert ramp.placement is not None


def test_attach_rotation_and_rect():
    from app.layout.placer import attach_rect, attach_rotation

    # 대상이 0° 일 때 뒷면(+Y)에 붙으려면 이 항목의 뒷면이 −Y 를 봐야 하므로 180°
    assert attach_rotation("back", 0) == 180
    assert attach_rotation("front", 0) == 0
    assert attach_rotation("left", 0) == 270 or attach_rotation("left", 0) == 90
    it = box_item(0, 80, 120, 50)
    rot, rect = attach_rect(it, Rect(100, 100, 200, 160), "back", 0)
    assert rot == 180 and (rect.y0, rect.x0, rect.x1) == (160, 110, 190)
    rot, rect = attach_rect(it, Rect(100, 100, 200, 160), "right", 0)
    assert rect.x0 == 200 and rect.cy == 130


def test_two_access_sides_are_both_checked(rules, syrian):
    """출입구가 여러 면인 구조물(앞·뒤 출입구 집)은 모든 출입 면 앞 공간이 비어 있어야 놓인다."""
    from app.templates.house import HouseTemplate
    t = HouseTemplate()
    house = build_item(0, t, t.Params(width_mm=160, depth_mm=130, height_mm=110, doors={"sides": ["front", "back"]}),
                       PlacementHint(zone="back"), rules.printing)
    assert place_all([house], CAGE, syrian.gap_trap) == []
    assert set(house.features.access_sides) == {"front", "back"}
    assert checks.check_access([house], CAGE, syrian) == []
    # 두 출입 면 모두 벽에서 출입 공간(P)만큼 떨어진다 (한 면만 보면 벽에 붙여 버린다)
    P = syrian.gap_trap.passable_min_mm
    r = house.world_rect
    for dx, dy in house.access_directions(house.placement.rotation_deg):
        gap = {(0, -1): r.y0, (0, 1): CAGE.depth_mm - r.y1, (-1, 0): r.x0, (1, 0): CAGE.width_mm - r.x1}[(dx, dy)]
        assert gap >= P - 1e-6
