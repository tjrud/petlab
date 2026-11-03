"""자동 보정.

1) 파라미터 보정: 템플릿 허용 범위·종 규칙·상호 제약을 위반한 값을 경계로 옮긴다(클램프).
2) 공간 보정: 케이지에 놓을 자리가 없으면 크기 파라미터를 단계적으로 줄인다 (엔진에서 사용).
보정할 수 없는 충돌은 error 이슈로 남긴다.
"""

from __future__ import annotations

import math

from annotated_types import Ge, Gt, Le, Lt
from pydantic import ValidationError

from app.templates.base import ParamConstraint, RuleContext, Template, TemplateParams
from app.validation.report import Issue, Severity

MAX_PASSES = 8


def field_bounds(params_cls: type[TemplateParams], name: str) -> tuple[float | None, float | None]:
    lo = hi = None
    for m in params_cls.model_fields[name].metadata:
        if isinstance(m, (Ge, Gt)):
            lo = float(m.ge if isinstance(m, Ge) else m.gt)
        elif isinstance(m, (Le, Lt)):
            hi = float(m.le if isinstance(m, Le) else m.lt)
    return lo, hi


def _is_int_field(params_cls: type[TemplateParams], name: str) -> bool:
    return params_cls.model_fields[name].annotation is int


def _fmt(v: float) -> str:
    return f"{v:g}" if isinstance(v, int) or float(v).is_integer() else f"{v:.1f}"


def clamp_params(
    template: Template,
    params: TemplateParams,
    ctx: RuleContext,
    extra: list[ParamConstraint] | None = None,
    item_index: int | None = None,
    label_ko: str | None = None,
) -> tuple[TemplateParams, list[Issue]]:
    """제약 위반 값을 경계로 옮긴다. 반환: (보정된 파라미터, 이슈 목록)."""
    cls = template.Params
    label = label_ko or template.display_name_ko
    values = params.model_dump()
    original = dict(values)
    reasons: dict[str, str] = {}
    unresolved: dict[str, ParamConstraint] = {}

    for _ in range(MAX_PASSES):
        current = cls.model_validate(values)
        cons = template.constraints(current, ctx) + list(extra or [])
        changed = False
        unresolved = {}
        for c in cons:
            v = values[c.field]
            if not c.violates(v):
                continue
            target = c.min if (c.min is not None and v < c.min) else c.max
            assert target is not None
            if _is_int_field(cls, c.field):
                target = math.ceil(target - 1e-9) if c.min is not None and v < c.min else math.floor(target + 1e-9)
            lo, hi = field_bounds(cls, c.field)
            clipped = target
            if lo is not None:
                clipped = max(clipped, lo)
            if hi is not None:
                clipped = min(clipped, hi)
            if clipped != target:
                unresolved[c.field] = c  # 템플릿 허용 범위를 벗어나야만 만족 가능
            if clipped != v:
                values[c.field] = clipped
                reasons[c.field] = c.reason_ko
                changed = True
        if not changed:
            break

    issues: list[Issue] = []
    for f, new in values.items():
        old = original[f]
        if new != old:
            issues.append(Issue(
                code="param_adjusted",
                severity=Severity.info,
                auto_fixed=True,
                item_index=item_index,
                message_ko=f"{label}: {_desc(cls, f)} {_fmt(old)} → {_fmt(new)} 로 보정했습니다. {reasons.get(f, '')}".strip(),
                details={"field": f, "from": old, "to": new},
            ))

    # 남은 위반 (경계끼리 충돌하거나 템플릿 범위 밖)
    try:
        final = cls.model_validate(values)
    except ValidationError as e:  # pragma: no cover - 위 클리핑으로 범위 안이 보장됨
        raise RuntimeError(f"보정 후 파라미터가 유효하지 않습니다: {e}") from e
    for c in template.constraints(final, ctx) + list(extra or []):
        if c.violates(getattr(final, c.field)):
            issues.append(Issue(
                code="param_conflict",
                severity=Severity.error,
                item_index=item_index,
                message_ko=f"{label}: {_desc(cls, c.field)} 조건을 만족시킬 수 없습니다. {c.reason_ko}",
                details={"field": c.field, "value": getattr(final, c.field), "min": c.min, "max": c.max},
            ))
    return final, issues


def constraint_violations(
    template: Template,
    params: TemplateParams,
    ctx: RuleContext,
    extra: list[ParamConstraint] | None = None,
    item_index: int | None = None,
    label_ko: str | None = None,
) -> list[Issue]:
    """값을 고치지 않고 제약 위반만 error 로 알린다 (저장된 버전을 다시 검증할 때: 고치면 다른 설계가 된다)."""
    cls = template.Params
    label = label_ko or template.display_name_ko
    out = []
    for c in template.constraints(params, ctx) + list(extra or []):
        v = getattr(params, c.field)
        if c.violates(v):
            out.append(Issue(
                code="param_out_of_range",
                severity=Severity.error,
                item_index=item_index,
                message_ko=(f"{label}: {_desc(cls, c.field)} {_fmt(v)} 이(가) 지금 기준 허용 범위를 벗어납니다. "
                            f"{c.reason_ko}").strip(),
                details={"field": c.field, "value": v, "min": c.min, "max": c.max},
            ))
    return out


def _desc(cls: type[TemplateParams], name: str) -> str:
    d = cls.model_fields[name].description or name
    return d.split(".")[0].replace(" mm", "")


def shrink_params(template: Template, params: TemplateParams, factor: float) -> TemplateParams:
    """크기 파라미터(size_fields)를 factor 배로 줄인다 (템플릿 허용 범위 하한까지)."""
    values = params.model_dump()
    for f in template.size_fields:
        lo, _ = field_bounds(template.Params, f)
        v = values[f] * factor
        values[f] = max(v, lo) if lo is not None else v
    return template.Params.model_validate(values)
