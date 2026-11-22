"""자유 조립 항목의 템플릿 (ComposedTemplate).

조립 해석기(app/modules/compose)가 정한 구조(ResolvedAssembly: 부품·결합·따르는 치수)를 템플릿 하나로 감싼다.
엔진의 보정·배치·검증·저장·내려받기는 이 템플릿을 보통 템플릿처럼 쓴다.

  - key = "assembly", Params: 부품 id 마다 그 부품 템플릿의 Params 를 담은 모델 (create_model).
    파라미터 경로는 "부품id.필드" ("hide.depth_mm") 이고 보정 문구는 부품 이름을 앞에 붙인다 ("은신처 · 세로")
  - expand: 부품마다 PartSpec(id, 템플릿, 그 부품 파라미터) + 저장된 결합(ResolvedJoin.join_spec)
  - constraints: 해석기의 derived_constraints(resolved, p, ctx) (자동 보정 패스마다 다시 계산한다).
    해석기가 아직 없으면 부품 제약에 부품 id 를 붙이고 따르는 치수(ties)를 주인 값으로 돌린 것 (fallback_constraints)
  - rule_issues: 부품 규칙 + 조립 규칙(연결 지점·슬라이드·끼움) + 연결 지점 중복 + 형상 검사 (AssemblyTemplate)
  - size_fields: 기준 구조물 부품(host·room_host)의 크기 파라미터 (따르는 치수·맞춰지는 높이는 뺀다)
  - 높이 제약(케이지 천장·어항 물 깊이): 부품마다의 높이 제약에 부품 id 를 붙인 것 (1단계는 모든 부품이 바닥에 선다)
  - 출력 파트·검사 문구의 부품 이름은 같은 템플릿이 여러 번 나오면 번호를 붙인다 ("은신처 2")

다시 만들 때는 저장된 ResolvedAssembly 와 파라미터만으로 이 템플릿을 만든다 (해석기를 다시 돌리지 않는다).
"""

from __future__ import annotations

import dataclasses
import importlib
import warnings
from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from pydantic import BaseModel, Field, create_model

from app.modules.assembly import (
    JoinSpec,
    PartSpec,
    join_problems,
    plug_problems,
    slide_problems,
)
from app.modules.module_template import AssemblyTemplate, _get_path
from app.modules.structure import ResolvedAssembly, part_names
from app.templates.base import ParamConstraint, RuleContext, Template, TemplateParams

# 조립 항목의 기준 구조물 역할 (이 부품들의 크기 파라미터를 케이지 공간이 부족할 때 줄인다)
HOST_ROLES = ("host", "room_host")

# 해석기가 정하는 제약: derived_constraints(resolved, p, ctx) -> list[ParamConstraint]
DerivedConstraints = Callable[[ResolvedAssembly, TemplateParams, RuleContext], list[ParamConstraint]]


class PartsParams(TemplateParams):
    """조립 항목 파라미터의 기반: 필드 = 부품 id, 값 = 그 부품 템플릿의 Params.

    part_labels: 부품 id → 부품 이름 (자동 보정 문구 app/validation/autofix._desc 가 쓴다)."""

    part_labels: ClassVar[dict[str, str]] = {}


def _reserved(pid: str) -> bool:
    """pydantic 모델 이름과 겹쳐 필드로 쓸 수 없는 부품 id (model_dump 등)."""
    return pid.startswith("model_") and hasattr(BaseModel, pid)


def _params_model(parts: list[tuple[str, Template]], labels: dict[str, str]) -> type[PartsParams]:
    fields: dict[str, Any] = {
        pid: (t.Params, Field(default_factory=t.Params, description=labels[pid])) for pid, t in parts
    }
    with warnings.catch_warnings():
        # 부품 id 가 BaseModel 의 옛 메서드 이름(json·copy 등)과 같으면 pydantic 이 경고만 하고 필드로 쓴다
        warnings.simplefilter("ignore", UserWarning)
        model = create_model("AssemblyParams", __base__=PartsParams, **fields)
    model.part_labels = dict(labels)
    return model


_HANGUL_FIRST, _HANGUL_LAST = 0xAC00, 0xD7A3  # 한글 음절 (가..힣)


def _josa_iga(word: str) -> str:
    """'이'/'가': 마지막 글자에 받침이 있으면 '이'."""
    code = ord(word[-1]) if word else 0
    if _HANGUL_FIRST <= code <= _HANGUL_LAST:
        return "이" if (code - _HANGUL_FIRST) % 28 else "가"
    return "이(가)"


def generated_name(resolved: ResolvedAssembly, template_names: Mapping[str, str]) -> str:
    """이름이 없는 조립 항목의 이름: "그릇 받침·물병 거치대·터널·은신처가 달린 은신처" (붙은 부품 종류 → 기준 부품)."""
    root = template_names.get(resolved.parts[0].template, resolved.parts[0].template)
    others = list(dict.fromkeys(template_names.get(p.template, p.template) for p in resolved.parts[1:]))
    if not others:
        return root
    joined = "·".join(others)
    return f"{joined}{_josa_iga(joined)} 달린 {root}"


