"""모의 해석기의 조립 문법: 붙이기·달기·잇기 요청 → 조립 항목(부품 + 연결), 따로 놓는 말 → 일반 항목.

모의 해석기는 실제 LLM 과 같은 계약(parse_spec)으로 내므로 여기서 보는 조립 항목은 조립 해석기(app/modules/compose)에
그대로 들어간다. 결합 방식·연결 지점·맞물리는 치수는 해석기가 정하고, 여기서는 어느 부품을 어느 부품의 어느 면에
붙이는지(connections 의 at)까지만 본다.
"""

from __future__ import annotations

import json
import re

import numpy as np
import pytest
import trimesh

from app.domain import Cage
from app.llm import mock as mock_module
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.llm.spec import parse_spec, to_item_specs
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.registry import get_template
from app.validation.checks import measure_thickness

# 부품 id 앞부분 → 템플릿 (모의 해석기가 붙이는 id: hide, hide2, bowl, bottle, tube, ramp, bath, house)
ID_TEMPLATES = {"hide": "hideout", "bowl": "bowl_holder", "bottle": "bottle_stand", "tube": "tunnel", "ramp": "ramp",
                "bath": "sand_bath", "house": "house"}


def _req(rules, prompt: str, *, language: str = "ko", size: str = "dwarf", previous=None, species: str = "hamster",
         allowed: tuple[str, ...] | None = None) -> InterpretRequest:
    entry = rules.species_entry(species)
    return InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo(species, entry.display_name, size, 1, Cage(800, 500, 400), habitat=entry.habitat),
        size_rules=rules.size_rules(species, size), min_wall_mm=rules.min_wall_for(species, size),
        language=language, allowed_templates=allowed or rules.allowed_templates(species), previous=previous,
    )


def interpret(rules, prompt: str, **kw):
    return MockInterpreter().interpret(_req(rules, prompt, **kw)).spec


def shape(spec) -> list[str]:
    """항목 모양: 일반 항목은 템플릿 키, 조립 항목은 'id id … | 자식>부모.면 …'. 부품 id 와 템플릿이 맞는지도 본다."""
    out = []
    for it in spec.items:
        if it.template != "assembly":
            out.append(it.template)
            continue
        for p in it.parts:
            assert ID_TEMPLATES.get(re.sub(r"\d+$", "", p.id), p.template) == p.template, (p.id, p.template)
        out.append(" ".join(p.id for p in it.parts) + " | "
                   + " ".join(f"{c.part}>{c.to}.{c.at}" for c in it.connections))
    return out


EXAMPLE_KO = "은신처 오른쪽에 밥그릇 받침, 왼쪽에 물병 거치대, 앞에는 터널로 은신처 하나 더 이어줘"
EXAMPLE_SHAPE = "hide bowl bottle tube hide2 | bowl>hide.right bottle>hide.left tube>hide.front hide2>tube.free_end"
EXAMPLE_EN = ("a hideout with a bowl on the right and a water bottle on the left, and connect another hideout through a "
              "tunnel at the front")


def test_module_keywords_are_gone():
    """고정 조립 모듈(세트)의 낱말 표는 없다: 부품을 고르고 잇는 일은 조립 문법이 한다."""
    assert not hasattr(mock_module, "MODULE_KEYWORDS")
    assert not hasattr(mock_module, "_module_keywords")


# ── 설계 문서의 모의 해석기 표 ─────────────────────────────────


def test_example_prompt_gives_five_parts_and_four_joins(rules):
    spec = interpret(rules, EXAMPLE_KO)
    assert shape(spec) == [EXAMPLE_SHAPE]
    it = spec.items[0]
    assert it.placement.zone == "auto"  # 면 낱말은 모두 연결에 쓰여 케이지 위치로 읽지 않는다
    assert it.name_ko.endswith("달린 은신처") and "그릇 받침" in it.name_ko
    assert "그릇 받침 → 은신처 오른쪽" in it.reason_ko
    # 엔진 입력: 조립 요청의 나무 순서(뿌리부터 너비 우선)가 연결 순서와 같다
    item = to_item_specs(spec)[0]
    assert item.template == "assembly" and list(item.params) == ["hide", "bowl", "bottle", "tube", "hide2"]
    assert [(c.part, c.to, c.at) for c in item.assembly.walk()] == [
        ("bowl", "hide", "right"), ("bottle", "hide", "left"), ("tube", "hide", "front"), ("hide2", "tube", "free_end")]
    # '하나 더' 는 같은 값의 은신처
    hide, hide2 = (p.params for p in it.parts if p.template == "hideout")
    assert hide == hide2
    assert spec.missing_parts == []


