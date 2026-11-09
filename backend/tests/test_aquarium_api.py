"""어항 종의 API 계약: /species 필드, 마릿수 상한, habitat_kind, 가상 케이지 제한, 모의 해석기로 만드는 설계 전체 흐름."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import i18n
from app.domain import Cage
from app.i18n import Catalog
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.main import create_app
from app.models import Habitat, MarketItem, User
from app.rules.loader import AquaticRules
from app.services import recommend
from tests.api_helpers import SYRIAN_CAGE, habitat_body, member_settings, signup, use

NANO_TANK = {"width_mm": 600, "depth_mm": 300, "height_mm": 280}  # 60×30×36cm 수조: 물 깊이 280mm
CAVE_PROMPT = "네온 테트라가 숨을 동굴 하나랑 터널 하나 만들어 주세요"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(member_settings(tmp_path))) as c:
        yield c


def aquarium_body(size: str = "nano_fish", count: int = 10, cage: dict = NANO_TANK, **extra) -> dict:
    return {"species": "aquarium", "size": size, "count": count, "cage": cage, **extra}


def species_out(client, key: str, **headers) -> dict:
    return next(s for s in client.get("/species", headers=headers).json()["species"] if s["key"] == key)


# ── /species ─────────────────────────────────────────────


def test_species_lists_habitat_templates_and_count_limits(client, rules):
    species = client.get("/species").json()["species"]
    assert [s["key"] for s in species][0] == "hamster"  # 화면의 기본 종
    ham = species[0]
    assert ham["habitat"] == "cage" and ham["templates"] == ["hideout", "tunnel", "ramp", "sand_bath"]
    assert ham["max_count"] == 10 and ham["print_notes_ko"] == [] and ham["size_hint_ko"] is None
    for s in ham["sizes"]:
        assert s["layout_rules"]["tunnel_max_length_mm"] > 0 and len(s["enclosure_min_floor_mm"]) == 2
        assert s["max_recommended_count"] == 1 and s["count_warning_ko"]
        assert s["min_recommended_count"] is None and s["min_count_warning_ko"] is None and s["aquatic"] is None

    aq = next(s for s in species if s["key"] == "aquarium")
    assert aq["habitat"] == "aquarium" and aq["templates"] == ["cave", "tunnel"] and aq["max_count"] == 200
    assert aq["print_notes_ko"] == list(rules.species_entry("aquarium").print_notes_ko) and len(aq["print_notes_ko"]) >= 5
    assert aq["size_hint_ko"] == rules.species_entry("aquarium").size_hint_ko and "합사 수조" in aq["size_hint_ko"]
    sizes = {s["key"]: s for s in aq["sizes"]}
    assert list(sizes) == ["shrimp", "nano_fish", "small_fish", "community"]
    for s in sizes.values():
        assert s["layout_rules"] is None  # 가상 케이지는 케이지 종만
        assert s["max_recommended_count"] is None and s["count_warning_ko"] is None
        assert set(s["aquatic"]) == set(AquaticRules.model_fields)
    assert sizes["shrimp"]["enclosure_min_floor_mm"] is None
    assert sizes["shrimp"]["min_recommended_count"] == 5 and sizes["shrimp"]["min_count_warning_ko"]
    assert sizes["shrimp"]["aquatic"]["min_volume_l"] == 10 and sizes["shrimp"]["aquatic"]["volume_l_per_animal"] is None
    nano = sizes["nano_fish"]
    assert nano["enclosure_min_floor_mm"] == [600, 300] and nano["min_recommended_count"] == 10
    assert nano["aquatic"]["min_volume_l"] == 54 and nano["aquatic"]["volume_l_per_animal"] == 1.5
    assert nano["aquatic"]["structure_top_clearance_mm"] == 30
    assert nano["aquatic"]["glass_thickness_assumed_mm"] == 6  # 화면도 같은 식으로 겉 크기를 어림한다
    assert sizes["community"]["min_recommended_count"] is None and sizes["community"]["min_count_warning_ko"] is None


def test_species_translates_print_notes_list_in_english(client, rules, monkeypatch):
    """영어 요청이면 _ko 열쇠의 목록(print_notes_ko)도 항목마다 카탈로그로 바꾼다."""
    notes = rules.species_entry("aquarium").print_notes_ko
    entries: dict[str, str] = {}
    for f in sorted(i18n._CATALOG_DIR.glob("*.json")):
        entries.update(json.loads(f.read_text(encoding="utf-8")))
    entries.update({n: f"EN note {i}" for i, n in enumerate(notes)})
    cat = Catalog(entries)
    monkeypatch.setattr(i18n, "catalog", lambda: cat)
    aq = species_out(client, "aquarium", **{"X-Lang": "en"})
    assert aq["print_notes_ko"] == [f"EN note {i}" for i in range(len(notes))]
    assert species_out(client, "aquarium")["print_notes_ko"] == list(notes)  # 한국어 요청은 그대로


def test_species_size_hint_and_print_notes_in_english(client, rules):
    """크기 구분 안내(size_hint_ko)와 출력·설치 안내는 영어 요청이면 실제 카탈로그로 바뀐다 (한국어·'hamster' 없이)."""
    from app.i18n import HANGUL

    aq = species_out(client, "aquarium", **{"X-Lang": "en"})
    assert aq["size_hint_ko"].startswith("Body length means the adult length without the tail fin.")
    assert "'Community tank'" in aq["size_hint_ko"]
    nano = next(s for s in aq["sizes"] if s["key"] == "nano_fish")
    assert nano["display_name"] == "Nano fish (neon and ember tetras, etc.; adult body length 2–3 cm, not counting the tail fin)"
    for text in (aq["size_hint_ko"], *aq["print_notes_ko"]):
        assert not HANGUL.search(text) and "hamster" not in text.lower(), text
    notes = aq["print_notes_ko"]
    assert any("shrimp or snails" in n and n.startswith("Material:") for n in notes)
    assert any("shrimp or snails" in n and n.startswith("Nozzle:") for n in notes)
    assert any(n.startswith("Before adding: first sand") for n in notes)
    assert any(n.startswith("Setting it down:") and "Corydoras" in n for n in notes)
    assert species_out(client, "hamster", **{"X-Lang": "en"})["size_hint_ko"] is None


def test_species_exposes_volume_note_in_both_languages(client, rules):
    """종별 권장 부피 안내(54L 는 하한일 뿐)를 /species 로 알리고, 영어 요청이면 영어로 바꾼다."""
    note = rules.size_rules("aquarium", "small_fish").aquatic.volume_note_ko
    ko = {s["key"]: s for s in species_out(client, "aquarium")["sizes"]}
    assert ko["small_fish"]["aquatic"]["volume_note_ko"] == note
    assert ko["small_fish"]["aquatic"]["volume_note_below_l"] == 100
    assert ko["shrimp"]["aquatic"]["volume_note_ko"] is None
    en = {s["key"]: s for s in species_out(client, "aquarium", **{"X-Lang": "en"})["sizes"]}
    assert en["small_fish"]["aquatic"]["volume_note_ko"].startswith("54 L is only the minimum.")


# ── 사육 환경: 마릿수·종·habitat_kind ─────────────────────────


def test_habitat_count_is_capped_per_species(client):
    signup(client, "user_a")
    r = client.post("/habitats", json=aquarium_body(count=30))
    assert r.status_code == 201, r.text
    got = r.json()
    assert got["habitat_kind"] == "aquarium" and got["count"] == 30 and got["cage"] == {k: float(v) for k, v in NANO_TANK.items()}
    assert client.get(f"/habitats/{got['id']}").json()["habitat_kind"] == "aquarium"
    assert client.post("/habitats", json=aquarium_body(count=200)).status_code == 201
    r = client.post("/habitats", json=aquarium_body(count=201))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "validation_error"

    # 햄스터는 예전처럼 10마리까지 (11 은 같은 422 로 막는다: 이제 스키마 대신 종별 상한이 막는다)
    r = client.post("/habitats", json=habitat_body(count=10))
    assert r.status_code == 201 and r.json()["habitat_kind"] == "cage"
    r = client.post("/habitats", json=habitat_body(count=11))
    assert r.status_code == 422
    assert r.json()["detail"] == {"code": "invalid_input", "message_ko": "햄스터은(는) 최대 10마리까지 입력할 수 있습니다."}
    r = client.post("/habitats", json=habitat_body(count=11), headers={"X-Lang": "en"})
    assert r.json()["detail"]["message_ko"] == "You can enter up to 10 animals for Hamster."
    assert client.post("/habitats", json=habitat_body(count=0)).status_code == 422


def test_species_max_count_comes_from_the_rules_file(tmp_path, rules_copy):
    path = rules_copy / "species.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["species"]["aquarium"]["max_count"] = 50
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with TestClient(create_app(member_settings(tmp_path, rules_dir=rules_copy))) as c:
        signup(c, "user_a")
        assert species_out(c, "aquarium")["max_count"] == 50
        assert c.post("/habitats", json=aquarium_body(count=50)).status_code == 201
        r = c.post("/habitats", json=aquarium_body(count=51))
        assert r.status_code == 422
        assert r.json()["detail"]["message_ko"] == "어항 (담수 관상어·새우)은(는) 최대 50마리까지 입력할 수 있습니다."


def test_habitat_pet_must_be_the_same_species(client):
    signup(client, "user_a")
    ham = client.post("/me/pets", json={"name": "콩이", "species": "hamster", "size": "syrian"}).json()
    fish = client.post("/me/pets", json={"name": "네온이", "species": "aquarium", "size": "nano_fish",
                                         "cage": NANO_TANK}).json()
    assert ham["habitat_kind"] == "cage" and fish["habitat_kind"] == "aquarium"
    assert {p["habitat_kind"] for p in client.get("/me/pets").json()} == {"cage", "aquarium"}
    assert client.get(f"/me/pets/{fish['id']}").json()["habitat_kind"] == "aquarium"

    r = client.post("/habitats", json=aquarium_body(pet_id=ham["id"]))
    assert r.status_code == 422
    assert r.json()["detail"] == {"code": "pet_species_mismatch", "message_ko": "반려동물 정보와 종이 다릅니다."}
    r = client.post("/habitats", json=habitat_body(pet_id=fish["id"]))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "pet_species_mismatch"
    # 같은 종이면 크기가 달라도 된다 (반려동물 정보는 출발점일 뿐)
    r = client.post("/habitats", json=aquarium_body(size="small_fish", pet_id=fish["id"]))
    assert r.status_code == 201 and r.json()["pet_id"] == fish["id"]
    assert client.post("/habitats", json=habitat_body(size="dwarf", pet_id=ham["id"])).status_code == 201


def test_pet_update_to_aquarium_keeps_kind_in_sync(client):
    signup(client, "user_a")
    pet = client.post("/me/pets", json={"name": "콩이", "species": "hamster", "size": "syrian"}).json()
    r = client.put(f"/me/pets/{pet['id']}", json={"name": "새우들", "species": "aquarium", "size": "shrimp"})
    assert r.status_code == 200 and r.json()["habitat_kind"] == "aquarium"
    r = client.put(f"/me/pets/{pet['id']}", json={"name": "새우들", "species": "aquarium", "size": "syrian"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_input"


def test_kind_of_rows_whose_species_left_the_rules_is_cage(client):
    signup(client, "user_a")
    with client.app.state.session_factory() as db:
        uid = db.scalar(select(User.id).where(User.username == "user_a"))
        hab = Habitat(owner_id=uid, species="ghost", size="tiny", count=1,
                      cage_width_mm=600, cage_depth_mm=400, cage_height_mm=300)
        db.add(hab)
        db.commit()
        hid = hab.id
    assert client.get(f"/habitats/{hid}").json()["habitat_kind"] == "cage"
    # 규칙에서 빠진 종의 사육 환경으로는 설계를 만들지 않는다 (예전에는 500). 사용량도 쓰지 않는다
    r = client.post("/designs", json={"habitat_id": hid, "prompt": "은신처"})
    assert r.status_code == 422
    assert r.json()["detail"] == {"code": "invalid_input", "message_ko": "지원하지 않는 종/크기입니다: ghost/tiny"}
    assert client.get("/me").json()["design_quota"]["used"] == 0


# ── 가상 케이지: 케이지 종만 ───────────────────────────────────


def layout_body(**kw) -> dict:
    return {"name": "우리 집 케이지", "species": "hamster", "size": "syrian", "cage": SYRIAN_CAGE, "items": [], **kw}


def test_virtual_cage_rejects_aquarium_species(client):
    signup(client, "user_a")
    expected = {"code": "virtual_cage_unsupported", "message_ko": "가상 케이지는 케이지에서 키우는 동물만 지원합니다."}
    r = client.post("/layouts", json=layout_body(species="aquarium", size="nano_fish"))
    assert r.status_code == 422 and r.json()["detail"] == expected
    assert client.get("/layouts").json() == []

    lay = client.post("/layouts", json=layout_body()).json()
    assert lay["habitat_kind"] == "cage"
    assert client.get("/layouts").json()[0]["habitat_kind"] == "cage"
    r = client.put(f"/layouts/{lay['id']}", json=layout_body(species="aquarium", size="shrimp", name="바꿈"))
    assert r.status_code == 422 and r.json()["detail"] == expected
    got = client.get(f"/layouts/{lay['id']}").json()
    assert (got["species"], got["name"], got["habitat_kind"]) == ("hamster", "우리 집 케이지", "cage")
    # 모르는 종은 예전처럼 invalid_input (종 확인이 먼저)
    r = client.post("/layouts", json=layout_body(species="rabbit"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_input"


def test_copy_layout_rejects_aquarium_snapshot(client):
    """탐색에서 담아 오는 배치도 같은 기준 (어항 종 배치가 DB 에 있어도 내 배치안으로 만들지 않는다)."""
    signup(client, "maker_a")
    with client.app.state.session_factory() as db:
        uid = db.scalar(select(User.id).where(User.username == "maker_a"))
        item = MarketItem(owner_id=uid, title="어항 배치", description="x", category="layout", layout={
            "name": "수조", "species": "aquarium", "size": "nano_fish", "cage": NANO_TANK, "items": []})
        db.add(item)
        db.commit()
        item_id = item.id
    got = client.get(f"/market/items/{item_id}").json()
    assert got["layout"]["habitat_kind"] == "aquarium" and got["layout"]["size_name_ko"]
    use(client, signup(client, "user_b"))
    r = client.post(f"/market/items/{item_id}/copy-layout")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "virtual_cage_unsupported"
    assert client.get("/layouts").json() == []


# ── 모의 해석기로 어항 설계 전체 흐름 ─────────────────────────────


def test_aquarium_design_flow_with_mock(client):
    signup(client, "user_a")
    r = client.post("/habitats", json=aquarium_body())
    hid = r.json()["id"]
    r = client.post("/designs", json={"habitat_id": hid, "prompt": CAVE_PROMPT})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["habitat"]["habitat_kind"] == "aquarium"
    cur = d["current"]
    assert [it["template"] for it in cur["items"]] == ["cave", "tunnel"]
    assert cur["validation"]["passed"] and cur["export_allowed"], cur["validation"]["issues"]
    codes = {i["code"] for i in cur["validation"]["issues"]}
    assert {"underwater_weight", "tunnel_trapped_air"} <= codes
    assert not codes & {"template_not_allowed", "gap_trap_ceiling", "count_below_recommended",
                        "tank_volume_below_recommended", "cage_below_recommended"}
    cave = cur["items"][0]
    assert cave["label_ko"] and cave["placement"] is not None
    assert cave["size_mm"][2] <= NANO_TANK["height_mm"] - 30 + 1e-6  # 구조물 위로 물 깊이 30mm 이상
    assert cave["params"]["entrance_count"] == 2 and cave["params"]["top_opening_mm"] >= 20
    for it in cur["items"]:
        assert it["placement"] is not None
        r = client.get(it["mesh_url"])
        assert r.status_code == 200 and r.headers["content-type"] == "model/stl"

    r = client.get(f"/designs/{d['id']}/export?format=stl")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = z.namelist()
    assert any("cave" in n for n in names) and any("tunnel" in n for n in names)
    r = client.get(f"/designs/{d['id']}/export?format=3mf")
    assert r.status_code == 200 and r.content[:2] == b"PK"

    # 수정: 동굴만 크게 (새 버전, 이전 버전 유지)
    r = client.post(f"/designs/{d['id']}/revise", json={"prompt": "동굴을 더 크게 해 주세요"})
    assert r.status_code == 201, r.text
    d2 = r.json()
    cur2 = d2["current"]
    assert cur2["version"] == 2 and [v["version"] for v in d2["versions"]] == [1, 2]
    assert [it["template"] for it in cur2["items"]] == ["cave", "tunnel"]
    assert cur2["items"][0]["params"]["width_mm"] > cave["params"]["width_mm"]
    assert cur2["items"][1]["params"] == cur["items"][1]["params"]
    assert cur2["validation"]["passed"] and cur2["export_allowed"]
    assert client.get(f"/designs/{d['id']}/export?format=stl&version=2").status_code == 200

    # 내역·공유한 설계에도 사육 환경 종류가 있다
    lst = client.get("/designs").json()["items"]
    assert lst[0]["id"] == d["id"] and lst[0]["habitat"]["habitat_kind"] == "aquarium"
    r = client.post("/community/posts", json={"title": "어항 동굴", "body": "네온 테트라용", "design_id": d["id"]})
    assert r.status_code == 201, r.text
    assert r.json()["design"]["habitat"]["habitat_kind"] == "aquarium"
    use(client, None)
    assert client.get(f"/designs/{d['id']}").json()["habitat"]["habitat_kind"] == "aquarium"


def test_aquarium_design_in_english(client):
    signup(client, "user_a")
    hid = client.post("/habitats", json=aquarium_body(size="small_fish", count=6)).json()["id"]
    r = client.post("/designs", json={"habitat_id": hid, "prompt": "Please make a cave and a tube"},
                    headers={"X-Lang": "en"})
    assert r.status_code == 201, r.text
    cur = r.json()["current"]
    assert [it["template"] for it in cur["items"]] == ["cave", "tunnel"] and cur["validation"]["passed"]
    assert "Underwater cave" in cur["summary_ko"]


def test_recommend_counts_caves_as_hideouts(client):
    signup(client, "user_a")
    hid = client.post("/habitats", json=aquarium_body()).json()["id"]
    assert client.post("/designs", json={"habitat_id": hid, "prompt": "동굴 하나 만들어 주세요"}).status_code == 201
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.username == "user_a"))
        prof = recommend.profile(db, user)
        assert prof["designs"] == {"hideout": 1.0}
        assert recommend.recommend(db, user) == []  # 탐색 작품이 없어도 어항 설계가 있어 깨지지 않는다


def test_recommend_does_not_treat_aquarium_pets_as_cage_pets(client):
    """어항 생물만 등록한 회원에게 햄스터 케이지·가상 케이지 배치를 '반려동물 케이지에 맞는 작품'으로 권하지 않는다."""
    from app.models import Pet

    signup(client, "maker_b")
    fish = signup(client, "fish_owner")
    with client.app.state.session_factory() as db:
        maker = db.scalar(select(User).where(User.username == "maker_b"))
        owner = db.scalar(select(User).where(User.username == "fish_owner"))
        for title, cat in (("햄스터 케이지", "cage"), ("배치 예시", "layout"), ("은신처", "hideout")):
            db.add(MarketItem(owner_id=maker.id, title=title, description="-", category=cat))
        db.add(Pet(owner_id=owner.id, name="네온", species="aquarium", size="nano_fish"))
        db.commit()
        owner_id = owner.id
    cage_reason = "반려동물 케이지에 맞는 작품이에요"
    use(client, fish)
    rec = client.get("/market/recommended").json()
    assert len(rec) == 3 and not [x for x in rec if x["reason_ko"] == cage_reason]
    with client.app.state.session_factory() as db:
        owner = db.get(User, owner_id)
        assert recommend.profile(db, owner, client.app.state.design_service.habitat_kind)["has_pets"] is False
        assert recommend.profile(db, owner)["has_pets"] is True  # 사육 환경을 모르면 예전처럼 모든 반려동물을 센다
        # 케이지 반려동물(햄스터)이 있으면 예전처럼 케이지 작품을 권한다
        db.add(Pet(owner_id=owner_id, name="햄찌", species="hamster", size="syrian"))
        db.commit()
    rec = client.get("/market/recommended").json()
    assert {x["title"] for x in rec if x["reason_ko"] == cage_reason} == {"햄스터 케이지", "배치 예시"}


# ── 모의 해석기: 어항 키워드 ─────────────────────────────────


def mock_items(rules, prompt: str, species: str = "aquarium", size: str = "nano_fish", count: int = 10,
               language: str = "ko") -> tuple[list[str], list[str]]:
    entry = rules.species_entry(species)
    req = InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo(species, entry.display_name, size, count, Cage(600, 300, 280), habitat=entry.habitat),
        size_rules=rules.size_rules(species, size), min_wall_mm=rules.min_wall_for(species, size),
        language=language, allowed_templates=entry.allowed_templates,
    )
    spec = MockInterpreter().interpret(req).spec
    return [it.template for it in spec.items], list(spec.notes_ko)


def test_mock_reads_aquarium_keywords(rules):
    assert mock_items(rules, CAVE_PROMPT) == (["cave", "tunnel"], [])
    assert mock_items(rules, "동굴 하나 만들어 주세요")[0] == ["cave"]  # '동굴'의 '굴'을 터널로 읽지 않는다
    assert mock_items(rules, "모래 바닥 위에 둘 은신처")[0] == ["cave"]  # 어항의 모래는 바닥재
    assert mock_items(rules, "새우가 지나갈 파이프")[0] == ["tunnel"]
    assert mock_items(rules, "a hiding place and a pipe", language="en")[0] == ["cave", "tunnel"]
    items, notes = mock_items(rules, "예쁘게 만들어 주세요")
    assert items == ["cave"] and notes == ["구체적인 구조물 언급이 없어 기본 물속 동굴 1개로 설계했습니다."]
    items, notes = mock_items(rules, "동굴이랑 계단, 모래목욕통도")
    assert items == ["cave"]
    assert notes == ["어항 (담수 관상어·새우)에는 만들 수 없는 구조물이라 제외했습니다: 램프/계단, 모래목욕통"]
    # 햄스터는 예전과 같다 ('동굴'은 터널, '모래'는 모래목욕통)
    assert mock_items(rules, "동굴이랑 모래", "hamster", "syrian", 1) == (["tunnel", "sand_bath"], [])
    assert mock_items(rules, "예쁘게", "hamster", "syrian", 1)[0] == ["hideout"]
