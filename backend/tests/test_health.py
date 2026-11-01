from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_ok():
    settings = Settings(llm_provider="mock", _env_file=None)
    with TestClient(create_app(settings)) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"
    assert body["rules"]["species_reviewed"] is False
