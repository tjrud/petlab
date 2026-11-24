"""조립 해석기 2단계 변경 (설계 문서 §3.2): 은신처 옆면 출입구, 키로 찾는 터널, 출입구 구조 값 고정(side_doors·door_fields),
출입구 단면을 고르는 방의 단면 맞추기(_adopt_room_profile), 해석기 출력 검증의 단면 사전 검사(spec._door_profiles).

단면을 고르는 방은 아직 라이브러리 부품이 없어 여기서 가짜 템플릿(FakeHub: 출입구 단면·폭을 파라미터로 고르는 방)으로 본다."""

from __future__ import annotations

from typing import ClassVar, Literal

import pytest
from pydantic import Field

from app.llm import spec as spec_module
from app.modules import compose
from app.modules.structure import AssemblyRequest, ResolvedAssembly
from app.templates.base import (
    Anchor,
    AttachKind,
    FaceFields,
    Features,
    Opening,
    ParamConstraint,
    RuleContext,
    Template,
    TemplateParams,
)
from app.templates.registry import primitives
from app.validation.report import Issue, Severity

P = primitives()


def rctx(rules, size: str = "dwarf", count: int = 1) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), count,
                       printing_max_overhang_deg=rules.printing.max_overhang_deg,
                       min_feature_mm=rules.printing.min_feature_mm)


@pytest.fixture(scope="module")
def dwarf(rules) -> RuleContext:
    return rctx(rules, "dwarf")


def dp(key: str, ctx: RuleContext | None = None, **over) -> dict:
    return {**P[key].default_params(ctx).model_dump(), **over}


def request(parts: list[tuple], conns: list[tuple]) -> AssemblyRequest:
    return AssemblyRequest(parts=[{"id": a, "template": b, "params": c} for a, b, c in parts],
                           connections=[{"part": a, "to": b, "at": c} for a, b, c in conns])


def resolve(req: AssemblyRequest, ctx: RuleContext, templates=None):
    return compose.resolve(req, None, ctx, templates=templates)


def resolve_ok(req, ctx, templates=None) -> tuple[ResolvedAssembly, dict, list[Issue]]:
    out = resolve(req, ctx, templates)
    assert not isinstance(out, Issue), out.message_ko
    return out


def resolve_err(req, ctx, templates=None) -> Issue:
    out = resolve(req, ctx, templates)
    assert isinstance(out, Issue), f"오류여야 합니다: {out[0].stored()}"
    assert out.severity == Severity.error
    return out


def joins(res: ResolvedAssembly) -> list[tuple]:
    return [(j.parent, j.child, j.mount, j.passage) for j in res.joins]


def codes(issues: list[Issue]) -> list[str]:
    return [i.code for i in issues]


HIDE = {"width_mm": 140, "depth_mm": 110, "height_mm": 90, "entrance_diameter_mm": 60, "entrance_count": 1,
        "vent_count": 6, "vent_diameter_mm": 4, "wall_thickness_mm": 3}
BOWL = {"bowl_diameter_mm": 90, "bowl_height_mm": 40, "clearance_mm": 1.0, "wall_thickness_mm": 3, "collar_height_mm": 30}
TUBE = {"length_mm": 100, "inner_diameter_mm": 60, "bend_angle_deg": 0, "wall_thickness_mm": 3, "shape": "tube",
        "path": "arc"}


# ── 가짜 템플릿 ──

Shape = Literal["round_arch", "pointed_arch", "box", "house"]


class HubParams(TemplateParams):
    wall_thickness_mm: float = Field(3, ge=2.3, le=6, description="벽 두께 mm")
    door_width_mm: float = Field(60, ge=25, le=100, description="출입구 폭 mm")
    door_shape: Shape = Field("box", description="출입구 단면 모양")
    size_mm: float = Field(100, ge=60, le=200, description="가로·세로 mm")
    height_mm: float = Field(90, ge=40, le=200, description="높이 mm")


