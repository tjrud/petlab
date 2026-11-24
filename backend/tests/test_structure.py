"""조립 구조 계약 (app/modules/structure) 과 템플릿 연결 표준 기본값 (app/templates/base)."""

from __future__ import annotations

import copy
import json

import pytest
from build123d import Align, Box
from pydantic import ValidationError

from app.modules.structure import (
    MAX_PARTS,
    PART_ID_MAX_LEN,
    AssemblyDisplay,
    AssemblyRequest,
    ResolvedAssembly,
    ResolvedJoin,
    ResolvedPart,
    Tie,
    assembly_display,
    canonical_json,
    link_id,
    part_names,
    tree_problems,
)
from app.templates.base import (
    Anchor,
    FaceFields,
    Features,
    ParamConstraint,
    RuleContext,
    Template,
    TemplateParams,
)

HIDE = {"width_mm": 140, "depth_mm": 110, "height_mm": 90, "entrance_diameter_mm": 60, "entrance_count": 1}

# 설계 문서의 예: 은신처 오른쪽 그릇 받침, 왼쪽 물병 거치대, 앞에 터널로 은신처 하나 더
EXAMPLE_REQUEST = {
    "parts": [
        {"id": "hide", "template": "hideout", "params": HIDE},
        {"id": "bowl", "template": "bowl_holder", "params": {"bowl_diameter_mm": 90}},
        {"id": "bottle", "template": "bottle_stand", "params": {}},
        {"id": "tube", "template": "tunnel", "params": {"length_mm": 100, "shape": "tube"}},
        {"id": "hide2", "template": "hideout", "params": HIDE},
    ],
    "connections": [
        {"part": "bowl", "to": "hide", "at": "right"},
        {"part": "bottle", "to": "hide", "at": "left"},
        {"part": "tube", "to": "hide", "at": "front"},
        {"part": "hide2", "to": "tube", "at": "free_end"},
    ],
}

EXAMPLE_RESOLVED = {
    "v": 1, "resolver": "compose/1", "root": "hide",
    "parts": [{"id": "hide", "template": "hideout"}, {"id": "bowl", "template": "bowl_holder"},
              {"id": "bottle", "template": "bottle_stand"}, {"id": "tube", "template": "tunnel"},
              {"id": "hide2", "template": "hideout"}],
    "joins": [
        {"parent": "hide.right", "child": "bowl.back", "mount": "slide", "passage": False, "shift": 0.0},
        {"parent": "hide.left", "child": "bottle.back", "mount": "slide", "passage": False, "shift": 0.0},
        {"parent": "hide.front", "child": "tube.end_b", "mount": "plug", "passage": "into_parent", "shift": 0.0},
        {"parent": "tube.end_a", "child": "hide2.front", "mount": "plug", "passage": "into_child", "shift": 0.0},
    ],
    "ties": [
        {"follower": "tube.inner_diameter_mm", "owner": "hide.entrance_diameter_mm"},
        {"follower": "hide2.entrance_diameter_mm", "owner": "hide.entrance_diameter_mm"},
    ],
    "fixed": {"tube.shape": "round_arch", "hide.entrance_count": 2, "hide2.entrance_count": 2},
    "faces": {"bowl": "right", "bottle": "left", "tube": "front", "hide2": "free_end"},
}


def req(**changes) -> dict:
    d = copy.deepcopy(EXAMPLE_REQUEST)
    d.update(changes)
    return d


def resolved(**changes) -> dict:
    d = copy.deepcopy(EXAMPLE_RESOLVED)
    d.update(changes)
    return d


def errors(data: dict, model=AssemblyRequest) -> str:
    with pytest.raises(ValidationError) as e:
        model.model_validate(data)
    return str(e.value)


# --- AssemblyRequest: 나무 구조 검증 ---


def test_request_example_parses_and_walks_breadth_first():
    r = AssemblyRequest.model_validate(EXAMPLE_REQUEST)
    assert r.root == "hide"
    assert r.part("tube").template == "tunnel"
    assert r.parent_of("hide2") == "tube" and r.parent_of("hide") is None
    assert [c.part for c in r.children_of("hide")] == ["bowl", "bottle", "tube"]
    assert [c.part for c in r.walk()] == ["bowl", "bottle", "tube", "hide2"]
    assert r.name_ko is None


