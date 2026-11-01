"""설계 엔진: 항목 명세 → (파라미터 보정 → 형상 생성 → 배치 → 공간 보정 → 검증).

LLM·DB 와 독립적인 순수 계산 단계다. LLM 이 낸 명세(템플릿·파라미터·배치 힌트)를 받아
검증된 템플릿 코드로 형상을 만들고, 자동 검증 보고서를 붙여 돌려준다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.domain import BuiltItem, Cage, PlacementHint, mesh_footprint
from app.geometry.mesh import part_to_mesh, to_print_orientation
from app.layout.placer import place_all
from app.rules.loader import PrintingRules, RuleBook, SizeRules
from app.templates.base import ParamConstraint, RuleContext, Template, TemplateParams
from app.templates.registry import get_template
from app.validation.autofix import clamp_params, shrink_params
from app.validation.checks import validate_all
from app.validation.report import Issue, Severity, ValidationReport

log = logging.getLogger(__name__)

SHRINK_STEPS = (0.9, 0.8, 0.7, 0.6, 0.5)


@dataclass(frozen=True)
class ItemSpec:
    template: str
    params: dict
    hint: PlacementHint = field(default_factory=PlacementHint)


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
        return RuleContext(self.size_rules, self.min_wall_mm)


@dataclass
class EngineResult:
    items: list[BuiltItem]
    report: ValidationReport


def build_item(
    index: int, template: Template, params: TemplateParams, hint: PlacementHint, printing: PrintingRules
) -> BuiltItem:
    part = template.build(params)
    mesh = part_to_mesh(part, printing.tessellation_tolerance_mm, printing.tessellation_angular_tolerance_deg)
    lo, hi = mesh.bounds
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    return BuiltItem(
        index=index,
        key=template.key,
        features=template.features(params),
        mesh=mesh,
        print_mesh=to_print_orientation(mesh, template.print_rotation(params)),
        footprint=mesh_footprint(mesh),
        hint=hint,
        template=template,
        params=params,
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


def _prepare(spec: ItemSpec, index: int, ctx: EngineContext) -> tuple[Template, TemplateParams, list[Issue]] | Issue:
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
    params, issues = clamp_params(template, params, ctx.rule_ctx, _height_constraint(template, ctx),
                                  index, _label(template, index))
    return template, params, issues


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
            candidate = build_item(item.index, t, p2, item.hint, ctx.rules.printing)
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
    for i, spec in enumerate(specs):
        prepared = _prepare(spec, i, ctx)
        if isinstance(prepared, Issue):
            report.extend([prepared])
            continue
        template, params, issues = prepared
        report.extend(issues)
        try:
            items.append(build_item(i, template, params, spec.hint, ctx.rules.printing))
        except Exception as e:  # 형상 커널 오류 등
            log.exception("build failed: %s", spec)
            report.extend([Issue(code="build_failed", severity=Severity.error, item_index=i,
                                 message_ko=f"{_label(template, i)}: 형상 생성에 실패했습니다 ({type(e).__name__}).")])

    _shrink_to_fit(items, ctx, report)
    report.extend(validate_all(
        items, ctx.cage, ctx.size_rules, ctx.rules.printing, ctx.min_wall_mm,
        count=ctx.count, measure_thickness_mesh=measure_thickness,
    ))
    items.sort(key=lambda it: it.index)
    return EngineResult(items=items, report=report)
