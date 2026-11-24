"""자유 조립 끝에서 끝까지: 요청 글(모의 해석기) → 계약(parse_spec) → 엔진(조립 해석·자동 보정·배치·검증) → 통과,
API 로 저장한 버전을 캐시를 비운 뒤 같은 바이트로 다시 만들고 출력 파트마다 파일 하나씩 내보내는지, 성능 예산.

설계 문서의 시험 계획(엔진·저장, 성능)에 있는 요청 글을 햄스터 두 크기(드워프·시리안)로 돌린다. 결합 방식·연결 지점은
해석기가 정하므로 여기서는 해석기가 고른 결과(부모 연결 지점 → 자식 연결 지점, 끼움 방식, 통로 방향)까지 본다.

성능 예산 (설계 문서): 조립 항목의 rule_issues 는 부품 5개 10초, 8개 30초 이하. 형상 캐시가 빈 새 조립 항목 템플릿으로 잰다.
"""

from __future__ import annotations

import hashlib
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from app.domain import Cage
from app.geometry.fingerprint import geometry_fingerprint
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.llm.spec import parse_spec, to_item_specs
from app.main import create_app
from app.models import DesignVersion
from app.modules import compose, module_template
from app.modules.composed import ComposedTemplate
from app.modules.structure import AssemblyRequest
from app.services import design_service, engine
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.validation.autofix import clamp_params
from app.validation.report import Issue, Severity
from tests.api_helpers import create_habitat
from tests.api_helpers import make_settings as settings
from tests.test_geometry_drift import exported_parts

SIZES = ("dwarf", "syrian")
CAGE = Cage(1000, 600, 400)

EXAMPLE_KO = "은신처 오른쪽에 밥그릇 받침, 왼쪽에 물병 거치대, 앞에는 터널로 은신처 하나 더 이어줘"
EXAMPLE_EN = ("a hideout with a bowl on the right and a water bottle on the left, and connect another hideout through a "
              "tunnel at the front")
EXAMPLE_JOINS = [("hide.right", "bowl.back", "slide", False), ("hide.left", "bottle.back", "slide", False),
                 ("hide.front", "tube.end_b", "plug", "into_parent"), ("tube.end_a", "hide2.front", "plug", "into_child")]
TWIN_JOINS = [("hide.front", "tube.end_b", "plug", "into_parent"), ("tube.end_a", "hide2.front", "plug", "into_child")]


# 요청 글 → (부품 id, 해석한 결합, 출력 파트 키, 꼭 나와야 하는 해석기 안내)
CASES: dict[str, tuple[list[str], list[tuple], list[str], set[str]]] = {
    EXAMPLE_KO: (["hide", "bowl", "bottle", "tube", "hide2"], EXAMPLE_JOINS,
                 ["body", "bowl", "bottle_base", "tube", "hide2", "bottle_holder"],
                 {"exit_added", "passage_shape_matched"}),
    "밥그릇 달린 은신처": (["hide", "bowl"], [("hide.right", "bowl.back", "slide", False)], ["body", "bowl"], set()),
    "경사로 달린 모래목욕통": (["bath", "ramp"], [("bath.front", "ramp.landing", "slide", False)], ["body", "ramp"], set()),
    "터널로 이은 은신처 두 개": (["hide", "tube", "hide2"], TWIN_JOINS, ["body", "tube", "hide2"],
                          {"exit_added", "passage_shape_matched"}),
    "은신처 양옆에 밥그릇이랑 물병": (["hide", "bowl", "bottle"],
                          [("hide.right", "bowl.back", "slide", False), ("hide.left", "bottle.back", "slide", False)],
                          ["body", "bowl", "bottle_base", "bottle_holder"], set()),
    # '집' 만 말하면 은신처다. 은신처 오른쪽 벽에 옆면 출입구를 내고 터널을 단다 (port_opened, 2단계 §3.2)
    "집 오른쪽에 터널 달고 그 끝에 은신처": (["hide", "tube", "hide2"],
                               [("hide.right", "tube.end_b", "plug", "into_parent"), TWIN_JOINS[1]],
                               ["body", "tube", "hide2"], {"port_opened", "exit_added", "passage_shape_matched"}),
}


