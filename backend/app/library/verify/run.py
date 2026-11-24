"""검증 실행 (설계 §7): 변형 → P 검사 → 변형마다 G·C 검사 → 시험 조립 → R 검사 → 면제 → 요약.

어느 Template 에도 쓴다. DSL 초안은 draft(부품 파일 dict)를 함께 주면 registry.overlay 로 잠시 등록해 엔진·해석기·LLM
스키마가 찾게 하고, 새 프로세스 다시 만들기(G12)와 작업 프로세스도 그 dict 로 같은 템플릿을 만든다. 코드 부품은
등록된 인스턴스를 그대로 쓴다 (tests/test_part_contract.py 의 계약 검사).

검사 묶음:
- 변형마다: G01–G09, G11 (모든 도달 가능한 변형), C01–C08 (기본값·min/max·선택 변형), G10 (기본값·min/max),
  G12 (크기 구분마다 마릿수 1 기본값; 결과가 골든)
- 부품 하나: P1–P4, T01–T02, R01–R04, C08 의 통로 자리 모음 (각 attach_order.passage 자리가 적어도 한 변형에서 통로이거나
  열 수 있는지)

jobs > 1 이면 형상 검사를 ProcessPoolExecutor(spawn) 로 나눠 돌린다. 작업 프로세스의 initializer 가 같은 템플릿을
만들고 overlay 를 건다. 결과는 변형 순서대로 모은다. 다른 프로세스에서 만들 수 없는 템플릿(등록되지 않은 시험용 코드
템플릿)은 한 프로세스로 돌리고 새 프로세스 다시 만들기(G12 의 세 번째 빌드)를 건너뛴다.
"""

from __future__ import annotations

import dataclasses
import json
import os
import time
from collections.abc import Iterable, Mapping
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from typing import Any, Literal

from app.library.verify import anchors as A
from app.library.verify import geometry as G
from app.library.verify import honesty as H
from app.library.verify import trials as T
from app.library.verify import variants as V
from app.library.verify.report import (
    CheckResult,
    RunSummary,
    apply_waivers,
    failed,
    now_iso,
    passed,
    rules_digest,
)
from app.templates.base import Template

ALL_CHECKS: tuple[str, ...] = (
    "P1", "P2", "P3", "P4",
    "G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10", "G11", "G12",
    "C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08",
    "T01", "T02", "R01", "R02", "R03", "R04",
)
# 코드 부품 계약 검사 (§7.6): quick 프로필의 C01–C08, G02, G04–G08, G11, G12
CONTRACT_CHECKS: tuple[str, ...] = ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08",
                                    "G02", "G04", "G05", "G06", "G07", "G08", "G11", "G12")
CONNECTION_KINDS = ("default", "min", "max", "choice")
ENGINE_KINDS = ("default", "min", "max")
SCHEMA_PART_MAX = 2_300
SCHEMA_TOTAL_MAX = 29_000
BUILD_DEFAULT_MAX_S = 3.0
CONSTRAINTS_MAX_S = 0.002


def _rules(rules: Any | None) -> Any:
    if rules is not None:
        return rules
    from app.config import BACKEND_DIR
    from app.rules.loader import load_rules

    return load_rules(BACKEND_DIR / "rules")


def _registered(t: Template) -> bool:
    from app.templates.registry import primitives

    return primitives().get(t.key) is t


def _draft_dict(t: Template, draft: Mapping[str, Any] | None) -> dict | None:
    """새 프로세스·작업 프로세스가 같은 템플릿을 만들 부품 파일 dict. 등록된 템플릿이면 None (key 로 찾는다)."""
    if draft is not None:
        return dict(draft)
    if _registered(t):
        return None
    pf = getattr(t, "part_file", None)
    if pf is None:
        return None  # 등록되지 않은 코드 템플릿 (시험용): 다른 프로세스에서 만들 수 없다
    return pf.model_dump(mode="json", exclude_unset=True)


# ── 변형 하나의 형상·연결 검사 (작업 프로세스에서도 돈다) ──


