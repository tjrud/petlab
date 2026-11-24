"""부품 라이브러리 명령 (설계 §8): `uv run python -m app.library <명령>`.

| 명령 | 하는 일 |
|---|---|
| schema | app/library/part.schema.json 을 쓴다 (설명과 예시 하나) |
| new <family> --role … | library_drafts/<family>.json 을 역할별 뼈대로 쓴다 (check 를 통과한다) |
| check <draft> | S01–S08, L01–L12 (커널 없이, 1초 안) |
| preview <draft> | use.stl, print_<key>.stl, sheet.png, info.json |
| verify <draft> | §7 검증 (정적 검사 + P·G·C·T·R). --quick, --species, --jobs, --report, --stl-dir |
| publish <draft> | 검사·전체 검증 뒤 parts/, reports/, index.json, i18n/en/library.json 을 쓴다 |
| retire / block / unretire | 색인 상태 바꾸기 |
| reverify, regolden, audit | 게시된 부품 다시 검증, 골든 다시 만들기(라이브러리 버전이 바뀔 때만), CI 검사 |
| demand <export.json> | 관리자 화면 내보내기 요약 |
| list | 게시된 부품 |

서버는 이 명령을 쓰지 않는다. 부품은 개발자 에이전트가 오프라인으로 쓰고 검증한다 (AI 호출 없음).
--library DIR 은 다른 라이브러리 폴더를 쓴다 (시험용; 저장소 라이브러리가 기본).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.library.errors import DslError

QUICK_BUDGET_S = 90.0
FULL_BUDGET_S = 600.0
ROLES = ("host", "room_host", "accessory", "none")


# ── 뼈대 (new) ──

AUTHORING_FILE = Path(__file__).resolve().parent / "authoring.json"


@lru_cache(maxsize=1)
def authoring() -> dict[str, Any]:
    """작성 도구용 데이터 (app/library/authoring.json): 역할별 뼈대 초안과 reverify 폐기 까닭. 사용자 화면 문구가
    아니라서 코드가 아닌 데이터 파일에 둔다 (영어 카탈로그 추출 대상이 아니다)."""
    return json.loads(AUTHORING_FILE.read_text(encoding="utf-8"))


def skeletons() -> dict[str, dict[str, Any]]:
    return authoring()["skeletons"]


def skeleton(family: str, role: str) -> dict[str, Any]:
    """역할별 뼈대 초안 (family·part_id 를 넣은 사본). 모두 check 를 통과한다 (tests/test_library_cli.py)."""
    if role not in skeletons():
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    d = copy.deepcopy(skeletons()[role])
    d["family"] = family
    d["part_id"] = family[:21].rstrip("_")
    return d


# ── 도움 ──

def _lib(args: argparse.Namespace) -> Any:
    from app.library.publish import library_at

    return library_at(getattr(args, "library", None))


def _rules(args: argparse.Namespace) -> Any:
    from app.config import get_settings
    from app.rules.loader import load_rules

    return load_rules(Path(args.rules) if getattr(args, "rules", None) else get_settings().rules_dir)


def _print_results(results: Sequence[Any], out: Any = sys.stdout) -> None:
    for r in results:
        if r.ok:
            continue
        where = " ".join(x for x in (r.variant or "", r.path or "") if x) or "/"
        out.write(f"{r.id} {where}: {r.message}" + (f"\n    hint: {r.hint}" if r.hint else "") + "\n")


def _read(path: str) -> tuple[dict, int]:
    from app.library.verify.dsl_checks import read_draft

    return read_draft(path)


# ── 명령 ──

def cmd_schema(args: argparse.Namespace) -> int:
    from app.library.schema import json_schema

    schema = json_schema()
    example = skeleton("small_room", "room_host")
    schema["examples"] = [example]
    out = Path(args.out) if args.out else Path(__file__).resolve().parent / "part.schema.json"
    out.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    from app.library.publish import DRAFTS_DIR

    d = skeleton(args.family, args.role)
    out_dir = Path(args.dir) if args.dir else DRAFTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.family}.json"
    if path.exists() and not args.force:
        print(f"{path} exists; pass --force to replace the draft", file=sys.stderr)
        return 1
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}\nnext: edit it, then `uv run python -m app.library check {path}`")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from app.library.publish import using
    from app.library.verify.dsl_checks import static_checks

    t0 = time.perf_counter()
    try:
        data, size = _read(args.draft)
    except DslError as e:
        print(f"S01 {e}")
        return 1
    with using(_lib(args)):
        results = static_checks(data, stem=Path(args.draft).stem, raw_size=size)
    bad = [r for r in results if not r.ok]
    if args.json:
        print(json.dumps({"ok": not bad, "failures": [r.as_dict() for r in bad]}, ensure_ascii=False, indent=2))
    else:
        _print_results(bad)
        print(f"check: {'ok' if not bad else f'{len(bad)} problem(s)'} ({time.perf_counter() - t0:.2f}s)")
    return 0 if not bad else 1


def cmd_preview(args: argparse.Namespace) -> int:
    from app.library.preview import preview
    from app.library.publish import using

    data, _ = _read(args.draft)
    params = json.loads(args.params) if args.params else None
    with using(_lib(args)):
        res = preview(data, params=params, species=args.species, size=args.size, out_dir=args.out)
    for f in res.files:
        print(f"wrote {f}")
    if res.sheet_error:
        print(res.sheet_error, file=sys.stderr)
    for i in res.info.get("issues", []):
        print(f"issue {i['code']}: {i['message']}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from app.library.publish import using
    from app.library.verify.dsl_checks import verify_draft
    from app.library.verify.report import build_report, format_text

    try:
        data, size = _read(args.draft)
    except DslError as e:
        print(f"S01 {e}")
        return 1
    profile = "quick" if args.quick else "full"
    t0 = time.perf_counter()
    with using(_lib(args)):
        run = verify_draft(data, stem=Path(args.draft).stem, raw_size=size, profile=profile, species=args.species,
                           jobs=args.jobs, rules=_rules(args))
        print(format_text(run))
        if args.report:
            Path(args.report).write_text(json.dumps(build_report(run, dsl=data.get("dsl")), ensure_ascii=False,
                                                    indent=2) + "\n", encoding="utf-8")
            print(f"wrote {args.report}")
        if args.stl_dir and not run.ok:
            for f in dump_failing(data, run, Path(args.stl_dir), _rules(args), profile, args.species):
                print(f"wrote {f}")
    elapsed = time.perf_counter() - t0
    budget = QUICK_BUDGET_S if args.quick else FULL_BUDGET_S
    print(f"time {elapsed:.1f}s (budget {budget:g}s)" + ("  OVER BUDGET" if elapsed > budget else ""))
    return 0 if run.ok else 1


def dump_failing(data: dict, run: Any, out: Path, rules: Any, profile: str, species: str | None) -> list[Path]:
    """실패한 변형의 사용 자세·출력 메시를 STL 로 쓴다."""
    from app.domain import PlacementHint
    from app.library.template import make_template
    from app.library.verify import variants as V
    from app.services.engine import build_item

    bad = {r.variant for r in run.failures if r.variant}
    if not bad:
        return []
    clean = {k: v for k, v in data.items() if not str(k).startswith("_")}
    t = make_template(clean, key=run.key if "?" not in run.key else None)
    out.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for v in V.generate(t, rules, profile, species):  # type: ignore[arg-type]
        if v.id not in bad or v.params is None:
            continue
        name = v.id.replace("/", "_").replace(":", "-").replace("=", "-")
        try:
            it = build_item(0, t, v.params, PlacementHint(), rules.printing)
        except Exception as e:  # noqa: BLE001
            print(f"{v.id}: does not build: {e}", file=sys.stderr)
            continue
        f = out / f"{name}_use.stl"
        f.write_bytes(it.mesh.export(file_type="stl"))
        g = out / f"{name}_print.stl"
        g.write_bytes(it.print_mesh.export(file_type="stl"))
        files += [f, g]
    return files


def cmd_publish(args: argparse.Namespace) -> int:
    from app.library.publish import PublishError, publish

    requests = [r for r in (args.requests or "").split(",") if r.strip()]
    try:
        publish(args.draft, lib=_lib(args), requests=requests, rules=_rules(args), jobs=args.jobs)
    except (PublishError, DslError) as e:
        print(f"publish refused: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_retire(args: argparse.Namespace) -> int:
    from app.library.publish import PublishError, retire

    try:
        retire(args.key, args.reason_ko, args.reason_en, superseded_by=args.superseded_by, lib=_lib(args))
    except PublishError as e:
        print(f"retire refused: {e}", file=sys.stderr)
        return 1
    print(f"{args.key}: retired")
    return 0


def cmd_block(args: argparse.Namespace) -> int:
    from app.library.publish import PublishError, block

    try:
        block(args.key, args.reason_ko, args.reason_en, lib=_lib(args))
    except PublishError as e:
        print(f"block refused: {e}", file=sys.stderr)
        return 1
    print(f"{args.key}: blocked (exports of stored designs that use it are refused)")
    return 0


def cmd_unretire(args: argparse.Namespace) -> int:
    from app.library.publish import PublishError, unretire

    try:
        unretire(args.key, force_unblock=args.force_unblock, lib=_lib(args))
    except PublishError as e:
        print(f"unretire refused: {e}", file=sys.stderr)
        return 1
    print(f"{args.key}: active")
    return 0


def cmd_reverify(args: argparse.Namespace) -> int:
    from app.library.publish import PublishError, reverify

    if not args.all and not args.key:
        print("give a key or --all", file=sys.stderr)
        return 2
    try:
        res = reverify(None if args.all else [args.key], apply=args.apply, lib=_lib(args), rules=_rules(args),
                       jobs=args.jobs)
    except PublishError as e:
        print(f"reverify refused: {e}", file=sys.stderr)
        return 1
    for r in res:
        print(f"{r.key}: {'pass' if r.ok else 'FAIL'}" + (f" ({r.applied})" if r.applied else ""))
    return 0 if all(r.ok for r in res) else 1


def cmd_regolden(args: argparse.Namespace) -> int:
    from app.library.publish import PublishError, regolden

    try:
        regolden(library_upgrade=args.library_upgrade, lib=_lib(args), rules=_rules(args))
    except PublishError as e:
        print(f"regolden refused: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from app.library.publish import audit

    problems = audit(_lib(args), rules=_rules(args), goldens=not args.no_goldens)
    for p in problems:
        print(p)
    print(f"audit: {'ok' if not problems else f'{len(problems)} problem(s)'}")
    return 0 if not problems else 1


def cmd_demand(args: argparse.Namespace) -> int:
    from app.library.publish import demand_summary

    export = json.loads(Path(args.export).read_text(encoding="utf-8"))
    print(demand_summary(export, _lib(args), top=args.top))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from app.library.publish import list_rows

    rows = list_rows(_lib(args))
    if not rows:
        print("(no published parts)")
    for r in rows:
        vf = "; ".join(f"{sp}: {', '.join(s)}" for sp, s in sorted(r["verified_for"].items()))
        print(f"{r['key']:<32} {r['status']:<8} {r['role']:<10} {r['published_at']}  {vf}")
    return 0


# ── 인자 ──

def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--library", help="library folder (default: app/library)")
    common.add_argument("--rules", help="rules folder (default: settings.rules_dir)")
    ap = argparse.ArgumentParser(prog="python -m app.library", description="NestForge part library tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("schema", parents=[common], help="write part.schema.json")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_schema)

    s = sub.add_parser("new", parents=[common], help="write a draft skeleton")
    s.add_argument("family")
    s.add_argument("--role", required=True, choices=ROLES)
    s.add_argument("--dir", help="draft folder (default: library_drafts)")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("check", parents=[common], help="static checks S01-S08, L01-L12")
    s.add_argument("draft")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("preview", parents=[common], help="STL files and sheet.png")
    s.add_argument("draft")
    s.add_argument("--params", help="JSON object of params over the defaults")
    s.add_argument("--species")
    s.add_argument("--size")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_preview)

    s = sub.add_parser("verify", parents=[common], help="verify a draft")
    s.add_argument("draft")
    s.add_argument("--quick", action="store_true")
    s.add_argument("--species")
    s.add_argument("--jobs", type=int)
    s.add_argument("--report")
    s.add_argument("--stl-dir")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("publish", parents=[common], help="check, verify fully and publish a draft")
    s.add_argument("draft")
    s.add_argument("--requests", help="comma-separated part request ids this part answers")
    s.add_argument("--jobs", type=int)
    s.set_defaults(fn=cmd_publish)

    for name, fn, help_ in (("retire", cmd_retire, "hide a part from new designs"),
                            ("block", cmd_block, "hide a part and refuse exports (safety problem)")):
        s = sub.add_parser(name, parents=[common], help=help_)
        s.add_argument("key")
        s.add_argument("--reason-ko", required=True)
        s.add_argument("--reason-en", required=True)
        if name == "retire":
            s.add_argument("--superseded-by")
        s.set_defaults(fn=fn)

    s = sub.add_parser("unretire", parents=[common], help="make a retired part active again")
    s.add_argument("key")
    s.add_argument("--force-unblock", action="store_true")
    s.set_defaults(fn=cmd_unretire)

    s = sub.add_parser("reverify", parents=[common], help="verify published parts again")
    s.add_argument("key", nargs="?")
    s.add_argument("--all", action="store_true")
    s.add_argument("--apply", action="store_true")
    s.add_argument("--jobs", type=int)
    s.set_defaults(fn=cmd_reverify)

    s = sub.add_parser("regolden", parents=[common], help="rebuild goldens after a library upgrade")
    s.add_argument("--library-upgrade", action="store_true")
    s.set_defaults(fn=cmd_regolden)

    s = sub.add_parser("audit", parents=[common], help="index, files, reports, goldens, gating, rules, i18n")
    s.add_argument("--no-goldens", action="store_true")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("demand", parents=[common], help="summarise an admin export")
    s.add_argument("export")
    s.add_argument("--top", type=int, default=20)
    s.set_defaults(fn=cmd_demand)

    s = sub.add_parser("list", parents=[common], help="published parts")
    s.set_defaults(fn=cmd_list)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(list(argv) if argv is not None else None)
    return int(args.fn(args))
