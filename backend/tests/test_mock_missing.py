"""모의 해석기: 카탈로그에 없는 부품(쳇바퀴·해먹·그네·시소)을 missing_parts 와 안내로 알린다."""

from __future__ import annotations

import pytest

from app.domain import Cage
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MISSING_KEYWORDS, MockInterpreter

CAGE = Cage(600, 400, 300)


@pytest.fixture
def base(rules) -> InterpretRequest:
    return InterpretRequest(
        prompt="", habitat=HabitatInfo("hamster", "햄스터", "syrian", 1, CAGE),
        size_rules=rules.size_rules("hamster", "syrian"), min_wall_mm=rules.min_wall_for("hamster", "syrian"),
        allowed_templates=tuple(rules.allowed_templates("hamster")),
    )


def _mock(base: InterpretRequest, prompt: str, language: str = "ko", previous=None):
    r = InterpretRequest(prompt=prompt, habitat=base.habitat, size_rules=base.size_rules, min_wall_mm=base.min_wall_mm,
                         previous=previous, language=language, allowed_templates=base.allowed_templates)
    return MockInterpreter().interpret(r).spec


def _missing(spec) -> list[tuple[str, str]]:
    return [(m.name_ko, m.purpose_ko) for m in spec.missing_parts]


def test_table_matches_design():
    assert set(MISSING_KEYWORDS) == {"wheel", "hammock", "swing", "seesaw"}
    m = MISSING_KEYWORDS["wheel"]
    assert (m.name_ko, m.purpose_ko, m.purpose_en) == ("쳇바퀴", "달리기 운동", "running exercise")
    assert (MISSING_KEYWORDS["hammock"].name_ko, MISSING_KEYWORDS["hammock"].purpose_ko) == ("해먹", "매달려 쉬기")
    assert MISSING_KEYWORDS["swing"].purpose_en == MISSING_KEYWORDS["seesaw"].purpose_en == "play"


def test_wheel_with_a_hideout_builds_the_hideout_and_lists_the_wheel(base):
    spec = _mock(base, "은신처랑 쳇바퀴 만들어줘")
    assert [it.template for it in spec.items] == ["hideout"]
    assert _missing(spec) == [("쳇바퀴", "달리기 운동")]
    assert "요청하신 쳇바퀴은(는) 아직 부품이 없어 다른 부품으로 만들었어요." in spec.notes_ko


def test_only_a_missing_part_gives_the_default_hideout_and_the_note(base):
    spec = _mock(base, "해먹 만들어 주세요")
    assert [it.template for it in spec.items] == ["hideout"]
    assert _missing(spec) == [("해먹", "매달려 쉬기")]
    assert spec.notes_ko == ["요청하신 해먹은(는) 아직 부품이 없어 다른 부품으로 만들었어요."]


def test_several_missing_parts_keep_their_order(base):
    spec = _mock(base, "시소랑 그네, 그리고 쳇바퀴도 넣어 주세요")
    assert [n for n, _ in _missing(spec)] == ["시소", "그네", "쳇바퀴"]
    assert len([n for n in spec.notes_ko if n.startswith("요청하신")]) == 3


def test_english_request_uses_english_names(base):
    spec = _mock(base, "A hideout and an exercise wheel, please", language="en")
    assert [it.template for it in spec.items] == ["hideout"]
    assert _missing(spec) == [("exercise wheel", "running exercise")]
    assert ("The exercise wheel you asked for isn't available as a part yet, so it was built from other parts."
            in spec.notes_ko)
    assert _missing(_mock(base, "a hammock and a see-saw", language="en")) == [("hammock", "hanging rest"),
                                                                              ("seesaw", "play")]


def test_no_missing_part_keeps_the_empty_list(base):
    spec = _mock(base, "은신처를 왼쪽에")
    assert spec.missing_parts == [] and not any(n.startswith("요청하신") for n in spec.notes_ko)


def test_revision_lists_a_new_missing_part_and_keeps_the_items(base):
    v1 = _mock(base, "은신처를 왼쪽에")
    v2 = _mock(base, "쳇바퀴도 추가해 주세요", previous=v1)
    assert [it.template for it in v2.items] == ["hideout"]
    assert _missing(v2) == [("쳇바퀴", "달리기 운동")]


def test_missing_part_next_to_an_assembly_request(base):
    spec = _mock(base, "은신처 오른쪽에 물병 붙여주고 쳇바퀴도")
    assert spec.items[0].template == "assembly"
    assert _missing(spec) == [("쳇바퀴", "달리기 운동")]


def test_the_note_is_translated_for_english_pages():
    from app.i18n import catalog
    assert catalog().translate("요청하신 쳇바퀴은(는) 아직 부품이 없어 다른 부품으로 만들었어요.") == (
        "The exercise wheel you asked for isn't available as a part yet, so it was built from other parts.")