def test_walk_is_breadth_first_even_when_connections_list_deep_first():
    d = req(connections=[
        {"part": "hide2", "to": "tube", "at": "free_end"},
        {"part": "tube", "to": "hide", "at": "front"},
        {"part": "bowl", "to": "hide", "at": "auto"},
        {"part": "bottle", "to": "hide2", "at": "left"},
    ])
    r = AssemblyRequest.model_validate(d)
    assert [c.part for c in r.walk()] == ["tube", "bowl", "hide2", "bottle"]


@pytest.mark.parametrize("n", [1, MAX_PARTS + 1])
def test_part_count_bounds(n):
    parts = [{"id": f"p{i}", "template": "hideout", "params": {}} for i in range(n)]
    conns = [{"part": f"p{i}", "to": "p0", "at": "auto"} for i in range(1, n)]
    assert "부품은 2~8개" in errors({"parts": parts, "connections": conns})


def test_max_parts_accepted():
    parts = [{"id": f"p{i}", "template": "hideout", "params": {}} for i in range(MAX_PARTS)]
    conns = [{"part": f"p{i}", "to": f"p{i - 1}", "at": "auto"} for i in range(1, MAX_PARTS)]
    AssemblyRequest.model_validate({"parts": parts, "connections": conns})


@pytest.mark.parametrize("bad", ["Hide", "1hide", "hide-2", "", "a" * (PART_ID_MAX_LEN + 1)])
def test_bad_ids(bad):
    d = req()
    d["parts"][1]["id"] = bad
    d["connections"][0]["part"] = bad
    assert "부품 id 는" in errors(d)


def test_duplicate_ids():
    d = req()
    d["parts"][4]["id"] = "hide"
    assert "겹칩니다" in errors(d)


def test_unknown_reference():
    d = req()
    d["connections"][3]["to"] = "tunnel"
    assert "없는 부품" in errors(d)


def test_self_reference():
    d = req()
    d["connections"][0]["to"] = "bowl"
    assert "자기 자신" in errors(d)


def test_root_cannot_be_child():
    d = req()
    d["connections"].append({"part": "hide", "to": "bowl", "at": "auto"})
    assert "기준(첫) 부품" in errors(d)


def test_two_parents():
    d = req()
    d["connections"].append({"part": "bowl", "to": "hide2", "at": "right"})
    assert "한 부품에만" in errors(d)


def test_unconnected_part():
    d = req()
    d["connections"].pop(1)
    assert "붙이지 않은 부품" in errors(d) and "bottle" in errors(d)


def test_cycle_detected():
    d = req()
    # tube 와 hide2 가 서로 붙어 뿌리에서 떨어진다 (각자 부모는 하나)
    d["connections"][2] = {"part": "tube", "to": "hide2", "at": "front"}
    msg = errors(d)
    assert "순환" in msg and "hide2" in msg and "tube" in msg


def test_at_literal_and_extra_fields():
    d = req()
    d["connections"][0]["at"] = "top"
    assert "at" in errors(d)
    d = req()
    d["connections"][0]["mount"] = "slide"  # 해석기는 결합 방식을 적지 않는다
    assert "mount" in errors(d)


def test_tree_problems_empty_for_valid_tree():
    assert tree_problems(["a", "b", "c"], [("b", "a"), ("c", "b")]) == []


# --- link_id ---


def test_link_id():
    assert link_id("hide2", {"hide", "hide2"}) == "hide2_link"
    assert link_id("hide2", {"hide2_link"}) == "hide2_link2"
    long = "a" * PART_ID_MAX_LEN
    lid = link_id(long, set())
    assert len(lid) == PART_ID_MAX_LEN and lid.endswith("_link")
    lid2 = link_id(long, {lid})
    assert len(lid2) == PART_ID_MAX_LEN and lid2.endswith("_link2")
    assert not tree_problems([long, lid, lid2], [(lid, long), (lid2, lid)])