def _request(rules, prompt: str, size: str, language: str = "ko") -> InterpretRequest:
    entry = rules.species_entry("hamster")
    return InterpretRequest(
        prompt=prompt, habitat=HabitatInfo("hamster", entry.display_name, size, 1, CAGE, habitat=entry.habitat),
        size_rules=rules.size_rules("hamster", size), min_wall_mm=rules.min_wall_for("hamster", size),
        language=language, allowed_templates=rules.allowed_templates("hamster"),
    )


def _ctx(rules, size: str, cage: Cage = CAGE) -> EngineContext:
    return EngineContext(cage=cage, species="hamster", size=size, count=1, rules=rules)


def _not_info(report) -> list[tuple[str, str]]:
    return [(i.code, i.message_ko) for i in report.issues if i.severity != Severity.info]


def _check_built(res, ids: list[str], joins: list[tuple], print_keys: list[str], infos: set[str]) -> None:
    assert res.report.passed, _not_info(res.report)
    assert not _not_info(res.report)  # 경고도 없다 (출력 크기 초과 등)
    [it] = res.items
    assert it.key == "assembly" and it.placement is not None
    assert [p.id for p in it.assembly.parts] == ids
    assert [(j.parent, j.child, j.mount, j.passage) for j in it.assembly.joins] == joins
    assert [pp.key for pp in it.print_parts] == print_keys
    got = {i.code for i in res.report.issues if i.severity == Severity.info}
    assert infos <= got, got
    # 해석기 안내는 어느 부품의 일인지 알린다
    assert all(i.details.get("part") for i in res.report.issues if i.code in compose.INFO_CODES)


# ── 요청 글 → 모의 해석기 → 엔진 → 통과 ─────────────────────────


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("prompt", list(CASES))
def test_mock_prompt_composes_and_passes_the_engine(rules, prompt, size):
    ids, joins, print_keys, infos = CASES[prompt]
    spec = MockInterpreter().interpret(_request(rules, prompt, size)).spec
    req = _request(rules, prompt, size)
    assert parse_spec(spec.model_dump_json(), req.allowed_templates) == spec  # 실제 LLM 과 같은 계약
    [item] = spec.items
    assert item.template == "assembly" and [p.id for p in item.parts] == ids
    assert spec.missing_parts == []
    _check_built(run_engine(to_item_specs(spec), _ctx(rules, size)), ids, joins, print_keys, infos)


def test_english_example_prompt_composes_the_same_structure(rules):
    spec = MockInterpreter().interpret(_request(rules, EXAMPLE_EN, "dwarf", language="en")).spec
    ids, joins, print_keys, infos = CASES[EXAMPLE_KO]
    _check_built(run_engine(to_item_specs(spec), _ctx(rules, "dwarf")), ids, joins, print_keys, infos)


@pytest.mark.parametrize("size", SIZES)
def test_example_links_sizes_and_follows_the_species(rules, size):
    """연결된 치수: 터널 내경과 두 번째 은신처 출입구는 첫 은신처 출입구를 따르고, 그 값은 이 종의 최소 출입구 이상이다.
    출구가 막히지 않게 두 은신처 모두 출입구 2개, 터널 단면은 은신처 출입구(둥근 아치) 모양."""
    spec = MockInterpreter().interpret(_request(rules, EXAMPLE_KO, size)).spec
    [it] = run_engine(to_item_specs(spec), _ctx(rules, size)).items
    p = it.params
    door = p.hide.entrance_diameter_mm
    assert door >= rules.size_rules("hamster", size).entrance_min_diameter_mm
    assert p.tube.inner_diameter_mm == door and p.hide2.entrance_diameter_mm == door
    assert p.hide.entrance_count == 2 and p.hide2.entrance_count == 2
    assert p.tube.shape == "round_arch"


# ── API: 저장 → 캐시를 비우고 다시 만들기 → 내보내기 ─────────────────


def _version_row(c: TestClient) -> DesignVersion:
    with c.app.state.session_factory() as db:
        return db.query(DesignVersion).order_by(DesignVersion.version.desc()).first()


def _cached(tmp_path, design_id: str, version: int = 1) -> dict[str, bytes]:
    vd = tmp_path / "meshes" / design_id / f"v{version}"
    return {p.name: p.read_bytes() for p in sorted(vd.glob("*.stl"))} if vd.is_dir() else {}