class FakeHub(Template):
    """출입구 단면·폭을 파라미터로 고르는 방 (앞·뒤 출입구, 옆면은 연결판 자리). 형상은 만들지 않는다."""

    key = "fake_hub"
    display_name_ko = "갈림길"
    description_ko = "시험용 갈림길"
    Params: ClassVar[type[TemplateParams]] = HubParams
    role = "room_host"
    attach_order: ClassVar[dict[AttachKind, tuple[str, ...]]] = {"passage": ("front", "back")}
    door_fields: ClassVar[tuple[str, ...]] = ("door_shape",)

    def constraints(self, p, ctx: RuleContext) -> list[ParamConstraint]:
        return [ctx.wall_thickness_constraint()]

    def build(self, p):
        raise AssertionError("조립 해석기는 형상을 만들지 않는다")

    def anchors(self, p) -> dict[str, Anchor]:
        S, H, t, d = p.size_mm, p.height_mm, p.wall_thickness_mm, p.door_width_mm
        z = (0.0, 0.0, 1.0)
        return {
            "front": Anchor((0, -S / 2, 0), (0, -1, 0), z, side="front", port=d, wall_mm=t, profile=p.door_shape),
            "back": Anchor((0, S / 2, 0), (0, 1, 0), z, side="back", port=d, wall_mm=t, profile=p.door_shape),
            "left": Anchor((-S / 2, 0, 0), (-1, 0, 0), z, mount=(-S / 2, S / 2, H)),
            "right": Anchor((S / 2, 0, 0), (1, 0, 0), z, mount=(-S / 2, S / 2, H)),
            "top": Anchor((0, 0, H), (0, 0, 1), (0, 1, 0)),
            "bottom": Anchor((0, 0, 0), (0, 0, -1), (0, 1, 0)),
        }

    def face_fields(self, p, anchor: str) -> FaceFields:
        if anchor in ("front", "back"):
            return FaceFields("size_mm", "height_mm", "wall_thickness_mm", port="door_width_mm", profile="door_shape")
        if anchor in ("left", "right"):
            return FaceFields("size_mm", "height_mm")
        return FaceFields()

    def open_port(self, p, anchor: str):
        return p if anchor in ("front", "back") else None

    def envelope(self, p) -> tuple[float, float, float]:
        return (p.size_mm, p.size_mm, p.height_mm)

    def features(self, p) -> Features:
        return Features(min_wall_thickness_mm=p.wall_thickness_mm,
                        openings=(Opening("passage", p.door_width_mm, "앞 출입구", rule_key="entrance_min_diameter_mm"),
                                  Opening("passage", p.door_width_mm, "뒤 출입구", rule_key="entrance_min_diameter_mm")),
                        access_sides=("front", "back"), entrance_count=2)


class NarrowHubParams(HubParams):
    door_shape: Literal["box", "house"] = Field("box", description="출입구 단면 모양")  # type: ignore[assignment]


class NarrowHub(FakeHub):
    """둥근 아치·뾰족 아치를 만들 수 없는 방."""

    key = "narrow_hub"
    Params: ClassVar[type[TemplateParams]] = NarrowHubParams


class FakeConnector(Template):
    """터널이 아닌 connector (라이브러리에 먼저 등록된 다른 이음 부품 흉내). 끼울 터널로 골라지면 안 된다."""

    key = "aaa_connector"
    display_name_ko = "이음관"
    description_ko = "시험용 이음관"
    Params: ClassVar[type[TemplateParams]] = type(P["tunnel"].default_params())
    role = "connector"
    attach_order: ClassVar[dict[AttachKind, tuple[str, ...]]] = {"passage": ("end_b", "end_a")}

    def constraints(self, p, ctx):
        return []

    def build(self, p):
        raise AssertionError("쓰이면 안 된다")

    def anchors(self, p):
        return P["tunnel"].anchors(p)

    def features(self, p):
        return P["tunnel"].features(p)


HUB, NARROW = FakeHub(), NarrowHub()
WITH_HUBS = {**P, HUB.key: HUB, NARROW.key: NARROW}


# ── 은신처 옆면 출입구 ──


@pytest.mark.parametrize("side", ["left", "right"])
def test_tunnel_at_a_hideout_side_opens_a_side_door(dwarf, side):
    res, params, issues = resolve_ok(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE)],
                                             [("tube", "hide", side)]), dwarf)
    assert joins(res) == [(f"hide.{side}", "tube.end_b", "plug", "into_parent")]
    assert res.faces == {"tube": side}
    assert params["hide"].side_doors == side and params["hide"].entrance_count == 1
    assert "join_relocated" not in codes(issues)
    opened = next(i for i in issues if i.code == "port_opened")
    assert opened.details == {"part": "hide", "child": "tube", "anchor": side}
    assert res.fixed["hide.side_doors"] == side and res.fixed["tube.shape"] == "round_arch"
    assert [(t.follower, t.owner) for t in res.ties] == [("tube.inner_diameter_mm", "hide.entrance_diameter_mm")]
    # 앞 출입구가 비어 있으므로 나갈 출입구를 더 내지 않는다
    assert "exit_added" not in codes(issues)


