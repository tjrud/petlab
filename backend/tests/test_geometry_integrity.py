"""저장된 설계 버전이 검증 당시와 다른 형상으로 내보내지지 않는지 (형상 지문·메시 요약값·재검증).

배포 환경(Vercel 컨테이너)은 /tmp 메시 캐시가 인스턴스마다 비어 있어, 메시를 *현재 배포된* 코드로 다시 만든다.
여기서는 같은 DB 를 쓰는 새 앱 인스턴스 + 비운 메시 캐시 + 템플릿·규칙 변경으로 재배포를 흉내 낸다.
"""

from __future__ import annotations

import io
import json
import shutil

import numpy as np
import pytest
import trimesh
import yaml
from build123d import Align, Box
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

import app.geometry.fingerprint as fingerprint_mod
import app.services.design_service as design_service_mod
from app.config import Settings
from app.db import ADDED_COLUMNS, init_db, make_engine
from app.domain import Placement, PlacementHint
from app.geometry.fingerprint import GeometryFingerprinter, mesh_digest
from app.main import create_app
from app.models import DesignVersion
from app.services.engine import EngineContext, build_item, revalidate
from app.templates.hideout import HideoutParams, HideoutTemplate

CAGE = {"width_mm": 600, "depth_mm": 400, "height_mm": 300}


def settings(tmp_path, **kw) -> Settings:
    base = dict(llm_provider="mock", database_url=f"sqlite:///{tmp_path / 'test.db'}",
                mesh_cache_dir=tmp_path / "meshes", _env_file=None)
    base.update(kw)
    return Settings(**base)


def new_design(c: TestClient, prompt: str = "은신처를 왼쪽에 넣고 싶어요") -> dict:
    hid = c.post("/habitats", json={"species": "hamster", "size": "syrian", "count": 1, "cage": CAGE}).json()["id"]
    r = c.post("/designs", json={"habitat_id": hid, "prompt": prompt})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["current"]["validation"]["passed"] and d["current"]["export_allowed"]
    return d


def export_stl(c: TestClient, design_id: str):
    return c.get(f"/designs/{design_id}/export?format=stl")


def wipe_mesh_cache(tmp_path) -> None:
    """새 인스턴스의 빈 /tmp 를 흉내 낸다."""
    shutil.rmtree(tmp_path / "meshes")


@pytest.fixture
def revalidations(monkeypatch):
    """재검증 호출 기록 (실제 재검증은 그대로 수행)."""
    calls = []

    def spy(items, ctx, *a, **kw):
        report = revalidate(items, ctx, *a, **kw)
        calls.append(report)
        return report

    monkeypatch.setattr(design_service_mod, "revalidate", spy)
    return calls


@pytest.fixture
def builds(monkeypatch):
    """메시 재생성(build_item) 호출 횟수."""
    calls = []
    original = design_service_mod.build_item

    def spy(*a, **kw):
        calls.append(a[0])
        return original(*a, **kw)

    monkeypatch.setattr(design_service_mod, "build_item", spy)
    return calls


def patch_hideout_build(monkeypatch, make):
    """템플릿 build() 가 바뀐 코드가 배포된 상황. make(original_build, self, params) → Part."""
    original = HideoutTemplate.build
    monkeypatch.setattr(HideoutTemplate, "build", lambda self, p: make(original, self, p))


# ── 저장 시 기록 ────────────────────────────────────────────


