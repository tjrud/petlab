"""검증 변형 (설계 §7.1)과 파라미터 검사 P1–P4 (§7.2).

종(species.yaml)마다, 크기 구분마다 엔진과 같은 규칙 문맥(EngineContext.rule_ctx·fit_ctx)을 만들고 그 위에서
파라미터 변형을 만든다:

| 변형 id | 파라미터 | 마릿수 |
|---|---|---|
| <sp>/<size>/c1/default, c2/default | default_params(ctx) | 1, 2 |
| …/c1/min:<f>, …/c1/max:<f> | 기본값에서 숫자 필드 f 만 필드 경계로 | 1 |
| …/c1/choice:<f>=<v> | 선택 필드의 값마다 | 1 |
| …/c1/bool:<f>=<v> | 참거짓 필드의 값마다 | 1 |
| …/c1/seed<k> (k=0..3) | 필드 경계 안에서 고르게 (정수는 정수로) | 1 |

모든 변형은 clamp_params(…, max_passes=8) 를 거친다. param_conflict 가 남는 변형(또는 모델 검증에 실패한 변형)은
unreachable 로 적고 형상 검사를 건너뛴다 (P2 가 다룬다). 보정 뒤 같은 파라미터가 된 변형은 하나로 합친다.
quick 프로필은 기본값(c1, c2)과 선택 변형만 만든다.

필드는 점 표기 경로로 다룬다 (코드 부품의 중첩 Params: "roof.kind", "walls.thickness_mm"). 목록 필드는 변형하지 않는다.
"""

from __future__ import annotations

import hashlib
import random
import typing
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.library.verify.report import CheckResult, failed, passed
from app.templates.base import RuleContext, Template, TemplateParams
from app.validation.autofix import clamp_params, field_bounds, get_path, set_path
from app.validation.report import Issue

Profile = Literal["quick", "full"]
SEEDS = 4
P2_LONG_PASSES = 40
P2_SHORT_PASSES = 8

# 검증 엔진 문맥의 케이지 (넉넉한 케이지: 공간 부족 축소가 결과를 바꾸지 않게)
VERIFY_CAGE_MM = (1000.0, 600.0, 400.0)


@dataclass(frozen=True)
class Leaf:
    """변형할 수 있는 Params 필드 하나 (점 표기 경로)."""

    path: str
    kind: Literal["number", "integer", "choice", "bool"]
    lo: float | None = None
    hi: float | None = None
    choices: tuple[Any, ...] = ()


@dataclass(frozen=True)
class SizeCase:
    species: str
    size: str
    habitat: str


@dataclass
class Variant:
    """변형 하나. params 는 보정 뒤 값 (unreachable 이면 보정 전 값 또는 None)."""

    id: str
    species: str
    size: str
    count: int
    kind: str  # default | min | max | choice | bool | seed
    field_path: str | None
    params: TemplateParams | None
    issues: list[Issue] = field(default_factory=list)
    unreachable: str | None = None  # 형상 검사를 건너뛰는 까닭 (param_conflict, invalid)
    aliases: list[str] = field(default_factory=list)  # 보정 뒤 같은 파라미터가 되어 합친 변형 id

    @property
    def case(self) -> str:
        return f"{self.species}/{self.size}"

    @property
    def is_default(self) -> bool:
        return self.kind == "default"

    def dump(self) -> dict[str, Any] | None:
        return None if self.params is None else self.params.model_dump(mode="json")


# ── 규칙 문맥 ──


def engine_context(rules: Any, species: str, size: str, count: int = 1, extra_keys: tuple[str, ...] = ()):
    """검증용 엔진 문맥 (VerifyEngineContext). rule_ctx·fit_ctx 가 엔진과 같은 값이 되도록 엔진 클래스를 그대로 쓴다."""
    from app.domain import Cage
    from app.library.verify.engine_ctx import VerifyEngineContext

    return VerifyEngineContext(Cage(*VERIFY_CAGE_MM), species, size, count, rules, extra_templates=extra_keys)


def rule_ctx(rules: Any, species: str, size: str, count: int = 1) -> RuleContext:
    return engine_context(rules, species, size, count).rule_ctx


def fit_ctx(rules: Any, species: str, size: str, count: int = 1) -> RuleContext:
    return engine_context(rules, species, size, count).fit_ctx


def template_habitats(t: Template) -> tuple[str, ...]:
    """부품이 쓰이는 사육 환경. DSL 부품은 파일의 habitats, 코드 부품은 HABITAT_TEMPLATES 에 든 곳."""
    pf = getattr(t, "part_file", None)
    if pf is not None:
        return tuple(pf.habitats)
    declared = getattr(t, "habitats", None)  # 시험용 템플릿처럼 사육 환경을 직접 적은 템플릿
    if declared is not None:
        return tuple(declared)
    from app.rules.loader import HABITAT_TEMPLATES

    return tuple(h for h, keys in HABITAT_TEMPLATES.items() if t.key in keys)