def test_four_way_hub_from_one_hideout(dwarf):
    """출입구 2개 + 옆면 출입구 양쪽: 네 면에 터널 넷 (네 갈래 은신처)."""
    parts = [("hide", "hideout", HIDE), *[(f"t{i}", "tunnel", TUBE) for i in range(4)]]
    conns = [("t0", "hide", "front"), ("t1", "hide", "back"), ("t2", "hide", "left"), ("t3", "hide", "right")]
    res, params, issues = resolve_ok(request(parts, conns), dwarf)
    assert [j[0] for j in joins(res)] == ["hide.front", "hide.back", "hide.left", "hide.right"]
    assert params["hide"].entrance_count == 2 and params["hide"].side_doors == "both"
    assert res.fixed["hide.side_doors"] == "both" and res.fixed["hide.entrance_count"] == 2
    assert "join_relocated" not in codes(issues)


def test_fill_exits_opens_a_side_door_when_the_back_is_taken(dwarf):
    """앞 출입구를 통로로 쓰고 뒷면에 그릇 받침이 있으면: 받침을 옮기지 않고 옆면에 나갈 출입구를 낸다."""
    res, params, issues = resolve_ok(request([("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL),
                                              ("tube", "tunnel", TUBE)],
                                             [("bowl", "hide", "back"), ("tube", "hide", "front")]), dwarf)
    assert ("hide.back", "bowl.back", "slide", False) in joins(res)
    assert res.faces["bowl"] == "back"
    assert "join_relocated" not in codes(issues)
    exit_added = next(i for i in issues if i.code == "exit_added")
    assert exit_added.details == {"part": "hide", "anchor": "left"}
    assert params["hide"].side_doors == "left" and params["hide"].entrance_count == 1
    assert res.fixed["hide.side_doors"] == "left"


def test_fill_exits_still_prefers_the_opposite_wall(dwarf):
    _, params, issues = resolve_ok(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE)],
                                           [("tube", "hide", "front")]), dwarf)
    assert next(i for i in issues if i.code == "exit_added").details["anchor"] == "back"
    assert params["hide"].entrance_count == 2 and params["hide"].side_doors == "none"
    # 옆면 터널이면 반대쪽 옆면이 아니라 (앞 출입구가 비어 있어) 아무것도 더 내지 않는다
    _, params, issues = resolve_ok(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE)],
                                           [("tube", "hide", "left")]), dwarf)
    assert "exit_added" not in codes(issues) and params["hide"].side_doors == "left"


def test_through_room_gets_a_side_exit_only_from_a_free_wall(dwarf):
    """통로가 둘인 은신처(지나가는 방): 빈 옆면이 있으면 옆면 출입구를 내고, 옆면이 모두 받침이면 옮기지 않고 그대로 둔다
    (옆면 출입구가 생기기 전과 같이 해석된다). 통로가 하나인 막다른 방은 나갈 곳이 없으면 face_unavailable."""
    parts = [("hide", "hideout", HIDE), ("t1", "tunnel", TUBE), ("t2", "tunnel", TUBE)]
    conns = [("t1", "hide", "front"), ("t2", "hide", "back")]
    _, params, issues = resolve_ok(request(parts, conns), dwarf)
    assert params["hide"].side_doors == "left" and params["hide"].entrance_count == 2
    assert [i.details for i in issues if i.code == "exit_added"] == [{"part": "hide", "anchor": "left"}]
    full = request([*parts, ("bowl", "bowl_holder", BOWL), ("bowl2", "bowl_holder", BOWL)],
                   [("bowl", "hide", "left"), ("bowl2", "hide", "right"), *conns])
    res, params, issues = resolve_ok(full, dwarf)
    assert params["hide"].side_doors == "none"
    assert not {"exit_added", "join_relocated"} & set(codes(issues))
    assert {(j[0], j[1]) for j in joins(res)} >= {("hide.left", "bowl.back"), ("hide.right", "bowl2.back")}
    dead_end = request([("hide", "hideout", HIDE), ("t1", "tunnel", TUBE), ("bowl", "bowl_holder", BOWL),
                        ("bowl2", "bowl_holder", BOWL), ("bowl3", "bowl_holder", BOWL)],
                       [("bowl", "hide", "left"), ("bowl2", "hide", "right"), ("bowl3", "hide", "back"),
                        ("t1", "hide", "front")])
    out = resolve_err(dead_end, dwarf)
    assert out.code == "face_unavailable" and out.details["part"] == "hide"


