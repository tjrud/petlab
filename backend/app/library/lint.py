"""Part DSL 정적 검사 L01–L12 (설계 §7.3).

형상 커널 없이 돈다: 스키마(schema)·식(expr) 컴파일과, 단계마다 계산한 축 정렬 상자(bbox) 산술만 쓴다.
`python -m app.library check` (S01–S08 + 이 검사)가 1초 안에 끝나도록 build123d·OCP·trimesh·shapely·numpy 를
불러오지 않는다 (테스트가 확인).

| id  | 규칙 |
|-----|------|
| L01 | 이름·형 (S02 의 일부). let 은 앞의 let 만 쓴다 (순환 없음) |
| L02 | rule.·ctx. 는 규칙 범위 자리(constraints, checks, rule_default)에만 (DSL004) |
| L03 | 합치기 겹침: 출력 파트 안에서 첫 add 뒤의 add 는 앞선 add 하나와 세 축 모두 0.2mm 이상 겹친다 |
| L04 | 자르는 상자의 면이 앞선 add 상자의 같은 쪽 면과 0.5mm 안에 있지 않다 (0.5mm 이상 더 나가거나 안쪽) |
| L05 | add 단계마다 형상을 남긴다: 상자가 뒤의 cut 상자 안에 다 들어가지 않는다 |
| L06 | envelope 가 add 상자들의 합(경계를 잘라 낸 cut 을 뺀 것)과 0.5mm 안에서 같다 (기본값에서) |
| L07 | 연결 지점 종류 (§5.6 역할 규칙), attach_order 의 이름, fields 의 파라미터 |
| L08 | rule. 이름이 SizeRules 필드에 있다, rule_key 열거값 |
| L09 | 파라미터 이름·단위 (_mm, _deg, _count), 설명 첫 문장 ko ≤ 30자, en ≤ 40자 |
| L10 | key·family·version·파일 이름이 서로 맞다 |
| L11 | print[0].key == "body", key 중복 없음, 단계의 part, 크기·높이·층 필드는 숫자 파라미터 |
| L12 | 아는 사육 환경, v1 이 허용하는 역할 |

상자 검사(L03–L06)는 첫 종·첫 크기의 기본값(rule_default 반영)과, 숫자 필드마다 최솟값·최댓값 변형, 선택·참거짓
변형에서 돈다. 변형은 파일의 제약(constraints)과 벽 두께 하한으로 가볍게 맞춘다 (clamp_params 와 같은 방향; 커널이 없는
근사). 계산이 안 되는 변형(DSL006)은 건너뛰고 skipped 에 적는다 (검증기의 P4 가 다룬다).

메시지와 고치는 방법(hint)은 다른 DSL 오류처럼 영어다 (개발자 에이전트가 읽는다).
"""

from __future__ import annotations

import json
import math
import re
import sys
import typing
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.library.errors import DslError, DslErrors, pointer
from app.library.expr import (
    RULE_NAMES,
    CompiledPart,
    compile_part,
    port_height,
    rule_ctx_bindings,
)
from app.library.index import desc_head
from app.library.schema import (
    BoxStep,
    CylinderStep,
    PartFile,
    PassageOpening,
    PassageStep,
    PrismStep,
    RuleKey,
    load_part_json,
    parse_part,
)

LINT_IDS: tuple[str, ...] = tuple(f"L{n:02d}" for n in range(1, 13))

OVERLAP_MIN_MM = 0.2  # L03: add 끼리 세 축 모두 이만큼 겹친다
COPLANAR_MM = 0.5  # L04: 자르는 면과 add 면 사이 최소 거리
ENVELOPE_TOL_MM = 0.5  # L06
ANCHOR_TOL_MM = 0.5  # L07: 슬라이드 연결 지점이 뒷면 아래 가운데에 있는지
DESC_HEAD_KO_MAX = 30  # L09
DESC_HEAD_EN_MAX = 40
SETTLE_PASSES = 8  # 변형을 제약에 맞추는 최대 횟수 (clamp_params 의 max_passes 와 같다)
REPEAT_MAX = 64  # app.library.template.REPEAT_MAX 와 같다 (테스트가 확인)
_EPS = 1e-6

V1_ROLES: tuple[str, ...] = ("host", "room_host", "accessory", "none")
V1_HABITATS: tuple[str, ...] = ("cage",)
# 수평 법선 → 그 면의 쪽 (출입구의 side 는 법선의 쪽과 같아야 한다)
SIDE_OF_NORMAL: dict[str, str] = {"-Y": "front", "+Y": "back", "-X": "left", "+X": "right"}
HORIZONTAL = frozenset(SIDE_OF_NORMAL)
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
_AXIS_NAMES = ("X", "Y", "Z")
_UNIT_SUFFIXES = ("_mm", "_deg", "_count")
_NUMERIC = ("number", "integer")

Box = tuple[float, float, float, float, float, float]  # (x0, y0, z0, x1, y1, z1)


# ── 결과 ──

@dataclass(frozen=True)
class LintIssue:
    """정적 검사 실패 하나. 보고서(§7.7)의 검사 결과와 같은 필드를 낸다 (to_dict)."""

    id: str  # L01..L12
    path: str  # JSON 포인터
    message: str  # 영어
    hint: str = ""
    variant: str | None = None  # 상자 검사에서 실패한 변형 (예: "hamster/dwarf/c1/max:size_mm")
    value: float | None = None
    limit: float | None = None
    code: str | None = None  # 바탕이 된 DSL 오류 코드 (L01·L02: DSL002 등, L11: DSL020)
    col: int | None = None

    def __str__(self) -> str:
        where = self.path or "/"
        if self.col is not None:
            where += f" (col {self.col})"
        s = f"{self.id} {where}: {self.message}"
        if self.variant:
            s += f" [{self.variant}]"
        if self.hint:
            s += f" (hint: {self.hint})"
        return s

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "ok": False, "variant": self.variant, "path": self.path,
                             "value": self.value, "limit": self.limit, "message": self.message, "hint": self.hint}
        if self.code is not None:
            d["code"] = self.code
        if self.col is not None:
            d["col"] = self.col
        return d


@dataclass(frozen=True)
class LintSkip:
    """상자 검사를 하지 못한 변형 (식 계산 오류 등). 실패가 아니다: 검증기의 P4 가 다룬다."""

    variant: str
    error: DslError

    def to_dict(self) -> dict[str, Any]:
        return {"variant": self.variant, **self.error.to_dict()}


