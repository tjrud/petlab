from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.config import REPO_DIR
from app.rules.loader import RuleBook, load_rules

RULES_DIR = REPO_DIR / "rules"


@pytest.fixture(scope="session")
def rules() -> RuleBook:
    return load_rules(RULES_DIR)


@pytest.fixture
def rules_copy(tmp_path: Path) -> Path:
    """규칙 파일을 임시 디렉터리로 복사 (파일 교체 시나리오 테스트용)."""
    dst = tmp_path / "rules"
    shutil.copytree(RULES_DIR, dst)
    return dst