def prefixed(pid: str, cons: list[ParamConstraint]) -> list[ParamConstraint]:
    """부품 제약의 필드 앞에 부품 id 를 붙인다 ("depth_mm" → "hide.depth_mm")."""
    return [dataclasses.replace(c, field=f"{pid}.{c.field}") for c in cons]


def redirect_to_owner(resolved: ResolvedAssembly, cons: list[ParamConstraint]) -> list[ParamConstraint]:
    """따르는 치수(tie follower)에 걸린 제약을 그 주인 값(owner)으로 옮긴다 (값이 같으므로 같은 범위).
    예: 터널 내경 최소 70mm → 은신처 출입구 지름 최소 70mm (터널 내경은 따라 바뀐다)."""
    owners = {t.follower: t.owner for t in resolved.ties}
    return [dataclasses.replace(c, field=owners[c.field]) if c.field in owners else c for c in cons]


def tie_constraints(resolved: ResolvedAssembly, p: TemplateParams) -> list[ParamConstraint]:
    """따르는 치수 = 주인 값 (min = max = 지금 주인 값). 주인이 움직이면 다음 패스에서 따라간다."""
    from app.validation.autofix import _desc

    out = []
    for t in resolved.ties:
        v = _get_path(p, t.owner)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        out.append(ParamConstraint(
            t.follower, min=float(v), max=float(v), source="geometry",
            reason_ko=f"이어 붙인 부품끼리 맞물리도록 {_desc(type(p), t.owner)}에 맞췄습니다",
        ))
    return out


def _derived_hook() -> DerivedConstraints | None:
    """조립 해석기(app/modules/compose)의 derived_constraints. 아직 없으면 None."""
    try:
        compose = importlib.import_module("app.modules.compose")
    except ModuleNotFoundError as e:
        if e.name != "app.modules.compose":
            raise
        return None
    return getattr(compose, "derived_constraints", None)


