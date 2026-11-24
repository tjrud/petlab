"""조립 해석기 (app/modules/compose): 결합 표, 옮기기·출입구 내기·터널 넣기, 맞물리는 치수, 조립 항목 제약,
라이브러리에서 옮긴 고정 데이터(tests/data/compositions), 무작위 조립.

형상 검사(rule_issues)는 고정 데이터·5부품 예·무작위 조립에서만 돌린다 (나머지는 형상 없이 연결 지점만 본다)."""

from __future__ import annotations

import dataclasses
import json
import random
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules import compose
from app.modules.composed import ComposedTemplate
from app.modules.structure import MAX_PARTS, AssemblyRequest, ResolvedAssembly
from app.templates.base import RuleContext, TemplateParams
from app.templates.registry import primitives
from app.validation.autofix import clamp_params
from app.validation.report import Issue, Severity

FIXTURES = Path(__file__).parent / "data" / "compositions"
FIXTURE_KEYS = sorted(p.stem for p in FIXTURES.glob("*.json"))
P = primitives()
SIZES = ("dwarf", "syrian")
# 무작위 조립이 끝날 수 있는 오류 (해석 오류, 보정할 수 없는 값, 규칙·형상 위반)
KNOWN_ERRORS = {*compose.ERROR_CODES, "param_conflict", "rule_violation"}


def rctx(rules, size: str, count: int = 1) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), count,
                       printing_max_overhang_deg=rules.printing.max_overhang_deg,
                       min_feature_mm=rules.printing.min_feature_mm)


@pytest.fixture(scope="module")
def dwarf(rules) -> RuleContext:
    return rctx(rules, "dwarf")


@pytest.fixture(scope="module")
def syrian(rules) -> RuleContext:
    return rctx(rules, "syrian")


def dp(key: str, ctx: RuleContext | None = None, **over) -> dict:
    """템플릿 기본값 (ctx 의 종 기준) + 덮어쓸 값."""
    return {**P[key].default_params(ctx).model_dump(), **over}


def request(parts: list[tuple], conns: list[tuple]) -> AssemblyRequest:
    return AssemblyRequest(parts=[{"id": a, "template": b, "params": c} for a, b, c in parts],
                           connections=[{"part": a, "to": b, "at": c} for a, b, c in conns])


def resolve_ok(req: AssemblyRequest, ctx: RuleContext) -> tuple[ResolvedAssembly, dict, list[Issue]]:
    out = compose.resolve(req, None, ctx)
    assert not isinstance(out, Issue), out.message_ko
    return out


def resolve_err(req: AssemblyRequest, ctx: RuleContext) -> Issue:
    out = compose.resolve(req, None, ctx)
    assert isinstance(out, Issue), f"오류여야 합니다: {out[0].stored()}"
    assert out.severity == Severity.error
    return out


def settle(res: ResolvedAssembly, params: dict, ctx: RuleContext, passes: int = compose.ASSEMBLY_MAX_PASSES,
           ) -> tuple[ComposedTemplate, TemplateParams, list[Issue]]:
    t = compose.template_for(res)
    p, issues = clamp_params(t, compose.assembly_params(t, params), ctx, max_passes=passes)
    return t, p, issues


def joins(res: ResolvedAssembly) -> list[tuple]:
    return [(j.parent, j.child, j.mount, j.passage) for j in res.joins]


def codes(issues: list[Issue]) -> list[str]:
    return [i.code for i in issues]


def errors(issues: list[Issue]) -> list[str]:
    return [i.message_ko for i in issues if i.severity == Severity.error]


HIDE = {"width_mm": 140, "depth_mm": 110, "height_mm": 90, "entrance_diameter_mm": 60, "entrance_count": 1,
        "vent_count": 6, "vent_diameter_mm": 4, "wall_thickness_mm": 3}
BOWL = {"bowl_diameter_mm": 90, "bowl_height_mm": 40, "clearance_mm": 1.0, "wall_thickness_mm": 3, "collar_height_mm": 30}
BOTTLE = {"bottle_diameter_mm": 60, "cap_diameter_mm": 40, "spout_height_mm": 55, "spout_drop_mm": 60,
          "holder_height_mm": 70, "base_width_mm": 110, "base_depth_mm": 110, "wall_thickness_mm": 3,
          "clearance_mm": 1.0}
TUBE = {"length_mm": 100, "inner_diameter_mm": 60, "bend_angle_deg": 0, "wall_thickness_mm": 3, "shape": "tube",
        "path": "arc"}


