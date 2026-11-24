from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

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
    """규칙 파일을 임시 디렉터리로 복사 (파일 교체 시나리오 테스트용).

    종의 templates 에서 라이브러리 부품 키(family@vN)는 뺀다: 이 사본을 쓰는 시험은 대개 임시 라이브러리 폴더
    (index.LIBRARY_DIR monkeypatch)를 쓰고, 그 폴더에 없는 키가 적혀 있으면 규칙을 읽지 못한다. 라이브러리 부품을
    게이팅하는 시험은 키를 직접 더한다. 저장소 규칙의 게이팅은 rules 픽스처와 tests/test_library_published.py 가 본다."""
    dst = tmp_path / "rules"
    shutil.copytree(RULES_DIR, dst)
    species = dst / "species.yaml"
    data = yaml.safe_load(species.read_text(encoding="utf-8"))
    entries = data["species"].values()
    if any("@" in k for e in entries for k in e.get("templates") or ()):
        for e in entries:
            if e.get("templates") is not None:
                e["templates"] = [k for k in e["templates"] if "@" not in k]
        species.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dst
