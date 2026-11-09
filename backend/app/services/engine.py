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
from app.rules.loader import BuoyancyRules, Habitat, PrintingRules, RuleBook, SizeRules
from app.templates.base import ParamConstraint, RuleContext, Template, TemplateParams
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
        return RuleContext(self.size_rules, self.min_wall_mm, self.count)

    @property
    def height_limit_mm(self) -> float | None:
        """어항: 구조물 최대 높이 (물 깊이 − 구조물 위 최소 물 깊이). 케이지는 None."""
        aquatic = self.size_rules.aquatic
        return None if aquatic is None else self.cage.height_mm - aquatic.structure_top_clearance_mm

    @property
    def fit_ctx(self) -> RuleContext:
        """새 설계를 보정할 때 쓰는 규칙 문맥. 어항이면 높이 한도를 함께 줘, 높이를 맞추려고 다른 값도 바꿔야 하는
        템플릿(물속 동굴의 지붕)이 그 값을 조정하게 한다. 저장된 버전을 다시 검증할 때(revalidate)는 rule_ctx 를 쓴다."""
        return RuleContext(self.size_rules, self.min_wall_mm, self.count, height_limit_mm=self.height_limit_mm)

    @property
    def habitat(self) -> Habitat:
        """사육 환경 (cage / aquarium)."""
        return self.rules.habitat(self.species)

    @property
    def allowed_templates(self) -> tuple[str, ...]:
        """이 종에 만들 수 있는 템플릿 키."""
        return self.rules.allowed_templates(self.species)

    @property
    def buoyancy(self) -> BuoyancyRules | None:
        """물속 무게 계산용 밀도 (어항 종만)."""
        return self.rules.buoyancy(self.species)

    @property
    def species_name(self) -> str:
        return self.rules.display_names(self.species, self.size)[0]


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


def _height_constraint(template: Template, ctx: EngineContext, params: TemplateParams) -> list[ParamConstraint]:
    aquatic = ctx.size_rules.aquatic
    if aquatic is not None:
        # 어항: Cage.height_mm 은 물 깊이(바닥재 위 ~ 수면). 구조물 위로 헤엄쳐 지나가고 수면 가까이에서 숨 쉴 물 깊이를 남긴다.
        # 높이 파라미터가 없는 템플릿(터널)도 높이를 정하는 파라미터(내경·벽 두께)로 맞춘다
        if _min_water_depth(template, ctx) is not None:
            return []  # 가장 낮게 만들어도 들어가지 않는다: _too_shallow 가 오류 하나로 알린다
        c = aquatic.structure_top_clearance_mm
        limit = ctx.cage.height_mm - c
        return template.height_limit_constraints(
            params, ctx.rule_ctx, limit,
            f"생물이 구조물 위로 지나가고 수면 가까이에서 숨 쉴 수 있도록 높이를 {limit:g}mm(물 깊이 − {c:g}mm) "
            "이하로 맞췄습니다.",
        )
    if not template.height_field:
        return []
    P = ctx.size_rules.gap_trap.passable_min_mm
    limit = ctx.cage.height_mm - P
    return [ParamConstraint(
        template.height_field, max=limit, source="geometry",
        reason_ko=f"케이지 천장과의 틈에 끼이지 않도록 높이를 {limit:g}mm(천장 높이 − {P:g}mm) 이하로 맞췄습니다.",
    )]


def _min_water_depth(template: Template, ctx: EngineContext) -> tuple[float, float] | None:
    """어항: 이 템플릿을 가장 낮게 만들어도 높이 한도(물 깊이 − 구조물 위 최소 물 깊이)를 넘으면
    (그 최소 높이, 필요한 물 깊이). 들어가거나 케이지면 None."""
    aquatic = ctx.size_rules.aquatic
    limit = ctx.height_limit_mm
    if aquatic is None or limit is None:
        return None
    need = template.min_height_mm(ctx.rule_ctx)
    if need is None or need <= limit + 1e-6:
        return None
    return need, need + aquatic.structure_top_clearance_mm


def _too_shallow(template: Template, ctx: EngineContext, index: int, label: str) -> Issue | None:
    """물이 얕아 이 구조물을 어떻게 만들어도 위에 물 깊이를 남길 수 없으면 오류 하나 (높이 보정 문구 대신)."""
    found = _min_water_depth(template, ctx)
    if found is None:
        return None
    need, depth_need = found
    aquatic = ctx.size_rules.aquatic
    assert aquatic is not None
    c = aquatic.structure_top_clearance_mm
    return Issue(
        code="water_too_shallow", severity=Severity.error, item_index=index,
        message_ko=(f"{label}: 물 깊이 {ctx.cage.height_mm:g}mm 로는 만들 수 없습니다. 생물이 구조물 위로 지나가고 "
                    f"수면 가까이에서 숨 쉴 수 있도록 위에 {c:g}mm 를 남기면, 가장 낮게 만들어도 높이가 {need:g}mm 라 "
                    f"물 깊이가 {depth_need:g}mm 이상이어야 합니다."),
        details={"water_depth_mm": ctx.cage.height_mm, "min_water_depth_mm": depth_need, "min_height_mm": need,
                 "clearance_mm": c},
    )


def _label(template: Template, index: int) -> str:
    return f"{template.display_name_ko} #{index + 1}"