@dataclass(frozen=True)
class LintReport:
    issues: tuple[LintIssue, ...]
    variants: tuple[str, ...] = ()  # 상자 검사를 한 변형
    skipped: tuple[LintSkip, ...] = ()
    context: str | None = None  # "<종>/<크기>" (규칙 없이 돌았으면 None)

    @property
    def ok(self) -> bool:
        return not self.issues

    def ids(self) -> set[str]:
        return {i.id for i in self.issues}

    def by_id(self, lint_id: str) -> list[LintIssue]:
        return [i for i in self.issues if i.id == lint_id]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "context": self.context, "variants": list(self.variants),
                "issues": [i.to_dict() for i in self.issues], "skipped": [s.to_dict() for s in self.skipped]}

    def text(self) -> str:
        if self.ok:
            return f"lint: ok ({len(self.variants)} variants)"
        return "\n".join([f"lint: {len(self.issues)} issue(s)"] + [f"  {i}" for i in self.issues])


# ── 규칙 문맥 (커널 없이) ──

@dataclass(frozen=True)
class LintContext:
    """rule_default·제약을 계산할 규칙 값. bindings 는 expr.rule_ctx_bindings 형식 ("rule.<이름>", "ctx.<이름>")."""

    species: str
    size: str
    bindings: Mapping[str, object]

    @property
    def case(self) -> str:
        return f"{self.species}/{self.size}"


@dataclass(frozen=True)
class _Ctx:
    """RuleContext 의 가벼운 대역 (expr.ctx_bindings 가 읽는 속성만). app.templates.base 는 커널을 불러온다."""

    size: Any
    min_wall_mm: float
    count: int
    build_volume_mm: tuple[float, float, float] | None

    @property
    def hideout_min_entrances(self) -> int:
        return self.size.hideout_min_entrances.for_count(self.count)

    @property
    def default_wall_mm(self) -> float:  # RuleContext.default_wall_mm 과 같다
        return max(3.0, self.min_wall_mm)


@lru_cache(maxsize=1)
def _default_rules():  # type: ignore[no-untyped-def]
    from app.config import get_settings
    from app.rules.loader import load_rules

    return load_rules(get_settings().rules_dir)


def context_for(habitats: Iterable[str], rules: object | None = None, count: int = 1) -> LintContext | None:
    """habitats 에 맞는 첫 종의 첫 크기 구분 문맥 (species.yaml 순서). 맞는 종이 없으면 None.
    rules 를 주지 않으면 rules/species.yaml·printing.yaml 을 읽는다 (한 번만)."""
    book = rules if rules is not None else _default_rules()
    wanted = set(habitats)
    for sp_key, sp in book.species_file.species.items():  # type: ignore[attr-defined]
        if sp.habitat not in wanted:
            continue
        for size_key, size in sp.sizes.items():
            bed = book.printing.build_volume_mm  # type: ignore[attr-defined]
            ctx = _Ctx(size, book.min_wall_for(sp_key, size_key), count,  # type: ignore[attr-defined]
                       tuple(float(v) for v in bed) if bed else None)  # type: ignore[arg-type]
            return LintContext(sp_key, size_key, rule_ctx_bindings(ctx))
    return None


@lru_cache(maxsize=1)
def size_rule_fields() -> frozenset[str]:
    """SizeRules 의 필드 이름 (중첩 모델은 점 표기: "gap_trap.safe_max_mm")."""
    from pydantic import BaseModel

    from app.rules.loader import SizeRules

    out: set[str] = set()

    def walk(model: type[BaseModel], prefix: str) -> None:
        for name, f in model.model_fields.items():
            out.add(prefix + name)
            for t in (f.annotation, *typing.get_args(f.annotation)):
                if isinstance(t, type) and issubclass(t, BaseModel):
                    walk(t, f"{prefix}{name}.")

    walk(SizeRules, "")
    return frozenset(out)


def _known_habitats() -> tuple[str, ...]:
    from app.rules.loader import Habitat

    return tuple(typing.get_args(Habitat))


# ── 단계 상자 ──

def step_bbox(op: str, args: Mapping[str, Any]) -> Box:
    """계산을 마친 단계 하나의 축 정렬 상자 (사용 자세). app.library.ops 의 형상과 같은 규칙
    (tests/test_library_lint.py 가 build123d 형상의 bounding box 와 비교한다)."""
    ax, ay, az = (float(v) for v in (args.get("at") or (0.0, 0.0, 0.0)))
    if op == "box":
        sx, sy, sz = (float(v) for v in args["size"])
        z0 = az if args.get("align", "bottom") == "bottom" else az - sz / 2
        return (ax - sx / 2, ay - sy / 2, z0, ax + sx / 2, ay + sy / 2, z0 + sz)
    if op == "cylinder":
        r, h = float(args["r"]), float(args["h"])
        bottom = args.get("align", "bottom") == "bottom"
        axis = args["axis"]
        if axis == "z":
            z0 = az if bottom else az - h / 2
            return (ax - r, ay - r, z0, ax + r, ay + r, z0 + h)
        cz = az + r if bottom else az
        if axis == "x":
            return (ax - h / 2, ay - r, cz - r, ax + h / 2, ay + r, cz + r)
        return (ax - r, ay - h / 2, cz - r, ax + r, ay + h / 2, cz + r)
    if op == "prism":
        pts = [(float(a), float(b)) for a, b in args["points"]]
        a0, a1 = min(p[0] for p in pts), max(p[0] for p in pts)
        b0, b1 = min(p[1] for p in pts), max(p[1] for p in pts)
        d = float(args["depth"]) / 2
        plane = args["plane"]
        if plane == "xz":
            return (ax + a0, ay - d, az + b0, ax + a1, ay + d, az + b1)
        if plane == "yz":
            return (ax - d, ay + a0, az + b0, ax + d, ay + a1, az + b1)
        return (ax + a0, ay + b0, az - d, ax + a1, ay + b1, az + d)
    if op == "passage":
        w, n = float(args["width"]), float(args["length"]) / 2
        top = az + port_height(str(args["shape"]), w)
        z0 = az - 1.0  # 터널 안쪽 단면은 바닥 아래 1mm 까지 (tunnel._CUT)
        if args["axis"] == "y":
            return (ax - w / 2, ay - n, z0, ax + w / 2, ay + n, top)
        return (ax - n, ay - w / 2, z0, ax + n, ay + w / 2, top)
    raise ValueError(f"unknown op {op!r}")


