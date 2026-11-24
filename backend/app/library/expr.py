"""Part DSL 식 언어 (설계 §5.4).

식은 파이썬 식의 일부다. ``ast.parse(src, mode="eval")`` 로 읽고(읽기만 하고 실행하지 않는다), 허용 목록에 있는 노드만
닫힌 함수(closure) 트리로 바꾼다. eval·exec·compile 은 쓰지 않고, rule./ctx. 말고는 속성에 접근하지 않는다.

형(type)은 컴파일할 때 확인한다: 수(num), 참거짓(bool), 선택값(choice: 파라미터의 선택지 집합).
문자열 상수는 선택 파라미터와 비교할 때, in 의 튜플 안, port_height 의 모양 인자, 그리고 선택값을 받는 자리에만 쓴다.

범위(scope):
- geometry (let, body, anchors, opens, envelope, face_needs, features): 파라미터, 앞서 정의한 let, body 의 반복 변수 i·j
- rule (constraints, checks): geometry 범위 + rule.<이름>, ctx.<이름>
- rule_default: 앞서 선언한 파라미터 + rule.·ctx. (let 은 쓸 수 없다)
geometry 는 rule.·ctx. 를 읽지 못하므로 형상은 파라미터만의 순수 함수다 (같은 파라미터 → 같은 바이트).

이 모듈은 표준 라이브러리(ast, math, difflib, dataclasses, re, keyword, collections.abc)와 app.library.errors 만
import 한다 (테스트가 확인).
"""

from __future__ import annotations

import ast
import difflib
import keyword
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from app.library.errors import DslError, DslErrors, pointer

# ── 상수 ──

MAX_SOURCE_CHARS = 400
MAX_NODES = 200
MAX_DEPTH = 32
MAX_EXPRESSIONS = 400

# app/templates/tunnel.py TIP_ANGLE_DEG 와 같아야 한다 (tunnel 을 import 하면 형상 커널을 불러와 값만 둔다. 테스트가 확인)
TIP_ANGLE_DEG = 50.0
# app/modules/compose.py DEFAULT_BED_MM 과 같아야 한다 (테스트가 확인)
DEFAULT_BED_MM = (220.0, 220.0, 250.0)
# 출입구(door)·통로(passage) 단면으로 쓸 수 있는 모양. tube 는 바닥이 막힌 관이라 출입구가 아니다
DOOR_PROFILES: tuple[str, ...] = ("round_arch", "pointed_arch", "box", "house")

# rule.<이름>: SizeRules 필드 (점 표기). 값이 null 일 수 있는 필드를 쓰면 그 크기 구분은 검증 대상에서 빠진다
RULE_NAMES: tuple[str, ...] = (
    "entrance_min_diameter_mm",
    "tunnel_min_inner_diameter_mm",
    "tunnel_max_length_mm",
    "gap_trap.safe_max_mm",
    "gap_trap.passable_min_mm",
    "min_wall_thickness_mm",
    "max_ramp_angle_deg",
    "max_climb_height_mm",
    "max_step_height_mm",
    "sand_bath_min_depth_mm",
)
NULLABLE_RULE_NAMES: frozenset[str] = frozenset({
    "tunnel_max_length_mm", "max_ramp_angle_deg", "max_climb_height_mm", "max_step_height_mm",
    "sand_bath_min_depth_mm",
})
# ctx.<이름>: RuleContext 에서 오는 값
CTX_NAMES: tuple[str, ...] = (
    "count", "min_wall_mm", "default_wall_mm", "min_entrances", "bed_x_mm", "bed_y_mm", "bed_z_mm",
)

# 함수 이름 → (최소, 최대) 인자 수
FUNCS: dict[str, tuple[int, int]] = {
    "min": (2, 8), "max": (2, 8), "abs": (1, 1), "floor": (1, 1), "ceil": (1, 1), "round": (1, 1),
    "sqrt": (1, 1), "clamp": (3, 3), "sin": (1, 1), "cos": (1, 1), "tan": (1, 1), "atan": (1, 1),
    "atan2": (2, 2), "port_height": (2, 2),
}
# 파라미터·let 이름으로 쓸 수 없는 이름
RESERVED: frozenset[str] = frozenset(FUNCS) | {"rule", "ctx", "i", "j", "True", "False", "None"} | frozenset(
    keyword.kwlist) | frozenset(keyword.softkwlist)

_STRING_RULE = ("a string can only be compared with a choice param (==, !=, in), "
                "be the shape argument of port_height, or be the value of a choice slot")


# ── 형 ──

@dataclass(frozen=True)
class Ty:
    """식의 형. kind: num | bool | choice | any (앞선 오류로 형을 모를 때: 오류를 되풀이하지 않게 무엇이든 받는다)."""

    kind: str
    values: frozenset[str] = frozenset()
    origin: str | None = None  # 선택값의 출처 파라미터 이름
    literal: bool = False  # 문자열 상수(들)뿐인 선택값

    def describe(self) -> str:
        if self.kind == "choice":
            if self.literal:
                return "string " + ", ".join(repr(v) for v in sorted(self.values))
            if self.origin:
                return f"choice {self.origin}"
            return "choice"
        return {"num": "number", "bool": "bool", "any": "any"}[self.kind]


NUM = Ty("num")
BOOL = Ty("bool")
ANY = Ty("any")


def choice(values: object, origin: str | None = None) -> Ty:
    return Ty("choice", frozenset(values), origin)  # type: ignore[arg-type]