def _cold_start(tmp_path) -> None:
    """새 인스턴스처럼: 메시 캐시와 조립 항목 템플릿·형상 캐시를 비운다."""
    shutil.rmtree(tmp_path / "meshes", ignore_errors=True)
    compose.composed_template.cache_clear()
    module_template._part_bounds_cached.cache_clear()


@pytest.fixture
def revalidations(monkeypatch) -> list[int]:
    calls: list[int] = []
    original = design_service.revalidate

    def spy(items, ctx):
        calls.append(len(items))
        return original(items, ctx)

    monkeypatch.setattr(design_service, "revalidate", spy)
    return calls


@pytest.mark.parametrize("prompt", list(CASES))
def test_stored_design_rebuilds_byte_identically_and_exports_each_print_part(tmp_path, monkeypatch, revalidations,
                                                                             prompt):
    """시리안 햄스터(설계 예시의 드워프는 test_geometry_drift 가 본다): 저장한 파일 해시 = 캐시를 비우고 다시 만든 파일,
    조립 해석기를 다시 부르지 않고, 다시 검증하지 않으며, STL 은 출력 파트마다 파일 하나, 3MF 도 내려받힌다."""
    ids, joins, print_keys, _ = CASES[prompt]
    with TestClient(create_app(settings(tmp_path))) as c:
        hid = create_habitat(c, {"width_mm": CAGE.width_mm, "depth_mm": CAGE.depth_mm, "height_mm": CAGE.height_mm},
                             size="syrian")
        r = c.post("/designs", json={"habitat_id": hid, "prompt": prompt})
        assert r.status_code == 201, r.text
        d = r.json()
        cur = d["current"]
        assert cur["validation"]["passed"], cur["validation"]
        [it] = cur["items"]
        assert [p["id"] for p in it["assembly"]["parts"]] == ids
        assert [(f"{j['to']}", j["part"], j["mount"], j["passage"]) for j in it["assembly"]["joins"]] == [
            (pa.split(".")[0], ch.split(".")[0], m, ps) for pa, ch, m, ps in joins]
        assert [p["key"] for p in it["parts"]] == print_keys

        row = _version_row(c)
        assert row.geometry["fingerprint"] == geometry_fingerprint(row.items, c.app.state.rules.printing)
        files = _cached(tmp_path, d["id"])
        assert set(files) == ({"world_0.stl", "print_0.stl"} | {f"print_0_{k}.stl" for k in print_keys[1:]}) \
            == set(row.geometry["files"])
        assert all(row.geometry["files"][n] == hashlib.sha256(b).hexdigest() for n, b in files.items())
        # 고친 명세의 at 은 실제로 붙은 면 (옮겨 단 연결도)
        [eff] = row.effective_spec["items"]
        faces = row.items[0]["assembly"]["faces"]
        assert [x["at"] for x in eff["connections"]] == [faces[x["part"]] for x in eff["connections"]]

        r = c.get(f"/designs/{d['id']}/export?format=stl")
        exported = exported_parts(r)
        assert sorted(exported) == sorted(f"part1_assembly_{k}.stl" for k in print_keys)

        def no_resolve(*a, **k):
            raise AssertionError("다시 만들 때 조립 해석기를 부르면 안 됩니다")

        monkeypatch.setattr(compose, "resolve", no_resolve)
        monkeypatch.setattr(engine, "resolve", no_resolve)
        _cold_start(tmp_path)
        assert exported_parts(c.get(f"/designs/{d['id']}/export?format=stl")) == exported
        assert _cached(tmp_path, d["id"]) == files
        assert revalidations == []
        assert c.get(f"/designs/{d['id']}/export?format=3mf").status_code == 200
        assert c.get(it["mesh_url"]).status_code == 200