def variant_checks(t: Template, v: V.Variant, rules: Any, want: frozenset[str], draft: dict | None,
                   subprocess: bool = True) -> tuple[list[CheckResult], dict[str, Any] | None, float]:
    """(결과, 골든 {params, files} 또는 None, 만드는 데 걸린 초)."""
    assert v.params is not None
    out: list[CheckResult] = []
    ctx = V.rule_ctx(rules, v.species, v.size, v.count)
    p = v.params
    b = G.build(t, p, rules.printing)
    out.append(G.check_build(b, v.id))
    if b.item is None:
        # 만들지 못하면 요청하지 않은 검사 묶음(계약 검사)에서도 실패로 남긴다
        return [r for r in out if r.id in want or not r.ok], None, b.seconds
    it = b.item
    if "G02" in want:
        out += G.check_meshes(it, v.id)
    if "G03" in want:
        out.append(G.check_volume(it, v.id))
    if "G04" in want:
        out += G.check_bed(it, rules.printing, v.id)
    if "G05" in want:
        out += G.check_overhang(it, rules.printing, v.id)
    if "G06" in want:
        out += G.check_walls(it, ctx, v.id)
    if "G07" in want:
        out.append(G.check_envelope(t, p, b, v.id))
    if "G08" in want:
        out.append(H.check_gap_trap(it.mesh, ctx.size, v.id))
    if "G09" in want:
        out += H.feature_honesty(t, p, it.mesh, ctx.size, v.id)
    if "G11" in want:
        out.append(H.check_stability(it.mesh, v.id))
    if "G10" in want and v.kind in ENGINE_KINDS:
        out.append(G.check_engine(t, p, rules, v.species, v.size, v.count, v.id, extra_keys=(t.key,)))
    if any(c.startswith("C") for c in want) and v.kind in CONNECTION_KINDS:
        only = {c: True for c in want if c.startswith("C")}
        out += A.connection_checks(t, p, variant=v.id, only=only)
    golden = None
    if "G12" in want and v.kind == "default" and v.count == 1:
        res, files = G.check_determinism(t, p, rules.printing, it, v.id, draft=draft, subprocess=subprocess)
        out.append(res)
        golden = {"params": p.model_dump(mode="json"), "files": files}
    return [r for r in out if r.id in want], golden, b.seconds


# 작업 프로세스 상태 (initializer 가 채운다)
_WORKER: dict[str, Any] = {}


def _worker_init(key: str, draft: dict | None, rules_dir: str, subprocess: bool) -> None:
    from app.rules.loader import load_rules
    from app.templates import registry

    if draft is not None:
        from app.library.template import make_template

        t = make_template(draft, key=key)
        # 이 프로세스가 끝날 때까지 등록해 둔다. 문맥 관리자를 붙잡아 둔다: 버리면 생성기가 닫히며 finally 가
        # 등록을 바로 지운다 (작업 프로세스의 G10 이 unknown_template 로 실패했다)
        cm = registry.overlay({key: t})
        cm.__enter__()
        _WORKER["overlay"] = cm
    else:
        t = registry.get_template(key)
    _WORKER.update(t=t, rules=load_rules(rules_dir), draft=draft, subprocess=subprocess)


def _worker_task(v: V.Variant, want: frozenset[str]) -> tuple[list[CheckResult], dict | None, float]:
    t = _WORKER["t"]
    if v.params is not None and not isinstance(v.params, t.Params):
        v = dataclasses.replace(v, params=t.Params.model_validate(v.params))
    return variant_checks(t, v, _WORKER["rules"], want, _WORKER["draft"], _WORKER["subprocess"])


# ── 실행 ──


