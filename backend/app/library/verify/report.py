"""검증 결과와 보고서 (설계 §7.2, §7.7). 가벼운 모듈이다 (형상 커널을 불러오지 않는다).

- CheckResult: 검사 하나의 결과 (id, 통과 여부, 변형 id, JSON 포인터, 값·한도, 영어 메시지·고치는 방법).
- rules_digest / library_versions / code_digests: 보고서가 "어떤 규칙·라이브러리·코드로 검증했는지" 적는 값.
- build_report: 실행 하나의 보고서 dict (reports/<key>.json 의 목록 항목 하나). 파일에 덧붙이는 일은 publish (T9) 몫이다.
- format_text: CLI 요약 (표 한 줄 + 실패 10개까지).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

VERIFIER = "verify/1"

# 보고서에 버전을 적는 라이브러리 (regolden --library-upgrade 가 이 값이 바뀌었을 때만 골든을 다시 만든다).
# 배포 이름이 설치 방식마다 달라 후보를 차례로 찾는다 (첫 이름이 보고서의 키)
LIBRARIES: dict[str, tuple[str, ...]] = {
    "build123d": ("build123d",),
    "cadquery-ocp": ("cadquery-ocp", "cadquery-ocp-novtk", "cadquery-ocp-proxy"),
    "trimesh": ("trimesh",),
    "numpy": ("numpy",),
}

# 보고서 "code" 에 적는 DSL 해석 모듈 (fingerprint.DSL_MODULES 와 같은 목록)
DSL_CODE_MODULES: tuple[str, ...] = ("app.library.template", "app.library.ops", "app.library.expr",
                                     "app.library.schema", "app.templates.tunnel")

# 검사 id 와 한 줄 설명 (§7.2). S·L 검사는 정적 검사(T8/T9)라 여기서는 이름만 둔다
CHECKS: dict[str, str] = {
    "P1": "defaults are feasible (clamp makes no change)",
    "P2": "autofix converges (8 passes == 40 passes)",
    "P3": "rule_issues raises nothing and is empty for defaults",
    "P4": "no evaluation error in a reachable variant",
    "G01": "build succeeds within the time limit",
    "G02": "print parts are watertight single bodies on the bed",
    "G03": "build volume equals the sum of print-part volumes",
    "G04": "print parts fit the build volume",
    "G05": "support-free in the declared print rotation",
    "G06": "wall thickness (designed, measured, declared)",
    "G07": "envelope matches the mesh; centred; on the floor",
    "G08": "self gap-trap scan with a floor plane",
    "G09": "feature honesty (climb, slope, opening probes, vent sizes)",
    "G10": "engine run without errors or safety warnings",
    "G11": "static stability (tipping angle)",
    "G12": "deterministic bytes in process and in a fresh process",
    "G13": "through-openings: declared holes only, none in the trap band",
    "C01": "anchor frames",
    "C02": "anchors on the surface, normals outward",
    "C03": "mounts are backed by a flat face",
    "C04": "doors open into usable space",
    "C05": "door profile family",
    "C06": "face fields move the anchor",
    "C07": "open_port makes a door; doors stay as they are",
    "C08": "attach_order anchors suit their kind; analytic envelope",
    "T01": "trial compositions resolve, converge and pass the rules",
    "T02": "trial time budgets",
    "R01": "LLM contract and schema budget",
    "R02": "i18n pairs do not conflict with the catalog",
    "R03": "rule coverage (rule fields used)",
    "R04": "performance (default build, constraints)",
}


@dataclass(frozen=True)
class CheckResult:
    """검사 하나의 결과. ok=False 면 실패. waived: 코드 부품의 면제 사유 (그때 ok 는 True 로 둔다)."""

    id: str
    ok: bool
    variant: str | None = None
    path: str | None = None
    value: float | None = None
    limit: float | None = None
    message: str = ""
    hint: str = ""
    waived: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None and v != ""}


def passed(cid: str, variant: str | None = None, **kw: Any) -> CheckResult:
    return CheckResult(cid, True, variant, **kw)


def failed(cid: str, variant: str | None, message: str, **kw: Any) -> CheckResult:
    return CheckResult(cid, False, variant, message=message, **kw)


def failures(results: Iterable[CheckResult]) -> list[CheckResult]:
    return [r for r in results if not r.ok]


def apply_waivers(results: Iterable[CheckResult], waivers: Mapping[str, str] | None) -> list[CheckResult]:
    """면제(check id → 사유)가 있는 실패를 통과로 바꾸고 사유를 적는다. 사유가 비면 ValueError (R6: 사유 없는 면제 금지)."""
    waivers = dict(waivers or {})
    for cid, why in waivers.items():
        if not str(why).strip():
            raise ValueError(f"waiver for {cid} needs a written reason")
    out = []
    for r in results:
        why = waivers.get(r.id)
        if why is not None and not r.ok:
            r = CheckResult(**{**asdict(r), "ok": True, "waived": why})
        out.append(r)
    return out


# ── 보고서가 적는 환경 값 ──


def canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def library_versions() -> dict[str, str]:
    from importlib import metadata

    out: dict[str, str] = {}
    for name, candidates in LIBRARIES.items():
        for dist in candidates:
            try:
                out[name] = metadata.version(dist)
                break
            except metadata.PackageNotFoundError:
                continue
        else:
            out[name] = "missing"
    return out


def code_digests(modules: Sequence[str] = DSL_CODE_MODULES) -> dict[str, str]:
    from app.geometry.fingerprint import _module_digest

    return {m: _module_digest(m) for m in modules}


def _plain(v: Any) -> Any:
    if hasattr(v, "model_dump"):
        return v.model_dump(mode="json")
    if isinstance(v, tuple):
        return [_plain(x) for x in v]
    return v


def rules_digest(rules: Any, species: str, size: str, used: Iterable[str]) -> str:
    """크기 구분 하나의 규칙 지문: 쓴 규칙 필드, 최소 벽, 은신처 최소 출입구 수, 출력 규칙 (§7.7).
    상관없는 species.yaml 수정은 지문을 바꾸지 않는다."""
    sr = rules.size_rules(species, size)
    fields: dict[str, Any] = {}
    for name in sorted(set(used)):
        v: Any = sr
        for part in name.split("."):
            v = getattr(v, part, None)
            if v is None:
                break
        fields[name] = _plain(v)
    data = {
        "fields": fields,
        "min_wall_thickness_mm": sr.min_wall_thickness_mm,
        "hideout_min_entrances": _plain(sr.hideout_min_entrances),
        "printing": rules.printing.model_dump(mode="json"),
    }
    return sha256_text(canonical(data))


def worst_of(results: Iterable[CheckResult]) -> dict[str, dict[str, Any]]:
    """검사 id 마다 한도에 가장 가까운(또는 가장 많이 넘은) 값. 한도가 상한인지 하한인지는 값이 한도 쪽에 있는지로 본다:
    통과한 값들 중 한도와의 차이가 가장 작은 것, 실패가 있으면 첫 실패."""
    best: dict[str, CheckResult] = {}
    for r in results:
        if r.value is None or r.limit is None:
            continue
        cur = best.get(r.id)
        if cur is None:
            best[r.id] = r
            continue
        if not r.ok and cur.ok or r.ok == cur.ok and abs(r.value - r.limit) < abs(cur.value - cur.limit):
            best[r.id] = r
    return {k: {"variant": v.variant, "value": v.value, "limit": v.limit} for k, v in sorted(best.items())}


@dataclass
class RunSummary:
    """검증 실행 하나의 결과 (run.verify 가 돌려준다)."""

    key: str
    profile: str
    results: list[CheckResult] = field(default_factory=list)
    variants: int = 0
    unreachable: list[str] = field(default_factory=list)
    verified_for: dict[str, list[str]] = field(default_factory=dict)
    rule_fields_used: list[str] = field(default_factory=list)
    rules_digest: dict[str, str] = field(default_factory=dict)
    schema: dict[str, Any] = field(default_factory=dict)
    trials: list[dict[str, Any]] = field(default_factory=list)
    golden: dict[str, dict[str, Any]] = field(default_factory=dict)
    habitats: list[str] = field(default_factory=list)
    seconds: float = 0.0
    started_at: str = ""

    @property
    def failures(self) -> list[CheckResult]:
        return failures(self.results)

    @property
    def ok(self) -> bool:
        return not self.failures


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_report(run: RunSummary, *, file_sha256: str | None = None, dsl: int | None = None) -> dict[str, Any]:
    """reports/<key>.json 에 덧붙일 실행 하나 (§7.7). 코드 부품은 file_sha256·dsl 이 None 이다."""
    report: dict[str, Any] = {
        "verifier": VERIFIER,
        "profile": run.profile,
        "key": run.key,
        "dsl": dsl,
        "file_sha256": file_sha256,
        "code": code_digests(),
        "libraries": library_versions(),
        "rules_digest": dict(sorted(run.rules_digest.items())),
        "started_at": run.started_at,
        "seconds": round(run.seconds, 1),
        "result": "pass" if run.ok else "fail",
        "habitats": list(run.habitats),
        "verified_for": {k: list(v) for k, v in sorted(run.verified_for.items())},
        "rule_fields_used": list(run.rule_fields_used),
        "schema": run.schema,
        "counts": {"variants": run.variants, "unreachable": len(run.unreachable), "checks": len(run.results),
                   "failed": len(run.failures)},
        "worst": worst_of(run.results),
        "failures": [r.as_dict() for r in run.failures],
        "waived": [r.as_dict() for r in run.results if r.waived],
        "unreachable": list(run.unreachable),
        "trials": list(run.trials),
        "golden": dict(sorted(run.golden.items())),
    }
    return report


def format_text(run: RunSummary, max_failures: int = 10) -> str:
    """CLI 출력: 요약 표, 그 아래 실패 max_failures 개까지 (id, 변형, 경로, 값/한도, 고치는 방법)."""
    by_id: dict[str, list[int]] = {}
    for r in run.results:
        c = by_id.setdefault(r.id, [0, 0])
        c[0 if r.ok else 1] += 1
    lines = [(f"{run.key}  profile={run.profile}  result={'pass' if run.ok else 'FAIL'}  "
              f"variants={run.variants} unreachable={len(run.unreachable)}  {run.seconds:.1f}s"),
             f"{'check':<6}{'pass':>7}{'fail':>7}  description"]
    for cid in sorted(by_id, key=_check_order):
        ok, bad = by_id[cid]
        lines.append(f"{cid:<6}{ok:>7}{bad:>7}  {CHECKS.get(cid, '')}")
    fails = run.failures
    for r in fails[:max_failures]:
        where = " ".join(x for x in (r.variant or "", r.path or "") if x)
        vl = f" value={r.value:g} limit={r.limit:g}" if r.value is not None and r.limit is not None else ""
        lines.append(f"FAIL {r.id} {where}{vl}: {r.message}" + (f"  hint: {r.hint}" if r.hint else ""))
    if len(fails) > max_failures:
        lines.append(f"… {len(fails) - max_failures} more failures")
    return "\n".join(lines)


def _check_order(cid: str) -> tuple[int, str]:
    return ("SLPGCTR".find(cid[0]) if cid[0] in "SLPGCTR" else 9, cid)