def _overlaps(a: Box, b: Box) -> tuple[float, float, float]:
    """축마다 겹친 길이 (음수면 그만큼 떨어져 있다)."""
    return (min(a[3], b[3]) - max(a[0], b[0]), min(a[4], b[4]) - max(a[1], b[1]),
            min(a[5], b[5]) - max(a[2], b[2]))


def _meet(a: Box, b: Box, gap: float) -> bool:
    """세 축 모두 gap 보다 많이 겹치는지 (빠른 판정)."""
    return (a[0] + gap < b[3] and b[0] + gap < a[3] and a[1] + gap < b[4] and b[1] + gap < a[4]
            and a[2] + gap < b[5] and b[2] + gap < a[5])


def _inside(a: Box, b: Box) -> bool:
    """a 가 b 안에 다 들어가는지."""
    return (a[0] >= b[0] - _EPS and a[1] >= b[1] - _EPS and a[2] >= b[2] - _EPS
            and a[3] <= b[3] + _EPS and a[4] <= b[4] + _EPS and a[5] <= b[5] + _EPS)


def _union(a: Box | None, b: Box) -> Box:
    if a is None:
        return b
    return (min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]), max(a[4], b[4]), max(a[5], b[5]))


def _trim(u: Box, c: Box) -> Box:
    """경계 상자 u 를 다른 두 축으로 완전히 덮고 한쪽 끝을 넘는 cut c 로 잘라 낸다 (아니면 그대로)."""
    out = list(u)
    for k in range(3):
        others = [m for m in range(3) if m != k]
        if not all(c[m] <= u[m] + _EPS and c[m + 3] >= u[m + 3] - _EPS for m in others):
            continue
        if c[k] <= u[k] + _EPS and u[k] + _EPS < c[k + 3] < u[k + 3] - _EPS:
            out[k] = c[k + 3]
        elif c[k + 3] >= u[k + 3] - _EPS and u[k] + _EPS < c[k] < u[k + 3] - _EPS:
            out[k + 3] = c[k]
    return tuple(out)  # type: ignore[return-value]


@dataclass(frozen=True)
class _Inst:
    """변형 하나에서 실제로 만들어지는 단계 사본 하나 (반복 변수마다)."""

    step: int
    part: str
    mode: str
    box: Box
    rep: str  # "" 또는 " (i=1)" 처럼 반복 변수

    @property
    def path(self) -> str:
        return pointer("body", self.step)

    @property
    def label(self) -> str:
        return f"step {self.step}{self.rep}"


class _VariantError(Exception):
    def __init__(self, error: DslError):
        super().__init__(str(error))
        self.error = error


def _num(compiled: CompiledPart, ptr: str, env: Mapping[str, object], default: float = 0.0) -> float:
    e = compiled.get(ptr)
    return default if e is None else float(e.evaluate(env))  # type: ignore[arg-type]


def _vec(compiled: CompiledPart, ptr: str, env: Mapping[str, object]) -> tuple[float, float, float]:
    return (_num(compiled, f"{ptr}/0", env), _num(compiled, f"{ptr}/1", env), _num(compiled, f"{ptr}/2", env))


def _when(compiled: CompiledPart, ptr: str, env: Mapping[str, object]) -> bool:
    e = compiled.get(ptr)
    return True if e is None else bool(e.evaluate(env))


def _instances(part: PartFile, compiled: CompiledPart, values: Mapping[str, object]) -> list[_Inst]:
    """변형의 파라미터 값 → 만들어지는 단계 사본 (파일 차례, 반복은 i 바깥 j 안쪽). 계산 오류는 _VariantError."""
    try:
        env = compiled.geometry_env(values)
        out: list[_Inst] = []
        for idx, step in enumerate(part.body):
            base = pointer("body", idx)
            counts: dict[str, int] = {}
            for v in sorted(step.repeat or {}):
                raw = _num(compiled, f"{base}/repeat/{v}", env)
                n = round(raw)
                if abs(raw - n) > 1e-9 or not 0 <= n <= REPEAT_MAX:
                    raise DslError("DSL006", f"{base}/repeat/{v}",
                                   f"repeat count {v} = {raw:g} must be a whole number in 0..{REPEAT_MAX}")
                counts[v] = n
            if math.prod(counts.values()) > REPEAT_MAX:
                raise DslError("DSL006", f"{base}/repeat",
                               f"repeat makes {math.prod(counts.values())} copies; the limit is {REPEAT_MAX}")
            for i in range(counts.get("i", 1)):
                for j in range(counts.get("j", 1)):
                    e = dict(env)
                    rep = []
                    if "i" in counts:
                        e["i"] = i
                        rep.append(f"i={i}")
                    if "j" in counts:
                        e["j"] = j
                        rep.append(f"j={j}")
                    if not _when(compiled, f"{base}/when", e):
                        continue
                    args = _step_args(step, compiled, base, e)
                    out.append(_Inst(idx, step.part, step.mode, step_bbox(step.op, args),
                                     f" ({', '.join(rep)})" if rep else ""))
        return out
    except DslError as err:
        raise _VariantError(err) from None


def _positive(v: float, what: str, ptr: str) -> float:
    if not (math.isfinite(v) and v > 0):
        raise DslError("DSL006", ptr, f"{what} must be a positive number, got {v:g}",
                       "check the expression at this step for the current params")
    return v


def _step_args(step: Any, compiled: CompiledPart, base: str, env: Mapping[str, object]) -> dict[str, Any]:
    args: dict[str, Any] = {"at": _vec(compiled, f"{base}/at", env)}
    if isinstance(step, BoxStep):
        size = _vec(compiled, f"{base}/size", env)
        for k, v in enumerate(size):
            _positive(v, f"box size[{k}]", f"{base}/size/{k}")
        args.update(size=size, align=step.align)
    elif isinstance(step, CylinderStep):
        args.update(r=_positive(_num(compiled, f"{base}/r", env), "cylinder r", f"{base}/r"),
                    h=_positive(_num(compiled, f"{base}/h", env), "cylinder h", f"{base}/h"),
                    axis=step.axis, align=step.align)
    elif isinstance(step, PrismStep):
        pts = [(_num(compiled, f"{base}/points/{k}/0", env), _num(compiled, f"{base}/points/{k}/1", env))
               for k in range(len(step.points))]
        args.update(plane=step.plane, points=pts,
                    depth=_positive(_num(compiled, f"{base}/depth", env), "prism depth", f"{base}/depth"))
    elif isinstance(step, PassageStep):
        shape = compiled[f"{base}/shape"].evaluate(env)
        args.update(shape=str(shape),
                    width=_positive(_num(compiled, f"{base}/width", env), "passage width", f"{base}/width"),
                    axis=step.axis,
                    length=_positive(_num(compiled, f"{base}/length", env), "passage length", f"{base}/length"))
    return args