def size_cases(t: Template, rules: Any, species: str | None = None) -> list[SizeCase]:
    """검증할 (종, 크기 구분). DSL 부품(초안 포함)·사육 환경을 직접 적은 템플릿은 사육 환경이 맞는 모든 종,
    코드 부품은 그 부품을 허용하는 종."""
    habitats = set(template_habitats(t))
    dsl = getattr(t, "part_file", None) is not None or getattr(t, "habitats", None) is not None
    out = []
    for sp, entry in rules.species_file.species.items():
        if species is not None and sp != species:
            continue
        if entry.habitat not in habitats:
            continue
        if not dsl and t.key not in entry.allowed_templates:
            continue
        out.extend(SizeCase(sp, size, entry.habitat) for size in entry.sizes)
    return out


# ── 필드 ──


def leaves(cls: type[BaseModel], prefix: str = "") -> list[Leaf]:
    """변형할 수 있는 필드 (선언 순서). 숫자는 경계가 둘 다 있을 때만 min/max·무작위 변형을 만든다."""
    out: list[Leaf] = []
    for name, info in cls.model_fields.items():
        path = f"{prefix}{name}"
        ann = info.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            out.extend(leaves(ann, path + "."))
            continue
        if typing.get_origin(ann) is Literal:
            out.append(Leaf(path, "choice", choices=tuple(typing.get_args(ann))))
        elif ann is bool:
            out.append(Leaf(path, "bool", choices=(False, True)))
        elif ann in (int, float):
            lo, hi = _bounds(cls, name)
            out.append(Leaf(path, "integer" if ann is int else "number", lo, hi))
    return out


def _bounds(cls: type[BaseModel], name: str) -> tuple[float | None, float | None]:
    return field_bounds(cls, name)  # type: ignore[arg-type]


def _with(t: Template, base: TemplateParams, updates: dict[str, Any]) -> TemplateParams:
    d = base.model_dump()
    for path, v in updates.items():
        set_path(d, path, v)
    return t.Params.model_validate(d)


def _seed(key: str, sp: str, size: str, k: int) -> int:
    return int(hashlib.sha256(f"{key}|{sp}|{size}|{k}".encode()).hexdigest()[:8], 16)