def combo() -> AssemblyRequest:
    """설계 문서의 5부품 예: 은신처 오른쪽 그릇 받침, 왼쪽 물병 거치대, 앞 터널, 터널 끝 두 번째 은신처."""
    return request(
        [("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL), ("bottle", "bottle_stand", BOTTLE),
         ("tube", "tunnel", TUBE), ("hide2", "hideout", HIDE)],
        [("bowl", "hide", "right"), ("bottle", "hide", "left"), ("tube", "hide", "front"), ("hide2", "tube", "free_end")],
    )


# ── 결합 표 ──


def test_row1_no_top_or_bottom_side() -> None:
    """위·아래 면은 at 에 없다 (위에 얹기는 2단계): 해석기 출력 검증이 막는다."""
    with pytest.raises(ValidationError):
        request([("hide", "hideout", HIDE), ("hide2", "hideout", HIDE)], [("hide2", "hide", "top")])


def test_row2_door_takes_tunnel_with_plug_tie_and_shape(dwarf) -> None:
    res, params, issues = resolve_ok(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE)],
                                             [("tube", "hide", "front")]), dwarf)
    assert joins(res) == [("hide.front", "tube.end_b", "plug", "into_parent")]
    assert [(t.follower, t.owner) for t in res.ties] == [("tube.inner_diameter_mm", "hide.entrance_diameter_mm")]
    assert res.fixed["tube.shape"] == "round_arch" and params["tube"].shape == "round_arch"
    assert res.faces == {"tube": "front"}
    # 관 → 둥근 아치 안내, 앞 출입구를 통로로 써서 뒤에 출입구를 더 낸다
    shape = next(i for i in issues if i.code == "passage_shape_matched")
    assert shape.details == {"part": "tube", "from": "tube", "to": "round_arch"}
    assert "exit_added" in codes(issues) and res.fixed["hide.entrance_count"] == 2
    assert all(i.severity == Severity.info and i.details.get("part") for i in issues)


def test_row3_room_on_tunnel_end_is_into_child(dwarf) -> None:
    res, _, _ = resolve_ok(combo(), dwarf)
    assert joins(res) == [
        ("hide.right", "bowl.back", "slide", False),
        ("hide.left", "bottle.back", "slide", False),
        ("hide.front", "tube.end_b", "plug", "into_parent"),
        ("tube.end_a", "hide2.front", "plug", "into_child"),
    ]
    # 터널 끝의 방은 주인 값(첫 은신처 출입구)을 따른다 (터널 내경을 거치지 않는다)
    assert {t.follower: t.owner for t in res.ties} == {
        "tube.inner_diameter_mm": "hide.entrance_diameter_mm",
        "hide2.entrance_diameter_mm": "hide.entrance_diameter_mm",
    }
    assert res.fixed == {"tube.shape": "round_arch", "hide.entrance_count": 2, "hide.side_doors": "none",
                         "hide2.entrance_count": 2, "hide2.side_doors": "none"}
    assert res.faces == {"bowl": "right", "bottle": "left", "tube": "front", "hide2": "free_end"}


@pytest.mark.parametrize("at", ["front", "right"])
def test_row4_room_on_room_inserts_tunnel(dwarf, at) -> None:
    res, params, issues = resolve_ok(request([("hide", "hideout", HIDE), ("hide2", "hideout", HIDE)],
                                             [("hide2", "hide", at)]), dwarf)
    assert res.part_ids == ["hide", "hide2_link", "hide2"]
    assert joins(res) == [(f"hide.{at}", "hide2_link.end_b", "plug", "into_parent"),
                          ("hide2_link.end_a", "hide2.front", "plug", "into_child")]
    assert res.faces == {"hide2_link": at, "hide2": "free_end"}
    inserted = next(i for i in issues if i.code == "tunnel_inserted")
    assert inserted.details == {"part": "hide2_link", "parent": "hide", "child": "hide2"}
    # 옆면에는 옆면 출입구를 내고 그 자리에 잇는다 (옮기지 않는다)
    assert "join_relocated" not in codes(issues)
    assert ("port_opened" in codes(issues)) == (at == "right")
    assert params["hide"].side_doors == ("right" if at == "right" else "none")
    link = params["hide2_link"]
    assert link.shape == "round_arch" and link.inner_diameter_mm == HIDE["entrance_diameter_mm"]
    _, p, adj = settle(res, params, dwarf)
    # 가장 짧은 터널: 내경의 1.5배 (필드 최소 80 보다 길다)
    assert p.hide2_link.length_mm == pytest.approx(1.5 * p.hide.entrance_diameter_mm)
    assert not errors(adj)