class ComposedTemplate(AssemblyTemplate):
    """자유 조립 항목 하나 (해석기가 정한 구조 하나마다 인스턴스 하나: 해석기의 composed_template 이 기억한다)."""

    key = "assembly"

    def __init__(self, resolved: ResolvedAssembly, templates: Mapping[str, Template] | None = None,
                 name_ko: str | None = None):
        super().__init__()
        if templates is None:
            from app.templates.registry import primitives

            templates = primitives()
        self.resolved = resolved
        parts: list[tuple[str, Template]] = []
        for rp in resolved.parts:
            t = templates.get(rp.template)
            if t is None:
                raise ValueError(f"조립 항목: 없는 부품 템플릿 {rp.template} ({rp.id})")
            if _reserved(rp.id):
                raise ValueError(f"조립 항목: 부품 id 로 쓸 수 없는 이름입니다 ({rp.id})")
            parts.append((rp.id, t))
        self._parts = parts
        self._by_id = dict(parts)
        tnames = {t.key: t.display_name_ko for _, t in parts}
        self.names: dict[str, str] = part_names(resolved.parts, tnames)
        self.display_name_ko = name_ko or generated_name(resolved, tnames)  # type: ignore[misc]
        self.description_ko = f"부품 {len(parts)}개를 이어 붙인 조립 구조물"  # type: ignore[misc]
        self.color = parts[0][1].color  # type: ignore[misc]
        self.Params = _params_model(parts, self.names)  # type: ignore[misc]
        self._joins: tuple[JoinSpec, ...] = tuple(j.join_spec() for j in resolved.joins)
        self._enclosure = any(_has_entrances(t) for _, t in parts)
        self.size_fields = self._size_fields()  # type: ignore[misc]

    def __repr__(self) -> str:
        return f"ComposedTemplate({self.resolved.geometry_digest()[:12]})"

    # ── 구조 ──

    def expand(self, p: TemplateParams) -> tuple[list[PartSpec], list[JoinSpec]]:
        return [PartSpec(pid, t, getattr(p, pid)) for pid, t in self._parts], list(self._joins)

    def part_names(self, parts: list[PartSpec]) -> dict[str, str]:
        return {q.id: self.names.get(q.id, q.template.display_name_ko) for q in parts}

    def part_template(self, pid: str) -> Template:
        return self._by_id[pid]

    @property
    def enclosure(self) -> bool:
        return self._enclosure

    @property
    def has_slide(self) -> bool:
        return any(j.slide for j in self._joins)

    @property
    def split(self) -> bool:
        return any(j.separate for j in self._joins)

    def _size_fields(self) -> tuple[str, ...]:
        """기준 구조물 부품의 크기 파라미터 (부품 id 를 붙여서). 다른 값을 따르는 치수와 맞춰지는 높이는 뺀다."""
        followers = {t.follower for t in self.resolved.ties}
        out: list[str] = []
        for pid, t in self._parts:
            if t.role not in HOST_ROLES:
                continue
            for f in t.size_fields:
                path = f"{pid}.{f}"
                if path not in followers and f != t.level_field:
                    out.append(path)
        return tuple(out)

    # ── 파라미터 ──

    def default_params(self, ctx: RuleContext | None = None) -> TemplateParams:
        return self.Params(**{pid: t.default_params(ctx) for pid, t in self._parts})

    def load_stored_params(self, raw: dict) -> TemplateParams:
        """저장된 파라미터 (부품 id → 부품 파라미터). 부품마다 저장 당시 없던 필드는 그 템플릿의 legacy_defaults 로."""
        values: dict[str, Any] = {}
        for pid, t in self._parts:
            part_raw = raw.get(pid)
            values[pid] = t.load_stored_params(dict(part_raw)) if isinstance(part_raw, dict) \
                else t.Params.model_validate({**t.legacy_defaults})
        extra = sorted(set(raw) - set(values))
        if extra:
            raise ValueError(f"조립 항목에 없는 부품의 파라미터입니다: {extra}")
        return self.Params(**values)

    # ── 제약 ──

    def constraints(self, p: TemplateParams, ctx: RuleContext) -> list[ParamConstraint]:
        """해석기의 derived_constraints (자동 보정 패스마다 다시 부른다). 해석기가 없으면 fallback_constraints."""
        hook = _derived_hook()
        if hook is not None:
            return hook(self.resolved, p, ctx)
        return self.fallback_constraints(p, ctx)

    def fallback_constraints(self, p: TemplateParams, ctx: RuleContext) -> list[ParamConstraint]:
        """부품마다의 제약(부품 id 를 붙이고 따르는 치수는 주인 값으로 옮긴 것) + 따르는 치수 = 주인 값."""
        out: list[ParamConstraint] = []
        for pid, t in self._parts:
            out += redirect_to_owner(self.resolved, prefixed(pid, t.constraints(getattr(p, pid), ctx)))
        return out + tie_constraints(self.resolved, p)

    def height_limit_constraints(
        self, p: TemplateParams, ctx: RuleContext, limit_mm: float, reason_ko: str
    ) -> list[ParamConstraint]:
        out: list[ParamConstraint] = []
        for pid, t in self._parts:
            out += prefixed(pid, t.height_limit_constraints(getattr(p, pid), ctx, limit_mm, reason_ko))
        return redirect_to_owner(self.resolved, out)

    def cage_height_constraints(
        self, p: TemplateParams, ctx: RuleContext, limit_mm: float, reason_ko: str
    ) -> list[ParamConstraint]:
        out: list[ParamConstraint] = []
        for pid, t in self._parts:
            out += prefixed(pid, t.cage_height_constraints(getattr(p, pid), ctx, limit_mm, reason_ko))
        return redirect_to_owner(self.resolved, out)

    def min_height_mm(self, ctx: RuleContext, p: TemplateParams | None = None) -> float | None:
        """가장 낮게 만든 높이 = 부품마다 가장 낮은 높이 중 가장 높은 것 (모든 부품이 바닥에 선다). 하나라도 모르면 None."""
        hs = [t.min_height_mm(ctx, None if p is None else getattr(p, pid)) for pid, t in self._parts]
        return None if any(h is None for h in hs) else max(hs)  # type: ignore[type-var]

    # ── 규칙 ──

    def rule_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        parts, joins = self.expand(p)
        out: list[str] = []
        for q in parts:
            out += [f"{self.names[q.id]}: {m}" for m in q.template.rule_issues(q.params, ctx)]
        out += join_problems(parts, joins)
        out += slide_problems(parts, joins)
        out += plug_problems(parts, joins)
        out += self.reuse_problems()
        if not out:
            out += self._geometry_rule_issues(p, ctx)
        return out

    def reuse_problems(self) -> list[str]:
        """연결 지점 하나에 둘 이상을 이었는지. 부모 옆면에 슬라이드 결합으로 나란히 끼우는 것만 여럿 된다."""
        uses: dict[tuple[str, str], list[tuple[str, JoinSpec]]] = {}
        for j in self._joins:
            uses.setdefault((j.parent, j.parent_anchor), []).append(("parent", j))
            uses.setdefault((j.child, j.child_anchor), []).append(("child", j))
        out: list[str] = []
        for (pid, anchor), us in uses.items():
            if len(us) < 2 or all(role == "parent" and j.slide for role, j in us):
                continue
            others = [self.names[j.child if role == "parent" else j.parent] for role, j in us]
            out.append(f"{self.names[pid]}의 연결 지점 '{anchor}'에 {', '.join(others)}을(를) 함께 이었습니다. "
                       "한 연결 지점에는 부품 하나만 이을 수 있습니다 (옆면에 슬라이드로 끼우는 부품만 나란히 여럿 됩니다)")
        return out


def _has_entrances(t: Template) -> bool:
    """드나드는 공간이 있는 부품인지 (특징에 출입구 수가 있는 은신처·집 등)."""
    if t.role == "room_host":
        return True
    try:
        return t.features(t.default_params()).entrance_count is not None
    except Exception:  # noqa: BLE001 (특징을 알 수 없는 부품은 드나드는 공간으로 보지 않는다)
        return False
