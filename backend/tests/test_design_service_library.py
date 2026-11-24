"""라이브러리 부품을 쓴 저장된 설계 (설계 문서 §9.6, §10): 폐기·차단 알림, 차단 부품의 내려받기 거절, 내려받는 파일 이름.

모의 해석기 + 임시 DB 로 API 를 거쳐 설계를 만들고, 색인 상태를 바꾼 뒤 다시 본다. 라이브러리 폴더·부품 등록은
tests/test_llm_library.py 의 도우미를 쓴다 (저장소의 index.json·species.yaml 은 건드리지 않는다).
"""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.design_service import export_base_name
from tests.api_helpers import make_settings
from tests.test_llm_library import DECK, JUNCTION, gated_rules, library_installed

ROOMY = {"width_mm": 1000, "depth_mm": 600, "height_mm": 400}
RETIRED = ("새 판으로 바꿨습니다", "Replaced by a new version")
BLOCKED = ("모서리가 날카롭습니다", "The edges are sharp")


def test_export_names_replace_the_at_sign_of_library_keys():
    assert export_base_name(0, "hideout") == "part1_hideout"
    assert export_base_name(2, "assembly") == "part3_assembly"
    assert export_base_name(1, "tunnel_junction@v1") == "part2_tunnel_junction-v1"
    assert export_base_name(0, "../x y") == "part1_---x-y"


@pytest.fixture
def lib_client(monkeypatch, tmp_path, rules_copy):
    """갈림길·발판 플랫폼·화장실 트레이를 게시하고 햄스터에 갈림길·발판 플랫폼을 허용한 앱."""
    with library_installed(monkeypatch, tmp_path / "lib") as lib:
        gated_rules(rules_copy, JUNCTION, DECK)
        with TestClient(create_app(make_settings(tmp_path, rules_dir=rules_copy))) as c:
            yield c, lib


def _design(c: TestClient, prompt: str) -> dict:
    r = c.post("/habitats", json={"species": "hamster", "size": "syrian", "count": 1, "cage": ROOMY})
    assert r.status_code == 201, r.text
    r = c.post("/designs", json={"habitat_id": r.json()["id"], "prompt": prompt})
    assert r.status_code == 201, r.text
    return r.json()


def _notices(cur: dict) -> list[dict]:
    return [i for i in cur["validation"]["issues"] if i["code"] in ("part_retired", "part_blocked")]


def test_retired_part_is_noted_and_blocked_part_cannot_be_downloaded(lib_client):
    c, lib = lib_client
    d = _design(c, "발판 플랫폼 하나랑 은신처 하나")
    cur = d["current"]
    assert [it["template"] for it in cur["items"]] == [DECK, "hideout"]
    assert cur["validation"]["passed"] and cur["export_allowed"], cur["validation"]
    assert _notices(cur) == []
    r = c.get(f"/designs/{d['id']}/export?format=stl")
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert sorted(zf.namelist()) == ["part1_deck_platform-v1.stl", "part2_hideout.stl"]

    # 폐기: 보기 화면에 경고로 알리고, 저장된 설계는 그대로 내려받는다
    lib.set_status(DECK, "retired", RETIRED)
    cur = c.get(f"/designs/{d['id']}").json()["current"]
    (n,) = _notices(cur)
    assert n["severity"] == "warning" and n["item_index"] == 0
    assert n["message_ko"] == "발판 플랫폼 부품은 더 이상 새 설계에 쓰지 않아요: 새 판으로 바꿨습니다"
    assert n["details"] == {"template": DECK, "status": "retired", "superseded_by": None}
    assert cur["validation"]["passed"] and cur["export_allowed"]
    assert cur["validation"]["summary"]["warnings"] >= 1
    assert c.get(f"/designs/{d['id']}/export?format=stl").status_code == 200

    # 차단: 경고로 알리고 내려받기를 막는다 (검증 결과는 그대로: 형상이 같으면 다시 검증하지 않는다)
    lib.set_status(DECK, "blocked", BLOCKED)
    cur = c.get(f"/designs/{d['id']}").json()["current"]
    (n,) = _notices(cur)
    assert n["code"] == "part_blocked"
    assert n["message_ko"] == "발판 플랫폼 부품은 안전 문제로 내려받을 수 없어요: 모서리가 날카롭습니다"
    assert cur["validation"]["passed"] and not cur["export_allowed"]
    for fmt in ("stl", "3mf"):
        r = c.get(f"/designs/{d['id']}/export?format={fmt}")
        assert r.status_code == 409, r.text
        body = r.json()["detail"]
        assert body["code"] == "part_blocked"
        assert "발판 플랫폼" in body["message_ko"]
        assert [e["code"] for e in body["errors"]] == ["part_blocked"]
    # 영어 화면: 알림 틀을 번역한다
    r = c.get(f"/designs/{d['id']}/export?format=stl", headers={"X-Lang": "en"})
    assert r.json()["detail"]["message_ko"].startswith("This design includes a part blocked for a safety problem")
    cur = c.get(f"/designs/{d['id']}", headers={"X-Lang": "en"}).json()["current"]
    assert "can't be downloaded because of a safety problem" in _notices(cur)[0]["message_ko"]

    # 다시 활성으로 되돌리면 알림도 막음도 없다 (색인 상태를 그때그때 읽는다)
    lib.set_status(DECK, "active")
    cur = c.get(f"/designs/{d['id']}").json()["current"]
    assert _notices(cur) == [] and cur["export_allowed"]


def test_blocked_part_inside_an_assembly_blocks_the_export(lib_client):
    c, lib = lib_client
    d = _design(c, "플랫폼 오른쪽에 램프")
    cur = d["current"]
    (item,) = cur["items"]
    assert item["template"] == "assembly" and cur["validation"]["passed"], cur["validation"]
    assert c.get(f"/designs/{d['id']}/export?format=stl").status_code == 200
    lib.set_status(DECK, "blocked", None)
    cur = c.get(f"/designs/{d['id']}").json()["current"]
    (n,) = _notices(cur)
    assert n["item_index"] == 0 and n["message_ko"] == "발판 플랫폼 부품은 안전 문제로 내려받을 수 없어요."
    assert not cur["export_allowed"]
    r = c.get(f"/designs/{d['id']}/export?format=stl")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "part_blocked"


def test_revision_drops_a_blocked_part_and_keeps_a_retired_one(lib_client):
    """수정: 폐기 부품은 직전 설계에서 계속 쓰고(sticky), 차단 부품은 해석기에 내놓지 않아 빠진다."""
    c, lib = lib_client
    d = _design(c, "플랫폼 오른쪽에 램프")
    lib.set_status(DECK, "retired", RETIRED)
    r = c.post(f"/designs/{d['id']}/revise", json={"prompt": "램프를 왼쪽으로 옮겨 줘"})
    assert r.status_code == 201, r.text
    cur = r.json()["current"]
    parts = [p["template"] for p in cur["items"][0]["assembly"]["parts"]]
    assert DECK in parts
    assert cur["validation"]["passed"], cur["validation"]
    assert [n["code"] for n in _notices(cur)] == ["part_retired"]

    lib.set_status(DECK, "blocked", BLOCKED)
    r = c.post(f"/designs/{d['id']}/revise", json={"prompt": "램프를 오른쪽으로 옮겨 줘"})
    assert r.status_code == 201, r.text
    cur = r.json()["current"]
    assert DECK not in str(cur["items"])
    assert _notices(cur) == [] and cur["export_allowed"] == cur["validation"]["passed"]
