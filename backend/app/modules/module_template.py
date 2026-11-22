"""조립 모듈을 템플릿처럼 쓰게 하는 어댑터.

엔진(보정·배치·검증·저장·내려받기)은 템플릿만 안다. 모듈 하나를 템플릿 하나로 감싸면
  - Params: 모듈이 드러낸 파라미터 (LLM 이 정한다)
  - constraints: 부품의 종별·출력 제약을 묶인 관계(scale·offset)로 모듈 파라미터 제약으로 되돌린 것 + 모듈 limits
    (자식 부품이 부모 면 안에 들어가게 하는 모듈 파라미터끼리의 관계)
  - build: 부품을 조립한 형상
  - features: 부품 특징을 합친 것 (출입 면·출입구 수·통로 크기 등)
  - print_parts / print_rotation: 부품끼리 붙은 본체는 여섯 방향으로 눕혀 보고 서포트가 가장 적은 자세로,
    부품이 따로 출력하는 파트(집의 지붕 뚜껑 등)는 그 부품이 정한 자세 그대로.
    슬라이드 결합(mount="slide")·끼움 결합(mount="plug")이 있으면 한 덩어리로 붙은 부품 묶음마다 출력 파트 하나 (연결판의
    도브테일 홈·자식의 도브테일 혀, 끼움 구멍의 틈새·아래를 보는 끼움 턱 둘레 깔때기는 출력 파트에만 있다).
    홈·혀가 있는 묶음은 도브테일이 세로로 서는 두 자세(사용·뒤집기) 중에서 고른다
  - rule_issues: 부품 규칙 + 자동 보정으로 맞출 수 없는 limits + 조립 규칙(끼움 결합 포함) + 형상 검사 (통로가 출입구를
    다 덮는지(끼움 결합은 넓힌 구멍까지), 따로 출력하는 파트끼리 겹치는지, 슬라이드 결합 연결판 자리·끼임 틈)
가 되어 기존 흐름을 그대로 탄다.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, ValidationError, create_model

from app.modules.assembly import (
    DOVETAIL_MIN_LENGTH_MM,
    OVERLAP_MM,
    PLATE_MM,
    AssemblyError,
    JoinSpec,
    PartSpec,
    SlidePlan,
    _bounds,
    _plane,
    _project,
    _side_profile_solid,
    anchor_frame,
    build_assembly,
    dovetail_centers,
    dovetail_fits,
    internal_gaps,
    join_problems,
    leftover_width,
    merge_features,
    passage_cutter,
    passage_leftover,
    place_parts,
    plate_gaps,
    plate_solid,
    plug_chamfer,
    plug_problems,
    slide_plan,
    slide_problems,
    slot_cutters,
    spigot_solid,
    tongue_solid,
)
from app.modules.definition import Bind, LimitDef, ModuleDef, bound_value
from app.templates.base import (
    Features,
    ParamConstraint,
    PrintPart,
    RuleContext,
    Template,
    TemplateParams,
)

# 통로가 출입구를 덮고 남긴 빈 곳, 따로 출력하는 파트끼리 겹친 부피가 이보다 크면 오류 (mm³, 형상 커널 오차 여유)
LEFTOVER_MAX_MM3 = 1.0
# 남은 빈 곳이 있어도 가장 넓은 폭이 이보다 좁으면 출력하면 메워지는 실금이라 세지 않는다 (노즐 0.4mm 의 선 폭보다 좁다)
LEFTOVER_MIN_WIDTH_MM = 0.5
OVERLAP_MAX_MM3 = 1.0
_CACHE_SIZE = 16

# 출력 자세 후보: 어느 면을 베드에 댈지 (위쪽 축을 아래로 보내는 회전)
_DOWN_ROTATIONS: tuple[np.ndarray, ...] = (
    np.eye(3),                                                   # 바닥이 아래 (사용 자세)
    np.diag([1.0, -1.0, -1.0]),                                  # 뒤집기 (지붕이 아래)
    np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]]),          # 앞면이 아래
    np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]]),          # 뒷면이 아래
    np.array([[0, 0, 1.0], [0, 1.0, 0], [-1.0, 0, 0]]),          # 왼쪽이 아래
    np.array([[0, 0, -1.0], [0, 1.0, 0], [1.0, 0, 0]]),          # 오른쪽이 아래
)
# 서포트 면적이 이 비율 안에서 비슷하면 사용 자세·낮은 자세를 앞세운다
_TIE = 1.05
# 슬라이드 결합 도브테일(세로 홈·혀)이 있는 묶음의 출력 자세 후보: 도브테일이 세로로 서는 자세만 (눕히면 홈 옆면이 오버행)
_VERTICAL_ROTATIONS: tuple[np.ndarray, ...] = _DOWN_ROTATIONS[:2]


def _field(model: type[BaseModel], path: str):  # noqa: ANN202
    """점 표기 경로("roof.kind")의 FieldInfo (없으면 None). 중첩 파라미터 모델을 따라 내려간다."""
    cls: type[BaseModel] = model
    *heads, last = path.split(".")
    for name in heads:
        f = cls.model_fields.get(name)
        ann = f.annotation if f is not None else None
        if not (isinstance(ann, type) and issubclass(ann, BaseModel)):
            return None
        cls = ann
    return cls.model_fields.get(last)


def _get_path(obj: Any, path: str) -> Any:
    for name in path.split("."):
        obj = getattr(obj, name)
    return obj


def _set_path(values: dict, path: str, value: Any) -> None:
    *heads, last = path.split(".")
    for name in heads:
        values = values[name]
    values[last] = value


def _params_model(defn: ModuleDef) -> type[TemplateParams]:
    fields: dict[str, Any] = {}
    for p in defn.params:
        if p.type == "choice":
            ann = Literal[tuple(p.choices or ())]  # type: ignore[valid-type]
            fields[p.name] = (ann, Field(p.default, description=p.description_ko))
        else:
            ann = int if p.type == "int" else float
            fields[p.name] = (ann, Field(ann(p.default), ge=p.min, le=p.max, description=p.description_ko))
    name = "".join(w.capitalize() for w in defn.key.split("_")) + "Params"
    return create_model(name, __base__=TemplateParams, **fields)


@dataclass(frozen=True)
class _Contact:
    """슬라이드 결합에서 자식 뒷면이 연결판에 닿는 곳 (도브테일 혀를 붙이는 자식 출력 파트)."""

    t0: float
    t1: float
    u0: float
    u1: float
    ok: bool  # 도브테일이 들어가는 폭·높이인지


@dataclass(frozen=True)
class _Layout:
    """슬라이드 결합이 있는 모듈의 출력 파트와 결합 정보."""

    parts: tuple[PrintPart, ...]
    plans: dict[int, SlidePlan]      # 결합 번호 → 연결판 자리
    contacts: dict[int, _Contact | None]
    owners: tuple[frozenset[str], ...] = ()  # 출력 파트마다 그 파트를 이루는 부품 id


class ModuleTemplate(Template):
    """모듈 정의 하나를 감싼 템플릿 (인스턴스마다 key·Params 가 다르다)."""

    def __init__(self, defn: ModuleDef, templates: dict[str, Template]):
        self.defn = defn
        self.key = defn.key  # type: ignore[misc]
        self.display_name_ko = defn.name_ko  # type: ignore[misc]
        self.description_ko = defn.description_ko  # type: ignore[misc]
        self.Params = _params_model(defn)  # type: ignore[misc]
        self.height_field = defn.height_param  # type: ignore[misc]
        self.size_fields = tuple(defn.size_params)  # type: ignore[misc]
        self.color = defn.color  # type: ignore[misc]
        self._templates = templates
        self._shapes: dict[str, object] = {}  # 같은 파라미터로 여러 번 부르는 build() (출력 자세·파트) 결과
        self._cache: dict[tuple[str, str], Any] = {}  # 출력 파트·형상 검사 결과 (파라미터별)
        self._lock = threading.Lock()
        for part in defn.parts:
            if part.template not in templates:
                raise ValueError(f"모듈 {defn.key}: 없는 부품 템플릿 {part.template}")
            t = templates[part.template]
            for k in part.params:
                if _field(t.Params, k) is None:
                    raise ValueError(f"모듈 {defn.key}: 부품 {part.id}({part.template})에 없는 파라미터 {k}")
        try:
            self.expand(self.Params())
        except ValidationError as e:
            raise ValueError(f"모듈 {defn.key}: 기본값으로 부품 파라미터를 만들 수 없습니다 ({e.error_count()})") from e
        # 모듈 파라미터의 끝값(최소·최대, 선택지 하나하나)도 부품 파라미터 범위·선택지 안이어야 한다
        # (아니면 사용자가 고른 값에서 부품 검증 오류로 엔진이 멈춘다). 나머지 파라미터는 기본값으로 둔다
        for mp in defn.params:
            values = list(mp.choices or ()) if mp.type == "choice" else [v for v in (mp.min, mp.max) if v is not None]
            for v in values:
                try:
                    self.expand(self.Params(**{mp.name: v}))
                except ValidationError as e:
                    raise ValueError(f"모듈 {defn.key}: 파라미터 {mp.name}={v} 로 부품 파라미터를 만들 수 없습니다 "
                                     f"({e.error_count()})") from e

    def _cached(self, name: str, p: TemplateParams, fn: Callable[[], Any]) -> Any:
        k = (name, _key(p))
        with self._lock:
            if k in self._cache:
                return self._cache[k]
        v = fn()
        with self._lock:
            if len(self._cache) >= _CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[k] = v
        return v

    # ── 펼치기 ──

    def _value(self, v: Any, p: TemplateParams) -> Any:
        if isinstance(v, Bind):
            x = getattr(p, v.param)
            return x if isinstance(x, str) else v.scale * x + v.offset
        return v

    def expand(self, p: TemplateParams) -> tuple[list[PartSpec], list[JoinSpec]]:
        parts: list[PartSpec] = []
        for part in self.defn.parts:
            t = self._templates[part.template]
            base = t.default_params().model_dump()
            for k, v in part.params.items():
                val = self._value(v, p)
                f = _field(t.Params, k)
                if f is not None and f.annotation is int and not isinstance(val, (str, bool)):
                    val = int(round(val))
                _set_path(base, k, val)
            parts.append(PartSpec(part.id, t, t.Params.model_validate(base)))
        joins = [
            JoinSpec(
                parent=j.parent.split(".")[0], parent_anchor=j.parent.split(".")[1],
                child=j.child.split(".")[0], child_anchor=j.child.split(".")[1],
                shift=float(self._value(j.shift, p)), lift=float(self._value(j.lift, p)),
                spin=j.spin, passage=bool(j.passage), mount=j.mount, reverse=j.into_child,
            )
            for j in self.defn.joins
        ]
        return parts, joins

    def default_params(self, ctx: RuleContext | None = None) -> TemplateParams:
        return self.Params()

    @property
    def has_slide(self) -> bool:
        return any(j.mount == "slide" for j in self.defn.joins)

    @property
    def split(self) -> bool:
        """따로 출력하는 결합(슬라이드·끼움)이 있어 출력 파트를 묶음마다 나누는지."""
        return any(j.mount in ("slide", "plug") for j in self.defn.joins)

    # ── 제약: 부품 제약을 모듈 파라미터로 되돌린다 ──

    def _bindings(self) -> dict[tuple[str, str], Bind]:
        """(부품 id, 부품 파라미터 경로) → 묶인 모듈 파라미터. 경로는 점 표기 그대로 (부품 제약의 field 와 같은 꼴)."""
        return {(part.id, k): v for part in self.defn.parts for k, v in part.params.items() if isinstance(v, Bind)}

    def constraints(self, p: TemplateParams, ctx: RuleContext) -> list[ParamConstraint]:
        out: list[ParamConstraint] = []
        binds = self._bindings()
        parts, _ = self.expand(p)
        for part in parts:
            for c in part.template.constraints(part.params, ctx):
                b = binds.get((part.id, c.field))
                if b is None or self.Params.model_fields[b.param].annotation not in (int, float):
                    continue  # 고정값 위반은 rule_issues 가 오류로 남긴다
                lo = None if c.min is None else (c.min - b.offset) / b.scale
                hi = None if c.max is None else (c.max - b.offset) / b.scale
                out.append(ParamConstraint(b.param, min=lo, max=hi, source=c.source,
                                           reason_ko=c.reason_ko, blocking=c.blocking))
        for lim, lo, hi in self._limit_bounds(p):
            # param 의 범위 밖으로 가야만 맞출 수 있는 쪽은 내지 않는다 (rule_issues 가 오류로 남긴다: 자동 보정은 묶인 쪽을
            # 바꾸지 않으므로 고칠 수 없다). 보정은 패스마다 그 패스 시작 값으로 이 범위를 다시 계산해 사슬을 따라간다
            lo_ok, hi_ok = self._limit_fixable(lim.param, lo, hi)
            if (lo_ok and lo is not None) or (hi_ok and hi is not None):
                out.append(ParamConstraint(lim.param, min=lo if lo_ok else None, max=hi if hi_ok else None,
                                           source="geometry", reason_ko=lim.reason_ko))
        return out

    # ── 모듈 limits ──

    def _limit_bounds(self, p: TemplateParams) -> list[tuple[LimitDef, float | None, float | None]]:
        """limit 마다 (정의, 지금 값에서의 min, max)."""
        values = {d.name: getattr(p, d.name) for d in self.defn.params if d.type != "choice"}
        return [(lim, bound_value(lim.min, values), bound_value(lim.max, values)) for lim in self.defn.limits]

    def _limit_fixable(self, name: str, lo: float | None, hi: float | None) -> tuple[bool, bool]:
        """param 을 그 범위(ParamDef min·max) 안에서 움직여 min·max 를 맞출 수 있는지 (정수 파라미터는 반올림해 본다)."""
        d = next(x for x in self.defn.params if x.name == name)
        integer = d.type == "int"
        lo_ok = lo is None or (math.ceil(lo - 1e-9) if integer else lo) <= d.max + 1e-9  # type: ignore[operator]
        hi_ok = hi is None or (math.floor(hi + 1e-9) if integer else hi) >= d.min - 1e-9  # type: ignore[operator]
        return lo_ok, hi_ok

    def _limit_issues(self, p: TemplateParams) -> list[str]:
        """자동 보정으로 맞출 수 없는 limit 위반 (param 의 범위 밖이어야 맞는 경우)."""
        out: list[str] = []
        for lim, lo, hi in self._limit_bounds(p):
            d = next(x for x in self.defn.params if x.name == lim.param)
            v = getattr(p, lim.param)
            lo_ok, hi_ok = self._limit_fixable(lim.param, lo, hi)
            name = _short(d.description_ko)
            if lo is not None and not lo_ok and v < lo - 1e-6:
                out.append(f"{name}은(는) {_num(lo)} 이상이어야 하지만 최대 {_num(d.max)} 까지라 자동으로 맞출 수 없습니다. "
                           f"{lim.reason_ko}")
            if hi is not None and not hi_ok and v > hi + 1e-6:
                out.append(f"{name}은(는) {_num(hi)} 이하여야 하지만 최소 {_num(d.min)} 까지라 자동으로 맞출 수 없습니다. "
                           f"{lim.reason_ko}")
        return out

    def rule_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        out: list[str] = []
        binds = self._bindings()
        parts, joins = self.expand(p)
        for part in parts:
            for c in part.template.constraints(part.params, ctx):
                if (part.id, c.field) in binds or not c.blocking:
                    continue
                if c.violates(_get_path(part.params, c.field)):
                    out.append(f"부품 {part.template.display_name_ko}({part.id}): {c.reason_ko}")
            out += [f"부품 {part.template.display_name_ko}({part.id}): {m}" for m in part.template.rule_issues(part.params, ctx)]
        out += self._limit_issues(p)
        out += join_problems(parts, joins)
        out += slide_problems(parts, joins)
        out += plug_problems(parts, joins)
        if not out:
            try:
                out += self._gap_issues(p, ctx)
            except AssemblyError as e:
                return [str(e)]
            out += self._geometry_issues(p, ctx)
        return out

    def _gap_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        """서로 잇지 않은 부품 사이 틈이 끼임 위험 구간이면 오류."""
        parts, joins = self.expand(p)
        solids = [q for q in parts if not q.template.cutter]
        if len(solids) < 3:
            return []  # 형상 부품이 둘이면 둘은 반드시 이어져 있다
        bounds = _part_bounds(self, _key(p))
        gt = ctx.size.gap_trap
        names = {q.id: q.template.display_name_ko for q in parts}
        return [f"{names[a]}({a})와 {names[b]}({b}) 사이 틈 {g:.1f}mm 가 끼임 위험 구간"
                f"({gt.safe_max_mm:g}~{gt.passable_min_mm:g}mm)에 있습니다"
                for a, b, g in internal_gaps(solids, joins, bounds) if gt.is_trap(g)]

    # ── 형상 검사 (파라미터별로 한 번만 계산해 둔다) ──

    def _geometry_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        gt = ctx.size.gap_trap
        out: list[str] = []
        try:
            facts = self._cached("geometry", p, lambda: self._geometry_facts(p))
        except AssemblyError as e:
            return [str(e)]
        for fact in facts:
            kind, args = fact[0], fact[1:]
            if kind == "leftover":
                a, b, vol = args
                out.append(f"{a}의 출입구가 {b}의 통로보다 커서 틈이 남습니다 (약 {vol:.0f}mm³). "
                           "통로 단면 모양과 폭을 출입구에 맞추세요")
            elif kind == "plug_leftover":
                a, b, vol = args
                out.append(f"{b}의 벽이 {a}의 출입구·끼움 구멍을 다 덮지 못해 틈이 남습니다 (약 {vol:.0f}mm³). "
                           "통로 단면 모양과 폭을 출입구에 맞추세요")
            elif kind == "overlap":
                a, b, vol = args
                out.append(f"따로 출력하는 파트 {a}와(과) {b}이(가) 겹칩니다 (약 {vol:.0f}mm³). "
                           "부품 위치나 크기를 바꾸세요")
            elif kind == "slide_wide":
                a, b, face = args
                out.append(f"{b}이(가) {a}의 '{face}' 면에서 연결판을 붙일 수 있는 곳보다 넓거나 벗어납니다. "
                           "부품이 면 밖으로 튀어나오지 않게 크기나 위치를 바꾸세요")
            elif kind == "slide_floor":
                a, b = args
                out.append(f"슬라이드 결합으로 붙이는 {b}은(는) {a}와(과) 같은 바닥에 서야 합니다")
            elif kind == "slide_contact":
                a, b = args
                out.append(f"{b}의 뒷면이 {a}의 연결판에 닿는 곳이 좁거나 낮아 도브테일을 낼 수 없습니다")
            elif kind == "slide_gap":
                a, b, gaps = args
                trapped = [g for g in gaps if gt.is_trap(g)]
                if trapped and max(trapped) <= PLATE_MM - OVERLAP_MM + 0.1:  # 연결판이 띄운 만큼의 틈 (벽 앞·경사 앞)
                    gap = max(trapped)
                    out.append(f"{a}의 연결판 위로 벽과 {b} 사이에 {gap:.1f}mm 틈이 생겨 끼임 위험 구간"
                               f"({gt.safe_max_mm:g}~{gt.passable_min_mm:g}mm)에 있습니다")
                elif trapped:
                    lo, hi = min(trapped), max(trapped)
                    out.append(f"{b}의 뒷면과 {a}의 벽·지붕 사이에 폭이 {lo:.1f}~{hi:.1f}mm 로 벌어지는 틈이 생겨 "
                               f"끼임 위험 구간({gt.safe_max_mm:g}~{gt.passable_min_mm:g}mm)에 있습니다. "
                               f"{b}을(를) {a}의 처마보다 낮게 하거나 지붕이 기울지 않은 면에 붙이세요")
        return out

    def _geometry_facts(self, p: TemplateParams) -> list[tuple]:
        """종별 기준과 상관없는 형상 사실 (메시지는 _geometry_issues 가 종별 기준으로 만든다)."""
        parts, joins = self.expand(p)
        placed = place_parts(parts, joins)
        names = {q.id: q.template.display_name_ko for q in parts}
        by_id = {q.id: q for q in parts}
        facts: list[tuple] = []
        # 1. 출입구·터널 끝에 통로로 이은 부품이 개구부를 다 덮는지 (끼움 결합은 넓힌 구멍까지)
        for j in joins:
            if not j.passage:
                continue
            wid, pid = j.wall_end[0], j.port_end[0]
            port = by_id[pid]
            if port.template.cutter:
                continue
            left = passage_leftover(placed, j, _plane(placed[pid]) * port.template.build(port.params))
            if left is not None and left.volume > LEFTOVER_MAX_MM3 \
                    and leftover_width(left, placed, j) > LEFTOVER_MIN_WIDTH_MM:
                facts.append(("plug_leftover" if j.plug else "leftover", names[wid], names[pid], float(left.volume)))
        # 2. 슬라이드 결합 연결판 자리
        printable = True
        if self.has_slide:
            layout = self._layout(p)
            for ji, plan in layout.plans.items():
                j = joins[ji]
                a, b = names[j.parent], names[j.child]
                if plan.mount is not None:
                    left_, right_, _ = plan.mount
                    if plan.t0 < left_ - 0.01 or plan.t1 > right_ + 0.01:
                        facts.append(("slide_wide", a, b, j.parent_anchor))
                if abs(plan.child_u[0]) > 0.5:
                    facts.append(("slide_floor", a, b))
                contact = layout.contacts.get(ji)
                if contact is None or not contact.ok:
                    facts.append(("slide_contact", a, b))
                    printable = False
                gaps = self._plate_gaps(layout, plan, joins[ji], parts, joins)
                if gaps:
                    facts.append(("slide_gap", a, b, gaps))
        # 3. 따로 출력하는 파트끼리 겹치지 않는지 (지붕 뚜껑에 닿은 부품, 도브테일 틈새 등)
        if printable:
            pps = self.print_parts(p)
            boxes = [_bounds(pp.part) for pp in pps]
            for i in range(len(pps)):
                for k in range(i + 1, len(pps)):
                    (alo, ahi), (blo, bhi) = boxes[i], boxes[k]
                    if np.any(alo > bhi - 0.01) or np.any(blo > ahi - 0.01):
                        continue
                    vol = float((pps[i].part & pps[k].part).volume)
                    if vol > OVERLAP_MAX_MM3:
                        facts.append(("overlap", pps[i].name_ko, pps[k].name_ko, vol))
        return facts

    # ── 형상 ──

    def build(self, p: TemplateParams):  # noqa: ANN201
        key = _key(p)
        hit = self._shapes.get(key)
        if hit is not None:
            return hit
        parts, joins = self.expand(p)
        try:
            shape = build_assembly(parts, joins)
        except AssemblyError:
            raise
        except Exception as e:  # noqa: BLE001 (형상 커널 오류)
            raise AssemblyError(f"조립 형상을 만들지 못했습니다 ({type(e).__name__})") from e
        if len(self._shapes) >= 8:
            self._shapes.pop(next(iter(self._shapes)))
        self._shapes[key] = shape
        return shape

    def features(self, p: TemplateParams) -> Features:
        parts, joins = self.expand(p)
        return merge_features(parts, joins, self.defn.enclosure)

    def print_rotation(self, p: TemplateParams) -> np.ndarray:
        """여섯 방향으로 눕혀 보고 서포트(오버행) 면적이 가장 작은 자세. 비슷하면 사용 자세·낮은 자세.
        따로 출력하는 결합(슬라이드·끼움)이 있으면 기준 부품 묶음(첫 출력 파트)의 자세."""
        if self.split:
            return self._layout(p).parts[0].rotation
        from app.geometry.mesh import part_to_mesh

        return self._cached("rotation", p, lambda: _best_rotation(part_to_mesh(self._body(p))))

    def print_parts(self, p: TemplateParams, built=None) -> list[PrintPart]:  # noqa: ANN001
        """부품끼리 붙은 본체 하나 + 부품이 따로 출력하는 파트들 (조립 위치 그대로, 출력 자세는 부품이 정한 대로).
        따로 출력하는 결합(슬라이드·끼움)이 있으면 한 덩어리로 붙은 부품 묶음마다 하나 (+ 부품이 따로 출력하는 파트들)."""
        if self.split:
            return list(self._layout(p).parts)
        extras = self._extra_parts(p)
        if not extras:
            body = built if built is not None else self.build(p)
            return [PrintPart("본체", body, self.print_rotation(p))]
        return [PrintPart("본체", self._body(p), self.print_rotation(p)), *extras]

    def _body(self, p: TemplateParams):  # noqa: ANN202
        """부품마다 첫 출력 파트(본체)만 모아 조립한 형상. 따로 출력하는 파트가 없으면 build() 와 같다.
        따로 출력하는 결합이 있으면 기준 부품 묶음의 출력 파트 (연결판·도브테일 홈·끼움 구멍 포함)."""
        if self.split:
            return self._layout(p).parts[0].part
        if not self._extra_parts(p):
            return self.build(p)
        return self._cached("body", p, lambda: self._fused_body(p))

    def _fused_body(self, p: TemplateParams):  # noqa: ANN202
        parts, joins = self.expand(p)
        placed = place_parts(parts, joins)
        body = None
        for part in parts:
            if part.template.cutter:
                continue
            solid = _plane(placed[part.id]) * part.template.print_parts(part.params)[0].part
            body = solid if body is None else body + solid
        for part in parts:
            if part.template.cutter:
                body = body - _plane(placed[part.id]) * part.template.build(part.params)
        for j in joins:
            if j.passage:
                body = body - passage_cutter(placed, j)
        return body

    def _extra_parts(self, p: TemplateParams) -> list[PrintPart]:
        return self._cached("extras", p, lambda: self._make_extra_parts(p))

    def _make_extra_parts(self, p: TemplateParams) -> list[PrintPart]:
        parts, joins = self.expand(p)
        out: list[PrintPart] = []
        placed = None
        for part in parts:
            if part.template.cutter:
                continue
            pps = part.template.print_parts(part.params)
            if len(pps) <= 1:
                continue
            placed = placed or place_parts(parts, joins)
            pl = placed[part.id]
            for pp in pps[1:]:
                # 부품 좌표의 출력 자세 회전을 조립 좌표에 맞게: 조립 좌표 → 부품 좌표(회전의 역) → 출력 자세
                out.append(PrintPart(f"{part.template.display_name_ko} {pp.name_ko}", _plane(pl) * pp.part,
                                     pp.rotation @ pl.rotation.T, key=f"{part.id}_{pp.key}"))
        return out

    # ── 슬라이드·끼움 결합: 묶음별 출력 파트 ──

    def _layout(self, p: TemplateParams) -> _Layout:
        return self._cached("layout", p, lambda: self._make_layout(p))

    def _make_layout(self, p: TemplateParams) -> _Layout:
        """한 덩어리로 붙은 부품 묶음(fused 결합의 연결 성분)마다 출력 파트 하나.

        - 묶음 본체 = 묶음 부품들의 첫 출력 파트 합 − 빼는 모양(창) − 통로 + (부모 쪽이면) 연결판(출력용: 자식 뒷면에서 끝남)
        - 끼움 결합: 벽 쪽 묶음은 넓힌 구멍으로 뚫고, 통로 쪽 묶음에 끼움 턱을 붙인다 (자세는 여섯 방향 중 서포트가
          가장 적은 쪽이라 세워 출력하는 터널은 끼움 턱이 위를 보게 선다)
        - 부품이 따로 출력하는 파트(집 지붕 등)는 그대로 따로
        - 자세: 홈·혀가 있는 묶음은 도브테일이 세로로 서는 사용·뒤집기 자세 중, 그 밖의 묶음은 여섯 방향 중 서포트가 가장 적은 쪽
        - 도브테일: 연결판에 홈, 자식 출력 파트 중 연결판에 가장 넓게 닿는 파트의 뒷면에 혀 (출력 자세에서 아래를 보는
          끝은 경사로 깎는다)"""
        from app.geometry.mesh import part_to_mesh

        parts, joins = self.expand(p)
        placed = place_parts(parts, joins)
        by_id = {q.id: q for q in parts}
        groups = fused_groups(parts, joins)
        group_of = {pid: gi for gi, g in enumerate(groups) for pid in g}
        bounds = {pid: (np.asarray(lo), np.asarray(hi)) for pid, (lo, hi) in _part_bounds(self, _key(p)).items()}

        mains: dict[str, Any] = {}
        extras: dict[str, list[list[Any]]] = {}  # 부품 id → [[이름, key, 솔리드, 자세], …]
        bodies: list[Any] = [None] * len(groups)
        for q in parts:
            if q.template.cutter:
                continue
            pl = placed[q.id]
            pps = q.template.print_parts(q.params)
            mains[q.id] = _plane(pl) * pps[0].part
            extras[q.id] = [[f"{q.template.display_name_ko} {pp.name_ko}", f"{q.id}_{pp.key}", _plane(pl) * pp.part,
                             pp.rotation @ pl.rotation.T] for pp in pps[1:]]
            gi = group_of[q.id]
            bodies[gi] = mains[q.id] if bodies[gi] is None else bodies[gi] + mains[q.id]
        for q in parts:
            if q.template.cutter:
                gi = group_of[q.id]
                bodies[gi] = bodies[gi] - _plane(placed[q.id]) * q.template.build(q.params)
        for j in joins:
            if j.passage:
                gi = group_of[j.wall_end[0]]
                bodies[gi] = bodies[gi] - passage_cutter(placed, j)
                if j.plug:
                    gp = group_of[j.port_end[0]]
                    bodies[gp] = bodies[gp] + spigot_solid(placed, j)
        plans: dict[int, SlidePlan] = {}
        for ji, j in enumerate(joins):
            if not j.slide:
                continue
            plan = slide_plan(placed, j, bounds[j.parent], bounds[j.child])
            plans[ji] = plan
            if plan.h > 0.5:
                gi = group_of[j.parent]
                bodies[gi] = bodies[gi] + plate_solid(plan, for_print=True)
        dovetailed = {group_of[joins[ji].parent] for ji in plans} | {group_of[joins[ji].child] for ji in plans}
        rots = [_best_rotation(part_to_mesh(b), _VERTICAL_ROTATIONS if gi in dovetailed else _DOWN_ROTATIONS)
                for gi, b in enumerate(bodies)]
        # 끼움 턱이 출력 자세에서 아래를 보면(세워 출력하는 터널의 아래 끝) 그 둘레 끝 면이 아래를 보는 턱이 되므로 깔때기로 깎는다
        for j in joins:
            if j.plug:
                gp = group_of[j.port_end[0]]
                _, _, _, n = anchor_frame(placed, *j.port_end)
                if float((rots[gp] @ n)[2]) < -0.5:
                    bodies[gp] = bodies[gp] - plug_chamfer(placed, j)

        contacts: dict[int, _Contact | None] = {}
        for ji, plan in plans.items():
            j = joins[ji]
            contact, target = self._contact(plan, mains[j.child], extras[j.child], bodies, rots, group_of[j.child])
            contacts[ji] = contact
            if contact is None or not contact.ok or plan.h <= 0.5:
                continue
            centers = dovetail_centers(contact.t0, contact.t1)
            u_lo, u_hi = max(0.0, contact.u0), min(plan.h, contact.u1)
            solid, rot = target
            plo, phi = _project(*_bounds(solid), plan.origin, plan.u)
            down_top = float((rot @ plan.u)[2]) < -0.5
            down_bottom = float((rot @ -plan.u)[2]) < -0.5
            tongue = tongue_solid(plan, centers, u_lo, u_hi,
                                  slope_top=down_top and u_hi < phi - 0.05,
                                  slope_bottom=down_bottom and u_lo > plo + 0.05)
            self._attach(target, tongue, bodies, extras[j.child], group_of[j.child])
            gi = group_of[j.parent]
            for cut in slot_cutters(plan, centers):
                bodies[gi] = bodies[gi] - cut

        out: list[PrintPart] = []
        owners: list[frozenset[str]] = [frozenset(g) for g in groups]
        separate_children = {j.child for j in joins if j.separate}
        for gi, g in enumerate(groups):
            if gi == 0:
                out.append(PrintPart("본체", bodies[gi], rots[gi], key="body"))
                continue
            head = next((pid for pid in g if pid in separate_children), g[0])
            q = by_id[head]
            pps = q.template.print_parts(q.params)
            if len(pps) > 1:
                name, key = f"{q.template.display_name_ko} {pps[0].name_ko}", f"{q.id}_{pps[0].key}"
            else:
                name, key = q.template.display_name_ko, q.id
            out.append(PrintPart(name, bodies[gi], rots[gi], key=key))
        for q in parts:
            for name, key, solid, rot in extras.get(q.id, []):
                out.append(PrintPart(name, solid, rot, key=key))
                owners.append(frozenset({q.id}))
        return _Layout(tuple(out), plans, contacts, tuple(owners))

    @staticmethod
    def _plate_gaps(layout: _Layout, plan: SlidePlan, j: JoinSpec, parts: list[PartSpec],
                    joins: list[JoinSpec]) -> tuple[float, ...]:
        """연결판 위 자식 뒷면과 그 뒤 사이 틈 (assembly.plate_gaps). 자식 쪽 = 자식과 한 덩어리인 부품들의 출력 파트."""
        import trimesh

        from app.geometry.mesh import part_to_mesh

        if plan.child_u[1] <= plan.h + 0.5:
            return ()
        group = next(g for g in fused_groups(parts, joins) if j.child in g)
        mine = [pp for pp, own in zip(layout.parts, layout.owners) if own <= set(group)]
        rest = [pp for pp, own in zip(layout.parts, layout.owners) if not own <= set(group)]
        if not mine or not rest:
            return ()
        child_mesh = trimesh.util.concatenate([part_to_mesh(pp.part) for pp in mine])
        other_mesh = trimesh.util.concatenate([part_to_mesh(pp.part) for pp in rest])
        return plate_gaps(plan, child_mesh, other_mesh)

    @staticmethod
    def _contact(plan: SlidePlan, main, extras, bodies, rots, child_group):  # noqa: ANN001, ANN205
        """자식 출력 파트 가운데 연결판에 가장 넓게 닿는 것과 그 닿는 범위. 돌려주는 target = (솔리드, 출력 자세 회전)
        (자식 본체면 묶음 본체·묶음 자세)."""
        f = plan.face_d
        if plan.h <= 0.5:
            return None, None
        slab = _side_profile_solid(plan, [(f, 0.0), (f + 1.0, 0.0), (f + 1.0, plan.h), (f, plan.h)], plan.t0, plan.t1)
        best = None
        for idx, solid in enumerate([main, *[e[2] for e in extras]]):
            inter = solid & slab
            vol = float(inter.volume) if inter is not None else 0.0
            if vol > 1e-3 and (best is None or vol > best[0]):
                best = (vol, idx, inter)
        if best is None:
            return None, None
        _, idx, inter = best
        lo, hi = _bounds(inter)
        t0, t1 = _project(lo, hi, plan.origin, plan.t)
        u0, u1 = _project(lo, hi, plan.origin, plan.u)
        u0, u1 = max(0.0, u0), min(plan.h, u1)
        ok = dovetail_fits(t0, t1) and u1 - u0 >= DOVETAIL_MIN_LENGTH_MM
        contact = _Contact(t0, t1, u0, u1, ok)
        if idx == 0:
            return contact, (bodies[child_group], rots[child_group])
        return contact, (extras[idx - 1][2], extras[idx - 1][3])

    @staticmethod
    def _attach(target, tongue, bodies, extras, child_group) -> None:  # noqa: ANN001
        solid = target[0]
        if solid is bodies[child_group]:
            bodies[child_group] = bodies[child_group] + tongue
            return
        for e in extras:
            if e[2] is solid:
                e[2] = e[2] + tongue
                return


def fused_groups(parts: list[PartSpec], joins: list[JoinSpec]) -> list[list[str]]:
    """한 덩어리로 붙는(fused 결합으로 이어진) 부품 묶음. 기준 부품의 묶음이 처음, 나머지는 부품 순서대로.
    슬라이드·끼움 결합은 묶음을 나눈다."""
    root = {p.id: p.id for p in parts}

    def find(x: str) -> str:
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x

    for j in joins:
        if not j.separate:
            a, b = find(j.parent), find(j.child)
            if a != b:
                root[b] = a
    groups: dict[str, list[str]] = {}
    for p in parts:
        groups.setdefault(find(p.id), []).append(p.id)
    first = find(parts[0].id)
    return [groups[first], *[g for r, g in groups.items() if r != first]]


def _best_rotation(mesh, candidates: tuple[np.ndarray, ...] = _DOWN_ROTATIONS) -> np.ndarray:  # noqa: ANN001
    from app.geometry.mesh import to_print_orientation
    from app.validation.checks import overhang_area

    best: tuple[float, float, int] | None = None
    best_rot = candidates[0]
    for i, rot in enumerate(candidates):
        m = to_print_orientation(mesh, rot)
        area = overhang_area(m, 45.0)
        key = (area, float(m.extents[2]), i)
        if best is None or area < best[0] / _TIE - 1.0 or (area <= best[0] * _TIE + 1.0 and key[1:] < best[1:]):
            best, best_rot = key, rot
    return best_rot


def _key(p: TemplateParams) -> str:
    return p.model_dump_json()


def _short(description: str) -> str:
    """파라미터 설명의 첫 문장에서 단위를 뺀 이름 (자동 보정 문구와 같은 꼴: app/validation/autofix._desc)."""
    return description.split(".")[0].replace(" mm", "")


def _num(x: float | None) -> str:
    x = float(x or 0.0)
    return f"{x:g}" if x.is_integer() else f"{x:.1f}"


@lru_cache(maxsize=64)
def _part_bounds_cached(module: ModuleTemplate, params_json: str) -> dict[str, tuple]:
    p = module.Params.model_validate_json(params_json)
    parts, joins = module.expand(p)
    placed = place_parts(parts, joins)
    out = {}
    for part in parts:
        if part.template.cutter:
            continue
        bb = (_plane(placed[part.id]) * part.template.build(part.params)).bounding_box()
        out[part.id] = ((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z))
    return out


def _part_bounds(module: ModuleTemplate, params_json: str) -> dict[str, tuple]:
    return _part_bounds_cached(module, params_json)

