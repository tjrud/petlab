"""자유 조립 항목 템플릿 (app/modules/composed.ComposedTemplate) 과 자동 보정의 조립 항목 지원.

손으로 만든 해석 결과(ResolvedAssembly): 은신처 + 오른쪽 그릇 받침(슬라이드) + 왼쪽 물병 거치대(슬라이드)
+ 앞 터널(끼움) + 터널 끝 두 번째 은신처(끼움, into_child)."""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from app.geometry.mesh import mesh_health, part_to_mesh
from app.modules.composed import ComposedTemplate, generated_name
from app.modules.structure import ResolvedAssembly
from app.templates.base import ParamConstraint, RuleContext
from app.templates.registry import primitives
from app.validation.autofix import _desc, clamp_params, shrink_params
from app.validation.report import Severity

BED_MM = (220.0, 220.0, 250.0)

COMBO = {
    "root": "hide",
    "parts": [{"id": "hide", "template": "hideout"}, {"id": "bowl", "template": "bowl_holder"},
              {"id": "bottle", "template": "bottle_stand"}, {"id": "tube", "template": "tunnel"},
              {"id": "hide2", "template": "hideout"}],
    "joins": [
        {"parent": "hide.right", "child": "bowl.back", "mount": "slide", "passage": False},
        {"parent": "hide.left", "child": "bottle.back", "mount": "slide", "passage": False},
        {"parent": "hide.front", "child": "tube.end_b", "mount": "plug", "passage": "into_parent"},
        {"parent": "tube.end_a", "child": "hide2.front", "mount": "plug", "passage": "into_child"},
    ],
    "ties": [{"follower": "tube.inner_diameter_mm", "owner": "hide.entrance_diameter_mm"},
             {"follower": "hide2.entrance_diameter_mm", "owner": "hide.entrance_diameter_mm"}],
    "fixed": {"tube.shape": "round_arch", "hide.entrance_count": 2, "hide2.entrance_count": 2},
    "faces": {"bowl": "right", "bottle": "left", "tube": "front", "hide2": "free_end"},
}
HIDE = {"width_mm": 140, "depth_mm": 120, "height_mm": 95, "entrance_diameter_mm": 60, "entrance_count": 2}
PARAMS = {
    "hide": HIDE,
    "bowl": {"bowl_diameter_mm": 90, "bowl_height_mm": 40, "collar_height_mm": 35},
    "bottle": {"base_width_mm": 110, "base_depth_mm": 110},
    "tube": {"length_mm": 100, "inner_diameter_mm": 60, "shape": "round_arch", "bend_angle_deg": 0},
    "hide2": HIDE,
}


def rctx(rules, size: str) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size),
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def resolved(**over) -> ResolvedAssembly:
    return ResolvedAssembly.model_validate({**COMBO, **over})


@pytest.fixture(scope="module")
def combo() -> tuple[ComposedTemplate, object]:
    t = ComposedTemplate(resolved())
    return t, t.Params.model_validate(PARAMS)


# ── 구조·파라미터 (형상 없이) ──

def test_params_are_nested_by_part_id(combo) -> None:
    t, p = combo
    assert t.key == "assembly"
    assert list(t.Params.model_fields) == ["hide", "bowl", "bottle", "tube", "hide2"]
    P = primitives()
    for pid, key in (("hide", "hideout"), ("bowl", "bowl_holder"), ("tube", "tunnel"), ("hide2", "hideout")):
        assert isinstance(getattr(p, pid), P[key].Params)
    # 기본값: 부품마다 그 템플릿의 기본값
    d = t.Params()
    assert d.hide == P["hideout"].Params() and d.tube == P["tunnel"].Params()
    assert t.Params.model_validate(p.model_dump()) == p
    with pytest.raises(ValueError):
        t.Params.model_validate({**PARAMS, "ghost": {}})


def test_names_and_ordinals(combo) -> None:
    t, _ = combo
    assert t.display_name_ko == "그릇 받침·물병 거치대·터널·은신처가 달린 은신처"
    assert t.names == {"hide": "은신처", "bowl": "그릇 받침", "bottle": "물병 거치대", "tube": "터널", "hide2": "은신처 2"}
    assert ComposedTemplate(resolved(), name_ko="급식 은신처").display_name_ko == "급식 은신처"
    names = {"hideout": "은신처", "tunnel": "터널", "bowl_holder": "그릇 받침"}
    two = resolved(parts=COMBO["parts"][:1] + [{"id": "tube", "template": "tunnel"}],
                   joins=[COMBO["joins"][2]], ties=[], fixed={}, faces={"tube": "front"})
    assert generated_name(two, names) == "터널이 달린 은신처"  # 받침이 있는 마지막 글자 → '이'


