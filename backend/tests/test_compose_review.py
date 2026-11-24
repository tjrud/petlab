"""자유 조립 리뷰에서 찾은 문제의 회귀 테스트: 해석기(compose)·조립 규칙(assembly)·엔진·해석기 출력 검증(spec).

형상을 만드는 검사(slot_gaps·엔진)는 꼭 필요한 경우만 돌린다."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from app.domain import Cage
from app.llm.spec import Connection, connection_problems
from app.modules import compose
from app.modules.assembly import (
    JoinSpec,
    PartSpec,
    merge_features,
    part_meshes,
    place_parts,
    slide_problems,
    slot_gaps,
)
from app.modules.module_template import unique_keys
from app.modules.structure import AssemblyRequest, tree_problems
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.base import PrintPart, RuleContext
from app.templates.registry import primitives
from app.validation.autofix import clamp_params
from app.validation.report import Issue, Severity

P = primitives()
SIZES = ("dwarf", "syrian")
BED = 220.0


def rctx(rules, size: str) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), 1,
                       printing_max_overhang_deg=rules.printing.max_overhang_deg,
                       min_feature_mm=rules.printing.min_feature_mm,
                       build_volume_mm=(BED, BED, 250.0))


def dp(key: str, ctx: RuleContext | None = None, **over) -> dict:
    return {**P[key].default_params(ctx).model_dump(), **over}


def request(parts: list[tuple], conns: list[tuple]) -> AssemblyRequest:
    return AssemblyRequest(parts=[{"id": a, "template": b, "params": c} for a, b, c in parts],
                           connections=[{"part": a, "to": b, "at": c} for a, b, c in conns])


def settle(res, params, ctx):
    t = compose.template_for(res)
    p, issues = clamp_params(t, compose.assembly_params(t, params), ctx, max_passes=compose.ASSEMBLY_MAX_PASSES)
    return t, p, issues


def engine(rules, req: AssemblyRequest, size: str = "dwarf"):
    ctx = EngineContext(cage=Cage(1000, 600, 400), species="hamster", size=size, count=1, rules=rules)
    spec = ItemSpec(template="assembly", params={p.id: p.params for p in req.parts}, assembly=req)
    return run_engine([spec], ctx)


# ── 해석기 ──


@pytest.mark.parametrize("root,over", [
    ("hideout", {"entrance_diameter_mm": 140, "width_mm": 300, "height_mm": 200, "depth_mm": 200}),
    ("house", {"doors": {"sides": ["front"], "width_mm": 140}, "width_mm": 300, "height_mm": 200, "depth_mm": 200}),
])
def test_inserted_tunnel_is_clipped_to_its_range(rules, root, over) -> None:
    """방끼리 이을 때 끼우는 터널: 출입구가 터널 내경 범위보다 넓어도 예외가 아니다. 터널 내경은 범위 안으로 자르고,
    조립 항목 보정이 주인 값(출입구)을 터널이 따를 수 있는 범위로 낮추거나 충돌로 알린다 (집은 단면 모양이 달라 해석 오류)."""
    ctx = rctx(rules, "syrian")
    req = request([("a", root, dp(root, ctx, **over)), ("b", "hideout", dp("hideout", ctx))], [("b", "a", "front")])
    out = compose.resolve(req, None, ctx)
    if isinstance(out, Issue):
        assert out.code in compose.ERROR_CODES
        return
    res, params, _ = out
    _, hi = compose.field_bounds(P["tunnel"].Params, "inner_diameter_mm")
    assert params["b_link"].inner_diameter_mm <= hi
    _, p, issues = settle(res, params, ctx)
    if not any(i.code == "param_conflict" for i in issues):
        assert p.b_link.inner_diameter_mm == pytest.approx(p.a.entrance_diameter_mm)
        assert p.a.entrance_diameter_mm <= hi


def test_ties_apply_before_the_tunnel_bend_turns_a_room(rules) -> None:
    """터널 내경이 출입구를 따라 커지면 휘는 각도 상한이 줄어든다: 해석 때 이미 줄여 방향을 정하므로 끝의 방이 비스듬해지고
    그 방에 받침을 끼울 수 없다는 것을 해석기가 알린다 (보정 뒤에 받침이 비스듬한 방에 붙지 않게)."""
    ctx = rctx(rules, "dwarf")
    req = request([("hide", "hideout", dp("hideout", ctx, entrance_diameter_mm=70)),
                   ("tube", "tunnel", dp("tunnel", ctx, bend_angle_deg=90, length_mm=100, inner_diameter_mm=55,
                                         shape="round_arch")),
                   ("hide2", "hideout", dp("hideout", ctx)), ("bowl", "bowl_holder", dp("bowl_holder", ctx))],
                  [("tube", "hide", "front"), ("hide2", "tube", "free_end"), ("bowl", "hide2", "auto")])
    out = compose.resolve(req, None, ctx)
    assert isinstance(out, Issue) and out.code == compose.JOIN_UNSUPPORTED
    assert "비스듬히" in out.message_ko


def test_slide_on_a_slanted_parent_is_a_rule_problem(rules) -> None:
    """보정 뒤 다시 검사: 슬라이드 결합의 부모가 축에 맞지 않게 놓였으면 규칙 위반."""
    ctx = rctx(rules, "dwarf")
    parts = [PartSpec("hide", P["hideout"], P["hideout"].Params.model_validate(dp("hideout", ctx))),
             PartSpec("tube", P["tunnel"], P["tunnel"].Params.model_validate(
                 dp("tunnel", ctx, bend_angle_deg=45, shape="round_arch"))),
             PartSpec("hide2", P["hideout"], P["hideout"].Params.model_validate(dp("hideout", ctx))),
             PartSpec("bowl", P["bowl_holder"], P["bowl_holder"].Params.model_validate(dp("bowl_holder", ctx)))]
    joins = [JoinSpec("hide", "front", "tube", "end_b", passage=True, mount="plug"),
             JoinSpec("tube", "end_a", "hide2", "front", passage=True, mount="plug", reverse=True),
             JoinSpec("hide2", "right", "bowl", "back", mount="slide")]
    assert any("비스듬히" in m for m in slide_problems(parts, joins))


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("kids", [("bowl_holder", "bowl_holder"), ("bowl_holder", "bottle_stand"),
                                  ("ramp", "bowl_holder")])
def test_two_accessories_on_one_side_fit_the_bed(rules, size, kids) -> None:
    """한 면에 둘을 붙여 본체가 출력 공간을 넘게 되면 다음 빈 면으로 옮긴다. 남으면 본체 가로·세로 + 연결판이 바닥에 든다."""
    ctx = rctx(rules, size)
    req = request([("hide", "hideout", dp("hideout", ctx))] + [(f"k{i}", k, dp(k, ctx)) for i, k in enumerate(kids)],
                  [(f"k{i}", "hide", "right") for i in range(len(kids))])
    res, params, _ = compose.resolve(req, None, ctx)
    _, p, issues = settle(res, params, ctx)
    assert not [i for i in issues if i.severity == Severity.error], [i.message_ko for i in issues]
    plates = {"x": 0, "y": 0}
    for j in res.joins:
        if j.mount == "slide":
            plates["x" if j.parent_anchor in ("left", "right") else "y"] += 1
    assert p.hide.width_mm + plates["x"] * compose.PLATE_OUT_MM <= BED
    assert p.hide.depth_mm + plates["y"] * compose.PLATE_OUT_MM <= BED


def test_wide_host_with_plates_is_capped_by_the_bed(rules) -> None:
    """모래목욕통(기본 가로 216mm) 양옆에 연결판을 붙이면 가로를 줄여 출력 공간에 맞춘다."""
    ctx = rctx(rules, "dwarf")
    req = request([("bath", "sand_bath", dp("sand_bath", ctx)), ("bottle", "bottle_stand", dp("bottle_stand", ctx)),
                   ("bowl", "bowl_holder", dp("bowl_holder", ctx))],
                  [("bottle", "bath", "left"), ("bowl", "bath", "right")])
    res, params, _ = compose.resolve(req, None, ctx)
    _, p, issues = settle(res, params, ctx)
    if not [i for i in issues if i.severity == Severity.error]:
        assert p.bath.width_mm + 2 * compose.PLATE_OUT_MM <= BED


@pytest.mark.parametrize("side", ["right", "left", "back", "auto"])
def test_ramp_on_a_default_house_settles(rules, side) -> None:
    """평지붕 1층 집: 면 높이 = 집 높이라 램프 경사 한도에 맞춰 집 높이를 낮춘다 (경사각 충돌로 끝나지 않는다)."""
    ctx = rctx(rules, "dwarf")
    req = request([("ho", "house", dp("house", ctx)), ("ramp", "ramp", dp("ramp", ctx))], [("ramp", "ho", side)])
    res, params, _ = compose.resolve(req, None, ctx)
    _, p, issues = settle(res, params, ctx)
    assert not [i for i in issues if i.severity == Severity.error], [i.message_ko for i in issues]
    assert p.ramp.height_mm == pytest.approx(p.ho.height_mm)
    assert p.ramp.slope_deg <= ctx.size.max_ramp_angle_deg + 1e-6


@pytest.mark.parametrize("height", [105, 130, 200])
def test_ramp_lowers_a_tall_hideout(rules, height) -> None:
    ctx = rctx(rules, "dwarf")
    req = request([("h", "hideout", dp("hideout", ctx, height_mm=height)), ("ramp", "ramp", dp("ramp", ctx))],
                  [("ramp", "h", "right")])
    res, params, _ = compose.resolve(req, None, ctx)
    _, p, issues = settle(res, params, ctx)
    assert not [i for i in issues if i.severity == Severity.error], [i.message_ko for i in issues]
    assert p.ramp.height_mm == pytest.approx(p.h.height_mm)
    assert p.ramp.slope_deg <= ctx.size.max_ramp_angle_deg + 1e-6


def test_ramp_on_a_face_that_cannot_come_down_is_refused(rules) -> None:
    """박공지붕 집: 면 높이를 움직일 파라미터가 없고 램프가 오를 수 있는 높이보다 높으면 해석기가 바로 알린다."""
    ctx = rctx(rules, "dwarf")
    house = dp("house", ctx, height_mm=220.0, roof={"kind": "pitched", "pitch_deg": 50.0, "tip_deg": 50.0})
    req = request([("ho", "house", house), ("ramp", "ramp", dp("ramp", ctx))], [("ramp", "ho", "left")])
    out = compose.resolve(req, None, ctx)
    assert isinstance(out, Issue) and out.code == compose.JOIN_UNSUPPORTED, out
    assert "오를 수 있는 높이" in out.message_ko


def test_accessory_on_the_exit_wall_stays_and_a_side_door_opens(rules) -> None:
    """방의 출구 벽(은신처 뒤)을 받침이 차지했으면: 은신처는 받침을 옮기지 않고 빈 옆면에 옆면 출입구를 낸다
    (2단계, 설계 문서 §3.2: 요청한 자리를 지킨다)."""
    ctx = rctx(rules, "dwarf")
    req = request([("hide", "hideout", dp("hideout", ctx)), ("bowl", "bowl_holder", dp("bowl_holder", ctx)),
                   ("tube", "tunnel", dp("tunnel", ctx)), ("hide2", "hideout", dp("hideout", ctx)),
                   ("bowl2", "bowl_holder", dp("bowl_holder", ctx))],
                  [("bowl", "hide", "back"), ("tube", "hide", "front"), ("hide2", "tube", "free_end"),
                   ("bowl2", "hide2", "front")])
    res, params, issues = compose.resolve(req, None, ctx)
    assert params["hide"].entrance_count == 1 and params["hide"].side_doors == "left"
    assert params["hide2"].entrance_count == 1 and params["hide2"].side_doors == "left"
    assert "join_relocated" not in {i.code for i in issues}
    used = {(j.parent, j.child) for j in res.joins}
    assert ("hide.back", "bowl.back") in used and ("hide2.back", "bowl2.back") in used
    assert [i.details for i in issues if i.code == "exit_added"] == [{"part": "hide", "anchor": "left"},
                                                                     {"part": "hide2", "anchor": "left"}]
    t = compose.template_for(res)
    p = compose.assembly_params(t, params)
    assert t.features(p).entrance_count >= 2


@pytest.mark.parametrize("bend", [90, 180])
def test_rooms_that_overlap_through_a_short_bent_tunnel_are_refused(rules, bend) -> None:
    ctx = rctx(rules, "dwarf")
    req = request([("h1", "hideout", dp("hideout", ctx)),
                   ("t1", "tunnel", dp("tunnel", ctx, bend_angle_deg=bend, length_mm=100)),
                   ("h2", "hideout", dp("hideout", ctx))],
                  [("t1", "h1", "front"), ("h2", "t1", "free_end")])
    out = compose.resolve(req, None, ctx)
    assert isinstance(out, Issue) and out.code == compose.JOIN_UNSUPPORTED
    assert "겹칩니다" in out.message_ko


def test_bent_round_arch_tunnel_names_the_support_need(rules) -> None:
    ctx = rctx(rules, "dwarf")
    req = request([("hide", "hideout", dp("hideout", ctx)), ("tube", "tunnel", dp("tunnel", ctx, bend_angle_deg=45))],
                  [("tube", "hide", "front")])
    _, _, issues = compose.resolve(req, None, ctx)
    assert any(i.details.get("support") and i.details.get("part") == "tube" for i in issues)


def test_effective_spec_keeps_the_same_canonical_structure(rules) -> None:
    """고친 명세(보정된 값)를 다시 해석해도 저장 형태가 같다: 통로로 이은 방의 출입구 구조 값은 늘 fixed 에 든다."""
    ctx = rctx(rules, "dwarf")
    for bend in (0, 45):
        req = request([("h1", "hideout", dp("hideout", ctx)), ("t1", "tunnel", dp("tunnel", ctx, bend_angle_deg=bend)),
                       ("h2", "hideout", dp("hideout", ctx)), ("t2", "tunnel", dp("tunnel", ctx)),
                       ("h3", "hideout", dp("hideout", ctx))],
                      [("t1", "h1", "front"), ("h2", "t1", "free_end"), ("t2", "h2", "auto"), ("h3", "t2", "free_end")])
        res, params, _ = compose.resolve(req, None, ctx)
        _, p, _ = settle(res, params, ctx)
        again = compose.resolve(res.to_request({pid: getattr(p, pid).model_dump() for pid in res.part_ids}), None, ctx)
        assert not isinstance(again, Issue), again
        assert again[0].canonical() == res.canonical()
        assert res.fixed["h1.entrance_count"] == 2


# ── 조립 규칙 (형상) ──


def _settled_parts(rules, size: str, req: AssemblyRequest):
    ctx = rctx(rules, size)
    res, params, _ = compose.resolve(req, None, ctx)
    t, p, _ = settle(res, params, ctx)
    parts, joins = t.expand(p)
    return ctx, t, p, parts, joins


@pytest.mark.parametrize("size", SIZES)
def test_bent_tunnel_pocket_against_its_own_hideout_is_a_gap(rules, size) -> None:
    """이은 쌍도 이은 자리(끼움 구멍 둘레)만 빼고 마주 보는 틈을 본다: 90° 터널 안쪽과 은신처 앞벽 사이 주머니."""
    req = request([("hide", "hideout", {}), ("tube", "tunnel", {"bend_angle_deg": 90})], [("tube", "hide", "front")])
    ctx, t, p, parts, joins = _settled_parts(rules, size, req)
    gaps = slot_gaps(parts, joins, part_meshes(parts, joins), ctx.size.gap_trap)
    assert ("hide", "tube") in {(a, b) for a, b, _ in gaps}
    assert any("끼임 위험" in m for m in t.rule_issues(p, ctx))


@pytest.mark.parametrize("bend,size", [(45, "dwarf"), (135, "syrian"), (180, "syrian")])
def test_bent_tunnel_mouth_is_an_access_side(rules, bend, size) -> None:
    """쓰지 않은 터널 끝의 조립 좌표 방향(비스듬하면 이웃한 두 면)이 드나드는 면에 든다."""
    req = request([("hide", "hideout", {}), ("tube", "tunnel", {"bend_angle_deg": bend})], [("tube", "hide", "front")])
    _, _, p, parts, joins = _settled_parts(rules, size, req)
    f = merge_features(parts, joins, enclosure=True)
    placed = place_parts(parts, joins)
    used = {(j.child, j.child_anchor) for j in joins} | {(j.parent, j.parent_anchor) for j in joins}
    mouth = next(n for n, a in P["tunnel"].anchors(p.tube).items() if a.port is not None and ("tube", n) not in used)
    v = placed["tube"].vector(np.asarray(P["tunnel"].anchors(p.tube)[mouth].normal, dtype=float))
    near = max(("front", "back", "left", "right"),
               key=lambda s: float(np.dot(v, {"front": (0, -1, 0), "back": (0, 1, 0), "left": (-1, 0, 0),
                                              "right": (1, 0, 0)}[s])))
    assert near in f.access_sides, (f.access_sides, v)


def test_print_part_keys_are_unique() -> None:
    a = PrintPart("본체", None, np.eye(3), key="body")  # type: ignore[arg-type]
    b = PrintPart("물병 거치대 받침판", None, np.eye(3), key="bottle_base")  # type: ignore[arg-type]
    c = PrintPart("그릇 받침", None, np.eye(3), key="bottle_base")  # type: ignore[arg-type]
    keys = [pp.key for pp in unique_keys([a, b, c])]
    assert keys == ["body", "bottle_base", "bottle_base_2"]


def test_body_is_a_reserved_part_id() -> None:
    assert any("body" in m for m in tree_problems(["hide", "body"], [("body", "hide")]))


# ── 해석기 출력 검증 ──


def test_tunnel_between_house_and_hideout_is_rejected_at_parse() -> None:
    conns = [Connection(part="tube", to="house", at="front"), Connection(part="hide", to="tube", at="free_end")]
    problems = connection_problems([("house", "house"), ("tube", "tunnel"), ("hide", "hideout")], conns)
    assert any("단면 모양이 달라" in m for m in problems)
    direct = connection_problems([("house", "house"), ("hide", "hideout")],
                                 [Connection(part="hide", to="house", at="front")])
    assert any("단면 모양이 달라" in m for m in direct)


@pytest.mark.parametrize("at", ["front", "auto"])
def test_tunnel_on_a_sand_bath_is_rejected_at_parse(at) -> None:
    problems = connection_problems([("bath", "sand_bath"), ("tube", "tunnel")],
                                   [Connection(part="tube", to="bath", at=at)])
    assert any("출입구가 없어" in m for m in problems)


# ── 엔진 ──


def test_engine_labels_are_the_same_for_resolver_and_clamp_notices(rules) -> None:
    ctx = rctx(rules, "dwarf")
    req = request([("hide", "hideout", dp("hideout", ctx, depth_mm=60)), ("bowl", "bowl_holder", dp("bowl_holder", ctx))],
                  [("bowl", "hide", "right")])
    out = engine(rules, req)
    labels = {i.message_ko.split(": ", 1)[0] for i in out.report.issues if i.item_index == 0}
    assert len(labels) == 1, labels


def test_engine_two_accessories_on_one_side_print_within_the_bed(rules) -> None:
    ctx = rctx(rules, "dwarf")
    req = request([("hide", "hideout", dp("hideout", ctx)), ("bowl", "bowl_holder", dp("bowl_holder", ctx)),
                   ("bottle", "bottle_stand", dp("bottle_stand", ctx))],
                  [("bowl", "hide", "right"), ("bottle", "hide", "right")])
    out = engine(rules, req)
    assert out.report.passed, [i.message_ko for i in out.report.issues if i.severity == Severity.error]
    assert not [i for i in out.report.issues if i.code == "exceeds_build_volume"]


def test_engine_does_not_raise_for_a_wide_door_between_rooms(rules) -> None:
    ctx = rctx(rules, "syrian")
    req = request([("a", "hideout", dp("hideout", ctx, entrance_diameter_mm=140, width_mm=300, height_mm=200,
                                       depth_mm=200)),
                   ("b", "hideout", dp("hideout", ctx))], [("b", "a", "front")])
    out = engine(rules, req, "syrian")  # 예외 없이 끝난다 (예전에는 pydantic ValidationError 로 500)
    assert out.items or not out.report.passed


def test_rule_context_bed_defaults(rules) -> None:
    ctx = dataclasses.replace(rctx(rules, "dwarf"), build_volume_mm=None)
    assert compose.bed_xy(ctx) == pytest.approx(220.0)