# ── 변형 ──

def _defaults(part: PartFile, compiled: CompiledPart, ctx: LintContext | None) -> dict[str, object]:
    """기본값 (DslTemplate.default_params 와 같은 규칙: rule_default 를 차례대로, 정수는 0.5 올림, 필드 범위로 자름)."""
    values: dict[str, object] = {k: spec.default for k, spec in part.params.items()}
    if ctx is None:
        return values
    for name, spec in part.params.items():
        if spec.type not in _NUMERIC or getattr(spec, "rule_default", None) is None:
            continue
        v = float(compiled[pointer("params", name, "rule_default")].evaluate({**values, **ctx.bindings}))  # type: ignore[arg-type]
        v = min(max(v, float(spec.min)), float(spec.max))  # type: ignore[union-attr]
        values[name] = math.floor(v + 0.5) if spec.type == "integer" else v
    return values


def _settle(part: PartFile, compiled: CompiledPart, values: dict[str, object],
            ctx: LintContext | None) -> dict[str, object] | None:
    """변형을 파일의 제약과 벽 두께 하한에 맞춘다 (clamp_params 의 가벼운 근사). 맞출 수 없으면 None."""
    if ctx is None:
        return values
    values = dict(values)
    params = part.params
    for _ in range(SETTLE_PASSES):
        changed = False
        bounds: list[tuple[str, str, float]] = []
        wall_min = ctx.bindings.get("ctx.min_wall_mm")
        if "wall_thickness_mm" in params and isinstance(wall_min, (int, float)):
            bounds.append(("wall_thickness_mm", "min", float(wall_min)))
        env = compiled.rule_env(values, ctx.bindings)
        for i, c in enumerate(part.constraints):
            spec = params.get(c.field)
            if spec is None or spec.type not in _NUMERIC:
                continue
            base = pointer("constraints", i)
            if not _when(compiled, f"{base}/when", env):
                continue
            which = "min" if c.min is not None else "max"
            bounds.append((c.field, which, _num(compiled, f"{base}/{which}", env)))
        for f, which, bound in bounds:
            spec = params[f]
            v = float(values[f])  # type: ignore[arg-type]
            if which == "min" and v < bound - 1e-9:
                nv = float(math.ceil(bound - 1e-9)) if spec.type == "integer" else bound
            elif which == "max" and v > bound + 1e-9:
                nv = float(math.floor(bound + 1e-9)) if spec.type == "integer" else bound
            else:
                continue
            lo, hi = float(spec.min), float(spec.max)  # type: ignore[union-attr]
            if nv < lo - 1e-9 or nv > hi + 1e-9:
                return None
            values[f] = int(nv) if spec.type == "integer" else nv
            changed = True
        if not changed:
            return values
    return None


def _variants(part: PartFile, compiled: CompiledPart,
              ctx: LintContext | None) -> tuple[list[tuple[str, dict[str, object]]], list[LintSkip]]:
    """(변형 id, 파라미터 값) 목록. 첫 항목이 기본값. 같은 값이 된 변형은 하나로 합친다."""
    prefix = f"{ctx.case}/c1/" if ctx is not None else ""
    skipped: list[LintSkip] = []
    try:
        default = _defaults(part, compiled, ctx)
    except DslError as err:
        return [], [LintSkip(f"{prefix}default", err)]
    raw: list[tuple[str, dict[str, object]]] = [(f"{prefix}default", default)]
    for name, spec in part.params.items():
        if spec.type in _NUMERIC:
            for which in ("min", "max"):
                bound = getattr(spec, which)
                raw.append((f"{prefix}{which}:{name}", {**default, name: bound}))
        elif spec.type == "choice":
            for v in spec.choices:  # type: ignore[union-attr]
                if v != default[name]:
                    raw.append((f"{prefix}choice:{name}={v}", {**default, name: v}))
        else:
            v = not default[name]
            raw.append((f"{prefix}bool:{name}={str(v).lower()}", {**default, name: v}))
    out: list[tuple[str, dict[str, object]]] = []
    seen: set[str] = set()
    for vid, values in raw:
        if vid != raw[0][0]:
            try:
                settled = _settle(part, compiled, values, ctx)
            except DslError as err:
                skipped.append(LintSkip(vid, err))
                continue
            if settled is None:
                continue  # 제약에 맞출 수 없는 변형 (검증기의 P2 가 unreachable 로 적는다)
            values = settled
        k = json.dumps(values, sort_keys=True, default=str)
        if k in seen:
            continue
        seen.add(k)
        out.append((vid, values))
    return out, skipped


# ── L01·L02: 식 ──

_RULE_IN_GEOMETRY = re.compile(r"^(rule|ctx)\.")


def _expr_issues(err: DslErrors | DslError) -> list[LintIssue]:
    errors = err.errors if isinstance(err, DslErrors) and err.errors else [err]
    out: list[LintIssue] = []
    for e in errors:
        lid = "L02" if e.code == "DSL004" and _RULE_IN_GEOMETRY.match(e.message) else "L01"
        out.append(LintIssue(lid, e.path, e.message, e.hint, code=e.code, col=e.col))
    return out


# ── L03–L06: 상자 ──

def _by_part(insts: list[_Inst]) -> dict[str, list[_Inst]]:
    out: dict[str, list[_Inst]] = {}
    for x in insts:
        out.setdefault(x.part, []).append(x)
    return out