def test_side_doors_pinned_for_passage_rooms(dwarf):
    """통로로 이은 은신처는 side_doors 를 (기본값 none 이어도) fixed 에 적는다. 통로가 없으면 적지 않는다."""
    res, _, _ = resolve_ok(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE)],
                                   [("tube", "hide", "front")]), dwarf)
    assert res.fixed == {"tube.shape": "round_arch", "hide.entrance_count": 2, "hide.side_doors": "none"}
    res, _, _ = resolve_ok(request([("hide", "hideout", HIDE), ("bowl", "bowl_holder", BOWL)],
                                   [("bowl", "hide", "right")]), dwarf)
    assert res.fixed == {}
    assert compose.DOOR_STRUCTURE_FIELDS == ("entrance_count", "side_doors", "doors.sides", "ports.sides")


def test_effective_spec_with_side_doors_resolves_to_the_same_structure(dwarf):
    """해석 결과 파라미터(옆면 출입구가 열린 값)로 다시 해석해도 같은 저장 형태 (고친 명세 다시 해석)."""
    req = request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE), ("hide2", "hideout", HIDE)],
                  [("tube", "hide", "left"), ("hide2", "tube", "free_end")])
    res, params, _ = resolve_ok(req, dwarf)
    again = request([(pid, res.template_of(pid), params[pid].model_dump()) for pid in res.part_ids],
                    [(c.part, c.to, c.at) for c in req.connections])
    res2, _, _ = resolve_ok(again, dwarf)
    assert res2.canonical() == res.canonical()


# ── 터널은 키로 찾는다 ──


def test_insert_tunnel_picks_the_tunnel_by_key(dwarf, monkeypatch):
    """다른 connector 가 먼저 등록돼 있어도 방과 방 사이에는 "tunnel" 을 넣는다."""
    first = {FakeConnector.key: FakeConnector(), **P}
    assert next(t for t in first.values() if t.role == "connector").key == FakeConnector.key
    monkeypatch.setattr(compose, "default_templates", lambda: dict(first))
    req = request([("hide", "hideout", HIDE), ("hide2", "hideout", HIDE)], [("hide2", "hide", "front")])
    for templates in (None, first):
        res, _, issues = resolve_ok(req, dwarf, templates)
        assert [(p.id, p.template) for p in res.parts] == [("hide", "hideout"), ("hide2_link", "tunnel"),
                                                            ("hide2", "hideout")]
        assert "tunnel_inserted" in codes(issues)


def test_insert_tunnel_without_a_tunnel_is_unsupported(dwarf):
    no_tunnel = {k: t for k, t in P.items() if k != "tunnel"}
    out = resolve_err(request([("hide", "hideout", HIDE), ("hide2", "hideout", HIDE)], [("hide2", "hide", "front")]),
                      dwarf, no_tunnel)
    assert out.code == "join_unsupported" and out.details["part"] == "hide2"
    assert out.message_ko.endswith("방끼리 이을 터널이 없습니다")


# ── 단면을 고르는 방: 터널 단면 따르기 ──


def test_literal_choices():
    assert compose.literal_choices(HubParams, "door_shape") == ("round_arch", "pointed_arch", "box", "house")
    assert compose.literal_choices(NarrowHubParams, "door_shape") == ("box", "house")
    assert compose.literal_choices(HubParams, "door_width_mm") == ()
    assert compose.literal_choices(HubParams, "nowhere") == ()
    assert set(compose.literal_choices(type(P["tunnel"].default_params()), "shape")) == {
        "round_arch", "pointed_arch", "tube", "box", "house"}
    house_params = type(P["house"].default_params())
    assert compose.literal_choices(house_params, "roof.kind") == ("flat", "pitched", "rounded")
    assert compose.literal_choices(house_params, "roof.nowhere") == ()


