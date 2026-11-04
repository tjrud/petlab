"""저장된 설계 버전이 검증 당시와 다른 형상으로 내보내지지 않는지 (배포 사이 템플릿·테셀레이션 변경).

메시 캐시는 인스턴스마다 사라지므로(Vercel /tmp) 새 인스턴스는 저장된 파라미터로 형상을 다시 만든다.
다시 만든 파일이 저장할 때 기록한 해시와 같으면 그대로 쓰고, 다르면(또는 해시가 없는 옛 버전이면)
내보내기 전에 다시 검증한다. 다시 검증을 통과하지 못하면 뷰어·내려받기 모두 409 로 막는다.
"""

from __future__ import annotations

import copy
import hashlib
import io
import shutil
import zipfile

import pytest
import yaml
from build123d import Align, Box
from fastapi.testclient import TestClient

import app.services.design_service as design_service
from app.geometry.fingerprint import geometry_fingerprint
from app.main import create_app
from app.models import DesignVersion, Habitat
from app.services.engine import EngineResult
from app.templates.base import ParamConstraint
from app.templates.hideout import HideoutTemplate
from app.templates.tunnel import TunnelTemplate
from tests.api_helpers import create_habitat
from tests.api_helpers import make_settings as settings

CAGE = {"width_mm": 900, "depth_mm": 500, "height_mm": 300}


def make_design(c: TestClient, prompt: str = "은신처") -> dict:
    hid = create_habitat(c, CAGE)
    r = c.post("/designs", json={"habitat_id": hid, "prompt": prompt})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["current"]["validation"]["passed"], d["current"]["validation"]
    return d


def export(c: TestClient, d: dict, fmt: str = "stl"):
    return c.get(f"/designs/{d['id']}/export?format={fmt}")


def exported_parts(r) -> dict[str, bytes]:
    """STL 내보내기 응답의 파트별 파일 (구조물 하나면 .stl, 여럿이면 zip).
    zip 은 시각을, 3MF 는 무작위 UUID 를 담으므로 묶음 자체가 아니라 파트 파일끼리 비교한다."""
    assert r.status_code == 200, r.text
    if r.content[:2] != b"PK":
        return {"part": r.content}
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def version_row(c: TestClient) -> DesignVersion:
    with c.app.state.session_factory() as db:
        return db.query(DesignVersion).one()


def version_dir(tmp_path, d: dict, version: int = 1):
    return tmp_path / "meshes" / d["id"] / f"v{version}"


def cached_files(tmp_path, d: dict) -> dict[str, bytes]:
    vd = version_dir(tmp_path, d)
    return {p.name: p.read_bytes() for p in sorted(vd.glob("*.stl"))} if vd.is_dir() else {}


def wipe_cache(tmp_path) -> None:
    """새 인스턴스(콜드 스타트)처럼 메시 캐시를 비운다."""
    shutil.rmtree(tmp_path / "meshes", ignore_errors=True)


@pytest.fixture
def revalidations(monkeypatch) -> list[int]:
    """다시 검증한 횟수를 센다 (실제 검증은 그대로 실행)."""
    calls: list[int] = []
    original = design_service.revalidate

    def spy(items, ctx):
        calls.append(len(items))
        return original(items, ctx)

    monkeypatch.setattr(design_service, "revalidate", spy)
    return calls


def thicker_walls(monkeypatch) -> None:
    """배포된 은신처 템플릿이 같은 파라미터로 벽을 0.5mm 더 두껍게 만들도록 바뀐 상황 (여전히 안전)."""
    orig = HideoutTemplate.build
    monkeypatch.setattr(HideoutTemplate, "build",
                        lambda self, p: orig(self, p.model_copy(update={"wall_thickness_mm": p.wall_thickness_mm + 0.5})))


def huge_base(monkeypatch) -> list[int]:
    """배포된 은신처 템플릿이 케이지보다 넓은 받침을 만들도록 잘못 바뀐 상황 (안전 검증 실패). 호출 횟수를 돌려준다."""
    calls: list[int] = []

    def build(self, p):
        calls.append(1)
        return Box(2000, 2000, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))

    monkeypatch.setattr(HideoutTemplate, "build", build)
    return calls


