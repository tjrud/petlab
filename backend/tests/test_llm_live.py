"""실제 Anthropic API 호출 테스트. 기본 실행에서는 제외된다.

실행: ANTHROPIC_API_KEY, ANTHROPIC_MODEL 설정 후 `uv run pytest -m live`
요청은 서비스(DesignService._generate)처럼 종의 사육 환경과 만들 수 있는 구조물(규칙 파일 templates)을 함께 보낸다.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.domain import Cage
from app.llm.anthropic_client import AnthropicInterpreter
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.spec import to_item_specs
from app.services.engine import EngineContext, run_engine
from app.validation.report import Severity

pytestmark = pytest.mark.live


def _interpreter() -> AnthropicInterpreter:
    s = Settings()
    if not (s.anthropic_api_key and s.anthropic_model):
        pytest.skip("ANTHROPIC_API_KEY / ANTHROPIC_MODEL 미설정")
    return AnthropicInterpreter.from_settings(
        s.anthropic_api_key.get_secret_value(), s.anthropic_model, s.llm_max_retries, s.llm_timeout_s
    )


def _request(rules, prompt: str, species: str, size: str, count: int, cage: Cage) -> InterpretRequest:
    entry = rules.species_entry(species)
    return InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo(species, entry.display_name, size, count, cage, habitat=entry.habitat),
        size_rules=rules.size_rules(species, size),
        min_wall_mm=rules.min_wall_for(species, size),
        allowed_templates=entry.allowed_templates,
    )


def test_live_interpretation(rules):
    interp = _interpreter()
    cage = Cage(600, 400, 300)
    req = _request(rules, "은신처를 한쪽에 몰아서 넣고 싶어요. 환기구는 넉넉하게요.", "hamster", "syrian", 1, cage)
    assert "cave" not in req.allowed_templates  # 서비스처럼 케이지 종에는 물속 동굴을 보내지 않는다
    res = interp.interpret(req)
    assert res.spec.items and res.spec.items[0].template == "hideout"
    out = run_engine(to_item_specs(res.spec), EngineContext(cage, "hamster", "syrian", 1, rules))
    assert all(it.placement is not None for it in out.items)


def test_live_aquarium_interpretation(rules):
    interp = _interpreter()
    cage = Cage(600, 300, 280)  # 60×30×36cm 수조의 물 깊이
    req = _request(rules, "네온 테트라 무리가 숨을 동굴 하나를 만들어 주세요.", "aquarium", "nano_fish", 10, cage)
    res = interp.interpret(req)
    assert res.spec.items
    assert {it.template for it in res.spec.items} <= {"cave", "tunnel"}
    out = run_engine(to_item_specs(res.spec), EngineContext(cage, "aquarium", "nano_fish", 10, rules))
    assert all(it.placement is not None for it in out.items)
    assert not [i for i in out.report.issues if i.code == "template_not_allowed"]
    assert not [i for i in out.report.issues if i.severity == Severity.error], out.report.errors