def _literal(value: str) -> Ty:
    return Ty("choice", frozenset({value}), None, True)


def _choices_text(ty: Ty, order: tuple[str, ...] | None = None) -> str:
    vals = [v for v in (order or ()) if v in ty.values] + sorted(v for v in ty.values if v not in (order or ()))
    return ", ".join(vals)


# ── 범위 ──

@dataclass(frozen=True)
class Scope:
    """식에서 보이는 이름과 형.

    names: 보이는 이름 → 형. rule: rule.·ctx. 를 쓸 수 있는지. hidden: 파일에는 있지만 여기서는 쓸 수 없는 이름 → 까닭.
    kind: 메시지용 범위 이름 (geometry, rule, rule_default, repeat).
    """

    names: Mapping[str, Ty]
    rule: bool = False
    hidden: Mapping[str, str] = field(default_factory=dict)
    kind: str = "geometry"
    # 선택 파라미터의 선택지 순서 (메시지에 선언 순서로 보이게)
    orders: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


# ── 계산 ──

class _EvalError(Exception):
    pass


def _finite(v: object) -> object:
    if isinstance(v, float) and not math.isfinite(v):
        raise _EvalError("the result is not a finite number")
    return v


def port_height(shape: str, width: float) -> float:
    """출입구 단면의 열린 높이 (바닥에서 꼭대기까지). tunnel.height_for(shape, width, 0) 과 같다.

    round_arch·box: 폭과 같다. pointed_arch·house: width/2 + (width/2)/cos(TIP_ANGLE_DEG)."""
    if shape in ("round_arch", "box"):
        return float(width)
    if shape in ("pointed_arch", "house"):
        r = width / 2
        return r + r / math.cos(math.radians(TIP_ANGLE_DEG))
    raise _EvalError(f"port_height: unknown shape {shape!r}; shapes: {', '.join(DOOR_PROFILES)}")


def _sqrt(x: float) -> float:
    if x < 0:
        raise _EvalError(f"sqrt of a negative number ({x:g})")
    return math.sqrt(x)


def _clamp(x: float, lo: float, hi: float) -> float:
    if lo > hi:
        raise _EvalError(f"clamp: lo {lo:g} is greater than hi {hi:g}")
    return min(max(x, lo), hi)


def _deg(fn: Callable[[float], float]) -> Callable[[float], float]:
    return lambda x: fn(math.radians(x))


_FUNC_IMPL: dict[str, Callable[..., object]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "floor": lambda x: float(math.floor(x)),
    "ceil": lambda x: float(math.ceil(x)),
    "round": lambda x: float(round(x)),
    "sqrt": _sqrt,
    "clamp": _clamp,
    "sin": _deg(math.sin),
    "cos": _deg(math.cos),
    "tan": _deg(math.tan),
    "atan": lambda x: math.degrees(math.atan(x)),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    "port_height": port_height,
}

Env = Mapping[str, object]


def _lookup(name: str) -> Callable[[Env], object]:
    def f(env: Env) -> object:
        try:
            v = env[name]
        except KeyError:
            raise _EvalError(f"no value for {name!r}") from None
        if v is None:
            if name.startswith("rule."):
                raise _EvalError(f"{name} is not defined for this size (null in rules/species.yaml)")
            raise _EvalError(f"{name} has no value")
        return v

    return f


# ── 컴파일된 식 ──

@dataclass(frozen=True)
class CompiledExpr:
    """컴파일된 식 하나. evaluate(env) 로 계산한다.

    env: 이름 → 값. 파라미터·let·i·j 는 그 이름, 규칙 값은 "rule.<이름>", 맥락 값은 "ctx.<이름>" 열쇠로 넣는다
    (rule_bindings, ctx_bindings 가 만든다)."""

    src: str
    path: str
    type: Ty
    names: frozenset[str]  # 쓴 파라미터·let·반복 변수
    rule_fields: frozenset[str]  # 쓴 rule. 이름 (점 표기, "rule." 없이)
    ctx_fields: frozenset[str]
    fn: Callable[[Env], object] = field(repr=False, compare=False)
    constant: bool = False  # JSON 숫자 그대로 쓴 자리

    def evaluate(self, env: Env) -> object:
        try:
            return _finite(self.fn(env))
        except _EvalError as e:
            msg = str(e)
        except ZeroDivisionError:
            msg = "division by zero"
        except (OverflowError, ValueError, ArithmeticError) as e:
            msg = f"arithmetic error ({e})"
        except RecursionError:
            msg = "expression too deep to evaluate"
        raise DslError("DSL006", self.path, f"{msg} evaluating '{self.src}'", hint=self._bindings(env))

    __call__ = evaluate

    def _bindings(self, env: Env) -> str:
        keys = sorted(self.names) + [f"rule.{n}" for n in sorted(self.rule_fields)] + [
            f"ctx.{n}" for n in sorted(self.ctx_fields)]
        if not keys:
            return ""
        return "with " + ", ".join(f"{k}={env.get(k, '<missing>')!r}" for k in keys)


def constant(value: float, path: str = "") -> CompiledExpr:
    """JSON 숫자로 적은 자리."""
    v = float(value)
    if not math.isfinite(v):
        raise DslError("DSL010", path, f"{value!r} is not a finite number")
    return CompiledExpr(repr(value), path, NUM, frozenset(), frozenset(), frozenset(), lambda env: v, constant=True)


# ── 컴파일러 ──

