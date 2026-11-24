"""부품 라이브러리의 가벼운 연결 (설계 문서 §9.4, §9.5): 템플릿 키 목록, 형상 지문, 종별 규칙의 게이팅.

라이브러리 폴더는 임시 폴더로 바꿔(index.LIBRARY_DIR monkeypatch) 쓴다. 저장소의 index.json 은 건드리지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.geometry import fingerprint as fp
from app.library import index
from app.rules.loader import RuleFileError, load_rules
from app.templates.keys import (
    TEMPLATE_MODULES,
    is_library_key,
    known_template_keys,
    library_template_keys,
)

BACKEND = Path(__file__).resolve().parents[1]
DRAFTS = Path(__file__).resolve().parent / "data" / "library"

JUNCTION = "tunnel_junction@v1"
DECK = "deck_platform@v1"
TRAY = "litter_tray@v1"


def _part_bytes(family: str, version: int = 1, draft: str | None = None) -> bytes:
    """§6 초안에 key·version 을 넣은 게시 파일 (publish 와 같은 정규 JSON)."""
    raw = json.loads((DRAFTS / f"{draft or family}.json").read_text(encoding="utf-8"))
    obj = {"dsl": raw["dsl"], "key": f"{family}@v{version}", "family": family, "version": version}
    obj.update({k: v for k, v in raw.items() if k not in obj})
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode()


def _entry(family: str, version: int, sha: str, **over: Any) -> dict[str, Any]:
    e: dict[str, Any] = {
        "sha256": sha, "status": "active", "published_at": "2026-12-01", "family": family, "version": version,
        "role": "room_host", "habitats": ["cage"], "verified_for": {"hamster": ["dwarf", "syrian"]},
        "rule_fields_used": ["entrance_min_diameter_mm"], "rules_digest": {}, "golden": {},
        "superseded_by": None, "reason": None, "request_ids": [],
    }
    e.update(over)
    return e


def make_library(root: Path, parts: dict[str, dict[str, Any]]) -> Path:
    """임시 라이브러리 폴더. parts: key → 색인 항목 덮어쓰기 (초안 파일은 family 이름으로 고른다)."""
    (root / "parts").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    entries = {}
    for key, over in parts.items():
        family, version = index.parse_key(key)  # type: ignore[misc]
        data = _part_bytes(family, version, draft=over.pop("_draft", None))
        (root / "parts" / f"{key}.json").write_bytes(data)
        entries[key] = _entry(family, version, hashlib.sha256(data).hexdigest(), **over)
    (root / "index.json").write_text(index.dump_index({"v": 1, "parts": entries}), encoding="utf-8")
    return root


@pytest.fixture
def use_library(monkeypatch, tmp_path):
    """make_library 로 만든 폴더를 라이브러리로 쓴다. 호출할 때마다 새 폴더."""
    counter = iter(range(1000))

    def _use(parts: dict[str, dict[str, Any]]) -> Path:
        root = make_library(tmp_path / f"lib{next(counter)}", {k: dict(v) for k, v in parts.items()})
        monkeypatch.setattr(index, "LIBRARY_DIR", root)
        index.clear_cache()
        return root

    yield _use
    index.clear_cache()


STANDARD = {
    JUNCTION: {},
    DECK: {"role": "host", "status": "retired",
           "rule_fields_used": ["max_climb_height_mm", "gap_trap.passable_min_mm", "entrance_min_diameter_mm"],
           "reason": {"ko": "새 판으로 바꿨습니다", "en": "Replaced by a new version"}},
    TRAY: {"role": "accessory", "status": "blocked",
           "rule_fields_used": ["max_step_height_mm", "gap_trap.passable_min_mm"],
           "reason": {"ko": "안전 문제가 있습니다", "en": "There is a safety problem"}},
}


def _edit_species(rules_dir: Path, fn) -> None:
    p = rules_dir / "species.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    fn(data)
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _add_hamster(rules_dir: Path, *keys: str) -> None:
    _edit_species(rules_dir, lambda d: d["species"]["hamster"].update(
        templates=list(d["species"]["hamster"]["templates"]) + list(keys)))


# ── 템플릿 키 ─────────────────────────────────────────────────

def test_known_template_keys_with_empty_library(use_library):
    use_library({})
    assert known_template_keys() == tuple(TEMPLATE_MODULES)
    assert library_template_keys() == ()
    assert not is_library_key("hideout") and not is_library_key(JUNCTION)


def test_known_template_keys_add_library_keys_after_code_keys(use_library):
    use_library(STANDARD)
    # 코드 부품 순서 그대로, 뒤에 라이브러리 부품 (key 순, 폐기·차단 포함)
    assert known_template_keys() == tuple(TEMPLATE_MODULES) + (DECK, TRAY, JUNCTION)
    assert library_template_keys() == (DECK, TRAY, JUNCTION)
    assert all(is_library_key(k) for k in (DECK, TRAY, JUNCTION))
    assert not is_library_key("tunnel") and not is_library_key("ghost@v1") and not is_library_key("assembly")
    assert TEMPLATE_MODULES["tunnel"] == "app.templates.tunnel"  # 코드 부품 표는 그대로


# ── 형상 지문 ─────────────────────────────────────────────────

def _expected_library_digest(sha: str) -> str:
    payload = {"file": sha, "dsl": [fp._module_digest(m) for m in fp.DSL_MODULES]}
    return fp.file_digest(json.dumps(payload, sort_keys=True).encode())


def test_dsl_modules_include_the_tunnel_profile_source():
    assert fp.DSL_MODULES == ("app.library.template", "app.library.ops", "app.library.expr", "app.library.schema",
                              "app.templates.tunnel")
    # 공용 모듈은 늘리지 않는다: 코드 부품 지문이 그대로여야 한다
    assert not set(fp.DSL_MODULES) & set(fp.SHARED_MODULES)


def test_library_key_digest_is_file_sha_plus_dsl_code(use_library):
    root = use_library(STANDARD)
    sha = index.entry(JUNCTION).sha256
    assert sha == hashlib.sha256((root / "parts" / f"{JUNCTION}.json").read_bytes()).hexdigest()
    assert fp._template_digest(JUNCTION) == _expected_library_digest(sha)
    # 폐기·차단 부품도 지문이 있다 (저장된 설계를 다시 만든다)
    for key in (DECK, TRAY):
        assert fp._template_digest(key) == _expected_library_digest(index.entry(key).sha256)
    assert len({fp._template_digest(k) for k in (JUNCTION, DECK, TRAY)}) == 3


def test_unknown_keys_are_missing(use_library):
    use_library(STANDARD)
    for key in ("ghost@v1", "tunnel_junction@v2", "burrow", ""):
        assert fp._template_digest(key) == "missing"


def test_library_digest_follows_the_file_and_the_dsl_code(use_library, monkeypatch):
    use_library(STANDARD)
    before = fp._template_digest(JUNCTION)
    # 같은 key 에 다른 파일 (실제로는 R3 로 일어나지 않지만, 바뀌면 지문이 따라 바뀐다)
    use_library({JUNCTION: {"_draft": "deck_platform"}})
    assert fp._template_digest(JUNCTION) != before
    use_library(STANDARD)
    assert fp._template_digest(JUNCTION) == before
    # DSL 해석 코드가 바뀌면 모든 라이브러리 부품의 지문이 바뀐다 (코드 부품은 그대로)
    code_before = {k: fp._template_digest(k) for k in TEMPLATE_MODULES}
    real = fp._module_digest
    monkeypatch.setattr(fp, "_module_digest",
                        lambda name: "changed" if name == "app.library.ops" else real(name))
    assert fp._template_digest(JUNCTION) != before
    assert {k: fp._template_digest(k) for k in TEMPLATE_MODULES} == code_before


def test_code_fingerprints_unchanged_by_library(use_library, rules):
    """라이브러리에 부품이 있어도 코드 부품 키·여러 키·조립 항목의 지문은 그대로다 (설계 문서 §3.4)."""
    code_keys = sorted(TEMPLATE_MODULES)
    stored_assembly = {"template": "assembly", "params": {}, "assembly": {
        "v": 1, "root": "hide",
        "parts": [{"id": "hide", "template": "hideout"}, {"id": "tube", "template": "tunnel"}],
        "joins": []}}

    def snapshot() -> dict[str, str]:
        out = {k: fp.geometry_fingerprint([k], rules.printing) for k in code_keys}
        out["*all"] = fp.geometry_fingerprint(code_keys, rules.printing)
        out["*items"] = fp.geometry_fingerprint([{"template": "ramp", "params": {}}, stored_assembly],
                                                rules.printing)
        return out

    use_library({})
    empty = snapshot()
    use_library(STANDARD)
    assert snapshot() == empty


def test_library_key_fingerprint_in_items_and_assemblies(use_library, rules):
    use_library(STANDARD)
    single = fp.geometry_fingerprint([{"template": JUNCTION, "params": {}}], rules.printing)
    assert single == fp.geometry_fingerprint([JUNCTION], rules.printing)
    assembly = {"template": "assembly", "params": {}, "assembly": {
        "v": 1, "root": "hide",
        "parts": [{"id": "hide", "template": "hideout"}, {"id": "hub", "template": JUNCTION}],
        "joins": []}}
    _, value = fp._assembly_entry(assembly["assembly"])
    with_library = fp.geometry_fingerprint([assembly], rules.printing)
    use_library({})  # 같은 기록인데 라이브러리에서 부품이 사라지면 "missing" 으로 바뀐다
    assert fp._assembly_entry(assembly["assembly"])[1] != value
    assert fp.geometry_fingerprint([assembly], rules.printing) != with_library
    assert fp.geometry_fingerprint([JUNCTION], rules.printing) != single


_LIGHT_SCRIPT = """
import sys
from pathlib import Path
from app.library import index
index.LIBRARY_DIR = Path(sys.argv[1])
from app.geometry.fingerprint import geometry_fingerprint
from app.rules.loader import load_rules
from app.templates.keys import known_template_keys
rules = load_rules(Path(sys.argv[2]))
keys = known_template_keys()
fps = [geometry_fingerprint([k], rules.printing) for k in keys]
offered = rules.offered_templates("hamster")
HEAVY = ("build123d", "OCP", "anthropic", "trimesh", "sklearn", "app.library.template", "app.library.ops")
print("keys=" + ",".join(keys))
print("offered=" + ",".join(offered))
print("heavy=" + ",".join(h for h in HEAVY if h in sys.modules))
"""


def test_keys_fingerprint_and_gating_stay_light(tmp_path, rules_copy):
    """키 목록·지문·게이팅은 형상 커널·DSL 해석 코드·anthropic 을 불러오지 않는다 (R9)."""
    lib = make_library(tmp_path / "lib", {k: dict(v) for k, v in STANDARD.items()})
    _add_hamster(rules_copy, JUNCTION, DECK, TRAY)
    out = subprocess.run([sys.executable, "-c", _LIGHT_SCRIPT, str(lib), str(rules_copy)], cwd=BACKEND,
                         capture_output=True, text=True, timeout=120, check=False)
    assert out.returncode == 0, out.stderr[-2000:]
    lines = out.stdout.strip().splitlines()
    assert lines[-3] == "keys=" + ",".join(tuple(TEMPLATE_MODULES) + (DECK, TRAY, JUNCTION))
    assert lines[-2].endswith("," + JUNCTION) and DECK not in lines[-2] and TRAY not in lines[-2]
    assert lines[-1] == "heavy=", lines[-1]


# ── 종별 게이팅 (rules/species.yaml) ───────────────────────────

def test_species_can_list_verified_library_parts(use_library, rules_copy):
    use_library(STANDARD)
    _add_hamster(rules_copy, JUNCTION, DECK, TRAY)
    rb = load_rules(rules_copy)
    allowed = rb.allowed_templates("hamster")
    assert allowed[-3:] == (JUNCTION, DECK, TRAY)
    assert rb.species_entry("hamster").library_templates == (JUNCTION, DECK, TRAY)
    # 폐기·차단 부품은 새 설계에 내놓지 않지만 allowed 에는 남는다 (저장된 설계 재검증, R7)
    offered = rb.offered_templates("hamster")
    assert offered == tuple(k for k in allowed if k not in (DECK, TRAY))
    assert JUNCTION in offered
    assert rb.offered_templates("aquarium") == rb.allowed_templates("aquarium")


def test_offered_follows_the_index_status_at_call_time(use_library, rules_copy):
    use_library(STANDARD)
    _add_hamster(rules_copy, JUNCTION, DECK)
    rb = load_rules(rules_copy)
    assert DECK not in rb.offered_templates("hamster")
    use_library({**STANDARD, DECK: {**STANDARD[DECK], "status": "active", "reason": None}})
    assert DECK in rb.offered_templates("hamster")
    use_library({**STANDARD, JUNCTION: {"status": "blocked"}})
    assert JUNCTION not in rb.offered_templates("hamster")
    assert JUNCTION in rb.allowed_templates("hamster")


def test_code_only_species_do_not_read_the_index(monkeypatch, tmp_path, rules_copy):
    """라이브러리 부품을 적지 않은 규칙 파일은 색인 없이도 읽힌다 (offered 도 색인을 읽지 않는다)."""
    monkeypatch.setattr(index, "LIBRARY_DIR", tmp_path / "nowhere")
    index.clear_cache()
    try:
        rb = load_rules(rules_copy)
        assert rb.offered_templates("hamster") == rb.allowed_templates("hamster")
    finally:
        index.clear_cache()


def test_broken_index_stops_loading_rules_that_use_it(monkeypatch, tmp_path, rules_copy):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "index.json").write_text('{"v": 1, "parts": {"bad": {}}}', encoding="utf-8")
    monkeypatch.setattr(index, "LIBRARY_DIR", tmp_path / "lib")
    index.clear_cache()
    _add_hamster(rules_copy, JUNCTION)
    try:
        with pytest.raises(index.LibraryError):
            load_rules(rules_copy)
    finally:
        index.clear_cache()


def test_unknown_library_key_rejected(use_library, rules_copy):
    use_library(STANDARD)
    _add_hamster(rules_copy, "tunnel_junction@v2")
    with pytest.raises(RuleFileError, match=r"(?s)알 수 없는 템플릿 키.*tunnel_junction@v2.*tunnel_junction@v1"):
        load_rules(rules_copy)


def test_unverified_size_rejected(use_library, rules_copy):
    use_library({JUNCTION: {"verified_for": {"hamster": ["dwarf"]}}})
    _add_hamster(rules_copy, JUNCTION)
    with pytest.raises(RuleFileError, match=r"tunnel_junction@v1 은\(는\) hamster/syrian 에서 검증하지 않았습니다"):
        load_rules(rules_copy)


def test_unverified_species_rejected(use_library, rules_copy):
    use_library({JUNCTION: {"verified_for": {"gerbil": ["small"]}}})
    _add_hamster(rules_copy, JUNCTION)
    with pytest.raises(RuleFileError, match=r"hamster/dwarf 에서 검증하지 않았습니다"):
        load_rules(rules_copy)


def test_null_rule_field_rejected(use_library, rules_copy):
    """부품이 읽는 규칙 값이 어느 크기 구분에서 null 이면 그 종에 쓸 수 없다 (R11)."""
    use_library({JUNCTION: {"rule_fields_used": ["entrance_min_diameter_mm", "sand_bath_min_depth_mm"]}})

    def edit(d):
        hamster = d["species"]["hamster"]
        hamster["templates"] = ["hideout", JUNCTION]  # 모래목욕통이 없으면 sand_bath_min_depth_mm 는 null 이어도 된다
        hamster["sizes"]["syrian"].pop("sand_bath_min_depth_mm")

    _edit_species(rules_copy, edit)
    with pytest.raises(RuleFileError, match=r"(?s)sand_bath_min_depth_mm.*hamster.*\['syrian'\]"):
        load_rules(rules_copy)
    # 같은 파일에서 부품만 빼면 읽힌다
    _edit_species(rules_copy, lambda d: d["species"]["hamster"].update(templates=["hideout"]))
    assert load_rules(rules_copy).allowed_templates("hamster") == ("hideout",)


def test_nested_rule_fields_are_resolved(use_library, rules_copy):
    use_library({JUNCTION: {"rule_fields_used": ["gap_trap.safe_max_mm", "gap_trap.passable_min_mm"]}})
    _add_hamster(rules_copy, JUNCTION)
    assert JUNCTION in load_rules(rules_copy).allowed_templates("hamster")
    use_library({JUNCTION: {"rule_fields_used": ["gap_trap.no_such_field"]}})
    with pytest.raises(RuleFileError, match="gap_trap.no_such_field"):
        load_rules(rules_copy)


def test_library_part_outside_its_habitat_rejected(use_library, rules_copy):
    use_library({JUNCTION: {"verified_for": {"hamster": ["dwarf", "syrian"], "aquarium": ["nano", "small"]}}})
    _edit_species(rules_copy, lambda d: d["species"]["aquarium"].update(templates=["cave", "tunnel", JUNCTION]))
    with pytest.raises(RuleFileError, match=r"(?s)라이브러리 부품 tunnel_junction@v1 는 habitat aquarium"):
        load_rules(rules_copy)


def test_cage_species_rejects_an_aquarium_only_library_part(use_library, rules_copy):
    use_library({JUNCTION: {"habitats": ["aquarium"]}})
    _add_hamster(rules_copy, JUNCTION)
    with pytest.raises(RuleFileError, match=r"(?s)tunnel_junction@v1 는 habitat cage"):
        load_rules(rules_copy)


def test_duplicate_library_key_rejected(use_library, rules_copy):
    use_library(STANDARD)
    _add_hamster(rules_copy, JUNCTION, JUNCTION)
    with pytest.raises(RuleFileError, match="두 번"):
        load_rules(rules_copy)