def test_row5_tunnel_on_tunnel_unsupported(dwarf) -> None:
    out = resolve_err(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE), ("tube2", "tunnel", TUBE)],
                              [("tube", "hide", "front"), ("tube2", "tube", "free_end")]), dwarf)
    assert out.code == "join_unsupported" and out.details["part"] == "tube2"


def test_row6_plain_wall_opens_port_or_relocates(dwarf) -> None:
    # 뒷면(출입구 1개면 벽): 출입구를 2개로 늘려 잇는다
    res, params, issues = resolve_ok(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE)],
                                             [("tube", "hide", "back")]), dwarf)
    assert joins(res) == [("hide.back", "tube.end_b", "plug", "into_parent")]
    assert params["hide"].entrance_count == 2 and res.fixed["hide.entrance_count"] == 2
    opened = next(i for i in issues if i.code == "port_opened")
    assert opened.details["part"] == "hide" and opened.details["anchor"] == "back"
    assert "exit_added" not in codes(issues)  # 앞 출입구가 비어 있다
    # 옆면: 옆면 출입구를 내고 그 자리에 잇는다 (옮기지 않는다)
    res, params, issues = resolve_ok(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE)],
                                             [("tube", "hide", "left")]), dwarf)
    assert joins(res) == [("hide.left", "tube.end_b", "plug", "into_parent")] and res.faces["tube"] == "left"
    assert params["hide"].side_doors == "left" and res.fixed["hide.side_doors"] == "left"
    assert "join_relocated" not in codes(issues)
    opened = next(i for i in issues if i.code == "port_opened")
    assert opened.details["part"] == "hide" and opened.details["anchor"] == "left"
    # 네 면을 다 쓰면 더 이을 곳이 없다
    out = resolve_err(request([("hide", "hideout", HIDE), *[(f"t{i}", "tunnel", TUBE) for i in range(1, 6)]],
                              [("t1", "hide", "front"), ("t2", "hide", "back"), ("t3", "hide", "left"),
                               ("t4", "hide", "right"), ("t5", "hide", "left")]), dwarf)
    assert out.code == "face_unavailable" and out.details["part"] == "t5"


def test_row6_house_side_gets_a_port(dwarf) -> None:
    house = dp("house", dwarf)
    assert house["doors"]["sides"] == ["front"] and house["ports"]["sides"] == []
    res, params, issues = resolve_ok(request([("house", "house", house), ("tube", "tunnel", TUBE)],
                                             [("tube", "house", "left")]), dwarf)
    assert joins(res) == [("house.left", "tube.end_b", "plug", "into_parent")]
    assert params["house"].ports.sides == ["left"] and res.fixed["house.ports.sides"] == ["left"]
    assert res.fixed["tube.shape"] == "pointed_arch"
    assert [(t.follower, t.owner) for t in res.ties] == [("tube.inner_diameter_mm", "house.ports.diameter_mm")]
    assert "port_opened" in codes(issues)