def test_expand_uses_stored_joins(combo) -> None:
    t, p = combo
    parts, joins = t.expand(p)
    assert [q.id for q in parts] == ["hide", "bowl", "bottle", "tube", "hide2"]
    assert parts[4].params.entrance_diameter_mm == 60
    assert [(j.parent, j.parent_anchor, j.child, j.child_anchor, j.mount, j.passage, j.reverse) for j in joins] == [
        ("hide", "right", "bowl", "back", "slide", False, False),
        ("hide", "left", "bottle", "back", "slide", False, False),
        ("hide", "front", "tube", "end_b", "plug", True, False),
        ("tube", "end_a", "hide2", "front", "plug", True, True),
    ]
    assert t.split and t.has_slide and t.enclosure


def test_load_stored_params_applies_part_legacy_defaults(combo) -> None:
    t, _ = combo
    raw = {pid: dict(v) for pid, v in PARAMS.items()}
    del raw["hide"]["entrance_count"]  # entrance_count 가 생기기 전에 저장된 은신처
    p = t.load_stored_params(raw)
    assert p.hide.entrance_count == 1 and p.hide2.entrance_count == 2
    with pytest.raises(ValueError):
        t.load_stored_params({**raw, "ghost": {}})


def test_reserved_part_id_rejected() -> None:
    bad = {**COMBO, "root": "model_dump",
           "parts": [{"id": "model_dump", "template": "hideout"}, {"id": "tube", "template": "tunnel"}],
           "joins": [{"parent": "model_dump.front", "child": "tube.end_b", "mount": "plug", "passage": "into_parent"}],
           "ties": [], "fixed": {}, "faces": {"tube": "front"}}
    with pytest.raises(ValueError, match="model_dump"):
        ComposedTemplate(ResolvedAssembly.model_validate(bad))


# ── 제약·자동 보정 ──

def test_fallback_constraints_prefixed_and_redirected(combo, rules) -> None:
    t, p = combo
    cons = t.fallback_constraints(p, rctx(rules, "syrian"))
    ids = set(t.Params.model_fields)
    assert cons and all(c.field.split(".")[0] in ids and "." in c.field for c in cons)
    # 따르는 치수(터널 내경·두 번째 은신처 출입구)에는 '주인 값과 같게' 외의 제약이 걸리지 않는다: 종 기준은 주인 값으로 간다
    followers = {"tube.inner_diameter_mm", "hide2.entrance_diameter_mm"}
    for c in cons:
        if c.field in followers:
            assert c.min == c.max == 60.0, c
    owner = [c for c in cons if c.field == "hide.entrance_diameter_mm"]
    assert {c.min for c in owner if c.min is not None} >= {70.0}  # 은신처·터널 모두 시리안 70mm


def test_constraints_use_derived_hook(combo, rules, monkeypatch) -> None:
    t, p = combo
    seen = []

    def derived_constraints(res, params, ctx):
        seen.append((res, params))
        return [ParamConstraint("hide.width_mm", min=150.0)]

    monkeypatch.setitem(sys.modules, "app.modules.compose",
                        types.SimpleNamespace(derived_constraints=derived_constraints))
    assert t.constraints(p, rctx(rules, "dwarf")) == [ParamConstraint("hide.width_mm", min=150.0)]
    assert seen == [(t.resolved, p)]


def test_constraints_fall_back_without_hook(combo, rules, monkeypatch) -> None:
    t, p = combo
    monkeypatch.setitem(sys.modules, "app.modules.compose", types.SimpleNamespace())
    c = rctx(rules, "dwarf")
    assert t.constraints(p, c) == t.fallback_constraints(p, c)


def test_height_constraints_prefixed(combo, rules) -> None:
    t, p = combo
    c = rctx(rules, "dwarf")
    cage = t.cage_height_constraints(p, c, 200.0, "이유")
    assert {x.field for x in cage} >= {"hide.height_mm", "hide2.height_mm"}
    assert all(x.max == 200.0 for x in cage)
    water = t.height_limit_constraints(p, c, 200.0, "이유")
    assert all("." in x.field for x in water)


def test_autofix_converges_and_follows_owner(combo, rules) -> None:
    t, p = combo
    c = rctx(rules, "syrian")
    fixed, issues = clamp_params(t, p, c, max_passes=12, label_ko="조립")
    assert not [i for i in issues if i.severity == Severity.error], issues
    assert fixed.hide.entrance_diameter_mm == 70
    assert fixed.tube.inner_diameter_mm == 70 and fixed.hide2.entrance_diameter_mm == 70
    assert fixed.tube.length_mm >= 1.5 * 70
    msgs = {i.details["field"]: i.message_ko for i in issues}
    assert msgs["hide.entrance_diameter_mm"].startswith("조립: 은신처 · ")
    assert msgs["hide2.entrance_diameter_mm"].startswith("조립: 은신처 2 · ")
    # 다시 보정해도 바뀌지 않는다 (고정점)
    again, issues2 = clamp_params(t, fixed, c, max_passes=12)
    assert again == fixed and issues2 == []