def _l03(insts: list[_Inst], variant: str) -> list[LintIssue]:
    out: list[LintIssue] = []
    for key, seq in _by_part(insts).items():
        adds = [x for x in seq if x.mode == "add"]
        need = OVERLAP_MIN_MM - 1e-9
        for k, a in enumerate(adds[1:], start=1):
            # 첫 add(바탕)와 바로 앞 add 들부터 본다 (쌓은 모양이 빨리 끝난다). 실패할 때만 모두 본다
            if any(_meet(a.box, b.box, need) for b in (adds[0], *reversed(adds[1:k]))):
                continue
            touching: tuple[_Inst, int, float] | None = None
            ok = False
            for b in adds[:k]:
                ov = _overlaps(a.box, b.box)
                if min(ov) >= need:
                    ok = True
                    break
                low = [m for m in range(3) if ov[m] < OVERLAP_MIN_MM - 1e-9]
                if touching is None and len(low) == 1 and ov[low[0]] > -1e-6:
                    touching = (b, low[0], ov[low[0]])
            if ok:
                continue
            if touching is not None:
                b, m, ov_m = touching
                out.append(LintIssue(
                    "L03", a.path,
                    f"{a.label} only touches {b.label} face to face along {_AXIS_NAMES[m]} "
                    f"(overlap {ov_m:.2f} mm) in print part {key!r}, so the union is unstable",
                    "overlap the shapes by at least 0.5 mm", variant, round(ov_m, 4), OVERLAP_MIN_MM))
            else:
                out.append(LintIssue(
                    "L03", a.path,
                    f"{a.label} does not overlap any earlier add step of print part {key!r}; it would print as "
                    f"a separate piece",
                    "move it so it overlaps an earlier add by at least 0.5 mm, or put it after the step it "
                    "rests on", variant))
    return out


def _l04(insts: list[_Inst], variant: str) -> list[LintIssue]:
    out: list[LintIssue] = []
    for seq in _by_part(insts).values():
        for k, c in enumerate(seq):
            if c.mode != "cut":
                continue
            for a in seq[:k]:
                if a.mode != "add" or not _meet(a.box, c.box, _EPS):
                    continue
                for m in range(3):
                    for end, sign in ((0, "-"), (3, "+")):
                        d = abs(c.box[m + end] - a.box[m + end])
                        if d < COPLANAR_MM - 1e-9:
                            out.append(LintIssue(
                                "L04", c.path,
                                f"the {sign}{_AXIS_NAMES[m]} face of cut {c.label} is {d:.2f} mm from the same "
                                f"face of add {a.label}",
                                "the cut face coincides with an outer face; extend the cut at least 0.5 mm beyond "
                                "it (or stop it at least 0.5 mm inside)", variant, round(d, 4), COPLANAR_MM))
    return out


def _l05(insts: list[_Inst], variant: str) -> list[LintIssue]:
    out: list[LintIssue] = []
    for seq in _by_part(insts).values():
        cuts = [(k, c) for k, c in enumerate(seq) if c.mode == "cut"]
        for k, a in enumerate(seq):
            if a.mode != "add":
                continue
            for _, c in (x for x in cuts if x[0] > k):
                if _inside(a.box, c.box):
                    out.append(LintIssue(
                        "L05", a.path, f"add {a.label} lies entirely inside the later cut {c.label}; it adds nothing",
                        "remove the step, or move it after the cut", variant))
                    break
    return out


def _part_boxes(insts: list[_Inst]) -> dict[str, Box]:
    """출력 파트마다 add 상자의 합에서, 경계를 통째로 잘라 낸 cut 을 뺀 상자."""
    out: dict[str, Box] = {}
    for key, seq in _by_part(insts).items():
        u: Box | None = None
        for x in seq:
            if x.mode == "add":
                u = _union(u, x.box)
            elif u is not None:
                u = _trim(u, x.box)
        if u is not None:
            out[key] = u
    return out


def _l06(part: PartFile, compiled: CompiledPart, values: Mapping[str, object], boxes: dict[str, Box],
         variant: str) -> list[LintIssue]:
    if part.envelope is None or not boxes:
        return []
    try:
        env = compiled.geometry_env(values)
        envelope = _vec(compiled, "/envelope", env)
    except DslError:
        return []  # 계산 오류는 검증기(P4)가 다룬다
    u: Box | None = None
    for b in boxes.values():
        u = _union(u, b)
    assert u is not None
    out: list[LintIssue] = []
    for k in range(3):
        span = u[k + 3] - u[k]
        if abs(envelope[k] - span) > ENVELOPE_TOL_MM + 1e-9:
            out.append(LintIssue(
                "L06", f"/envelope/{k}",
                f"envelope {_AXIS_NAMES[k]} is {envelope[k]:g} mm but the add steps span {span:g} mm",
                "make the envelope the outer size of the part in use pose", variant,
                round(envelope[k], 4), round(span, 4)))
    return out


# ── L07: 연결 지점 ──

def _alias(part: PartFile, src: object) -> str | None:
    """식이 파라미터 이름 하나(또는 그것을 가리키는 let 사슬)면 그 파라미터 이름."""
    if not isinstance(src, str):
        return None
    lets = {x.name: x.expr for x in part.let}
    name = src.strip()
    for _ in range(len(lets) + 1):
        if name in part.params:
            return name
        if name in lets and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", lets[name].strip()):
            name = lets[name].strip()
            continue
        return None
    return None


