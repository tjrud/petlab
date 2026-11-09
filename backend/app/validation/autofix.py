"""자동 보정.

1) 파라미터 보정: 템플릿 허용 범위·종 규칙·상호 제약을 위반한 값을 경계로 옮긴다(클램프).
2) 공간 보정: 케이지에 놓을 자리가 없으면 크기 파라미터를 단계적으로 줄인다 (엔진에서 사용).
보정할 수 없는 충돌은 error 이슈로 남긴다.

제약의 field 는 점 표기 경로("roof.pitch_deg")로 중첩 Params(조립형 템플릿의 부품 모델) 안의 값을 가리킬 수 있다.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterator
from typing import Any

from annotated_types import Ge, Gt, Le, Lt
from pydantic import BaseModel, ValidationError

from app.templates.base import ParamConstraint, RuleContext, Template, TemplateParams
from app.validation.report import Issue, Severity

MAX_PASSES = 8


def _field_info(params_cls: type[BaseModel], path: str):
    """점 표기 경로("roof.pitch_deg")의 FieldInfo. 중첩 Params(부품 모델)를 따라 내려간다."""
    cls: type[BaseModel] = params_cls
    parts = path.split(".")
    for name in parts[:-1]:
        cls = cls.model_fields[name].annotation  # type: ignore[assignment]
    return cls.model_fields[parts[-1]]


def get_path(values: dict, path: str) -> Any:
    """model_dump() 결과에서 점 표기 경로의 값."""
    for name in path.split("."):
        values = values[name]
    return values


def set_path(values: dict, path: str, value: Any) -> None:
    *heads, last = path.split(".")
    for name in heads:
        values = values[name]
    values[last] = value


def _get_attr(params: BaseModel, path: str) -> Any:
    v: Any = params
    for name in path.split("."):
        v = getattr(v, name)
    return v


def field_bounds(params_cls: type[TemplateParams], name: str) -> tuple[float | None, float | None]:
    lo = hi = None
    for m in _field_info(params_cls, name).metadata:
        if isinstance(m, (Ge, Gt)):
            lo = float(m.ge if isinstance(m, Ge) else m.gt)
        elif isinstance(m, (Le, Lt)):
            hi = float(m.le if isinstance(m, Le) else m.lt)
    return lo, hi


def clip_to_field_bounds(params_cls: type[TemplateParams], name: str, value: float) -> float:
    """값을 필드의 기하적 허용 범위(Field ge/le) 안으로 자른다.

    하한 → 상한 순서로 자르고, 원래 값을 max/min 의 첫 인자로 둔다.
    그래서 경계 안쪽(또는 경계와 같은) 값은 원래 타입(int/float) 그대로 남는다.
    """
    lo, hi = field_bounds(params_cls, name)
    if lo is not None:
        value = max(value, lo)
    if hi is not None:
        value = min(value, hi)
    return value


def _all_constraints(
    template: Template, params: TemplateParams, ctx: RuleContext, extra: list[ParamConstraint] | None
) -> list[ParamConstraint]:
    """템플릿 제약 뒤에 호출자가 준 추가 제약(케이지 높이 등)을 붙인 전체 제약 목록."""
    return template.constraints(params, ctx) + list(extra or [])


def _violations(
    template: Template, params: TemplateParams, ctx: RuleContext, extra: list[ParamConstraint] | None
) -> Iterator[tuple[ParamConstraint, Any]]:
    """params 가 어기는 제약과 그 필드의 현재 값을 제약 목록 순서대로 내준다."""
    for c in _all_constraints(template, params, ctx, extra):
        v = _get_attr(params, c.field)
        if c.violates(v):
            yield c, v


def _is_int_field(params_cls: type[TemplateParams], name: str) -> bool:
    return _field_info(params_cls, name).annotation is int


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
    original = copy.deepcopy(values)
    reasons: dict[str, str] = {}

    for _ in range(MAX_PASSES):
        current = cls.model_validate(values)
        cons = _all_constraints(template, current, ctx, extra)
        changed = False
        for c in cons:
            # 패스 시작 시점(current)이 아니라 values 에서 읽는다: 같은 필드의 뒤 제약이 앞 제약이 바꾼 값을 본다
            v = get_path(values, c.field)
            if not c.violates(v):
                continue
            below = c.min is not None and v < c.min
            target = c.min if below else c.max
            assert target is not None
            if _is_int_field(cls, c.field):
                # 정수 필드는 허용 범위 안쪽으로 반올림한다 (하한은 올림, 상한은 내림)
                target = math.ceil(target - 1e-9) if below else math.floor(target + 1e-9)
            # 템플릿 허용 범위를 벗어나야만 만족할 수 있으면 경계에서 멈추고, 아래 param_conflict 로 남는다
            clipped = clip_to_field_bounds(cls, c.field, target)
            if clipped != v:
                set_path(values, c.field, clipped)
                reasons[c.field] = c.reason_ko
                changed = True
        if not changed:
            break

    issues: list[Issue] = []
    for f, new in _leaves(values):
        old = get_path(original, f)
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
    for c, v in _violations(template, final, ctx, extra):
        issues.append(Issue(
            code="param_conflict",
            severity=Severity.error,
            item_index=item_index,
            message_ko=f"{label}: {_desc(cls, c.field)} 조건을 만족시킬 수 없습니다. {c.reason_ko}",
            details={"field": c.field, "value": v, "min": c.min, "max": c.max},
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
    """값을 고치지 않고 제약 위반만 error 로 알린다 (저장된 버전을 다시 검증할 때: 고치면 다른 설계가 된다).

    막지 않는 제약(blocking=False, 나중에 더한 기준)은 error 대신 rule_changed 경고로 알린다."""
    cls = template.Params
    label = label_ko or template.display_name_ko
    out = []
    for c, v in _violations(template, params, ctx, extra):
        if not c.blocking:
            out.append(_rule_changed(cls, label, c, v, item_index))
            continue
        out.append(Issue(
            code="param_out_of_range",
            severity=Severity.error,
            item_index=item_index,
            message_ko=(f"{label}: {_desc(cls, c.field)} {_fmt(v)} 이(가) 지금 기준 허용 범위를 벗어납니다. "
                        f"{c.reason_ko}").strip(),
            details={"field": c.field, "value": v, "min": c.min, "max": c.max},
        ))
    return out


def _rule_changed(cls: type[TemplateParams], label: str, c: ParamConstraint, v: Any, item_index: int | None) -> Issue:
    return Issue(
        code="rule_changed",
        severity=Severity.warning,
        item_index=item_index,
        message_ko=(f"{label}: {_desc(cls, c.field)} {_fmt(v)} 이(가) 지금 기준을 넘습니다. {c.reason_ko.rstrip('.')}. "
                    "이 기준은 이 버전을 저장한 뒤에 생겨 이 버전을 막지는 않으며, 설계를 수정하면 새 기준으로 맞춰집니다."),
        details={"field": c.field, "value": v, "min": c.min, "max": c.max},
    )


def rule_change_notices(
    template: Template,
    params: TemplateParams,
    ctx: RuleContext,
    item_index: int | None = None,
    label_ko: str | None = None,
) -> list[Issue]:
    """저장된 파라미터가 나중에 더한 기준(blocking=False)을 넘는지: 설계 화면에 경고로만 보여 준다."""
    cls = template.Params
    label = label_ko or template.display_name_ko
    return [_rule_changed(cls, label, c, v, item_index)
            for c, v in _violations(template, params, ctx, None) if not c.blocking]


def _leaves(values: dict, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """중첩 dict 의 (점 표기 경로, 값). 목록 값은 하나의 잎으로 본다."""
    for k, v in values.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from _leaves(v, path + ".")
        else:
            yield path, v


def _desc(cls: type[TemplateParams], name: str) -> str:
    d = _field_info(cls, name).description or name
    return d.split(".")[0].replace(" mm", "")


def shrink_params(template: Template, params: TemplateParams, factor: float) -> TemplateParams:
    """크기 파라미터(size_fields)를 factor 배로 줄인다 (템플릿 허용 범위 하한까지)."""
    values = params.model_dump()
    for f in template.size_fields:
        lo, _ = field_bounds(template.Params, f)
        v = values[f] * factor
        values[f] = max(v, lo) if lo is not None else v
    return template.Params.model_validate(values)