def _not_allowed(label: str, index: int, key: str, ctx: EngineContext) -> Issue:
    """이 종(사육 환경)에 만들 수 없는 구조물 (예: 어항의 램프·모래목욕통, 물속에서 공기가 갇히는 은신처)."""
    return Issue(code="template_not_allowed", severity=Severity.error, item_index=index,
                 message_ko=f"{label}: {ctx.species_name}에는 만들 수 없는 구조물입니다.",
                 details={"template": key, "allowed": list(ctx.allowed_templates)})


def _prepare(spec: ItemSpec, index: int, ctx: EngineContext) -> tuple[Template, TemplateParams, list[Issue]] | Issue:
    try:
        template = get_template(spec.template)
    except KeyError:
        return Issue(code="unknown_template", severity=Severity.error, item_index=index,
                     message_ko=f"항목 #{index + 1}: 지원하지 않는 구조물 종류입니다 ({spec.template}).")
    if template.key not in ctx.allowed_templates:
        return _not_allowed(_label(template, index), index, template.key, ctx)
    try:
        params = template.Params.model_validate(spec.params)
    except ValidationError as e:
        return Issue(code="invalid_params", severity=Severity.error, item_index=index,
                     message_ko=f"{_label(template, index)}: 파라미터가 허용 범위를 벗어났습니다.",
                     details={"errors": e.errors(include_url=False, include_context=False)})
    label = _label(template, index)
    params, issues = clamp_params(template, params, ctx.fit_ctx, _height_constraint(template, ctx, params),
                                  index, label)
    shallow = _too_shallow(template, ctx, index, label)
    return template, params, issues + ([shallow] if shallow is not None else [])


def _shrink_to_fit(items: list[BuiltItem], ctx: EngineContext, report: ValidationReport) -> None:
    gap = ctx.size_rules.gap_trap
    aquarium = ctx.size_rules.aquatic is not None
    # 어항: 휜 터널처럼 사각형이 아닌 바닥 윤곽 사이의 실제 틈도 피한다 (케이지 배치 결과는 그대로 둔다)
    failed = place_all(items, ctx.cage, gap, exact_gaps=aquarium)
    tried: set[int] = set()
    while failed:
        item = next((f for f in failed if f.index not in tried), None)
        if item is None or item.template is None or not item.template.size_fields:
            break
        tried.add(item.index)
        t, base = item.template, item.params
        assert base is not None
        for factor in SHRINK_STEPS:
            shrunk = shrink_params(t, base, factor)
            p2, issues = clamp_params(t, shrunk, ctx.fit_ctx, _height_constraint(t, ctx, shrunk),
                                      item.index, item.label_ko)
            if p2 == item.params or any(i.severity == Severity.error for i in issues):
                continue
            candidate = build_item(item.index, t, p2, item.hint, ctx.rules.printing)
            trial = [candidate if it.index == item.index else it for it in items]
            trial_failed = place_all(trial, ctx.cage, gap, exact_gaps=aquarium)
            if candidate.placement is not None and len(trial_failed) < len(failed):
                items[:] = trial
                failed = trial_failed
                pct = round(factor * 100)
                msg = (f"{item.label_ko}: 수조 공간이 부족해 크기를 {pct}% 로 줄였습니다." if aquarium
                       else f"{item.label_ko}: 케이지 공간이 부족해 크기를 {pct}% 로 줄였습니다.")
                report.extend([Issue(
                    code="resized_to_fit", severity=Severity.info, auto_fixed=True, item_index=item.index,
                    message_ko=msg, details={"factor": factor},
                )])
                break
        else:
            failed = place_all(items, ctx.cage, gap, exact_gaps=aquarium)  # 원래 상태로 배치 복원


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
        count=ctx.count, measure_thickness_mesh=measure_thickness, buoyancy=ctx.buoyancy,
    ))
    items.sort(key=lambda it: it.index)
    return EngineResult(items=items, report=report)


def revalidate(items: list[BuiltItem], ctx: EngineContext) -> ValidationReport:
    """저장된 파라미터·배치 그대로 다시 만든 형상을 검증한다.

    처음 설계할 때(run_engine)와 같은 기준이지만 보정·축소·재배치는 하지 않는다. 고치면 저장된 버전과 다른
    설계가 되므로, 지금 템플릿 제약을 벗어난 파라미터도 자동 보정 대신 오류로 남긴다."""
    report = ValidationReport()
    allowed = ctx.allowed_templates
    for it in items:
        if it.key not in allowed:
            # 이 종에 없는 구조물은 제약을 계산하지 않는다 (예: 어항 크기 구분에는 램프·모래목욕통 기준 값이 없다)
            report.extend([_not_allowed(it.label_ko, it.index, it.key, ctx)])
            continue
        if it.template is not None and it.params is not None:
            shallow = _too_shallow(it.template, ctx, it.index, it.label_ko)
            if shallow is not None:
                report.extend([shallow])
            report.extend(constraint_violations(it.template, it.params, ctx.rule_ctx,
                                                _height_constraint(it.template, ctx, it.params), it.index, it.label_ko))
    report.extend(validate_all(
        items, ctx.cage, ctx.size_rules, ctx.rules.printing, ctx.min_wall_mm, count=ctx.count,
        buoyancy=ctx.buoyancy,
    ))
    return report