def _l07(part: PartFile) -> list[LintIssue]:
    out: list[LintIssue] = []
    anchors = part.anchors
    names = set(anchors) | {"bottom"}
    kinds = {k: v.type for k, v in part.params.items()}

    def issue(path: str, message: str, hint: str = "") -> None:
        out.append(LintIssue("L07", path, message, hint))

    doors = [n for n, a in anchors.items() if a.door is not None]
    for name, a in anchors.items():
        base = pointer("anchors", name)
        horizontal = a.normal in HORIZONTAL
        if a.normal[1] == a.up[1]:
            issue(f"{base}/up", f"up {a.up} is not perpendicular to normal {a.normal}")
        if name in ("top", "bottom"):
            want = "+Z" if name == "top" else "-Z"
            if a.normal != want or a.up != "+Y":
                issue(base, f"anchor {name!r} must have normal {want} and up +Y",
                      f"write \"normal\": \"{want}\", \"up\": \"+Y\"")
            extra = [k for k in ("side", "wall", "door", "mount", "fields") if getattr(a, k) is not None]
            if a.openable:
                extra.append("openable")
            if a.part != "body":
                extra.append("part")
            if extra:
                issue(base, f"anchor {name!r} takes only origin, normal and up; remove {', '.join(extra)}")
            continue
        if not horizontal:
            issue(f"{base}/normal", f"anchor {name!r} has a vertical normal; v1 joins only on side faces",
                  "only the 'top' and 'bottom' anchors face up or down")
            continue
        if a.up != "+Z":
            issue(f"{base}/up", f"side anchor {name!r} must have up +Z (doors and mounts stand on the floor)")
        if a.door is not None:
            if part.role != "room_host":
                issue(f"{base}/door", f"only room_host parts have doors; this part is {part.role!r}")
            if a.side is None:
                issue(f"{base}/side", f"door anchor {name!r} needs its side",
                      f"normal {a.normal} faces {SIDE_OF_NORMAL[a.normal]!r}")
            elif a.side != SIDE_OF_NORMAL[a.normal]:
                issue(f"{base}/side", f"door anchor {name!r} has side {a.side!r} but its normal {a.normal} faces "
                                      f"{SIDE_OF_NORMAL[a.normal]!r}", f"write \"side\": \"{SIDE_OF_NORMAL[a.normal]}\"")
            if a.wall is None:
                issue(f"{base}/wall", f"door anchor {name!r} needs the wall thickness behind its face",
                      "add \"wall\": \"wall_thickness_mm\"")
        elif a.side is not None:
            issue(f"{base}/side", f"side is allowed only on door anchors; {name!r} has no door",
                  "remove side (access sides go in features.access_sides)")
        if a.openable:
            if a.door is None:
                issue(f"{base}/openable", f"openable anchor {name!r} has no door to open",
                      "declare the door (with a when that is false while closed) and an opens entry")
            if a.wall is None:
                issue(f"{base}/wall", f"openable anchor {name!r} needs a wall")
            if not any(o.anchor == name for o in part.opens):
                issue(f"{base}/openable", f"openable anchor {name!r} has no opens entry",
                      "add {\"anchor\": \"" + name + "\", \"set\": {…}} to opens")
        if a.fields is not None:
            fb = f"{base}/fields"
            for slot in ("width", "height", "wall", "port", "profile"):
                ref = getattr(a.fields, slot)
                if ref is None:
                    continue
                if ref not in kinds:
                    issue(f"{fb}/{slot}", f"fields.{slot} {ref!r} is not a param")
                elif slot == "profile" and kinds[ref] != "choice":
                    issue(f"{fb}/{slot}", f"fields.profile {ref!r} must be a choice param")
                elif slot != "profile" and kinds[ref] not in _NUMERIC:
                    issue(f"{fb}/{slot}", f"fields.{slot} {ref!r} must be a number param")
            # fields 는 그 면의 값을 정하는 파라미터다: 식이 파라미터 하나면 같아야 한다
            pairs = (("port", a.door.width if a.door else None), ("profile", a.door.profile if a.door else None),
                     ("wall", a.wall))
            for slot, src in pairs:
                ref, own = getattr(a.fields, slot), _alias(part, src)
                if ref is not None and own is not None and ref != own:
                    issue(f"{fb}/{slot}", f"fields.{slot} is {ref!r} but the anchor's {slot} comes from {own!r}",
                          f"write \"{slot}\": \"{own}\"")
            if a.fields.port is not None and a.door is None:
                issue(f"{fb}/port", f"fields.port is set but anchor {name!r} has no door")
            if a.fields.profile is not None and a.door is None:
                issue(f"{fb}/profile", f"fields.profile is set but anchor {name!r} has no door")
        if a.mount is None and a.door is None and not a.openable and name not in (part.attach_order.slide or ()):
            issue(base, f"side anchor {name!r} is not a door, a mount or a slide face",
                  "add a mount or a door, list it in attach_order.slide (accessory), or remove it")

    # attach_order
    slide = list(part.attach_order.slide or ())
    passage = list(part.attach_order.passage or ())
    for kind, seq in (("slide", slide), ("passage", passage)):
        for i, n in enumerate(seq):
            p = f"/attach_order/{kind}/{i}"
            if n not in names:
                issue(p, f"unknown anchor {n!r}", "anchors: " + ", ".join(sorted(names)))
                continue
            a = anchors.get(n)
            if kind == "slide" and (a is None or a.door is not None or a.normal not in HORIZONTAL or a.up != "+Z"):
                issue(p, f"slide anchor {n!r} must be a side face with up +Z and no door")
            if kind == "passage" and (a is None or (a.door is None and not a.openable)):
                issue(p, f"passage anchor {n!r} must be a door or openable")

    # 역할 규칙
    role = part.role
    if role == "accessory":
        if not slide:
            issue("/attach_order/slide", "an accessory needs attach_order.slide (the back faces it slides on with)")
    elif role == "host":
        if not any(a.mount is not None and a.normal in HORIZONTAL and a.up == "+Z" for a in anchors.values()):
            issue("/anchors", "a host needs at least one side mount anchor (horizontal normal, up +Z, mount)")
        for n in doors:
            issue(pointer("anchors", n, "door"), "a host has no doors")
    elif role == "room_host":
        if not doors:
            issue("/anchors", "a room_host needs at least one door anchor")
        if not passage:
            issue("/attach_order/passage", "a room_host needs attach_order.passage (the order doors are used in)")
    elif role == "none":
        for n in anchors:
            if n not in ("top", "bottom"):
                issue(pointer("anchors", n), f"a part with role 'none' has only top and bottom anchors; remove {n!r}")
    return out


def _l07_slide_geometry(part: PartFile, compiled: CompiledPart, values: Mapping[str, object],
                        boxes: dict[str, Box], variant: str) -> list[LintIssue]:
    """accessory 의 슬라이드 연결 지점: 그 파트 경계 상자의 뒷면(법선 쪽 끝) 아래 가운데."""
    if part.role != "accessory":
        return []
    out: list[LintIssue] = []
    try:
        env = compiled.geometry_env(values)
    except DslError:
        return []
    for n in part.attach_order.slide or ():
        a = part.anchors.get(n)
        if a is None or a.normal not in HORIZONTAL or a.part not in boxes:
            continue
        b = boxes[a.part]
        o = _vec(compiled, pointer("anchors", n, "origin"), env)
        k = _AXIS_INDEX[a.normal[1].lower()]
        lat = 1 - k  # 수평 법선의 옆 방향 (x ↔ y)
        want = (b[k + 3] if a.normal[0] == "+" else b[k], (b[lat] + b[lat + 3]) / 2, b[2])
        got = (o[k], o[lat], o[2])
        what = ("on the back face", "at the middle of the face", "at the bottom of the part")
        for w, g, label in zip(want, got, what):
            if abs(w - g) > ANCHOR_TOL_MM + 1e-9:
                out.append(LintIssue(
                    "L07", pointer("anchors", n, "origin"),
                    f"slide anchor {n!r} is not {label} ({g:g} vs {w:g} mm)",
                    "put the origin at the bottom centre of the flat back face", variant, round(g, 4), round(w, 4)))
    return out


