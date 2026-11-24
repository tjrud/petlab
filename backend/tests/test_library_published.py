"""게시된 부품 라이브러리의 CI 검사 (설계 §8 audit, §9, R3–R5, R7, R8).

저장소의 app/library (index.json, parts/, reports/)와 app/i18n/en/library.json, rules/species.yaml 을 본다:
- 색인 ↔ 부품 파일 ↔ 보고서 (sha, 이름, 통과한 전체 검증)
- 마지막 보고서가 색인을 비춘다
- 골든을 다시 만들어 비교한다 (R4: 해석기 수정이 게시된 형상을 바꾸면 실패)
- species.yaml 게이팅과 LLM 스키마 예산 (R11, R12)
- 규칙 지문이 지금 규칙과 같다 (다르면 같은 PR 에서 `reverify --apply`)
- 영어 문구 파일이 다시 만든 짝과 같다
- 폐기 부품은 새 설계에 내놓지 않지만 레지스트리·allowed_templates 에는 남는다 (R7)
- app.library 는 anthropic 을 불러오지 않는다 (R5)

색인이 비어 있으면 앞의 검사들은 할 일이 없어 통과한다 (부품이 게시되면 그대로 검사가 된다).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from app.library import index
from app.library import publish as pub

BACKEND = Path(__file__).resolve().parents[1]
DRAFTS = BACKEND / "tests" / "data" / "library"


@pytest.fixture(scope="module")
def lib() -> pub.Library:
    return pub.default_library()


def test_index_files_and_reports_agree(lib):
    assert pub.audit_integrity(lib) == []


def test_latest_reports_mirror_the_index(lib):
    assert pub.audit_mirror(lib) == []


def test_goldens_rebuild_identically(lib, rules):
    t0 = time.perf_counter()
    assert pub.audit_goldens(lib, rules) == []
    n = max(1, len(index.entries()))
    assert time.perf_counter() - t0 <= 60.0 * n / 10 + 10  # §15: 부품 10개에 60 s


def test_species_gating_cross_check(lib, rules):
    assert pub.audit_gating(lib, rules.source_dir) == []


def test_reports_match_current_rules(lib, rules):
    assert pub.audit_rules_digests(lib, rules) == []


def test_i18n_library_file_is_current(lib):
    assert pub.audit_i18n(lib) == []


def test_every_published_part_is_registered():
    from app.templates.registry import primitives

    prim = primitives()
    for key in index.entries():
        t = prim[key]
        assert type(t).__module__ == "app.library.template"
        assert getattr(t, "retired", False) == (index.status(key) != "active")


def test_published_files_are_canonical(lib):
    for key, e in index.entries().items():
        text = lib.part_path(key).read_text(encoding="utf-8")
        obj = json.loads(text)
        assert list(obj)[:4] == ["dsl", "key", "family", "version"], key
        assert text == json.dumps(obj, ensure_ascii=False, indent=2) + "\n", key
        assert hashlib.sha256(text.encode()).hexdigest() == e.sha256


# ── 폐기 부품 (임시 라이브러리) ──

def _part_text(family: str, draft: str) -> str:
    raw = json.loads((DRAFTS / f"{draft}.json").read_text(encoding="utf-8"))
    raw["family"] = family
    raw["part_id"] = family
    raw["name"] = {"ko": "시험 갈림길", "en": "Test junction"}
    return pub.canonical_part(raw, f"{family}@v1", 1)


@pytest.fixture
def retired_library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    pub.init_library(root)
    key = "published_test_hub@v1"
    text = _part_text("published_test_hub", "tunnel_junction")
    (root / "parts" / f"{key}.json").write_text(text, encoding="utf-8")
    entry = {
        "sha256": hashlib.sha256(text.encode()).hexdigest(), "status": "retired", "published_at": "2026-12-01",
        "family": "published_test_hub", "version": 1, "role": "room_host", "habitats": ["cage"],
        "verified_for": {"hamster": ["dwarf", "syrian"]}, "rule_fields_used": ["entrance_min_diameter_mm"],
        "rules_digest": {}, "golden": {}, "superseded_by": None,
        "reason": {"ko": "새 판으로 바꿨습니다", "en": "Replaced by a new version"}, "request_ids": [],
    }
    (root / "index.json").write_text(index.dump_index({"v": 1, "parts": {key: entry}}), encoding="utf-8")
    monkeypatch.setattr(index, "LIBRARY_DIR", root)
    index.clear_cache()
    yield key
    index.clear_cache()


def test_retired_parts_are_not_offered_but_stay_registered_and_allowed(retired_library, rules_copy):
    from app.library.template import make_template
    from app.llm.spec import template_keys
    from app.rules.loader import load_rules
    from app.templates import registry

    key = retired_library
    p = rules_copy / "species.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data["species"]["hamster"]["templates"] = list(data["species"]["hamster"]["templates"]) + [key]
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    rules = load_rules(rules_copy)
    allowed, offered = rules.allowed_templates("hamster"), rules.offered_templates("hamster")
    assert key in allowed and key not in offered
    t = make_template(index.read_part(key), key=key, status="retired", published=True)
    with registry.overlay({key: t}):
        assert key in registry.primitives()
        assert key in template_keys(allowed)
        assert key not in template_keys(offered)
        assert registry.get_template(key).retired


# ── R5: 서버 쪽 AI 호출 없음 ──

def test_app_library_imports_no_anthropic():
    code = (
        "import json, pkgutil, importlib, sys\n"
        "import app.library\n"
        "mods = [m.name for m in pkgutil.walk_packages(app.library.__path__, 'app.library.') "
        "if not m.name.endswith('__main__')]\n"
        "for m in mods:\n"
        "    importlib.import_module(m)\n"
        "from app.llm.spec import api_schema\n"
        "from app.llm.prompts import template_catalog\n"
        "api_schema(); template_catalog()\n"
        "bad = sorted(m for m in sys.modules if m == 'anthropic' or m.startswith('anthropic.') "
        "or m in ('app.llm.anthropic_client', 'app.llm.factory'))\n"
        "print(json.dumps({'mods': mods, 'bad': bad}))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["bad"] == []
    for m in ("app.library.cli", "app.library.publish", "app.library.preview", "app.library.verify.dsl_checks",
              "app.library.verify.run", "app.library.template"):
        assert m in res["mods"]
