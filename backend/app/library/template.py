"""Part DSL 부품 → Template (설계 §5.5–§5.9).

게시된 부품 파일(app/library/parts/<family>@v<N>.json) 하나가 DslTemplate 인스턴스 하나가 된다. 코드 부품과 같은
Template API(Params, constraints, build, anchors, features …)를 내므로 엔진·조립 해석기·LLM 스키마가 둘을 가리지 않는다.

- load_library(): 색인(index.json)의 모든 부품(활성·폐기·차단, R7)을 key 순으로 읽는다. 파일 sha256(R3), 스키마,
  식 컴파일, 구조 규칙 중 하나라도 어긋나면 LibraryError 로 멈춘다 (R8, fail fast).
- make_template(data, key=…): 초안(draft)이나 게시 파일 하나로 템플릿을 만든다 (검증기·미리보기·시험).
- 형상(build)은 파라미터만의 순수 함수다: 식의 geometry 범위는 rule.·ctx. 를 읽지 못한다 (R4).

무거운 모듈이다 (build123d: app.library.ops, app.templates.base).
"""

from __future__ import annotations

import copy
import math
import sys
import threading
from collections import OrderedDict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

import numpy as np
from build123d import Part
from pydantic import Field, ValidationError, create_model

from app.library import index, ops
from app.library.errors import DslError, DslErrors, pointer
from app.library.expr import CompiledPart, compile_part, rule_ctx_bindings
from app.library.index import DEFAULT_COLOR, LibraryError, parse_key
from app.library.schema import (
    BoxStep,
    ChoiceParam,
    CylinderStep,
    IntegerParam,
    NumberParam,
    PartFile,
    PassageStep,
    PrismStep,
    VentOpening,
    parse_part,
)
from app.templates.base import (
    Anchor,
    FaceFields,
    Features,
    Opening,
    ParamConstraint,
    PrintPart,
    RuleContext,
    Template,
    TemplateParams,
    cutter_at,
)

# 출입구 이름 (코드 은신처의 이름과 같은 한국어라 영어 카탈로그에 이미 있다)
DOOR_LABEL_KO: dict[str, str] = {"front": "앞 출입구", "back": "뒤 출입구", "left": "왼쪽 출입구", "right": "오른쪽 출입구"}
ROTATIONS = ops.ROTATIONS
# 형상 기억: 템플릿마다 최근 파라미터 이만큼 (build_item 이 build 뒤에 print_parts(built=) 를 부른다)
BUILD_CACHE_SIZE = 8
# repeat 의 반복 횟수 한도 (변수 하나, 두 변수의 곱)
REPEAT_MAX = 64
# 반복을 펼친 고체 수 한도 (부품 하나, 모든 단계). 정적 검사 S07 이 필드 범위 전체에서 막고, 만들 때도 다시 막는다
SOLIDS_MAX = 512
_AUTO_BOTTOM = Anchor((0.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))
_NUMERIC = ("number", "integer")


def camel(family: str) -> str:
    """'tunnel_junction' → 'TunnelJunction' (클래스 이름)."""
    return "".join(w[:1].upper() + w[1:] for w in family.split("_") if w)


def next_key(family: str) -> str:
    """초안을 게시할 때 받을 key: 그 family 의 게시된 가장 높은 버전 + 1."""
    versions = [e.version for e in index.entries().values() if e.family == family]
    return f"{family}@v{max(versions, default=0) + 1}"


# ── 파라미터 모델 ──

