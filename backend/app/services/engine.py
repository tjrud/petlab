"""설계 엔진: 항목 명세 → (파라미터 보정 → 형상 생성 → 배치 → 공간 보정 → 검증).

LLM·DB 와 독립적인 순수 계산 단계다. LLM 이 낸 명세(템플릿·파라미터·배치 힌트)를 받아
검증된 템플릿 코드로 형상을 만들고, 자동 검증 보고서를 붙여 돌려준다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.domain import BuiltItem, BuiltPart, Cage, PlacementHint, mesh_footprint
from app.geometry.mesh import part_to_mesh, to_print_orientation
from app.layout.placer import attach_satisfied, place_all
from app.rules.loader import PrintingRules, RuleBook, SizeRules
from app.templates.base import ParamConstraint, RuleContext, Template, TemplateParams
from app.templates.decor import PatternDecor, apply_decor, parse_decor
from app.templates.registry import get_template
from app.validation.autofix import clamp_params, constraint_violations, shrink_params
from app.validation.checks import validate_all
from app.validation.report import Issue, Severity, ValidationReport

log = logging.getLogger(__name__)

SHRINK_STEPS = (0.9, 0.8, 0.7, 0.6, 0.5)


@dataclass(frozen=True)
class ItemSpec:
    template: str
    params: dict
    hint: PlacementHint = field(default_factory=PlacementHint)
    decor: dict | None = None  # 장식 명세 (templates/decor.py 의 PatternDecor | TextDecor). 없으면 None


@dataclass(frozen=True)
class EngineContext:
    cage: Cage
    species: str
    size: str
    count: int
    rules: RuleBook

    @property
    def size_rules(self) -> SizeRules:
        return self.rules.size_rules(self.species, self.size)

    @property
    def min_wall_mm(self) -> float:
        return self.rules.min_wall_for(self.species, self.size)

    @property
    def rule_ctx(self) -> RuleContext:
        return RuleContext(self.size_rules, self.min_wall_mm, self.count,
                           printing_max_overhang_deg=self.rules.printing.max_overhang_deg,
                           min_feature_mm=self.rules.printing.min_feature_mm)


@dataclass
class EngineResult:
    items: list[BuiltItem]
    report: ValidationReport


def build_item(
    index: int, template: Template, params: TemplateParams, hint: PlacementHint, printing: PrintingRules,
    decor: dict | None = None, rule_ctx: RuleContext | None = None,
) -> BuiltItem:
    """형상 생성. decor 가 있으면(장식 명세) 파트 분할 뒤 파트별로 장식을 얹고 조립 형상은 그 파트들의 합으로 만든다.
    장식이 없으면 예전과 똑같은 경로·바이트다."""
    tol, ang = printing.tessellation_tolerance_mm, printing.tessellation_angular_tolerance_deg
    decor_issues: list[Issue] = []
    part = template.build(params)
    print_parts = template.print_parts(params, built=part)
    decorated = False
    if decor is not None and rule_ctx is not None:
        label = _label(template, index)
        print_parts, decor_issues = apply_decor(print_parts, template, params, parse_decor(decor), rule_ctx,
                                                item_index=index, label_ko=label)
        decorated = not any(i.code == "decor_skipped" for i in decor_issues) or len(decor_issues) == 0
        if decorated:
            part = print_parts[0].part
            for pp in print_parts[1:]:
                part = part + pp.part
    mesh = part_to_mesh(part, tol, ang)
    lo, hi = mesh.bounds
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    print_mesh = to_print_orientation(mesh, template.print_rotation(params))
    # 출력 파트: 파트가 하나뿐인 템플릿은 예전과 똑같은 메시(조립 형상 = 본체)를 쓴다 (파일 바이트가 바뀌지 않게)
    parts: list[BuiltPart] = []
    if len(print_parts) > 1:
        for pp in print_parts:
            pmesh = part_to_mesh(pp.part, tol, ang)
            parts.append(BuiltPart(pp.key, pp.name_ko, pmesh, to_print_orientation(pmesh, pp.rotation)))
        print_mesh = parts[0].print_mesh
    return BuiltItem(
        index=index,
        key=template.key,
        features=template.features(params),
        mesh=mesh,
        print_mesh=print_mesh,
        footprint=mesh_footprint(mesh),
        hint=hint,
        template=template,
        params=params,
        parts=parts,
        decor=decor,
        decor_issues=decor_issues,
    )


def _height_constraint(template: Template, ctx: EngineContext) -> list[ParamConstraint]:
    if not template.height_field:
        return []
    P = ctx.size_rules.gap_trap.passable_min_mm
    limit = ctx.cage.height_mm - P
    return [ParamConstraint(
        template.height_field, max=limit, source="geometry",
        reason_ko=f"케이지 천장과의 틈에 끼이지 않도록 높이를 {limit:g}mm(천장 높이 − {P:g}mm) 이하로 맞췄습니다.",
    )]


def _label(template: Template, index: int) -> str:
    return f"{template.display_name_ko} #{index + 1}"


def attach_constraints(template: Template, hint: PlacementHint, targets: dict[int, BuiltItem | tuple[Template, TemplateParams]]
                       ) -> list[ParamConstraint]:
    """attach_to 로 다른 구조물에 붙는 항목의 상호 제약: 램프 꼭대기 높이 = 대상의 착지판 높이 (2층 집의 바깥 램프)."""
    if hint.attach_to is None or not template.height_field:
        return []
    idx, _ = hint.attach_to
    target = targets.get(idx)
    if target is None:
        return []
    t_template, t_params = (target.template, target.params) if isinstance(target, BuiltItem) else target
    if t_template is None or t_params is None:
        return []
    landing = t_template.features(t_params).extra.get("landing_height_mm")
    if landing is None:
        return []
    return [ParamConstraint(
        template.height_field, min=landing, max=landing,
        reason_ko=f"램프 꼭대기가 {_label(t_template, idx)}의 착지판({landing:g}mm)에 닿도록 높이를 맞췄습니다",
    )]


def decor_constraints(template: Template, params: TemplateParams, decor: dict | None, ctx: RuleContext
                      ) -> list[ParamConstraint]:
    """각인(파내기)을 넣는 면의 벽은 최소 벽 두께 + 깊이 이상이어야 한다: 장식을 줄이기 전에 벽을 두껍게 보정한다."""
    if decor is None:
        return []
    try:
        d = parse_decor(decor)
    except ValueError:
        return []
    if d is None or (isinstance(d, PatternDecor) and d.mode == "relief"):
        return []
    fields = {z.thickness_field for z in template.decor_zones(params)
              if z.thickness_field and (d.face == "walls" and z.face != "roof" or z.face == d.face)}
    need = ctx.min_wall_mm + d.depth_mm
    return [ParamConstraint(
        f, min=need, reason_ko=f"각인 깊이 {d.depth_mm:g}mm 를 빼고도 벽이 최소 두께 {ctx.min_wall_mm:g}mm 이상 남도록 두껍게 했습니다",
    ) for f in sorted(fields)]


def _prepare(spec: ItemSpec, index: int, ctx: EngineContext,
             extra: list[ParamConstraint] | None = None) -> tuple[Template, TemplateParams, list[Issue]] | Issue:
    try:
        template = get_template(spec.template)
    except KeyError:
        return Issue(code="unknown_template", severity=Severity.error, item_index=index,
                     message_ko=f"항목 #{index + 1}: 지원하지 않는 구조물 종류입니다 ({spec.template}).")
    try:
        params = template.Params.model_validate(spec.params)
    except ValidationError as e:
        return Issue(code="invalid_params", severity=Severity.error, item_index=index,
                     message_ko=f"{_label(template, index)}: 파라미터가 허용 범위를 벗어났습니다.",
                     details={"errors": e.errors(include_url=False, include_context=False)})
    cons = _height_constraint(template, ctx) + decor_constraints(template, params, spec.decor, ctx.rule_ctx) + list(extra or [])
    params, issues = clamp_params(template, params, ctx.rule_ctx, cons, index, _label(template, index))
    return template, params, issues


def _attach_issues(items: list[BuiltItem]) -> list[Issue]:
    """attach_to 힌트를 지키지 못한 항목(대상 측면에 맞닿지 않음)은 일반 배치로 놓였다고 경고한다."""
    by_index = {it.index: it for it in items}
    out = []
    for it in items:
        if it.hint.attach_to is None or it.placement is None:
            continue
        idx, side = it.hint.attach_to
        target = by_index.get(idx)
        if target is None or target.placement is None:
            where = f"항목 #{idx + 1}"
        elif attach_satisfied(it, target, side):
            continue
        else:
            where = target.label_ko
        out.append(Issue(
            code="attach_fallback", severity=Severity.warning, item_index=it.index,
            related_index=idx if target is not None else None,
            message_ko=f"{it.label_ko}: {where} 옆에 붙일 자리가 없어 따로 놓았어요. 직접 옮겨 이어 주세요.",
            details={"attach_to": [idx, side]},
        ))
    return out


def _shrink_to_fit(items: list[BuiltItem], ctx: EngineContext, report: ValidationReport) -> None:
    gap = ctx.size_rules.gap_trap
    failed = place_all(items, ctx.cage, gap)
    tried: set[int] = set()
    while failed:
        item = next((f for f in failed if f.index not in tried), None)
        if item is None or item.template is None or not item.template.size_fields:
            break
        tried.add(item.index)
        t, base = item.template, item.params
        assert base is not None
        for factor in SHRINK_STEPS:
            p2, issues = clamp_params(t, shrink_params(t, base, factor), ctx.rule_ctx,
                                      _height_constraint(t, ctx), item.index, item.label_ko)
            if p2 == item.params or any(i.severity == Severity.error for i in issues):
                continue
            candidate = build_item(item.index, t, p2, item.hint, ctx.rules.printing, item.decor, ctx.rule_ctx)
            trial = [candidate if it.index == item.index else it for it in items]
            trial_failed = place_all(trial, ctx.cage, gap)
            if candidate.placement is not None and len(trial_failed) < len(failed):
                items[:] = trial
                failed = trial_failed
                report.extend([Issue(
                    code="resized_to_fit", severity=Severity.info, auto_fixed=True, item_index=item.index,
                    message_ko=f"{item.label_ko}: 케이지 공간이 부족해 크기를 {round(factor * 100)}% 로 줄였습니다.",
                    details={"factor": factor},
                )])
                break
        else:
            failed = place_all(items, ctx.cage, gap)  # 원래 상태로 배치 복원


def run_engine(specs: list[ItemSpec], ctx: EngineContext, measure_thickness: bool = True) -> EngineResult:
    report = ValidationReport()
    items: list[BuiltItem] = []
    # attach_to 대상(2층 집 등)을 먼저 보정해 두고, 붙는 항목(램프)은 대상의 최종 값에 맞춘다
    attached = {i for i, s in enumerate(specs) if s.hint.attach_to is not None}
    prepared_all: dict[int, tuple[Template, TemplateParams, list[Issue]] | Issue] = {}
    for i, spec in enumerate(specs):
        if i not in attached:
            prepared_all[i] = _prepare(spec, i, ctx)
    targets = {i: (pr[0], pr[1]) for i, pr in prepared_all.items() if not isinstance(pr, Issue)}
    for i in attached:
        spec = specs[i]
        try:
            template = get_template(spec.template)
        except KeyError:
            template = None
        extra = attach_constraints(template, spec.hint, targets) if template is not None else []
        prepared_all[i] = _prepare(spec, i, ctx, extra)
    for i, spec in enumerate(specs):
        prepared = prepared_all[i]
        if isinstance(prepared, Issue):
            report.extend([prepared])
            continue
        template, params, issues = prepared
        report.extend(issues)
        try:
            items.append(build_item(i, template, params, spec.hint, ctx.rules.printing, spec.decor, ctx.rule_ctx))
        except Exception as e:  # 형상 커널 오류 등
            log.exception("build failed: %s", spec)
            report.extend([Issue(code="build_failed", severity=Severity.error, item_index=i,
                                 message_ko=f"{_label(template, i)}: 형상 생성에 실패했습니다 ({type(e).__name__}).")])

    _shrink_to_fit(items, ctx, report)
    for it in items:  # 장식을 줄이거나 뺀 경고 (공간 보정으로 다시 만든 항목은 그때의 결과)
        report.extend(it.decor_issues)
    report.extend(_attach_issues(items))
    report.extend(validate_all(
        items, ctx.cage, ctx.size_rules, ctx.rules.printing, ctx.min_wall_mm,
        count=ctx.count, measure_thickness_mesh=measure_thickness,
    ))
    items.sort(key=lambda it: it.index)
    return EngineResult(items=items, report=report)


def revalidate(items: list[BuiltItem], ctx: EngineContext) -> ValidationReport:
    """저장된 파라미터·배치 그대로 다시 만든 형상을 검증한다.

    처음 설계할 때(run_engine)와 같은 기준이지만 보정·축소·재배치는 하지 않는다. 고치면 저장된 버전과 다른
    설계가 되므로, 지금 템플릿 제약을 벗어난 파라미터도 자동 보정 대신 오류로 남긴다."""
    report = ValidationReport()
    by_index = {it.index: it for it in items}
    for it in items:
        if it.template is not None and it.params is not None:
            extra = _height_constraint(it.template, ctx) + attach_constraints(it.template, it.hint, by_index)
            report.extend(constraint_violations(it.template, it.params, ctx.rule_ctx, extra, it.index, it.label_ko))
    report.extend(validate_all(
        items, ctx.cage, ctx.size_rules, ctx.rules.printing, ctx.min_wall_mm, count=ctx.count,
    ))
    return report
