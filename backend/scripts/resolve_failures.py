"""조립 항목 실패 집계: 조립 해석은 됐는데 형상 검사(슬라이드·남은 틈·겹침·끼임 틈)에 걸린 비율을 센다.

stage 2 설계 §3.5.6: 형상만 바꿔 다시 찾는 재시도 탐색(다른 면·연결판 자리, shift 변형)은 이 비율이
조립 설계의 5 % 를 넘을 때만 만든다. 같은 집계가 조립 해석 실패도 코드별로 세고, 그중 "양 끝의 출입구 단면
모양이 달라" (port_adapter 가 풀 경우, §2.2 의 2 % 기준)를 따로 센다.

저장된 설계 버전(DesignVersion)만 읽는다: llm_spec(해석기가 낸 명세), items(만든 항목), report(검증 보고서).
형상을 다시 만들지 않는다. 보고서 문구는 저장 때의 한국어 원문이라 문구 꼴로 종류를 가른다
(`app/modules/module_template.AssemblyTemplate._geometry_issues`·`_gap_issues` 의 문구,
`tests/test_resolve_failures.py` 가 두 함수가 만든 문구로 맞는지 확인한다).

    cd backend
    uv run python scripts/resolve_failures.py [--db-url URL] [--since 2026-11-01] [--latest-only] [--json]

단위: "조립 설계" = 조립 항목이 하나 이상 있는 설계 버전. 수정 버전도 한 번씩 센다 (`--latest-only` 는 설계마다
마지막 버전만). 해석기 재시도로 버려진 시도는 저장되지 않으므로 세지 않는다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # `python scripts/resolve_failures.py` 로 돌릴 때 app 패키지를 찾게
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ASSEMBLY_KEY = "assembly"
RETRY_SEARCH_PCT = 5.0   # §3.5.6: 이보다 크면 재시도 탐색을 만든다
PORT_ADAPTER_PCT = 2.0   # §2.2: 단면 모양이 다른 실패가 이 이상이면 port_adapter

# 조립 해석(_prepare_assembly)이 항목을 만들기 전에 낸 오류 코드
RESOLVE_CODES = frozenset({
    "join_unsupported", "face_unavailable", "too_many_parts", "invalid_params", "unknown_template",
    "template_not_allowed",
})
PROFILE_MISMATCH = "양 끝의 출입구 단면 모양이 달라"

# 형상 사실 → 문구 꼴 (module_template._geometry_issues, _gap_issues). 위에서부터 처음 맞는 것.
GEOMETRY_KINDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("slot_gap", re.compile(r"\)와 .+\(.+\) 사이 틈 [\d.]+mm 가 끼임 위험 구간")),
    ("slide_gap", re.compile(r"의 연결판 위로 벽과 .+ 사이에 [\d.]+mm 틈이 생겨|의 뒷면과 .+의 벽·지붕 사이에 폭이")),
    ("slide_wide", re.compile(r"연결판을 붙일 수 있는 곳보다 넓거나 벗어납니다")),
    ("slide_floor", re.compile(r"슬라이드 결합으로 붙이는 .+ 같은 바닥에 서야 합니다")),
    ("slide_contact", re.compile(r"도브테일을 낼 수 없습니다")),
    ("plug_leftover", re.compile(r"출입구·끼움 구멍을 다 덮지 못해 틈이 남습니다")),
    ("leftover", re.compile(r"의 통로보다 커서 틈이 남습니다")),
    ("overlap", re.compile(r"따로 출력하는 파트 .+ 겹칩니다")),
    ("geometry_error", re.compile(r"조립 형상을 만들지 못했습니다")),
)
_PART_ID = re.compile(r"(?<![A-Za-z0-9_])([a-z][a-z0-9_]{0,40})(?![A-Za-z0-9_])")  # 부품 id·출력 파트 key
UNKNOWN = "(unknown)"


def classify_message(message: str) -> str | None:
    """rule_violation 문구 → 형상 사실 종류 (형상 사실이 아니면 None)."""
    for kind, pattern in GEOMETRY_KINDS:
        if pattern.search(message):
            return kind
    return None


@lru_cache(maxsize=1)
def _template_names() -> dict[str, str]:
    """템플릿 key → 화면 이름 (부품 이름을 템플릿으로 되돌리는 데 쓴다). 레지스트리를 못 읽으면 빈 표."""
    try:
        from app.templates.registry import primitives
    except Exception:  # noqa: BLE001 (집계 스크립트: 이름 없이도 종류별 집계는 된다)
        return {}
    return {k: t.display_name_ko for k, t in primitives().items()}


def part_lookup(parts: list[dict], template_names: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """저장된 부품 [{id, template}] → (부품 id → 템플릿, 문구 속 부품 이름 → 템플릿).
    이름은 composed 템플릿이 문구에 쓰는 것과 같다 (structure.part_names: 같은 템플릿 둘째부터 " 2")."""
    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}
    seen: Counter[str] = Counter()
    for p in parts:
        pid, key = str(p.get("id", "")), str(p.get("template", ""))
        by_id[pid] = key
        seen[key] += 1
        name = template_names.get(key, key)
        by_name[name if seen[key] == 1 else f"{name} {seen[key]}"] = key
    return by_id, by_name


def templates_in(message: str, by_id: Mapping[str, str], by_name: Mapping[str, str], root: str | None) -> list[str]:
    """문구에 나온 부품의 템플릿 (나온 순서, 중복 없이).
    부품 이름("은신처 2"), 부품 id("(hide)"), 출력 파트 key("ramp_body"), 기준 묶음 출력 파트 "본체" 를 찾는다."""
    found: list[tuple[int, str]] = []
    text = message
    for name in sorted(by_name, key=len, reverse=True):  # "은신처 2" 를 "은신처" 보다 먼저
        for m in re.finditer(re.escape(name), text):
            found.append((m.start(), by_name[name]))
        text = text.replace(name, "\0" * len(name))
    for m in _PART_ID.finditer(text):
        pid = m.group(1)
        while pid not in by_id and "_" in pid:  # 출력 파트 key "{부품id}_{key}"
            pid = pid.rsplit("_", 1)[0]
        if pid in by_id:
            found.append((m.start(), by_id[pid]))
    if root is not None:  # 기준 묶음 출력 파트 (부품 이름 뒤의 "본체" 는 그 부품의 출력 파트다)
        found += [(m.start(), root) for m in re.finditer("본체", text) if not text[:m.start()].endswith("\0 ")]
    return list(dict.fromkeys(k for _, k in sorted(found))) or [UNKNOWN]


@dataclass
class VersionRow:
    """집계에 필요한 설계 버전 값 (DB 행이나 시험 자료)."""

    design_id: str
    version: int
    llm_spec: dict
    items: list
    report: dict
    species: str = ""
    size: str = ""


@dataclass
class Tally:
    versions: int = 0
    assembly_versions: int = 0
    assembly_items: int = 0
    resolve_failed_items: int = 0
    resolve_codes: Counter[str] = field(default_factory=Counter)
    profile_mismatch_items: int = 0
    profile_mismatch_versions: int = 0
    build_failed_items: int = 0
    resolved_items: int = 0
    geometry_items: int = 0
    geometry_versions: int = 0
    kind_items: Counter[str] = field(default_factory=Counter)
    kind_facts: Counter[str] = field(default_factory=Counter)
    template_items: Counter[str] = field(default_factory=Counter)
    other_items: int = 0
    other_codes: Counter[str] = field(default_factory=Counter)
    kind_templates: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    by_size: Counter[str] = field(default_factory=Counter)
    examples: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def as_dict(self) -> dict[str, Any]:
        def pct(n: int) -> float:
            return round(100.0 * n / self.assembly_versions, 2) if self.assembly_versions else 0.0

        geometry_pct = pct(self.geometry_versions)
        mismatch_pct = pct(self.profile_mismatch_versions)
        return {
            "versions": self.versions,
            "assembly_versions": self.assembly_versions,
            "assembly_items": self.assembly_items,
            "resolve_failed": {"items": self.resolve_failed_items, "by_code": dict(self.resolve_codes.most_common()),
                               "profile_mismatch_items": self.profile_mismatch_items},
            "build_failed_items": self.build_failed_items,
            "resolved_items": self.resolved_items,
            "geometry_failed": {
                "items": self.geometry_items, "versions": self.geometry_versions,
                "by_kind": {k: {"items": n, "facts": self.kind_facts[k],
                                "templates": dict(self.kind_templates[k].most_common())}
                            for k, n in self.kind_items.most_common()},
                "by_template": dict(self.template_items.most_common()),
                "by_size": dict(self.by_size.most_common()),
                "examples": {k: v for k, v in self.examples.items()},
            },
            "other_errors_after_resolve": {"items": self.other_items, "by_code": dict(self.other_codes.most_common())},
            "rates_pct": {"geometry_failed": geometry_pct, "profile_mismatch": mismatch_pct},
            "thresholds_pct": {"retry_search": RETRY_SEARCH_PCT, "port_adapter": PORT_ADAPTER_PCT},
            "verdict": {"retry_search": geometry_pct > RETRY_SEARCH_PCT,
                        "port_adapter": mismatch_pct >= PORT_ADAPTER_PCT and self.profile_mismatch_versions > 0},
        }


def _issues_by_item(report: Any) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = defaultdict(list)
    issues = report.get("issues", []) if isinstance(report, dict) else []
    for iss in issues:
        if isinstance(iss, dict) and isinstance(iss.get("item_index"), int):
            out[iss["item_index"]].append(iss)
    return out


def _is_error(iss: dict) -> bool:
    return iss.get("severity") == "error" and not iss.get("auto_fixed", False)


def tally(rows: Iterable[VersionRow], *, examples: int = 3,
          template_names: Mapping[str, str] | None = None) -> Tally:
    names = _template_names() if template_names is None else template_names
    t = Tally()
    for row in rows:
        t.versions += 1
        spec_items = row.llm_spec.get("items", []) if isinstance(row.llm_spec, dict) else []
        asm = [i for i, it in enumerate(spec_items) if isinstance(it, dict) and it.get("template") == ASSEMBLY_KEY]
        if not asm:
            continue
        t.assembly_versions += 1
        built = {it.get("index"): it for it in row.items or [] if isinstance(it, dict)}
        issues = _issues_by_item(row.report)
        version_geometry = version_mismatch = False
        for i in asm:
            t.assembly_items += 1
            errors = [iss for iss in issues.get(i, []) if _is_error(iss)]
            item = built.get(i)
            stored = item.get(ASSEMBLY_KEY) if isinstance(item, dict) else None
            if not isinstance(stored, dict):
                resolve = [iss for iss in errors if iss.get("code") in RESOLVE_CODES]
                if resolve:
                    t.resolve_failed_items += 1
                    t.resolve_codes[str(resolve[0]["code"])] += 1
                    if any(PROFILE_MISMATCH in str(iss.get("message_ko", "")) for iss in resolve):
                        t.profile_mismatch_items += 1
                        version_mismatch = True
                elif any(iss.get("code") == "build_failed" for iss in errors):
                    t.build_failed_items += 1
                continue
            t.resolved_items += 1
            parts = stored.get("parts", []) if isinstance(stored.get("parts"), list) else []
            by_id, by_name = part_lookup(parts, names)
            root = by_id.get(str(stored.get("root", ""))) or (str(parts[0].get("template")) if parts else None)
            label = f"{item.get('label_ko')}: "
            kinds: set[str] = set()
            templates: set[str] = set()
            others: set[str] = set()
            for iss in errors:
                msg = str(iss.get("message_ko", ""))
                kind = classify_message(msg) if iss.get("code") == "rule_violation" else None
                if kind is None:  # 형상 사실이 아닌 오류 (배치 실패, 부품 규칙 위반 등): 따로 센다
                    others.add(str(iss.get("code")))
                    continue
                t.kind_facts[kind] += 1
                # 항목 이름("은신처와 … #1: ")에 나온 부품 이름은 세지 않는다
                body = msg.removeprefix(label)
                keys = templates_in(body, by_id, by_name, root)
                if kind not in kinds:
                    t.kind_items[kind] += 1
                    t.kind_templates[kind].update(keys)
                    if len(t.examples[kind]) < examples:
                        t.examples[kind].append(msg)
                kinds.add(kind)
                templates.update(keys)
            if others:
                t.other_items += 1
                t.other_codes.update(others)
            if kinds:
                t.geometry_items += 1
                t.template_items.update(templates)
                t.by_size[f"{row.species}/{row.size}"] += 1
                version_geometry = True
        t.geometry_versions += version_geometry
        t.profile_mismatch_versions += version_mismatch
    return t


# ── DB ──────────────────────────────────────────────


def load_rows(db: Any, *, since: date | None = None, latest_only: bool = False, batch: int = 500) -> Iterator[VersionRow]:
    """설계 버전을 오래된 것부터 batch 개씩 읽는다."""
    from sqlalchemy import func, select

    from app.models import Design, DesignVersion, Habitat

    latest = None
    if latest_only:
        latest = (select(DesignVersion.design_id, func.max(DesignVersion.version).label("v"))
                  .group_by(DesignVersion.design_id).subquery())
    last_id = 0
    while True:
        q = (select(DesignVersion, Habitat.species, Habitat.size)
             .join(Design, Design.id == DesignVersion.design_id)
             .join(Habitat, Habitat.id == Design.habitat_id)
             .where(DesignVersion.id > last_id))
        if since is not None:
            q = q.where(DesignVersion.created_at >= datetime(since.year, since.month, since.day, tzinfo=UTC))
        if latest is not None:
            q = q.join(latest, (latest.c.design_id == DesignVersion.design_id) & (latest.c.v == DesignVersion.version))
        rows = db.execute(q.order_by(DesignVersion.id).limit(batch)).all()
        if not rows:
            return
        for v, species, size in rows:
            last_id = v.id
            yield VersionRow(design_id=v.design_id, version=v.version,
                             llm_spec=v.llm_spec if isinstance(v.llm_spec, dict) else {},
                             items=v.items if isinstance(v.items, list) else [],
                             report=v.report if isinstance(v.report, dict) else {},
                             species=species, size=size)
        db.expunge_all()


def render(d: dict[str, Any]) -> str:
    """사람이 읽는 요약 (PR 에 붙인다)."""
    rf, gf = d["resolve_failed"], d["geometry_failed"]
    rates, limits = d["rates_pct"], d["thresholds_pct"]
    lines = [
        f"design versions scanned: {d['versions']}",
        f"assembly designs (versions with an assembly item): {d['assembly_versions']}",
        f"assembly items: {d['assembly_items']}",
        f"resolve failed: {rf['items']} items {rf['by_code'] or ''}".rstrip(),
        (f"  door cross-section mismatch (port_adapter case): {rf['profile_mismatch_items']} items"
         f" = {rates['profile_mismatch']}% of assembly designs (trigger >= {limits['port_adapter']}%)"),
        f"build failed after resolve: {d['build_failed_items']} items",
        f"resolved: {d['resolved_items']} items",
        (f"  other errors after resolve (not geometry facts): {d['other_errors_after_resolve']['items']} items "
         f"{d['other_errors_after_resolve']['by_code'] or ''}").rstrip(),
        (f"geometry facts after a successful resolve: {gf['items']} items in {gf['versions']} designs"
         f" = {rates['geometry_failed']}% of assembly designs (retry search trigger > {limits['retry_search']}%)"),
    ]
    if gf["by_kind"]:
        lines += ["", f"{'kind':<16}{'items':>7}{'facts':>7}  templates"]
        for kind, v in gf["by_kind"].items():
            tpl = ", ".join(f"{k} {n}" for k, n in v["templates"].items())
            lines.append(f"{kind:<16}{v['items']:>7}{v['facts']:>7}  {tpl}")
        lines += ["", "by template (items): " + ", ".join(f"{k} {n}" for k, n in gf["by_template"].items()),
                  "by species/size (items): " + ", ".join(f"{k} {n}" for k, n in gf["by_size"].items())]
    v = d["verdict"]
    lines += ["", (f"verdict: retry search {'NEEDED' if v['retry_search'] else 'not needed'}; "
                   f"port_adapter {'NEEDED' if v['port_adapter'] else 'not needed'}")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/resolve_failures.py",
        description="Tally assembly items that resolved but failed geometry checks (stage 2 §3.5.6).")
    parser.add_argument("--db-url", help="database URL (default: DATABASE_URL from the settings)")
    parser.add_argument("--since", type=date.fromisoformat, help="only versions created on or after this date")
    parser.add_argument("--latest-only", action="store_true", help="only the latest version of each design")
    parser.add_argument("--examples", type=int, default=3, help="example messages kept per kind")
    parser.add_argument("--json", action="store_true", help="print JSON instead of the text summary")
    args = parser.parse_args(argv)

    from app.config import get_settings
    from app.db import make_engine, make_session_factory

    engine = make_engine(args.db_url or get_settings().database_url)
    db = make_session_factory(engine)()
    try:
        d = tally(load_rows(db, since=args.since, latest_only=args.latest_only), examples=args.examples).as_dict()
    finally:
        db.close()
        engine.dispose()
    print(json.dumps(d, ensure_ascii=False, indent=2) if args.json else render(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