def params_model(part: PartFile, class_name: str) -> type[TemplateParams]:
    """파일의 params → pydantic 모델 (평평한 필드만). number → float, integer → int, choice → Literal, bool → bool.
    필드마다 Field(기본값, ge=min, le=max, description=desc.ko). 클래스 이름이 부품마다 달라 LLM 스키마의 $defs 가
    겹치지 않는다."""
    fields: dict[str, Any] = {}
    for name, spec in part.params.items():
        desc = spec.desc.ko
        if isinstance(spec, NumberParam):
            fields[name] = (float, Field(float(spec.default), ge=float(spec.min), le=float(spec.max), description=desc))
        elif isinstance(spec, IntegerParam):
            fields[name] = (int, Field(int(spec.default), ge=int(spec.min), le=int(spec.max), description=desc))
        elif isinstance(spec, ChoiceParam):
            fields[name] = (Literal[tuple(spec.choices)], Field(spec.default, description=desc))  # type: ignore[valid-type]
        else:
            fields[name] = (bool, Field(bool(spec.default), description=desc))
    return create_model(class_name, __base__=TemplateParams, __module__=__name__, **fields)


# ── 구조 검사 (템플릿이 동작하는 데 꼭 필요한 것만; 전체 정적 검사 S01–S08 은 검증기 몫) ──

def structure_errors(part: PartFile) -> list[DslError]:
    """DslTemplate 이 동작하는 데 꼭 필요한 구조 규칙 (읽을 때 확인한다, fail fast). 정적 검사(S03·S04·L07·L11)의
    일부라 검증기가 그대로 써도 된다. 오류 목록 (없으면 [])."""
    errs: list[DslError] = []
    params = part.params
    kinds = {k: v.type for k, v in params.items()}
    print_keys = [pp.key for pp in part.print]
    if print_keys[0] != "body":
        errs.append(DslError("DSL010", "/print/0/key", "the first print part must have key 'body'",
                             "the main body is print[0]; name it 'body'"))
    for i, k in enumerate(print_keys):
        if k in print_keys[:i]:
            errs.append(DslError("DSL010", f"/print/{i}/key", f"print key {k!r} is used twice"))
    if "wall_thickness_mm" not in params or kinds["wall_thickness_mm"] != "number":
        errs.append(DslError("DSL011", "/params/wall_thickness_mm", "a number param 'wall_thickness_mm' is required",
                             "every part declares its wall thickness (min >= 1.0, max <= 8)"))

    def need_param(ptr: str, name: str | None, numeric: bool) -> None:
        if name is None:
            return
        if name not in params:
            errs.append(DslError("DSL002", ptr, f"unknown param {name!r}"))
        elif numeric and kinds[name] not in _NUMERIC:
            errs.append(DslError("DSL003", ptr, f"param {name!r} must be a number or integer"))

    need_param("/height_field", part.height_field, True)
    need_param("/level_field", part.level_field, True)
    for i, f in enumerate(part.size_fields):
        need_param(f"/size_fields/{i}", f, True)
    for i, f in enumerate(part.door_fields):
        need_param(f"/door_fields/{i}", f, False)
    for i, c in enumerate(part.constraints):
        need_param(f"/constraints/{i}/field", c.field, True)

    # 단계: 출력 파트, 파트마다 첫 단계는 add (DSL020), 구멍 이름이 가리키는 단계
    added: set[str] = set()
    used: set[str] = set()
    step_ids: dict[str, int] = {}
    for i, step in enumerate(part.body):
        used.add(step.part)
        if step.part not in print_keys:
            errs.append(DslError("DSL002", f"/body/{i}/part", f"unknown print part {step.part!r}",
                                 f"declare it in print[]; print keys: {', '.join(print_keys)}"))
        if step.mode == "add":
            added.add(step.part)
        elif step.part not in added:
            errs.append(DslError("DSL020", f"/body/{i}/mode", f"a cut before the first add of print part {step.part!r}",
                                 "start every print part with an add step"))
        if step.id is not None:
            if step.id in step_ids:
                errs.append(DslError("DSL010", f"/body/{i}/id", f"step id {step.id!r} is used twice"))
            step_ids.setdefault(step.id, i)
    for n, k in enumerate(print_keys):
        if k not in used:
            errs.append(DslError("DSL011", f"/print/{n}/key", f"print part {k!r} has no body step"))

    # 연결 지점
    names = set(part.anchors) | {"bottom"}
    for name, a in part.anchors.items():
        base = pointer("anchors", name)
        if a.part not in print_keys:
            errs.append(DslError("DSL002", f"{base}/part", f"unknown print part {a.part!r}"))
        if abs(float(np.dot(ops.AXES[a.normal], ops.AXES[a.up]))) > 1e-9:
            errs.append(DslError("DSL010", f"{base}/up", f"up {a.up} is not perpendicular to normal {a.normal}"))
        if a.door is not None and a.side is None:
            errs.append(DslError("DSL011", f"{base}/side", "a door anchor needs its side (front, back, left, right)"))
        if a.door is not None and a.wall is None:
            errs.append(DslError("DSL011", f"{base}/wall", "a door anchor needs the wall thickness behind its face",
                                 "add \"wall\": \"wall_thickness_mm\" (or the wall expression)"))
        if a.openable and a.wall is None:
            errs.append(DslError("DSL011", f"{base}/wall", "an openable anchor needs a wall"))
        if a.fields is not None:
            for fname in ("width", "height", "wall", "port"):
                need_param(f"{base}/fields/{fname}", getattr(a.fields, fname), True)
            need_param(f"{base}/fields/profile", a.fields.profile, False)
    for kind in ("slide", "passage"):
        for i, n in enumerate(getattr(part.attach_order, kind) or ()):
            if n not in names:
                errs.append(DslError("DSL002", f"/attach_order/{kind}/{i}", f"unknown anchor {n!r}"))
    for i, o in enumerate(part.opens):
        if o.anchor not in part.anchors:
            errs.append(DslError("DSL002", f"/opens/{i}/anchor", f"unknown anchor {o.anchor!r}"))
        elif part.anchors[o.anchor].door is None:
            errs.append(DslError("DSL010", f"/opens/{i}/anchor", f"anchor {o.anchor!r} has no door to open"))

    # 특징의 환기구·창: 자르는 상자·원기둥·통로 단계 (크기는 그 단계에서 구한다)
    for i, o in enumerate(part.features.openings or ()):
        if not isinstance(o, VentOpening):
            continue
        ptr = f"/features/openings/{i}"
        idx = step_ids.get(o.step)
        if idx is None:
            errs.append(DslError("DSL002", f"{ptr}/step", f"unknown step id {o.step!r}"))
            continue
        step = part.body[idx]
        if step.mode != "cut" or isinstance(step, PrismStep):
            errs.append(DslError("DSL010", f"{ptr}/step", f"step {o.step!r} must be a box, cylinder or passage cut"))
        elif isinstance(step, BoxStep) and o.axis is None:
            errs.append(DslError("DSL011", f"{ptr}/axis", "a box vent needs its axis (the direction of the hole)"))

    if part.role != "none" and part.envelope is None:
        errs.append(DslError("DSL011", "/envelope", "envelope is required unless role is 'none'"))
    return errs


