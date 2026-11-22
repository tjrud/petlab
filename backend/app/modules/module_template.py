"""조립 모듈을 템플릿처럼 쓰게 하는 어댑터.

엔진(보정·배치·검증·저장·내려받기)은 템플릿만 안다. 모듈 하나를 템플릿 하나로 감싸면
  - Params: 모듈이 드러낸 파라미터 (LLM 이 정한다)
  - constraints: 부품의 종별·출력 제약을 묶인 관계(scale·offset)로 모듈 파라미터 제약으로 되돌린 것
  - build: 부품을 조립한 형상
  - features: 부품 특징을 합친 것 (출입 면·출입구 수·통로 크기 등)
  - print_parts / print_rotation: 부품끼리 붙은 본체는 여섯 방향으로 눕혀 보고 서포트가 가장 적은 자세로,
    부품이 따로 출력하는 파트(집의 지붕 뚜껑 등)는 그 부품이 정한 자세 그대로
가 되어 기존 흐름을 그대로 탄다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

import numpy as np
from pydantic import Field, create_model

from app.modules.assembly import (
    AssemblyError,
    JoinSpec,
    PartSpec,
    _plane,
    build_assembly,
    internal_gaps,
    join_problems,
    merge_features,
    place_parts,
)
from app.modules.definition import Bind, ModuleDef
from app.templates.base import Features, ParamConstraint, PrintPart, RuleContext, Template, TemplateParams

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
        for part in defn.parts:
            if part.template not in templates:
                raise ValueError(f"모듈 {defn.key}: 없는 부품 템플릿 {part.template}")

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
                if t.Params.model_fields[k].annotation is int and not isinstance(val, str):
                    val = int(round(val))
                base[k] = val
            parts.append(PartSpec(part.id, t, t.Params.model_validate(base)))
        joins = [
            JoinSpec(
                parent=j.parent.split(".")[0], parent_anchor=j.parent.split(".")[1],
                child=j.child.split(".")[0], child_anchor=j.child.split(".")[1],
                shift=float(self._value(j.shift, p)), lift=float(self._value(j.lift, p)),
                spin=j.spin, passage=j.passage,
            )
            for j in self.defn.joins
        ]
        return parts, joins

    def default_params(self, ctx: RuleContext | None = None) -> TemplateParams:
        return self.Params()

    # ── 제약: 부품 제약을 모듈 파라미터로 되돌린다 ──

    def _bindings(self) -> dict[tuple[str, str], Bind]:
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
        return out

    def rule_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        out: list[str] = []
        binds = self._bindings()
        parts, joins = self.expand(p)
        for part in parts:
            for c in part.template.constraints(part.params, ctx):
                if (part.id, c.field) in binds or not c.blocking:
                    continue
                if c.violates(getattr(part.params, c.field)):
                    out.append(f"부품 {part.template.display_name_ko}({part.id}): {c.reason_ko}")
            out += [f"부품 {part.template.display_name_ko}({part.id}): {m}" for m in part.template.rule_issues(part.params, ctx)]
        out += join_problems(parts, joins)
        if not out:
            out += self._gap_issues(p, ctx)
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
        """여섯 방향으로 눕혀 보고 서포트(오버행) 면적이 가장 작은 자세. 비슷하면 사용 자세·낮은 자세."""
        from app.geometry.mesh import part_to_mesh

        return _best_rotation(part_to_mesh(self._body(p)))

    def print_parts(self, p: TemplateParams, built=None) -> list[PrintPart]:  # noqa: ANN001
        """부품끼리 붙은 본체 하나 + 부품이 따로 출력하는 파트들 (조립 위치 그대로, 출력 자세는 부품이 정한 대로)."""
        extras = self._extra_parts(p)
        if not extras:
            body = built if built is not None else self.build(p)
            return [PrintPart("본체", body, self.print_rotation(p))]
        return [PrintPart("본체", self._body(p), self.print_rotation(p)), *extras]

    def _body(self, p: TemplateParams):  # noqa: ANN202
        """부품마다 첫 출력 파트(본체)만 모아 조립한 형상. 따로 출력하는 파트가 없으면 build() 와 같다."""
        if not self._extra_parts(p):
            return self.build(p)
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
                pa = placed[j.parent].spec.template.anchors(placed[j.parent].spec.params)[j.parent_anchor]
                child = placed[j.child]
                cutter = child.spec.template.port_cutter(child.spec.params, j.child_anchor, (pa.wall_mm or 0) + 1.3)
                if cutter is not None:
                    body = body - _plane(child) * cutter
        return body

    def _extra_parts(self, p: TemplateParams) -> list[PrintPart]:
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


def _best_rotation(mesh) -> np.ndarray:  # noqa: ANN001
    from app.geometry.mesh import to_print_orientation
    from app.validation.checks import overhang_area

    best: tuple[float, float, int] | None = None
    best_rot = _DOWN_ROTATIONS[0]
    for i, rot in enumerate(_DOWN_ROTATIONS):
        m = to_print_orientation(mesh, rot)
        area = overhang_area(m, 45.0)
        key = (area, float(m.extents[2]), i)
        if best is None or area < best[0] / _TIE - 1.0 or (area <= best[0] * _TIE + 1.0 and key[1:] < best[1:]):
            best, best_rot = key, rot
    return best_rot


def _key(p: TemplateParams) -> str:
    return p.model_dump_json()


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

