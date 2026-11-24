"""부품 라이브러리 색인 (app/library/index.py, 설계 §9.1, §9.2)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.library import index
from app.library.index import IndexFile, LibraryError, dump_index, sha256_bytes
from app.library.schema import parse_part

DATA = Path(__file__).parent / "data" / "library"
BACKEND = Path(__file__).resolve().parents[1]


def draft(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def as_published(d: dict, version: int = 1) -> dict:
    d = dict(d)
    out = {"dsl": d.pop("dsl"), "key": f"{d['family']}@v{version}", "family": d.pop("family"), "version": version}
    out.update(d)
    return out


def part_text(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def make_library(root: Path, parts: list[tuple[dict, str, dict | None]]) -> Path:
    """parts: (게시 파일 dict, 상태, 까닭). 부품 파일과 index.json 을 쓴다."""
    (root / "parts").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    entries = {}
    for obj, status, reason in parts:
        key = obj["key"]
        data = part_text(obj)
        (root / "parts" / f"{key}.json").write_bytes(data)
        entries[key] = {
            "sha256": sha256_bytes(data), "status": status, "published_at": "2026-12-03",
            "family": obj["family"], "version": obj["version"], "role": obj["role"], "habitats": obj["habitats"],
            "verified_for": {"hamster": ["dwarf", "syrian"]}, "rule_fields_used": ["entrance_min_diameter_mm"],
            "rules_digest": {"hamster/dwarf": "e31c", "hamster/syrian": "9a07"},
            "golden": {"hamster/dwarf/default": {"params": {"size_mm": 81.0}, "files": {"print_0.stl": "9b1e"}}},
            "superseded_by": None, "reason": reason, "request_ids": ["7f3c"],
        }
    (root / "index.json").write_text(dump_index({"v": 1, "parts": entries}), encoding="utf-8")
    return root


@pytest.fixture
def lib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    junction = as_published(draft("tunnel_junction"))
    deck = as_published(draft("deck_platform"))
    tray = as_published(draft("litter_tray"))
    tray2 = as_published(draft("litter_tray"), version=2)
    root = make_library(tmp_path / "library", [
        (junction, "active", None),
        (deck, "retired", {"ko": "기준이 바뀌어 다시 검증이 필요합니다", "en": "The rules changed; re-verify"}),
        (tray, "blocked", {"ko": "안전 문제", "en": "Safety problem"}),
        (tray2, "active", None),
    ])
    monkeypatch.setattr(index, "LIBRARY_DIR", root)
    yield root
    index.clear_cache()


def test_repository_index_is_empty_and_valid() -> None:
    raw = json.loads((BACKEND / "app" / "library" / "index.json").read_text(encoding="utf-8"))
    assert raw == {"v": 1, "parts": {}}
    assert index.keys() == ()
    assert index.integrity_problems() == []
    assert (BACKEND / "app" / "library" / "parts" / ".gitkeep").exists()
    assert (BACKEND / "app" / "library" / "reports" / ".gitkeep").exists()


def test_entries_and_statuses(lib: Path) -> None:
    keys = ("deck_platform@v1", "litter_tray@v1", "litter_tray@v2", "tunnel_junction@v1")
    assert index.keys() == keys
    assert list(index.entries()) == list(keys)
    e = index.entry("tunnel_junction@v1")
    assert e is not None and e.status == "active" and e.key == "tunnel_junction@v1" and e.role == "room_host"
    assert e.verified_for == {"hamster": ["dwarf", "syrian"]}
    assert e.golden["hamster/dwarf/default"].files == {"print_0.stl": "9b1e"}
    assert index.entry("nope@v1") is None
    assert index.status("deck_platform@v1") == "retired"
    assert index.status("litter_tray@v1") == "blocked"
    assert index.status("hideout") is None
    assert index.is_library_key("litter_tray@v2") and not index.is_library_key("hideout")
    assert index.hidden_keys() == {"deck_platform@v1", "litter_tray@v1"}
    assert index.blocked_keys() == {"litter_tray@v1"}
    assert index.active_keys() == ("litter_tray@v2", "tunnel_junction@v1")
    assert index.part_path("deck_platform@v1") == lib / "parts" / "deck_platform@v1.json"
    assert index.integrity_problems() == []


def test_read_part_returns_fresh_copies(lib: Path) -> None:
    a = index.read_part("tunnel_junction@v1")
    a["name"]["ko"] = "바뀜"
    b = index.read_part("tunnel_junction@v1")
    assert b["name"]["ko"] == "터널 갈림길"
    parse_part(b, published=True, stem="tunnel_junction@v1")
    with pytest.raises(LibraryError):
        index.read_part("nope@v1")


def test_sha_mismatch_fails_fast(lib: Path) -> None:
    path = lib / "parts" / "tunnel_junction@v1.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    obj["name"]["ko"] = "고친 이름"
    path.write_bytes(part_text(obj))
    with pytest.raises(LibraryError, match="sha256"):
        index.read_part("tunnel_junction@v1")
    assert any("sha256 mismatch" in p for p in index.integrity_problems())


def test_missing_file(lib: Path) -> None:
    (lib / "parts" / "deck_platform@v1.json").unlink()
    with pytest.raises(LibraryError, match="missing"):
        index.read_part("deck_platform@v1")
    assert index.integrity_problems() == ["deck_platform@v1: part file missing (deck_platform@v1.json)"]
    with pytest.raises(LibraryError):
        index.display_meta()


def test_stem_differs_from_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    obj = as_published(draft("deck_platform"))
    root = make_library(tmp_path / "lib", [(obj, "active", None)])
    # 파일 안의 key 를 바꾸고 색인 sha 도 맞춘다: 파일 이름과 key 가 다르다
    path = root / "parts" / "deck_platform@v1.json"
    obj2 = dict(obj, key="deck_platform@v2", version=2)
    path.write_bytes(part_text(obj2))
    idx = json.loads((root / "index.json").read_text(encoding="utf-8"))
    idx["parts"]["deck_platform@v1"]["sha256"] = sha256_bytes(path.read_bytes())
    (root / "index.json").write_text(dump_index(idx), encoding="utf-8")
    # 색인에 없는 파일
    (root / "parts" / "stray@v1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(index, "LIBRARY_DIR", root)
    problems = index.integrity_problems()
    assert any("does not match the file name" in p for p in problems)
    assert any("family/version" in p for p in problems)
    assert "stray@v1.json: not in the index" in problems


def test_invalid_index_fails_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    monkeypatch.setattr(index, "LIBRARY_DIR", root)
    with pytest.raises(LibraryError, match="missing"):
        index.keys()
    (root / "index.json").write_text("{", encoding="utf-8")
    index.clear_cache()
    with pytest.raises(LibraryError, match="invalid JSON"):
        index.keys()
    good = make_library(tmp_path / "good", [(as_published(draft("deck_platform")), "active", None)])
    idx = json.loads((good / "index.json").read_text(encoding="utf-8"))
    for mutate in (
        lambda d: d["parts"]["deck_platform@v1"].update(status="gone"),
        lambda d: d["parts"]["deck_platform@v1"].update(version=2),
        lambda d: d["parts"]["deck_platform@v1"].update(sha256="abc"),
        lambda d: d["parts"]["deck_platform@v1"].update(extra=1),
        lambda d: d.update(v=2),
    ):
        bad = json.loads(json.dumps(idx))
        mutate(bad)
        (root / "index.json").write_text(json.dumps(bad), encoding="utf-8")
        index.clear_cache()
        with pytest.raises(LibraryError, match="invalid index"):
            index.keys()
    index.clear_cache()


def test_cache_is_per_directory(lib: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert len(index.keys()) == 4
    other = make_library(tmp_path / "other", [(as_published(draft("deck_platform")), "active", None)])
    monkeypatch.setattr(index, "LIBRARY_DIR", other)
    assert index.keys() == ("deck_platform@v1",)
    monkeypatch.setattr(index, "LIBRARY_DIR", lib)
    assert len(index.keys()) == 4


def test_display_meta(lib: Path) -> None:
    meta = index.display_meta()
    assert set(meta) == set(index.keys())  # 폐기·차단 부품도 저장된 설계를 보여 주려고 넣는다
    j = meta["tunnel_junction@v1"]
    assert j["name_ko"] == "터널 갈림길" and j["color"] == "#c9a46e" and j["status"] == "active"
    assert j["params"]["door_width_mm"] == {"label_ko": "출입구 폭", "unit": "mm"}
    assert j["params"]["layout"] == {"label_ko": "출입구 배치", "unit": None}
    assert j["params"]["wall_thickness_mm"]["label_ko"] == "벽·지붕 두께"
    assert j["choices"]["layout"] == {"I": {"label_ko": "일자"}, "L": {"label_ko": "기역자"},
                                      "T": {"label_ko": "T자"}, "X": {"label_ko": "십자"}}
    assert j["choices"]["door_shape"]["house"] == {"label_ko": "집 모양"}
    assert meta["deck_platform@v1"]["status"] == "retired" and meta["deck_platform@v1"]["choices"] == {}
    assert meta["litter_tray@v1"]["status"] == "blocked"


def test_desc_head_matches_autofix() -> None:
    from pydantic import BaseModel, Field

    from app.validation.autofix import _desc

    for text in ("출입구 폭 mm. 종별 최소 출입구 폭 이상", "출입구 배치. I=앞·뒤", "벽·지붕 두께 mm", "Door width mm. At least"):
        class M(BaseModel):
            x: float = Field(1, description=text)

        assert index.desc_head(text) == _desc(M, "x")


def test_i18n_pairs(lib: Path) -> None:
    pairs = index.i18n_pairs()
    assert list(pairs) == sorted(pairs)
    expected = {
        "터널 갈림길": "Tunnel junction",
        "발판 플랫폼": "Deck platform",
        "화장실 트레이": "Litter tray",
        "벽·지붕 두께": "Wall and roof thickness",
        "출입구 배치": "Door layout",
        "출입구 폭": "Door width",
        "일자": "Straight",
        "뾰족 아치": "Pointed arch",
        "{1} 갈림길 출입구는 최소 {0}mm 이상이어야 합니다": "{1} junction doors must be at least {0} mm wide",
        "본체": "Body",
        "발판 아래 통로": "Passage under the deck",
        "기준이 바뀌어 다시 검증이 필요합니다": "The rules changed; re-verify",
        "안전 문제": "Safety problem",
    }
    for ko, en in expected.items():
        assert pairs.get(ko) == en, ko
    assert index.i18n_conflicts() == []
    # 설명 전체(_desc 머리가 아닌 문장)는 넣지 않는다
    assert not any(ko.startswith("출입구 폭 mm") for ko in pairs)


def test_part_pairs_on_a_draft() -> None:
    pairs = index.part_pairs(draft("tunnel_junction"))
    assert pairs[0] == ("터널 갈림길", "Tunnel junction")
    assert ("외형 높이", "Outer height") in pairs
    assert ("T자", "T-piece") in pairs


def test_i18n_conflicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = as_published(draft("deck_platform"))
    b = as_published(draft("litter_tray"))
    b["print"][0]["name"]["en"] = "Main body"
    root = make_library(tmp_path / "c", [(a, "active", None), (b, "active", None)])
    monkeypatch.setattr(index, "LIBRARY_DIR", root)
    assert index.i18n_conflicts() == [("본체", "Body", "Main body")]
    assert index.i18n_pairs()["본체"] == "Body"  # key 순으로 처음 것


def test_keywords_part_ids_fulfills(lib: Path) -> None:
    kw = index.keywords()
    assert set(kw) == {"tunnel_junction@v1", "litter_tray@v2"}  # 활성 부품만
    assert kw["tunnel_junction@v1"]["ko"][0] == "갈림길" and "junction" in kw["tunnel_junction@v1"]["en"]
    assert index.part_ids() == {"deck_platform@v1": "deck", "litter_tray@v1": "toilet", "litter_tray@v2": "toilet",
                                "tunnel_junction@v1": "hub"}
    assert index.fulfills() == {"litter_tray@v2": ["화장실", "배변통", "모래화장실", "구석화장실"],
                                "tunnel_junction@v1": ["터널갈림길", "터널분기", "터널연결부"]}


def test_parse_key_and_dump_index() -> None:
    assert index.parse_key("tunnel_junction@v12") == ("tunnel_junction", 12)
    assert index.parse_key("hideout") is None
    assert index.parse_key("tunnel_junction@v0") is None
    text = dump_index({"v": 1, "parts": {"b_part@v1": {"x": 1}, "a_part@v1": {"x": 2}}})
    assert list(json.loads(text)["parts"]) == ["a_part@v1", "b_part@v1"] and text.endswith("}\n")
    model = IndexFile.model_validate({"v": 1, "parts": {}})
    assert dump_index(model) == '{\n  "v": 1,\n  "parts": {}\n}\n'
    assert (BACKEND / "app" / "library" / "index.json").read_text(encoding="utf-8") == dump_index(model)


def test_light_modules_import_no_kernel() -> None:
    """index·schema·expr·errors 는 형상 커널·LLM 클라이언트를 불러오지 않는다 (R9)."""
    code = ("import sys\n"
            "import app.library.index, app.library.schema, app.library.expr, app.library.errors\n"
            "from app.library import index\n"
            "index.keys(); index.display_meta(); index.i18n_pairs(); index.integrity_problems()\n"
            "heavy = ('build123d', 'OCP', 'trimesh', 'sklearn', 'anthropic', 'numpy', 'shapely', 'sqlalchemy')\n"
            "print([m for m in heavy if m in sys.modules or any(k.startswith(m + '.') for k in sys.modules)])\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=BACKEND, check=True)
    assert out.stdout.strip() == "[]", out.stdout + out.stderr