def verify(t: Template, *, rules: Any | None = None, profile: V.Profile = "full", species: str | None = None,
           jobs: int | None = None, draft: Mapping[str, Any] | None = None, checks: Iterable[str] | None = None,
           waivers: Mapping[str, str] | None = None, trials: bool = True, subprocess: bool = True,
           trial_mode: Literal["all", "quick"] | None = None) -> RunSummary:
    """부품 하나를 검증한다. checks: 돌릴 검사 id (None: 모두). waivers: 코드 부품 면제 (check id → 사유)."""
    from app.templates import registry

    rules = _rules(rules)
    want = frozenset(checks or ALL_CHECKS)
    started, t0 = now_iso(), time.perf_counter()
    run = RunSummary(key=t.key, profile=profile, started_at=started, habitats=list(V.template_habitats(t)))
    raw = _draft_dict(t, draft)
    registered = _registered(t)
    if raw is None and not registered:
        jobs, subprocess = 1, False  # 다른 프로세스가 같은 템플릿을 만들 수 없다 (시험용 템플릿)
    overlay = registry.overlay({t.key: t}) if not registered else nullcontext()
    with overlay:
        variants = V.generate(t, rules, profile, species)
        run.variants = len(variants)
        run.unreachable = [v.id for v in variants if v.unreachable]
        results: list[CheckResult] = []
        if want & {"P1", "P2", "P3", "P4"}:
            results += [r for r in V.param_checks(t, rules, variants) if r.id in want]
        reach = V.reachable(variants)
        geo, goldens, seconds = _geometry(t, reach, rules, want, raw, jobs, subprocess)
        results += geo
        if "C08" in want and t.composable:
            results += _passage_coverage(t, reach)
        cases = V.size_cases(t, rules, species)
        if trials and want & {"T01", "T02"} and t.role in ("accessory", "host", "room_host"):
            mode = trial_mode or ("quick" if profile == "quick" else "all")
            tr = _trials(t, rules, cases, mode)
            results += [r for r in T.trial_checks(tr) if r.id in want]
            if "T01" in want:
                results += T.engine_check(tr, t.key, rules)
            run.trials = [r.summary() for r in tr]
        used = rule_fields_used(t, rules, cases)
        run.rule_fields_used = sorted(used)
        excluded = _null_rule_sizes(rules, cases, used)
        if "R03" in want:
            results.append(_coverage(cases, excluded))
        if "R04" in want:
            results += _performance(t, rules, cases, seconds)
        if "R01" in want:
            r01, schema = schema_contract(t, rules, cases)
            results += r01
            run.schema = schema
        if "R02" in want:
            results += i18n_conflicts(t, raw)
    results = apply_waivers(results, waivers)
    run.results = results
    run.golden = {f"{c.species}/{c.size}/default": g for c, g in goldens.items()}
    bad_sizes = {r.variant.split("/")[0] + "/" + r.variant.split("/")[1] for r in run.failures
                 if r.variant and r.variant.count("/") >= 2}
    verified: dict[str, list[str]] = {}
    for c in cases:
        cs = f"{c.species}/{c.size}"
        if cs in excluded or cs in bad_sizes or (not run.ok and not bad_sizes):
            continue
        verified.setdefault(c.species, []).append(c.size)
        run.rules_digest[cs] = rules_digest(rules, c.species, c.size, used)
    run.verified_for = verified
    run.seconds = time.perf_counter() - t0
    return run


def _geometry(t: Template, reach: list[V.Variant], rules: Any, want: frozenset[str], draft: dict | None,
              jobs: int | None, subprocess: bool) -> tuple[list[CheckResult], dict[V.SizeCase, dict], dict[str, float]]:
    geo_want = frozenset(c for c in want if c[0] in "GC")
    if not geo_want or not reach:
        return [], {}, {}
    jobs = jobs if jobs is not None else min(4, os.cpu_count() or 1)
    outs: list[tuple[list[CheckResult], dict | None, float]]
    if jobs <= 1 or len(reach) == 1:
        outs = [variant_checks(t, v, rules, geo_want, draft, subprocess) for v in reach]
    else:
        import multiprocessing

        payload = [dataclasses.replace(v, params=v.dump()) for v in reach]  # 모델 대신 dict 로 넘긴다
        with ProcessPoolExecutor(max_workers=min(jobs, len(reach)), mp_context=multiprocessing.get_context("spawn"),
                                 initializer=_worker_init,
                                 initargs=(t.key, draft, str(rules.source_dir), subprocess)) as pool:
            outs = list(pool.map(_worker_task, payload, [geo_want] * len(payload)))
    results: list[CheckResult] = []
    goldens: dict[V.SizeCase, dict] = {}
    seconds: dict[str, float] = {}
    for v, (res, golden, sec) in zip(reach, outs, strict=True):
        results += res
        seconds[v.id] = sec
        if golden is not None:
            goldens[V.SizeCase(v.species, v.size, "")] = golden
    return results, goldens, seconds


def _passage_coverage(t: Template, reach: list[V.Variant]) -> list[CheckResult]:
    names = t.attach_order.get("passage", ())
    if not names:
        return []
    seen: set[str] = set()
    for v in reach:
        assert v.params is not None
        seen |= A.passage_capable(t, v.params)
    out = []
    for n in names:
        ptr = f"/attach_order/passage/{n}"
        out.append(passed("C08", None, path=ptr) if n in seen else
                   failed("C08", None, f"passage anchor {n} is never a port and never openable in any variant",
                          path=ptr, hint="remove it from attach_order.passage or give it a door/opens entry"))
    return out