# --- ResolvedJoin, Tie ---


def test_join_refs_and_mount_rules():
    j = ResolvedJoin(parent="tube.end_a", child="hide2.front", mount="plug", passage="into_child")
    assert (j.parent_id, j.parent_anchor, j.child_id, j.child_anchor) == ("tube", "end_a", "hide2", "front")
    assert j.reverse
    with pytest.raises(ValidationError, match="형식"):
        ResolvedJoin(parent="hide", child="bowl.back", mount="slide", passage=False)
    with pytest.raises(ValidationError, match="슬라이드"):
        ResolvedJoin(parent="hide.right", child="bowl.back", mount="slide", passage="into_parent")
    with pytest.raises(ValidationError, match="끼움"):
        ResolvedJoin(parent="hide.front", child="tube.end_b", mount="plug", passage=False)
    with pytest.raises(ValidationError):
        ResolvedJoin(parent="hide.front", child="tube.end_b", mount="fused", passage="into_parent")


def test_join_shift_is_rounded_and_signless_zero():
    j = ResolvedJoin(parent="hide.right", child="bowl.back", mount="slide", passage=False, shift=-0.0)
    assert json.dumps(j.shift) == "0.0"
    j = ResolvedJoin(parent="hide.right", child="bowl.back", mount="slide", passage=False, shift=12.1 + 0.2 - 0.3)
    assert j.shift == 12.0


def test_join_spec_conversion():
    from app.modules.assembly import JoinSpec

    j = ResolvedJoin(parent="tube.end_a", child="hide2.front", mount="plug", passage="into_child", shift=1.5)
    assert j.join_spec() == JoinSpec("tube", "end_a", "hide2", "front", shift=1.5, passage=True, mount="plug",
                                     reverse=True)
    s = ResolvedJoin(parent="hide.right", child="bowl.back", mount="slide", passage=False).join_spec()
    assert s.slide and not s.passage and not s.reverse


def test_tie_refs():
    t = Tie(follower="house.doors.width_mm", owner="hide.entrance_diameter_mm")
    assert (t.follower_id, t.follower_path) == ("house", "doors.width_mm")
    with pytest.raises(ValidationError, match="형식"):
        Tie(follower="inner_diameter_mm", owner="hide.entrance_diameter_mm")
    with pytest.raises(ValidationError, match="자기 자신"):
        Tie(follower="hide.x", owner="hide.x")


# --- ResolvedAssembly ---


def test_resolved_example_round_trips():
    r = ResolvedAssembly.model_validate(EXAMPLE_RESOLVED)
    assert r.part_ids == ["hide", "bowl", "bottle", "tube", "hide2"]
    assert r.template_of("hide2") == "hideout"
    assert r.join_to("hide2").parent == "tube.end_a" and r.join_to("hide") is None
    stored = r.stored()
    assert stored == EXAMPLE_RESOLVED
    assert ResolvedAssembly.from_stored(json.loads(json.dumps(stored))) == r
    # 정수 값은 정수로 남는다 (2.0 이 아니라 2)
    assert '"hide.entrance_count":2' in r.canonical()


def test_canonical_independent_of_key_order():
    a = ResolvedAssembly.model_validate(EXAMPLE_RESOLVED)
    shuffled = {k: EXAMPLE_RESOLVED[k] for k in reversed(list(EXAMPLE_RESOLVED))}
    shuffled["fixed"] = dict(reversed(list(EXAMPLE_RESOLVED["fixed"].items())))
    shuffled["faces"] = dict(reversed(list(EXAMPLE_RESOLVED["faces"].items())))
    b = ResolvedAssembly.model_validate(shuffled)
    assert a.canonical() == b.canonical() and a.digest() == b.digest()
    assert a.canonical() == canonical_json(json.loads(a.canonical()))
    assert " " not in a.canonical().replace("compose/1", "")