def test_row7_side_takes_accessory_by_slide(dwarf) -> None:
    res, _, issues = resolve_ok(request([("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL)],
                                        [("bowl", "hide", "left")]), dwarf)
    assert joins(res) == [("hide.left", "bowl.back", "slide", False)]
    assert res.ties == [] and res.fixed == {} and res.faces == {"bowl": "left"} and issues == []
    # 출입구 1개 은신처의 뒷면은 드나드는 면이 아니라 벽이다
    res, _, issues = resolve_ok(request([("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL)],
                                        [("bowl", "hide", "back")]), dwarf)
    assert joins(res) == [("hide.back", "bowl.back", "slide", False)] and issues == []


def test_row8_accessory_moves_off_doors_and_access_sides(dwarf) -> None:
    res, _, issues = resolve_ok(request([("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL)],
                                        [("bowl", "hide", "front")]), dwarf)
    assert joins(res) == [("hide.right", "bowl.back", "slide", False)]
    assert next(i for i in issues if i.code == "join_relocated").details["to"] == "right"
    # 모래목욕통 앞(출입 면): 램프는 출입을 막지 않아 그대로, 그릇 받침은 옆으로
    bath = dp("sand_bath", dwarf)
    res, _, issues = resolve_ok(request([("bath", "sand_bath", bath), ("ramp", "ramp", dp("ramp", dwarf)),
                                         ("bowl", "bowl_holder", BOWL)],
                                        [("ramp", "bath", "front"), ("bowl", "bath", "front")]), dwarf)
    assert joins(res) == [("bath.front", "ramp.landing", "slide", False), ("bath.right", "bowl.back", "slide", False)]
    assert codes(issues) == ["join_relocated"]
    # 빈 연결판 면이 없으면 face_unavailable (출입구 2개 은신처: 옆면 둘을 이미 썼다)
    two = {**HIDE, "entrance_count": 2}
    out = resolve_err(request([("hide", "hideout", two), ("bowl", "bowl_holder", BOWL),
                               ("bottle", "bottle_stand", BOTTLE), ("bowl2", "bowl_holder", BOWL)],
                              [("bowl", "hide", "right"), ("bottle", "hide", "left"), ("bowl2", "hide", "back")]),
                      dwarf)
    assert out.code == "face_unavailable" and out.details["part"] == "bowl2"


def test_row9_unsupported_children_and_parents(dwarf) -> None:
    bath = dp("sand_bath", dwarf)
    out = resolve_err(request([("hide", "hideout", HIDE), ("bath", "sand_bath", bath)], [("bath", "hide", "right")]),
                      dwarf)
    assert out.code == "join_unsupported" and out.details["part"] == "bath"
    out = resolve_err(request([("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL), ("tube", "tunnel", TUBE)],
                              [("bowl", "hide", "right"), ("tube", "bowl", "front")]), dwarf)
    assert out.code == "join_unsupported" and out.details == {"part": "tube", "parent": "bowl"}
    # 터널은 방 출입구에만 (모래목욕통에는 출입구가 없다)
    out = resolve_err(request([("bath", "sand_bath", bath), ("tube", "tunnel", TUBE)], [("tube", "bath", "front")]),
                      dwarf)
    assert out.code == "join_unsupported"
    # 다른 부품과 잇지 않는 템플릿 (물속 동굴)
    out = resolve_err(request([("hide", "hideout", HIDE), ("cave", "cave", P["cave"].default_params().model_dump())],
                              [("cave", "hide", "right")]), dwarf)
    assert out.code == "join_unsupported" and out.details["part"] == "cave"


def test_tunnel_cannot_join_two_door_profiles(dwarf) -> None:
    """은신처(둥근 아치)와 집(뾰족 아치)을 한 터널로: 단면을 둘 다에 맞출 수 없다 (2단계 이음 부품)."""
    out = resolve_err(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE), ("house", "house", dp("house", dwarf))],
                              [("tube", "hide", "front"), ("house", "tube", "free_end")]), dwarf)
    assert out.code == "join_unsupported" and out.details["part"] == "tube"


def test_tunnel_as_root_owns_the_size(dwarf) -> None:
    res, _, issues = resolve_ok(request([("tube", "tunnel", TUBE), ("a", "hideout", HIDE), ("b", "hideout", HIDE)],
                                        [("a", "tube", "free_end"), ("b", "tube", "free_end")]), dwarf)
    assert joins(res) == [("tube.end_a", "a.front", "plug", "into_child"), ("tube.end_b", "b.front", "plug", "into_child")]
    assert {t.follower: t.owner for t in res.ties} == {"a.entrance_diameter_mm": "tube.inner_diameter_mm",
                                                        "b.entrance_diameter_mm": "tube.inner_diameter_mm"}
    assert codes(issues).count("exit_added") == 2


def test_house_to_house_through_a_tunnel(dwarf) -> None:
    house = dp("house", dwarf)
    res, params, _ = resolve_ok(request([("house", "house", house), ("tube", "tunnel", TUBE), ("house2", "house", house)],
                                        [("tube", "house", "right"), ("house2", "tube", "free_end")]), dwarf)
    assert joins(res) == [("house.right", "tube.end_b", "plug", "into_parent"),
                          ("tube.end_a", "house2.front", "plug", "into_child")]
    assert {t.follower: t.owner for t in res.ties} == {"tube.inner_diameter_mm": "house.ports.diameter_mm",
                                                        "house2.doors.width_mm": "house.ports.diameter_mm"}
    # 두 번째 집은 하나뿐인 출입구를 통로로 써서 뒤에 연결부를 더 낸다
    assert params["house2"].ports.sides == ["back"] and res.fixed["tube.shape"] == "pointed_arch"


def test_accessory_on_slanted_room_unsupported(dwarf) -> None:
    """45° 휜 터널 끝의 방은 비스듬히 놓여 연결판 자리를 정할 수 없다."""
    out = resolve_err(request([("hide", "hideout", HIDE), ("tube", "tunnel", {**TUBE, "bend_angle_deg": 45}),
                               ("hide2", "hideout", HIDE), ("bowl", "bowl_holder", BOWL)],
                              [("tube", "hide", "front"), ("hide2", "tube", "free_end"), ("bowl", "hide2", "right")]),
                      dwarf)
    assert out.code == "join_unsupported" and out.details == {"part": "bowl", "parent": "hide2"}


def test_auto_sides(dwarf) -> None:
    res, _, issues = resolve_ok(request(
        [("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL), ("bottle", "bottle_stand", BOTTLE),
         ("tube", "tunnel", TUBE), ("hide2", "hideout", HIDE)],
        [("bowl", "hide", "auto"), ("bottle", "hide", "auto"), ("tube", "hide", "auto"), ("hide2", "tube", "auto")],
    ), dwarf)
    assert res.faces == {"bowl": "right", "bottle": "left", "tube": "front", "hide2": "free_end"}
    assert "join_relocated" not in codes(issues)


def test_side_names_are_in_root_frame(dwarf) -> None:
    """터널 끝의 두 번째 은신처는 첫 은신처와 마주 보게 돌아간다: 기준 부품에서 본 '오른쪽'은 그 은신처의 왼쪽 면."""
    req = request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE), ("hide2", "hideout", HIDE),
                   ("bowl", "bowl_holder", BOWL)],
                  [("tube", "hide", "front"), ("hide2", "tube", "free_end"), ("bowl", "hide2", "right")])
    res, _, _ = resolve_ok(req, dwarf)
    assert res.join_to("bowl").parent == "hide2.left" and res.faces["bowl"] == "right"


def test_too_many_parts_with_inserted_tunnels(dwarf) -> None:
    rooms = [(f"h{i}", "hideout", HIDE) for i in range(MAX_PARTS)]
    conns = [(f"h{i}", "h0", "auto") for i in range(1, MAX_PARTS)]
    out = resolve_err(request(rooms, conns), dwarf)
    assert out.code in ("too_many_parts", "face_unavailable")
    out = resolve_err(request(rooms[:5], [(f"h{i}", f"h{i - 1}", "auto") for i in range(1, 5)]), dwarf)
    assert out.code == "too_many_parts"


def test_effective_spec_resolves_to_the_same_structure(dwarf) -> None:
    """고친 명세(at = 실제로 붙은 면, 끼운 터널은 보통 부품)를 다시 해석해도 같은 구조가 된다."""
    for req in (combo(), request([("hide", "hideout", HIDE), ("hide2", "hideout", HIDE), ("bowl", "bowl_holder", BOWL)],
                                 [("hide2", "hide", "right"), ("bowl", "hide", "front")])):
        res, params, _ = resolve_ok(req, dwarf)
        again, _, _ = resolve_ok(res.to_request({k: v.model_dump() for k, v in params.items()}), dwarf)
        assert again.joins == res.joins and again.faces == res.faces
        assert {t.follower for t in again.ties} == {t.follower for t in res.ties}


# ── 맞물리는 치수·조립 제약 ──


def test_syrian_tunnel_minimum_raises_the_owner(syrian) -> None:
    res, params, _ = resolve_ok(combo(), syrian)
    t = compose.template_for(res)
    cons = compose.derived_constraints(res, compose.assembly_params(t, params), syrian)
    tunnel_min = [c for c in cons if c.field == "hide.entrance_diameter_mm" and c.min == 70 and "터널" in c.reason_ko]
    assert tunnel_min, "터널 내경 최소값은 주인 값(은신처 출입구)으로 옮겨져야 합니다"
    # 따르는 값에는 '주인과 같게'만 남는다
    on_tube = [c for c in cons if c.field == "tube.inner_diameter_mm"]
    assert on_tube and all(c.min == c.max for c in on_tube)
    _, p, issues = settle(res, params, syrian)
    assert not errors(issues)
    assert p.hide.entrance_diameter_mm == p.tube.inner_diameter_mm == p.hide2.entrance_diameter_mm == 70
    assert p.tube.length_mm >= 1.5 * 70


def test_tie_redirect_when_tunnel_minimum_is_larger(syrian) -> None:
    """터널 최소 내경이 출입구 최소 폭보다 크면, 은신처 출입구가 터널 기준으로 커지고 터널·두 번째 은신처가 따른다."""
    ctx = dataclasses.replace(syrian, size=syrian.size.model_copy(update={"tunnel_min_inner_diameter_mm": 80}))
    res, params, _ = resolve_ok(combo(), ctx)
    _, p, issues = settle(res, params, ctx)
    assert not errors(issues)
    assert p.hide.entrance_diameter_mm == p.tube.inner_diameter_mm == p.hide2.entrance_diameter_mm == 80
    raised = next(i for i in issues if i.details.get("field") == "hide.entrance_diameter_mm")
    assert "터널" in raised.message_ko


def test_side_width_grows_for_the_bottle_stand(dwarf) -> None:
    res, params, _ = resolve_ok(combo(), dwarf)
    _, p, issues = settle(res, params, dwarf)
    # 물병 거치대 바닥판 110 + 양쪽 여유 3 = 116 (그릇 받침은 106 이라 이미 들어간다)
    assert p.hide.depth_mm == pytest.approx(110 + 2 * compose.EDGE_MARGIN_MM)
    grown = next(i for i in issues if i.details.get("field") == "hide.depth_mm")
    assert grown.details["from"] == 110 and "물병 거치대" in grown.message_ko
    # 붙인 그릇 받침의 턱: 그릇 테두리 − 5mm (joined_constraints)
    assert p.bowl.collar_height_mm == pytest.approx(BOWL["bowl_height_mm"] - 5)


def test_siblings_share_a_side_with_passable_gap(dwarf) -> None:
    # 출력 공간이 넉넉하면 (두 그릇 받침이 한 면에 들어가는 본체) 같은 면에 나란히
    big = dataclasses.replace(dwarf, build_volume_mm=(400.0, 400.0, 400.0))
    res, params, _ = resolve_ok(request([("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL),
                                         ("bowl2", "bowl_holder", BOWL)],
                                        [("bowl", "hide", "right"), ("bowl2", "hide", "right")]), big)
    w = compose.face_width(P["bowl_holder"], params["bowl"], "back")
    gap = compose.sibling_gap(big)
    assert gap > big.size.gap_trap.passable_min_mm
    # 바깥에서 볼 때 왼쪽부터 connections 순서로, 가운데 맞춤
    assert [j.shift for j in res.joins] == [pytest.approx(-(w + gap) / 2), pytest.approx((w + gap) / 2)]
    _, p, _ = settle(res, params, big)
    assert p.hide.depth_mm == pytest.approx(2 * w + gap + 2 * compose.EDGE_MARGIN_MM)


def test_ramp_level_on_hideout_and_sand_bath(dwarf) -> None:
    # 은신처 옆면: 램프 꼭대기 = 은신처 높이 (오르는 높이 상한은 은신처 높이로 옮겨진다)
    tall = {**HIDE, "height_mm": 130}
    ramp = dp("ramp", dwarf, steps=4)
    res, params, _ = resolve_ok(request([("hide", "hideout", tall), ("ramp", "ramp", ramp)],
                                        [("ramp", "hide", "right")]), dwarf)
    _, p, issues = settle(res, params, dwarf)
    assert not errors(issues)
    assert p.hide.height_mm == dwarf.size.max_climb_height_mm == p.ramp.height_mm
    assert P["ramp"].anchors(p.ramp)  # 램프는 여전히 유효한 파라미터
    # 보통 높이: 은신처는 그대로, 램프가 따라간다
    res, params, _ = resolve_ok(request([("hide", "hideout", HIDE), ("ramp", "ramp", dp("ramp", dwarf))],
                                        [("ramp", "hide", "right")]), dwarf)
    _, p, issues = settle(res, params, dwarf)
    assert p.hide.height_mm == HIDE["height_mm"] == p.ramp.height_mm and not errors(issues)
    # 모래목욕통 앞면: 램프 꼭대기 = 턱 높이
    bath = dp("sand_bath", dwarf)
    res, params, _ = resolve_ok(request([("bath", "sand_bath", bath), ("ramp", "ramp", dp("ramp", dwarf))],
                                        [("ramp", "bath", "front")]), dwarf)
    _, p, issues = settle(res, params, dwarf)
    assert p.ramp.height_mm == p.bath.lip_height_mm == bath["lip_height_mm"] and not errors(issues)


def test_plug_wall_minimums_are_derived(dwarf) -> None:
    res, params, _ = resolve_ok(combo(), dwarf)
    t = compose.template_for(res)
    cons = compose.derived_constraints(res, compose.assembly_params(t, params), dwarf)
    mins = {(c.field, round(c.min, 6)) for c in cons if c.source == "printing" and c.min is not None}
    assert ("tube.wall_thickness_mm", round(compose.PLUG_PORT_WALL_MIN_MM, 6)) in mins
    assert ("hide.wall_thickness_mm", round(compose.PLUG_DOOR_WALL_MIN_MM, 6)) in mins
    assert ("hide2.wall_thickness_mm", round(compose.PLUG_DOOR_WALL_MIN_MM, 6)) in mins
    # 해석기가 정한 수 값은 그대로 지킨다
    assert any(c.field == "hide.entrance_count" and c.min == c.max == 2 for c in cons)


@pytest.mark.parametrize("size", SIZES)
def test_autofix_converges_within_12_passes(rules, size) -> None:
    ctx = rctx(rules, size)
    reqs = [combo()] + [_fixture_request(k) for k in FIXTURE_KEYS]
    for req in reqs:
        res, params, _ = resolve_ok(req, ctx)
        _, p12, issues = settle(res, params, ctx)
        _, p40, _ = settle(res, params, ctx, passes=40)
        assert p12 == p40, res.parts
        assert "param_conflict" not in codes(issues)


def test_resolve_settles_group_entrances_first(rules) -> None:
    """여러 마리: 부품마다 먼저 보정해 출입구가 2개가 된 은신처는 뒷면이 출입구다 (받침은 옆면으로)."""
    ctx = rctx(rules, "dwarf", count=2)
    res, params, issues = resolve_ok(request([("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL)],
                                             [("bowl", "hide", "back")]), ctx)
    assert params["hide"].entrance_count == 2
    assert res.join_to("bowl").parent == "hide.right"
    adjusted = next(i for i in issues if i.code == "param_adjusted")
    assert adjusted.details["field"] == "hide.entrance_count" and adjusted.details["part"] == "hide"
    assert "은신처 · " in adjusted.message_ko


def test_invalid_and_unknown_parts(dwarf) -> None:
    out = compose.resolve(request([("hide", "hideout", HIDE), ("x", "tunnel", TUBE)], [("x", "hide", "front")]),
                          {"x": {**TUBE, "length_mm": 5}}, dwarf)
    assert isinstance(out, Issue) and out.code == "invalid_params" and out.details["path"] == "x"
    out = compose.resolve(request([("hide", "hideout", HIDE), ("x", "slide", {})], [("x", "hide", "front")]), None,
                          dwarf)
    assert isinstance(out, Issue) and out.code == "unknown_template"


def test_composed_template_is_cached(dwarf) -> None:
    res, _, _ = resolve_ok(combo(), dwarf)
    a = compose.template_for(res)
    assert compose.template_for(ResolvedAssembly.from_stored(json.loads(res.canonical()))) is a
    assert compose.composed_template(res.canonical(), "급식 은신처") is not a
    assert compose.composed_template(res.canonical(), "급식 은신처").display_name_ko == "급식 은신처"
    assert a.constraints(a.default_params(dwarf), dwarf)  # 조립 항목 템플릿의 제약 = derived_constraints


def test_combo_passes_rule_issues(rules) -> None:
    """설계 문서의 5부품 예: 드워프·골든 모두 보정 뒤 규칙·형상 검사를 통과한다."""
    for size in SIZES:
        ctx = rctx(rules, size)
        res, params, _ = resolve_ok(combo(), ctx)
        t, p, issues = settle(res, params, ctx)
        assert not errors(issues)
        start = time.perf_counter()
        assert t.rule_issues(p, ctx) == []
        assert time.perf_counter() - start < 15


# ── 라이브러리에서 옮긴 고정 데이터 ──


def _fixture(key: str) -> dict:
    return json.loads((FIXTURES / f"{key}.json").read_text())


def _fixture_request(key: str) -> AssemblyRequest:
    it = _fixture(key)["spec"]["items"][0]
    return AssemblyRequest(parts=it["parts"], connections=it["connections"], name_ko=it["name_ko"])


def test_fixtures_cover_the_library() -> None:
    assert FIXTURE_KEYS == ["dining_hideout", "hideout_with_bottle", "hideout_with_bowl", "hideout_with_ramp",
                            "hideout_with_tunnel", "house_with_tunnel", "sand_bath_with_ramp", "twin_hideouts"]
    for key in FIXTURE_KEYS:
        fx = _fixture(key)
        ids = fx["library"]["ids"]
        old = [(j["parent"], j["child"]) for j in fx["library"]["joins"]]
        renamed = [tuple(".".join([ids.get(r.split(".")[0], r.split(".")[0]), r.split(".")[1]]) for r in pair)
                   for pair in old]
        # 손으로 만든 라이브러리와 같은 연결 지점끼리 (붙인 터널만 한 덩어리(fused) → 끼움(plug))
        assert renamed == [(j["parent"], j["child"]) for j in fx["expected"]["joins"]], key
        mounts = [j.get("mount", "fused") for j in fx["library"]["joins"]]
        if key == "hideout_with_tunnel":
            assert mounts == ["fused"] and fx["expected"]["joins"][0]["mount"] == "plug"
        else:
            assert mounts == [j["mount"] for j in fx["expected"]["joins"]], key


def test_fixture_specs_are_interpreter_output(rules) -> None:
    """고정 데이터의 spec 은 해석기 출력 계약(app/llm/spec)을 그대로 통과한다 (few-shot 예로도 쓴다)."""
    from app.llm.spec import parse_spec, to_item_specs

    allowed = rules.species_entry("hamster").allowed_templates
    for key in FIXTURE_KEYS:
        spec = parse_spec(json.dumps(_fixture(key)["spec"], ensure_ascii=False), allowed)
        (item,) = to_item_specs(spec)
        assert item.template == "assembly" and item.assembly == _fixture_request(key), key


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("key", FIXTURE_KEYS)
def test_fixture_resolves_and_passes(rules, key, size) -> None:
    ctx = rctx(rules, size)
    res, params, issues = resolve_ok(_fixture_request(key), ctx)
    stored = res.stored()
    for k, v in _fixture(key)["expected"].items():
        assert stored[k] == v, (key, k)
    assert all(i.severity == Severity.info for i in issues)
    t, p, adj = settle(res, params, ctx)
    assert not errors(adj), errors(adj)
    assert t.rule_issues(p, ctx) == []


# ── 무작위 조립 ──

ROOT_CHOICES = ("hideout", "hideout", "house", "sand_bath")
SEEDS = range(12)


def _random_request(rng: random.Random, ctx: RuleContext) -> AssemblyRequest:
    """뿌리(은신처·집·모래목욕통)에 어울리는 부품을 2~6개까지 붙인 무작위 나무."""
    n = rng.randint(2, 6)
    root = rng.choice(ROOT_CHOICES)
    parts = [("p0", root, dp(root, ctx))]
    conns: list[tuple] = []
    counts = {"p0": 0}
    while len(parts) < n:
        pid, key, _ = rng.choice(parts)
        role = P[key].role
        if role == "room_host":
            child = rng.choice(("bowl_holder", "bottle_stand", "ramp", "tunnel", "hideout"))
        elif role == "host":
            child = rng.choice(("bowl_holder", "bottle_stand", "ramp"))
        elif role == "connector":
            if counts[pid] >= 1:
                continue
            child = rng.choice(("hideout", "house"))
        else:
            continue
        cid = f"p{len(parts)}"
        params = dp(child, ctx)
        if child == "tunnel":
            params.update(shape=rng.choice(("round_arch", "pointed_arch", "tube")),
                          bend_angle_deg=rng.choice((0, 0, 45, 90)))
        sides = ("free_end", "auto") if role == "connector" else ("front", "back", "left", "right", "auto")
        parts.append((cid, child, params))
        conns.append((cid, pid, rng.choice(sides)))
        counts[pid] += 1
        counts[cid] = 0
    return request(parts, conns)


@pytest.mark.parametrize("seed", SEEDS)
def test_random_trees_pass_or_fail_cleanly(rules, seed) -> None:
    rng = random.Random(seed)
    ctx = rctx(rules, SIZES[seed % 2])
    req = _random_request(rng, ctx)
    start = time.perf_counter()
    out = compose.resolve(req, None, ctx)
    if isinstance(out, Issue):
        assert out.code in KNOWN_ERRORS, out
        return
    res, params, _ = out
    t, p, issues = settle(res, params, ctx)
    _, p_more, _ = settle(res, params, ctx, passes=40)
    assert p == p_more, "자동 보정이 12패스 안에 수렴해야 합니다"
    errs = [i for i in issues if i.severity == Severity.error]
    assert {i.code for i in errs} <= KNOWN_ERRORS
    if not errs:
        t.rule_issues(p, ctx)  # 위반은 문구로 남을 뿐 예외가 나지 않는다
    assert time.perf_counter() - start < 15