@pytest.mark.parametrize(("room", "shape"), [("hideout", "round_arch"), ("house", "pointed_arch")])
def test_room_adopts_the_fixed_tunnel_shape(dwarf, room, shape):
    """은신처(둥근 아치)·집(뾰족 아치) 출입구에 맞춘 터널의 끝에 단면을 고르는 방: 방이 터널 단면을 따른다."""
    res, params, issues = resolve_ok(request([("room", room, dp(room, dwarf)), ("tube", "tunnel", TUBE),
                                              ("hub", "fake_hub", HubParams().model_dump())],
                                             [("tube", "room", "front"), ("hub", "tube", "free_end")]),
                                     dwarf, WITH_HUBS)
    assert ("tube.end_a", "hub.front", "plug", "into_child") in joins(res)
    assert params["hub"].door_shape == shape and params["tube"].shape == shape
    assert res.fixed["tube.shape"] == shape and res.fixed["hub.door_shape"] == shape
    matched = [i for i in issues if i.code == "passage_shape_matched" and i.details["part"] == "hub"]
    assert len(matched) == 1 and matched[0].details == {"part": "hub", "from": "box", "to": shape}
    assert matched[0].message_ko.endswith(f"갈림길 출입구 단면을 터널에 맞춰 {compose.PROFILE_KO[shape]}로 바꿨습니다")
    # 방 출입구 폭은 첫 방의 출입구 폭을 따른다
    owner = "room.entrance_diameter_mm" if room == "hideout" else "room.doors.width_mm"
    assert {t.follower: t.owner for t in res.ties}["hub.door_width_mm"] == owner


def test_room_already_in_the_tunnel_shape_gets_no_notice(dwarf):
    hub = HubParams(door_shape="round_arch").model_dump()
    res, _, issues = resolve_ok(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE),
                                         ("hub", "fake_hub", hub)],
                                        [("tube", "hide", "front"), ("hub", "tube", "free_end")]),
                                dwarf, WITH_HUBS)
    assert not [i for i in issues if i.code == "passage_shape_matched" and i.details["part"] == "hub"]
    assert res.fixed["hub.door_shape"] == "round_arch"


def test_tube_root_keeps_the_room_shape_and_the_tunnel_follows(dwarf):
    """뿌리 터널이 둥근 관(방이 만들 수 없는 단면)이고 아직 정해지지 않았으면 방은 그대로, 터널이 방 출입구를 따른다."""
    res, params, issues = resolve_ok(request([("tube", "tunnel", TUBE), ("hub", "fake_hub", HubParams().model_dump())],
                                             [("hub", "tube", "free_end")]), dwarf, WITH_HUBS)
    assert params["hub"].door_shape == "box" and params["tube"].shape == "box"
    assert res.fixed["tube.shape"] == "box" and res.fixed["hub.door_shape"] == "box"
    matched = [i for i in issues if i.code == "passage_shape_matched"]
    assert [i.details for i in matched] == [{"part": "tube", "from": "tube", "to": "box"}]


def test_free_tunnel_shape_the_room_can_make_is_adopted(dwarf):
    """뿌리 터널 단면이 정해지지 않았어도 방이 만들 수 있는 모양이면 방이 따른다 (해석기가 고른 터널 단면을 지킨다)."""
    tube = {**TUBE, "shape": "pointed_arch"}
    res, params, _ = resolve_ok(request([("tube", "tunnel", tube), ("hub", "fake_hub", HubParams().model_dump())],
                                        [("hub", "tube", "free_end")]), dwarf, WITH_HUBS)
    assert params["hub"].door_shape == "pointed_arch" and params["tube"].shape == "pointed_arch"
    assert res.fixed["hub.door_shape"] == "pointed_arch"


def test_impossible_fixed_shape_is_unsupported(dwarf):
    out = resolve_err(request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE),
                               ("hub", "narrow_hub", NarrowHubParams().model_dump())],
                              [("tube", "hide", "front"), ("hub", "tube", "free_end")]), dwarf, WITH_HUBS)
    assert out.code == "join_unsupported"
    assert out.details == {"part": "hub", "parent": "tube"}
    assert out.message_ko.endswith("갈림길 출입구는 둥근 아치 단면을 만들 수 없어 터널에 이을 수 없습니다")