def test_version_records_fingerprint_and_mesh_digests(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = new_design(c)
        svc = c.app.state.design_service
        with c.app.state.session_factory() as db:
            row = db.query(DesignVersion).one()
        assert row.geometry_fingerprint == svc.geometry_fingerprint(row.items)
        assert len(row.geometry_fingerprint) == 64
        assert all(len(it["mesh_sha256"]) == 64 for it in row.items)
        # 저장 직후의 응답과 다시 조회한 응답이 같은 형상 키를 쓴다
        url = d["current"]["items"][0]["mesh_url"]
        assert "?g=" in url
        assert c.get(f"/designs/{d['id']}").json()["current"]["items"][0]["mesh_url"] == url
        manifest = json.loads(next((tmp_path / "meshes").rglob("geometry.json")).read_text())
        assert manifest["identical"] is True and manifest["report"] is None


# ── 같은 형상으로 다시 만들어지는 경우 ─────────────────────────


def test_cold_start_rebuilds_identically_without_revalidation(tmp_path, revalidations, builds):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = new_design(c)
        reference = export_stl(c, d["id"]).content
        wipe_mesh_cache(tmp_path)

        got = c.get(f"/designs/{d['id']}").json()["current"]
        assert got["validation"] == d["current"]["validation"]  # 저장된 보고서 그대로
        assert got["export_allowed"]
        assert got["items"][0]["mesh_url"] == d["current"]["items"][0]["mesh_url"]
        r = export_stl(c, d["id"])
        assert r.status_code == 200 and r.content == reference
        assert revalidations == []
        assert len(builds) == 1  # GET 에서 한 번 만들고, 내려받기는 캐시를 쓴다


def test_pipeline_change_with_identical_geometry_skips_revalidation(tmp_path, monkeypatch, revalidations):
    """지문이 바뀌어도(예: 템플릿 파일의 주석 수정) 다시 만든 메시가 같으면 검증된 형상 그대로다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        d = new_design(c)
        reference = export_stl(c, d["id"]).content
        old_fp = c.app.state.design_service.geometry_fingerprint(d["current"]["items"])

    real_hash = fingerprint_mod.module_source_hash
    monkeypatch.setattr(fingerprint_mod, "module_source_hash",
                        lambda m: "edited" if m == HideoutTemplate.__module__ else real_hash(m))
    with TestClient(create_app(settings(tmp_path))) as c:  # 재배포 (이전 메시 캐시는 남아 있음)
        new_fp = c.app.state.design_service.geometry_fingerprint(d["current"]["items"])
        assert new_fp != old_fp
        got = c.get(f"/designs/{d['id']}").json()["current"]
        assert got["export_allowed"] and got["validation"] == d["current"]["validation"]
        r = export_stl(c, d["id"])
        assert r.status_code == 200 and r.content == reference
    assert revalidations == []
    # 이전 지문의 캐시를 그대로 믿지 않고 새 지문 디렉터리에 다시 만들었다
    version_dir = tmp_path / "meshes" / d["id"] / "v1"
    assert sorted(p.name for p in version_dir.iterdir()) == sorted([old_fp[:16], new_fp[:16]])


# ── 형상이 바뀐 경우: 재검증 ─────────────────────────────────


def test_changed_template_geometry_is_revalidated_before_export(tmp_path, monkeypatch, revalidations, builds):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = new_design(c, prompt="은신처를 왼쪽에, 출입구 50mm")  # 출입구는 시리안 기준 70mm 로 자동 보정됨
        assert any(i["auto_fixed"] for i in d["current"]["validation"]["issues"])
        before = trimesh.load(io.BytesIO(export_stl(c, d["id"]).content), file_type="stl")
        old_url = d["current"]["items"][0]["mesh_url"]

        # 새 배포: 환기구 배치가 바뀐 은신처 템플릿 (여전히 안전 기준을 만족하는 형상)
        patch_hideout_build(monkeypatch, lambda orig, self, p: orig(
            self, p.model_copy(update={"vent_count": 0 if p.vent_count else 4})))
        wipe_mesh_cache(tmp_path)

        got = c.get(f"/designs/{d['id']}").json()["current"]
        assert len(revalidations) == 1 and revalidations[0].passed
        assert got["validation"]["passed"] and got["export_allowed"]
        assert got["validation"]["issues"][0]["code"] == "geometry_revalidated"
        # 파라미터 자동 보정 이력은 유지된다
        assert any(i["auto_fixed"] for i in got["validation"]["issues"])
        new_url = got["items"][0]["mesh_url"]
        assert new_url != old_url  # 브라우저 캐시에 이전 형상이 섞이지 않도록 URL 이 바뀐다
        assert c.get(new_url).status_code == 200

        r = export_stl(c, d["id"])
        assert r.status_code == 200
        after = trimesh.load(io.BytesIO(r.content), file_type="stl")
        assert after.is_watertight
        assert len(after.faces) != len(before.faces)  # 다시 검증한 새 형상이 내보내졌다
        # 재검증·재생성은 인스턴스마다 한 번 (판정이 캐시에 남는다)
        assert len(revalidations) == 1 and len(builds) == 1


def test_changed_template_geometry_failing_validation_blocks_export(tmp_path, monkeypatch, revalidations, builds):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = new_design(c)

        # 새 배포: 은신처가 케이지 천장(300mm)보다 높은 형상을 만드는 잘못된 템플릿
        patch_hideout_build(monkeypatch, lambda orig, self, p: Box(
            p.width_mm, p.depth_mm, 400, align=(Align.CENTER, Align.CENTER, Align.MIN)))
        wipe_mesh_cache(tmp_path)

        got = c.get(f"/designs/{d['id']}").json()["current"]
        assert not got["validation"]["passed"] and not got["export_allowed"]
        first = got["validation"]["issues"][0]
        assert first["code"] == "geometry_changed" and first["severity"] == "error"
        assert "새 버전" in first["message_ko"]
        assert "too_tall" in {i["code"] for i in got["validation"]["issues"]}
        assert got["validation"]["summary"]["errors"] >= 2

        for _ in range(2):  # 판정이 캐시돼 다시 요청해도 같은 결과 (재생성·재검증 반복 없음)
            r = export_stl(c, d["id"])
            assert r.status_code == 409
            body = r.json()["detail"]
            assert body["code"] == "geometry_changed"
            assert "새 버전" in body["message_ko"]
            assert "too_tall" in {e["code"] for e in body["errors"]}
            assert c.get(f"/designs/{d['id']}/export?format=3mf").status_code == 409
        assert len(revalidations) == 1 and len(builds) == 1

        # 뷰어는 지금 형상을 보여 준다 (검증 패널에 문제가 표시됨)
        r = c.get(got["items"][0]["mesh_url"])
        assert r.status_code == 200
        assert trimesh.load(io.BytesIO(r.content), file_type="stl").extents[2] == pytest.approx(400)


def test_changed_tessellation_rules_are_revalidated(tmp_path, rules_copy, revalidations):
    """printing.yaml 의 테셀레이션 설정이 바뀐 배포에서도 저장된 버전은 다시 검증한 뒤 내보낸다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        d = new_design(c)
        before = trimesh.load(io.BytesIO(export_stl(c, d["id"]).content), file_type="stl")

    printing_path = rules_copy / "printing.yaml"
    printing = yaml.safe_load(printing_path.read_text(encoding="utf-8"))
    printing["tessellation_tolerance_mm"] = 0.5
    printing["tessellation_angular_tolerance_deg"] = 20
    printing_path.write_text(yaml.safe_dump(printing), encoding="utf-8")

    with TestClient(create_app(settings(tmp_path, rules_dir=rules_copy))) as c:
        got = c.get(f"/designs/{d['id']}").json()["current"]
        assert len(revalidations) == 1
        assert got["validation"]["issues"][0]["code"] == "geometry_revalidated" and got["export_allowed"]
        r = export_stl(c, d["id"])
        assert r.status_code == 200
        after = trimesh.load(io.BytesIO(r.content), file_type="stl")
        assert len(after.faces) < len(before.faces)  # 더 거친 테셀레이션


def test_failed_version_is_not_revalidated(tmp_path, monkeypatch, revalidations):
    """검증에 실패했던 버전은 원래 내려받을 수 없으므로 재검증하지 않고 저장된 보고서를 보여 준다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        hid = c.post("/habitats", json={"species": "hamster", "size": "syrian", "count": 1,
                                        "cage": {**CAGE, "height_mm": 130}}).json()["id"]
        d = c.post("/designs", json={"habitat_id": hid, "prompt": "은신처"}).json()
        assert not d["current"]["validation"]["passed"]
        patch_hideout_build(monkeypatch, lambda orig, self, p: orig(
            self, p.model_copy(update={"vent_count": 0 if p.vent_count else 4})))
        wipe_mesh_cache(tmp_path)
        got = c.get(f"/designs/{d['id']}").json()["current"]
        assert got["validation"] == d["current"]["validation"] and not got["export_allowed"]
        assert export_stl(c, d["id"]).json()["detail"]["code"] == "validation_failed"
    assert revalidations == []


# ── 이 기능 이전에 저장된 버전 (지문·요약값 없음, 열 없는 DB) ────


def test_legacy_database_is_upgraded_and_old_versions_are_revalidated(tmp_path, revalidations):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = new_design(c)
        reference = export_stl(c, d["id"]).content

    # 이 기능 이전의 DB 로 되돌린다: 열이 없고, items 에 메시 요약값이 없다
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, items FROM design_versions")).all()
        for row_id, items in rows:
            legacy = [{k: v for k, v in it.items() if k != "mesh_sha256"} for it in json.loads(items)]
            conn.execute(text("UPDATE design_versions SET items = :items WHERE id = :id"),
                         {"items": json.dumps(legacy, ensure_ascii=False), "id": row_id})
        conn.execute(text("ALTER TABLE design_versions DROP COLUMN geometry_fingerprint"))
    assert "geometry_fingerprint" not in {c["name"] for c in inspect(engine).get_columns("design_versions")}
    engine.dispose()
    wipe_mesh_cache(tmp_path)

    with TestClient(create_app(settings(tmp_path))) as c:  # 기동 시 열이 추가된다
        with c.app.state.session_factory() as db:
            assert db.query(DesignVersion).one().geometry_fingerprint is None
        got = c.get(f"/designs/{d['id']}").json()["current"]
        # 같은 형상인지 확인할 수 없으므로 현재 규칙으로 다시 검증한다
        assert len(revalidations) == 1 and revalidations[0].passed
        assert got["validation"]["issues"][0]["code"] == "geometry_revalidated" and got["export_allowed"]
        r = export_stl(c, d["id"])
        assert r.status_code == 200 and r.content == reference  # 코드는 그대로라 형상도 같다
        manifest = json.loads(next((tmp_path / "meshes").rglob("geometry.json")).read_text())
        assert manifest["identical"] is None
        # 새로 만드는 버전은 지문을 기록한다
        r = c.post(f"/designs/{d['id']}/revise", json={"prompt": "조금 더 크게 해 주세요"})
        with c.app.state.session_factory() as db:
            assert db.query(DesignVersion).filter_by(version=2).one().geometry_fingerprint


def test_init_db_adds_missing_columns_idempotently(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    init_db(engine)
    with engine.begin() as conn:
        for table, column in ADDED_COLUMNS:
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
    for _ in range(2):
        init_db(engine)
        for table, column in ADDED_COLUMNS:
            assert column in {c["name"] for c in inspect(engine).get_columns(table)}
    engine.dispose()


# ── 메시 URL 캐시 ───────────────────────────────────────────


def test_mesh_cache_header_depends_on_geometry_key(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        url = new_design(c)["current"]["items"][0]["mesh_url"]
        assert c.get(url).headers["cache-control"] == "public, max-age=86400"
        path = url.split("?")[0]
        assert c.get(path).headers["cache-control"] == "no-cache"
        assert c.get(path + "?g=0000000000000000").headers["cache-control"] == "no-cache"


def test_regeneration_failure_is_reported_in_design_response(tmp_path, monkeypatch):
    """메시를 다시 만들 수 없으면 조회는 성공하되 내려받기·뷰어 메시를 막고 이유를 보여 준다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        d = new_design(c)

        def broken(orig, self, p):
            raise RuntimeError("kernel error")

        patch_hideout_build(monkeypatch, broken)
        wipe_mesh_cache(tmp_path)
        r = c.get(f"/designs/{d['id']}")
        assert r.status_code == 200
        got = r.json()["current"]
        assert not got["export_allowed"] and got["items"][0]["mesh_url"] is None
        assert got["validation"]["issues"][-1]["code"] == "mesh_unavailable"
        r = export_stl(c, d["id"])
        assert r.status_code == 409 and r.json()["detail"]["code"] == "mesh_unavailable"


# ── 지문 / 요약값 / 재검증 단위 테스트 ─────────────────────────


def test_fingerprint_covers_templates_and_tessellation(rules):
    fp = GeometryFingerprinter(rules.printing)
    assert fp.for_templates(["hideout", "tunnel"]) == fp.for_templates(["tunnel", "hideout", "hideout"])
    assert fp.for_templates(["hideout"]) != fp.for_templates(["hideout", "tunnel"])
    assert GeometryFingerprinter(rules.printing).for_templates(["hideout"]) == fp.for_templates(["hideout"])

    coarse = rules.printing.model_copy(update={"tessellation_tolerance_mm": 0.1})
    assert GeometryFingerprinter(coarse).for_templates(["hideout"]) != fp.for_templates(["hideout"])

    # 터널 템플릿만 바뀌면 은신처만 쓰는 버전의 지문은 그대로다
    edited = GeometryFingerprinter(rules.printing)
    edited.templates["tunnel"] = "edited"
    assert edited.for_templates(["hideout"]) == fp.for_templates(["hideout"])
    assert edited.for_templates(["tunnel"]) != fp.for_templates(["tunnel"])


def test_mesh_digest_ignores_float_noise_but_not_geometry_changes():
    m = trimesh.creation.box((100, 80, 60))
    noisy = m.copy()
    noisy.vertices = m.vertices + 1e-9
    moved = m.copy()
    moved.apply_translation([0.01, 0, 0])
    assert mesh_digest(m) == mesh_digest(m.copy()) == mesh_digest(noisy)
    assert mesh_digest(m) != mesh_digest(moved)
    assert mesh_digest(m, None) != mesh_digest(m, m)


def _hideout_item(rules, **params):
    t = HideoutTemplate()
    it = build_item(0, t, HideoutParams(**params), PlacementHint(), rules.printing)
    w, d = it.size_xy(0)
    it.placement = Placement(w / 2, 200, 0)  # 왼쪽 벽에 붙임
    return it


def test_revalidate_reports_without_auto_fixing(rules):
    from app.domain import Cage

    ctx = EngineContext(Cage(600, 400, 300), "hamster", "syrian", 1, rules)
    ok = _hideout_item(rules, entrance_diameter_mm=75)
    assert revalidate([ok], ctx).passed

    # 시리안 기준(출입구 ≥ 70mm)을 어기는 저장 파라미터: 보정하지 않고 error 로 남긴다
    bad = _hideout_item(rules, entrance_diameter_mm=50)
    report = revalidate([bad], ctx)
    assert not report.passed
    codes = {i.code for i in report.errors}
    assert "param_out_of_range" in codes and "opening_too_small" in codes
    assert not any(i.auto_fixed for i in report.issues)
    assert bad.params.entrance_diameter_mm == 50
    assert np.isclose(bad.mesh.extents[0], 140)