# ── 계산한 연결 지점 ──

@dataclass(frozen=True)
class _Solids:
    """한 파라미터의 형상 (기억한 것; 바꾸지 않는다). parts: 출력 파트 key → 사용 자세 형상, union: 모든 파트의 합."""

    parts: dict[str, Part]
    union: Part


@dataclass(frozen=True)
class _AnchorState:
    anchor: Anchor
    part: str
    door: bool  # 출입구가 열려 있는지 (door.when 참)
    width: float | None = None
    profile: str | None = None
    wall: float | None = None


class DslTemplate(Template):
    """DSL 부품 파일 하나의 템플릿. make_template 이 부품마다 하위 클래스(Lib<Family>V<N>)를 만들어 인스턴스 하나를 낸다.
    읽은 뒤에는 바꾸지 않는다 (여러 스레드에서 함께 쓴다; 형상 기억만 잠금으로 지킨다)."""

    part_file: ClassVar[PartFile]
    compiled: ClassVar[CompiledPart]
    door_fields: ClassVar[tuple[str, ...]] = ()
    legacy_defaults: ClassVar[dict[str, object]] = {}
    standalone = True
    cutter = False

    def __init__(self, status: str = "active") -> None:
        # 폐기·차단 상태 (인스턴스 속성: base.py 를 바꾸지 않고 getattr 로 읽는다, R1)
        self.status = status
        self.retired = status in ("retired", "blocked")
        self.blocked = status == "blocked"
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, _Solids] = OrderedDict()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.key} ({self.status})>"

    # ── 식 계산 ──

    def _expr(self, ptr: str, env: Mapping[str, object]) -> object:
        return self.compiled[ptr].evaluate(env)

    def _num(self, ptr: str, env: Mapping[str, object], default: float = 0.0) -> float:
        e = self.compiled.get(ptr)
        return default if e is None else float(e.evaluate(env))  # type: ignore[arg-type]

    def _vec(self, ptr: str, env: Mapping[str, object]) -> tuple[float, float, float]:
        return (self._num(f"{ptr}/0", env), self._num(f"{ptr}/1", env), self._num(f"{ptr}/2", env))

    def _when(self, ptr: str, env: Mapping[str, object]) -> bool:
        e = self.compiled.get(ptr)
        return True if e is None else bool(e.evaluate(env))

    def _geo(self, p: TemplateParams) -> dict[str, object]:
        return self.compiled.geometry_env(p.model_dump())

    def _rule(self, p: TemplateParams, ctx: RuleContext) -> dict[str, object]:
        return self.compiled.rule_env(p.model_dump(), rule_ctx_bindings(ctx))

    def _bindings(self, idx: int, env: Mapping[str, object]) -> Iterator[dict[str, object]]:
        """body[idx] 의 반복 변수 값마다 (i 바깥, j 안쪽) env 사본. when 이 거짓인 것은 뺀다."""
        step = self.part_file.body[idx]
        base = pointer("body", idx)
        counts: dict[str, int] = {}
        for v in sorted(step.repeat or {}):
            raw = self._num(f"{base}/repeat/{v}", env)
            n = round(raw)
            if abs(raw - n) > 1e-9 or not 0 <= n <= REPEAT_MAX:
                raise DslError("DSL006", f"{base}/repeat/{v}",
                               f"repeat count {v} = {raw:g} must be a whole number in 0..{REPEAT_MAX}")
            counts[v] = n
        if math.prod(counts.values()) > REPEAT_MAX:
            raise DslError("DSL006", f"{base}/repeat", f"repeat makes {math.prod(counts.values())} copies; "
                                                       f"the limit is {REPEAT_MAX}")
        ni, nj = counts.get("i", 1), counts.get("j", 1)
        for i in range(ni):
            for j in range(nj):
                e = dict(env)
                if "i" in counts:
                    e["i"] = i
                if "j" in counts:
                    e["j"] = j
                if self._when(f"{base}/when", e):
                    yield e

    def _step_args(self, idx: int, env: Mapping[str, object]) -> dict[str, object]:
        step = self.part_file.body[idx]
        base = pointer("body", idx)
        args: dict[str, object] = {"at": self._vec(f"{base}/at", env)}
        if isinstance(step, BoxStep):
            args.update(size=self._vec(f"{base}/size", env), align=step.align)
        elif isinstance(step, CylinderStep):
            args.update(r=self._num(f"{base}/r", env), h=self._num(f"{base}/h", env), axis=step.axis,
                        align=step.align)
        elif isinstance(step, PrismStep):
            pts = [(self._num(f"{base}/points/{k}/0", env), self._num(f"{base}/points/{k}/1", env))
                   for k in range(len(step.points))]
            args.update(plane=step.plane, points=pts, depth=self._num(f"{base}/depth", env))
        elif isinstance(step, PassageStep):
            args.update(shape=str(self._expr(f"{base}/shape", env)), width=self._num(f"{base}/width", env),
                        axis=step.axis, length=self._num(f"{base}/length", env))
        return args

    # ── 연결 지점 ──

    def _anchor_states(self, p: TemplateParams, env: Mapping[str, object] | None = None) -> dict[str, _AnchorState]:
        env = self._geo(p) if env is None else env
        out: dict[str, _AnchorState] = {}
        for name, a in self.part_file.anchors.items():
            base = pointer("anchors", name)
            origin = self._vec(f"{base}/origin", env)
            normal, up = ops.AXES[a.normal], ops.AXES[a.up]
            wall = self._num(f"{base}/wall", env) if a.wall is not None else None
            door = a.door is not None and self._when(f"{base}/door/when", env)
            if door:
                width = self._num(f"{base}/door/width", env)
                profile = str(self._expr(f"{base}/door/profile", env))
                anchor = Anchor(origin, normal, up, side=a.side, port=width, wall_mm=wall,
                                profile=profile)  # type: ignore[arg-type]
                out[name] = _AnchorState(anchor, a.part, True, width, profile, wall)
                continue
            mount = self._vec(f"{base}/mount", env) if a.mount is not None else None
            anchor = Anchor(origin, normal, up, wall_mm=wall if a.openable else None, mount=mount)
            out[name] = _AnchorState(anchor, a.part, False, wall=wall if a.openable else None)
        if "bottom" not in out:
            out["bottom"] = _AnchorState(_AUTO_BOTTOM, "body", False)
        return out

    def anchors(self, p: TemplateParams) -> dict[str, Anchor]:
        return {k: s.anchor for k, s in self._anchor_states(p).items()}

    def face_fields(self, p: TemplateParams, anchor: str) -> FaceFields:
        a = self.part_file.anchors.get(anchor)
        if a is None or a.fields is None:
            return FaceFields()
        st = self._anchor_states(p)[anchor]
        f = a.fields
        return FaceFields(width=f.width, height=f.height,
                          wall=f.wall if st.anchor.wall_mm is not None else None,
                          port=f.port if st.door else None, profile=f.profile if st.door else None)

    def open_port(self, p: TemplateParams, anchor: str) -> TemplateParams | None:
        """출입구가 열린 자리면 p. 아니면 그 자리의 opens 항목 중 when 이 참인 첫 것의 set 을 적용한 파라미터
        (그 결과 출입구가 열려야 한다). 없거나 맞지 않으면 None."""
        if anchor not in self.part_file.anchors:
            return None
        env = self._geo(p)
        if self._anchor_states(p, env)[anchor].door:
            return p
        for idx, o in enumerate(self.part_file.opens):
            if o.anchor != anchor:
                continue
            base = pointer("opens", idx)
            if not self._when(f"{base}/when", env):
                continue
            update: dict[str, object] = {}
            for k in o.set:
                v = self._expr(f"{base}/set/{pointer(k)[1:]}", env)
                if isinstance(self.part_file.params[k], IntegerParam) and isinstance(v, float) and v.is_integer():
                    v = int(v)
                update[k] = v
            try:
                q = self.Params.model_validate({**p.model_dump(), **update})
            except ValidationError:
                return None
            return q if self._anchor_states(q)[anchor].door else None
        return None

    def _door_profile(self, st: _AnchorState):
        assert st.width is not None and st.profile is not None
        return ops.passage_profile(st.profile, st.width, st.wall or 0.0)

    def port_profile(self, p: TemplateParams, anchor: str):
        st = self._anchor_states(p).get(anchor)
        if st is None or not st.door:
            return None
        return self._door_profile(st)

    def port_cutter(self, p: TemplateParams, anchor: str, depth_mm: float) -> Part | None:
        st = self._anchor_states(p).get(anchor)
        if st is None or not st.door:
            return None
        return cutter_at(st.anchor, self._door_profile(st), depth_mm)

    # ── 형상 ──

    def _solids(self, p: TemplateParams) -> _Solids:
        """이 파라미터의 형상 (최근 BUILD_CACHE_SIZE 개를 기억한다). 돌려준 형상을 바꾸지 말 것: 밖으로는 사본을 준다."""
        key = p.model_dump_json()
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        out = self._make_solids(p)
        with self._lock:
            self._cache[key] = out
            while len(self._cache) > BUILD_CACHE_SIZE:
                self._cache.popitem(last=False)
        return out

    def _make_solids(self, p: TemplateParams) -> _Solids:
        env = self._geo(p)
        solids: dict[str, Part | None] = {pp.key: None for pp in self.part_file.print}
        plan = [(idx, step, list(self._bindings(idx, env))) for idx, step in enumerate(self.part_file.body)]
        count = sum(len(b) for _, _, b in plan)
        if count > SOLIDS_MAX:
            raise DslError("DSL006", "/body", f"these params make {count} solids after repeat expansion; "
                                              f"the limit is {SOLIDS_MAX}", "use fewer repeats")
        for idx, step, bindings in plan:
            base = pointer("body", idx)
            for e in bindings:
                s = ops.make(step.op, self._step_args(idx, e), base)
                cur = solids[step.part]
                if step.mode == "add":
                    solids[step.part] = s if cur is None else cur + s
                elif cur is None:
                    raise DslError("DSL020", f"{base}/mode", f"a cut before the first add of print part "
                                                             f"{step.part!r} (the earlier add steps were skipped)",
                                   "make sure an add step of this print part is always active")
                else:
                    solids[step.part] = cur - s
        parts: dict[str, Part] = {}
        for k, s in solids.items():
            if s is None:
                raise DslError("DSL006", "/body", f"print part {k!r} has no solid for these params",
                               "every print part needs at least one active add step")
            parts[k] = s
        # 열린 출입구를 그 연결 지점이 속한 파트의 벽에서 자른다 (그 파트의 모든 단계 뒤)
        for st in self._anchor_states(p, env).values():
            if st.door:
                assert st.width is not None and st.profile is not None and st.wall is not None
                parts[st.part] = parts[st.part] - ops.door_cutter(st.anchor, st.profile, st.width, st.wall)
        union: Part | None = None
        for s in parts.values():
            union = s if union is None else union + s
        assert union is not None
        return _Solids(parts, union)

    def build(self, p: TemplateParams) -> Part:
        """모든 출력 파트의 합 (사용 자세). 파트가 하나면 그 파트 형상. 부를 때마다 새 사본을 준다."""
        return copy.deepcopy(self._solids(p).union)

    def print_rotation(self, p: TemplateParams) -> np.ndarray:
        return ROTATIONS[self.part_file.print[0].rotation].copy()

    def print_parts(self, p: TemplateParams, built: Part | None = None) -> list[PrintPart]:
        pp = self.part_file.print
        if len(pp) == 1:
            solid = built if built is not None else self.build(p)
            return [PrintPart(pp[0].name.ko, solid, ROTATIONS[pp[0].rotation].copy(), pp[0].key)]
        solids = self._solids(p).parts
        return [PrintPart(x.name.ko, copy.deepcopy(solids[x.key]), ROTATIONS[x.rotation].copy(), x.key) for x in pp]

    def envelope(self, p: TemplateParams) -> tuple[float, float, float]:
        if self.part_file.envelope is None:
            return super().envelope(p)
        return self._vec("/envelope", self._geo(p))

    def face_needs(self, p: TemplateParams) -> tuple[float | None, float | None]:
        fn = self.part_file.face_needs
        if fn is None:
            return (None, None)
        env = self._geo(p)
        return (self._num("/face_needs/min", env) if fn.min is not None else None,
                self._num("/face_needs/max", env) if fn.max is not None else None)

    # ── 규칙 ──

    def default_params(self, ctx: RuleContext | None = None) -> TemplateParams:
        """기본값. ctx 가 있으면 rule_default 를 파라미터 차례대로(앞의 값을 반영해) 계산하고, 정수는 반올림(0.5 올림),
        필드 범위로 자른다."""
        if ctx is None:
            return self.Params()
        values: dict[str, object] = self.Params().model_dump()
        bindings = rule_ctx_bindings(ctx)
        for name, spec in self.part_file.params.items():
            if not isinstance(spec, (NumberParam, IntegerParam)) or spec.rule_default is None:
                continue
            v = float(self._expr(pointer("params", name, "rule_default"), {**values, **bindings}))  # type: ignore[arg-type]
            v = min(max(v, float(spec.min)), float(spec.max))
            values[name] = math.floor(v + 0.5) if isinstance(spec, IntegerParam) else v
        return self.Params.model_validate(values)

    def constraints(self, p: TemplateParams, ctx: RuleContext) -> list[ParamConstraint]:
        """벽 두께 공통 제약 + 파일의 제약 중 when 이 참인 것. 까닭의 {0} 은 경계값(0.1 단위로 반올림해 :g),
        {1} 은 크기 구분 이름."""
        env = self._rule(p, ctx)
        out = [ctx.wall_thickness_constraint()]
        for i, c in enumerate(self.part_file.constraints):
            base = pointer("constraints", i)
            if not self._when(f"{base}/when", env):
                continue
            which = "min" if c.min is not None else "max"
            bound = self._num(f"{base}/{which}", env)
            # 경계값은 0.1mm 까지 (계산한 경계 76.2824 → "76.3"): 보정 문구에 긴 소수가 나오지 않게
            reason = c.reason.ko.replace("{0}", f"{round(bound, 1):g}").replace("{1}", ctx.size.display_name)
            out.append(ParamConstraint(c.field, source=c.source, reason_ko=reason, blocking=c.blocking,
                                       **{which: bound}))
        return out

    def rule_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        if not self.part_file.checks:
            return []
        env = self._rule(p, ctx)
        return [c.message.ko for i, c in enumerate(self.part_file.checks)
                if bool(self._expr(pointer("checks", i, "fail_if"), env))]

    # ── 특징 ──

    def _vent_size(self, idx: int, axis: str | None, env: Mapping[str, object]) -> float | None:
        """구멍 단계 body[idx] 에서 구한 크기 (원기둥 2r, 상자 axis 에 수직인 두 변 중 작은 것, 통로 폭).
        그 단계가 하나도 만들어지지 않으면 None."""
        step = self.part_file.body[idx]
        for e in self._bindings(idx, env):
            args = self._step_args(idx, e)
            if isinstance(step, CylinderStep):
                return 2 * float(args["r"])  # type: ignore[arg-type]
            if isinstance(step, PassageStep):
                return float(args["width"])  # type: ignore[arg-type]
            size = args["size"]
            k = "xyz".index(axis or "z")
            return min(float(v) for n, v in enumerate(size) if n != k)  # type: ignore[union-attr]
        return None

    def features(self, p: TemplateParams) -> Features:
        f = self.part_file.features
        env = self._geo(p)
        states = self._anchor_states(p, env)
        openings: list[Opening] = []
        sides: list[str] = []
        doors = 0
        for name, a in self.part_file.anchors.items():
            st = states[name]
            if not st.door:
                continue
            doors += 1
            assert st.width is not None and a.side is not None
            openings.append(Opening("passage", st.width, DOOR_LABEL_KO[a.side], rule_key="entrance_min_diameter_mm"))
            sides.append(a.side)
        step_ids = {s.id: i for i, s in enumerate(self.part_file.body) if s.id is not None}
        for i, o in enumerate(f.openings or ()):
            base = f"/features/openings/{i}"
            if not self._when(f"{base}/when", env):
                continue
            if isinstance(o, VentOpening):
                size = self._vent_size(step_ids[o.step], o.axis, env)
                if size is not None:
                    openings.append(Opening(o.kind, size, o.label.ko))
            else:
                openings.append(Opening("passage", self._num(f"{base}/size", env), o.label.ko, rule_key=o.rule_key))
        for i, s in enumerate(f.access_sides or ()):
            if self._when(f"/features/access_sides/{i}/when", env):
                sides.append(s.side)

        def opt(name: str) -> float | None:
            return self._num(f"/features/{name}", env) if getattr(f, name) is not None else None

        return Features(
            min_wall_thickness_mm=(self._num("/features/min_wall", env) if f.min_wall is not None
                                   else float(env["wall_thickness_mm"])),  # type: ignore[arg-type]
            openings=tuple(openings),
            access_sides=tuple(dict.fromkeys(sides)),  # type: ignore[arg-type]
            climb_height_mm=opt("climb_height"),
            slope_deg=opt("slope_deg"),
            step_height_mm=opt("step_height"),
            entrance_count=doors if self.role == "room_host" else None,
            extra={},
        )


