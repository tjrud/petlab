"""부품 라이브러리 명령과 게시 수명 주기 (설계 §8, §9.1, §9.6).

임시 라이브러리 폴더(--library)에 게시한다. 저장소의 index.json·parts·reports·i18n/en/library.json 은 건드리지 않는다.
publish 는 원래 전체(full) 검증을 돌리지만 시험 시간을 줄이려고 publish.VERIFY_PROFILE 을 quick 으로 바꾼다.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.library import cli, index
from app.library import publish as pub
from app.library.publish import PublishError

BACKEND = Path(__file__).resolve().parents[1]
GOOD = BACKEND / "tests" / "data" / "library"


@pytest.fixture(autouse=True)
def code_only_rules(monkeypatch, rules_copy):
    """규칙은 라이브러리 키를 뺀 사본(rules_copy)으로 읽는다: 이 시험들은 임시 라이브러리(--library)를 쓰고, 저장소
    규칙이 게이팅한 부품(예: tunnel_junction@v1)은 그 라이브러리에 없다. 새 프로세스(G12)는 저장소 규칙·라이브러리를
    함께 읽으므로 그대로 맞다."""
    from app.config import get_settings
    from app.library.verify import run as verify_run
    from app.rules.loader import load_rules

    monkeypatch.setattr(get_settings(), "rules_dir", rules_copy)
    real = verify_run._rules
    monkeypatch.setattr(verify_run, "_rules", lambda rules: real(rules) if rules is not None else load_rules(rules_copy))


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(pub, "VERIFY_PROFILE", "quick")


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "lib"
    pub.init_library(root)
    yield pub.library_at(root)
    index.clear_cache()


def run_cli(*argv: str) -> int:
    return cli.main(list(argv))


def _entry(lib: pub.Library, key: str) -> dict:
    return pub.read_index(lib)["parts"][key]


# ── new / check ──

@pytest.mark.parametrize("role", cli.ROLES)
def test_new_writes_a_skeleton_that_passes_check(tmp_path, role, capsys):
    family = f"sk_{role}"
    assert run_cli("new", family, "--role", role, "--dir", str(tmp_path)) == 0
    path = tmp_path / f"{family}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["family"] == family and data["role"] == role and "key" not in data
    assert run_cli("check", str(path)) == 0
    assert "check: ok" in capsys.readouterr().out
    assert run_cli("new", family, "--role", role, "--dir", str(tmp_path)) == 1  # 덮어쓰지 않는다


def test_check_reports_pointers_and_hints_as_json(tmp_path, capsys):
    data = json.loads((GOOD / "litter_tray.json").read_text(encoding="utf-8"))
    data["body"][1]["size"][2] = "lip_height_mm - t"  # 자르는 면이 테두리와 겹친다 (L04)
    path = tmp_path / "litter_tray.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert run_cli("check", str(path), "--json") == 1
    out = json.loads(capsys.readouterr().out)
    assert not out["ok"]
    assert {f["id"] for f in out["failures"]} == {"L04"}
    assert all(f["path"].startswith("/body/1") and f["hint"] for f in out["failures"])


def test_check_rejects_broken_json(tmp_path, capsys):
    path = tmp_path / "x.json"
    path.write_text("{", encoding="utf-8")
    assert run_cli("check", str(path)) == 1
    assert "S01" in capsys.readouterr().out


def test_check_runs_without_the_kernel():
    code = ("import sys\nfrom app.library.cli import main\n"
            "rc = main(['check', 'tests/data/library/tunnel_junction.json'])\n"
            "heavy = [m for m in sys.modules if m.split('.')[0] in ('build123d', 'OCP', 'trimesh', 'anthropic')]\n"
            "print('HEAVY', heavy, 'RC', rc)\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    assert "HEAVY [] RC 0" in out.stdout


# ── 전체 흐름 ──

def test_new_check_verify_publish_retire_block_audit(tmp_path, lib, quick, capsys):
    drafts = tmp_path / "drafts"
    assert run_cli("new", "cli_dish", "--role", "none", "--dir", str(drafts)) == 0
    draft = drafts / "cli_dish.json"
    assert run_cli("check", str(draft), "--library", str(lib.root)) == 0
    report = tmp_path / "report.json"
    assert run_cli("verify", str(draft), "--quick", "--jobs", "1", "--report", str(report),
                   "--library", str(lib.root)) == 0
    out = capsys.readouterr().out
    assert "result=pass" in out and "budget 90s" in out
    rep = json.loads(report.read_text(encoding="utf-8"))
    assert rep["result"] == "pass" and rep["key"] == "cli_dish@v1" and rep["profile"] == "quick"

    assert run_cli("publish", str(draft), "--library", str(lib.root), "--requests", "req1,req2", "--jobs", "1") == 0
    out = capsys.readouterr().out
    key = "cli_dish@v1"
    assert f"published {key}" in out
    assert 'add "cli_dish@v1" to species.hamster.templates' in out
    assert "tests/test_library_published.py" in out
    assert "PATCH /admin/part-requests/req1" in out
    # 부품 파일: 정규 JSON, key·version 을 넣었다, sha 가 색인에 있다
    text = lib.part_path(key).read_text(encoding="utf-8")
    obj = json.loads(text)
    assert list(obj)[:4] == ["dsl", "key", "family", "version"] and obj["key"] == key and obj["version"] == 1
    assert text == json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    e = _entry(lib, key)
    assert e["sha256"] == index.sha256_bytes(text.encode()) and e["status"] == "active"
    assert e["request_ids"] == ["req1", "req2"] and e["role"] == "none"
    assert e["verified_for"] == {"hamster": ["dwarf", "syrian"]}
    assert set(e["golden"]) == {"hamster/dwarf/default", "hamster/syrian/default"}
    runs = pub.read_reports(lib, key)
    assert len(runs) == 1 and runs[0]["file_sha256"] == e["sha256"] and runs[0]["result"] == "pass"
    pairs = json.loads(lib.i18n_path.read_text(encoding="utf-8"))
    assert pairs["새 부품"] == "New part" and list(pairs) == sorted(pairs)

    assert run_cli("list", "--library", str(lib.root)) == 0
    assert key in capsys.readouterr().out
    assert run_cli("audit", "--library", str(lib.root)) == 0
    assert "audit: ok" in capsys.readouterr().out

    assert run_cli("retire", key, "--reason-ko", "새 판으로 바꿨습니다", "--reason-en", "Replaced by a new version",
                   "--library", str(lib.root)) == 0
    e = _entry(lib, key)
    assert e["status"] == "retired" and e["reason"]["en"] == "Replaced by a new version"
    assert json.loads(lib.i18n_path.read_text(encoding="utf-8"))["새 판으로 바꿨습니다"] == "Replaced by a new version"
    assert run_cli("block", key, "--reason-ko", "안전 문제가 있습니다", "--reason-en", "There is a safety problem",
                   "--library", str(lib.root)) == 0
    assert _entry(lib, key)["status"] == "blocked"
    assert run_cli("unretire", key, "--library", str(lib.root)) == 1  # 차단은 --force-unblock 없이 풀 수 없다
    assert run_cli("audit", "--library", str(lib.root)) == 0
    # 부품 파일은 그대로다 (R3)
    assert lib.part_path(key).read_text(encoding="utf-8") == text
    assert run_cli("unretire", key, "--force-unblock", "--library", str(lib.root)) == 0
    assert _entry(lib, key)["status"] == "active" and _entry(lib, key)["reason"] is None

    # 같은 초안을 다시 게시하면 v2 가 된다. 그 파일이 이미 있으면 거절한다
    lib.part_path("cli_dish@v2").write_text("{}", encoding="utf-8")
    assert run_cli("publish", str(draft), "--library", str(lib.root), "--jobs", "1") == 1
    assert "already exists" in capsys.readouterr().err
    assert "cli_dish@v2" not in pub.read_index(lib)["parts"]
    # 색인에 없는 파일이 생겼으니 audit 이 알린다
    assert any("not in the index" in p for p in pub.audit(lib, goldens=False))


def test_publish_refuses_code_families_drafts_with_keys_and_failing_drafts(tmp_path, lib, quick):
    for family, extra in (("hideout", {}), ("assembly", {})):
        d = cli.skeleton(family, "none")
        d.update(extra)
        p = tmp_path / f"{family}.json"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(PublishError, match="code part key or reserved"):
            pub.publish(p, lib=lib, out=lambda s: None)
    d = cli.skeleton("keyed_dish", "none")
    d["key"], d["version"] = "keyed_dish@v1", 1
    p = tmp_path / "keyed_dish.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PublishError, match="no key or version"):
        pub.publish(p, lib=lib, out=lambda s: None)
    bad = json.loads((BACKEND / "tests" / "data" / "library_bad" / "infeasible_defaults.json").read_text("utf-8"))
    p = tmp_path / "infeasible_defaults.json"
    p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PublishError, match="verify failed"):
        pub.publish(p, lib=lib, out=lambda s: None, jobs=1)
    assert pub.read_index(lib)["parts"] == {}
    assert not any((lib.root / "parts").iterdir())


def test_retire_rules(tmp_path, lib, quick):
    key = _publish_dish(tmp_path, lib)
    with pytest.raises(PublishError, match="not in the library index"):
        pub.retire("nope@v1", "까닭", "reason", lib=lib)
    with pytest.raises(PublishError, match="English"):
        pub.retire(key, "까닭", "한글 까닭", lib=lib)
    with pytest.raises(PublishError, match="superseded-by"):
        pub.retire(key, "까닭", "reason", superseded_by="other@v1", lib=lib)
    with pytest.raises(PublishError, match="already active"):
        pub.unretire(key, lib=lib)
    pub.retire(key, "까닭", "reason", lib=lib)
    pub.unretire(key, lib=lib)
    with pytest.raises(PublishError, match="already active"):
        pub.unretire(key, lib=lib)


def _publish_dish(tmp_path: Path, lib: pub.Library, family: str = "flow_dish") -> str:
    d = cli.skeleton(family, "none")
    p = tmp_path / f"{family}.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return pub.publish(p, lib=lib, out=lambda s: None, jobs=1).key


# ── regolden / reverify ──

def test_regolden_refuses_without_a_library_version_change(tmp_path, lib, quick, capsys):
    key = _publish_dish(tmp_path, lib)
    assert run_cli("regolden", "--library", str(lib.root)) == 1
    assert "needs --library-upgrade" in capsys.readouterr().err
    assert run_cli("regolden", "--library-upgrade", "--library", str(lib.root)) == 1
    assert "regolden refused" in capsys.readouterr().err
    assert len(pub.read_reports(lib, key)) == 1


def test_regolden_after_a_library_upgrade(tmp_path, lib, quick):
    key = _publish_dish(tmp_path, lib)
    path = lib.report_path(key)
    runs = json.loads(path.read_text(encoding="utf-8"))
    runs[-1]["libraries"] = {**runs[-1]["libraries"], "trimesh": "0.0.1"}  # 예전 버전으로 검증한 것처럼
    path.write_text(json.dumps(runs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    before = _entry(lib, key)["golden"]
    assert pub.regolden(library_upgrade=True, lib=lib, out=lambda s: None) == [key]
    runs = pub.read_reports(lib, key)
    assert len(runs) == 2 and runs[-1]["tag"] == "regolden" and runs[-1]["libraries"]["trimesh"] != "0.0.1"
    assert _entry(lib, key)["golden"] == before  # 같은 라이브러리로 다시 만들었으니 같다
    assert pub.audit(lib) == []


def test_reverify_apply_refreshes_or_retires(tmp_path, lib, quick, monkeypatch):
    key = _publish_dish(tmp_path, lib)
    res = pub.reverify([key], apply=True, lib=lib, jobs=1, out=lambda s: None)
    assert [(r.key, r.ok, r.applied) for r in res] == [(key, True, "refreshed")]
    assert len(pub.read_reports(lib, key)) == 2 and pub.read_reports(lib, key)[-1]["tag"] == "reverify"
    assert pub.audit(lib, goldens=False) == []

    from app.library.verify import run as run_mod
    from app.library.verify.report import failed

    real = run_mod.verify

    def failing(*a, **kw):
        s = real(*a, **kw)
        s.results.append(failed("G06", "hamster/dwarf/c1/default", "thinner than the new rule"))
        s.verified_for = {"hamster": ["syrian"]}
        return s

    monkeypatch.setattr(run_mod, "verify", failing)
    res = pub.reverify(None, apply=True, lib=lib, jobs=1, out=lambda s: None)
    assert [(r.ok, r.applied) for r in res] == [(False, "retired")]
    e = _entry(lib, key)
    assert e["status"] == "retired" and e["reason"] == pub.REVERIFY_REASON
    assert e["verified_for"] == {"hamster": ["dwarf", "syrian"]}  # 저장된 설계가 쓰므로 게이팅은 그대로 (R7)
    assert pub.read_reports(lib, key)[-1]["result"] == "fail"
    assert pub.audit(lib, goldens=False) == []  # 색인은 마지막으로 통과한 실행을 비춘다


def test_reverify_without_apply_changes_only_the_report(tmp_path, lib, quick):
    key = _publish_dish(tmp_path, lib)
    before = pub.read_index(lib)
    pub.reverify([key], lib=lib, jobs=1, out=lambda s: None)
    assert pub.read_index(lib) == before
    assert len(pub.read_reports(lib, key)) == 2


# ── preview, verify 출력, schema, demand ──

def test_verify_writes_failing_meshes(tmp_path, capsys):
    bad = BACKEND / "tests" / "data" / "library_bad" / "thin_wall.json"
    stl = tmp_path / "stl"
    assert run_cli("verify", str(bad), "--quick", "--jobs", "1", "--stl-dir", str(stl)) == 1
    out = capsys.readouterr().out
    assert "FAIL G06" in out
    files = sorted(p.name for p in stl.iterdir())
    assert "hamster_dwarf_c1_default_use.stl" in files and "hamster_dwarf_c1_default_print.stl" in files


def test_preview_writes_meshes_and_info(tmp_path):
    from app.library.preview import preview

    data = json.loads((GOOD / "tunnel_junction.json").read_text(encoding="utf-8"))
    res = preview(data, params={"layout": "X"}, species="hamster", size="syrian", out_dir=tmp_path,
                  key="tunnel_junction@v1")
    names = {p.name for p in res.files}
    assert {"use.stl", "print_body.stl", "info.json"} <= names
    info = json.loads((tmp_path / "info.json").read_text(encoding="utf-8"))
    assert info["params"]["layout"] == "X" and info["params"]["door_width_mm"] == 75.0
    assert {n: a["kind"] for n, a in info["anchors"].items()} == {
        "front": "door", "back": "door", "left": "door", "right": "door", "top": "plain", "bottom": "plain"}
    assert info["envelope"] == [101.0, 101.0, 89.0]
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        assert res.sheet_error and "uv run --with matplotlib" in res.sheet_error
    else:
        assert (tmp_path / "sheet.png").stat().st_size > 10_000


def test_schema_file_is_current(tmp_path):
    out = tmp_path / "part.schema.json"
    assert run_cli("schema", "--out", str(out)) == 0
    committed = BACKEND / "app" / "library" / "part.schema.json"
    assert out.read_text(encoding="utf-8") == committed.read_text(encoding="utf-8"), \
        "run `uv run python -m app.library schema`"
    schema = json.loads(out.read_text(encoding="utf-8"))
    assert schema["title"] == "NestForge Part DSL v1" and len(schema["examples"]) == 1


def test_demand_summary(tmp_path, lib, quick, capsys):
    d = cli.skeleton("demand_dish", "none")
    d["fulfills"] = ["쳇바퀴"]
    p = tmp_path / "demand_dish.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    pub.publish(p, lib=lib, out=lambda s: None, jobs=1)
    export = {"exported_at": "2026-11-24T00:00:00Z", "requests": [
        {"id": "a", "name_ko": "해먹", "users": 2, "count": 3, "species_counts": {"hamster/dwarf": 3},
         "purposes": ["매달려 쉬기"], "examples": [{"excerpt": "해먹 달린 은신처", "lang": "ko"}]},
        {"id": "b", "name_ko": "쳇바퀴", "users": 5, "count": 9, "purposes": ["달리기 운동"], "examples": []},
    ]}
    f = tmp_path / "demand.json"
    f.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
    assert run_cli("demand", str(f), "--library", str(lib.root)) == 0
    out = capsys.readouterr().out
    assert out.index("쳇바퀴") < out.index("해먹")  # 사용자 수 순
    assert "fulfilled_by=demand_dish@v1" in out and "purpose: 매달려 쉬기" in out and "example: 해먹 달린 은신처" in out


def test_published_tmp_library_loads_as_templates(tmp_path, lib, quick, monkeypatch):
    """게시한 파일은 load_library 가 그대로 읽는다 (sha, 스키마, 구조)."""
    from app.library.template import load_library

    key = _publish_dish(tmp_path, lib)
    monkeypatch.setattr(index, "LIBRARY_DIR", lib.root)
    index.clear_cache()
    loaded = load_library()
    assert list(loaded) == [key] and loaded[key].key == key
