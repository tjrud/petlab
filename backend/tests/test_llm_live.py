"""실제 Anthropic API 호출 테스트. 기본 실행에서는 제외된다.

실행: ANTHROPIC_API_KEY, ANTHROPIC_MODEL 설정 후 `uv run pytest -m live`
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.domain import Cage
from app.llm.anthropic_client import AnthropicInterpreter
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.spec import to_item_specs
from app.services.engine import EngineContext, run_engine

pytestmark = pytest.mark.live


def test_live_interpretation(rules):
    s = Settings()
    if not (s.anthropic_api_key and s.anthropic_model):
        pytest.skip("ANTHROPIC_API_KEY / ANTHROPIC_MODEL 미설정")
    interp = AnthropicInterpreter.from_settings(
        s.anthropic_api_key.get_secret_value(), s.anthropic_model, s.llm_max_retries, s.llm_timeout_s
    )
    cage = Cage(600, 400, 300)
    req = InterpretRequest(
        prompt="은신처를 한쪽에 몰아서 넣고 싶어요. 환기구는 넉넉하게요.",
        habitat=HabitatInfo("hamster", "햄스터", "syrian", 1, cage),
        size_rules=rules.size_rules("hamster", "syrian"),
        min_wall_mm=rules.min_wall_for("hamster", "syrian"),
    )
    res = interp.interpret(req)
    assert res.spec.items and res.spec.items[0].template == "hideout"
    out = run_engine(to_item_specs(res.spec), EngineContext(cage, "hamster", "syrian", 1, rules))
    assert all(it.placement is not None for it in out.items)