_NODE_NAMES: dict[type, str] = {
    ast.Subscript: "subscripts (x[i])",
    ast.Lambda: "lambda",
    ast.ListComp: "comprehensions",
    ast.SetComp: "comprehensions",
    ast.DictComp: "comprehensions",
    ast.GeneratorExp: "comprehensions",
    ast.JoinedStr: "f-strings",
    ast.FormattedValue: "f-strings",
    ast.NamedExpr: "assignment expressions (:=)",
    ast.Starred: "starred arguments (*x)",
    ast.List: "lists",
    ast.Dict: "dicts",
    ast.Set: "sets",
    ast.Await: "await",
    ast.Yield: "yield",
    ast.YieldFrom: "yield",
    ast.Slice: "slices",
}
_BINOPS: dict[type, Callable[[object, object], object]] = {
    ast.Add: lambda a, b: a + b,  # type: ignore[operator]
    ast.Sub: lambda a, b: a - b,  # type: ignore[operator]
    ast.Mult: lambda a, b: a * b,  # type: ignore[operator]
    ast.Div: lambda a, b: a / b,  # type: ignore[operator]
    ast.Mod: lambda a, b: a % b,  # type: ignore[operator]
}
_BINOP_HINTS: dict[type, str] = {
    ast.Pow: "'**' is not allowed; multiply, or use sqrt",
    ast.FloorDiv: "'//' is not allowed; use floor(a / b)",
}
_CMP_NUM: dict[type, Callable[[object, object], bool]] = {
    ast.Lt: lambda a, b: a < b,  # type: ignore[operator]
    ast.LtE: lambda a, b: a <= b,  # type: ignore[operator]
    ast.Gt: lambda a, b: a > b,  # type: ignore[operator]
    ast.GtE: lambda a, b: a >= b,  # type: ignore[operator]
}