@pytest.mark.parametrize("prompt,expected", [
    ("밥그릇 달린 은신처", ["hide bowl | bowl>hide.auto"]),
    ("밥그릇이랑 은신처", ["bowl_holder", "hideout"]),                     # 붙인다는 말이 없으면 따로 놓는다
    ("경사로 달린 모래목욕통", ["bath ramp | ramp>bath.front"]),          # 램프는 모래목욕통 출입 면(앞 턱)에
    ("터널로 이은 은신처 두 개", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
])
def test_design_table_ko(rules, prompt, expected):
    assert shape(interpret(rules, prompt)) == expected


def test_zone_and_side_in_one_request(rules):
    """'왼쪽 구석'은 케이지 위치, '은신처 오른쪽'은 은신처의 면. 두 번 말한 은신처는 같은 은신처다."""
    spec = interpret(rules, "왼쪽 구석에 은신처, 은신처 오른쪽에 물병")
    assert shape(spec) == ["hide bottle | bottle>hide.right"]
    assert spec.items[0].placement.zone == "back_left"


@pytest.mark.parametrize("prompt,language,needle", [
    ("은신처 위에 은신처", "ko", "위에 얹기는 아직 지원하지 않아"),
    ("은신처 위에 밥그릇", "ko", "위에 얹기는 아직 지원하지 않아"),
    ("a hideout with a bowl on top", "en", "Stacking on top isn't supported yet"),
])
def test_stacking_on_top_gives_a_note(rules, prompt, language, needle):
    spec = interpret(rules, prompt, language=language)
    assert all(it.template != "assembly" for it in spec.items)
    assert any(needle in n for n in spec.notes_ko), spec.notes_ko


# ── 사용자가 실제로 쓸 만한 한국어 표현 (조사·띄어쓰기·어순) ──────────────


@pytest.mark.parametrize("prompt,expected", [
    # 면 + 조사 (에·에는·엔·에다가·으로·의 … 면)
    ("은신처 오른쪽에 밥그릇 놓아줘", ["hide bowl | bowl>hide.right"]),
    ("은신처 오른편에 밥그릇 받침을 달아 주세요", ["hide bowl | bowl>hide.right"]),
    ("은신처의 오른쪽에 밥그릇을 붙여주세요", ["hide bowl | bowl>hide.right"]),
    ("은신처 오른쪽에다가 그릇 받침 붙여", ["hide bowl | bowl>hide.right"]),
    ("은신처의 왼쪽 면에 물병", ["hide bottle | bottle>hide.left"]),
    ("은신처 우측에 급수기, 좌측에 먹이그릇", ["hide bottle bowl | bottle>hide.right bowl>hide.left"]),
    ("은신처 오른쪽엔 밥그릇, 왼쪽엔 물병 달아줘", ["hide bowl bottle | bowl>hide.right bottle>hide.left"]),
    ("은신처 뒤에 경사로 붙여줘", ["hide ramp | ramp>hide.back"]),
    ("숨숨집 앞에 터널 달아주세요", ["hide tube | tube>hide.front"]),
    ("은신처 앞쪽으로 터널 연결", ["hide tube | tube>hide.front"]),
    ("은신처 뒷면에 터널 연결해줘", ["hide tube | tube>hide.back"]),
    ("모래목욕통 앞에 경사로", ["bath ramp | ramp>bath.front"]),
    # 띄어쓰기
    ("은신처오른쪽에밥그릇달아줘", ["hide bowl | bowl>hide.right"]),
    ("은신처 오른쪽 에 밥그릇", ["hide bowl | bowl>hide.right"]),
    # 어순: 붙일 것을 먼저
    ("물병 거치대를 은신처 왼쪽에 붙여 주세요", ["hide bottle | bottle>hide.left"]),
    ("밥그릇은 은신처 오른쪽에 달아줘", ["hide bowl | bowl>hide.right"]),
    ("밥그릇이 오른쪽에 달린 은신처", ["hide bowl | bowl>hide.right"]),
    # 면 없이 붙이기 (빈 면은 조립 해석기가 고른다)
    ("은신처에 밥그릇 붙여줘", ["hide bowl | bowl>hide.auto"]),
    ("은신처에다 물병 달아줘", ["hide bottle | bottle>hide.auto"]),
    ("은신처 옆에 밥그릇 놓아줘", ["hide bowl | bowl>hide.auto"]),
    ("은신처 옆면에 물병 거치대 달아줘", ["hide bottle | bottle>hide.auto"]),
    ("모래목욕통에 경사로 붙여줘", ["bath ramp | ramp>bath.front"]),
    ("은신처 지붕으로 올라가는 경사로", ["hide ramp | ramp>hide.auto"]),
    # 여럿 나열 (와·과·이랑·쉼표)
    ("밥그릇과 물병 달린 은신처", ["hide bowl bottle | bowl>hide.auto bottle>hide.auto"]),
    ("물병이랑 밥그릇 붙은 은신처", ["hide bottle bowl | bottle>hide.auto bowl>hide.auto"]),
    ("밥그릇, 물병 달린 은신처", ["hide bowl bottle | bowl>hide.auto bottle>hide.auto"]),
    ("밥그릇이랑 큰 물병 달린 은신처", ["hide bowl bottle | bowl>hide.auto bottle>hide.auto"]),
    ("은신처에 밥그릇이랑 물병 붙여줘", ["hide bowl bottle | bowl>hide.auto bottle>hide.auto"]),
    # 양옆: 나열은 오른쪽·왼쪽 순, 하나면 같은 받침 둘
    ("은신처 양옆에 밥그릇이랑 물병", ["hide bowl bottle | bowl>hide.right bottle>hide.left"]),
    ("은신처 양쪽에 그릇 받침", ["hide bowl bowl2 | bowl>hide.right bowl2>hide.left"]),
    # 터널로 잇기 (P4·P5·P6, 터널 끝)
    ("은신처랑 은신처를 터널로 이어줘", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("은신처 두 개를 터널로 연결해 주세요", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("은신처 2개를 터널로 이어주세요", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("쌍둥이 은신처를 터널로 이어줘", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("터널로 연결된 은신처 두 채", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("은신처 앞에 터널 연결하고 그 끝에 은신처 하나 더", ["hide tube hide2 | tube>hide.front hide2>tube.free_end"]),
    ("은신처 앞에 터널, 터널 끝에 은신처 하나 더", ["hide tube hide2 | tube>hide.front hide2>tube.free_end"]),
    ("터널 달린 은신처", ["hide tube | tube>hide.auto"]),
    ("집 모양 터널 달린 은신처", ["hide tube | tube>hide.auto"]),  # '집 모양'은 터널 단면이지 은신처가 아니다
    # 방을 방에 바로: 조립 해석기가 터널을 끼운다
    ("은신처 앞에 은신처 하나 더 붙여줘", ["hide hide2 | hide2>hide.front"]),
    # 절 나누기: 붙이고·달고 … 뒤 절은 앞 절의 기준 구조물에
    ("은신처 앞에 터널 달고 오른쪽엔 밥그릇 달아줘", ["hide tube bowl | tube>hide.front bowl>hide.right"]),
    # '…달린 은신처' 둘은 서로 다른 은신처
    ("터널 달린 은신처와 밥그릇과 물병이 달린 은신처",
     ["hide tube | tube>hide.auto", "hide2 bowl bottle | bowl>hide2.auto bottle>hide2.auto"]),
    ("물병 달린 은신처랑 터널 달린 은신처", ["hide bottle | bottle>hide.auto", "hide2 tube | tube>hide2.auto"]),
    # 옛 세트 낱말 목록에서 온 말투: 띄어 쓰기만 한 나열, '…과 연결된', 동사 줄기, 수를 앞에
    ("그릇 물병 달린 숨숨집", ["hide bowl bottle | bowl>hide.auto bottle>hide.auto"]),
    ("터널과 연결된 은신처", ["hide tube | tube>hide.auto"]),
    ("경사로를 모래목욕통에 달아", ["bath ramp | ramp>bath.front"]),
    ("두 개의 은신처를 터널로", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("은신처 두 개가 터널로", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    # 2층 집에도 붙인다 ('집'은 2층 집)
    ("2층 집에 물병 거치대 붙여 주세요", ["house bottle | bottle>house.auto"]),
    # '…달린 A' 와 'A SIDE에 …' 가 기준 부품 낱말 하나를 함께 쓰면 둘 다 그 부품에 붙인다
    ("경사로 달린 모래목욕통 앞에 밥그릇 받침도 달아줘", ["bath ramp bowl | ramp>bath.front bowl>bath.front"]),
    ("밥그릇 달린 은신처 오른쪽에 물병 거치대", ["hide bowl bottle | bowl>hide.auto bottle>hide.right"]),
    ("물병 달린 은신처 앞에 터널로 은신처 하나 더 이어줘",
     ["hide bottle tube hide2 | bottle>hide.auto tube>hide.front hide2>tube.free_end"]),
    ("밥그릇 달린 은신처랑 물병 달린 은신처", ["hide bowl | bowl>hide.auto", "hide2 bottle | bottle>hide2.auto"]),
])
def test_korean_phrasings(rules, prompt, expected):
    assert shape(interpret(rules, prompt)) == expected


@pytest.mark.parametrize("prompt,expected,zone", [
    # 케이지 위치 (구석·벽·케이지 …) 와 '을/를' 로 놓을 곳을 말한 면은 부품의 면이 아니다
    ("은신처를 왼쪽에 넣어 주세요", ["hideout"], "left"),
    ("은신처를 왼쪽에, 밥그릇을 오른쪽에 놓아 주세요", ["hideout", "bowl_holder"], "left"),
    ("은신처를 왼쪽에 두고 오른쪽에 밥그릇 놓아줘", ["hideout", "bowl_holder"], "left"),
    ("은신처 왼쪽 구석에 밥그릇", ["hideout", "bowl_holder"], "back_left"),
    ("케이지 왼쪽에 밥그릇 달린 은신처", ["hide bowl | bowl>hide.auto"], "left"),
    ("경사로가 붙은 모래목욕통을 오른쪽 구석에", ["bath ramp | ramp>bath.front"], "back_right"),
    # 예전 그대로: 붙이는 말 없는 나열·몰아 놓기·2층 집 바깥 램프·창문 있는 집·장식 글귀
    ("은신처와 터널을 한쪽에 몰아서 넣고 싶어요", ["hideout", "tunnel"], "left"),
    ("2층 집을 왼쪽에, 바깥 램프로 올라가게 해 주세요", ["house", "ramp"], "left"),
    ("창문 3개 있는 경사 지붕 집", ["house"], "auto"),
    ("은신처 왼쪽에 '뽀송이'라고 새겨 주세요", ["hideout"], "left"),
    ("은신처 두 개", ["hideout"], "auto"),
])
def test_zone_words_and_unjoined_mentions_stay_plain(rules, prompt, expected, zone):
    spec = interpret(rules, prompt)
    assert shape(spec) == expected
    assert spec.items[0].placement.zone == zone


@pytest.mark.parametrize("prompt,expected,needle", [
    ("밥그릇 달린 터널", ["bowl_holder", "tunnel"], "그릇 받침은 터널에 붙일 수 없어"),
    ("터널 끝에 밥그릇", ["tunnel", "bowl_holder"], "그릇 받침은 터널에 붙일 수 없어"),
    ("은신처와 모래목욕통을 터널로 이어줘", ["hideout", "sand_bath", "tunnel"], "터널 끝에는 은신처·집 같은 방만"),
    ("은신처 앞으로 터널을 연결하고 터널 끝에는 모래목욕통", ["hide tube | tube>hide.front", "sand_bath"],
     "모래목욕통은 터널에 붙일 수 없어"),
])
def test_joins_the_standard_cannot_make_stay_separate_with_a_note(rules, prompt, expected, needle):
    """연결 표준으로 안 되는 연결(받침에 붙이기, 터널 끝에 받침·모래목욕통)은 따로 놓고 알린다 (계약 검증을 통과한다)."""
    spec = interpret(rules, prompt)
    assert shape(spec) == expected
    assert any(needle in n for n in spec.notes_ko), spec.notes_ko


def test_parts_per_structure_are_capped(rules):
    """한 조립 항목은 부품 8개까지 (해석기가 끼울 터널 포함): 넘치는 연결은 따로 두고 알린다."""
    spec = interpret(rules, "은신처 양쪽에 밥그릇, 양쪽에 물병, 양쪽에 경사로, 앞에 터널로 은신처 하나 더 이어줘")
    asm = [it for it in spec.items if it.template == "assembly"]
    assert len(asm) == 1 and len(asm[0].parts) <= 8
    assert any("8개까지" in n for n in spec.notes_ko)


# ── 영어 ──────────────────────────────────────────────────


@pytest.mark.parametrize("prompt,expected", [
    (EXAMPLE_EN, [EXAMPLE_SHAPE]),
    ("a hideout with a bowl", ["hide bowl | bowl>hide.auto"]),
    ("hideout with a bowl and a water bottle", ["hide bowl bottle | bowl>hide.auto bottle>hide.auto"]),
    ("a hideout with a small bowl and a big water bottle", ["hide bowl bottle | bowl>hide.auto bottle>hide.auto"]),
    ("a hideout with a water bottle on the left side", ["hide bottle | bottle>hide.left"]),
    ("a bowl on the right side of the hideout", ["hide bowl | bowl>hide.right"]),
    ("attach a bowl to the hideout", ["hide bowl | bowl>hide.auto"]),
    ("put a bowl next to the hideout", ["hide bowl | bowl>hide.auto"]),
    ("a tunnel in front of the hideout", ["hide tube | tube>hide.front"]),
    ("a house with a tunnel attached", ["hide tube | tube>hide.auto"]),
    ("a hideout with a house-shaped tunnel", ["hide tube | tube>hide.auto"]),
    ("a ramp up to the roof of the hideout", ["hide ramp | ramp>hide.auto"]),
    ("a sandbath with a ramp", ["bath ramp | ramp>bath.front"]),
    ("a sand bath with stairs", ["bath ramp | ramp>bath.front"]),
    ("steps into the sand bath", ["bath ramp | ramp>bath.front"]),
    ("Twin hideouts joined by a tunnel", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("two hideouts connected by a tunnel", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("connect two hideouts with a tunnel", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("a hideout with a tunnel, and connect another hideout at the end of the tunnel",
     ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    # 따로 놓는 것
    ("a ramp with a bowl attached", ["ramp", "bowl_holder"]),  # 램프(받침)에는 붙일 수 없다
    ("a hideout, a bowl and a tunnel", ["hideout", "bowl_holder", "tunnel"]),
    ("A hideout on the left and a tunnel", ["hideout", "tunnel"]),
    ("a bowl on the left", ["bowl_holder"]),
])
def test_english_phrasings(rules, prompt, expected):
    assert shape(interpret(rules, prompt, language="en")) == expected


def test_english_zone_vs_side(rules):
    spec = interpret(rules, "put a hideout in the back left corner and a bottle on the left side of the hideout",
                     language="en")
    assert shape(spec) == ["hide bottle | bottle>hide.left"] and spec.items[0].placement.zone == "back_left"
    spec = interpret(rules, "a hideout on the left with a bowl", language="en")
    assert shape(spec) == ["hide bowl | bowl>hide.auto"] and spec.items[0].placement.zone == "left"
    spec = interpret(rules, "a bowl on the left side of the cage", language="en")
    assert shape(spec) == ["bowl_holder"] and spec.items[0].placement.zone == "left"
    spec = interpret(rules, "a hideout with a bowl", language="en")
    assert spec.items[0].name_ko == "Hideout with bowl holder" and "bowl holder → hideout" in spec.items[0].reason_ko


# ── 부품 값: 그 부품을 말한 절에서만 읽는다 ───────────────────────────


def test_params_come_from_each_parts_own_clause(rules):
    base = interpret(rules, "은신처").items[0].params
    spec = interpret(rules, "은신처 환기구 8개, 오른쪽에 밥그릇 달아줘")
    hide = spec.items[0].parts[0].params
    assert hide.vent_count == 8
    spec = interpret(rules, "터널은 U자로, 은신처 앞에 터널 달아줘")
    tube = next(p for p in spec.items[0].parts if p.template == "tunnel")
    assert tube.params.bend_angle_deg == 180
    # 크게는 모래목욕통 절의 말: 조립 항목의 은신처는 그대로, 따로 놓는 모래목욕통은 커진다
    spec = interpret(rules, "은신처 오른쪽에 밥그릇 달고, 모래목욕통은 크게")
    assert shape(spec) == ["hide bowl | bowl>hide.right", "sand_bath"]
    assert spec.items[0].parts[0].params.width_mm == base.width_mm
    assert spec.items[1].params.width_mm > interpret(rules, "모래목욕통").items[0].params.width_mm
    # 크기 말만 있는 절은 다음에 말한 기준 구조물에 쓴다
    spec = interpret(rules, "크게, 은신처 오른쪽에 밥그릇")
    assert spec.items[0].parts[0].params.width_mm > base.width_mm


def test_one_more_copies_the_values_of_the_same_template(rules):
    spec = interpret(rules, "환기구 8개짜리 은신처 앞에 터널로 은신처 하나 더 이어줘")
    assert shape(spec) == ["hide tube hide2 | tube>hide.front hide2>tube.free_end"]
    hide, _, hide2 = (p.params for p in spec.items[0].parts)
    assert hide.vent_count == 8 and hide2 == hide


# ── 수정 요청 (직전 설계 위에 빼기·더하기·크기) ─────────────────────────


def _revise(rules, prompts: list[str], **kw):
    spec = None
    for p in prompts:
        # 저장된 버전은 모든 템플릿 계약으로 다시 읽는다 (DesignService._previous_spec 과 같다)
        previous = parse_spec(spec.model_dump_json()) if spec is not None else None
        spec = interpret(rules, p, previous=previous, **kw)
    return spec


def test_revision_removes_a_part_with_its_connection_and_descendants(rules):
    assert shape(_revise(rules, ["은신처 오른쪽에 밥그릇 달아줘", "밥그릇 빼줘"])) == ["hideout"]
    spec = _revise(rules, ["밥그릇과 물병 달린 은신처", "물병 빼줘"])
    assert shape(spec) == ["hide bowl | bowl>hide.auto"]
    assert "물병" not in spec.items[0].name_ko
    # 터널을 빼면 터널 끝의 은신처도 빠진다
    assert shape(_revise(rules, ["은신처 앞에 터널로 은신처 하나 더 이어줘", "터널 빼줘"])) == ["hideout"]
    # '은신처에서' 는 어디서 빼는지: 은신처는 남는다
    assert shape(_revise(rules, ["밥그릇 달린 은신처", "은신처에서 밥그릇 빼줘"])) == ["hideout"]
    # 뿌리를 빼면 조립 항목이 통째로 빠지고 기본 은신처가 남는다
    spec = _revise(rules, ["밥그릇 달린 은신처", "은신처 빼줘"])
    assert shape(spec) == ["hideout"] and "모두 제외" in spec.items[0].reason_ko
    spec = _revise(rules, ["a hideout with a bowl", "remove the bowl from the hideout"], language="en")
    assert shape(spec) == ["hideout"]


def test_revision_adds_relations_to_the_previous_design(rules):
    # 따로 놓인 은신처에 붙이면 그 은신처(값·위치 그대로)가 조립 항목의 뿌리가 된다
    v1 = _revise(rules, ["은신처를 왼쪽에, 환기구 10개"])
    spec = _revise(rules, ["은신처를 왼쪽에, 환기구 10개", "은신처 오른쪽에 밥그릇 달아줘"])
    assert shape(spec) == ["hide bowl | bowl>hide.right"]
    assert spec.items[0].placement.zone == "left"
    assert spec.items[0].parts[0].params == v1.items[0].params
    # 면만 말해도 직전 설계의 기준 구조물에 붙는다
    spec = _revise(rules, ["밥그릇 달린 은신처", "왼쪽에 물병도 달아줘"])
    assert shape(spec) == ["hide bowl bottle | bowl>hide.auto bottle>hide.left"]
    assert "물병 거치대" in spec.items[0].name_ko
    spec = _revise(rules, ["밥그릇 달린 은신처", "앞에 터널로 은신처 하나 더 이어줘"])
    assert shape(spec) == ["hide bowl tube hide2 | bowl>hide.auto tube>hide.front hide2>tube.free_end"]
    # 따로 놓인 받침을 은신처에 붙이면 그 받침 항목이 조립 항목으로 옮겨 간다
    spec = _revise(rules, ["밥그릇이랑 은신처", "밥그릇을 은신처 오른쪽에 붙여줘"])
    assert shape(spec) == ["hide bowl | bowl>hide.right"]
    # 붙이는 말 없이 '하나 더 추가'는 예전처럼 따로 놓는 항목
    assert shape(_revise(rules, ["밥그릇 달린 은신처", "밥그릇 하나 더 추가해줘"])) == [
        "hide bowl | bowl>hide.auto", "bowl_holder"]


def test_revision_size_words_scale_the_host_parts(rules):
    v1 = _revise(rules, ["밥그릇 달린 은신처"])
    v2 = _revise(rules, ["밥그릇 달린 은신처", "더 크게 해 주세요"])
    assert shape(v2) == shape(v1)
    old, new = v1.items[0].parts, v2.items[0].parts
    assert new[0].params.width_mm > old[0].params.width_mm  # 은신처(기준 구조물)
    assert new[1].params == old[1].params  # 받침은 시판 그릇 크기에 맞춘 값이라 그대로
    assert v2.items[0].name_ko == v1.items[0].name_ko and v2.items[0].reason_ko == v1.items[0].reason_ko
    v3 = _revise(rules, ["밥그릇 달린 은신처", "환기구 10개로 바꿔 주세요"])
    assert v3.items[0].parts[0].params.vent_count == 10


def test_revision_reads_engine_inserted_parts_from_the_effective_spec(rules):
    """유효 명세에는 해석기가 끼운 터널(hide2_link)과 정해진 면이 들어 있다: 그대로 읽고 고친다."""
    v1 = interpret(rules, "은신처 앞에 은신처 하나 더 붙여줘")
    stored = json.loads(v1.model_dump_json())
    it = stored["items"][0]
    tube = interpret(rules, "터널").items[0].params.model_dump()
    it["parts"].insert(1, {"id": "hide2_link", "template": "tunnel", "params": tube})
    it["connections"] = [{"part": "hide2_link", "to": "hide", "at": "front"},
                         {"part": "hide2", "to": "hide2_link", "at": "free_end"}]
    previous = parse_spec(json.dumps(stored, ensure_ascii=False))
    spec = MockInterpreter().interpret(_req(rules, "은신처 오른쪽에 밥그릇 달아줘", previous=previous)).spec
    # 뿌리부터 너비 우선: 은신처의 자식(끼운 터널, 새 받침) 다음에 터널 끝의 은신처
    assert shape(spec) == ["hide hide2_link bowl hide2 | hide2_link>hide.front bowl>hide.right hide2>hide2_link.free_end"]


# ── 계약 묶음 ───────────────────────────────────────────────


def test_no_assembly_where_the_contract_has_none(rules):
    """기준 구조물이 없는 묶음(어항, 터널·램프·받침뿐)에는 조립 항목이 없다: 예전처럼 따로 놓는다."""
    spec = interpret(rules, "동굴 옆에 터널 달아줘", species="aquarium", size="nano_fish")
    assert all(it.template != "assembly" for it in spec.items)
    spec = interpret(rules, "밥그릇 달린 터널", allowed=("tunnel", "ramp", "bowl_holder"))
    assert shape(spec) == ["bowl_holder", "tunnel"]


def test_parts_outside_the_species_list_are_not_joined(rules):
    spec = interpret(rules, "물병 달린 은신처", allowed=("hideout", "bowl_holder"))
    assert shape(spec) == ["hideout"]
    assert any("만들 수 없는 구조물" in n and "물병 거치대" in n for n in spec.notes_ko), spec.notes_ko


# ── 모듈 라이브러리 시험(test_module_library)에서 옮긴, 세트와 상관없는 검사 ──────────────


def test_thickness_measure_skips_only_designed_thin_features():
    """끼움 턱·도브테일 혀처럼 일부러 얇게 만든 모양(PrintPart.thin_ok)의 표면 샘플만 뺀다: 같은 얇은 지느러미도 빼라고
    준 모양이 아니면 그대로 잡힌다."""
    plate = trimesh.creation.box((40, 40, 6))
    fin = trimesh.creation.box((1.2, 20, 10))
    fin.apply_translation([0, 0, 8])  # 판 윗면(z=3)에 선 1.2mm 지느러미 (광선 두께 측정에는 두 메시를 이어 붙이면 된다)
    mesh = trimesh.util.concatenate([plate, fin])
    far = trimesh.creation.box((5, 5, 5))
    far.apply_translation([100, 0, 0])
    assert np.percentile(measure_thickness(mesh), 1) < 2.0
    assert np.percentile(measure_thickness(mesh, exclude=far), 1) < 2.0
    assert np.percentile(measure_thickness(mesh, exclude=fin), 1) > 5.0


def test_shrink_to_fit_skips_sizes_that_break_part_rules(rules, monkeypatch):
    """공간 보정은 보정으로 고칠 수 없는 규칙(rule_issues)을 어기는 줄인 크기를 쓰지 않는다 (run_engine 은 규칙 검사를
    줄이기 전에만 하므로, 쓰면 저장된 설계를 다시 검증할 때 오류가 난다)."""
    t = get_template("hideout")
    monkeypatch.setattr(type(t), "rule_issues", lambda self, p, ctx: ["줄이면 안 됨"] if p.width_mm < 299 else [])
    ectx = EngineContext(cage=Cage(260, 230, 300), species="hamster", size="syrian", count=1, rules=rules)
    res = run_engine([ItemSpec("hideout", {"width_mm": 300, "depth_mm": 250, "height_mm": 150, "entrance_diameter_mm": 75})],
                     ectx)
    assert not [i for i in res.report.issues if i.code == "resized_to_fit"]
    assert res.items[0].params.width_mm == 300


def test_revision_keeps_two_assemblies_with_the_same_part_ids_apart(rules):
    """조립 항목마다 부품 id 가 따로라 두 항목에 hide·bowl 이 함께 있을 수 있다: 서로 섞지 않고 id 도 그대로 둔다."""
    v1 = interpret(rules, "밥그릇 달린 은신처")
    stored = json.loads(v1.model_dump_json())
    stored["items"].append(json.loads(json.dumps(stored["items"][0])))
    stored["items"][1]["placement"]["zone"] = "right"
    previous = parse_spec(json.dumps(stored, ensure_ascii=False))
    spec = MockInterpreter().interpret(_req(rules, "환기구 10개로 바꿔 주세요", previous=previous)).spec
    assert shape(spec) == ["hide bowl | bowl>hide.auto", "hide bowl | bowl>hide.auto"]
    assert [it.placement.zone for it in spec.items] == ["auto", "right"]
    # 새 연결은 마지막 항목의 은신처에 붙고, 다른 항목은 그대로
    spec = MockInterpreter().interpret(_req(rules, "은신처 왼쪽에 물병 달아줘", previous=previous)).spec
    assert shape(spec) == ["hide bowl | bowl>hide.auto", "hide bowl bottle | bowl>hide.auto bottle>hide.left"]
    assert spec.items[1].placement.zone == "right"


def test_decoration_is_left_out_of_assemblies_with_a_note(rules):
    spec = interpret(rules, "벌집 무늬 은신처에 밥그릇 달아줘")
    assert shape(spec) == ["hide bowl | bowl>hide.auto"]
    assert any("장식" in n for n in spec.notes_ko)
    spec = _revise(rules, ["벌집 무늬 은신처", "은신처에 밥그릇 달아줘"])
    assert shape(spec) == ["hide bowl | bowl>hide.auto"]
    assert any("장식" in n for n in spec.notes_ko)
    assert interpret(rules, "벌집 무늬 은신처").items[0].decor.pattern == "honeycomb"  # 따로 놓는 은신처는 예전 그대로


# ── 리뷰에서 찾은 해석 문제 (회귀) ──


@pytest.mark.parametrize("prompt,expected", [
    # 같은 받침·터널을 다른 면에 다시 말하면 하나 더 (앞 요청을 옮기지 않는다)
    ("은신처 오른쪽에 밥그릇, 왼쪽에 밥그릇", ["hide bowl bowl2 | bowl>hide.right bowl2>hide.left"]),
    ("은신처 앞에 터널, 뒤에 터널", ["hide tube tube2 | tube>hide.front tube2>hide.back"]),
    ("은신처 앞에 터널 달고 뒤에도 터널 달아줘", ["hide tube tube2 | tube>hide.front tube2>hide.back"]),
    ("은신처 오른쪽에 물병, 왼쪽에도 물병", ["hide bottle bottle2 | bottle>hide.right bottle2>hide.left"]),
    # 터널로 방 여러 개
    ("터널로 은신처 두 개 연결해줘", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("터널로 은신처 두 개 이어줘", ["hide tube hide2 | tube>hide.auto hide2>tube.free_end"]),
    ("은신처 3개를 터널로 이어줘",
     ["hide tube hide2 tube2 hide3 | tube>hide.auto hide2>tube.free_end tube2>hide2.auto hide3>tube2.free_end"]),
    ("터널로 이은 은신처 3개",
     ["hide tube hide2 tube2 hide3 | tube>hide.auto hide2>tube.free_end tube2>hide2.auto hide3>tube2.free_end"]),
    # 개수 말
    ("은신처 오른쪽에 밥그릇 두 개", ["hide bowl bowl2 | bowl>hide.right bowl2>hide.right"]),
    ("은신처에 터널 두 개 달아줘", ["hide tube tube2 | tube>hide.auto tube2>hide.auto"]),
    # 앞뒤
    ("은신처 앞뒤로 터널 연결", ["hide tube tube2 | tube>hide.front tube2>hide.back"]),
])
def test_review_korean_phrasings(rules, prompt, expected):
    assert shape(interpret(rules, prompt)) == expected


def test_review_too_many_rooms_in_a_tunnel_chain_gets_a_note(rules):
    spec = interpret(rules, "은신처 다섯 개를 터널로 이어줘")
    assert len(spec.items[0].parts) == 7  # 방 4 + 터널 3
    assert any("4개까지" in n for n in spec.notes_ko)


@pytest.mark.parametrize("prompt,expected", [
    ("three hideouts connected by tunnels",
     ["hide tube hide2 tube2 hide3 | tube>hide.auto hide2>tube.free_end tube2>hide2.auto hide3>tube2.free_end"]),
    ("put a bowl on the hideout's right side", ["hide bowl | bowl>hide.right"]),
    ("a bowl on the hideout's left side", ["hide bowl | bowl>hide.left"]),
    ("the hideout's right side gets a bowl", ["hide bowl | bowl>hide.right"]),
    ("two hideouts connected by a tunnel with a bowl on the right of the first",
     ["hide tube bowl hide2 | tube>hide.auto bowl>hide.right hide2>tube.free_end"]),
])
def test_review_english_phrasings(rules, prompt, expected):
    assert shape(interpret(rules, prompt, language="en")) == expected


@pytest.mark.parametrize("prompt,needle", [
    ("2층 집 앞에 터널로 은신처 이어줘", "출입구 모양이 달라"),
    ("모래목욕통 앞에 터널 연결", "출입구가 없는"),
])
def test_review_joins_the_engine_rejects_are_split_with_a_note(rules, prompt, needle):
    spec = interpret(rules, prompt)
    assert all(it.template != "assembly" for it in spec.items)
    assert any(needle in n for n in spec.notes_ko)


@pytest.mark.parametrize("prompts,expected,lang", [
    (["은신처 두 개를 터널로 이어줘", "두 번째 은신처 오른쪽에 밥그릇 달아줘"],
     ["hide tube hide2 bowl | tube>hide.auto hide2>tube.free_end bowl>hide2.right"], "ko"),
    (["밥그릇 달린 은신처", "밥그릇을 왼쪽으로 옮겨줘"], ["hide bowl | bowl>hide.left"], "ko"),
    (["a hideout with a bowl on the right", "move the bowl to the left"], ["hide bowl | bowl>hide.left"], "en"),
    (["은신처 오른쪽에 밥그릇, 왼쪽에 물병 달아줘", "물병 빼고 터널 달아줘"],
     ["hide bowl tube | bowl>hide.right tube>hide.auto"], "ko"),
    (["밥그릇 달린 은신처", "은신처 하나 더 터널로 이어줘"],
     ["hide bowl tube hide2 | bowl>hide.auto tube>hide.auto hide2>tube.free_end"], "ko"),
    (["은신처 양옆에 물병", "물병 하나 빼줘"], ["hide bottle | bottle>hide.right"], "ko"),
    (["은신처 양옆에 물병", "물병 빼줘"], ["hideout"], "ko"),
])
def test_review_revisions(rules, prompts, expected, lang):
    spec = _revise(rules, prompts, language=lang)
    assert shape(spec) == expected
    if prompts[-1] in ("밥그릇을 왼쪽으로 옮겨줘", "move the bowl to the left"):
        assert spec.items[0].placement.zone == "auto"  # 구조물 전체를 케이지 왼쪽으로 옮기지 않는다