def test_max_passes_limits_the_chain(combo, rules) -> None:
    t, p = combo
    # 한 패스로는 주인 값만 오르고 따르는 치수는 다음 패스에서야 따라가므로 남은 위반이 오류로 남는다
    _, issues = clamp_params(t, p, rctx(rules, "syrian"), max_passes=1)
    assert any(i.code == "param_conflict" for i in issues)


def test_desc_prefixes_part_label(combo) -> None:
    t, _ = combo
    assert _desc(t.Params, "hide2.depth_mm") == f"은신처 2 · {_desc(primitives()['hideout'].Params, 'depth_mm')}"
    # 조립 항목이 아닌 중첩 파라미터(집의 문 폭)는 그대로
    house = primitives()["house"]
    assert " · " not in _desc(house.Params, "doors.width_mm")


def test_size_fields_and_dotted_shrink(rules, monkeypatch) -> None:
    P = primitives()
    monkeypatch.setattr(type(P["hideout"]), "role", "room_host")
    monkeypatch.setattr(type(P["bowl_holder"]), "role", "accessory")
    monkeypatch.setattr(type(P["tunnel"]), "role", "connector")
    t = ComposedTemplate(resolved(ties=[*COMBO["ties"], {"follower": "hide2.depth_mm", "owner": "hide.depth_mm"}]))
    assert t.size_fields == ("hide.width_mm", "hide.depth_mm", "hide.height_mm", "hide2.width_mm", "hide2.height_mm")
    p = t.Params.model_validate(PARAMS)
    s = shrink_params(t, p, 0.9)
    assert s.hide.width_mm == pytest.approx(126) and s.hide2.height_mm == pytest.approx(85.5)
    assert s.hide2.depth_mm == 120 and s.bowl == p.bowl and s.tube == p.tube


def test_reuse_problems() -> None:
    # 터널과 그릇 받침을 같은 앞 출입구에: 연결 지점 중복
    bad = resolved(
        parts=[{"id": "hide", "template": "hideout"}, {"id": "tube", "template": "tunnel"},
               {"id": "bowl", "template": "bowl_holder"}],
        joins=[COMBO["joins"][2], {"parent": "hide.front", "child": "bowl.back", "mount": "slide", "passage": False}],
        ties=[], fixed={}, faces={"tube": "front", "bowl": "front"})
    msgs = ComposedTemplate(bad).reuse_problems()
    assert len(msgs) == 1 and "'front'" in msgs[0] and "터널" in msgs[0]
    # 같은 옆면에 슬라이드로 나란히 끼우는 것은 된다
    ok = resolved(
        parts=[{"id": "hide", "template": "hideout"}, {"id": "b1", "template": "bowl_holder"},
               {"id": "b2", "template": "bowl_holder"}],
        joins=[{"parent": "hide.right", "child": "b1.back", "mount": "slide", "passage": False, "shift": -40},
               {"parent": "hide.right", "child": "b2.back", "mount": "slide", "passage": False, "shift": 40}],
        ties=[], fixed={}, faces={"b1": "right", "b2": "right"})
    assert ComposedTemplate(ok).reuse_problems() == []


# ── 형상 ──

def test_build_is_watertight(combo) -> None:
    t, p = combo
    h = mesh_health(part_to_mesh(t.build(p)))
    assert h.watertight and h.winding_consistent


def test_print_parts(combo) -> None:
    t, p = combo
    pps = t.print_parts(p)
    assert len(pps) == 6
    assert sorted(pp.key for pp in pps) == sorted(["body", "bowl", "bottle_base", "bottle_holder", "tube", "hide2"])
    assert {pp.key: pp.name_ko for pp in pps}["hide2"] == "은신처 2"
    for pp in pps:
        m = part_to_mesh(pp.part)
        assert mesh_health(m).watertight, pp.key
        bb = pp.part.bounding_box()
        ext = np.abs(pp.rotation @ np.array([bb.size.X, bb.size.Y, bb.size.Z]))
        assert np.all(ext <= np.array(BED_MM) + 1e-6), (pp.key, ext)
    assert t.features(p).entrance_count == 2  # 두 은신처의 뒷문


def test_rule_issues_clean_for_dwarf(combo, rules) -> None:
    t, p = combo
    # 열린 모서리를 사이에 둔 받침·거치대와 터널(상자 거리 약 42mm·41mm)은 끼임 틈이 아니다
    assert t.rule_issues(p, rctx(rules, "dwarf")) == []


def test_rule_issues_clean_for_syrian_after_autofix(combo, rules) -> None:
    t, p = combo
    c = rctx(rules, "syrian")
    fixed, _ = clamp_params(t, p, c, max_passes=12)
    assert t.rule_issues(fixed, c) == []
