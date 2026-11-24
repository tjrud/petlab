"""Part DSL 정적 검사 L01–L12 (app/library/lint.py, 설계 §7.3).

§6 의 세 초안(tests/data/library)은 깨끗해야 하고, 검사마다 작은 변형 파일에서 정확히 그 검사가 걸려야 한다.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.library import lint as L
from app.library.errors import DslError
from app.library.expr import RULE_NAMES, compile_part, port_height
from app.library.lint import (
    LintContext,
    LintIssue,
    LintReport,
    context_for,
    lint,
    lint_file,
    step_bbox,
)
from app.library.schema import parse_part

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "tests" / "data" / "library"
DRAFTS = ("tunnel_junction", "deck_platform", "litter_tray")


def draft(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def run(data: dict, **kw) -> LintReport:
    return lint(data, **kw)


def only(report: LintReport, lint_id: str) -> list[LintIssue]:
    """lint_id 만 걸렸는지 확인하고 그 문제들."""
    assert report.ids() == {lint_id}, report.text()
    return report.by_id(lint_id)


# ── §6 초안 ──

@pytest.mark.parametrize("name", DRAFTS)
def test_section6_drafts_lint_clean(name):
    r = lint_file(DATA / f"{name}.json")
    assert r.ok, r.text()
    assert r.context == "hamster/dwarf"
    assert r.variants[0] == "hamster/dwarf/c1/default"
    assert len(r.variants) > 5
    assert not r.skipped


@pytest.mark.parametrize("name", DRAFTS)
def test_section6_drafts_lint_clean_for_every_hamster_size_and_without_rules(name):
    book = L._default_rules()
    for size in book.species_file.species["hamster"].sizes:
        ctx = _context("hamster", size)
        r = lint(draft(name), context=ctx)
        assert r.ok and not r.skipped, (size, r.text())
    r = lint(draft(name), use_rules=False)
    assert r.ok and r.context is None, r.text()
    assert r.variants[0] == "default"


def _context(species: str, size: str) -> LintContext:
    from app.library.expr import rule_ctx_bindings

    book = L._default_rules()
    sz = book.species_file.species[species].sizes[size]
    ctx = L._Ctx(sz, book.min_wall_for(species, size), 1, tuple(book.printing.build_volume_mm))
    return LintContext(species, size, rule_ctx_bindings(ctx))


def test_defaults_follow_rule_defaults_of_the_first_size():
    """§6.1 표: dwarf 기본값 door 55, size 81, height 69."""
    part = parse_part(draft("tunnel_junction"))
    ctx = context_for(part.habitats)
    assert ctx is not None and ctx.case == "hamster/dwarf"
    values = L._defaults(part, compile_part(part), ctx)
    assert values["door_width_mm"] == 55 and values["size_mm"] == 81 and values["height_mm"] == 69
    assert values["layout"] == "T" and values["wall_thickness_mm"] == 3


def test_lint_is_kernel_free():
    code = (
        "import sys, json\n"
        "from app.library.lint import lint_file\n"
        "r = lint_file('tests/data/library/tunnel_junction.json')\n"
        "assert r.ok, r.text()\n"
        "heavy = [m for m in ('build123d', 'OCP', 'trimesh', 'shapely', 'numpy', 'sklearn', 'anthropic') "
        "if m in sys.modules]\n"
        "print(json.dumps(heavy))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=120,
                         check=False)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == []


def test_lint_is_fast():
    lint_file(DATA / "deck_platform.json")  # 규칙 파일 읽기 (한 번)
    t0 = time.perf_counter()
    for name in DRAFTS:
        lint_file(DATA / f"{name}.json")
    assert time.perf_counter() - t0 < 1.0


def test_schema_errors_are_not_lints():
    d = draft("deck_platform")
    d["bogus"] = 1
    with pytest.raises(DslError) as e:
        lint(d)
    assert e.value.code == "DSL012"


def test_repeat_limit_matches_template():
    from app.library.template import REPEAT_MAX

    assert L.REPEAT_MAX == REPEAT_MAX


# ── 단계 상자 = ops 형상의 bounding box ──

def _bbox_cases():
    cases = [("box", {"size": (10, 20, 30), "at": (1, 2, 3), "align": al}) for al in ("bottom", "center")]
    for ax in "xyz":
        for al in ("bottom", "center"):
            cases.append(("cylinder", {"r": 4, "h": 12, "axis": ax, "at": (1, 2, 3), "align": al}))
    for pl in ("xz", "yz", "xy"):
        cases.append(("prism", {"plane": pl, "points": [(-3, 0), (5, 1), (2, 7)], "depth": 6, "at": (1, 2, 3)}))
    for sh in ("round_arch", "pointed_arch", "box", "house"):
        for ax in "xy":
            cases.append(("passage", {"shape": sh, "width": 40, "axis": ax, "length": 15, "at": (1, 2, 3)}))
    return cases


@pytest.mark.parametrize(("op", "args"), _bbox_cases())
def test_step_bbox_matches_ops_geometry(op, args):
    from app.library import ops

    bb = ops.make(op, dict(args)).bounding_box()
    got = (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)
    assert step_bbox(op, args) == pytest.approx(got, abs=1e-6)


def test_passage_bbox_height_is_port_height():
    b = step_bbox("passage", {"shape": "pointed_arch", "width": 60, "axis": "y", "length": 10, "at": (0, 0, 5)})
    assert b[5] == pytest.approx(5 + port_height("pointed_arch", 60))
    assert b[2] == pytest.approx(4.0)  # 바닥 아래 1mm


# ── L01·L02: 식 ──

def test_l01_unknown_name():
    d = draft("tunnel_junction")
    d["body"][0]["size"] = ["S", "S", "Hh"]
    (i,) = only(run(d), "L01")
    assert i.path == "/body/0/size/2" and i.code == "DSL002" and "did you mean 'H'" in i.hint


def test_l01_let_uses_a_later_let():
    d = draft("tunnel_junction")
    d["let"][0]["expr"] = "H"  # S = H, but H is defined after S
    issues = only(run(d), "L01")
    assert issues[0].path == "/let/0/expr" and issues[0].code == "DSL004"
    assert "defined later" in issues[0].hint


def test_l01_bad_choice_literal():
    d = draft("tunnel_junction")
    d["let"][3]["expr"] = "layout in ('I', 'x')"
    (i,) = only(run(d), "L01")
    assert i.code == "DSL003" and i.path == "/let/3/expr" and "'x'" in i.message


def test_l02_rule_in_geometry():
    d = draft("deck_platform")
    d["envelope"] = ["W", "D", "min(H, rule.max_climb_height_mm)"]
    (i,) = only(run(d), "L02")
    assert i.path == "/envelope/2" and i.code == "DSL004"
    assert "geometry must depend on params only" in i.hint


def test_rule_in_rule_scope_is_fine():
    d = draft("deck_platform")
    assert "rule." in d["constraints"][1]["max"]
    assert run(d).ok


# ── L03: 합치기 겹침 ──

def test_l03_touching_face_to_face():
    d = draft("deck_platform")
    d["body"][1]["size"] = ["t", "D", "H - dt"]  # walls end where the deck begins
    issues = only(run(d), "L03")
    assert [i.path for i in issues] == ["/body/1", "/body/1"]  # both repeat copies, reported once each
    assert "touches step 0 face to face along Z" in issues[0].message and "(i=0)" in issues[0].message
    assert issues[0].variant == "hamster/dwarf/c1/default"
    assert issues[0].value == pytest.approx(0.0) and issues[0].limit == L.OVERLAP_MIN_MM


def test_l03_small_overlap_is_still_touching():
    d = draft("deck_platform")
    d["body"][1]["size"] = ["t", "D", "H - dt + 0.1"]
    assert run(d).ids() == {"L03"}
    d["body"][1]["size"] = ["t", "D", "H - dt + 0.2"]
    assert run(d).ok


def test_l03_disconnected_add():
    d = draft("litter_tray")
    d["body"].append({"op": "box", "size": [10, 10, 10], "at": [500, 0, 0]})
    (i,) = run(d).by_id("L03")  # L06 (envelope) and L07 (slide face) follow from the far box too
    assert i.path == "/body/2" and "does not overlap any earlier add" in i.message


def test_l03_order_matters():
    """벽을 먼저 놓으면 둘째 벽이 앞선 add(첫 벽)와 겹치지 않는다: 발판을 먼저 둔다 (§6.2 의 note)."""
    d = draft("deck_platform")
    d["body"] = [d["body"][1], d["body"][0]]
    issues = only(run(d), "L03")
    assert issues[0].path == "/body/0" and "(i=1)" in issues[0].message


# ── L04: 같은 면에 걸친 자르기 ──

def test_l04_cut_flush_with_the_open_bottom():
    d = draft("tunnel_junction")
    d["body"][1]["at"] = [0, 0, 0]
    d["body"][1]["size"] = ["S - 2 * t", "S - 2 * t", "H - t"]
    (i,) = only(run(d), "L04")
    assert i.path == "/body/1" and "-Z face" in i.message and i.value == pytest.approx(0.0)


def test_l04_cut_flush_with_the_rim():
    d = draft("litter_tray")
    d["body"][1]["size"] = ["width_mm - 2 * t", "depth_mm - 2 * t", "lip_height_mm - t"]
    (i,) = only(run(d), "L04")
    assert "+Z face" in i.message


def test_l04_thin_skin_left_by_a_cut_is_flagged():
    d = draft("litter_tray")
    d["body"][1]["at"] = [0, 0, 0.3]  # floor 0.3 mm
    d["body"][1]["size"] = ["width_mm - 2 * t", "depth_mm - 2 * t", "lip_height_mm + 1"]
    (i,) = only(run(d), "L04")
    assert "-Z face" in i.message and i.value == pytest.approx(0.3)


def test_l04_half_millimetre_beyond_is_fine():
    d = draft("tunnel_junction")
    d["body"][1]["at"] = [0, 0, -0.5]
    d["body"][1]["size"] = ["S - 2 * t", "S - 2 * t", "H - t + 0.5"]
    assert run(d).ok


# ── L05: 남지 않는 add ──

def test_l05_add_swallowed_by_a_later_cut():
    d = draft("litter_tray")
    d["body"].insert(1, {"op": "box", "size": [10, 10, 5], "at": [0, 0, "t + 1"]})
    (i,) = only(run(d), "L05")
    assert i.path == "/body/1" and "inside the later cut step 2" in i.message


def test_l05_add_after_the_cut_is_fine():
    d = draft("litter_tray")
    d["body"].append({"op": "box", "size": [10, 10, 5], "at": [0, 0, "t - 1"]})
    assert run(d).ok


# ── L06: 외형 ──

def test_l06_envelope_too_short():
    d = draft("tunnel_junction")
    d["envelope"] = ["S", "S", "H - 10"]
    (i,) = only(run(d), "L06")
    assert i.path == "/envelope/2" and i.value == pytest.approx(59.0) and i.limit == pytest.approx(69.0)
    assert i.variant == "hamster/dwarf/c1/default"


def test_l06_counts_a_cut_that_slices_the_part():
    d = draft("tunnel_junction")
    d["body"].append({"op": "box", "mode": "cut", "size": ["S + 2", "S + 2", 20], "at": [0, 0, "H - 10"]})
    assert run(d).by_id("L06")  # the top 10 mm is cut away: envelope H is now too tall
    d["envelope"] = ["S", "S", "H - 10"]
    assert run(d).ok


# ── L07: 연결 지점 ──

def test_l07_door_side_must_match_normal():
    d = draft("tunnel_junction")
    d["anchors"]["left"]["side"] = "right"
    (i,) = only(run(d), "L07")
    assert i.path == "/anchors/left/side" and '"left"' in i.hint


def test_l07_host_has_no_doors():
    d = draft("deck_platform")
    d["anchors"]["left"].update(side="left", wall="t", door={"when": "True", "width": 50, "profile": "'box'"})
    msgs = [i.message for i in only(run(d), "L07")]
    assert any("only room_host parts have doors" in m for m in msgs)
    assert any("a host has no doors" in m for m in msgs)


def test_l07_side_only_on_doors():
    d = draft("deck_platform")
    d["anchors"]["left"]["side"] = "left"
    (i,) = only(run(d), "L07")
    assert i.path == "/anchors/left/side"


def test_l07_top_takes_nothing_else():
    d = draft("tunnel_junction")
    d["anchors"]["top"]["mount"] = ["-S / 2", "S / 2", 10]
    (i,) = only(run(d), "L07")
    assert i.path == "/anchors/top" and "mount" in i.message


def test_l07_vertical_anchor_must_be_top_or_bottom():
    d = draft("tunnel_junction")
    d["anchors"]["roof"] = {"origin": [0, 0, "H"], "normal": "+Z", "up": "+Y"}
    (i,) = only(run(d), "L07")
    assert i.path == "/anchors/roof/normal"


def test_l07_attach_order_names_existing_anchors():
    d = draft("tunnel_junction")
    d["attach_order"]["passage"] = ["front", "rear"]
    (i,) = only(run(d), "L07")
    assert i.path == "/attach_order/passage/1"


def test_l07_room_host_needs_passage_order_and_accessory_needs_slide():
    d = draft("tunnel_junction")
    d["attach_order"] = {}
    (i,) = only(run(d), "L07")
    assert i.path == "/attach_order/passage"
    d = draft("litter_tray")
    d["attach_order"] = {}
    paths = {i.path for i in only(run(d), "L07")}
    assert "/attach_order/slide" in paths


def test_l07_fields_name_params_and_match_the_anchor():
    d = draft("tunnel_junction")
    d["anchors"]["front"]["fields"]["port"] = "size_mm"
    (i,) = only(run(d), "L07")
    assert i.path == "/anchors/front/fields/port" and "'door_width_mm'" in i.message
    d = draft("tunnel_junction")
    d["anchors"]["back"]["fields"]["width"] = "size"
    (i,) = only(run(d), "L07")
    assert i.path == "/anchors/back/fields/width" and "not a param" in i.message
    d = draft("tunnel_junction")
    d["anchors"]["back"]["fields"]["profile"] = "size_mm"
    msgs = [i.message for i in only(run(d), "L07")]
    assert any("must be a choice param" in m for m in msgs)
    assert any("profile comes from 'door_shape'" in m for m in msgs)


def test_l07_wall_alias_through_let_is_resolved():
    """초안의 wall 은 let t (= wall_thickness_mm), fields.wall 은 wall_thickness_mm: 같은 것이다."""
    part = parse_part(draft("tunnel_junction"))
    assert L._alias(part, "t") == "wall_thickness_mm"
    assert L._alias(part, "t + 1") is None


def test_l07_openable_needs_an_opens_entry():
    d = draft("tunnel_junction")
    d["anchors"]["back"]["openable"] = True
    (i,) = only(run(d), "L07")
    assert i.path == "/anchors/back/openable" and "no opens entry" in i.message
    d["opens"] = [{"anchor": "back", "set": {"layout": "'X'"}}]
    assert run(d).ok


def test_l07_none_role_has_only_top_and_bottom():
    d = draft("deck_platform")
    d["role"] = "none"
    issues = only(run(d), "L07")
    assert {i.path for i in issues} == {"/anchors/left", "/anchors/right"}


def test_l07_slide_anchor_at_bottom_centre_of_the_back_face():
    d = draft("litter_tray")
    d["anchors"]["back"]["origin"] = [0, "depth_mm / 2 - 5", 0]
    (i,) = only(run(d), "L07")
    assert i.path == "/anchors/back/origin" and "back face" in i.message
    assert i.value == pytest.approx(60.0) and i.limit == pytest.approx(65.0)
    d["anchors"]["back"]["origin"] = [20, "depth_mm / 2", 0]
    (i,) = only(run(d), "L07")
    assert "middle of the face" in i.message


def test_l07_slide_anchor_must_be_a_plain_side_face():
    d = draft("litter_tray")
    d["anchors"]["back"]["up"] = "+X"
    msgs = [i.message for i in only(run(d), "L07")]
    assert any("must have up +Z" in m for m in msgs)
    assert any("slide anchor 'back' must be a side face" in m for m in msgs)


# ── L08: 규칙 이름 ──

def test_rule_names_are_size_rule_fields():
    assert set(RULE_NAMES) <= L.size_rule_fields()
    assert "gap_trap.passable_min_mm" in L.size_rule_fields()


def test_l08_rule_field_missing_from_size_rules(monkeypatch):
    monkeypatch.setattr(L, "size_rule_fields", lambda: frozenset({"gap_trap.safe_max_mm"}))
    issues = only(run(draft("tunnel_junction")), "L08")
    assert issues[0].path == "/params/door_width_mm/rule_default"
    assert "rule.entrance_min_diameter_mm" in issues[0].message


def test_l08_opening_rule_key(monkeypatch):
    known = L.size_rule_fields() - {"entrance_min_diameter_mm"}
    monkeypatch.setattr(L, "size_rule_fields", lambda: known)
    paths = {i.path for i in only(run(draft("deck_platform")), "L08")}
    assert "/features/openings/0/rule_key" in paths


# ── L09: 이름과 설명 ──

def test_l09_param_names_and_units():
    d = draft("deck_platform")
    desc = {"ko": "예비", "en": "Spare"}
    d["params"]["spare"] = {"type": "number", "default": 1, "min": 0, "max": 2, "desc": desc}
    d["params"]["doors"] = {"type": "integer", "default": 1, "min": 0, "max": 2, "desc": desc}
    d["params"]["shape_mm"] = {"type": "choice", "choices": ["a", "b"], "default": "a", "desc": desc}
    d["params"]["tilt_deg"] = {"type": "number", "default": 1, "min": 0, "max": 2, "desc": desc}
    d["params"]["post_count"] = {"type": "integer", "default": 1, "min": 0, "max": 2, "desc": desc}
    paths = [i.path for i in only(run(d), "L09")]
    assert paths == ["/params/spare", "/params/doors", "/params/shape_mm"]


def test_l09_desc_first_sentence_length():
    d = draft("deck_platform")
    d["params"]["height_mm"]["desc"]["en"] = "Height of the top surface of the wooden deck mm. Details."
    (i,) = only(run(d), "L09")
    assert i.path == "/params/height_mm/desc/en" and i.value == 44 and i.limit == 40
    d = draft("deck_platform")
    d["params"]["height_mm"]["desc"]["ko"] = "가" * 31 + " mm. 자세히"
    (i,) = only(run(d), "L09")
    assert i.path == "/params/height_mm/desc/ko"
    d["params"]["height_mm"]["desc"]["ko"] = "가" * 30 + " mm. 자세히"  # " mm" does not count
    assert run(d).ok


# ── L10: 이름 일치 ──

def test_l10_draft_file_name_is_the_family():
    (i,) = only(run(draft("deck_platform"), stem="deck"), "L10")
    assert i.path == "/family" and "deck_platform.json" in i.hint
    assert run(draft("deck_platform"), stem="deck_platform").ok


def test_l10_published_file_name_is_the_key():
    d = draft("deck_platform")
    d = {"dsl": 1, "key": "deck_platform@v1", "version": 1, **{k: v for k, v in d.items() if k != "dsl"}}
    assert run(d, stem="deck_platform@v1").ok
    (i,) = only(run(d, stem="deck_platform@v2"), "L10")
    assert i.path == "/key"


# ── L11: 출력 파트와 필드 ──

def test_l11_print_keys():
    d = draft("deck_platform")
    d["print"][0]["key"] = "main"
    msgs = [i.message for i in only(run(d), "L11")]
    assert any("must be 'body'" in m for m in msgs)
    assert any("unknown print part 'body'" in m for m in msgs)
    d = draft("deck_platform")
    d["print"].append(dict(d["print"][0]))
    (i,) = only(run(d), "L11")
    assert i.path == "/print/1/key" and "used twice" in i.message


def test_l11_size_height_level_fields_are_numbers():
    d = draft("tunnel_junction")
    d["size_fields"] = ["size_mm", "layout"]
    d["height_field"] = "door_shape"
    d["level_field"] = "height"
    paths = {i.path for i in only(run(d), "L11")}
    assert paths == {"/size_fields/1", "/height_field", "/level_field"}


def test_l11_cut_before_the_first_add():
    d = draft("litter_tray")
    d["body"] = [d["body"][1], d["body"][0]]
    (i,) = only(run(d), "L11")
    assert i.path == "/body/0/mode" and i.code == "DSL020"


def test_l11_cut_first_in_one_variant():
    d = draft("litter_tray")
    d["body"][0]["when"] = "lip_height_mm < 20"  # the default lip (30) skips the only add
    issues = run(d).by_id("L11")
    assert issues and issues[0].variant == "hamster/dwarf/c1/default" and issues[0].code == "DSL020"


# ── L12: 사육 환경과 역할 ──

def test_l12_habitat_and_role():
    part = parse_part(draft("deck_platform"))
    r = lint(part.model_copy(update={"habitats": ["aquarium"]}), use_rules=False)
    (i,) = only(r, "L12")
    assert i.path == "/habitats/0" and "not supported by DSL v1" in i.message
    r = lint(part.model_copy(update={"habitats": ["moon"]}), use_rules=False)
    assert "unknown habitat" in only(r, "L12")[0].message
    r = lint(part.model_copy(update={"role": "stacker"}), use_rules=False)
    assert r.by_id("L12")[0].path == "/role"


# ── 변형과 보고 ──

def test_variants_are_settled_by_constraints():
    part = parse_part(draft("tunnel_junction"))
    compiled = compile_part(part)
    ctx = context_for(part.habitats)
    base = L._defaults(part, compiled, ctx)
    v = L._settle(part, compiled, {**base, "door_width_mm": 100.0}, ctx)
    assert v is not None
    assert v["size_mm"] == pytest.approx(100 + 2 * 3 + 8)
    assert v["height_mm"] == pytest.approx(port_height("round_arch", 100) + 6)
    v = L._settle(part, compiled, {**base, "wall_thickness_mm": 2.3}, ctx)
    assert v["wall_thickness_mm"] == pytest.approx(ctx.bindings["ctx.min_wall_mm"])


def test_unsettlable_variant_is_dropped():
    d = draft("litter_tray")
    d["constraints"][1]["min"] = "lip_height_mm + 100"
    part = parse_part(d)
    compiled = compile_part(part)
    ctx = context_for(part.habitats)
    assert L._settle(part, compiled, L._defaults(part, compiled, ctx), ctx) is None


def test_evaluation_errors_skip_the_variant():
    d = draft("deck_platform")
    d["body"][0]["size"] = ["W", "D - 60", "dt"]  # zero at depth_mm 60
    r = run(d)
    assert r.ok, r.text()
    skipped = {s.variant: s.error.code for s in r.skipped}
    assert skipped == {"hamster/dwarf/c1/min:depth_mm": "DSL006"}
    assert "hamster/dwarf/c1/min:depth_mm" not in r.variants


def test_report_shape_and_order():
    d = draft("tunnel_junction")
    d["envelope"] = ["S", "S", "H - 10"]
    d["anchors"]["left"]["side"] = "right"
    r = run(d)
    assert [i.id for i in r.issues] == ["L06", "L07"]
    out = r.to_dict()
    assert out["ok"] is False and out["context"] == "hamster/dwarf"
    assert set(out["issues"][0]) >= {"id", "ok", "variant", "path", "value", "limit", "message", "hint"}
    json.dumps(out)
    assert "L06 /envelope/2" in r.text()


def test_lint_file_reads_and_checks_the_name(tmp_path):
    f = tmp_path / "deck.json"
    f.write_text((DATA / "deck_platform.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert lint_file(f).ids() == {"L10"}
    assert L.main([str(f)]) == 1
    assert L.main([str(DATA / "deck_platform.json")]) == 0


def test_drafts_are_not_mutated():
    d = draft("tunnel_junction")
    before = copy.deepcopy(d)
    run(d)
    assert d == before