def _random_updates(rng: random.Random, fields: list[Leaf]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields:
        if f.kind in ("choice", "bool"):
            out[f.path] = rng.choice(f.choices)
        elif f.lo is not None and f.hi is not None:
            if f.kind == "integer":
                out[f.path] = rng.randint(int(f.lo), int(f.hi))
            else:
                out[f.path] = round(rng.uniform(f.lo, f.hi), 3)
    return out


def _candidates(t: Template, key: str, case: SizeCase, profile: Profile, ctx1: RuleContext, ctx2: RuleContext
                ) -> Iterator[tuple[str, int, str, str | None, Any]]:
    """(id, count, kind, field, 파라미터 또는 만들지 못한 까닭 문자열)."""
    base = f"{case.species}/{case.size}"
    yield f"{base}/c1/default", 1, "default", None, _safe(lambda: t.default_params(ctx1))
    yield f"{base}/c2/default", 2, "default", None, _safe(lambda: t.default_params(ctx2))
    default = t.default_params(ctx1)
    fields = leaves(t.Params)
    if profile == "full":
        for f in fields:
            if f.kind in ("number", "integer"):
                for kind, v in (("min", f.lo), ("max", f.hi)):
                    if v is not None:
                        v = int(v) if f.kind == "integer" else float(v)
                        yield f"{base}/c1/{kind}:{f.path}", 1, kind, f.path, _safe(lambda v=v, f=f: _with(t, default, {f.path: v}))
    for f in fields:
        if f.kind == "choice":
            for v in f.choices:
                yield f"{base}/c1/choice:{f.path}={v}", 1, "choice", f.path, _safe(lambda v=v, f=f: _with(t, default, {f.path: v}))
        elif f.kind == "bool" and profile == "full":
            for v in f.choices:
                yield (f"{base}/c1/bool:{f.path}={str(v).lower()}", 1, "bool", f.path,
                       _safe(lambda v=v, f=f: _with(t, default, {f.path: v})))
    if profile == "full":
        for k in range(SEEDS):
            rng = random.Random(_seed(key, case.species, case.size, k))
            yield f"{base}/c1/seed{k}", 1, "seed", None, _safe(lambda rng=rng: _with(t, default, _random_updates(rng, fields)))


def _safe(make):
    try:
        return make()
    except ValidationError as e:
        return f"invalid params: {e.errors(include_url=False)[0].get('msg', 'invalid')}"


def generate(t: Template, rules: Any, profile: Profile = "full", species: str | None = None,
             key: str | None = None) -> list[Variant]:
    """변형 목록 (변형 id 순서는 만드는 순서; 보정 뒤 같은 파라미터는 처음 것에 합친다)."""
    key = key or t.key
    out: list[Variant] = []
    seen: dict[tuple[str, int, str], Variant] = {}
    for case in size_cases(t, rules, species):
        ctxs = {n: fit_ctx(rules, case.species, case.size, n) for n in (1, 2)}
        for vid, count, kind, fld, raw in _candidates(t, key, case, profile, ctxs[1], ctxs[2]):
            if isinstance(raw, str):
                out.append(Variant(vid, case.species, case.size, count, kind, fld, None, unreachable=raw))
                continue
            try:
                p, issues = clamp_params(t, raw, ctxs[count], max_passes=P2_SHORT_PASSES)
            except Exception as e:
                if getattr(e, "code", None) != "DSL006":
                    raise
                out.append(Variant(vid, case.species, case.size, count, kind, fld, raw))
                continue
            conflict = [i for i in issues if i.code == "param_conflict"]
            v = Variant(vid, case.species, case.size, count, kind, fld, p, issues,
                        unreachable="param_conflict: " + conflict[0].message_ko if conflict else None)
            if v.unreachable is None and kind != "default":
                sig = (case.species + "/" + case.size, count, p.model_dump_json())
                if sig in seen:
                    seen[sig].aliases.append(vid)
                    continue
                seen[sig] = v
            elif v.unreachable is None:
                seen[(case.species + "/" + case.size, count, p.model_dump_json())] = v
            out.append(v)
    return out


def reachable(variants: list[Variant]) -> list[Variant]:
    return [v for v in variants if v.unreachable is None and v.params is not None]


# ── P1–P4 ──


def param_checks(t: Template, rules: Any, variants: list[Variant]) -> list[CheckResult]:
    """P1 기본값이 보정 없이 맞는지, P2 보정이 수렴하는지, P3 rule_issues, P4 식·제약 계산 오류."""
    out: list[CheckResult] = []
    for v in variants:
        ctx = fit_ctx(rules, v.species, v.size, v.count)
        if v.is_default:
            if v.params is None:
                out.append(failed("P1", v.id, f"default_params failed: {v.unreachable}"))
            else:
                changed = [i for i in v.issues if i.code in ("param_adjusted", "param_conflict")]
                if changed:
                    i = changed[0]
                    out.append(failed("P1", v.id, f"defaults are not feasible: {i.code} {i.details.get('field')} "
                                                  f"{i.details.get('from', i.details.get('value'))} → "
                                                  f"{i.details.get('to', '')}".strip(),
                                      path=_param_ptr(i.details.get("field")),
                                      hint="make the default (or rule_default) satisfy every constraint"))
                else:
                    out.append(passed("P1", v.id))
        if v.params is None:
            continue
        # P2: 8 패스와 40 패스가 같은 값 (보정 전 값에서 다시)
        try:
            long, _ = clamp_params(t, v.params, ctx, max_passes=P2_LONG_PASSES)
            again, _ = clamp_params(t, v.params, ctx, max_passes=P2_SHORT_PASSES)
        except Exception as e:  # noqa: BLE001 - 어떤 예외든 실패로 적는다
            if getattr(e, "code", None) == "DSL006":  # 식 계산 오류: P4 (보정이 아니라 식을 고쳐야 한다)
                out.append(failed("P4", v.id, f"evaluation failed ({e.code}): {e}", path=getattr(e, "path", None),
                                  hint=getattr(e, "hint", "") or "guard the expression for every value in the "
                                                                  "field bounds"))
                continue
            out.append(failed("P2", v.id, f"clamp raised {type(e).__name__}: {e}"))
            continue
        if long != again:
            diff = _diff(again.model_dump(), long.model_dump())
            out.append(failed("P2", v.id, f"autofix does not converge in {P2_SHORT_PASSES} passes: {diff}",
                              hint="a constraint chain needs more passes; make bounds depend on fewer fields"))
        else:
            out.append(passed("P2", v.id))
        if v.unreachable is not None:
            continue
        # P3: rule_issues 가 예외 없이, 기본값은 빈 목록
        try:
            issues = t.rule_issues(v.params, ctx)
        except Exception as e:  # noqa: BLE001
            out.append(failed("P3", v.id, f"rule_issues raised {type(e).__name__}: {e}"))
        else:
            if v.is_default and issues:
                out.append(failed("P3", v.id, f"rule_issues on defaults: {issues[0]}"))
            else:
                out.append(passed("P3", v.id))
        # P4: 형상 범위의 식·특징·연결 지점 계산 (DSL006 등)
        out.append(_evaluation(t, v, ctx))
    return out


def _evaluation(t: Template, v: Variant, ctx: RuleContext) -> CheckResult:
    p = v.params
    assert p is not None
    try:
        t.constraints(p, ctx)
        t.features(p)
        t.anchors(p)
        if t.composable:
            t.envelope(p)
            t.face_needs(p)
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", None)
        return failed("P4", v.id, f"evaluation failed ({code or type(e).__name__}): {e}",
                      path=getattr(e, "path", None), hint=getattr(e, "hint", "") or "")
    return passed("P4", v.id)


def _param_ptr(path: str | None) -> str | None:
    if not path:
        return None
    return "/params/" + path.split(".")[0]


def _diff(a: dict, b: dict) -> str:
    from app.validation.autofix import _leaves

    out = []
    for p, va in _leaves(a):
        vb = get_path(b, p)
        if va != vb:
            out.append(f"{p}: {va} vs {vb}")
    return "; ".join(out[:3])