def test_digests_track_the_right_fields():
    base = ResolvedAssembly.model_validate(EXAMPLE_RESOLVED)
    d = resolved()
    d["joins"][0]["shift"] = 2.0
    moved = ResolvedAssembly.model_validate(d)
    assert moved.digest() != base.digest() and moved.geometry_digest() != base.geometry_digest()
    d = resolved(ties=[], fixed={})
    untied = ResolvedAssembly.model_validate(d)
    # ties·fixed 는 형상을 바꾸지 않는다: 형상 지문은 같고 전체(캐시 키)는 다르다
    assert untied.geometry_digest() == base.geometry_digest() and untied.digest() != base.digest()
    assert json.loads(base.geometry_canonical()).keys() == {"parts", "joins"}


def test_resolved_rejects_bad_structure():
    assert "root" in errors(resolved(root="bowl"), ResolvedAssembly)
    d = resolved()
    d["joins"][3]["child"] = "bowl.front"  # bowl 이 두 번, hide2 는 이어지지 않음
    msg = errors(d, ResolvedAssembly)
    assert "한 부품에만" in msg and "hide2" in msg
    d = resolved()
    d["faces"].pop("hide2")
    assert "faces" in errors(d, ResolvedAssembly)
    d = resolved()
    d["faces"]["hide"] = "front"
    assert "faces" in errors(d, ResolvedAssembly)
    d = resolved()
    d["faces"]["bowl"] = "auto"  # 해석한 뒤에는 실제 면만
    errors(d, ResolvedAssembly)
    assert "없는 부품" in errors(resolved(fixed={"nope.shape": "box"}), ResolvedAssembly)
    assert "ties" in errors(resolved(ties=[{"follower": "x.a", "owner": "hide.a"}]), ResolvedAssembly)
    assert errors(resolved(v=2), ResolvedAssembly)


def test_resolved_ties_point_at_final_owner():
    d = resolved(ties=[
        {"follower": "tube.inner_diameter_mm", "owner": "hide.entrance_diameter_mm"},
        {"follower": "hide2.entrance_diameter_mm", "owner": "tube.inner_diameter_mm"},
    ])
    assert "owner" in errors(d, ResolvedAssembly)
    d = resolved(ties=[
        {"follower": "tube.inner_diameter_mm", "owner": "hide.entrance_diameter_mm"},
        {"follower": "tube.inner_diameter_mm", "owner": "hide2.entrance_diameter_mm"},
    ])
    assert "둘 이상" in errors(d, ResolvedAssembly)


def test_to_request_writes_resolved_sides_back():
    r = ResolvedAssembly.model_validate(EXAMPLE_RESOLVED)
    params = {p["id"]: p["params"] for p in EXAMPLE_REQUEST["parts"]}
    eff = r.to_request(params, name_ko="급식 은신처")
    assert [p.id for p in eff.parts] == r.part_ids
    assert [(c.part, c.to, c.at) for c in eff.connections] == [
        ("bowl", "hide", "right"), ("bottle", "hide", "left"), ("tube", "hide", "front"), ("hide2", "tube", "free_end"),
    ]
    assert eff.part("hide").params == HIDE and eff.name_ko == "급식 은신처"


# --- 표시 형태 ---


def test_part_names_number_repeated_templates():
    parts = [ResolvedPart(id=i, template=t) for i, t in
             [("hide", "hideout"), ("tube", "tunnel"), ("hide2", "hideout"), ("hide3", "hideout"), ("x", "mystery")]]
    names = part_names(parts, {"hideout": "은신처", "tunnel": "터널"})
    assert names == {"hide": "은신처", "tube": "터널", "hide2": "은신처 2", "hide3": "은신처 3", "x": "mystery"}


