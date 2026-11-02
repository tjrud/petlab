"""API 통합 테스트 (모의 해석기 + 임시 SQLite)."""

from __future__ import annotations

import io
import shutil
import zipfile

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.base import LLMSchemaError
from app.main import create_app

SYRIAN_CAGE = {"width_mm": 600, "depth_mm": 400, "height_mm": 300}


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(llm_provider="mock", database_url=f"sqlite:///{tmp_path / 'test.db'}",
                mesh_cache_dir=tmp_path / "meshes", _env_file=None)
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


def habitat(client, cage=SYRIAN_CAGE, size="syrian", count=1) -> str:
    r = client.post("/habitats", json={"species": "hamster", "size": size, "count": count, "cage": cage})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def design(client, prompt="은신처를 왼쪽에 넣고 싶어요", **kw) -> dict:
    r = client.post("/designs", json={"habitat_id": habitat(client, **kw), "prompt": prompt})
    assert r.status_code == 201, r.text
    return r.json()


# ── 메타 / 사육 환경 ────────────────────────────────────────


def test_health_and_species(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["llm_provider"] == "mock" and h["llm_ready"]
    sp = client.get("/species").json()
    assert sp["species"][0]["key"] == "hamster"
    assert {s["key"] for s in sp["species"][0]["sizes"]} == {"dwarf", "syrian"}


def test_habitat_crud_and_validation(client):
    hid = habitat(client)
    got = client.get(f"/habitats/{hid}").json()
    assert got["species_name_ko"] == "햄스터" and got["cage"]["width_mm"] == 600
    r = client.post("/habitats", json={"species": "rabbit", "size": "x", "count": 1, "cage": SYRIAN_CAGE})
    assert r.status_code == 422 and "지원하지 않는" in r.json()["detail"]["message_ko"]
    r = client.post("/habitats", json={"species": "hamster", "size": "syrian", "count": 1,
                                       "cage": {"width_mm": 50, "depth_mm": 400, "height_mm": 300}})
    assert r.status_code == 422
    assert client.get("/habitats/nope").status_code == 404


# ── 설계 생성 / 조회 / 메시 ──────────────────────────────────


def test_create_design_and_fetch_mesh(client):
    d = design(client)
    cur = d["current"]
    assert cur["version"] == 1 and cur["provider"] == "mock"
    assert cur["validation"]["passed"] and cur["export_allowed"]
    item = cur["items"][0]
    assert item["template"] == "hideout" and item["placement"] is not None
    assert item["params"]["entrance_diameter_mm"] >= 70  # 시리안 기준

    r = client.get(item["mesh_url"])
    assert r.status_code == 200 and r.headers["content-type"] == "model/stl"
    m = trimesh.load(io.BytesIO(r.content), file_type="stl")
    lo, hi = m.bounds
    assert lo[0] >= -1e-6 and lo[1] >= -1e-6 and lo[2] >= -1e-6
    assert hi[0] <= 600 + 1e-6 and hi[1] <= 400 + 1e-6 and hi[2] <= 300
    assert lo[0] == pytest.approx(0, abs=1e-6)  # 왼쪽 벽에 붙음

    assert client.get(f"/designs/{d['id']}").json()["current"]["version"] == 1
    assert client.get(f"/designs/{d['id']}?version=9").status_code == 404
    assert client.get("/designs/nope").status_code == 404


def test_revise_keeps_previous_versions(client):
    d = design(client)
    v1_width = d["current"]["items"][0]["params"]["width_mm"]
    r = client.post(f"/designs/{d['id']}/revise", json={"prompt": "조금 더 크게 해 주세요"})
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["current"]["version"] == 2
    assert [v["version"] for v in v2["versions"]] == [1, 2]
    assert v2["current"]["items"][0]["params"]["width_mm"] > v1_width
    # v1 은 그대로 남아 있다
    v1 = client.get(f"/designs/{d['id']}?version=1").json()["current"]
    assert v1["items"][0]["params"]["width_mm"] == v1_width
    # 특정 버전을 기준으로 수정
    r = client.post(f"/designs/{d['id']}/revise", json={"prompt": "더 작게", "base_version": 1})
    v3 = r.json()["current"]
    assert v3["version"] == 3 and v3["items"][0]["params"]["width_mm"] < v1_width


# ── 내보내기 ────────────────────────────────────────────────


def test_export_stl_and_3mf(client):
    d = design(client)
    r = client.get(f"/designs/{d['id']}/export?format=stl")
    assert r.status_code == 200
    assert ".stl" in r.headers["content-disposition"]
    assert trimesh.load(io.BytesIO(r.content), file_type="stl").is_watertight

    r = client.get(f"/designs/{d['id']}/export?format=3mf")
    assert r.status_code == 200 and r.headers["content-type"] == "model/3mf"
    scene = trimesh.load(io.BytesIO(r.content), file_type="3mf")
    assert all(g.is_watertight for g in scene.geometry.values())

    assert client.get(f"/designs/{d['id']}/export?format=obj").status_code == 422


def test_export_multi_part_zip(client):
    d = design(client, prompt="은신처를 왼쪽에", cage={"width_mm": 900, "depth_mm": 500, "height_mm": 300})
    r = client.post(f"/designs/{d['id']}/revise", json={"prompt": "은신처를 하나 더 추가해 주세요"})
    cur = r.json()["current"]
    assert len(cur["items"]) == 2 and cur["validation"]["passed"], cur["validation"]
    r = client.get(f"/designs/{d['id']}/export?format=stl")
    assert r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert sorted(zf.namelist()) == ["part1_hideout.stl", "part2_hideout.stl"]


def test_export_blocked_when_validation_fails(client):
    # 낮은 케이지: 천장 틈 기준(높이 ≤ 130-70=60mm)과 시리안 출입구 기준(높이 ≥ 81mm)이 충돌
    d = design(client, cage={"width_mm": 600, "depth_mm": 400, "height_mm": 130})
    cur = d["current"]
    assert not cur["validation"]["passed"] and not cur["export_allowed"]
    codes = {i["code"] for i in cur["validation"]["issues"]}
    assert "param_conflict" in codes
    r = client.get(f"/designs/{d['id']}/export?format=stl")
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["code"] == "validation_failed" and body["errors"]


def test_export_rebuilds_missing_mesh_cache(client, tmp_path):
    d = design(client)
    shutil.rmtree(tmp_path / "meshes")
    r = client.get(f"/designs/{d['id']}/export?format=stl")
    assert r.status_code == 200
    assert client.get(d["current"]["items"][0]["mesh_url"]).status_code == 200


def test_legacy_hideout_rebuilds_with_single_entrance(client, tmp_path):
    """entrance_count 가 없던 시절 저장된 은신처는 캐시를 다시 만들어도 출입구 1개 형상 그대로여야 한다."""
    from app.models import DesignVersion
    from app.templates.hideout import HideoutParams, HideoutTemplate

    d = design(client)
    it = d["current"]["items"][0]
    with client.app.state.session_factory() as db:
        v = db.query(DesignVersion).filter_by(design_id=d["id"]).one()
        items = [dict(x) for x in v.items]
        stored = dict(items[0]["params"])
        assert stored.pop("entrance_count") == 2
        items[0] = {**items[0], "params": stored}
        v.items = items
        db.commit()
    shutil.rmtree(tmp_path / "meshes")
    r = client.get(it["mesh_url"])
    assert r.status_code == 200
    mesh = trimesh.load(io.BytesIO(r.content), file_type="stl")
    single = HideoutTemplate().build(HideoutParams(**stored, entrance_count=1)).volume
    double = HideoutTemplate().build(HideoutParams(**stored, entrance_count=2)).volume
    assert abs(mesh.volume - single) < abs(mesh.volume - double)
    assert mesh.volume == pytest.approx(single, rel=5e-3)


# ── LLM 오류 안내 ───────────────────────────────────────────


class FailingInterpreter:
    name = "failing"

    def interpret(self, req):
        raise LLMSchemaError("요구사항을 설계로 바꾸는 데 실패했어요. 다시 시도해 주세요.", "test")


def test_llm_failure_returns_user_message_and_saves_nothing(tmp_path):
    with TestClient(create_app(make_settings(tmp_path), interpreter=FailingInterpreter())) as c:
        hid = habitat(c)
        r = c.post("/designs", json={"habitat_id": hid, "prompt": "은신처"})
        assert r.status_code == 422
        assert r.json()["detail"] == {"code": "LLMSchemaError",
                                      "message_ko": "요구사항을 설계로 바꾸는 데 실패했어요. 다시 시도해 주세요."}
        from app.models import Design
        with c.app.state.session_factory() as db:
            assert db.query(Design).count() == 0


def test_llm_misconfiguration_is_reported(tmp_path):
    s = make_settings(tmp_path, llm_provider="anthropic", anthropic_api_key=None)
    with TestClient(create_app(s)) as c:
        assert c.get("/health").json()["llm_ready"] is False
        r = c.post("/designs", json={"habitat_id": habitat(c), "prompt": "은신처"})
        assert r.status_code == 500 and "관리자" in r.json()["detail"]["message_ko"]


# ── 제작·배송 대기 ──────────────────────────────────────────


def test_waitlist(client):
    d = design(client)
    r = client.post("/waitlist", json={"email": "user@example.com", "design_id": d["id"], "version": 1})
    assert r.status_code == 201 and r.json()["ok"]
    assert client.post("/waitlist", json={"email": "not-an-email"}).status_code == 422
    assert client.post("/waitlist", json={"email": "a@example.com", "design_id": "nope"}).status_code == 422
    assert client.post("/waitlist", json={"email": "a@example.com", "design_id": "0" * 32}).status_code == 404
    assert client.post("/waitlist", json={"email": "a@example.com", "design_id": d["id"], "version": 7}).status_code == 404


class FlakyInterpreter:
    """첫 호출은 모의 해석기로 성공, 이후 호출은 실패 (수정 실패 시나리오)."""

    name = "flaky"

    def __init__(self):
        from app.llm.mock import MockInterpreter

        self.inner = MockInterpreter()
        self.calls = 0

    def interpret(self, req):
        self.calls += 1
        if self.calls > 1:
            raise LLMSchemaError("요구사항을 설계로 바꾸는 데 실패했어요. 다시 시도해 주세요.", "test")
        return self.inner.interpret(req)


def test_failed_revision_keeps_existing_versions(tmp_path):
    with TestClient(create_app(make_settings(tmp_path), interpreter=FlakyInterpreter())) as c:
        d = c.post("/designs", json={"habitat_id": habitat(c), "prompt": "은신처"}).json()
        r = c.post(f"/designs/{d['id']}/revise", json={"prompt": "더 크게"})
        assert r.status_code == 422 and "다시 시도" in r.json()["detail"]["message_ko"]
        after = c.get(f"/designs/{d['id']}").json()
        assert [v["version"] for v in after["versions"]] == [1]
        assert after["current"]["items"] == d["current"]["items"]


def test_revision_passes_previous_effective_spec_to_llm(tmp_path):
    """수정 시 LLM 에 '자동 보정이 반영된' 직전 설계가 맥락으로 전달된다."""
    from app.llm.mock import MockInterpreter

    seen = []

    class Spy(MockInterpreter):
        def interpret(self, req):
            seen.append(req.previous)
            return super().interpret(req)

    with TestClient(create_app(make_settings(tmp_path), interpreter=Spy())) as c:
        hid = habitat(c)
        # 시리안 기준 위반 값(출입구 50mm)을 갖게 만든 뒤 수정 요청
        d = c.post("/designs", json={"habitat_id": hid, "prompt": "은신처, 출입구 50mm"}).json()
        fixed = d["current"]["items"][0]["params"]["entrance_diameter_mm"]
        assert fixed == 70  # 자동 보정됨
        c.post(f"/designs/{d['id']}/revise", json={"prompt": "환기구 10개"})
        assert seen[0] is None
        assert seen[1].items[0].params.entrance_diameter_mm == fixed
