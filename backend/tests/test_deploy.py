"""배포 환경(Vercel Services + 컨테이너 + Postgres) 관련 동작 테스트."""

from __future__ import annotations

import io
import shutil
from concurrent.futures import ThreadPoolExecutor

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import make_engine, normalize_database_url
from app.main import create_app

CAGE = {"width_mm": 900, "depth_mm": 500, "height_mm": 300}


def settings(tmp_path, **kw) -> Settings:
    base = dict(llm_provider="mock", database_url=f"sqlite:///{tmp_path / 'test.db'}",
                mesh_cache_dir=tmp_path / "meshes", _env_file=None)
    base.update(kw)
    return Settings(**base)


# ── API 경로 접두사 (/api) ──────────────────────────────────


@pytest.mark.parametrize("raw,expected", [("", ""), ("/", ""), ("/api", "/api"), ("api/", "/api"), (" /api/ ", "/api")])
def test_api_prefix_normalization(raw, expected):
    assert Settings(api_prefix=raw, _env_file=None).normalized_api_prefix == expected


def test_routes_are_served_under_api_prefix(tmp_path):
    """Vercel rewrite(/api/(.*) → backend)는 원래 경로를 그대로 넘기므로 백엔드가 /api 아래에서 응답해야 한다."""
    with TestClient(create_app(settings(tmp_path, api_prefix="/api"))) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        assert c.get("/health").status_code == 404
        assert c.get("/api/openapi.json").status_code == 200
        hid = c.post("/api/habitats", json={"species": "hamster", "size": "syrian", "count": 1, "cage": CAGE}).json()["id"]
        d = c.post("/api/designs", json={"habitat_id": hid, "prompt": "은신처를 왼쪽에"}).json()
        mesh_url = d["current"]["items"][0]["mesh_url"]
        # mesh_url 은 API 루트 기준 경로 → 프론트엔드가 API_BASE("/api")를 붙여 요청한다
        assert mesh_url.startswith("/designs/")
        assert c.get("/api" + mesh_url).status_code == 200
        assert c.get(f"/api/designs/{d['id']}/export?format=stl").status_code == 200


# ── Postgres 연결 URL ───────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("postgres://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
    ("postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
    ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("sqlite:////tmp/kkomul.db", "sqlite:////tmp/kkomul.db"),
])
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected


def test_postgres_engine_uses_psycopg_with_pre_ping():
    # 엔진 생성은 연결하지 않는다 (드라이버·풀 설정만 확인)
    engine = make_engine("postgres://u:p@localhost:5432/db?sslmode=require")
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"
    assert engine.pool._pre_ping is True
    engine.dispose()


# ── 메시 캐시 동시 재생성 (컨테이너 콜드 스타트) ─────────────


def test_concurrent_mesh_requests_after_cache_wipe(tmp_path):
    """캐시가 빈 상태(새 인스턴스)에서 같은 버전 메시를 동시에 요청해도 잘리거나 빈 파일을 응답하지 않는다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        hid = c.post("/habitats", json={"species": "hamster", "size": "syrian", "count": 1, "cage": CAGE}).json()["id"]
        d = c.post("/designs", json={"habitat_id": hid, "prompt": "은신처와 터널, 모래목욕통을 넣어 주세요"}).json()
        items = [i for i in d["current"]["items"] if i["mesh_url"]]
        assert len(items) >= 2
        reference = {i["index"]: c.get(i["mesh_url"]).content for i in items}

        bad = []
        for _ in range(6):
            shutil.rmtree(tmp_path / "meshes", ignore_errors=True)
            with ThreadPoolExecutor(8) as ex:
                results = list(ex.map(lambda it: (it["index"], c.get(it["mesh_url"])), items * 4))
            for idx, r in results:
                if r.status_code != 200 or r.content != reference[idx]:
                    bad.append((idx, r.status_code, len(r.content), len(reference[idx])))
        assert bad == []
        # 내려받기도 정상
        m = trimesh.load(io.BytesIO(c.get(f"/designs/{d['id']}/export?format=3mf").content), file_type="3mf")
        assert all(g.is_watertight for g in m.geometry.values())
        # 임시 파일이 남지 않는다
        leftovers = list((tmp_path / "meshes").rglob("*.tmp"))
        assert leftovers == []