def _trials(t: Template, rules: Any, cases: list[V.SizeCase], mode: str) -> list[T.TrialResult]:
    from app.templates.registry import primitives

    templates = primitives()
    out: list[T.TrialResult] = []
    for c in cases:
        if c.habitat != "cage":
            continue  # 조립 항목은 케이지 전용 (어항 묶음에는 기준 부품이 없다)
        ctx = V.fit_ctx(rules, c.species, c.size, 1)
        for tr in T.generate(t.key, t, templates, ctx, quick=mode == "quick"):
            out.append(T.run_trial(tr, templates, rules, c.species, c.size))
    return out


# ── R03: 쓴 규칙 필드 ──


class _RecordingSize:
    """SizeRules 를 감싸 읽은 필드 이름을 적는다 (코드 부품의 rule_fields_used)."""

    _SKIP = frozenset({"display_name", "aquatic"})

    def __init__(self, size: Any, used: set[str]) -> None:
        object.__setattr__(self, "_size", size)
        object.__setattr__(self, "_used", used)

    def __getattr__(self, name: str) -> Any:
        if name not in self._SKIP and not name.startswith("_"):
            self._used.add(name)
        return getattr(self._size, name)

    def __hash__(self) -> int:
        return hash(self._size)

    def __eq__(self, other: object) -> bool:
        return self._size == (other._size if isinstance(other, _RecordingSize) else other)


def rule_fields_used(t: Template, rules: Any, cases: list[V.SizeCase]) -> set[str]:
    compiled = getattr(t, "compiled", None)
    if compiled is not None:
        return set(compiled.rule_fields)
    used: set[str] = set()
    for c in cases:
        for count in (1, 2):
            base = V.fit_ctx(rules, c.species, c.size, count)
            ctx = dataclasses.replace(base, size=_RecordingSize(base.size, used))
            try:
                p = t.default_params(ctx)
                t.constraints(p, ctx)
                t.rule_issues(p, ctx)
                t.assembly_constraints(p, ctx)
                for name in t.anchors(p):
                    t.joined_constraints(p, ctx, name)
            except Exception:  # noqa: BLE001,S112 - P 검사가 따로 알린다
                continue
    return used - {"min_wall_thickness_mm", "hideout_min_entrances"}


def _null_rule_sizes(rules: Any, cases: list[V.SizeCase], used: set[str]) -> set[str]:
    out = set()
    for c in cases:
        size = rules.size_rules(c.species, c.size)
        for name in used:
            v: Any = size
            for part in name.split("."):
                v = getattr(v, part, None)
                if v is None:
                    break
            if v is None:
                out.add(f"{c.species}/{c.size}")
    return out


def _coverage(cases: list[V.SizeCase], excluded: set[str]) -> CheckResult:
    kept = [c for c in cases if f"{c.species}/{c.size}" not in excluded]
    if not kept:
        return failed("R03", None, "no size defines every rule field the part reads",
                      hint="use only rule fields defined for the sizes of the target species")
    msg = f"excluded (null rule field): {sorted(excluded)}" if excluded else ""
    return passed("R03", None, message=msg)


# ── R04: 성능 ──