# ── 저장할 때 형상 지문 기록 ─────────────────────────────────


def test_version_records_digest_of_every_cached_file(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c, "은신처와 터널을 넣어 주세요")
        geometry = version_row(c).geometry
        files = cached_files(tmp_path, d)
        assert files and set(geometry["files"]) == set(files)
        assert all(geometry["files"][n] == hashlib.sha256(b).hexdigest() for n, b in files.items())
        templates = {it["template"] for it in d["current"]["items"]}
        assert geometry["fingerprint"] == geometry_fingerprint(templates, c.app.state.rules.printing)
        # 뷰어 메시 URL 에 지금 형상 코드 지문이 붙는다 (배포로 형상이 바뀌면 URL 도 바뀌어 브라우저 캐시가 섞이지 않게)
        for it in d["current"]["items"]:
            assert it["mesh_url"].endswith(f".stl?g={geometry['fingerprint'][:16]}")
            assert c.get(it["mesh_url"]).status_code == 200


def test_version_records_leave_unbuilt_items_out_of_effective_spec(tmp_path):
    """엔진이 만들지 못한 구조물은 저장 기록(items)과 보정 반영 명세(effective_spec)에서 빠지고,
    LLM 명세(llm_spec)는 바뀌지 않는다. 하나도 만들지 못하면 보정 반영 명세는 LLM 명세 그대로다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        hid = create_habitat(c, CAGE)
        svc = c.app.state.design_service
        with c.app.state.session_factory() as db:
            h = db.get(Habitat, hid)
            g = svc._generate(h, "은신처와 터널을 한쪽에 몰아서 넣고 싶어요", None)
        assert len(g.engine.items) >= 2

        llm_spec = g.interpret.spec.model_dump(mode="json")
        original = copy.deepcopy(llm_spec)
        # 첫 구조물을 엔진이 만들지 못한 상황
        kept = EngineResult(items=g.engine.items[1:], report=g.engine.report)
        items, effective = design_service._version_records(llm_spec, kept)

        assert [it["index"] for it in items] == [it.index for it in kept.items]
        assert len(effective["items"]) == len(kept.items)
        for k, built in enumerate(kept.items):
            assert items[k]["hint"] == llm_spec["items"][built.index]["placement"]
            assert items[k]["params"] == effective["items"][k]["params"]
        assert {k: v for k, v in effective.items() if k != "items"} == \
            {k: v for k, v in llm_spec.items() if k != "items"}
        assert llm_spec == original  # 입력 명세는 바꾸지 않는다

        _, effective_empty = design_service._version_records(llm_spec, EngineResult(items=[], report=g.engine.report))
        assert effective_empty == llm_spec


# ── 경로 1: 똑같이 다시 만들어짐 → 다시 검증하지 않음 ──────────


def test_identical_rebuild_is_served_without_revalidation(tmp_path, revalidations):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c, "은신처와 터널, 모래목욕통을 넣어 주세요")
        before_files = cached_files(tmp_path, d)
        before_export = exported_parts(export(c, d))
        wipe_cache(tmp_path)
        assert exported_parts(export(c, d)) == before_export
        assert cached_files(tmp_path, d) == before_files  # 바이트 단위로 같은 파일
        assert export(c, d, "3mf").status_code == 200
        for it in d["current"]["items"]:
            assert c.get(it["mesh_url"]).status_code == 200
        assert revalidations == []


# ── 경로 2: 형상이 바뀜 → 다시 검증 → 통과하면 바뀐 형상으로 내보냄 ──


def test_changed_template_is_revalidated_then_exported(tmp_path, monkeypatch, revalidations):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c)
        before_export = export(c, d).content
        before_files = cached_files(tmp_path, d)
        wipe_cache(tmp_path)
        thicker_walls(monkeypatch)  # 새 배포: 템플릿 build() 가 바뀜

        r = export(c, d)
        assert r.status_code == 200
        assert r.content != before_export  # 형상이 바뀌었고 ...
        assert revalidations == [1]        # ... 내보내기 전에 다시 검증했다
        after_files = cached_files(tmp_path, d)
        assert set(after_files) == set(before_files) and after_files != before_files
        # 캐시가 채워진 뒤에는 다시 검증하지 않고, 뷰어도 다시 검증한 같은 형상을 받는다
        assert export(c, d).content == r.content
        mesh = c.get(d["current"]["items"][0]["mesh_url"])
        assert mesh.status_code == 200 and mesh.content == after_files["world_0.stl"]
        assert revalidations == [1]


def test_changed_template_failing_revalidation_blocks_export_and_viewer(tmp_path, monkeypatch, revalidations):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c)
        wipe_cache(tmp_path)
        builds = huge_base(monkeypatch)

        r = export(c, d)
        assert r.status_code == 409
        body = r.json()["detail"]
        assert body["code"] == "geometry_changed"
        assert "새 버전" in body["message_ko"]
        assert body["errors"] and {"out_of_cage"} <= {e["code"] for e in body["errors"]}
        assert all(e["severity"] == "error" for e in body["errors"])
        # 검증하지 못한 형상은 캐시에 남기지 않는다 (다음 요청이 파일을 찾아 그대로 내보내지 않게)
        assert cached_files(tmp_path, d) == {}
        # 뷰어 메시도 막히고, 같은 인스턴스에서는 형상 생성·검증을 되풀이하지 않는다
        mesh = c.get(d["current"]["items"][0]["mesh_url"])
        assert mesh.status_code == 409 and mesh.json()["detail"]["code"] == "geometry_changed"
        assert export(c, d, "3mf").status_code == 409
        assert len(builds) == 1 and revalidations == [1]
        assert cached_files(tmp_path, d) == {}


def test_tightened_template_constraint_fails_revalidation(tmp_path, monkeypatch):
    """다시 검증은 보정하지 않는다: 지금 템플릿 제약을 벗어난 저장 파라미터는 오류로 막는다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c)
        wipe_cache(tmp_path)
        thicker_walls(monkeypatch)
        orig = HideoutTemplate.constraints
        monkeypatch.setattr(HideoutTemplate, "constraints", lambda self, p, ctx: orig(self, p, ctx) + [
            ParamConstraint("wall_thickness_mm", min=7.5, reason_ko="새 기준: 벽은 7.5mm 이상이어야 합니다.")])
        r = export(c, d)
        assert r.status_code == 409
        errors = r.json()["detail"]["errors"]
        assert [e["code"] for e in errors] == ["param_out_of_range"]
        assert errors[0]["details"]["field"] == "wall_thickness_mm"