def test_revision_removes_a_part_and_the_new_version_rebuilds(tmp_path, revalidations):
    """수정 요청으로 부품을 빼면 그 연결도 빠진 새 버전이 통과하고, 그 버전도 캐시를 비운 뒤 같은 바이트로 다시 만든다."""
    with TestClient(create_app(settings(tmp_path))) as c:
        hid = create_habitat(c, {"width_mm": 1000, "depth_mm": 600, "height_mm": 400}, size="dwarf")
        d = c.post("/designs", json={"habitat_id": hid, "prompt": EXAMPLE_KO}).json()
        r = c.post(f"/designs/{d['id']}/revise", json={"prompt": "물병 거치대는 빼줘"})
        assert r.status_code == 201, r.text
        cur = r.json()["current"]
        assert cur["validation"]["passed"], cur["validation"]
        [it] = cur["items"]
        assert [p["id"] for p in it["assembly"]["parts"]] == ["hide", "bowl", "tube", "hide2"]
        assert [p["key"] for p in it["parts"]] == ["body", "bowl", "tube", "hide2"]
        version = cur["version"]
        files = _cached(tmp_path, d["id"], version)
        assert files
        _cold_start(tmp_path)
        assert c.get(f"/designs/{d['id']}/export?format=stl&version={version}").status_code == 200
        assert _cached(tmp_path, d["id"], version) == files
        assert revalidations == []


# ── 성능 예산 ─────────────────────────────────────────────


_FIVE = {
    "parts": [{"id": "hide", "template": "hideout", "params": {}}, {"id": "bowl", "template": "bowl_holder", "params": {}},
              {"id": "bottle", "template": "bottle_stand", "params": {}}, {"id": "tube", "template": "tunnel", "params": {}},
              {"id": "hide2", "template": "hideout", "params": {}}],
    "connections": [{"part": "bowl", "to": "hide", "at": "right"}, {"part": "bottle", "to": "hide", "at": "left"},
                    {"part": "tube", "to": "hide", "at": "front"}, {"part": "hide2", "to": "tube", "at": "free_end"}],
}
# 두 번째 은신처에도 그릇 받침·램프를 끼우고 뒤 출입구에 터널을 하나 더 (부품 8개 = MAX_PARTS)
_EIGHT = {
    "parts": _FIVE["parts"] + [{"id": "bowl2", "template": "bowl_holder", "params": {}},
                               {"id": "ramp", "template": "ramp", "params": {}},
                               {"id": "tube2", "template": "tunnel", "params": {}}],
    "connections": _FIVE["connections"] + [{"part": "bowl2", "to": "hide2", "at": "right"},
                                           {"part": "ramp", "to": "hide2", "at": "left"},
                                           {"part": "tube2", "to": "hide2", "at": "back"}],
}
BUDGET_S = {5: 10.0, 8: 30.0}


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("n,body", [(5, _FIVE), (8, _EIGHT)], ids=["5parts", "8parts"])
def test_rule_issues_and_engine_stay_within_the_budget(rules, n, body, size):
    ctx = _ctx(rules, size, Cage(1200, 700, 500))
    req = AssemblyRequest.model_validate(body)
    out = compose.resolve(req, None, ctx.fit_ctx)
    assert not isinstance(out, Issue), out.message_ko
    resolved, params, _ = out
    assert len(resolved.parts) == n
    t = ComposedTemplate(resolved)  # 캐시를 거치지 않은 새 템플릿: 형상·검사 캐시가 비어 있다
    p, adj = clamp_params(t, compose.assembly_params(t, params), ctx.fit_ctx, max_passes=compose.ASSEMBLY_MAX_PASSES)
    assert not [i for i in adj if i.severity == Severity.error]
    start = time.perf_counter()
    problems = t.rule_issues(p, ctx.rule_ctx)
    rule_s = time.perf_counter() - start
    assert problems == []

    compose.composed_template.cache_clear()
    start = time.perf_counter()
    res = run_engine([ItemSpec("assembly", {x["id"]: x["params"] for x in body["parts"]}, assembly=req)], ctx)
    engine_s = time.perf_counter() - start
    assert res.report.passed, _not_info(res.report)
    print(f"\n[budget] {n} parts {size}: rule_issues {rule_s:.1f}s, run_engine {engine_s:.1f}s")
    assert rule_s <= BUDGET_S[n], f"rule_issues {rule_s:.1f}s > {BUDGET_S[n]}s"
    assert engine_s <= BUDGET_S[8], f"run_engine {engine_s:.1f}s > {BUDGET_S[8]}s"
