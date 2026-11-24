"""scripts/resolve_failures.py: 조립 해석 뒤 형상 검사 실패 집계 (stage 2 §3.5.6).

문구 꼴은 module_template 의 실제 문구 함수로 만든 문구에 맞춰 본다 (문구가 바뀌면 이 시험이 깨진다)."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import DesignVersion
from app.modules import module_template
from app.modules.module_template import AssemblyTemplate
from app.rules.loader import GapTrapRule
from scripts import resolve_failures as rf
from tests.api_helpers import make_design, signup
from tests.api_helpers import member_settings as settings

NAMES = {"hideout": "은신처", "bowl_holder": "그릇 받침", "tunnel": "터널", "ramp": "램프/계단",
         "deck_platform@v1": "발판 플랫폼"}


def _ctx(safe: float = 3.0, passable: float = 50.0):
    return SimpleNamespace(size=SimpleNamespace(gap_trap=GapTrapRule(safe_max_mm=safe, passable_min_mm=passable)))


def _geometry_messages(facts: list[tuple]) -> list[str]:
    fake = SimpleNamespace(_cached=lambda name, p, fn: facts)
    return AssemblyTemplate._geometry_issues(fake, None, _ctx())


FACTS = [
    (("leftover", "집", "터널", 120.0), "leftover"),
    (("plug_leftover", "은신처", "터널", 40.0), "plug_leftover"),
    (("overlap", "본체", "bowl", 12.0), "overlap"),
    (("slide_wide", "은신처", "그릇 받침", "right"), "slide_wide"),
    (("slide_floor", "은신처", "그릇 받침"), "slide_floor"),
    (("slide_contact", "은신처", "물병 거치대"), "slide_contact"),
    (("slide_gap", "은신처", "그릇 받침", [3.7]), "slide_gap"),          # 연결판이 띄운 만큼의 틈
    (("slide_gap", "집", "램프/계단", [6.0, 12.0]), "slide_gap"),        # 처마 쪽 쐐기 틈
]


@pytest.mark.parametrize(("fact", "kind"), FACTS, ids=[f"{k}-{i}" for i, (_, k) in enumerate(FACTS)])
def test_every_geometry_fact_message_is_classified(fact, kind):
    msgs = _geometry_messages([fact])
    assert len(msgs) == 1
    assert rf.classify_message(f"은신처 조립 #1: {msgs[0]}") == kind


def test_slot_gap_message_is_classified(monkeypatch):
    monkeypatch.setattr(module_template, "slot_gaps", lambda *a: [("hide", "bowl", 12.5)])
    monkeypatch.setattr(module_template, "part_meshes", lambda *a: {})
    parts = [SimpleNamespace(id="hide", template=SimpleNamespace(cutter=False)),
             SimpleNamespace(id="bowl", template=SimpleNamespace(cutter=False))]
    fake = SimpleNamespace(expand=lambda p: (parts, []), _cached=lambda name, p, fn: fn(),
                           part_names=lambda ps: {"hide": "은신처", "bowl": "그릇 받침"})
    msgs = AssemblyTemplate._gap_issues(fake, None, _ctx())
    assert len(msgs) == 1
    assert rf.classify_message(msgs[0]) == "slot_gap"


@pytest.mark.parametrize("msg", [
    "은신처 조립 #1: 은신처의 연결 지점 'front'에 터널, 그릇 받침을(를) 함께 이었습니다. 하나만 이으세요",
    "은신처 조립 #1: 은신처: 출입구 지름이 최소값보다 작습니다",
])
def test_other_rule_messages_are_not_geometry_facts(msg):
    assert rf.classify_message(msg) is None


def test_templates_are_found_by_name_id_and_root():
    parts = [{"id": "hide", "template": "hideout"}, {"id": "bowl", "template": "bowl_holder"},
             {"id": "hide2", "template": "hideout"}, {"id": "tube", "template": "tunnel"}]
    by_id, by_name = rf.part_lookup(parts, NAMES)
    assert by_name == {"은신처": "hideout", "그릇 받침": "bowl_holder", "은신처 2": "hideout", "터널": "tunnel"}
    assert rf.templates_in("그릇 받침이(가) 은신처 2의 '오른쪽' 면에서", by_id, by_name, "hideout") == \
        ["bowl_holder", "hideout"]
    assert rf.templates_in("따로 출력하는 파트 본체와(과) 그릇 받침 본체이(가) 겹칩니다", by_id, by_name, "hideout") == \
        ["hideout", "bowl_holder"]
    assert rf.templates_in("따로 출력하는 파트 그릇 받침 본체와(과) tube_body이(가) 겹칩니다", by_id, by_name,
                           "hideout") == ["bowl_holder", "tunnel"]
    assert rf.templates_in("터널(tube)와 그릇 받침(bowl) 사이 틈", by_id, by_name, None) == ["tunnel", "bowl_holder"]
    assert rf.templates_in("아무 이름도 없는 문구", by_id, by_name, None) == [rf.UNKNOWN]


# ── 집계 ──────────────────────────────────────────────


def _issue(code: str, msg: str, index: int = 0, severity: str = "error", **kw) -> dict:
    return {"code": code, "severity": severity, "message_ko": msg, "item_index": index, "auto_fixed": False,
            "details": {}, **kw}


def _row(n: int, *, spec_items: list, items: list, issues: list, size: str = "dwarf") -> rf.VersionRow:
    return rf.VersionRow(design_id=f"d{n}", version=1, llm_spec={"items": spec_items}, items=items,
                         report={"issues": issues}, species="hamster", size=size)


ASM = {"template": "assembly"}
LABEL = "그릇 받침이 달린 은신처 #1"


def _built(parts: list[dict], index: int = 0) -> dict:
    return {"index": index, "template": "assembly", "label_ko": LABEL,
            "assembly": {"v": 1, "root": parts[0]["id"], "parts": parts, "joins": []}}


def _rows() -> list[rf.VersionRow]:
    hide_bowl = [{"id": "hide", "template": "hideout"}, {"id": "bowl", "template": "bowl_holder"}]
    deck = [{"id": "deck", "template": "deck_platform@v1"}, {"id": "ramp", "template": "ramp"}]
    return [
        # 1. 일반 항목만: 조립 설계가 아니다
        _row(1, spec_items=[{"template": "hideout"}], items=[{"index": 0, "template": "hideout"}], issues=[]),
        # 2. 깨끗한 조립 (경고는 세지 않는다)
        _row(2, spec_items=[ASM], items=[_built(hide_bowl)],
             issues=[_issue("rule_violation", f"{LABEL}: 그릇 받침이(가) 은신처의 'right' 면에서 연결판을 붙일 수 "
                                              "있는 곳보다 넓거나 벗어납니다", severity="warning")]),
        # 3. 해석 실패: 단면 모양이 다르다 (port_adapter 경우)
        _row(3, spec_items=[ASM], items=[],
             issues=[_issue("join_unsupported", "조립 #1: 터널 양 끝의 출입구 단면 모양이 달라 (둥근 아치, 뾰족 아치) "
                                                "한 터널로 이을 수 없습니다")]),
        # 4. 해석 실패: 면 없음
        _row(4, spec_items=[ASM], items=[], issues=[_issue("face_unavailable", "조립 #1: 붙일 면이 없습니다")]),
        # 5. 해석 뒤 형상 사실 둘 (같은 항목: 항목 하나로 센다), 다른 규칙 위반은 세지 않는다
        _row(5, spec_items=[ASM], items=[_built(hide_bowl)], size="syrian", issues=[
            _issue("rule_violation", f"{LABEL}: 그릇 받침이(가) 은신처의 'right' 면에서 연결판을 붙일 수 있는 곳보다 "
                                     "넓거나 벗어납니다. 부품이 면 밖으로 튀어나오지 않게 크기나 위치를 바꾸세요"),
            _issue("rule_violation", f"{LABEL}: 은신처(hide)와 그릇 받침(bowl) 사이 틈 12.5mm 가 끼임 위험 구간"
                                     "(5~70mm)에 있습니다"),
            _issue("rule_violation", f"{LABEL}: 은신처: 바깥 출입구가 모자랍니다"),
        ]),
        # 6. 조립 둘 중 하나만 형상 사실 (설계 하나로 센다), 고친 오류는 세지 않는다
        _row(6, spec_items=[ASM, ASM], items=[_built(deck), _built(hide_bowl, index=1)], issues=[
            _issue("rule_violation", f"{LABEL}: 따로 출력하는 파트 본체와(과) 램프/계단 본체이(가) 겹칩니다 (약 40mm³). "
                                     "부품 위치나 크기를 바꾸세요"),
            _issue("rule_violation", f"{LABEL}: 은신처(hide)와 그릇 받침(bowl) 사이 틈 9mm 가 끼임 위험 구간",
                   index=1, auto_fixed=True),
        ]),
        # 7. 형상 생성 실패
        _row(7, spec_items=[ASM], items=[], issues=[_issue("build_failed", "조립 #1: 형상 생성에 실패했습니다")]),
    ]


def test_tally_counts_designs_items_kinds_and_templates():
    d = rf.tally(_rows(), template_names=NAMES).as_dict()
    assert (d["versions"], d["assembly_versions"], d["assembly_items"]) == (7, 6, 7)
    assert d["resolve_failed"] == {"items": 2, "by_code": {"join_unsupported": 1, "face_unavailable": 1},
                                   "profile_mismatch_items": 1}
    assert d["build_failed_items"] == 1
    assert d["resolved_items"] == 4
    g = d["geometry_failed"]
    assert (g["items"], g["versions"]) == (2, 2)
    assert {k: (v["items"], v["facts"]) for k, v in g["by_kind"].items()} == \
        {"slide_wide": (1, 1), "slot_gap": (1, 1), "overlap": (1, 1)}
    assert g["by_kind"]["slide_wide"]["templates"] == {"bowl_holder": 1, "hideout": 1}
    assert g["by_kind"]["overlap"]["templates"] == {"deck_platform@v1": 1, "ramp": 1}
    assert g["by_template"] == {"hideout": 1, "bowl_holder": 1, "deck_platform@v1": 1, "ramp": 1}
    assert g["by_size"] == {"hamster/syrian": 1, "hamster/dwarf": 1}
    assert d["other_errors_after_resolve"] == {"items": 1, "by_code": {"rule_violation": 1}}
    assert d["rates_pct"] == {"geometry_failed": round(200 / 6, 2), "profile_mismatch": round(100 / 6, 2)}
    assert d["verdict"] == {"retry_search": True, "port_adapter": True}
    text = rf.render(d)
    assert "retry search NEEDED" in text and "slot_gap" in text


def test_empty_database_gives_zero_rates():
    d = rf.tally([], template_names={}).as_dict()
    assert d["rates_pct"] == {"geometry_failed": 0.0, "profile_mismatch": 0.0}
    assert d["verdict"] == {"retry_search": False, "port_adapter": False}
    assert "not needed" in rf.render(d)


# ── 저장된 설계에서 (모의 해석기 + API) ─────────────────────────


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


def test_cli_reads_stored_versions(client, capsys):
    signup(client, "tally1")
    d = make_design(client, prompt="은신처 오른쪽에 그릇 받침")
    url = client.app.state.settings.database_url
    with client.app.state.session_factory() as db:
        v = db.scalar(select(DesignVersion).where(DesignVersion.design_id == d["id"]))
        built = [it for it in v.items if it.get("assembly")]
        assert built, "the mock should compose a hideout with a bowl holder"
        label = built[0]["label_ko"]
        # 같은 설계의 둘째 버전: 형상 사실이 하나 붙은 보고서
        report = copy.deepcopy(v.report)
        report["issues"].append(_issue("rule_violation", f"{label}: 은신처(hide)와 그릇 받침(bowl) 사이 틈 "
                                       "12.5mm 가 끼임 위험 구간(5~70mm)에 있습니다", index=built[0]["index"]))
        db.add(DesignVersion(design_id=v.design_id, version=2, prompt=v.prompt, provider=v.provider,
                             llm_spec=v.llm_spec, effective_spec=v.effective_spec, items=v.items, report=report,
                             passed=False))
        db.commit()

    assert rf.main(["--db-url", url, "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["assembly_versions"], out["resolved_items"]) == (2, 2)
    assert out["geometry_failed"]["by_kind"]["slot_gap"]["templates"] == {"hideout": 1, "bowl_holder": 1}
    assert out["rates_pct"]["geometry_failed"] == 50.0

    assert rf.main(["--db-url", url, "--latest-only"]) == 0
    text = capsys.readouterr().out
    assert "assembly designs (versions with an assembly item): 1" in text
    assert "= 100.0% of assembly designs" in text

    assert rf.main(["--db-url", url, "--json", "--since", "2999-01-01"]) == 0
    assert json.loads(capsys.readouterr().out)["versions"] == 0
