"""Part DSL 식 언어 (app/library/expr.py, 설계 §5.4)."""

from __future__ import annotations

import ast
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import pytest

from app.library import expr as E
from app.library.errors import DslError, DslErrors
from app.library.expr import BOOL, NUM, Scope, choice, compile_expr, compile_part

DATA = Path(__file__).parent / "data" / "library"
FIXTURES = ("tunnel_junction", "deck_platform", "litter_tray")
SHAPES = ("round_arch", "pointed_arch", "box", "house")

NAMES = {
    "width_mm": NUM,
    "depth_mm": NUM,
    "door_width_mm": NUM,
    "n_count": NUM,
    "flag": BOOL,
    "door_shape": choice(SHAPES, "door_shape"),
    "layout": choice(("I", "L", "T", "X"), "layout"),
}
ORDERS = {"door_shape": SHAPES, "layout": ("I", "L", "T", "X")}
GEO = Scope(NAMES, orders=ORDERS)
RULE = Scope(NAMES, rule=True, kind="rule", orders=ORDERS)
ENV = {
    "width_mm": 120.0, "depth_mm": 80.0, "door_width_mm": 55.0, "n_count": 3, "flag": True,
    "door_shape": "pointed_arch", "layout": "T",
    "rule.entrance_min_diameter_mm": 50.0, "rule.tunnel_min_inner_diameter_mm": 50.0,
    "rule.tunnel_max_length_mm": 300.0, "rule.gap_trap.safe_max_mm": 4.0, "rule.gap_trap.passable_min_mm": 50.0,
    "rule.min_wall_thickness_mm": 2.4, "rule.max_ramp_angle_deg": 30.0, "rule.max_climb_height_mm": 120.0,
    "rule.max_step_height_mm": None, "rule.sand_bath_min_depth_mm": None,
    "ctx.count": 2, "ctx.min_wall_mm": 2.4, "ctx.default_wall_mm": 3.0, "ctx.min_entrances": 2,
    "ctx.bed_x_mm": 220.0, "ctx.bed_y_mm": 220.0, "ctx.bed_z_mm": 250.0,
}


def ev(src: str, scope: Scope = RULE, env: dict | None = None) -> object:
    return compile_expr(src, scope, None, "/x").evaluate(ENV if env is None else env)


def code_of(src: str, scope: Scope = RULE, expect=None) -> str:
    with pytest.raises(DslError) as e:
        compile_expr(src, scope, expect, "/x")
    return e.value.code