def test_room_inserted_between_rooms_adopts_the_link_shape(dwarf):
    """방 ← 단면을 고르는 방: 끼운 터널이 첫 방 출입구 단면을 받고, 그 끝의 방이 그 단면을 따른다."""
    res, params, _ = resolve_ok(request([("house", "house", dp("house", dwarf)),
                                         ("hub", "fake_hub", HubParams().model_dump())],
                                        [("hub", "house", "front")]), dwarf, WITH_HUBS)
    assert res.part_ids == ["house", "hub_link", "hub"]
    assert params["hub_link"].shape == "pointed_arch" and params["hub"].door_shape == "pointed_arch"
    assert res.fixed["hub.door_shape"] == "pointed_arch"


def test_mixed_network_through_an_adaptable_room_fails_at_resolve(dwarf):
    """집(뾰족 아치) → 터널 → 단면을 고르는 방 → 터널 → 은신처(둥근 아치): 해석기가 단면이 다르다고 막는다
    (해석기 출력 검증은 단면을 고르는 방을 건너뛰어 여기까지 온다)."""
    req = request([("house", "house", dp("house", dwarf)), ("tube", "tunnel", TUBE),
                   ("hub", "fake_hub", HubParams().model_dump()), ("tube2", "tunnel", TUBE),
                   ("hide", "hideout", HIDE)],
                  [("tube", "house", "front"), ("hub", "tube", "free_end"), ("tube2", "hub", "back"),
                   ("hide", "tube2", "free_end")])
    out = resolve_err(req, dwarf, WITH_HUBS)
    assert out.code == "join_unsupported" and out.details["part"] == "tube2"
    assert "양 끝의 출입구 단면 모양이 달라" in out.message_ko
    by_id = {"house": P["house"], "tube": P["tunnel"], "hub": HUB, "tube2": P["tunnel"], "hide": P["hideout"]}
    assert spec_module._profile_problems(by_id, list(req.connections)) == []


def test_network_of_one_room_type_through_an_adaptable_room(dwarf):
    """은신처 → 터널 → 단면을 고르는 방 → 터널 → 은신처: 단면·폭이 한 값으로 이어진다."""
    req = request([("hide", "hideout", HIDE), ("tube", "tunnel", TUBE), ("hub", "fake_hub", HubParams().model_dump()),
                   ("tube2", "tunnel", TUBE), ("hide2", "hideout", HIDE)],
                  [("tube", "hide", "front"), ("hub", "tube", "free_end"), ("tube2", "hub", "back"),
                   ("hide2", "tube2", "free_end")])
    res, params, _ = resolve_ok(req, dwarf, WITH_HUBS)
    assert {params[k].shape for k in ("tube", "tube2")} == {"round_arch"} and params["hub"].door_shape == "round_arch"
    ties = {t.follower: t.owner for t in res.ties}
    for f in ("tube.inner_diameter_mm", "hub.door_width_mm", "tube2.inner_diameter_mm", "hide2.entrance_diameter_mm"):
        assert ties[f] == "hide.entrance_diameter_mm", f
    assert res.fixed["hub.door_shape"] == "round_arch"


# ── 해석기 출력 검증: 단면 사전 검사 ──


def test_door_profiles_skip_adaptable_rooms():
    assert spec_module._door_profiles(P["hideout"]) == frozenset({"round_arch"})
    assert spec_module._door_profiles(P["house"]) == frozenset({"pointed_arch"})
    assert spec_module._door_profiles(HUB) == frozenset()
    assert spec_module._door_profiles(NARROW) == frozenset()


def test_profile_problems_still_reject_house_and_hideout():
    by_id = {"house": P["house"], "tube": P["tunnel"], "hide": P["hideout"], "hub": HUB}
    conns = list(request([("house", "house", {}), ("tube", "tunnel", TUBE), ("hide", "hideout", HIDE)],
                         [("tube", "house", "front"), ("hide", "tube", "free_end")]).connections)
    assert len(spec_module._profile_problems(by_id, conns)) == 1
    conns = list(request([("house", "house", {}), ("tube", "tunnel", TUBE), ("hub", "fake_hub", {})],
                         [("tube", "house", "front"), ("hub", "tube", "free_end")]).connections)
    assert spec_module._profile_problems(by_id, conns) == []
    # 방끼리 바로 이을 때 (해석기가 터널을 끼운다)
    conns = list(request([("house", "house", {}), ("hub", "fake_hub", {})], [("hub", "house", "front")]).connections)
    assert spec_module._profile_problems(by_id, conns) == []