# ── 해시가 없는 옛 버전 (이 기능 이전에 저장됨) ────────────────


def _forget_geometry(c: TestClient) -> None:
    with c.app.state.session_factory() as db:
        v = db.query(DesignVersion).one()
        v.geometry = None
        db.commit()


def test_legacy_version_without_digests_is_revalidated(tmp_path, revalidations):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c, "은신처와 터널을 넣어 주세요")
        before_export = exported_parts(export(c, d))
        _forget_geometry(c)
        wipe_cache(tmp_path)
        # 같은 형상인지 확인할 수 없으므로 다시 검증한다 (코드가 같으니 통과하고 같은 파일이 나온다)
        assert exported_parts(export(c, d)) == before_export
        assert revalidations == [len(d["current"]["items"])]
        export(c, d)
        assert len(revalidations) == 1  # 캐시가 채워진 뒤에는 다시 검증하지 않는다


def test_legacy_version_with_unsafe_rebuild_is_blocked(tmp_path, monkeypatch):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c)
        _forget_geometry(c)
        wipe_cache(tmp_path)
        huge_base(monkeypatch)
        r = export(c, d)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "geometry_changed"


# ── 캐시 일부만 남아 있을 때 ────────────────────────────────


def test_partial_cache_with_changed_geometry_is_rewritten_as_one_validated_set(tmp_path, monkeypatch, revalidations):
    """다시 검증한 형상 집합과 응답하는 파일이 섞이지 않는다 (남아 있던 옛 파일도 다시 검증한 형상으로 맞춘다)."""
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c, "은신처와 터널을 넣어 주세요")
        items = {it["template"]: it["index"] for it in d["current"]["items"]}
        assert {"hideout", "tunnel"} <= set(items)
        before = cached_files(tmp_path, d)
        # 은신처 파일만 사라졌고, 은신처·터널 템플릿 모두 바뀐 배포
        vd = version_dir(tmp_path, d)
        for name in (f"print_{items['hideout']}.stl", f"world_{items['hideout']}.stl"):
            (vd / name).unlink()
        thicker_walls(monkeypatch)
        orig = TunnelTemplate.build
        # 터널은 벽을 안쪽으로 0.5mm 두껍게 (바깥 크기는 그대로라 여전히 안전)
        monkeypatch.setattr(TunnelTemplate, "build", lambda self, p: orig(self, p.model_copy(update={
            "wall_thickness_mm": p.wall_thickness_mm + 0.5, "inner_diameter_mm": p.inner_diameter_mm - 1.0})))

        assert export(c, d, "3mf").status_code == 200
        assert revalidations == [len(d["current"]["items"])]  # 구조물 전체를 함께 다시 검증
        after = cached_files(tmp_path, d)
        tunnel_world = f"world_{items['tunnel']}.stl"
        assert after[tunnel_world] != before[tunnel_world]  # 남아 있던 옛 터널 파일도 다시 검증한 형상으로 교체