class _Compiler:
    def __init__(self, src: str, scope: Scope, path: str, lead: int = 0):
        self.src = src
        self.lead = lead
        self.scope = scope
        self.path = path
        self.names: set[str] = set()
        self.rule_fields: set[str] = set()
        self.ctx_fields: set[str] = set()

    # 오류
    def _col(self, node: ast.AST | None) -> int | None:
        off = getattr(node, "col_offset", None)
        if off is None:
            return None
        # col_offset 은 UTF-8 바이트 위치다: 글자 위치로 바꾼다
        return len(self.src.encode("utf-8")[:off].decode("utf-8", errors="ignore")) + 1 + self.lead

    def err(self, code: str, node: ast.AST | None, message: str, hint: str = "") -> DslError:
        return DslError(code, self.path, message, hint, self._col(node))

    def need(self, got: Ty, want: Ty, node: ast.AST, what: str) -> None:
        """got 이 want(num|bool) 인지. 아니면 DSL003."""
        if got.kind == "any" or got.kind == want.kind:
            return
        if got.literal:
            raise self.err("DSL003", node, f"{what} needs a {want.describe()}, got {got.describe()}", _STRING_RULE)
        raise self.err("DSL003", node, f"{what} needs a {want.describe()}, got {got.describe()}")

    # 이름
    def _suggest(self, name: str, candidates: list[str]) -> str:
        close = difflib.get_close_matches(name, candidates, n=1, cutoff=0.6)
        return f"did you mean {close[0]!r}?" if close else ""

    def name(self, node: ast.Name) -> tuple[Ty, Callable[[Env], object]]:
        n = node.id
        if n in self.scope.names:
            self.names.add(n)
            return self.scope.names[n], _lookup(n)
        if n in FUNCS:
            raise self.err("DSL003", node, f"'{n}' is a function", f"call it, e.g. {n}(...)")
        if n in ("rule", "ctx"):
            raise self.err("DSL001", node, f"'{n}' needs a field name", f"write {n}.<name>")
        if n in self.scope.hidden:
            raise self.err("DSL004", node, f"'{n}' cannot be used here", self.scope.hidden[n])
        cands = list(self.scope.names) + list(self.scope.hidden)
        if self.scope.rule:
            cands += [f"rule.{r}" for r in RULE_NAMES] + [f"ctx.{c}" for c in CTX_NAMES]
        hint = self._suggest(n, cands)
        if not hint and not self.scope.rule and (n in RULE_NAMES or n in CTX_NAMES):
            hint = "geometry must depend on params only"
        raise self.err("DSL002", node, f"unknown name '{n}'", hint)

    def attribute(self, node: ast.Attribute) -> tuple[Ty, Callable[[Env], object]]:
        parts: list[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name) or cur.id not in ("rule", "ctx"):
            raise self.err("DSL001", node, "attribute access is allowed only as rule.<name> or ctx.<name>")
        root = cur.id
        dotted = ".".join(reversed(parts))
        if not self.scope.rule:
            raise self.err("DSL004", node, f"{root}.{dotted} cannot be used in {self.scope.kind} expressions",
                           "geometry must depend on params only; move the rule into constraints, checks or "
                           "rule_default")
        known = RULE_NAMES if root == "rule" else CTX_NAMES
        if dotted not in known:
            hint = self._suggest(dotted, list(known))
            if not hint:
                hint = f"{root}. names: " + ", ".join(known)
            raise self.err("DSL002", node, f"unknown name '{root}.{dotted}'", hint)
        (self.rule_fields if root == "rule" else self.ctx_fields).add(dotted)
        return NUM, _lookup(f"{root}.{dotted}")

    # 노드
    def compile(self, node: ast.AST) -> tuple[Ty, Callable[[Env], object]]:
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool):
                return BOOL, (lambda env, v=v: v)
            if isinstance(v, (int, float)):
                try:
                    f = float(v)
                except OverflowError:
                    raise self.err("DSL001", node, "number literal out of range") from None
                if not math.isfinite(f):
                    raise self.err("DSL001", node, "number literal out of range")
                return NUM, (lambda env, f=f: f)
            if isinstance(v, str):
                return _literal(v), (lambda env, v=v: v)
            raise self.err("DSL001", node, f"constant {v!r} is not allowed", "use numbers, True, False or 'strings'")
        if isinstance(node, ast.Name):
            return self.name(node)
        if isinstance(node, ast.Attribute):
            return self.attribute(node)
        if isinstance(node, ast.UnaryOp):
            t, f = self.compile(node.operand)
            if isinstance(node.op, ast.Not):
                self.need(t, BOOL, node.operand, "'not'")
                return BOOL, (lambda env: not f(env))
            if isinstance(node.op, (ast.USub, ast.UAdd)):
                self.need(t, NUM, node.operand, "unary '-'" if isinstance(node.op, ast.USub) else "unary '+'")
                if isinstance(node.op, ast.USub):
                    return NUM, (lambda env: -f(env))  # type: ignore[operator]
                return NUM, f
            raise self.err("DSL001", node, "'~' is not allowed")
        if isinstance(node, ast.BinOp):
            op = _BINOPS.get(type(node.op))
            if op is None:
                raise self.err("DSL001", node, f"operator {type(node.op).__name__} is not allowed",
                               _BINOP_HINTS.get(type(node.op), "allowed operators: + - * / %"))
            ta, fa = self.compile(node.left)
            tb, fb = self.compile(node.right)
            self.need(ta, NUM, node.left, "arithmetic")
            self.need(tb, NUM, node.right, "arithmetic")
            return NUM, (lambda env: _finite(op(fa(env), fb(env))))
        if isinstance(node, ast.BoolOp):
            parts = [self.compile(v) for v in node.values]
            for (t, _), v in zip(parts, node.values):
                self.need(t, BOOL, v, "'and'" if isinstance(node.op, ast.And) else "'or'")
            fs = [f for _, f in parts]
            if isinstance(node.op, ast.And):
                return BOOL, (lambda env: all(f(env) for f in fs))
            return BOOL, (lambda env: any(f(env) for f in fs))
        if isinstance(node, ast.Compare):
            return self.compare(node)
        if isinstance(node, ast.IfExp):
            tt, ft = self.compile(node.test)
            self.need(tt, BOOL, node.test, "the condition of 'if'")
            ta, fa = self.compile(node.body)
            tb, fb = self.compile(node.orelse)
            return self.unify(ta, tb, node), (lambda env: fa(env) if ft(env) else fb(env))
        if isinstance(node, ast.Call):
            return self.call(node)
        if isinstance(node, ast.Tuple):
            raise self.err("DSL001", node, "tuples are allowed only on the right side of 'in'",
                           "write x in ('a', 'b')")
        what = _NODE_NAMES.get(type(node), type(node).__name__)
        raise self.err("DSL001", node, f"{what} not allowed")

    def unify(self, a: Ty, b: Ty, node: ast.AST) -> Ty:
        if a.kind == "any":
            return b
        if b.kind == "any":
            return a
        if a.kind != b.kind:
            raise self.err("DSL003", node, f"both branches of 'if' must have the same type; got {a.describe()} "
                                           f"and {b.describe()}")
        if a.kind != "choice":
            return a
        if not a.literal and not b.literal and a.values != b.values:
            raise self.err("DSL003", node, f"both branches of 'if' must be choices of the same param; got "
                                           f"{a.describe()} and {b.describe()}")
        if a.literal and not b.literal:
            self.member(a, b, node)
            return b
        if b.literal and not a.literal:
            self.member(b, a, node)
            return a
        return Ty("choice", a.values | b.values, a.origin if a.origin == b.origin else None, a.literal and b.literal)

    def member(self, lit: Ty, of: Ty, node: ast.AST) -> None:
        """문자열 상수 lit 가 선택값 of 의 선택지인지."""
        bad = sorted(lit.values - of.values)
        if not bad:
            return
        v = bad[0]
        order = self.scope.orders.get(of.origin or "", None)
        owner = f"`{of.origin}`" if of.origin else "this slot"
        hint = self._suggest(v, sorted(of.values))
        raise self.err("DSL003", node, f"`{v!r}` is not a choice of {owner}; choices: {_choices_text(of, order)}",
                       hint)

    def compare(self, node: ast.Compare) -> tuple[Ty, Callable[[Env], object]]:
        if len(node.ops) != 1:
            raise self.err("DSL001", node, "chained comparisons are not allowed", "write (a < b) and (b < c)")
        op = node.ops[0]
        left, right = node.left, node.comparators[0]
        if isinstance(op, (ast.In, ast.NotIn)):
            tl, fl = self.compile(left)
            if not isinstance(right, ast.Tuple):
                raise self.err("DSL001", right, "the right side of 'in' must be a tuple of strings",
                               "write x in ('a', 'b') (a single item needs a trailing comma: ('a',))")
            if not right.elts:
                raise self.err("DSL001", right, "the tuple after 'in' is empty; it needs at least one string",
                               "write x in ('a',) or compare with ==")
            values: list[str] = []
            for e in right.elts:
                if not (isinstance(e, ast.Constant) and isinstance(e.value, str)):
                    raise self.err("DSL003", e, "the tuple after 'in' may contain only strings")
                values.append(e.value)
            if tl.kind != "any":
                if tl.kind != "choice" or tl.literal:
                    raise self.err("DSL003", left, f"the left side of 'in' must be a choice param, got "
                                                   f"{tl.describe()}")
                self.member(Ty("choice", frozenset(values), None, True), tl, right)
            vs = frozenset(values)
            if isinstance(op, ast.In):
                return BOOL, (lambda env: fl(env) in vs)
            return BOOL, (lambda env: fl(env) not in vs)
        tl, fl = self.compile(left)
        tr, fr = self.compile(right)
        num_op = _CMP_NUM.get(type(op))
        if num_op is not None:
            self.need(tl, NUM, left, "comparison")
            self.need(tr, NUM, right, "comparison")
            return BOOL, (lambda env: num_op(fl(env), fr(env)))
        if not isinstance(op, (ast.Eq, ast.NotEq)):
            raise self.err("DSL001", node, f"comparison {type(op).__name__} is not allowed",
                           "use <, <=, >, >=, ==, != or in")
        if tl.kind != "any" and tr.kind != "any":
            if tl.kind != tr.kind:
                bad = tl if tl.literal else tr
                if bad.literal:
                    raise self.err("DSL003", node, f"cannot compare {tl.describe()} with {tr.describe()}",
                                   _STRING_RULE)
                raise self.err("DSL003", node, f"cannot compare {tl.describe()} with {tr.describe()}")
            if tl.kind == "choice":
                if tl.literal and tr.literal:
                    raise self.err("DSL003", node, "comparing two strings is always the same; compare a choice "
                                                   "param with a string")
                if tl.literal:
                    self.member(tl, tr, left)
                elif tr.literal:
                    self.member(tr, tl, right)
                elif not (tl.values & tr.values):
                    raise self.err("DSL003", node, f"{tl.describe()} and {tr.describe()} have no common choice")
        if isinstance(op, ast.Eq):
            return BOOL, (lambda env: fl(env) == fr(env))
        return BOOL, (lambda env: fl(env) != fr(env))

    def call(self, node: ast.Call) -> tuple[Ty, Callable[[Env], object]]:
        if not isinstance(node.func, ast.Name):
            raise self.err("DSL001", node, "only the built-in functions can be called",
                           "functions: " + ", ".join(FUNCS))
        fname = node.func.id
        if fname not in FUNCS:
            hint = self._suggest(fname, list(FUNCS)) or ("functions: " + ", ".join(FUNCS))
            raise self.err("DSL002", node.func, f"unknown function '{fname}'", hint)
        if node.keywords:
            raise self.err("DSL001", node, f"{fname}() takes positional arguments only")
        for a in node.args:
            if isinstance(a, ast.Starred):
                raise self.err("DSL001", a, "starred arguments (*x) not allowed")
        lo, hi = FUNCS[fname]
        n = len(node.args)
        if not lo <= n <= hi:
            want = str(lo) if lo == hi else f"{lo} to {hi}"
            raise self.err("DSL003", node, f"{fname}() takes {want} arguments, got {n}")
        impl = _FUNC_IMPL[fname]
        if fname == "port_height":
            ts, fs = self.compile(node.args[0])
            tw, fw = self.compile(node.args[1])
            if ts.kind != "any":
                if ts.kind != "choice":
                    raise self.err("DSL003", node.args[0], f"port_height() shape must be a choice, got "
                                                           f"{ts.describe()}")
                bad = sorted(ts.values - set(DOOR_PROFILES))
                src = ast.unparse(node.args[0])
                if bad:
                    raise self.err("DSL003", node.args[0], f"port_height() shape `{src}` can be {bad[0]!r}, which is "
                                                           f"not a door shape; shapes: {', '.join(DOOR_PROFILES)}")
            self.need(tw, NUM, node.args[1], "port_height() width")
            return NUM, (lambda env: _finite(port_height(fs(env), fw(env))))  # type: ignore[arg-type]
        args = [self.compile(a) for a in node.args]
        for (t, _), a in zip(args, node.args):
            self.need(t, NUM, a, f"{fname}()")
        fs = [f for _, f in args]
        return NUM, (lambda env: _finite(impl(*(f(env) for f in fs))))