def test_assembly_display_shape():
    r = ResolvedAssembly.model_validate(EXAMPLE_RESOLVED)
    names = {"hideout": "은신처", "bowl_holder": "그릇 받침", "bottle_stand": "물병 거치대", "tunnel": "터널"}
    disp = assembly_display(r, names)
    assert isinstance(disp, AssemblyDisplay)
    out = disp.model_dump(mode="json")
    assert out["parts"][4] == {"id": "hide2", "template": "hideout", "name_ko": "은신처 2"}
    assert out["joins"] == [
        {"part": "bowl", "to": "hide", "at": "right", "mount": "slide", "passage": False},
        {"part": "bottle", "to": "hide", "at": "left", "mount": "slide", "passage": False},
        {"part": "tube", "to": "hide", "at": "front", "mount": "plug", "passage": "into_parent"},
        {"part": "hide2", "to": "tube", "at": "free_end", "mount": "plug", "passage": "into_child"},
    ]


# --- 템플릿 연결 표준 기본값 (base.py) ---


class _BoxParams(TemplateParams):
    w: float = 30.0
    d: float = 20.0
    h: float = 10.0


class _BoxTemplate(Template):
    key = "test_box"
    display_name_ko = "상자"
    description_ko = "시험용"
    Params = _BoxParams
    height_field = "h"

    def __init__(self) -> None:
        self.builds = 0

    def constraints(self, p, ctx):
        return []

    def build(self, p):
        self.builds += 1
        return Box(p.w, p.d, p.h, align=(Align.CENTER, Align.CENTER, Align.MIN))

    def features(self, p):
        return Features(min_wall_thickness_mm=p.w)


def test_anchor_and_face_fields_defaults():
    a = Anchor((0, 0, 0), (0, -1, 0), (0, 0, 1), side="front", port=60.0, wall_mm=3.0)
    assert a.profile is None
    assert Anchor((0, 0, 0), (0, -1, 0), (0, 0, 1), port=60.0, profile="round_arch").profile == "round_arch"
    assert FaceFields() == FaceFields(None, None, None, None, None)


def test_template_connection_defaults_are_noops():
    t = _BoxTemplate()
    p = t.Params()
    assert t.role == "none" and not t.composable
    assert t.attach_order == {} and t.passes_access is False and t.level_field is None
    assert t.face_fields(p, "front") == FaceFields()
    assert t.open_port(p, "back") is None
    assert t.face_needs(p) == (None, None)
    assert t.joined_constraints(p, None, "back") == []  # type: ignore[arg-type]
    assert t.assembly_constraints(p, None) == []  # type: ignore[arg-type]


def test_envelope_default_is_cached_bounding_box():
    t = _BoxTemplate()
    p = t.Params(w=31.0, d=22.0, h=12.5)
    w, d, h = t.envelope(p)
    assert (w, d, h) == pytest.approx((31.0, 22.0, 12.5), abs=1e-3)
    assert t.envelope(t.Params(w=31.0, d=22.0, h=12.5)) == (w, d, h)
    assert t.builds == 1
    assert t.envelope(t.Params(w=40.0))[0] == pytest.approx(40.0, abs=1e-3)
    assert t.builds == 2


def test_cage_height_default_matches_height_field_cap():
    """케이지 높이 제약 기본값 = 지금 엔진 케이지 분기(height_field 상한)와 같은 제약."""
    from app.templates.keys import TEMPLATE_MODULES
    from app.templates.registry import get_template

    ctx: RuleContext = None  # type: ignore[assignment]  기본 구현은 ctx 를 쓰지 않는다
    t = _BoxTemplate()
    assert t.cage_height_constraints(t.Params(), ctx, 250.0, "이유") == [
        ParamConstraint("h", max=250.0, source="geometry", reason_ko="이유")]
    for key in TEMPLATE_MODULES:
        tpl = get_template(key)
        got = tpl.cage_height_constraints(tpl.Params(), ctx, 250.0, "이유")
        want = [ParamConstraint(tpl.height_field, max=250.0, source="geometry", reason_ko="이유")] \
            if tpl.height_field else []
        assert got == want, key


def test_tree_problems_rejects_model_prefixed_ids():
    """model_ 로 시작하는 id 는 조립 파라미터 모델 필드(model_dump 등)와 겹칠 수 있어 받지 않는다."""
    assert tree_problems(["hide", "model_dump"], [("model_dump", "hide")])
    assert not tree_problems(["hide", "modelx"], [("modelx", "hide")])
