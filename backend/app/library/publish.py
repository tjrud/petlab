"""부품 라이브러리 게시 수명 주기 (설계 §8, §9.1, §9.6): publish, retire, block, unretire, reverify, regolden, audit,
demand, list.

- 게시된 부품 파일(parts/<key>.json)은 바꾸거나 지우지 않는다 (R3). 덮어쓰기·지우기 명령은 없다.
- index.json 은 라이브러리에서 유일하게 바뀌는 파일이다. 보고서(reports/<key>.json)는 실행을 덧붙이기만 한다.
- git 작업은 하지 않는다. species.yaml 에 넣을 줄과 돌릴 시험 명령, 관리자 화면에서 할 일을 출력한다.
- 서버는 이 모듈을 쓰지 않는다. 부품을 쓰는 일은 개발자 에이전트가 오프라인으로 한다 (AI 호출 없음, R5).

Library(root, i18n_path) 로 다른 라이브러리 폴더(시험의 임시 폴더)를 다룰 수 있다. 작업 동안 index.LIBRARY_DIR 을
그 폴더로 바꿔 두어 색인을 읽는 모듈(다음 버전 key, part_id 중복 검사, 문구 짝)이 같은 폴더를 본다.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.library import index
from app.library.index import (
    INDEX_FILE,
    PARTS_DIR,
    REPORTS_DIR,
    IndexEntry,
    IndexFile,
    parse_key,
    sha256_bytes,
)

APP_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = APP_DIR.parent
DEFAULT_I18N = APP_DIR / "i18n" / "en" / "library.json"
DRAFTS_DIR = BACKEND_DIR / "library_drafts"
VERIFY_PROFILE = "full"  # publish·reverify 가 돌리는 검증 (시험은 quick 으로 바꾼다)
# reverify --apply 가 실패한 부품을 폐기할 때 적는 까닭 (app/library/authoring.json; 사용자에게는 library.json 으로 번역된다)
REVERIFY_REASON: dict[str, str] = json.loads((APP_DIR / "library" / "authoring.json").read_text(encoding="utf-8"))[
    "reverify_reason"]
TEST_COMMAND = ("uv run pytest tests/test_library_published.py tests/test_part_contract.py tests/test_i18n.py "
                "tests/test_llm.py -q")
SCHEMA_TOTAL_MAX = 29_000


class PublishError(RuntimeError):
    """게시·폐기 작업을 거절한다 (이유는 메시지)."""


@dataclass(frozen=True)
class Library:
    """라이브러리 폴더 (index.json, parts/, reports/)와 영어 문구 파일."""

    root: Path
    i18n_path: Path

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_FILE

    def part_path(self, key: str) -> Path:
        return self.root / PARTS_DIR / f"{key}.json"

    def report_path(self, key: str) -> Path:
        return self.root / REPORTS_DIR / f"{key}.json"


def default_library() -> Library:
    return Library(index.library_dir(), DEFAULT_I18N)


def library_at(root: Path | str | None, i18n_path: Path | str | None = None) -> Library:
    """root 가 None 이면 저장소의 라이브러리. 다른 폴더면 문구 파일은 그 안의 library.i18n.json (저장소 파일을 건드리지 않게)."""
    if root is None:
        lib = default_library()
        return lib if i18n_path is None else Library(lib.root, Path(i18n_path))
    root = Path(root)
    same = root.resolve() == index.library_dir().resolve()
    default_i18n = DEFAULT_I18N if same else root / "library.i18n.json"
    return Library(root, Path(i18n_path) if i18n_path is not None else default_i18n)


@contextmanager
def using(lib: Library) -> Iterator[None]:
    """작업 동안 색인 모듈이 lib.root 를 읽게 한다."""
    old = index.LIBRARY_DIR
    index.LIBRARY_DIR = lib.root
    index.clear_cache()
    try:
        yield
    finally:
        index.LIBRARY_DIR = old
        index.clear_cache()


def init_library(root: Path) -> Library:
    """빈 라이브러리 폴더를 만든다 (시험·새 저장소). 이미 있으면 그대로 둔다."""
    (root / PARTS_DIR).mkdir(parents=True, exist_ok=True)
    (root / REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    if not (root / INDEX_FILE).exists():
        (root / INDEX_FILE).write_text(index.dump_index({"v": 1, "parts": {}}), encoding="utf-8")
    return library_at(root)


# ── 읽기·쓰기 ──

def read_index(lib: Library) -> dict[str, Any]:
    raw = json.loads(lib.index_path.read_text(encoding="utf-8"))
    IndexFile.model_validate(raw)  # 형식 확인
    return raw


def write_index(lib: Library, data: Mapping[str, Any]) -> None:
    IndexFile.model_validate(data)
    lib.index_path.write_text(index.dump_index(dict(data)), encoding="utf-8")
    index.clear_cache()


def read_reports(lib: Library, key: str) -> list[dict[str, Any]]:
    p = lib.report_path(key)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise PublishError(f"{p.name}: a report file is a JSON list")
    return data


def append_report(lib: Library, key: str, report: Mapping[str, Any]) -> None:
    """보고서 목록 끝에 실행 하나를 덧붙인다 (앞의 실행은 바꾸지 않는다)."""
    runs = read_reports(lib, key) + [dict(report)]
    lib.report_path(key).parent.mkdir(parents=True, exist_ok=True)
    lib.report_path(key).write_text(json.dumps(runs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def latest_report(lib: Library, key: str) -> dict[str, Any] | None:
    runs = read_reports(lib, key)
    return runs[-1] if runs else None


def canonical_part(draft: Mapping[str, Any], key: str, version: int) -> str:
    """게시 파일의 정규 JSON: 열쇠 순서 dsl, key, family, version, 그다음 초안 순서. 들여쓰기 2, 끝에 줄바꿈."""
    obj: dict[str, Any] = {"dsl": draft["dsl"], "key": key, "family": draft["family"], "version": version}
    obj.update({k: v for k, v in draft.items() if k not in obj and not str(k).startswith("_")})
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def i18n_text(lib: Library) -> str:
    """영어 문구 파일의 내용: 색인의 모든 부품의 한국어 → 영어 짝 (한국어 순, 들여쓰기 2)."""
    with using(lib):
        pairs = index.i18n_pairs()
    return json.dumps(pairs, ensure_ascii=False, indent=2) + "\n"


def write_i18n(lib: Library) -> None:
    lib.i18n_path.parent.mkdir(parents=True, exist_ok=True)
    lib.i18n_path.write_text(i18n_text(lib), encoding="utf-8")


def today() -> str:
    return datetime.now(UTC).date().isoformat()


# ── 템플릿 ──

def template_for(lib: Library, key: str) -> tuple[Any, dict | None]:
    """게시된 부품의 템플릿과 (등록되지 않았으면) 그 파일 dict. 레지스트리에 같은 key 가 있으면 그것을 쓴다."""
    from app.library.template import make_template
    from app.templates.registry import primitives

    with using(lib):
        part = index.read_part(key)
        e = index.entry(key)
    reg = primitives().get(key)
    if reg is not None and lib.root.resolve() == (APP_DIR / "library").resolve():
        return reg, None  # 저장소 라이브러리의 등록된 부품 (같은 파일: 레지스트리가 sha 를 확인했다)
    t = make_template(part, key=key, status=e.status if e else "active", published=True)
    return t, part


def _strip(part: Mapping[str, Any]) -> dict:
    return {k: v for k, v in part.items() if not str(k).startswith("_")}


# ── publish ──

@dataclass
class PublishResult:
    key: str
    run: Any
    report: dict[str, Any]
    entry: dict[str, Any]
    messages: list[str] = field(default_factory=list)


def publish(draft_path: Path | str, *, lib: Library | None = None, requests: Sequence[str] = (),
            rules: Any | None = None, jobs: int | None = None, profile: str | None = None,
            out: Callable[[str], None] = print) -> PublishResult:
    """초안을 검사·검증하고 parts/<key>.json, 보고서, 색인 항목, 영어 문구 파일을 쓴다 (§8 publish)."""
    from app.library.verify.dsl_checks import read_draft, static_checks, verify_draft
    from app.library.verify.report import build_report, format_text

    lib = lib or default_library()
    path = Path(draft_path)
    data, size = read_draft(path)
    data = _strip(data)
    if data.get("key") is not None or data.get("version") is not None:
        raise PublishError("a draft has no key or version; publish injects them")
    family = str(data.get("family", ""))
    from app.library.verify.dsl_checks import code_template_keys

    if family in code_template_keys() or family == "assembly":
        raise PublishError(f"family {family!r} is a code part key or reserved")
    with using(lib):
        # 1. 정적 검사
        static = static_checks(data, stem=path.stem, raw_size=size, rules=rules)
        bad = [r for r in static if not r.ok]
        if bad:
            raise PublishError("check failed:\n" + "\n".join(_line(r) for r in bad[:10]))
        # 3. 다음 버전과 기존 파일
        versions = [e.version for e in index.entries().values() if e.family == family]
        version = max(versions, default=0) + 1
        key = f"{family}@v{version}"
        if lib.part_path(key).exists():
            raise PublishError(f"{lib.part_path(key).name} already exists; published files are never overwritten")
        # 2. 새로 전체 검증 (캐시 없음)
        run = verify_draft(data, key=key, stem=path.stem, raw_size=size, rules=rules,
                           profile=profile or VERIFY_PROFILE, jobs=jobs)
        out(format_text(run))
        if not run.ok:
            raise PublishError(f"verify failed for {key}; nothing was written")
        # 4. 부품 파일
        text = canonical_part(data, key, version)
        lib.part_path(key).parent.mkdir(parents=True, exist_ok=True)
        with open(lib.part_path(key), "x", encoding="utf-8") as f:  # 덮어쓰지 않는다
            f.write(text)
        sha = sha256_bytes(text.encode("utf-8"))
        # 5. 보고서
        report = build_report(run, file_sha256=sha, dsl=int(data["dsl"]))
        append_report(lib, key, report)
        # 6. 색인
        idx = read_index(lib)
        entry = {
            "sha256": sha, "status": "active", "published_at": today(), "family": family, "version": version,
            "role": data["role"], "habitats": list(data["habitats"]),
            "verified_for": {k: list(v) for k, v in sorted(run.verified_for.items())},
            "rule_fields_used": list(run.rule_fields_used),
            "rules_digest": dict(sorted(run.rules_digest.items())),
            "golden": dict(sorted(run.golden.items())),
            "superseded_by": None, "reason": None, "request_ids": list(dict.fromkeys(requests)),
        }
        idx["parts"][key] = entry
        write_index(lib, idx)
        older = sorted(k for k, e in idx["parts"].items() if e["family"] == family and k != key
                       and e["status"] == "active")
    # 7. 영어 문구
    write_i18n(lib)
    # 8. 다음에 할 일
    msgs = publish_messages(key, run, requests, rules if rules is not None else _rules())
    # 스키마 예산(R01)은 같은 계열의 옛 판을 뺀 목록으로 셌다: 옛 판은 새 설계에서 내린다
    msgs[1:1] = [f"retire the older version: uv run python -m app.library retire {k} --superseded-by {key} "
                 "--reason-ko … --reason-en …" for k in older]
    for m in msgs:
        out(m)
    return PublishResult(key, run, report, entry, msgs)


def publish_messages(key: str, run: Any, requests: Sequence[str], rules: Any | None = None) -> list[str]:
    """게시 뒤 할 일: species.yaml 에 넣을 줄(그 종의 모든 크기 구분을 검증했고 스키마 예산 안일 때만), 시험 명령, 관리자 PATCH."""
    msgs = [f"published {key}"]
    gate = (run.schema or {}).get("gate_ok") or {}
    for sp, sizes in sorted(run.verified_for.items()):
        every = list(rules.species_entry(sp).sizes) if rules is not None else list(sizes)
        missing = [s for s in every if s not in sizes]
        if missing:
            msgs.append(f"do not gate {key} for {sp}: not verified for {', '.join(missing)}")
        elif gate.get(sp, False):
            msgs.append(f"rules/species.yaml: add \"{key}\" to species.{sp}.templates (verified for {', '.join(sizes)})")
        else:
            total = (run.schema or {}).get("totals", {}).get(sp)
            msgs.append(f"do not gate {key} for {sp} yet: the LLM schema would be {total} chars "
                        f"(limit {SCHEMA_TOTAL_MAX})")
    msgs.append(f"then run: {TEST_COMMAND}")
    for rid in requests:
        msgs.append(f"after deploy: PATCH /admin/part-requests/{rid} "
                    + json.dumps({"status": "published", "published_key": key}))
    return msgs


def _line(r: Any) -> str:
    where = " ".join(x for x in (r.variant or "", r.path or "") if x)
    return f"{r.id} {where}: {r.message}" + (f" (hint: {r.hint})" if r.hint else "")


# ── retire / block / unretire ──

def _reason(reason_ko: str, reason_en: str) -> dict[str, str]:
    from app.library.verify.dsl_checks import _HANGUL

    if not reason_ko.strip() or not reason_en.strip():
        raise PublishError("both --reason-ko and --reason-en are required")
    if _HANGUL.search(reason_en):
        raise PublishError("--reason-en must be English (no Hangul)")
    return {"ko": reason_ko.strip(), "en": reason_en.strip()}


def _set_status(lib: Library, key: str, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    idx = read_index(lib)
    e = idx["parts"].get(key)
    if e is None:
        raise PublishError(f"{key} is not in the library index")
    change(e)
    write_index(lib, idx)
    write_i18n(lib)
    return e


def retire(key: str, reason_ko: str, reason_en: str, *, superseded_by: str | None = None,
           lib: Library | None = None) -> dict[str, Any]:
    """색인 상태를 retired 로 (새 설계에 내놓지 않는다; 등록·다시 만들기·내려받기는 그대로, R7)."""
    lib = lib or default_library()
    reason = _reason(reason_ko, reason_en)

    def change(e: dict[str, Any]) -> None:
        if e["status"] == "blocked":
            raise PublishError(f"{key} is blocked; unretire --force-unblock first")
        if superseded_by is not None and (superseded_by == key or superseded_by not in read_index(lib)["parts"]):
            raise PublishError(f"--superseded-by {superseded_by} is not another published key")
        e.update(status="retired", reason=reason, superseded_by=superseded_by)

    return _set_status(lib, key, change)


def block(key: str, reason_ko: str, reason_en: str, *, lib: Library | None = None) -> dict[str, Any]:
    """색인 상태를 blocked 로 (안전 문제: 저장된 설계의 내려받기도 막는다, §9.6)."""
    lib = lib or default_library()
    reason = _reason(reason_ko, reason_en)
    return _set_status(lib, key, lambda e: e.update(status="blocked", reason=reason))


def unretire(key: str, *, force_unblock: bool = False, lib: Library | None = None) -> dict[str, Any]:
    lib = lib or default_library()

    def change(e: dict[str, Any]) -> None:
        if e["status"] == "blocked" and not force_unblock:
            raise PublishError(f"{key} is blocked; pass --force-unblock to make it active again")
        if e["status"] == "active":
            raise PublishError(f"{key} is already active")
        e.update(status="active", reason=None, superseded_by=None)

    return _set_status(lib, key, change)


# ── reverify ──

@dataclass
class ReverifyResult:
    key: str
    ok: bool
    applied: str | None  # "retired" | "refreshed" | None
    messages: list[str] = field(default_factory=list)


def reverify(keys: Iterable[str] | None = None, *, apply: bool = False, lib: Library | None = None,
             rules: Any | None = None, jobs: int | None = None, profile: str | None = None,
             out: Callable[[str], None] = print) -> list[ReverifyResult]:
    """게시된 부품을 지금 규칙·라이브러리로 다시 검증하고 보고서에 덧붙인다. apply: 실패면 retired,
    통과면 rules_digest·verified_for(좁히기만)·golden(파라미터가 같으면 파일이 같아야 한다)을 고친다."""
    from app.library.verify.report import build_report, format_text
    from app.library.verify.run import verify

    lib = lib or default_library()
    results: list[ReverifyResult] = []
    with using(lib):
        todo = list(keys) if keys is not None else list(index.keys())
        for key in todo:
            e = index.entry(key)
            if e is None:
                raise PublishError(f"{key} is not in the library index")
            t, raw = template_for(lib, key)
            run = verify(t, rules=rules, profile=profile or VERIFY_PROFILE, jobs=jobs, draft=raw)  # type: ignore[arg-type]
            out(format_text(run))
            report = build_report(run, file_sha256=e.sha256, dsl=t.part_file.dsl)  # type: ignore[attr-defined]
            report["tag"] = "reverify"
            res = ReverifyResult(key, run.ok, None)
            drift = golden_drift(e, run.golden)
            if drift:
                res.ok = False
                res.messages.append(f"{key}: geometry changed for the same params ({', '.join(drift)}); "
                                    "an interpreter or library change needs dsl 2 or regolden --library-upgrade")
            append_report(lib, key, report)
            if apply and not drift:
                idx = read_index(lib)
                entry = idx["parts"][key]
                if not run.ok:
                    if entry["status"] == "active":
                        entry.update(status="retired", reason=dict(REVERIFY_REASON))
                    res.applied = "retired"
                else:
                    entry["rules_digest"] = dict(sorted(run.rules_digest.items()))
                    entry["verified_for"] = {sp: [s for s in sizes if s in run.verified_for.get(sp, [])]
                                             for sp, sizes in sorted(entry["verified_for"].items())}
                    entry["verified_for"] = {sp: s for sp, s in entry["verified_for"].items() if s}
                    entry["golden"] = dict(sorted({**entry["golden"], **run.golden}.items()))
                    res.applied = "refreshed"
                write_index(lib, idx)
            for m in res.messages:
                out(m)
            results.append(res)
    write_i18n(lib)
    return results


def golden_drift(e: IndexEntry, golden: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """같은 파라미터인데 파일 지문이 달라진 골든 (형상이 바뀌었다)."""
    out = []
    for name, g in golden.items():
        old = e.golden.get(name)
        if old is not None and old.params == dict(g.get("params", {})) and old.files != dict(g.get("files", {})):
            out.append(name)
    return out


# ── regolden ──

def regolden(*, library_upgrade: bool = False, lib: Library | None = None, rules: Any | None = None,
             out: Callable[[str], None] = print) -> list[str]:
    """라이브러리(build123d·OCP·trimesh·numpy) 버전이 바뀌었을 때만 골든을 다시 만들고, regolden 실행을 보고서에 덧붙인다.
    버전이 마지막 보고서와 같으면 거절한다 (해석기 변경을 골든 갱신으로 숨길 수 없게)."""
    from app.library.verify.report import library_versions

    if not library_upgrade:
        raise PublishError("regolden needs --library-upgrade")
    lib = lib or default_library()
    current = library_versions()
    done: list[str] = []
    with using(lib):
        changed: list[str] = []
        for key in list(index.entries()):
            last = latest_report(lib, key)
            if last is not None and last.get("libraries") != current:
                changed.append(key)
        if not changed:
            raise PublishError("the installed library versions equal the latest reports; regolden refused")
        rules = rules if rules is not None else _rules()
        for key in changed:
            e = index.entry(key)
            assert e is not None
            t, _ = template_for(lib, key)
            golden = {name: {"params": dict(g.params), "files": rebuild_digests(t, g.params, rules)}
                      for name, g in e.golden.items()}
            last = latest_report(lib, key) or {}
            report = {**last, "profile": "regolden", "tag": "regolden", "started_at": _now(),
                      "libraries": current, "code": _code(), "golden": dict(sorted(golden.items())),
                      "result": "pass", "failures": [], "seconds": 0.0}
            append_report(lib, key, report)
            idx = read_index(lib)
            idx["parts"][key]["golden"] = dict(sorted(golden.items()))
            write_index(lib, idx)
            out(f"regolden {key}: {len(golden)} goldens")
            done.append(key)
    return done


def _now() -> str:
    from app.library.verify.report import now_iso

    return now_iso()


def _code() -> dict[str, str]:
    from app.library.verify.report import code_digests

    return code_digests()


def _rules() -> Any:
    from app.config import get_settings
    from app.rules.loader import load_rules

    return load_rules(get_settings().rules_dir)


def rebuild_digests(t: Any, params: Mapping[str, Any], rules: Any) -> dict[str, str]:
    """engine.build_item 으로 다시 만든 파일 지문 (G12 와 같은 파일들)."""
    from app.domain import PlacementHint
    from app.library.verify.geometry import file_digests
    from app.services.engine import build_item

    p = t.Params.model_validate(dict(params))
    return file_digests(build_item(0, t, p, PlacementHint(), rules.printing))


# ── audit ──

def audit_integrity(lib: Library) -> list[str]:
    """색인 ↔ 부품 파일 ↔ 보고서: sha, 파일 이름, 보고서가 있고 마지막 보고서의 file_sha256 이 색인과 같다."""
    with using(lib):
        problems = index.integrity_problems()
        try:
            entries = index.entries()
        except index.LibraryError as e:
            return problems + [str(e)]
    reports_dir = lib.root / REPORTS_DIR
    for key, e in entries.items():
        last = latest_report(lib, key)
        if last is None:
            problems.append(f"{key}: no report ({REPORTS_DIR}/{key}.json)")
            continue
        if last.get("file_sha256") != e.sha256:
            problems.append(f"{key}: the latest report is for another file sha256")
        if last.get("key") != key:
            problems.append(f"{key}: the latest report is for {last.get('key')!r}")
        if not any(r.get("result") == "pass" and r.get("profile") == VERIFY_PROFILE for r in read_reports(lib, key)):
            problems.append(f"{key}: no passing {VERIFY_PROFILE} verification in the report")
        # 검증한 크기마다 기본값 골든 (R4: 골든을 색인에서 지우면 다시 만들기 비교가 조용히 빠진다)
        for sp, sizes in e.verified_for.items():
            for size in sizes:
                if f"{sp}/{size}/default" not in e.golden:
                    problems.append(f"{key}: no golden {sp}/{size}/default for a verified size")
    if reports_dir.is_dir():
        for f in sorted(reports_dir.glob("*.json")):
            if f.stem not in entries:
                problems.append(f"{REPORTS_DIR}/{f.name}: not in the index")
    return problems


def latest_passing_report(lib: Library, key: str) -> dict[str, Any] | None:
    runs = [r for r in read_reports(lib, key) if r.get("result") == "pass"]
    return runs[-1] if runs else None


def audit_mirror(lib: Library) -> list[str]:
    """마지막으로 통과한 보고서가 색인을 비춘다: 규칙 필드, 규칙 지문, 골든, 검증한 크기 (색인은 보고서보다 좁을 수만
    있다). 실패한 reverify 는 색인을 바꾸지 않으므로(--apply 면 폐기만) 비교에서 뺀다."""
    problems: list[str] = []
    with using(lib):
        entries = index.entries()
    for key, e in entries.items():
        last = latest_passing_report(lib, key)
        if last is None:
            continue
        if list(last.get("rule_fields_used", [])) != list(e.rule_fields_used):
            problems.append(f"{key}: rule_fields_used differs from the latest report")
        rep_digest = last.get("rules_digest", {})
        for cs, d in e.rules_digest.items():
            if rep_digest.get(cs) != d:
                problems.append(f"{key}: rules_digest[{cs}] differs from the latest report")
        rep_golden = last.get("golden", {})
        for name, g in e.golden.items():
            if rep_golden.get(name) != g.model_dump(mode="json"):
                problems.append(f"{key}: golden {name} differs from the latest report")
        # 보고서의 골든은 (색인이 아직 검증한 크기라면) 모두 색인에 있어야 한다: 색인에서만 빼면 R4 비교가 빠진다
        verified = {f"{sp}/{size}" for sp, sizes in e.verified_for.items() for size in sizes}
        for name in rep_golden:
            if "/".join(name.split("/")[:2]) in verified and name not in e.golden:
                problems.append(f"{key}: golden {name} of the latest report is missing from the index")
        rep_vf = last.get("verified_for", {})
        for sp, sizes in e.verified_for.items():
            extra = sorted(set(sizes) - set(rep_vf.get(sp, [])))
            if extra:
                problems.append(f"{key}: verified_for {sp} {extra} not in the latest report")
    return problems


def audit_goldens(lib: Library, rules: Any | None = None) -> list[str]:
    """골든을 다시 만들어 비교한다 (R4: 해석기 수정이 게시된 부품의 형상을 바꾸면 실패)."""
    rules = rules if rules is not None else _rules()
    problems: list[str] = []
    with using(lib):
        entries = index.entries()
        for key, e in entries.items():
            t, _ = template_for(lib, key)
            for name, g in e.golden.items():
                try:
                    got = rebuild_digests(t, g.params, rules)
                except Exception as err:  # noqa: BLE001
                    problems.append(f"{key}: golden {name} does not build: {type(err).__name__}: {err}")
                    continue
                if got != g.files:
                    bad = sorted(k for k in set(got) | set(g.files) if got.get(k) != g.files.get(k))
                    problems.append(f"{key}: golden {name} differs: {bad}")
    return problems


def audit_gating(lib: Library, rules_dir: Path | str | None = None) -> list[str]:
    """species.yaml 게이팅: 규칙 파일이 읽히고(검증한 크기·규칙 값, loader), 나열한 부품이 색인에 있고, 마지막 보고서가
    그 종에 gate_ok 이며, 그 종의 LLM 스키마가 29,000자 이하다 (R12)."""
    from app.rules.loader import RuleFileError, load_rules

    problems: list[str] = []
    with using(lib):
        try:
            rules = load_rules(Path(rules_dir) if rules_dir is not None else _rules().source_dir)
        except RuleFileError as e:
            return [f"rules: {e}"]
        from app.templates.keys import TEMPLATE_MODULES

        for sp in rules.species_file.species:
            lib_keys = [k for k in rules.allowed_templates(sp) if k not in TEMPLATE_MODULES]
            if not lib_keys:
                continue
            for key in lib_keys:
                if index.entry(key) is None:
                    problems.append(f"species.{sp}: {key} is not in the library index")
                    continue
                last = latest_report(lib, key) or {}
                gate = ((last.get("schema") or {}).get("gate_ok") or {}).get(sp)
                if gate is False:
                    problems.append(f"species.{sp}: {key} is gated although its report says gate_ok false")
            try:
                from app.llm.spec import api_schema

                total = len(json.dumps(api_schema(rules.offered_templates(sp)), ensure_ascii=False))
            except Exception as e:  # noqa: BLE001
                problems.append(f"species.{sp}: the LLM schema does not build: {type(e).__name__}: {e}")
                continue
            if total > SCHEMA_TOTAL_MAX:
                problems.append(f"species.{sp}: the LLM schema has {total} chars (limit {SCHEMA_TOTAL_MAX})")
    return problems


def audit_rules_digests(lib: Library, rules: Any | None = None) -> list[str]:
    """활성 부품의 rules_digest 가 지금 규칙과 같다. 다르면 같은 PR 에서 reverify --apply."""
    from app.library.verify.report import rules_digest

    rules = rules if rules is not None else _rules()
    problems: list[str] = []
    with using(lib):
        entries = index.entries()
    for key, e in entries.items():
        if e.status != "active":
            continue  # 폐기·차단 부품은 새 설계에 쓰지 않는다 (저장된 설계는 지금 규칙으로 다시 검증된다)
        for sp, sizes in e.verified_for.items():
            for size in sizes:
                cs = f"{sp}/{size}"
                stored = e.rules_digest.get(cs)
                if stored is None:
                    problems.append(f"{key}: no rules_digest for {cs}")
                    continue
                try:
                    now = rules_digest(rules, sp, size, e.rule_fields_used)
                except KeyError:
                    problems.append(f"{key}: {cs} is no longer in the rules")
                    continue
                if now != stored:
                    problems.append(f"{key}: the rules for {cs} changed since verification; run "
                                    f"`python -m app.library reverify {key} --apply`")
    return problems


def audit_i18n(lib: Library) -> list[str]:
    """영어 문구 파일이 다시 만든 짝과 같다 (파일이 없으면 짝도 비어 있어야 한다)."""
    want = json.loads(i18n_text(lib))
    have = json.loads(lib.i18n_path.read_text(encoding="utf-8")) if lib.i18n_path.exists() else {}
    if have == want:
        return []
    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    changed = sorted(k for k in set(want) & set(have) if want[k] != have[k])
    return [(f"{lib.i18n_path.name} is stale (missing {missing[:3]}, extra {extra[:3]}, changed {changed[:3]}); "
             "it is regenerated by publish/retire/block")]


def audit(lib: Library | None = None, *, rules: Any | None = None, goldens: bool = True) -> list[str]:
    """CI 가 돌리는 검사 모두 (tests/test_library_published.py 가 하나씩도 돌린다). 문제 목록 (없으면 [])."""
    lib = lib or default_library()
    problems = audit_integrity(lib)
    if problems:
        return problems  # 파일이 맞지 않으면 나머지는 뜻이 없다
    problems += audit_mirror(lib)
    if goldens:
        problems += audit_goldens(lib, rules)
    problems += audit_gating(lib, rules.source_dir if rules is not None else None)
    problems += audit_rules_digests(lib, rules)
    problems += audit_i18n(lib)
    return problems


# ── list, demand ──

def list_rows(lib: Library | None = None) -> list[dict[str, Any]]:
    lib = lib or default_library()
    with using(lib):
        return [{"key": k, "status": e.status, "verified_for": e.verified_for, "published_at": e.published_at,
                 "role": e.role} for k, e in index.entries().items()]


def demand_summary(export: Mapping[str, Any], lib: Library | None = None, top: int = 20) -> str:
    """관리자 화면 "JSON 내보내기" 파일 요약: 사용자 수 순 요청, 쓰임새, 예시, 이를 채우는 활성 부품(fulfills)."""
    from app.services.part_requests import normalize_name

    lib = lib or default_library()
    with using(lib):
        fulfills = index.fulfills()
    claimed: dict[str, list[str]] = {}
    for key, names in fulfills.items():
        for n in names:
            claimed.setdefault(normalize_name(n) or n, []).append(key)
    reqs = sorted(export.get("requests") or [], key=lambda r: (-int(r.get("users", 0)), -int(r.get("count", 0)),
                                                               str(r.get("name_ko", ""))))
    lines = [f"exported_at {export.get('exported_at', '?')}: {len(reqs)} requests"]
    for r in reqs[:top]:
        name = str(r.get("name_ko", ""))
        keys = claimed.get(normalize_name(name) or name, [])
        lines.append(f"- {name}  users={r.get('users', 0)} count={r.get('count', 0)} id={r.get('id', '')}"
                     + (f"  fulfilled_by={','.join(keys)}" if keys else ""))
        species = r.get("species_counts") or {}
        if species:
            lines.append("    species: " + ", ".join(f"{k} {v}" for k, v in sorted(species.items())))
        for p in (r.get("purposes") or [])[:3]:
            lines.append(f"    purpose: {p}")
        for ex in (r.get("examples") or [])[:3]:
            text = ex.get("excerpt", "") if isinstance(ex, dict) else str(ex)
            lines.append(f"    example: {text}")
    return "\n".join(lines)


def copy_library(src: Library, dst_root: Path) -> Library:
    """라이브러리 폴더 사본 (시험)."""
    shutil.copytree(src.root, dst_root, dirs_exist_ok=True)
    return library_at(dst_root)


def parse_published_key(key: str) -> tuple[str, int]:
    parsed = parse_key(key)
    if parsed is None:
        raise PublishError(f"{key!r} is not <family>@v<N>")
    return parsed