def _parse(src: str, path: str) -> ast.Expression:
    if not isinstance(src, str):
        raise DslError("DSL013", path, f"an expression must be a string, got {type(src).__name__}")
    if len(src) > MAX_SOURCE_CHARS:
        raise DslError("DSL005", path, f"expression is {len(src)} characters; the limit is {MAX_SOURCE_CHARS}",
                       "split it into let values")
    if not src.strip():
        raise DslError("DSL001", path, "empty expression")
    lead = len(src) - len(src.lstrip())
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError as e:
        col = e.offset + lead if isinstance(e.offset, int) and e.offset > 0 else None
        raise DslError("DSL001", path, f"syntax error: {e.msg}", "check brackets, quotes and operators",
                       col) from None
    except (ValueError, RecursionError, MemoryError, OverflowError) as e:
        raise DslError("DSL001", path, f"syntax error: {e}") from None
    # 크기 한도: 식 노드 수와 중첩 깊이 (반복으로 센다)
    count = 0
    stack: list[tuple[ast.AST, int]] = [(tree.body, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, ast.expr):
            count += 1
            if count > MAX_NODES:
                raise DslError("DSL005", path, f"expression has more than {MAX_NODES} nodes",
                               "split it into let values")
            if depth > MAX_DEPTH:
                raise DslError("DSL005", path, f"expression is nested deeper than {MAX_DEPTH} levels",
                               "split it into let values")
            depth += 1
        stack.extend((c, depth) for c in ast.iter_child_nodes(node))
    return tree


def compile_expr(src: str, scope: Scope, expect: Ty | None = None, path: str = "") -> CompiledExpr:
    """식 하나를 컴파일한다. expect: 자리의 형 (NUM, BOOL, 또는 허용 선택지의 choice). None 이면 형을 그대로 둔다.

    오류는 DslError (code·path·col·message·hint). 다른 예외는 내지 않는다."""
    tree = _parse(src, path)
    c = _Compiler(src.strip(), scope, path, len(src) - len(src.lstrip()))
    try:
        ty, fn = c.compile(tree.body)
        if expect is not None:
            _check_slot(c, ty, expect, tree.body)
    except RecursionError:
        raise DslError("DSL005", path, "expression is nested too deeply") from None
    if expect is not None and expect.kind == "choice" and ty.kind == "choice":
        ty = Ty("choice", ty.values, ty.origin or expect.origin, ty.literal)
    return CompiledExpr(src, path, ty, frozenset(c.names), frozenset(c.rule_fields), frozenset(c.ctx_fields), fn)


def _check_slot(c: _Compiler, got: Ty, want: Ty, node: ast.AST) -> None:
    if got.kind == "any" or want.kind == "any":
        return
    if want.kind in ("num", "bool"):
        c.need(got, want, node, "this slot")
        return
    # 선택값 자리: 값이 모두 허용 선택지 안에 있어야 한다
    if got.kind != "choice":
        raise c.err("DSL003", node, f"this slot needs a {want.describe()} value, got {got.describe()}")
    if got.literal:
        c.member(got, want, node)
        return
    bad = sorted(got.values - want.values)
    if bad:
        order = c.scope.orders.get(want.origin or "", None)
        raise c.err("DSL003", node, f"{got.describe()} can be {bad[0]!r}, which this slot does not allow; "
                                    f"allowed: {_choices_text(want, order)}")


# ── 규칙·맥락 값 ──

def rule_bindings(size: object) -> dict[str, object]:
    """SizeRules(크기 구분 규칙) → {"rule.<이름>": 값}. 값이 없는(null) 필드는 None."""
    out: dict[str, object] = {}
    for name in RULE_NAMES:
        v: object = size
        for part in name.split("."):
            v = getattr(v, part, None)
            if v is None:
                break
        out[f"rule.{name}"] = v
    return out


def ctx_bindings(ctx: object) -> dict[str, object]:
    """RuleContext → {"ctx.<이름>": 값}. 출력 공간이 없으면 기준 프린터(220×220×250)로 본다."""
    bed = getattr(ctx, "build_volume_mm", None) or DEFAULT_BED_MM
    return {
        "ctx.count": ctx.count,
        "ctx.min_wall_mm": ctx.min_wall_mm,
        "ctx.default_wall_mm": ctx.default_wall_mm,
        "ctx.min_entrances": ctx.hideout_min_entrances,
        "ctx.bed_x_mm": float(bed[0]),
        "ctx.bed_y_mm": float(bed[1]),
        "ctx.bed_z_mm": float(bed[2]),
    }


def rule_ctx_bindings(ctx: object) -> dict[str, object]:
    """RuleContext 하나로 rule.·ctx. 값을 함께 만든다."""
    return {**rule_bindings(ctx.size), **ctx_bindings(ctx)}


# ── 파일 단위 컴파일 ──

_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def param_type(name: str, spec: Mapping[str, object]) -> Ty:
    kind = spec.get("type")
    if kind in ("number", "integer"):
        return NUM
    if kind == "bool":
        return BOOL
    if kind == "choice":
        return choice(spec.get("choices") or (), name)
    return ANY


@dataclass(frozen=True)
class CompiledPart:
    """부품 파일의 모든 식을 컴파일한 것.

    exprs: JSON 포인터 → 컴파일된 식 (JSON 숫자로 적은 자리도 상수 식으로 들어 있다).
    lets: (이름, 식) 차례. rule_fields: 파일 전체에서 쓴 rule. 이름 (R03 rule_fields_used)."""

    params: dict[str, Ty]
    lets: tuple[tuple[str, CompiledExpr], ...]
    exprs: dict[str, CompiledExpr]
    rule_fields: frozenset[str]
    ctx_fields: frozenset[str]

    def get(self, ptr: str) -> CompiledExpr | None:
        return self.exprs.get(ptr)

    def __getitem__(self, ptr: str) -> CompiledExpr:
        return self.exprs[ptr]

    def geometry_env(self, params: Mapping[str, object]) -> dict[str, object]:
        """파라미터 값 → let 까지 계산한 geometry 범위의 값."""
        env: dict[str, object] = dict(params)
        for name, e in self.lets:
            env[name] = e.evaluate(env)
        return env

    def rule_env(self, params: Mapping[str, object], bindings: Mapping[str, object]) -> dict[str, object]:
        """geometry 범위 + rule.·ctx. 값 (bindings 는 rule_ctx_bindings 로 만든다)."""
        env = self.geometry_env(params)
        env.update(bindings)
        return env


class _FileCompiler:
    """부품 파일(스키마 검사를 마친 dict)의 식 자리를 범위·형에 맞춰 모두 컴파일한다. 오류는 모아서 낸다."""

    def __init__(self, data: Mapping[str, object]):
        self.data = data
        self.errors: list[DslError] = []
        self.exprs: dict[str, CompiledExpr] = {}
        self.count = 0
        params = data.get("params") or {}
        self.param_specs: dict[str, Mapping[str, object]] = {
            k: v for k, v in params.items() if isinstance(v, dict)}  # type: ignore[union-attr]
        self.params: dict[str, Ty] = {k: param_type(k, v) for k, v in self.param_specs.items()}
        self.orders = {k: tuple(v.get("choices") or ()) for k, v in self.param_specs.items()  # type: ignore[arg-type]
                       if v.get("type") == "choice"}
        self.lets: list[tuple[str, CompiledExpr]] = []
        self.let_types: dict[str, Ty] = {}
        self.all_let_names: list[str] = [
            x["name"] for x in (data.get("let") or [])  # type: ignore[union-attr]
            if isinstance(x, dict) and isinstance(x.get("name"), str)]

    # 범위 만들기
    def scope(self, *, rule: bool = False, repeat: tuple[str, ...] = (), kind: str = "geometry") -> Scope:
        """파라미터 + 지금까지 정의한 let (+ 반복 변수). 아직 정의하지 않은 let 과 반복 변수는 hidden."""
        names: dict[str, Ty] = dict(self.params)
        names.update(self.let_types)
        hidden: dict[str, str] = {}
        for n in self.all_let_names:
            if n not in names:
                hidden[n] = f"'{n}' is defined later in let; a let may use only params and earlier lets"
        for v in ("i", "j"):
            if v in repeat:
                names[v] = NUM
            else:
                hidden[v] = ("repeat counts cannot use i or j" if kind == "repeat"
                             else f"'{v}' exists only in body steps whose repeat declares it")
        return Scope(names, rule, hidden, kind, self.orders)

    def rule_default_scope(self, upto: str) -> Scope:
        names: dict[str, Ty] = {}
        hidden: dict[str, str] = {}
        seen = False
        for k, t in self.params.items():
            if k == upto:
                seen = True
                hidden[k] = "rule_default may use only params declared before it"
            elif seen:
                hidden[k] = "rule_default may use only params declared before it"
            else:
                names[k] = t
        for n in self.all_let_names:
            hidden[n] = "lets cannot be used in rule_default (they depend on every param)"
        for v in ("i", "j"):
            hidden[v] = f"'{v}' exists only in body steps whose repeat declares it"
        return Scope(names, True, hidden, "rule_default", self.orders)

    # 자리 하나
    def slot(self, value: object, ptr: str, scope: Scope, expect: Ty | None) -> CompiledExpr | None:
        if value is None:
            return None
        try:
            if isinstance(value, bool):
                raise DslError("DSL013", ptr, "expected a number or an expression string, got a boolean",
                               "write the expression 'True' or 'False' as a string")
            if isinstance(value, (int, float)):
                if expect is not None and expect.kind not in ("num", "any"):
                    raise DslError("DSL003", ptr, f"this slot needs a {expect.describe()} value, got a number")
                e = constant(value, ptr)
            else:
                self.count += 1
                e = compile_expr(value, scope, expect, ptr)  # type: ignore[arg-type]
        except DslError as err:
            self.errors.append(err)
            return None
        self.exprs[ptr] = e
        return e

    def vec(self, values: object, ptr: str, scope: Scope) -> None:
        if isinstance(values, list):
            for k, v in enumerate(values):
                self.slot(v, f"{ptr}/{k}", scope, NUM)

    # 이름 정의
    def check_names(self) -> None:
        for k in self.param_specs:
            if k in RESERVED:
                self.errors.append(DslError("DSL007", pointer("params", k), f"'{k}' is a reserved name",
                                            "rename the param (lengths end _mm, angles _deg, counts _count)"))
        seen: set[str] = set()
        for idx, let in enumerate(self.data.get("let") or []):  # type: ignore[union-attr]
            n = let.get("name") if isinstance(let, dict) else None
            if not isinstance(n, str):
                continue
            p = pointer("let", idx, "name")
            if n in RESERVED:
                self.errors.append(DslError("DSL007", p, f"'{n}' is a reserved name"))
            elif n in self.param_specs:
                self.errors.append(DslError("DSL007", p, f"let '{n}' has the same name as a param",
                                            "choose another name"))
            elif n in seen:
                self.errors.append(DslError("DSL007", p, f"let '{n}' is defined twice"))
            elif not _NAME_RE.match(n):
                self.errors.append(DslError("DSL007", p, f"'{n}' is not a valid name"))
            seen.add(n)

    def run(self) -> CompiledPart:
        d = self.data
        self.check_names()
        # let: 파라미터와 앞의 let 까지만 보인다
        for idx, let in enumerate(d.get("let") or []):  # type: ignore[union-attr]
            if not isinstance(let, dict):
                continue
            name = let.get("name")
            if not isinstance(name, str) or name in self.let_types or name in self.params or name in RESERVED:
                continue
            e = self.slot(let.get("expr"), pointer("let", idx, "expr"), self.scope(kind="geometry"), None)
            if e is not None and e.type.kind == "choice" and e.type.literal:
                self.errors.append(DslError("DSL003", e.path, "a let cannot be a bare string", _STRING_RULE))
                e = None
            self.let_types[name] = e.type if e is not None else ANY
            if e is not None:
                self.lets.append((name, e))
        geo = self.scope()
        rule = self.scope(rule=True, kind="rule")

        # 파라미터 rule_default (앞의 파라미터 + rule.·ctx.)
        for k, spec in self.param_specs.items():
            if "rule_default" in spec:
                self.slot(spec["rule_default"], pointer("params", k, "rule_default"), self.rule_default_scope(k), NUM)

        for idx, c in enumerate(d.get("constraints") or []):  # type: ignore[union-attr]
            for key in ("min", "max"):
                if key in c:
                    self.slot(c[key], pointer("constraints", idx, key), rule, NUM)
            if "when" in c:
                self.slot(c["when"], pointer("constraints", idx, "when"), rule, BOOL)
        for idx, c in enumerate(d.get("checks") or []):  # type: ignore[union-attr]
            self.slot(c.get("fail_if"), pointer("checks", idx, "fail_if"), rule, BOOL)

        # body
        rep_scope = self.scope(kind="repeat")
        for idx, step in enumerate(d.get("body") or []):  # type: ignore[union-attr]
            base = pointer("body", idx)
            repeat = step.get("repeat") or {}
            for v, cnt in repeat.items():
                self.slot(cnt, f"{base}/repeat/{v}", rep_scope, NUM)
            sc = self.scope(repeat=tuple(sorted(repeat)))
            if "when" in step:
                self.slot(step["when"], f"{base}/when", sc, BOOL)
            for key in ("size", "at"):
                self.vec(step.get(key), f"{base}/{key}", sc)
            for key in ("r", "h", "depth", "width", "length"):
                if key in step:
                    self.slot(step[key], f"{base}/{key}", sc, NUM)
            for k, pt in enumerate(step.get("points") or []):
                self.vec(pt, f"{base}/points/{k}", sc)
            if "shape" in step:
                self.slot(step["shape"], f"{base}/shape", sc, choice(DOOR_PROFILES))

        # anchors
        for name, a in (d.get("anchors") or {}).items():  # type: ignore[union-attr]
            base = pointer("anchors", name)
            self.vec(a.get("origin"), f"{base}/origin", geo)
            self.vec(a.get("mount"), f"{base}/mount", geo)
            if "wall" in a:
                self.slot(a["wall"], f"{base}/wall", geo, NUM)
            door = a.get("door")
            if isinstance(door, dict):
                self.slot(door.get("when"), f"{base}/door/when", geo, BOOL)
                self.slot(door.get("width"), f"{base}/door/width", geo, NUM)
                self.slot(door.get("profile"), f"{base}/door/profile", geo, choice(DOOR_PROFILES))

        # opens: set 의 값은 대상 파라미터의 형
        for idx, o in enumerate(d.get("opens") or []):  # type: ignore[union-attr]
            base = pointer("opens", idx)
            if "when" in o:
                self.slot(o["when"], f"{base}/when", geo, BOOL)
            for k, v in (o.get("set") or {}).items():
                ptr = f"{base}/set/{pointer(k)[1:]}"
                if k not in self.params:
                    hint = difflib.get_close_matches(k, list(self.params), n=1)
                    self.errors.append(DslError("DSL002", ptr, f"unknown param '{k}'",
                                                f"did you mean {hint[0]!r}?" if hint else ""))
                    continue
                self.slot(v, ptr, geo, self.params[k])

        self.vec(d.get("envelope"), "/envelope", geo)
        fn = d.get("face_needs") or {}
        for key in ("min", "max"):
            if fn.get(key) is not None:  # type: ignore[union-attr]
                self.slot(fn[key], f"/face_needs/{key}", geo, NUM)  # type: ignore[index]

        feats = d.get("features") or {}
        for key in ("min_wall", "climb_height", "slope_deg", "step_height"):
            if key in feats:  # type: ignore[operator]
                self.slot(feats[key], f"/features/{key}", geo, NUM)  # type: ignore[index]
        for idx, s in enumerate(feats.get("access_sides") or []):  # type: ignore[union-attr]
            if "when" in s:
                self.slot(s["when"], f"/features/access_sides/{idx}/when", geo, BOOL)
        for idx, o in enumerate(feats.get("openings") or []):  # type: ignore[union-attr]
            base = f"/features/openings/{idx}"
            if "when" in o:
                self.slot(o["when"], f"{base}/when", geo, BOOL)
            if "size" in o:
                self.slot(o["size"], f"{base}/size", geo, NUM)
            probe = o.get("probe")
            if isinstance(probe, dict):
                self.vec(probe.get("at"), f"{base}/probe/at", geo)
                if "length" in probe:
                    self.slot(probe["length"], f"{base}/probe/length", geo, NUM)

        if self.count > MAX_EXPRESSIONS:
            self.errors.append(DslError("DSL005", "", f"the file has {self.count} expressions; the limit is "
                                                      f"{MAX_EXPRESSIONS}"))
        if self.errors:
            raise DslErrors.of(self.errors)
        rule_fields = frozenset().union(*(e.rule_fields for e in self.exprs.values()))
        ctx_fields = frozenset().union(*(e.ctx_fields for e in self.exprs.values()))
        return CompiledPart(dict(self.params), tuple(self.lets), dict(self.exprs), rule_fields, ctx_fields)


def compile_part(data: Mapping[str, object]) -> CompiledPart:
    """부품 파일(스키마 검사를 마친 JSON dict, 또는 schema.PartFile)의 모든 식을 컴파일한다 (S02).
    오류가 있으면 모두 모아 DslErrors 로 낸다."""
    dump = getattr(data, "model_dump", None)
    if dump is not None:
        data = dump(mode="json", exclude_none=True)
    return _FileCompiler(data).run()
