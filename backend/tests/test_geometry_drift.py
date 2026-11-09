"""저장된 설계 버전이 검증 당시와 다른 형상으로 내보내지지 않는지 (배포 사이 템플릿·테셀레이션 변경).

메시 캐시는 인스턴스마다 사라지므로(Vercel /tmp) 새 인스턴스는 저장된 파라미터로 형상을 다시 만든다.
다시 만든 파일이 저장할 때 기록한 해시와 같으면 그대로 쓰고, 다르면(또는 해시가 없는 옛 버전이면)
내보내기 전에 다시 검증한다. 다시 검증을 통과하지 못하면 뷰어·내려받기 모두 409 로 막는다.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
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


# ── 기존 템플릿 4종의 형상 바이트 고정 ──────────────────────────
# 조립형 템플릿(house)·다중 파트 출력을 더하면서 공용 코드(계약·엔진·배치)가 바뀌어도 은신처·터널·램프·모래목욕통의
# STL 바이트(사용 자세·출력 자세)는 그대로여야 한다. 값은 이 기능 이전 코드에서 뽑았다 (uv.lock 의 OCP 테셀레이션 기준).
# 템플릿 build() 를 의도적으로 바꾸면 다시 뽑는다. 파라미터는 model_dump() 의 JSON (키 정렬).

GOLDEN_DIGESTS: list[tuple[str, str, str, str]] = [
    ('hideout', '{"depth_mm": 111.0, "entrance_count": 1, "entrance_diameter_mm": 55.0, "height_mm": 90.0, "vent_count": 6, "vent_diameter_mm": 4.0, "wall_thickness_mm": 3.0, "width_mm": 140.0}',
     '66d792fd4fd6826a5597fe8f29dd720361b058842c6ff04b755ea171f5f9dff5',
     'ce78e6f34412219ed649338a0e77340156872ebad8c9a47cbd66c4da4ab09827'),
    ('hideout', '{}',
     '1fa6d920363f23abcceb21c86d6344ef4499b5bbe190c7ec12b54a3d9ba5cd97',
     'e5d91408a36ec83bd4fc260501771fed1ddf9cf9b3d20c657aee03541ca106b5'),
    ('hideout', '{"depth_mm": 150, "entrance_count": 2, "entrance_diameter_mm": 75, "height_mm": 120, "vent_count": 9, "vent_diameter_mm": 5, "width_mm": 200}',
     '1f0ad93486f72fdb59f5ae9f7fba0365093b7b688fa924e21788930cda39ca2b',
     '269c95a558f9da06bec2464fbb99546560946887d3b127288a38a6e8b9e62e14'),
    ('hideout', '{"depth_mm": 131.0, "entrance_count": 1, "entrance_diameter_mm": 75.0, "height_mm": 96.0, "vent_count": 6, "vent_diameter_mm": 4.0, "wall_thickness_mm": 3.0, "width_mm": 140.0}',
     'a76fe4730a2fd111436433af50873722d5bfcd0863019ef9d3a50af3907279d7',
     '657a425d74f8b1429af4611f98b27f128bb4b0e617fc511c3d4d60fe1d625a9b'),
    ('tunnel', '{"bend_angle_deg": 0.0, "inner_diameter_mm": 55.0, "length_mm": 100.0, "path": "arc", "shape": "pointed_arch", "wall_thickness_mm": 3.0}',
     '65cc685abb409f631c7fb21c4de5f2f40bec38e23a8cb1a8207b6f39dbd88987',
     '65cc685abb409f631c7fb21c4de5f2f40bec38e23a8cb1a8207b6f39dbd88987'),
    ('tunnel', '{}',
     '68b370ae49f6a3193c3c237a4cabb2532fe3486083c3307be7b73ead75fbc465',
     '68b370ae49f6a3193c3c237a4cabb2532fe3486083c3307be7b73ead75fbc465'),
    ('tunnel', '{"bend_angle_deg": 90, "inner_diameter_mm": 75, "length_mm": 250, "shape": "house"}',
     'c5cd78f4672bcacb7316ba770d5acdb30bbbda0fe59888a490b8f32c34ddf83d',
     'c5cd78f4672bcacb7316ba770d5acdb30bbbda0fe59888a490b8f32c34ddf83d'),
    ('tunnel', '{"bend_angle_deg": 60, "inner_diameter_mm": 60, "length_mm": 200, "path": "s_curve"}',
     'ddeff5e06996548efd85ba64f62a66117aa9a1b28f93633801ea3da47eda154e',
     'ddeff5e06996548efd85ba64f62a66117aa9a1b28f93633801ea3da47eda154e'),
    ('tunnel', '{"bend_angle_deg": 0.0, "inner_diameter_mm": 75.0, "length_mm": 200.0, "path": "arc", "shape": "pointed_arch", "wall_thickness_mm": 3.0}',
     'ccf92b428e6e51fd1f4abab2687f5f285e878dd1e657b5d3e715c19e3436e456',
     'ccf92b428e6e51fd1f4abab2687f5f285e878dd1e657b5d3e715c19e3436e456'),
    ('ramp', '{"height_mm": 60.0, "slope_deg": 25.0, "steps": 0, "width_mm": 60.0}',
     '2b6784ae898794a0fe39288d26cb00f31994f26ab9870c75bed250e5ad7e10d0',
     '2b6784ae898794a0fe39288d26cb00f31994f26ab9870c75bed250e5ad7e10d0'),
    ('ramp', '{}',
     'd3799811043db24fc50fe3dd38d6e53f3ec839e8a363471ae3ed624d61e5311f',
     'd3799811043db24fc50fe3dd38d6e53f3ec839e8a363471ae3ed624d61e5311f'),
    ('ramp', '{"height_mm": 90, "slope_deg": 35, "steps": 3, "width_mm": 80}',
     '75577e6277840896dbd80242b6e9d385c11a358a8c2dcaca5b91e636ef089fa6',
     '75577e6277840896dbd80242b6e9d385c11a358a8c2dcaca5b91e636ef089fa6'),
    ('ramp', '{"height_mm": 60.0, "slope_deg": 25.0, "steps": 0, "width_mm": 80.0}',
     'd3799811043db24fc50fe3dd38d6e53f3ec839e8a363471ae3ed624d61e5311f',
     'd3799811043db24fc50fe3dd38d6e53f3ec839e8a363471ae3ed624d61e5311f'),
    ('sand_bath', '{"basin_depth_mm": 50.0, "depth_mm": 216.0, "lip_height_mm": 28.0, "wall_thickness_mm": 3.0, "width_mm": 216.0}',
     '12d8570383f9ef03e705080cee5e0e54f37445c02773f8cadb401fd072a9cd32',
     '12d8570383f9ef03e705080cee5e0e54f37445c02773f8cadb401fd072a9cd32'),
    ('sand_bath', '{}',
     'ec596ee2be3d00a1aef51f6d734fe2cd8d0e3fc3d4fcec0342fdaeb3ae218d81',
     'ec596ee2be3d00a1aef51f6d734fe2cd8d0e3fc3d4fcec0342fdaeb3ae218d81'),
    ('sand_bath', '{"basin_depth_mm": 60, "depth_mm": 220, "lip_height_mm": 40, "width_mm": 250}',
     'e3824cf015d465cbfe375cb327b0b9e84237d1379508392a9934905b20e9d2fa',
     'e3824cf015d465cbfe375cb327b0b9e84237d1379508392a9934905b20e9d2fa'),
    ('sand_bath', '{"basin_depth_mm": 60.0, "depth_mm": 216.0, "lip_height_mm": 28.0, "wall_thickness_mm": 3.0, "width_mm": 216.0}',
     'ec71b83ba3e1f716b9af2dec8b6de6b92f601615eea4301ded56542a8d93fb05',
     'ec71b83ba3e1f716b9af2dec8b6de6b92f601615eea4301ded56542a8d93fb05'),
]


# 조립형 집(장식 없음): 장식 영역(PR 2) 이전 코드에서 뽑은 조립 형상·본체·파트별 출력 메시 해시
HOUSE_GOLDEN_DIGESTS: list[tuple[str, str, str, str, dict]] = [
    ('house', '{"depth_mm": 131.0, "doors": {"sides": ["front"], "width_mm": 75.0}, "floor": {"enabled": false, "thickness_mm": 3.0}, "floors": {"climb": "internal_ramp", "count": 1, "exit_side": "back", "level_height_mm": 100.0, "plate_thickness_mm": 3.0, "ramp_width_mm": 80.0, "slope_deg": 30.0}, "height_mm": 110.0, "ports": {"diameter_mm": 75.0, "flange_mm": 3.0, "sides": []}, "roof": {"kind": "flat", "pitch_deg": 50, "tip_deg": 50}, "walls": {"thickness_mm": 3.0}, "width_mm": 160.0, "windows": {"count": 0, "diameter_mm": 4.0}}',
     '31e94ef6925893317ab56b13f2cad87758cd484c69fa2c6ea046773b281c7342',
     'fdad9cc50d9033efc30233c07edd0f0a59680eb6b68fc32e482951651f7f9071',
     {}),
    ('house', '{"depth_mm": 131.0, "doors": {"sides": ["front"], "width_mm": 75.0}, "floor": {"enabled": false, "thickness_mm": 3.0}, "floors": {"climb": "internal_ramp", "count": 1, "exit_side": "back", "level_height_mm": 100.0, "plate_thickness_mm": 3.0, "ramp_width_mm": 80.0, "slope_deg": 30.0}, "height_mm": 190, "ports": {"diameter_mm": 75.0, "flange_mm": 3.0, "sides": []}, "roof": {"kind": "pitched", "pitch_deg": 50, "tip_deg": 50}, "walls": {"thickness_mm": 3.0}, "width_mm": 160.0, "windows": {"count": 0, "diameter_mm": 4.0}}',
     'bba621e32ab2d97b63bc06024298e7a01db9e5c2703d90a05cb68926a640d07c',
     '9fcc6278ccd1389e196d7ace5f9e998f7803d72069d10eb29f1a85b1044b76e3',
     {"body": "9fcc6278ccd1389e196d7ace5f9e998f7803d72069d10eb29f1a85b1044b76e3", "roof": "e859c6232bad0c9742d59553820318f129953f1347623fa3651498165368069f"}),
    ('house', '{"depth_mm": 131.0, "doors": {"sides": ["front"], "width_mm": 75.0}, "floor": {"enabled": false, "thickness_mm": 3.0}, "floors": {"climb": "external_ramp", "count": 2, "exit_side": "back", "level_height_mm": 110, "plate_thickness_mm": 3.0, "ramp_width_mm": 80.0, "slope_deg": 30.0}, "height_mm": 220, "ports": {"diameter_mm": 75.0, "flange_mm": 3.0, "sides": []}, "roof": {"kind": "flat", "pitch_deg": 50, "tip_deg": 50}, "walls": {"thickness_mm": 3.0}, "width_mm": 160.0, "windows": {"count": 0, "diameter_mm": 4.0}}',
     '9ace91a77f04b07ad0ebaae5caff93ed2321d1c40c33141e0f4497f23cc980b7',
     '76aaf3ea1128bc3326924cb4e69b8c981c78737e78a3adcefdf949cc37101644',
     {"body": "76aaf3ea1128bc3326924cb4e69b8c981c78737e78a3adcefdf949cc37101644", "roof": "42f29424c09dc5145c26e27195b7c5527621190f1f7fafbd09401928233ba933", "floor2": "5bcd92c606fb08a0f4a286fd1360fdfe53fcb0cb14164377a55d7baaf4d9385f"}),
]


@pytest.mark.parametrize("key,params_json,mesh_digest,print_digest,part_digests", HOUSE_GOLDEN_DIGESTS,
                         ids=["house-flat", "house-pitched", "house-two-external"])
def test_house_without_decor_bytes_are_unchanged(rules, key, params_json, mesh_digest, print_digest, part_digests):
    from app.domain import PlacementHint
    from app.services.engine import build_item
    from app.templates.registry import get_template

    t = get_template(key)
    it = build_item(0, t, t.Params(**json.loads(params_json)), PlacementHint(), rules.printing)
    assert hashlib.sha256(it.mesh.export(file_type="stl")).hexdigest() == mesh_digest
    assert hashlib.sha256(it.print_mesh.export(file_type="stl")).hexdigest() == print_digest
    assert {p.key: hashlib.sha256(p.print_mesh.export(file_type="stl")).hexdigest() for p in it.parts} == part_digests


@pytest.mark.parametrize("key,params_json,mesh_digest,print_digest", GOLDEN_DIGESTS,
                         ids=[f"{k}-{i}" for i, (k, *_) in enumerate(GOLDEN_DIGESTS)])
def test_existing_template_bytes_are_unchanged(rules, key, params_json, mesh_digest, print_digest):
    from app.domain import PlacementHint
    from app.services.engine import build_item
    from app.templates.registry import get_template

    t = get_template(key)
    it = build_item(0, t, t.Params(**json.loads(params_json)), PlacementHint(), rules.printing)
    assert hashlib.sha256(it.mesh.export(file_type="stl")).hexdigest() == mesh_digest
    assert hashlib.sha256(it.print_mesh.export(file_type="stl")).hexdigest() == print_digest
    assert it.parts == []  # 파트가 하나뿐인 템플릿은 본체 하나 (출력 파일 이름·내용도 그대로)
    assert [p.key for p in it.print_parts] == ["body"]


# ── 지문 ────────────────────────────────────────────────────


def test_geometry_fingerprint_is_stable_and_sensitive(rules):
    p = rules.printing
    fp = geometry_fingerprint(["hideout", "tunnel"], p)
    assert fp == geometry_fingerprint(["tunnel", "hideout", "hideout"], p)
    assert fp != geometry_fingerprint(["hideout"], p)
    assert fp != geometry_fingerprint(["hideout", "tunnel"], p.model_copy(update={"tessellation_tolerance_mm": 0.1}))
    assert geometry_fingerprint(["removed_template"], p)  # 삭제된 템플릿이어도 예외 없이 계산


def test_fingerprint_covers_house_parts_modules():
    """조립형 템플릿의 부품 라이브러리가 바뀌면 지문도 바뀌어야 한다 (SHARED_MODULES 에 포함)."""
    from app.geometry.fingerprint import SHARED_MODULES, _module_digest

    parts = [m for m in SHARED_MODULES if m.startswith("app.templates.parts.")]
    assert {"app.templates.parts.common", "app.templates.parts.shell", "app.templates.parts.openings",
            "app.templates.parts.levels"} <= set(parts)
    assert all(not _module_digest(m).startswith("unreadable") for m in SHARED_MODULES)


def test_house_version_caches_every_part_and_exports_them(tmp_path):
    """다중 파트 구조물: 버전 캐시에 파트별 출력 메시가 있고 해시가 기록되며, STL zip 에 파트별 파일이 들어간다.
    캐시를 비워도 같은 바이트로 다시 만들어진다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c, "2층 집을 만들어 주세요")  # 평 지붕 2층: 지붕 뚜껑·층판이 따로
        [it] = d["current"]["items"]
        assert it["template"] == "house"
        assert [p["key"] for p in it["parts"]] == ["body", "roof", "floor2"]
        files = cached_files(tmp_path, d)
        assert {"print_0.stl", "print_0_roof.stl", "print_0_floor2.stl", "world_0.stl"} == set(files)
        assert set(version_row(c).geometry["files"]) == set(files)
        parts = exported_parts(export(c, d))
        assert sorted(parts) == ["part1_house_body.stl", "part1_house_floor2.stl", "part1_house_roof.stl"]
        wipe_cache(tmp_path)
        assert exported_parts(export(c, d)) == parts
        assert cached_files(tmp_path, d) == files
        assert export(c, d, "3mf").status_code == 200


def test_decor_is_stored_and_reapplied_on_regeneration(tmp_path, revalidations):
    """장식 명세가 버전에 저장되고, 캐시를 비워 다시 만들어도 같은 바이트(다시 검증 없이)로 나온다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        d = make_design(c, "은신처 왼쪽에 'Mochi-01'이라고 새겨 주세요")
        [it] = d["current"]["items"]
        assert it["decor"] == {"kind": "text", "text": "Mochi-01", "face": "left", "height_mm": 15, "depth_mm": 0.6}
        assert it["params"]["wall_thickness_mm"] == pytest.approx(3.6)  # 각인 깊이만큼 두꺼워짐
        row = version_row(c)
        assert row.items[0]["decor"] == it["decor"] and row.effective_spec["items"][0]["decor"] == it["decor"]
        before = cached_files(tmp_path, d)
        wipe_cache(tmp_path)
        assert export(c, d).status_code == 200
        assert cached_files(tmp_path, d) == before and revalidations == []
