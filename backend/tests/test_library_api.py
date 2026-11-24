"""라이브러리 부품 표시 정보 GET /library/display (설계 문서 §13): 누구나, 가벼움, 영어 번역, 캐시 헤더.

라이브러리 폴더는 임시 폴더로 바꿔(index.LIBRARY_DIR monkeypatch) 쓴다. 저장소의 index.json 은 건드리지 않는다.
영어 문구는 게시 도구가 app/i18n/en/library.json 에 쓰는 것과 같은 짝(index.i18n_pairs)을 카탈로그에 더해 확인한다.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import i18n
from app.library import index
from app.main import create_app
from tests.api_helpers import make_settings, member_settings, signup, use

BACKEND = Path(__file__).resolve().parents[1]
DRAFTS = Path(__file__).resolve().parent / "data" / "library"
HANGUL = re.compile(r"[가-힣]")

JUNCTION = "tunnel_junction@v1"
DECK = "deck_platform@v1"
DECK2 = "deck_platform@v2"  # rules/species.yaml 이 허용하는 부품은 시험 라이브러리에도 있어야 규칙 파일이 읽힌다


def part_bytes(family: str, version: int = 1) -> bytes:
    """§6 초안(tests/data/library)에 key·version 을 넣은 게시 파일."""
    raw = json.loads((DRAFTS / f"{family}.json").read_text(encoding="utf-8"))
    obj = {"dsl": raw["dsl"], "key": f"{family}@v{version}", "family": family, "version": version}
    obj.update({k: v for k, v in raw.items() if k not in obj})
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode()


def make_library(root: Path, parts: dict[str, dict[str, Any]], reports: dict[str, Any] | None = None) -> Path:
    """임시 라이브러리 폴더. parts: key → 색인 항목 덮어쓰기. reports: key → reports/<key>.json 내용."""
    (root / "parts").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    entries = {}
    for key, over in parts.items():
        family, version = index.parse_key(key)  # type: ignore[misc]
        data = part_bytes(family, version)
        (root / "parts" / f"{key}.json").write_bytes(data)
        e: dict[str, Any] = {
            "sha256": hashlib.sha256(data).hexdigest(), "status": "active", "published_at": "2026-12-01",
            "family": family, "version": version, "role": "room_host", "habitats": ["cage"],
            "verified_for": {"hamster": ["dwarf", "syrian"]}, "rule_fields_used": [], "rules_digest": {},
            "golden": {}, "superseded_by": None, "reason": None, "request_ids": [],
        }
        e.update(over)
        entries[key] = e
    for key, runs in (reports or {}).items():
        (root / "reports" / f"{key}.json").write_text(json.dumps(runs, ensure_ascii=False), encoding="utf-8")
    (root / "index.json").write_text(index.dump_index({"v": 1, "parts": entries}), encoding="utf-8")
    return root


STANDARD = {
    JUNCTION: {},
    DECK: {"role": "host", "status": "retired", "superseded_by": DECK2,
           "reason": {"ko": "새 판으로 바꿨습니다", "en": "Replaced by a new version"}},
    DECK2: {"role": "host"},
}


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = make_library(tmp_path / "lib", {k: dict(v) for k, v in STANDARD.items()})
    monkeypatch.setattr(index, "LIBRARY_DIR", root)
    index.clear_cache()
    yield root
    index.clear_cache()


@pytest.fixture
def english(library, monkeypatch):
    """게시 뒤의 카탈로그: app/i18n/en/*.json + 라이브러리 문구 (library.json 이 하는 일)."""
    entries: dict[str, str] = {}
    for f in sorted((BACKEND / "app" / "i18n" / "en").glob("*.json")):
        entries.update(json.loads(f.read_text(encoding="utf-8")))
    entries.update(index.i18n_pairs())
    cat = i18n.Catalog(entries)
    monkeypatch.setattr(i18n, "catalog", lambda: cat)
    return cat


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


def _draft(family: str) -> dict:
    return json.loads((DRAFTS / f"{family}.json").read_text(encoding="utf-8"))


def test_display_lists_every_part_with_labels(library, client):
    r = client.get("/library/display")
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "max-age=300"
    parts = r.json()["parts"]
    assert sorted(parts) == [DECK, DECK2, JUNCTION]  # 폐기한 부품도 (저장된 설계를 보여 준다)

    draft = _draft("tunnel_junction")
    hub = parts[JUNCTION]
    assert hub["name_ko"] == draft["name"]["ko"] and hub["status"] == "active"
    assert hub["color"] == draft["color"]
    assert list(hub["params"]) == list(draft["params"])
    assert hub["params"]["door_width_mm"] == {"label_ko": index.desc_head(draft["params"]["door_width_mm"]["desc"]["ko"]),
                                              "unit": "mm"}
    assert hub["params"]["layout"]["unit"] is None
    assert hub["choices"]["layout"] == {v: {"label_ko": lab["ko"]}
                                        for v, lab in draft["params"]["layout"]["choice_labels"].items()}
    assert set(hub["choices"]) == {"layout", "door_shape"}
    assert parts[DECK]["status"] == "retired" and parts[DECK]["choices"] == {}


def test_display_is_translated_in_english(english, client):
    r = client.get("/library/display", headers={"X-Lang": "en"})
    assert r.status_code == 200, r.text
    hub = r.json()["parts"][JUNCTION]
    draft = _draft("tunnel_junction")
    assert hub["name_ko"] == draft["name"]["en"]
    assert hub["choices"]["door_shape"]["pointed_arch"]["label_ko"] == \
        draft["params"]["door_shape"]["choice_labels"]["pointed_arch"]["en"]
    # 모든 이름이 영어 (파라미터 키·선택지 값·색은 그대로)
    for key, part in r.json()["parts"].items():
        labels = [part["name_ko"]] + [p["label_ko"] for p in part["params"].values()] + \
                 [c["label_ko"] for ch in part["choices"].values() for c in ch.values()]
        assert not [s for s in labels if HANGUL.search(s)], (key, labels)
        assert set(part["params"]) == set(json.loads(part_bytes(key.split("@")[0]))["params"])
    assert r.headers["cache-control"] == "max-age=300" and "X-Lang" in r.headers["vary"]


def test_display_with_empty_library(tmp_path, monkeypatch, client):
    make_library(tmp_path / "empty", {})
    monkeypatch.setattr(index, "LIBRARY_DIR", tmp_path / "empty")
    index.clear_cache()
    try:
        assert client.get("/library/display").json() == {"parts": {}}
    finally:
        index.clear_cache()


def test_display_is_public_when_auth_is_on(library, tmp_path):
    with TestClient(create_app(member_settings(tmp_path))) as c:
        use(c, None)
        assert c.get("/library/display").status_code == 200
        signup(c, "member1")
        assert sorted(c.get("/library/display").json()["parts"]) == [DECK, DECK2, JUNCTION]


_LIGHT_SCRIPT = """
import sys, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.library import index
index.LIBRARY_DIR = Path(sys.argv[1])
from tests.api_helpers import admin_login, member_settings
from app.main import create_app
HEAVY = ("build123d", "OCP", "anthropic", "trimesh", "sklearn")
with TestClient(create_app(member_settings(Path(tempfile.mkdtemp())))) as c:
    r = c.get("/library/display", headers={"X-Lang": "en"})
    assert r.status_code == 200 and len(r.json()["parts"]) == 3, r.text
    admin_login(c)
    r = c.get("/admin/library")
    assert r.status_code == 200 and len(r.json()["parts"]) == 3, r.text
    assert c.get("/admin/part-requests/counts").status_code == 200
print("heavy=" + ",".join(h for h in HEAVY if h in sys.modules))
"""


def test_display_and_admin_library_are_light(library):
    """표시 정보와 관리자 라이브러리 목록은 형상 커널·LLM SDK 를 불러오지 않는다 (R9)."""
    out = subprocess.run([sys.executable, "-c", _LIGHT_SCRIPT, str(library)], cwd=BACKEND, capture_output=True,
                         text=True, timeout=120, check=False)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "heavy=", out.stdout