# ── L08–L12: 구조 ──

_RULE_REF = re.compile(r"\brule\.([A-Za-z_][A-Za-z0-9_.]*)")


def _l08(part: PartFile, compiled: CompiledPart | None) -> list[LintIssue]:
    known = size_rule_fields()
    out: list[LintIssue] = []
    if compiled is not None:
        used: dict[str, str] = {}
        for ptr, e in compiled.exprs.items():
            for f in e.rule_fields:
                used.setdefault(f, ptr)
    else:  # 컴파일 오류: 식에서 rule. 이름만 찾는다. RULE_NAMES 밖의 이름은 L01 이 이미 알린다
        used = {}
        _scan_rule_refs(part.model_dump(mode="json", exclude_none=True), "", used)
        used = {f: p for f, p in used.items() if f in RULE_NAMES}
    for f, ptr in sorted(used.items(), key=lambda kv: kv[1]):
        if f not in known:
            out.append(LintIssue("L08", ptr, f"rule.{f} is not a SizeRules field",
                                 "rule. names come from rules/species.yaml sizes"))
    keys = typing.get_args(RuleKey)
    for i, o in enumerate(part.features.openings or ()):
        if (isinstance(o, PassageOpening) and o.rule_key is not None
                and (o.rule_key not in keys or o.rule_key not in known)):
            out.append(LintIssue("L08", f"/features/openings/{i}/rule_key",
                                 f"rule_key {o.rule_key!r} is not a SizeRules size field",
                                 "use " + " or ".join(keys)))
    return out


def _scan_rule_refs(node: object, ptr: str, used: dict[str, str]) -> None:
    if isinstance(node, str):
        for m in _RULE_REF.finditer(node):
            used.setdefault(m.group(1), ptr)
    elif isinstance(node, dict):
        for k, v in node.items():
            _scan_rule_refs(v, f"{ptr}/{pointer(k)[1:]}", used)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_rule_refs(v, f"{ptr}/{i}", used)


def _l09(part: PartFile) -> list[LintIssue]:
    out: list[LintIssue] = []
    for name, spec in part.params.items():
        base = pointer("params", name)
        if spec.type == "number" and not name.endswith(("_mm", "_deg")):
            out.append(LintIssue("L09", base, f"number param {name!r} must end in _mm (length) or _deg (angle)",
                                 f"rename it, e.g. {name}_mm"))
        elif spec.type == "integer" and not name.endswith("_count"):
            out.append(LintIssue("L09", base, f"integer param {name!r} must end in _count",
                                 f"rename it, e.g. {name}_count"))
        elif spec.type in ("choice", "bool") and name.endswith(_UNIT_SUFFIXES):
            out.append(LintIssue("L09", base, f"{spec.type} param {name!r} must not end in a unit suffix "
                                              f"({', '.join(_UNIT_SUFFIXES)})", "rename it"))
        for lang, limit in (("ko", DESC_HEAD_KO_MAX), ("en", DESC_HEAD_EN_MAX)):
            head = desc_head(getattr(spec.desc, lang)).strip()
            p = f"{base}/desc/{lang}"
            if not head:
                out.append(LintIssue("L09", p, "the first sentence of desc is empty",
                                     "start with a short name of the param, e.g. \"Wall thickness mm\""))
            elif len(head) > limit:
                out.append(LintIssue("L09", p, f"the first sentence of desc has {len(head)} characters; the limit "
                                               f"is {limit}",
                                     "the first sentence is the param's name in messages; keep it short and put "
                                     "details after a period", value=len(head), limit=limit))
    return out


def _l10(part: PartFile, stem: str | None) -> list[LintIssue]:
    out: list[LintIssue] = []
    if (part.key is None) != (part.version is None):
        out.append(LintIssue("L10", "/key", "key and version are set together (publish injects both)"))
    if part.key is not None and part.version is not None and part.key != f"{part.family}@v{part.version}":
        out.append(LintIssue("L10", "/key", f"key {part.key!r} must equal family@v<version> = "
                                            f"{part.family}@v{part.version!r}"))
    if stem is not None:
        if part.key is not None and stem != part.key:
            out.append(LintIssue("L10", "/key", f"key {part.key!r} does not match the file name {stem!r}.json",
                                 f"a published file is named {part.key}.json"))
        elif part.key is None and stem != part.family:
            out.append(LintIssue("L10", "/family", f"draft file {stem!r}.json does not match family "
                                                   f"{part.family!r}", f"name the draft {part.family}.json"))
    return out


def _l11(part: PartFile) -> list[LintIssue]:
    out: list[LintIssue] = []
    keys = [pp.key for pp in part.print]
    if keys[0] != "body":
        out.append(LintIssue("L11", "/print/0/key", f"the first print part has key {keys[0]!r}; it must be 'body'",
                             "the main body is print[0]; name it 'body'"))
    for i, k in enumerate(keys):
        if k in keys[:i]:
            out.append(LintIssue("L11", f"/print/{i}/key", f"print key {k!r} is used twice"))
    added: set[str] = set()
    used: set[str] = set()
    for i, step in enumerate(part.body):
        if step.part not in keys:
            out.append(LintIssue("L11", f"/body/{i}/part", f"unknown print part {step.part!r}",
                                 "print keys: " + ", ".join(keys)))
            continue
        used.add(step.part)
        if step.mode == "add":
            added.add(step.part)
        elif step.part not in added:
            out.append(LintIssue("L11", f"/body/{i}/mode", f"a cut before the first add of print part {step.part!r}",
                                 "start every print part with an add step", code="DSL020"))
    for i, k in enumerate(keys):
        if k not in used:
            out.append(LintIssue("L11", f"/print/{i}/key", f"print part {k!r} has no body step"))
    kinds = {k: v.type for k, v in part.params.items()}

    def numeric(ptr: str, name: str | None, what: str) -> None:
        if name is None:
            return
        if name not in kinds:
            out.append(LintIssue("L11", ptr, f"{what} {name!r} is not a param"))
        elif kinds[name] not in _NUMERIC:
            out.append(LintIssue("L11", ptr, f"{what} {name!r} must be a number param, not {kinds[name]}"))

    numeric("/height_field", part.height_field, "height_field")
    numeric("/level_field", part.level_field, "level_field")
    for i, f in enumerate(part.size_fields):
        numeric(f"/size_fields/{i}", f, "size field")
    return out


