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
from tests.api_helpers import create_habitat
from tests.api_helpers import make_settings as settings

CAGE = {"width_mm": 900, "depth_mm": 500, "height_mm": 300}


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
    # Supabase(Vercel Marketplace) 풀러 URL: libpq 가 모르는 supa 파라미터 제거, sslmode 유지
    ("postgres://postgres.abc:pw@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres?sslmode=require&supa=base-pooler.x",
     "postgresql+psycopg://postgres.abc:pw@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres?sslmode=require"),
    ("postgres://u:p@h/db?pgbouncer=true&connect_timeout=10", "postgresql+psycopg://u:p@h/db?connect_timeout=10"),
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
        hid = create_habitat(c, CAGE)
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


# ── LLM 전체 시간 상한 (Vercel Hobby 300초) ─────────────────


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _slow_invalid_client(clock, seconds_per_call):
    """호출마다 시간이 흐르고 스키마 위반 응답을 주는 가짜 클라이언트."""
    import json
    from types import SimpleNamespace

    calls = []

    def create(**kw):
        calls.append(kw)
        clock.t += seconds_per_call
        bad = {"summary_ko": "x", "items": [], "notes_ko": []}
        return SimpleNamespace(stop_reason="end_turn", stop_details=None,
                               content=[SimpleNamespace(type="text", text=json.dumps(bad))])

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def _req(rules):
    from app.domain import Cage
    from app.llm.base import HabitatInfo, InterpretRequest

    return InterpretRequest(
        prompt="은신처", habitat=HabitatInfo("hamster", "햄스터", "syrian", 1, Cage(600, 400, 300)),
        size_rules=rules.size_rules("hamster", "syrian"), min_wall_mm=rules.min_wall_for("hamster", "syrian"),
    )


def test_llm_stops_retrying_at_deadline(rules):
    from app.llm.anthropic_client import AnthropicInterpreter
    from app.llm.base import LLMSchemaError

    clock = _Clock()
    client, calls = _slow_invalid_client(clock, seconds_per_call=100)
    interp = AnthropicInterpreter(client, "m", max_retries=5, timeout_s=60, deadline_s=240, clock=clock)
    with pytest.raises(LLMSchemaError):
        interp.interpret(_req(rules))
    # 0s, 100s, 200s 에 시작 → 남은 시간 40s 에서 세 번째 시도, 300s 시점엔 시작하지 않음
    assert len(calls) == 3
    assert clock.t <= 300
    # SDK 재시도까지 포함해 남은 시간을 넘지 않도록 시도당 타임아웃이 줄어든다
    assert calls[0]["timeout"] == 60
    assert calls[2]["timeout"] == pytest.approx(20)


def test_llm_deadline_already_spent_is_unavailable(rules):
    from app.llm.anthropic_client import AnthropicInterpreter
    from app.llm.base import LLMUnavailableError

    clock = _Clock()
    client, calls = _slow_invalid_client(clock, seconds_per_call=1)
    interp = AnthropicInterpreter(client, "m", deadline_s=10, clock=clock)
    with pytest.raises(LLMUnavailableError):
        interp.interpret(_req(rules))
    assert calls == []


# ── Postgres 가 거부하는 입력은 입력 단계에서 422 / 404 ───────