def test_partial_cache_with_identical_geometry_keeps_validated_files(tmp_path, revalidations):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c, "은신처와 터널을 넣어 주세요")
        before = cached_files(tmp_path, d)
        (version_dir(tmp_path, d) / "print_0.stl").unlink()
        assert export(c, d).status_code == 200
        assert cached_files(tmp_path, d) == before and revalidations == []


# ── 실제 배포 시나리오: printing.yaml 테셀레이션 설정 변경 ──────


def test_tessellation_change_between_deploys_is_revalidated(tmp_path, rules_copy, revalidations):
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c)
        old_url = d["current"]["items"][0]["mesh_url"]
        before_export = export(c, d).content

    printing_path = rules_copy / "printing.yaml"
    printing = yaml.safe_load(printing_path.read_text(encoding="utf-8"))
    printing["tessellation_tolerance_mm"] = 0.1
    printing["tessellation_angular_tolerance_deg"] = 10
    printing_path.write_text(yaml.safe_dump(printing, allow_unicode=True), encoding="utf-8")
    wipe_cache(tmp_path)  # 새 배포 = 새 인스턴스 (같은 DB, 빈 /tmp)

    with TestClient(create_app(settings(tmp_path, rules_dir=rules_copy))) as c:
        got = c.get(f"/designs/{d['id']}").json()
        new_url = got["current"]["items"][0]["mesh_url"]
        assert new_url != old_url  # 브라우저가 옛 형상을 캐시에서 보여주지 않는다
        r = export(c, d)
        assert r.status_code == 200 and r.content != before_export
        assert revalidations == [1]
        assert c.get(new_url).status_code == 200


# ── 지문 ────────────────────────────────────────────────────


def test_geometry_fingerprint_is_stable_and_sensitive(rules):
    p = rules.printing
    fp = geometry_fingerprint(["hideout", "tunnel"], p)
    assert fp == geometry_fingerprint(["tunnel", "hideout", "hideout"], p)
    assert fp != geometry_fingerprint(["hideout"], p)
    assert fp != geometry_fingerprint(["hideout", "tunnel"], p.model_copy(update={"tessellation_tolerance_mm": 0.1}))
    assert geometry_fingerprint(["removed_template"], p)  # 삭제된 템플릿이어도 예외 없이 계산
