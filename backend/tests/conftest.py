from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.config import BACKEND_DIR
from app.rules.loader import RuleBook, load_rules

RULES_DIR = BACKEND_DIR / "rules"

# 공용 API 도우미(tests/api_helpers.py)의 assert 도 실패 시 값(예: 422 == 201)을 보여 주게 한다
pytest.register_assert_rewrite("tests.api_helpers")


@pytest.fixture(autouse=True)
def _no_failed_login_delay(monkeypatch):
    """실패 응답 지연만 없애고 시도 횟수 제한은 그대로 검사한다."""
    import app.api.auth as auth_api
    monkeypatch.setattr(auth_api, "FAILED_LOGIN_DELAY_S", 0)


@pytest.fixture(scope="session")
def rules() -> RuleBook:
    return load_rules(RULES_DIR)


@pytest.fixture
def rules_copy(tmp_path: Path) -> Path:
    """규칙 파일을 임시 디렉터리로 복사 (파일 교체 시나리오 테스트용)."""
    dst = tmp_path / "rules"
    shutil.copytree(RULES_DIR, dst)
    return dst