def test_invalid_inputs_rejected_before_db(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        hid = create_habitat(c, CAGE)
        assert c.post("/designs", json={"habitat_id": hid, "prompt": "은신처\x00"}).status_code == 422
        assert c.post("/designs", json={"habitat_id": "not-an-id", "prompt": "은신처"}).status_code == 422
        d = c.post("/designs", json={"habitat_id": hid, "prompt": "은신처"}).json()
        assert c.get(f"/designs/{d['id']}?version={2**40}").status_code == 422
        assert c.post(f"/designs/{d['id']}/revise", json={"prompt": "더 크게", "base_version": 2**40}).status_code == 422
        assert c.get("/designs/abc%00def").status_code == 404
        assert c.get(f"/designs/{d['id']}/versions/{2**40}/parts/0.stl").status_code == 422
        r = c.post("/waitlist", json={"email": "a@example.com", "design_id": d["id"], "version": 2**40})
        assert r.status_code == 422


# ── 임시 저장소 표시 ────────────────────────────────────────


@pytest.mark.parametrize("url,fs,ephemeral", [
    ("sqlite:////tmp/kkomul.db", True, True),
    ("sqlite:////tmp/kkomul.db", False, False),
    ("sqlite://", False, True),
    ("sqlite:///:memory:", False, True),
    ("sqlite:////home/user/petlab/backend/data/kkomul.db", False, False),
    ("postgres://u:p@h/db", True, False),
])
def test_is_ephemeral_database(url, fs, ephemeral):
    from app.db import is_ephemeral_database

    assert is_ephemeral_database(url, fs) is ephemeral


def test_health_reports_ephemeral_storage(tmp_path):
    s = settings(tmp_path, ephemeral_filesystem=True)
    with TestClient(create_app(s)) as c:
        h = c.get("/health").json()
        assert h["database"] == {"dialect": "sqlite", "persistent": False}
        assert c.get("/species").json()["storage_persistent"] is False
    with TestClient(create_app(settings(tmp_path))) as c:
        assert c.get("/health").json()["database"]["persistent"] is True


# ── 메시 재생성 실패 → 409 ──────────────────────────────────


def test_mesh_regeneration_failure_is_409(tmp_path):
    from app.models import DesignVersion

    with TestClient(create_app(settings(tmp_path))) as c:
        hid = create_habitat(c, CAGE)
        d = c.post("/designs", json={"habitat_id": hid, "prompt": "은신처"}).json()
        # 템플릿이 바뀌어 저장된 파라미터가 더 이상 유효하지 않은 상황을 만든다
        with c.app.state.session_factory() as db:
            v = db.query(DesignVersion).one()
            items = [dict(it, params={**it["params"], "width_mm": -1}) for it in v.items]
            v.items = items
            db.commit()
        shutil.rmtree(tmp_path / "meshes", ignore_errors=True)
        r = c.get(d["current"]["items"][0]["mesh_url"])
        assert r.status_code == 409 and r.json()["detail"]["code"] == "mesh_unavailable"
        assert c.get(f"/designs/{d['id']}/export?format=stl").status_code == 409


def test_postgres_url_env_is_used_when_database_url_missing(monkeypatch):
    """Vercel Marketplace Supabase 연동은 DATABASE_URL 대신 POSTGRES_URL 을 주입한다."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_URL", "postgres://u:p@h:6543/postgres?sslmode=require")
    assert Settings(_env_file=None).database_url.startswith("postgres://u:p@h:6543")
    monkeypatch.setenv("DATABASE_URL", "postgres://neon/db")
    assert Settings(_env_file=None).database_url == "postgres://neon/db"  # DATABASE_URL 이 우선
    assert Settings(database_url="sqlite://", _env_file=None).database_url == "sqlite://"  # 이름으로도 지정 가능


_LIGHT_PATHS_SCRIPT = """
import sys, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from tests.api_helpers import make_settings
from app.main import create_app
HEAVY = ("build123d", "OCP", "anthropic", "trimesh", "sklearn")
with TestClient(create_app(make_settings(Path(tempfile.mkdtemp())))) as c:
    for p in ("/health", "/species", "/market/config", "/market/items", "/market/recommended",
              "/community/posts", "/auth/me", "/me", "/layouts", "/designs"):
        c.get(p)
print("heavy=" + ",".join(h for h in HEAVY if h in sys.modules))
"""


def test_light_requests_do_not_load_the_geometry_kernel_or_llm_sdk():
    """서버 기동과 탐색·커뮤니티·로그인 같은 가벼운 요청(목록)은 형상 커널(build123d/OCP)·trimesh·Anthropic SDK 를
    불러오지 않는다 (콜드 스타트 수 초). 설계 생성·설계 상세(규칙 변경 안내·메시)·내려받기 요청에서는 불러온다"""
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-c", _LIGHT_PATHS_SCRIPT], cwd=backend, capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "heavy=", f"불러온 무거운 모듈: {out.stdout.strip()}"


def test_template_key_map_matches_registry():
    from app.templates.keys import TEMPLATE_MODULES
    from app.templates.registry import all_templates

    assert TEMPLATE_MODULES == {t.key: type(t).__module__ for t in all_templates()}
