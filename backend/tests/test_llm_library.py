"""라이브러리 부품과 해석기 (설계 문서 §10, §9.6): 내놓는 부품(offered)과 수정 때 남기는 부품(sticky), 카탈로그·스키마,
모의 해석기의 라이브러리 낱말·이름·부품 id 와 없는 부품 안내 막기.

라이브러리 폴더는 임시 폴더로 바꿔(index.LIBRARY_DIR monkeypatch) 쓰고, 부품 템플릿은 registry.overlay 로 잠시 등록한다.
저장소의 index.json·species.yaml 은 건드리지 않는다. 부품 파일은 tests/data/library 의 §6 초안에 key·version 을 넣은 것이다.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.domain import Cage
from app.library import index
from app.library.template import make_template
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MISSING_KEYWORDS, MockInterpreter
from app.llm.prompts import template_catalog
from app.llm.spec import api_schema, parse_spec
from app.rules.loader import RuleBook, load_rules
from app.templates import registry

DRAFTS = Path(__file__).resolve().parent / "data" / "library"
JUNCTION, DECK, TRAY = "tunnel_junction@v1", "deck_platform@v1", "litter_tray@v1"
ROLES = {"tunnel_junction": "room_host", "deck_platform": "host", "litter_tray": "accessory"}
CAGE = Cage(1000, 600, 400)
# R12: 햄스터 구조화 출력 스키마의 게이팅 한도 (테스트 한도 30,000 보다 낮다)
SCHEMA_GATE = 29_000


def part_file(draft: str, *, family: str | None = None, version: int = 1, **override: Any) -> dict:
    """§6 초안 → 게시 파일 (key·version 을 넣은 정규 순서). override 는 최상위 필드를 바꾼다."""
    raw = json.loads((DRAFTS / f"{draft}.json").read_text(encoding="utf-8"))
    family = family or raw["family"]
    obj = {"dsl": raw["dsl"], "key": f"{family}@v{version}", "family": family, "version": version}
    obj.update({k: v for k, v in raw.items() if k not in obj})
    obj.update(copy.deepcopy(override))
    return obj


@dataclass
class Library:
    """임시 라이브러리 폴더 + 등록된 템플릿. set_status 로 색인 상태를 바꾼다 (파일 sha 는 그대로)."""

    root: Path
    entries: dict[str, dict] = field(default_factory=dict)
    templates: dict[str, Any] = field(default_factory=dict)

    def write_index(self) -> None:
        (self.root / "index.json").write_text(index.dump_index({"v": 1, "parts": self.entries}), encoding="utf-8")
        index.clear_cache()

    def set_status(self, key: str, status: str, reason: tuple[str, str] | None = None) -> None:
        self.entries[key]["status"] = status
        self.entries[key]["reason"] = {"ko": reason[0], "en": reason[1]} if reason else None
        self.write_index()


def build_library(root: Path, parts: dict[str, dict]) -> Library:
    """parts: key → 게시 파일 dict. 상태는 모두 active, 햄스터 두 크기에서 검증했다고 적는다."""
    (root / "parts").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    lib = Library(root)
    for key, obj in parts.items():
        data = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode()
        (root / "parts" / f"{key}.json").write_bytes(data)
        lib.entries[key] = {
            "sha256": hashlib.sha256(data).hexdigest(), "status": "active", "published_at": "2026-12-01",
            "family": obj["family"], "version": obj["version"], "role": obj["role"], "habitats": ["cage"],
            "verified_for": {"hamster": ["dwarf", "syrian"]}, "rule_fields_used": [], "rules_digest": {},
            "golden": {}, "superseded_by": None, "reason": None, "request_ids": [],
        }
        lib.templates[key] = make_template(obj, key=key, published=True)
    lib.write_index()
    return lib


STANDARD = {JUNCTION: ("tunnel_junction", {}), DECK: ("deck_platform", {}), TRAY: ("litter_tray", {})}


@contextlib.contextmanager
def library_installed(monkeypatch, root: Path, parts: dict[str, dict] | None = None) -> Iterator[Library]:
    """라이브러리 폴더를 쓰고 부품 템플릿을 등록한다 (나올 때 등록을 지운다)."""
    if parts is None:
        parts = {k: part_file(d, **o) for k, (d, o) in STANDARD.items()}
    monkeypatch.setattr(index, "LIBRARY_DIR", root)
    lib = build_library(root, parts)
    try:
        with without_repository_parts(), registry.overlay(lib.templates):
            yield lib
    finally:
        index.clear_cache()


@contextlib.contextmanager
def without_repository_parts() -> Iterator[None]:
    """저장소 라이브러리에서 게시해 등록된 부품을 레지스트리에서 잠시 뺀다: 임시 라이브러리가 같은 key 를 다시
    등록하고(overlay 는 겹치는 key 를 거절한다), 레지스트리가 임시 색인과 맞게 한다. 나올 때 그대로 되돌린다."""
    saved_p, saved_t = dict(registry._PRIMITIVES), dict(registry._TEMPLATES)
    for key in set(registry._PRIMITIVES) - set(registry.code_keys()):
        registry._PRIMITIVES.pop(key)
        registry._TEMPLATES.pop(key, None)
    registry._clear_caches()
    try:
        yield
    finally:
        registry._PRIMITIVES.clear()
        registry._PRIMITIVES.update(saved_p)
        registry._TEMPLATES.clear()
        registry._TEMPLATES.update(saved_t)
        registry._clear_caches()


@pytest.fixture
def library(monkeypatch, tmp_path) -> Iterator[Library]:
    """§6 의 세 부품(갈림길·발판 플랫폼·화장실 트레이)을 활성으로 게시한 라이브러리."""
    with library_installed(monkeypatch, tmp_path / "lib") as lib:
        yield lib


def gated_rules(rules_dir: Path, *keys: str) -> RuleBook:
    """햄스터 templates 에 라이브러리 키를 더한 규칙 (색인을 먼저 바꿔 둔 뒤에 읽는다: 게이팅 검사가 색인을 본다)."""
    p = rules_dir / "species.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data["species"]["hamster"]["templates"] = list(dict.fromkeys([*data["species"]["hamster"]["templates"], *keys]))
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return load_rules(rules_dir)


def request(rules: RuleBook, prompt: str, allowed: tuple[str, ...], language: str = "ko", previous=None,
            size: str = "syrian") -> InterpretRequest:
    return InterpretRequest(
        prompt=prompt, habitat=HabitatInfo("hamster", "햄스터", size, 1, CAGE),
        size_rules=rules.size_rules("hamster", size), min_wall_mm=rules.min_wall_for("hamster", size),
        previous=previous, language=language, allowed_templates=allowed,
    )


def mock(rules: RuleBook, prompt: str, allowed: tuple[str, ...], **kw):
    return MockInterpreter().interpret(request(rules, prompt, allowed, **kw)).spec


def shape(spec) -> list:
    """항목 요약: 일반 항목은 템플릿 키, 조립 항목은 (부품 (id, 템플릿), 연결 (part, to, at))."""
    out: list = []
    for it in spec.model_dump(mode="json")["items"]:
        if it["template"] == "assembly":
            out.append(([(p["id"], p["template"]) for p in it["parts"]],
                        [(c["part"], c["to"], c["at"]) for c in it["connections"]]))
        else:
            out.append(it["template"])
    return out


def resolve_all(rules: RuleBook, spec, size: str = "syrian") -> list:
    """조립 항목마다 조립 해석기를 돌려 (부모 연결 지점, 자식 연결 지점, 결합) 목록을 돌려준다 (오류면 실패)."""
    from app.modules import compose
    from app.services.engine import EngineContext

    ctx = EngineContext(cage=CAGE, species="hamster", size=size, count=1, rules=rules)
    out = []
    for it in spec.items:
        if it.template != "assembly":
            continue
        res = compose.resolve(it.to_request(), None, ctx.fit_ctx, templates=registry.primitives())
        assert not hasattr(res, "code"), getattr(res, "message_ko", res)
        resolved, _, _ = res
        out.append([(j.parent, j.child, j.mount) for j in resolved.joins])
    return out


@pytest.fixture
def code_allowed(rules) -> tuple[str, ...]:
    """햄스터에 허용한 코드 부품 (저장소에서 게이팅한 라이브러리 부품은 뺀다: 시험마다 임시 라이브러리를 쓴다)."""
    return tuple(k for k in rules.allowed_templates("hamster") if "@" not in k)


# ── 내놓는 부품과 카탈로그·스키마 ─────────────────────────────────

def test_catalog_and_schema_include_offered_library_parts(library, rules_copy):
    rules = gated_rules(rules_copy, JUNCTION, DECK)
    offered = rules.offered_templates("hamster")
    assert offered[-2:] == (JUNCTION, DECK)
    catalog = {e["template"]: e for e in template_catalog(offered)}
    assert catalog[JUNCTION]["이름"] == "터널 갈림길"
    assert catalog[DECK]["이름"] == "발판 플랫폼"
    # 연결 설명은 연결 지점에서 만든다: 갈림길은 터널 끝에 잇는 방, 발판 플랫폼은 옆면에 램프를 받는 기준 부품
    assert "끝에 이을 수 있다" in catalog[JUNCTION]["연결"]
    assert "기준 부품" in catalog[DECK]["연결"] and "램프" in catalog[DECK]["연결"]
    assert set(catalog[JUNCTION]["파라미터"]) == {"wall_thickness_mm", "layout", "door_width_mm", "door_shape",
                                                 "size_mm", "height_mm"}
    schema = json.dumps(api_schema(offered), ensure_ascii=False)
    assert "LibTunnelJunctionV1Params" in schema and "LibDeckPlatformV1Params" in schema
    assert "LibLitterTrayV1Params" not in schema
    # 해석 결과 계약도 그 부품을 받는다 (조립 항목의 부품으로도)
    spec = mock(rules, "갈림길로 은신처 세 개", offered)
    parse_spec(spec.model_dump_json(), offered)


def test_retired_and_blocked_parts_are_hidden_from_new_designs(library, rules_copy):
    rules = gated_rules(rules_copy, JUNCTION, DECK, TRAY)
    library.set_status(DECK, "retired", ("새 판으로 바꿨습니다", "Replaced by a new version"))
    library.set_status(TRAY, "blocked", ("안전 문제가 있습니다", "There is a safety problem"))
    offered = rules.offered_templates("hamster")
    assert JUNCTION in offered and DECK not in offered and TRAY not in offered
    # 저장된 설계를 다시 검증·재생성할 수 있게 허용 목록과 레지스트리에는 남는다 (R7)
    assert {DECK, TRAY} <= set(rules.allowed_templates("hamster")) <= set(registry.primitives())
    names = {e["template"] for e in template_catalog(offered)}
    assert JUNCTION in names and not {DECK, TRAY} & names
    schema = json.dumps(api_schema(offered), ensure_ascii=False)
    assert "LibDeckPlatformV1Params" not in schema and "LibLitterTrayV1Params" not in schema
    # 모의 해석기도 그 부품 낱말을 읽지 않는다 (색인 keywords() 는 활성 부품만)
    assert shape(mock(rules, "발판 플랫폼 하나", offered)) == ["hideout"]


def test_hamster_schema_with_the_first_parts_stays_under_the_gate(library, code_allowed):
    """R12: 갈림길과 발판 플랫폼을 더한 햄스터 스키마가 29,000 자 이하이고, 부품 하나가 2,300 자를 넘게 늘리지 않는다
    (화장실 트레이까지 더하면 한도를 넘어 카탈로그 좁히기를 기다린다: §6.3, §15)."""
    def size(keys) -> int:
        return len(json.dumps(api_schema(keys), ensure_ascii=False))

    base = size(code_allowed)
    for key in (JUNCTION, DECK, TRAY):
        assert size((*code_allowed, key)) - base <= 2_300, key
    assert size((*code_allowed, JUNCTION, DECK)) <= SCHEMA_GATE


# ── 서비스: 내놓는 부품과 수정 때 남기는 부품 ───────────────────────

def _service(rules: RuleBook, tmp_path: Path, seen: list):
    from app.llm.base import InterpretResult
    from app.services.design_service import DesignService

    class Spy:
        name = "spy"

        def interpret(self, req: InterpretRequest) -> InterpretResult:
            seen.append(req.allowed_templates)
            return MockInterpreter().interpret(req)

    return DesignService(rules, interpreter=lambda: Spy(), mesh_dir=tmp_path / "meshes")


def _habitat():
    from app.models import Habitat

    return Habitat(species="hamster", size="syrian", count=1, cage_width_mm=1000, cage_depth_mm=600,
                   cage_height_mm=400)


def test_generate_offers_library_parts_and_keeps_retired_parts_in_revisions(library, rules_copy, tmp_path,
                                                                            monkeypatch):
    from app.services import design_service

    monkeypatch.setattr(design_service, "run_engine", lambda specs, ctx: None)  # 형상은 만들지 않는다
    rules = gated_rules(rules_copy, JUNCTION, DECK, TRAY)
    seen: list = []
    svc = _service(rules, tmp_path, seen)
    h = _habitat()
    first = svc._generate(h, "플랫폼 오른쪽에 램프, 은신처 옆에 화장실", previous=None)
    assert seen[-1] == rules.allowed_templates("hamster")  # 모두 활성: 허용 목록 그대로
    previous = first.interpret.spec
    assert {DECK, TRAY} <= {k for it in shape(previous) if isinstance(it, tuple) for _, k in it[0]}

    library.set_status(DECK, "retired", ("새 판으로 바꿨습니다", "Replaced by a new version"))
    library.set_status(TRAY, "blocked", ("안전 문제가 있습니다", "There is a safety problem"))
    svc._generate(h, "은신처 하나 더", previous=None)
    assert DECK not in seen[-1] and TRAY not in seen[-1]
    # 수정: 직전 설계가 쓰던 폐기 부품은 남고(sticky, 맨 뒤), 차단 부품은 내놓지 않는다
    svc._generate(h, "램프를 왼쪽으로 옮겨 줘", previous=previous)
    assert seen[-1] == (*rules.offered_templates("hamster"), DECK)
    assert svc.offered_templates("hamster", previous) == seen[-1]
    # 직전 설계에 없는 폐기 부품은 수정에서도 내놓지 않는다
    v1 = mock(rules, "은신처 하나", rules.offered_templates("hamster"))
    assert svc.offered_templates("hamster", v1) == rules.offered_templates("hamster")


def test_sticky_parts_must_still_be_allowed_for_the_species(library, rules_copy, tmp_path):
    """종 규칙에서 빠진 부품은 직전 설계에 있어도 내놓지 않는다 (엔진도 allowed 로 막는다)."""
    rules = gated_rules(rules_copy, JUNCTION)
    with_deck = gated_rules(rules_copy, DECK)  # 같은 폴더: 이제 junction·deck 모두
    previous = mock(with_deck, "플랫폼 오른쪽에 램프", with_deck.offered_templates("hamster"))
    svc = _service(rules, tmp_path, [])
    assert DECK not in svc.offered_templates("hamster", previous)
    svc2 = _service(with_deck, tmp_path, [])
    assert DECK in svc2.offered_templates("hamster", previous)


# ── 모의 해석기: 라이브러리 낱말 ────────────────────────────────────

ALL = (JUNCTION, DECK, TRAY)


def test_mock_reads_library_keywords_and_part_ids(library, rules, code_allowed):
    allowed = (*code_allowed, *ALL)
    assert shape(mock(rules, "갈림길 하나 만들어 주세요", allowed)) == [JUNCTION]
    assert shape(mock(rules, "a deck platform, please", allowed, language="en")) == [DECK]
    # 갈림길로 은신처 세 개 → 은신처 ← 터널 ← 갈림길 ← 터널 ← 은신처 (×2)
    spec = mock(rules, "갈림길로 은신처 세 개", allowed)
    assert shape(spec) == [(
        [("hide", "hideout"), ("tube", "tunnel"), ("hub", JUNCTION), ("tube2", "tunnel"), ("tube3", "tunnel"),
         ("hide2", "hideout"), ("hide3", "hideout")],
        [("tube", "hide", "auto"), ("hub", "tube", "free_end"), ("tube2", "hub", "auto"), ("tube3", "hub", "auto"),
         ("hide2", "tube2", "free_end"), ("hide3", "tube3", "free_end")],
    )]
    assert spec.notes_ko == []
    # 플랫폼 오른쪽에 램프 → 발판 플랫폼 + 오른쪽 램프 / 은신처 옆에 화장실 → 은신처 + 빈 면의 트레이
    assert shape(mock(rules, "플랫폼 오른쪽에 램프", allowed)) == [
        ([("deck", DECK), ("ramp", "ramp")], [("ramp", "deck", "right")])]
    assert shape(mock(rules, "은신처 옆에 화장실", allowed)) == [
        ([("hide", "hideout"), ("toilet", TRAY)], [("toilet", "hide", "auto")])]


def test_mock_phrases_resolve(library, rules, code_allowed):
    """세 문구의 조립 항목이 조립 해석기를 통과한다: 갈림길 출입구 셋에 터널이 하나씩, 램프는 발판 오른쪽 면에 끼운다."""
    allowed = (*code_allowed, *ALL)
    (hub,) = resolve_all(rules, mock(rules, "갈림길로 은신처 세 개", allowed))
    assert {p for p, _, _ in hub if p.startswith("hub.")} == {"hub.left", "hub.right"}
    assert ("tube.end_a", "hub.front", "plug") in hub
    assert resolve_all(rules, mock(rules, "플랫폼 오른쪽에 램프, 왼쪽에 물병 거치대", allowed)) == [
        [("deck.right", "ramp.landing", "slide"), ("deck.left", "bottle.back", "slide")]]
    ((tray_join,),) = resolve_all(rules, mock(rules, "은신처 옆에 화장실", allowed))
    assert tray_join[1:] == ("toilet.back", "slide")


def test_mock_english_phrases_and_names(library, rules, code_allowed):
    allowed = (*code_allowed, *ALL)
    spec = mock(rules, "connect three hideouts with a junction", allowed, language="en")
    assert [k for _, k in shape(spec)[0][0]].count(JUNCTION) == 1
    assert shape(mock(rules, "three hideouts around a junction", allowed, language="en")) == shape(spec)
    spec = mock(rules, "a litter tray next to the hideout", allowed, language="en")
    assert shape(spec) == [([("hide", "hideout"), ("toilet", TRAY)], [("toilet", "hide", "auto")])]
    assert spec.items[0].name_ko == "Hideout with litter tray"
    # 따로 놓는 항목의 설명·요약에도 부품 이름 (응답 언어)
    spec = mock(rules, "a deck platform", allowed, language="en")
    assert "Deck platform" in spec.items[0].reason_ko and "Deck platform" in spec.summary_ko
    spec = mock(rules, "발판 플랫폼 하나", allowed)
    assert "'발판 플랫폼'" in spec.items[0].reason_ko


def test_mock_hub_is_capped_by_the_doors_of_the_junction(library, rules, code_allowed):
    spec = mock(rules, "갈림길로 은신처 네 개", (*code_allowed, *ALL))
    parts = shape(spec)[0][0]
    assert [k for _, k in parts].count("hideout") == 3
    assert spec.notes_ko == ["터널 갈림길에는 출입구가 3개라 방을 3개만 이었습니다."]
    en = mock(rules, "connect four hideouts with a junction", (*code_allowed, *ALL), language="en")
    assert en.notes_ko == ["The tunnel junction has 3 doors, so I linked 3 rooms."]


def test_mock_without_tunnels_joins_rooms_to_the_hub_directly(library, rules):
    """터널을 내놓지 않으면 방을 갈림길에 바로 잇는다 (해석기가 터널을 끼운다: 이 종에 터널이 없으면 엔진이 막는다)."""
    allowed = ("hideout", "house", JUNCTION)
    assert shape(mock(rules, "갈림길로 은신처 세 개", allowed)) == [(
        [("hide", "hideout"), ("hub", JUNCTION), ("hide2", "hideout"), ("hide3", "hideout")],
        [("hub", "hide", "auto"), ("hide2", "hub", "auto"), ("hide3", "hub", "auto")])]


def test_code_words_keep_their_meaning(library, rules, code_allowed):
    """코드 부품 낱말과 같은 라이브러리 낱말은 쓰지 않는다: '2층'은 집, '터널 연결'은 터널 + 연결 말. 낱말이 겹치면
    라이브러리 부품의 긴 낱말이 먼저다 ('모래 화장실'은 모래목욕통이 아니라 화장실 트레이)."""
    allowed = (*code_allowed, *ALL)
    assert shape(mock(rules, "2층 집", allowed)) == ["house"]
    assert shape(mock(rules, "a loft house", allowed, language="en")) == ["house"]
    assert shape(mock(rules, "모래 화장실 하나", allowed)) == [TRAY]
    assert shape(mock(rules, "모래목욕통 하나", allowed)) == ["sand_bath"]


def test_library_words_need_the_part_to_be_offered(library, rules, code_allowed):
    """내놓지 않은(이 종에 허용되지 않은) 라이브러리 부품의 낱말은 읽지 않는다: 예전과 같은 결과."""
    assert shape(mock(rules, "갈림길로 은신처 세 개", code_allowed)) == ["hideout"]
    assert shape(mock(rules, "플랫폼 오른쪽에 램프", code_allowed)) == ["ramp"]


def test_newest_offered_version_of_a_family_takes_the_words(monkeypatch, tmp_path, rules, code_allowed):
    v2 = part_file("tunnel_junction", version=2, part_id="hub", keywords={"ko": ["갈림길", "분기"], "en": ["junction"]})
    parts = {JUNCTION: part_file("tunnel_junction"), "tunnel_junction@v2": v2}
    with library_installed(monkeypatch, tmp_path / "lib", parts):
        both = (*code_allowed, JUNCTION, "tunnel_junction@v2")
        assert shape(mock(rules, "갈림길 하나", both)) == ["tunnel_junction@v2"]
        assert shape(mock(rules, "갈림길 하나", (*code_allowed, JUNCTION))) == [JUNCTION]


def test_missing_part_is_not_reported_when_a_library_part_claims_the_word(monkeypatch, tmp_path, rules,
                                                                         code_allowed):
    """쳇바퀴를 맡은 라이브러리 부품을 내놓으면 쳇바퀴는 더는 '없는 부품'이 아니다 (부품 수요로 세지 않는다)."""
    wheel = part_file("litter_tray", family="spin_wheel", part_id="wheel",
                      name={"ko": "회전 바퀴", "en": "Spin wheel"},
                      keywords={"ko": ["쳇바퀴"], "en": ["exercise wheel"]}, fulfills=["쳇바퀴"])
    with library_installed(monkeypatch, tmp_path / "lib", {"spin_wheel@v1": wheel}):
        offered = (*code_allowed, "spin_wheel@v1")
        spec = mock(rules, "은신처 옆에 쳇바퀴", offered)
        assert spec.missing_parts == []
        assert shape(spec) == [([("hide", "hideout"), ("wheel", "spin_wheel@v1")], [("wheel", "hide", "auto")])]
        en = mock(rules, "a hideout and an exercise wheel", offered, language="en")
        assert en.missing_parts == [] and "spin_wheel@v1" in shape(en)
        # 다른 없는 부품(해먹)은 그대로 알린다. 부품을 내놓지 않은 종에서는 쳇바퀴도 그대로 알린다
        assert [m.name_ko for m in mock(rules, "쳇바퀴랑 해먹", offered).missing_parts] == ["해먹"]
        assert [m.name_ko for m in mock(rules, "쳇바퀴랑 해먹", code_allowed).missing_parts] == ["쳇바퀴", "해먹"]
    assert set(MISSING_KEYWORDS) == {"wheel", "hammock", "swing", "seesaw"}


def test_missing_parts_are_not_repeated_in_notes(rules, code_allowed):
    """없는 부품은 화면이 missing_parts 로 알린다 (설계 화면의 안내). notes_ko 에 같은 말을 적지 않는다."""
    spec = mock(rules, "은신처랑 쳇바퀴 만들어줘", code_allowed)
    assert [m.name_ko for m in spec.missing_parts] == ["쳇바퀴"]
    assert not any("쳇바퀴" in n for n in spec.notes_ko)


def test_revision_keeps_a_retired_part_through_the_mock(library, rules_copy):
    """폐기 부품을 쓴 설계를 고치면 (그 부품이 sticky 로 허용 목록에 남아) 모의 해석기가 그 부품을 그대로 둔다."""
    rules = gated_rules(rules_copy, DECK)
    v1 = mock(rules, "플랫폼 오른쪽에 램프", rules.offered_templates("hamster"))
    library.set_status(DECK, "retired", ("새 판으로 바꿨습니다", "Replaced by a new version"))
    sticky = (*rules.offered_templates("hamster"), DECK)
    v2 = mock(rules, "램프를 왼쪽으로 옮겨 줘", sticky, previous=v1)
    assert shape(v2) == [([("deck", DECK), ("ramp", "ramp")], [("ramp", "deck", "left")])]
    # 허용 목록에서 빠지면(차단) 실제 LLM 처럼 빼고 알린다
    v3 = mock(rules, "램프를 왼쪽으로 옮겨 줘", rules.offered_templates("hamster"), previous=v1)
    assert DECK not in json.dumps(shape(v3))
    assert any("발판 플랫폼" in n for n in v3.notes_ko)