def _l12(part: PartFile) -> list[LintIssue]:
    out: list[LintIssue] = []
    known = _known_habitats()
    for i, h in enumerate(part.habitats):
        if h not in known:
            out.append(LintIssue("L12", f"/habitats/{i}", f"unknown habitat {h!r}", "habitats: " + ", ".join(known)))
        elif h not in V1_HABITATS:
            out.append(LintIssue("L12", f"/habitats/{i}", f"habitat {h!r} is not supported by DSL v1",
                                 "v1 parts are for cages only"))
    if part.role not in V1_ROLES:
        out.append(LintIssue("L12", "/role", f"role {part.role!r} is not allowed in DSL v1",
                             "roles: " + ", ".join(V1_ROLES)))
    return out


# ── 진입점 ──

def lint(data: Mapping[str, Any] | PartFile, *, stem: str | None = None, context: LintContext | None = None,
         rules: object | None = None, use_rules: bool = True) -> LintReport:
    """부품 파일(초안 또는 게시 파일) 하나의 정적 검사 L01–L12.

    data: JSON 을 읽은 dict 또는 schema.PartFile. dict 가 스키마(S01)에 맞지 않으면 DslErrors 를 낸다 (린트는 스키마를
    통과한 파일에만 뜻이 있다). stem: 파일 이름에서 .json 을 뺀 것 (주면 L10 이 이름을 확인한다).
    context: rule_default·제약을 계산할 규칙 문맥. 주지 않으면 rules(RuleBook, 없으면 rules/ 를 읽음)의 첫 맞는 종·크기.
    use_rules=False 면 규칙 없이 파일에 적힌 기본값만 쓴다."""
    part = data if isinstance(data, PartFile) else parse_part(data)
    issues: list[LintIssue] = []
    compiled: CompiledPart | None
    try:
        compiled = compile_part(part)
    except DslError as err:
        compiled = None
        issues += _expr_issues(err)
    issues += _l07(part)
    issues += _l08(part, compiled)
    issues += _l09(part)
    issues += _l10(part, stem)
    issues += _l11(part)
    issues += _l12(part)

    ctx = context
    if ctx is None and use_rules:
        ctx = context_for(part.habitats, rules)
    variants: list[str] = []
    skipped: list[LintSkip] = []
    structural_ok = not any(i.id == "L11" for i in issues)
    if compiled is not None and structural_ok:
        cases, skipped = _variants(part, compiled, ctx)
        seen: set[tuple] = set()
        for n, (vid, values) in enumerate(cases):
            try:
                insts = _instances(part, compiled, values)
            except _VariantError as e:
                skipped.append(LintSkip(vid, e.error))
                continue
            variants.append(vid)
            shape = tuple((x.step, x.part, x.mode, x.box) for x in insts)
            if n > 0 and shape in seen:
                continue  # 형상이 앞 변형과 같다 (형상에 쓰지 않는 파라미터만 바뀜): 같은 결과
            seen.add(shape)
            cut_first = _cut_before_add(insts, vid)
            if cut_first:
                issues += cut_first
                continue
            issues += _l03(insts, vid) + _l04(insts, vid) + _l05(insts, vid)
            if n == 0:
                boxes = _part_boxes(insts)
                issues += _l06(part, compiled, values, boxes, vid)
                issues += _l07_slide_geometry(part, compiled, values, boxes, vid)
    return LintReport(_sorted_unique(issues), tuple(variants), tuple(skipped), ctx.case if ctx else None)


def _cut_before_add(insts: list[_Inst], variant: str) -> list[LintIssue]:
    """변형에서 add 가 모두 꺼져(when) 첫 단계가 cut 이 된 파트 (DslTemplate 이 DSL020 으로 멈춘다)."""
    out: list[LintIssue] = []
    for key, seq in _by_part(insts).items():
        if seq and seq[0].mode == "cut":
            out.append(LintIssue("L11", f"{seq[0].path}/mode",
                                 f"in this variant the first active step of print part {key!r} is a cut",
                                 "make sure an add step of this print part is always active", variant,
                                 code="DSL020"))
    return out


def _sorted_unique(issues: list[LintIssue]) -> tuple[LintIssue, ...]:
    """같은 (id, 경로, 메시지) 는 처음 것만 (여러 변형에서 같은 문제가 되풀이되지 않게). id 순, 같은 id 안에서는 나온 순."""
    seen: set[tuple[str, str, str]] = set()
    out: list[LintIssue] = []
    for i in issues:
        k = (i.id, i.path, i.message)
        if k in seen:
            continue
        seen.add(k)
        out.append(i)
    order = {lid: n for n, lid in enumerate(LINT_IDS)}
    return tuple(sorted(out, key=lambda i: order.get(i.id, len(order))))


def lint_file(path: str | Path, **kwargs: Any) -> LintReport:
    """파일 하나를 읽어 lint (파일 이름으로 L10 을 확인한다). JSON·스키마 오류는 DslErrors."""
    p = Path(path)
    part = load_part_json(p.read_bytes())
    return lint(part, stem=p.stem, **kwargs)


def main(argv: list[str] | None = None) -> int:
    """python -m app.library.lint FILE… (개발용; 작성 흐름은 python -m app.library check)."""
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python -m app.library.lint FILE.json [...]", file=sys.stderr)
        return 2
    code = 0
    for a in args:
        try:
            report = lint_file(a)
        except DslError as err:
            print(f"{a}: schema\n{err}")
            code = 1
            continue
        print(f"{a}: {report.text()}")
        for s in report.skipped:
            print(f"  skipped {s.variant}: {s.error}")
        if not report.ok:
            code = 1
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