# ── 만들기·읽기 ──

def make_template(data: Mapping[str, Any] | PartFile, *, key: str | None = None, status: str = "active",
                  published: bool = False) -> DslTemplate:
    """부품 파일(dict 또는 PartFile) 하나 → 템플릿. 초안은 key 를 주거나(검증기) 다음 버전 key(next_key)를 받는다.
    published=True 면 게시 파일 규칙(key·version 필수, key 가 파일 이름 = key 인자와 같음)을 더한다.
    오류는 DslErrors (스키마, 식, 구조)."""
    part = data if isinstance(data, PartFile) else parse_part(data, published=published,
                                                                stem=key if published else None)
    if published and part.key is None:
        raise DslErrors.of([DslError("DSL014", "/key", "a published file needs key and version")])
    if part.key is not None and key is not None and part.key != key:
        raise DslErrors.of([DslError("DSL014", "/key", f"file key {part.key!r} does not match {key!r}")])
    key = part.key or key or next_key(part.family)
    parsed = parse_key(key)
    if parsed is None or parsed[0] != part.family:
        raise DslErrors.of([DslError("DSL014", "/key", f"key {key!r} is not {part.family}@v<N>")])
    compiled = compile_part(part)
    errs = structure_errors(part)
    if errs:
        raise DslErrors.of(errs)
    version = parsed[1]
    cls_name = f"Lib{camel(part.family)}V{version}"
    params_cls = params_model(part, f"{cls_name}Params")
    attach = {k: tuple(v) for k in ("slide", "passage") if (v := getattr(part.attach_order, k))}
    ns: dict[str, Any] = {
        "__module__": __name__,
        "__doc__": part.description.en,
        "key": key,
        "display_name_ko": part.name.ko,
        "description_ko": part.description.ko,
        "color": part.color or DEFAULT_COLOR,
        "Params": params_cls,
        "height_field": part.height_field,
        "size_fields": tuple(part.size_fields),
        "role": part.role,
        "attach_order": attach,
        "passes_access": part.passes_access,
        "level_field": part.level_field,
        "door_fields": tuple(part.door_fields),
        "part_file": part,
        "compiled": compiled,
    }
    cls = type(cls_name, (DslTemplate,), ns)
    # 프로세스 사이로 파라미터·템플릿을 넘길 수 있게 모듈 이름으로 찾을 수 있게 둔다 (같은 이름이면 나중 것)
    mod = sys.modules[__name__]
    setattr(mod, cls_name, cls)
    setattr(mod, params_cls.__name__, params_cls)
    return cls(status)


def load_library() -> dict[str, Template]:
    """색인의 모든 부품(활성·폐기·차단) → key 순 {key: 템플릿}. 하나라도 읽지 못하면 LibraryError (fail fast, R8)."""
    out: dict[str, Template] = {}
    for key, e in index.entries().items():
        try:
            t = make_template(index.read_part(key), key=key, status=e.status, published=True)
        except DslError as err:
            raise LibraryError(f"{key}: the published part file is invalid: {err}") from err
        if t.role != e.role or list(t.part_file.habitats) != list(e.habitats):
            raise LibraryError(f"{key}: role/habitats in the file ({t.role}, {t.part_file.habitats}) differ from "
                               f"the index ({e.role}, {e.habitats})")
        out[key] = t
    return out