def _performance(t: Template, rules: Any, cases: list[V.SizeCase], seconds: Mapping[str, float]) -> list[CheckResult]:
    out = []
    for c in cases:
        vid = f"{c.species}/{c.size}/c1/default"
        sec = seconds.get(vid)
        if sec is not None:
            out.append(passed("R04", vid, path="/build", value=sec, limit=BUILD_DEFAULT_MAX_S)
                       if sec <= BUILD_DEFAULT_MAX_S else
                       failed("R04", vid, f"default build takes {sec:.2f} s", path="/build", value=sec,
                              limit=BUILD_DEFAULT_MAX_S))
        ctx = V.fit_ctx(rules, c.species, c.size, 1)
        p = t.default_params(ctx)
        times = []
        for _ in range(21):
            t0 = time.perf_counter()
            t.constraints(p, ctx)
            times.append(time.perf_counter() - t0)
        med = sorted(times)[len(times) // 2]
        out.append(passed("R04", vid, path="/constraints", value=med * 1000, limit=CONSTRAINTS_MAX_S * 1000)
                   if med <= CONSTRAINTS_MAX_S else
                   failed("R04", vid, f"one constraints evaluation takes {med * 1000:.2f} ms", path="/constraints",
                          value=med * 1000, limit=CONSTRAINTS_MAX_S * 1000))
    return out


# ── R01: LLM 계약 ──


def _schema_len(keys: Iterable[str]) -> int:
    from app.llm.spec import api_schema

    return len(json.dumps(api_schema(tuple(keys)), ensure_ascii=False))


def schema_contract(t: Template, rules: Any, cases: list[V.SizeCase]) -> tuple[list[CheckResult], dict[str, Any]]:
    """R01: 부품 모델이 만들어지고, 종 카탈로그 + 부품 스키마가 예산 안이며, 카탈로그 문구·최소 명세가 읽힌다.
    총량(29,000)을 넘는 종은 실패가 아니라 gate_ok=False (그 종에는 아직 넣지 않는다)."""
    from app.llm.prompts import template_catalog
    from app.llm.spec import _item_model, _part_model, parse_spec

    out: list[CheckResult] = []
    schema: dict[str, Any] = {"chars_added": None, "totals": {}, "gate_ok": {}}
    try:
        _item_model(t, False)
        if t.composable:
            _part_model(t)
        template_catalog([t.key])
    except Exception as e:  # noqa: BLE001
        return [failed("R01", None, f"LLM models or catalog failed: {type(e).__name__}: {e}")], schema
    added: list[int] = []
    for sp in dict.fromkeys(c.species for c in cases):
        base = tuple(k for k in rules.allowed_templates(sp) if k != t.key)
        with_part = base + (t.key,)
        total = _schema_len(with_part)
        add = total - _schema_len(base) if base else total
        added.append(add)
        schema["totals"][sp] = total
        schema["gate_ok"][sp] = total <= SCHEMA_TOTAL_MAX
        try:
            parse_spec(json.dumps(_minimal_spec(t, with_part, rules, sp, cases), ensure_ascii=False), with_part)
        except Exception as e:  # noqa: BLE001
            out.append(failed("R01", f"{sp}", f"a minimal spec with defaults does not parse: {str(e)[:300]}"))
    schema["chars_added"] = max(added) if added else None
    if added and max(added) > SCHEMA_PART_MAX:
        out.append(failed("R01", None, f"the part adds {max(added)} chars to the LLM schema", path="/description",
                          value=float(max(added)), limit=float(SCHEMA_PART_MAX),
                          hint="shorten descriptions and choice lists"))
    elif not any(not r.ok for r in out):
        out.append(passed("R01", None, value=float(max(added)) if added else None,
                          limit=float(SCHEMA_PART_MAX) if added else None))
    return out, schema


def _minimal_spec(t: Template, keys: tuple[str, ...], rules: Any, sp: str, cases: list[V.SizeCase]) -> dict:
    from app.llm.spec import ATTACH_TEMPLATES

    size = next(c.size for c in cases if c.species == sp)
    p = t.default_params(V.fit_ctx(rules, sp, size, 1))
    placement: dict[str, Any] = {"zone": "auto", "group": None, "rotation": None}
    if all(k in keys for k in ATTACH_TEMPLATES):
        placement["attach_to"] = None
    return {"summary_ko": "verify", "items": [{"template": t.key, "params": p.model_dump(mode="json"),
                                             "placement": placement, "reason_ko": "verify"}],
            "notes_ko": [], "missing_parts": []}


# ── R02: 문구 ──


def i18n_conflicts(t: Template, raw: Mapping[str, Any] | None) -> list[CheckResult]:
    """DSL 부품의 한국어 → 영어 짝이 이미 있는 카탈로그 항목과 다르지 않은지 (같은 한국어, 다른 영어)."""
    part = raw
    if part is None and getattr(t, "part_file", None) is not None:
        from app.library import index

        part = index.read_part(t.key) if index.entry(t.key) is not None else \
            t.part_file.model_dump(mode="json", exclude_unset=True)  # type: ignore[attr-defined]
    if part is None:
        return []
    from pathlib import Path

    from app.library import index

    entries: dict[str, str] = {}
    root = Path(__file__).resolve().parents[2] / "i18n" / "en"
    for f in sorted(root.glob("*.json")):
        if f.name == "library.json" and index.entry(t.key) is None:
            pass  # 게시 전 초안도 이미 게시된 부품 문구와 겹치면 안 된다
        entries.update(json.loads(f.read_text(encoding="utf-8")))
    out = []
    for ko, en in index.part_pairs(dict(part)):
        have = entries.get(ko)
        if have is not None and have != en:
            out.append(failed("R02", None, f"{ko!r} is already translated as {have!r}, not {en!r}",
                              hint="reuse the existing English text or change the Korean text"))
    return out or [passed("R02", None)]