def load(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


# ── 받아들이는 식 (모든 허용 노드) ──

ACCEPT = [
    ("1", 1.0),
    ("2.5", 2.5),
    ("True", True),
    ("False", False),
    ("width_mm", 120.0),
    ("n_count", 3),
    ("flag", True),
    ("-width_mm", -120.0),
    ("+width_mm", 120.0),
    ("not flag", False),
    ("width_mm + depth_mm", 200.0),
    ("width_mm - depth_mm", 40.0),
    ("width_mm * 2", 240.0),
    ("width_mm / 4", 30.0),
    ("width_mm % 7", 120.0 % 7),
    ("flag and width_mm > 100", True),
    ("flag or False", True),
    ("width_mm < 1", False),
    ("width_mm <= 120", True),
    ("width_mm > 119.9", True),
    ("width_mm >= 121", False),
    ("width_mm == 120", True),
    ("width_mm != 120", False),
    ("flag == True", True),
    ("door_shape == 'pointed_arch'", True),
    ("'box' != door_shape", True),
    ("layout in ('T', 'X')", True),
    ("layout not in ('T', 'X')", False),
    ("layout in ('T',)", True),
    ("10 if flag else 20", 10.0),
    ("door_shape if flag else 'box'", "pointed_arch"),
    ("'box' if flag else 'house'", "box"),
    ("(width_mm + 1) * 2", 242.0),
    ("min(width_mm, depth_mm)", 80.0),
    ("max(1, 2, 3)", 3.0),
    ("abs(-2)", 2.0),
    ("floor(2.7)", 2.0),
    ("ceil(2.1)", 3.0),
    ("round(2.5)", 2.0),  # 파이썬 round (짝수 쪽으로)
    ("round(3.5)", 4.0),
    ("sqrt(16)", 4.0),
    ("clamp(150, 0, 100)", 100.0),
    ("clamp(-5, 0, 100)", 0.0),
    ("sin(30)", math.sin(math.radians(30))),
    ("cos(60)", math.cos(math.radians(60))),
    ("tan(45)", math.tan(math.radians(45))),
    ("atan(1)", 45.0),
    ("atan2(1, 1)", 45.0),
    ("port_height('box', 60)", 60.0),
    ("port_height(door_shape, door_width_mm)", 27.5 + 27.5 / math.cos(math.radians(50))),
    ("rule.entrance_min_diameter_mm + 5", 55.0),
    ("rule.gap_trap.safe_max_mm", 4.0),
    ("ctx.default_wall_mm", 3.0),
    ("ctx.min_entrances", 2),
    ("ctx.bed_z_mm - 10", 240.0),
    ("  width_mm  ", 120.0),
]


@pytest.mark.parametrize("src,want", ACCEPT)
def test_accept(src: str, want: object) -> None:
    got = ev(src)
    if isinstance(want, float):
        assert got == pytest.approx(want)
    else:
        assert got == want


# ── 거부하는 식 ──

REJECT = [
    # 문법·허용하지 않는 노드 (DSL001)
    ("width_mm ** 2", "DSL001"),
    ("width_mm // 2", "DSL001"),
    ("width_mm @ 2", "DSL001"),
    ("n_count & 1", "DSL001"),
    ("n_count | 1", "DSL001"),
    ("n_count ^ 1", "DSL001"),
    ("n_count << 1", "DSL001"),
    ("~n_count", "DSL001"),
    ("width_mm[0]", "DSL001"),
    ("width_mm[0:1]", "DSL001"),
    ("lambda: 1", "DSL001"),
    ("[x for x in (1, 2)]", "DSL001"),
    ("{x for x in (1,)}", "DSL001"),
    ("{x: 1 for x in (1,)}", "DSL001"),
    ("(x for x in (1,))", "DSL001"),
    ("[1, 2]", "DSL001"),
    ("{1, 2}", "DSL001"),
    ("{1: 2}", "DSL001"),
    ("(1, 2)", "DSL001"),
    ("f'{width_mm}'", "DSL001"),
    ("(w := 1)", "DSL001"),
    ("min(*(1, 2))", "DSL001"),
    ("min(a=1, b=2)", "DSL001"),
    ("width_mm.real", "DSL001"),
    ("(1).real", "DSL001"),
    ("math.pi", "DSL001"),
    ("rule", "DSL001"),
    ("None", "DSL001"),
    ("1j", "DSL001"),
    ("b'x'", "DSL001"),
    ("...", "DSL001"),
    ("1 < width_mm < 3", "DSL001"),
    ("flag is True", "DSL001"),
    ("flag is not True", "DSL001"),
    ("layout in 'TX'", "DSL001"),
    ("layout in ['T']", "DSL001"),
    ("await width_mm", "DSL001"),
    ("width_mm if flag", "DSL001"),
    ("width_mm +", "DSL001"),
    ("", "DSL001"),
    ("   ", "DSL001"),
    ("1e999", "DSL001"),
    ("9" * 400, "DSL001"),
    ("__import__('os')", "DSL002"),
    ("open('x')", "DSL002"),
    ("eval('1')", "DSL002"),
    ("(lambda: 1)()", "DSL001"),
    ("min.__class__", "DSL001"),
    # 모르는 이름 (DSL002)
    ("door_width", "DSL002"),
    ("rule.entrance_min", "DSL002"),
    ("rule.gap_trap", "DSL002"),
    ("ctx.size", "DSL002"),
    ("foo(1)", "DSL002"),
    # 형 (DSL003)
    ("not width_mm", "DSL003"),
    ("flag + 1", "DSL003"),
    ("width_mm and flag", "DSL003"),
    ("flag or 1", "DSL003"),
    ("flag < 1", "DSL003"),
    ("width_mm == flag", "DSL003"),
    ("layout == 1", "DSL003"),
    ("layout < 'X'", "DSL003"),
    ("layout == door_shape", "DSL003"),
    ("'a' == 'a'", "DSL003"),
    ("'a' + 'b'", "DSL003"),
    ("-'a'", "DSL003"),
    ("min('a', 1)", "DSL003"),
    ("min(1)", "DSL003"),
    ("clamp(1, 2)", "DSL003"),
    ("port_height(1, 2)", "DSL003"),
    ("port_height('tube', 60)", "DSL003"),
    ("port_height(door_shape)", "DSL003"),
    ("1 if flag else flag", "DSL003"),
    ("1 if width_mm else 2", "DSL003"),
    ("layout if flag else door_shape", "DSL003"),
    ("'Q' if flag else layout", "DSL003"),
    ("layout in ('T', 'Q')", "DSL003"),
    ("layout in (1, 2)", "DSL003"),
    ("'T' in ('T',)", "DSL003"),
    ("width_mm in ('T',)", "DSL003"),
    ("door_shape == 'pointed-arch'", "DSL003"),
    ("min", "DSL003"),
]


@pytest.mark.parametrize("src,code", REJECT)
def test_reject(src: str, code: str) -> None:
    assert code_of(src) == code


def test_error_carries_path_col_message_hint() -> None:
    with pytest.raises(DslError) as e:
        compile_expr("width_mm + door_width", RULE, NUM, "/params/size_mm/rule_default")
    err = e.value
    assert err.to_dict() == {"code": "DSL002", "path": "/params/size_mm/rule_default", "col": 12,
                             "message": "unknown name 'door_width'", "hint": "did you mean 'door_width_mm'?"}


def test_syntax_error_column() -> None:
    with pytest.raises(DslError) as e:
        compile_expr("width_mm + * 2", RULE, NUM, "/x")
    assert e.value.code == "DSL001" and e.value.col is not None and e.value.col >= 10


def test_choice_literal_error_names_choices_and_suggests() -> None:
    with pytest.raises(DslError) as e:
        compile_expr("door_shape == 'pointed-arch'", RULE, BOOL, "/checks/0/fail_if")
    assert e.value.code == "DSL003"
    assert e.value.message == ("`'pointed-arch'` is not a choice of `door_shape`; choices: "
                               "round_arch, pointed_arch, box, house")
    assert e.value.hint == "did you mean 'pointed_arch'?"
    with pytest.raises(DslError) as e2:
        compile_expr("layout in ('I', 'x')", RULE, BOOL, "/x")
    assert "not a choice of `layout`; choices: I, L, T, X" in e2.value.message


def test_rule_suggestion_for_bare_rule_name() -> None:
    with pytest.raises(DslError) as e:
        compile_expr("entrance_min_diameter_mm", RULE, NUM, "/x")
    assert e.value.code == "DSL002" and "rule.entrance_min_diameter_mm" in e.value.hint


# ── 우선순위 ──

PRECEDENCE = [
    ("1 + 2 * 3", 7.0),
    ("(1 + 2) * 3", 9.0),
    ("10 - 4 - 3", 3.0),
    ("24 / 4 / 2", 3.0),
    ("-2 * 3", -6.0),
    ("- 2 + 5", 3.0),
    ("2 * 7 % 4", 2.0),
    ("7 % 4 * 2", 6.0),
    ("not False and False", False),
    ("not (False and False)", True),
    ("True or True and False", True),
    ("(True or True) and False", False),
    ("1 if False else 2 + 3", 5.0),
    ("(1 if False else 2) + 3", 5.0),
    ("1 + 1 if True else 0", 2.0),
    ("width_mm > 100 and depth_mm < 100", True),
    ("not width_mm > 100", False),
    ("2 + 3 == 5", True),
]


@pytest.mark.parametrize("src,want", PRECEDENCE)
def test_precedence(src: str, want: object) -> None:
    assert ev(src) == want


# ── 형 ──

def test_types_of_results() -> None:
    assert compile_expr("width_mm > 1", RULE, None).type == BOOL
    assert compile_expr("width_mm + 1", RULE, None).type == NUM
    t = compile_expr("door_shape", RULE, None).type
    assert t.kind == "choice" and t.origin == "door_shape" and t.values == frozenset(SHAPES)
    lit = compile_expr("'box' if flag else 'house'", RULE, None).type
    assert lit.kind == "choice" and lit.literal and lit.values == {"box", "house"}


def test_slot_types() -> None:
    assert code_of("flag", RULE, NUM) == "DSL003"
    assert code_of("width_mm", RULE, BOOL) == "DSL003"
    assert code_of("'box'", RULE, NUM) == "DSL003"
    allowed = choice(SHAPES)
    compile_expr("door_shape", RULE, allowed)
    compile_expr("'house'", RULE, allowed)
    compile_expr("'box' if flag else door_shape", RULE, allowed)
    assert code_of("'tube'", RULE, allowed) == "DSL003"
    assert code_of("layout", RULE, allowed) == "DSL003"
    assert code_of("width_mm", RULE, allowed) == "DSL003"
    tube = Scope({"s": choice(("tube", "box"), "s")}, rule=True)
    with pytest.raises(DslError) as e:
        compile_expr("s", tube, allowed, "/x")
    assert e.value.code == "DSL003" and "'tube'" in e.value.message


def test_choice_values_are_not_numbers_and_bools_are_not_numbers() -> None:
    assert code_of("layout + 1") == "DSL003"
    assert code_of("flag * 2") == "DSL003"


# ── 범위 ──

def test_geometry_cannot_read_rule_or_ctx() -> None:
    for src in ("rule.entrance_min_diameter_mm", "ctx.count + 1", "rule.nope"):
        with pytest.raises(DslError) as e:
            compile_expr(src, GEO, NUM, "/body/0/size/0")
        assert e.value.code == "DSL004"
        assert "geometry must depend on params only" in e.value.hint
    compile_expr("rule.entrance_min_diameter_mm", RULE, NUM)


def test_hidden_names_give_dsl004_with_reason() -> None:
    sc = Scope({"a_mm": NUM}, hidden={"b_mm": "rule_default may use only params declared before it"})
    with pytest.raises(DslError) as e:
        compile_expr("a_mm + b_mm", sc, NUM, "/x")
    assert e.value.code == "DSL004" and "declared before" in e.value.hint


def test_names_used_are_recorded() -> None:
    c = compile_expr("width_mm + rule.gap_trap.passable_min_mm + ctx.count", RULE, NUM)
    assert c.names == {"width_mm"}
    assert c.rule_fields == {"gap_trap.passable_min_mm"}
    assert c.ctx_fields == {"count"}


# ── 한도 ──

def test_limits() -> None:
    long = "1 + " * 99 + "1"
    assert len(long) <= 400
    assert code_of(long) == "DSL005"  # 노드 수
    deep = "(" * 33 + "1" + ")" * 33
    compile_expr("(" * 30 + "1" + ")" * 30, RULE, NUM)
    nested = "1"
    for _ in range(40):
        nested = f"abs({nested})"
    assert code_of(nested) == "DSL005"  # 깊이
    assert code_of("-" * 40 + "1") == "DSL005"
    assert code_of("width_mm + " + "1" * 400) == "DSL005"  # 길이
    assert compile_expr(deep, RULE, NUM).evaluate(ENV) == 1.0  # 괄호는 노드가 아니다


def test_file_expression_count_limit() -> None:
    d = load("litter_tray")
    d["let"] = [{"name": f"v{k}", "expr": "1 + 1"} for k in range(24)]
    d["body"] = [{"op": "box", "size": ["1", "1", "1"], "at": ["0", "0", "0"], "when": "True"} for _ in range(48)]
    d["checks"] = [{"fail_if": "False", "message": {"ko": "가", "en": "a"}}] * 8
    d["constraints"] = [{"field": "width_mm", "min": "1", "when": "True", "source": "geometry",
                         "reason": {"ko": "가", "en": "a"}}] * 24
    with pytest.raises(DslErrors) as e:
        compile_part(d)
    assert any(x.code == "DSL005" and "limit is 400" in x.message for x in e.value.errors)


# ── 계산 오류 ──

EVAL_ERRORS = [
    ("width_mm / (depth_mm - 80)", "division by zero"),
    ("width_mm % 0", "division by zero"),
    ("sqrt(depth_mm - 100)", "sqrt of a negative"),
    ("1e300 * 1e300", "not a finite"),
    ("tan(90) * 1e300 * 1e300", "not a finite"),
    ("clamp(1, 5, 2)", "clamp"),
    ("rule.max_step_height_mm + 1", "not defined for this size"),
]


@pytest.mark.parametrize("src,msg", EVAL_ERRORS)
def test_eval_errors(src: str, msg: str) -> None:
    c = compile_expr(src, RULE, NUM, "/constraints/0/min")
    with pytest.raises(DslError) as e:
        c.evaluate(ENV)
    assert e.value.code == "DSL006" and e.value.path == "/constraints/0/min"
    assert msg in e.value.message


def test_eval_error_reports_bindings() -> None:
    c = compile_expr("width_mm / (depth_mm - 80)", RULE, NUM, "/x")
    with pytest.raises(DslError) as e:
        c.evaluate(ENV)
    assert "depth_mm=80.0" in e.value.hint and "width_mm=120.0" in e.value.hint


def test_missing_binding_is_dsl006() -> None:
    c = compile_expr("width_mm + 1", RULE, NUM, "/x")
    with pytest.raises(DslError) as e:
        c.evaluate({})
    assert e.value.code == "DSL006"


# ── port_height 와 코드 상수 ──

def test_port_height_matches_tunnel() -> None:
    from app.templates import tunnel

    assert E.TIP_ANGLE_DEG == tunnel.TIP_ANGLE_DEG
    for shape in SHAPES:
        for w in (12, 25, 50.5, 60, 75, 100, 130):
            assert E.port_height(shape, w) == pytest.approx(tunnel.height_for(shape, w, 0), abs=1e-9)
            got = compile_expr(f"port_height('{shape}', {w})", RULE, NUM).evaluate({})
            assert got == pytest.approx(tunnel.height_for(shape, w, 0), abs=1e-9)
    assert set(E.DOOR_PROFILES) == set(tunnel.TunnelParams.model_fields["shape"].annotation.__args__) - {"tube"}


def test_default_bed_matches_compose() -> None:
    from app.modules import compose

    assert E.DEFAULT_BED_MM == compose.DEFAULT_BED_MM


def test_rule_names_are_size_rules_fields(rules) -> None:
    from app.rules.loader import SizeRules

    for name in E.RULE_NAMES:
        head, _, rest = name.partition(".")
        assert head in SizeRules.model_fields, name
        if rest:
            sub = SizeRules.model_fields[head].annotation
            assert rest in sub.model_fields, name
    nullable = {n for n in E.RULE_NAMES if "." not in n and SizeRules.model_fields[n].default is None}
    assert nullable == E.NULLABLE_RULE_NAMES


def test_bindings_from_real_rules(rules) -> None:
    from app.domain import Cage
    from app.services.engine import EngineContext

    ctx = EngineContext(cage=Cage(1000, 600, 400), species="hamster", size="dwarf", count=2, rules=rules).rule_ctx
    b = E.rule_ctx_bindings(ctx)
    assert set(b) == {f"rule.{n}" for n in E.RULE_NAMES} | {f"ctx.{n}" for n in E.CTX_NAMES}
    assert b["rule.gap_trap.passable_min_mm"] == ctx.size.gap_trap.passable_min_mm
    assert b["ctx.min_entrances"] == ctx.hideout_min_entrances == ctx.size.hideout_min_entrances.group
    assert b["ctx.default_wall_mm"] == ctx.default_wall_mm
    bed = ctx.build_volume_mm
    assert (b["ctx.bed_x_mm"], b["ctx.bed_y_mm"], b["ctx.bed_z_mm"]) == tuple(float(v) for v in bed)


# ── 파일 단위 컴파일 ──

@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_files_compile(name: str) -> None:
    cp = compile_part(load(name))
    assert cp.exprs
    assert all(p.startswith("/") for p in cp.exprs)


def test_rule_fields_used() -> None:
    assert compile_part(load("tunnel_junction")).rule_fields == {"entrance_min_diameter_mm"}
    assert compile_part(load("deck_platform")).rule_fields == {
        "entrance_min_diameter_mm", "gap_trap.passable_min_mm", "max_climb_height_mm"}
    assert compile_part(load("litter_tray")).rule_fields == {"gap_trap.passable_min_mm", "max_step_height_mm"}


def _rule_defaults(cp: E.CompiledPart, part: dict, bindings: dict) -> dict:
    """T5 default_params 의 rule_default 계산 차례 (앞의 파라미터부터)."""
    out: dict = {}
    for name, spec in part["params"].items():
        e = cp.get(f"/params/{name}/rule_default")
        out[name] = e.evaluate({**out, **bindings}) if e is not None else spec["default"]
    return out


@pytest.mark.parametrize("size,want", [
    ("dwarf", {"wall_thickness_mm": 3.0, "door_width_mm": 55.0, "size_mm": 81.0, "height_mm": 69.0}),
    ("syrian", {"wall_thickness_mm": 3.0, "door_width_mm": 75.0, "size_mm": 101.0, "height_mm": 89.0}),
])
def test_junction_rule_defaults_match_design_table(rules, size: str, want: dict) -> None:
    from app.domain import Cage
    from app.services.engine import EngineContext

    ctx = EngineContext(cage=Cage(1000, 600, 400), species="hamster", size=size, count=1, rules=rules).rule_ctx
    part = load("tunnel_junction")
    cp = compile_part(part)
    got = _rule_defaults(cp, part, E.rule_ctx_bindings(ctx))
    for k, v in want.items():
        assert got[k] == pytest.approx(v), k
    env = cp.geometry_env(got)
    assert env["S"] == got["size_mm"] and env["has_left"] is True and env["has_back"] is False
    # 제약은 기본값에서 지켜진다
    renv = cp.rule_env(got, E.rule_ctx_bindings(ctx))
    for idx, c in enumerate(part["constraints"]):
        bound = cp[f"/constraints/{idx}/min"].evaluate(renv)
        assert got[c["field"]] >= bound


def test_deck_and_tray_rule_defaults(rules) -> None:
    from app.domain import Cage
    from app.services.engine import EngineContext

    for size, tray_w in (("dwarf", 130.0), ("syrian", 146.0)):
        ctx = EngineContext(cage=Cage(1000, 600, 400), species="hamster", size=size, count=1, rules=rules).rule_ctx
        b = E.rule_ctx_bindings(ctx)
        deck = load("deck_platform")
        d = _rule_defaults(compile_part(deck), deck, b)
        assert (d["width_mm"], d["depth_mm"], d["height_mm"], d["deck_thickness_mm"]) == (160.0, 120, 100.0, 4.0)
        tray = load("litter_tray")
        t = _rule_defaults(compile_part(tray), tray, b)
        assert t["width_mm"] == tray_w and t["lip_height_mm"] == 30.0


def test_repeat_variables_only_in_repeating_steps() -> None:
    d = load("deck_platform")
    cp = compile_part(d)
    assert cp["/body/1/at/0"].names == {"i", "W", "t"}
    env = cp.geometry_env({"wall_thickness_mm": 3.0, "width_mm": 160.0, "depth_mm": 120.0, "height_mm": 100.0,
                           "deck_thickness_mm": 4.0})
    assert [cp["/body/1/at/0"].evaluate({**env, "i": i}) for i in (0, 1)] == [-78.5, 78.5]
    d["body"][0]["at"][0] = "i * 2"
    with pytest.raises(DslErrors) as e:
        compile_part(d)
    assert [(x.code, x.path) for x in e.value.errors] == [("DSL004", "/body/0/at/0")]
    d = load("deck_platform")
    d["body"][1]["repeat"] = {"i": "i + 1"}
    with pytest.raises(DslErrors) as e:
        compile_part(d)
    assert e.value.errors[0].path == "/body/1/repeat/i" and e.value.errors[0].code == "DSL004"


def test_file_scope_errors_are_collected_with_pointers() -> None:
    d = load("tunnel_junction")
    d["body"][0]["size"][0] = "rule.entrance_min_diameter_mm"        # geometry 에서 rule
    d["params"]["door_width_mm"]["rule_default"] = "size_mm - 20"     # 뒤에 선언한 파라미터
    d["let"][0]["expr"] = "H + 1"                                     # 뒤의 let
    d["anchors"]["front"]["door"]["profile"] = "'tube'"               # 출입구 단면이 될 수 없는 모양
    d["anchors"]["back"]["door"]["when"] = "1"                        # bool 자리에 수
    d["constraints"][0]["min"] = "door_width"                         # 모르는 이름
    d["checks"] = [{"fail_if": "layout == 'Y'", "message": {"ko": "가", "en": "a"}}]
    d["opens"] = [{"anchor": "back", "set": {"layuot": "'X'"}}, {"anchor": "left", "set": {"layout": "'Y'"}},
                  {"anchor": "right", "set": {"layout": 1}}]
    with pytest.raises(DslErrors) as e:
        compile_part(d)
    got = {(x.path, x.code) for x in e.value.errors}
    assert got == {
        ("/body/0/size/0", "DSL004"),
        ("/params/door_width_mm/rule_default", "DSL004"),
        ("/let/0/expr", "DSL004"),
        ("/anchors/front/door/profile", "DSL003"),
        ("/anchors/back/door/when", "DSL003"),
        ("/constraints/0/min", "DSL002"),
        ("/checks/0/fail_if", "DSL003"),
        ("/opens/0/set/layuot", "DSL002"),
        ("/opens/1/set/layout", "DSL003"),
        ("/opens/2/set/layout", "DSL003"),
    }
    by_path = {x.path: x for x in e.value.errors}
    assert by_path["/opens/0/set/layuot"].hint == "did you mean 'layout'?"
    assert "declared before" in by_path["/params/door_width_mm/rule_default"].hint


def test_rule_default_cannot_use_lets_or_itself() -> None:
    d = load("tunnel_junction")
    d["params"]["size_mm"]["rule_default"] = "S + 1"
    d["params"]["height_mm"]["rule_default"] = "height_mm"
    with pytest.raises(DslErrors) as e:
        compile_part(d)
    assert {(x.path, x.code) for x in e.value.errors} == {
        ("/params/size_mm/rule_default", "DSL004"), ("/params/height_mm/rule_default", "DSL004")}


def test_name_definitions() -> None:
    d = load("litter_tray")
    d["let"] = [{"name": "t", "expr": "1"}, {"name": "t", "expr": "2"}, {"name": "width_mm", "expr": "1"},
                {"name": "min", "expr": "1"}, {"name": "i", "expr": "1"}]
    d["params"]["max"] = {"type": "number", "default": 1, "min": 0, "max": 2, "desc": {"ko": "가", "en": "a"}}
    with pytest.raises(DslErrors) as e:
        compile_part(d)
    assert {(x.path, x.code) for x in e.value.errors} == {
        ("/params/max", "DSL007"), ("/let/1/name", "DSL007"), ("/let/2/name", "DSL007"),
        ("/let/3/name", "DSL007"), ("/let/4/name", "DSL007")}


def test_let_cannot_be_a_bare_string_and_bool_json_is_rejected() -> None:
    d = load("litter_tray")
    d["let"] = [{"name": "s", "expr": "'box'"}]
    with pytest.raises(DslErrors) as e:
        compile_part(d)
    assert e.value.errors[0].code == "DSL003"
    d = load("litter_tray")
    d["envelope"][0] = True
    with pytest.raises(DslErrors) as e:
        compile_part(d)
    assert e.value.errors[0].path == "/envelope/0"


def test_json_numbers_are_constants() -> None:
    cp = compile_part(load("deck_platform"))
    c = cp["/body/0/at/0"]
    assert c.constant and c.evaluate({}) == 0.0
    assert cp["/body/1/repeat/i"].evaluate({}) == 2.0


# ── 퍼즈 ──

_TOKENS = ["width_mm", "depth_mm", "flag", "layout", "door_shape", "n_count", "rule", "ctx", ".", "gap_trap",
           "entrance_min_diameter_mm", "count", "safe_max_mm", "(", ")", ",", "+", "-", "*", "/", "%", "**", "//",
           "<", "<=", ">", ">=", "==", "!=", "and", "or", "not", "in", "is", "if", "else", "for", "lambda", ":",
           "[", "]", "{", "}", "'T'", "'box'", "'", '"', "0", "1", "2.5", "1e308", "1e-9", "True", "False", "None",
           "min", "max", "abs", "floor", "ceil", "round", "sqrt", "clamp", "sin", "cos", "tan", "atan", "atan2",
           "port_height", "__import__", "os", "=", ":=", "@", "~", "&", "|", "^", "<<", "\\", "\n", "#", "f'",
           "\x00", "가", "x", "_", " ", "  ", "9" * 30, "...", "*", "**", "yield", "await", "async"]


_ATOMS = ["width_mm", "depth_mm", "n_count", "flag", "layout", "door_shape", "'T'", "'box'", "0", "1", "-3",
          "1e308", "rule.entrance_min_diameter_mm", "rule.max_step_height_mm", "ctx.count", "True"]
_BIN = ["+", "-", "*", "/", "%", "<", "==", "!=", "and", "or", "in"]
_FN = ["min", "max", "abs", "floor", "ceil", "round", "sqrt", "clamp", "sin", "tan", "atan", "atan2", "port_height"]


def _grammar(rnd: random.Random, depth: int = 0) -> str:
    """문법에 가까운 식 (계산 경로까지 가도록)."""
    r = rnd.random()
    if depth > 3 or r < 0.3:
        return rnd.choice(_ATOMS)
    if r < 0.55:
        op = rnd.choice(_BIN)
        right = "('T', 'X')" if op == "in" else _grammar(rnd, depth + 1)
        return f"({_grammar(rnd, depth + 1)} {op} {right})"
    if r < 0.65:
        return f"(not {_grammar(rnd, depth + 1)})"
    if r < 0.75:
        return f"({_grammar(rnd, depth + 1)} if {_grammar(rnd, depth + 1)} else {_grammar(rnd, depth + 1)})"
    fn = rnd.choice(_FN)
    args = ", ".join(_grammar(rnd, depth + 1) for _ in range(rnd.randint(1, 3)))
    return f"{fn}({args})"


@pytest.mark.filterwarnings("ignore::SyntaxWarning")
def test_fuzz_only_dsl_errors() -> None:
    rnd = random.Random(1234)
    scopes = (RULE, GEO, Scope({}, rule=True))
    compiled = 0
    for k in range(5000):
        n = rnd.randint(1, 14)
        if k % 2:
            src = _grammar(rnd)
        elif k % 4:
            src = " ".join(rnd.choice(_TOKENS) for _ in range(n))
        else:
            src = "".join(rnd.choice(_TOKENS) for _ in range(n))
        scope = scopes[k % 3]
        try:
            c = compile_expr(src, scope, None, "/fuzz")
        except DslError:
            continue
        compiled += 1
        try:
            c.evaluate(ENV)
        except DslError:
            pass
    assert compiled > 500  # 퍼즈가 계산까지 가 본다


# ── import 허용 목록 ──

ALLOWED_IMPORTS = {"__future__", "ast", "math", "difflib", "dataclasses", "re", "keyword", "collections.abc",
                   "app.library.errors"}


def test_expr_imports_only_whitelisted_modules() -> None:
    for mod in ("expr", "errors"):
        tree = ast.parse((Path(E.__file__).parent / f"{mod}.py").read_text(encoding="utf-8"))
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                found.add(node.module or "")
        assert found <= ALLOWED_IMPORTS, (mod, found - ALLOWED_IMPORTS)


def test_expr_import_pulls_nothing_heavy() -> None:
    code = ("import sys, app.library.expr; "
            "bad = [m for m in ('pydantic', 'build123d', 'OCP', 'trimesh', 'numpy', 'sklearn', 'anthropic', "
            "'yaml', 'sqlalchemy') if m in sys.modules]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=Path(__file__).resolve().parents[1], check=True)
    assert out.stdout.strip() == "[]"


def test_compile_part_accepts_a_parsed_part_file() -> None:
    from app.library.schema import parse_part

    for name in FIXTURES:
        d = load(name)
        assert set(compile_part(parse_part(d)).exprs) == set(compile_part(d).exprs)
