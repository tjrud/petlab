"""가상 케이지 배치안 저장·불러오기·권한·입력 검증, 종 목록의 배치 규칙 값."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api_helpers import SYRIAN_CAGE as CAGE
from tests.api_helpers import member_settings, signup, use

ITEMS = [
    {"id": "a1", "asset": "wheel_280", "x_mm": 150, "y_mm": 200, "rotation_deg": 0},
    {"id": "a2", "asset": "hideout_house", "x_mm": 450, "y_mm": 120, "rotation_deg": 90},
]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(member_settings(tmp_path))) as c:
        yield c


def body(**kw) -> dict:
    b = {"name": "우리 집 케이지", "species": "hamster", "size": "syrian", "cage": CAGE, "items": ITEMS}
    b.update(kw)
    return b


def test_species_exposes_layout_rules(client):
    sizes = client.get("/species").json()["species"][0]["sizes"]
    syrian = next(s for s in sizes if s["key"] == "syrian")
    r = syrian["layout_rules"]
    assert r["gap_safe_max_mm"] < r["gap_passable_min_mm"]
    assert r["entrance_min_diameter_mm"] > 0 and r["max_climb_height_mm"] > 0
    assert r["hideout_min_entrances"] >= 1 and len(r["sand_bath_min_inner_mm"]) == 2
    assert r["enclosure_min_floor_mm"] == syrian["enclosure_min_floor_mm"]


def test_layouts_require_login(client):
    client.cookies.clear()
    assert client.get("/layouts").status_code == 401
    assert client.post("/layouts", json=body()).status_code == 401


def test_layout_crud_and_isolation(client):
    a = signup(client, "user_a")
    r = client.post("/layouts", json=body())
    assert r.status_code == 201, r.text
    lay = r.json()
    assert lay["item_count"] == 2 and lay["items"][1]["rotation_deg"] == 90 and lay["size_name_ko"]
    assert lay["cage"] == {"width_mm": 600, "depth_mm": 400, "height_mm": 300}

    r = client.put(f"/layouts/{lay['id']}", json=body(name="바꾼 이름", items=ITEMS[:1],
                                                       cage={"width_mm": 800, "depth_mm": 500, "height_mm": 400}))
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "바꾼 이름" and r.json()["item_count"] == 1 and r.json()["cage"]["width_mm"] == 800
    listed = client.get("/layouts").json()
    assert [x["id"] for x in listed] == [lay["id"]] and "items" not in listed[0]

    b = signup(client, "user_b")
    use(client, b)
    assert client.get("/layouts").json() == []
    assert client.get(f"/layouts/{lay['id']}").status_code == 404
    assert client.put(f"/layouts/{lay['id']}", json=body()).status_code == 404
    assert client.delete(f"/layouts/{lay['id']}").status_code == 404
    assert client.get("/layouts/not-an-id").status_code == 404

    use(client, a)
    assert client.get(f"/layouts/{lay['id']}").json()["items"] == ITEMS[:1]
    assert client.delete(f"/layouts/{lay['id']}").status_code == 204
    assert client.get("/layouts").json() == []


def test_layout_pet_link(client):
    signup(client, "user_a")
    pet = client.post("/me/pets", json={"name": "콩이", "species": "hamster", "size": "dwarf", "cage": CAGE}).json()
    lay = client.post("/layouts", json=body(size="dwarf", pet_id=pet["id"])).json()
    assert lay["pet_id"] == pet["id"]
    # 반려동물을 지워도 배치안은 남고 연결만 끊긴다
    assert client.delete(f"/me/pets/{pet['id']}").status_code == 204
    assert client.get(f"/layouts/{lay['id']}").json()["pet_id"] is None

    # 없는(지운) 반려동물로 저장하면 배치안 없음과 구분되는 코드로 알린다 (수정·새로 저장 모두)
    r = client.put(f"/layouts/{lay['id']}", json=body(size="dwarf", pet_id=pet["id"]))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "pet_not_found"
    missing = client.put("/layouts/" + "0" * 32, json=body())
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "not_found"

    other = signup(client, "user_b")
    use(client, other)
    r = client.post("/layouts", json=body(pet_id=pet["id"]))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "pet_not_found"


@pytest.mark.parametrize("override", [
    {"name": ""},
    {"name": "x" * 41},
    {"name": "두\n줄"},
    {"cage": {"width_mm": 10, "depth_mm": 400, "height_mm": 300}},
    {"items": [{"id": "a", "asset": "Wheel!", "x_mm": 0, "y_mm": 0, "rotation_deg": 0}]},
    {"items": [{"id": "a", "asset": "wheel", "x_mm": 0, "y_mm": 0, "rotation_deg": 360}]},
    {"items": [{"id": "a", "asset": "wheel", "x_mm": 9999, "y_mm": 0, "rotation_deg": 0}]},
    {"items": [{"id": "a", "asset": "wheel", "x_mm": 0, "y_mm": 0, "rotation_deg": 0, "extra": 1}]},
    {"items": [{"id": "a", "asset": "wheel", "x_mm": 0, "y_mm": 0, "rotation_deg": 0}] * 2},
    {"items": [{"id": f"i{i}", "asset": "bowl", "x_mm": 0, "y_mm": 0, "rotation_deg": 0} for i in range(81)]},
])
def test_layout_validation(client, override):
    signup(client, "user_a")
    assert client.post("/layouts", json=body(**override)).status_code == 422


def test_layout_unknown_species_and_limit(client):
    signup(client, "user_a")
    r = client.post("/layouts", json=body(species="rabbit"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_input"
    for i in range(30):
        assert client.post("/layouts", json=body(name=f"배치 {i}", items=[])).status_code == 201
    r = client.post("/layouts", json=body())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "too_many_layouts"
