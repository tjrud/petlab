"""2단계(부품 라이브러리) 기준선 (T0): 2단계 작업 전 main(bd94114)에서 뽑은 형상 바이트·저장 기록을 고정한다.

2단계 작업(은신처 옆면 출입구, 조립 해석기 변경, 라이브러리 부품 등록, 지문 계산 변경)이 이미 저장된 설계를 바꾸지
않는지 확인한다. 값은 tests/data/golden/stage2_baseline.json 에 있고, 수정하지 않은 main 에서 이 모듈로 뽑았다:

    uv run python -m tests.test_stage2_baseline --write tests/data/golden/stage2_baseline.json

- builds: 템플릿 하나를 저장된 파라미터 그대로 build_item 으로 만든 메시 해시 (사용 자세·출력 자세·파트별).
  은신처는 출입구 2개, 필드 최솟값·최댓값, 돋을새김 무늬(파라미터·장식으로 정해지는 고정 씨앗), 골든 기본값.
- versions: 실제 저장 경로(run_engine → _version_records → _cache_files)로 만든 설계 버전 기록과 파일 해시.
  고정 데이터 8개(tests/data/compositions, 드워프·골든)와 은신처·2층 바깥 램프 집. 다시 만들 때는
  DesignService._ensure_meshes 를 그대로 쓰고, 조립 해석기(compose.resolve, engine.resolve)를 부르면 실패하게 한다.
- 저장된 조립 구조: ResolvedAssembly.stored()·digest()·geometry_digest() 가 그대로인지.
- 지문: 코드 부품 키·저장 기록의 geometry_fingerprint 와 그 계산에 쓰는 모듈 해시. 2단계는 SHARED_MODULES·
  ASSEMBLY_MODULES·은신처 밖의 템플릿 모듈을 바꾸지 않는다 (설계 문서 R1).
- 옛 은신처 파라미터의 연결 지점·면 필드·특징·제약 메시지 (옆면 출입구를 더해도 그대로여야 한다).

값을 다시 뽑는 일은 형상을 일부러 바꿀 때뿐이다. 2단계 작업 중에 이 테스트가 깨지면 저장된 설계가 바뀐 것이다.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

GOLDEN_PATH = Path(__file__).parent / "data" / "golden" / "stage2_baseline.json"
FIXTURES = Path(__file__).parent / "data" / "compositions"
BASE_COMMIT = "bd94114"

# 고정 데이터 조립은 넉넉한 케이지에 놓는다 (배치·축소 보정이 형상을 바꾸지 않게)
ROOMY_CAGE = (1000.0, 600.0, 400.0)
SIZES = ("dwarf", "syrian")
# 무늬 장식 (돋을새김, 바깥 벽 전부). 씨앗은 decor_seed(템플릿, 파라미터, 장식) 로 정해진다
RELIEF_DECOR = {"kind": "pattern", "pattern": "dots", "density": 2, "direction": 0, "depth_mm": 0.6,
                "face": "walls", "mode": "relief"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stl_digest(mesh) -> str:
    return sha(mesh.export(file_type="stl"))


# ── 기준선 항목 정의 (뽑을 때와 검사할 때 같이 쓴다) ──────────────────────

def _build_cases(rules) -> list[dict[str, Any]]:
    """build_item 으로 바로 만드는 항목: (id, 템플릿, 파라미터, 장식, 종/크기). 파라미터는 저장된 형태(model_dump)."""
    from app.templates.registry import get_template

    hide = get_template("hideout")
    dwarf, syrian = rule_ctx(rules, "dwarf"), rule_ctx(rules, "syrian")
    d_dump = hide.default_params(dwarf).model_dump(mode="json")
    cases = [
        ("hideout/plain", "hideout", hide.Params().model_dump(mode="json"), None, "dwarf"),
        ("hideout/dwarf_default", "hideout", d_dump, None, "dwarf"),
        ("hideout/dwarf_count2", "hideout", {**d_dump, "entrance_count": 2}, None, "dwarf"),
        ("hideout/syrian_default", "hideout", hide.default_params(syrian).model_dump(mode="json"), None, "syrian"),
        ("hideout/syrian_count2", "hideout",
         {**hide.default_params(syrian).model_dump(mode="json"), "entrance_count": 2}, None, "syrian"),
        # 필드 최솟값: 가로·세로 60, 출입구 25, 벽 1 (규칙 보정 없이 만들 수 있는 가장 작은 은신처)
        ("hideout/field_min", "hideout",
         {"width_mm": 60.0, "depth_mm": 60.0, "height_mm": 50.0, "entrance_diameter_mm": 25.0, "entrance_count": 1,
          "vent_count": 0, "vent_diameter_mm": 2.0, "wall_thickness_mm": 1.0}, None, "dwarf"),
        ("hideout/field_min_count2", "hideout",
         {"width_mm": 60.0, "depth_mm": 60.0, "height_mm": 50.0, "entrance_diameter_mm": 25.0, "entrance_count": 2,
          "vent_count": 1, "vent_diameter_mm": 2.0, "wall_thickness_mm": 1.0}, None, "dwarf"),
        # 드워프 규칙 안에서 가로·세로를 가장 작게 (출입구 50, 벽 2.4)
        ("hideout/dwarf_min_footprint", "hideout",
         {"width_mm": 60.0, "depth_mm": 60.0, "height_mm": 60.0, "entrance_diameter_mm": 50.0, "entrance_count": 2,
          "vent_count": 6, "vent_diameter_mm": 4.0, "wall_thickness_mm": 2.4}, None, "dwarf"),
        ("hideout/field_max", "hideout",
         {"width_mm": 350.0, "depth_mm": 350.0, "height_mm": 250.0, "entrance_diameter_mm": 150.0, "entrance_count": 2,
          "vent_count": 30, "vent_diameter_mm": 10.0, "wall_thickness_mm": 8.0}, None, "syrian"),
        ("hideout/dwarf_relief", "hideout", d_dump, RELIEF_DECOR, "dwarf"),
        ("house/two_floor_external", "house", _two_floor_house(rules), None, "dwarf"),
        ("cave/default", "cave", get_template("cave").Params().model_dump(mode="json"), None, None),
        ("bowl_holder/dwarf_default", "bowl_holder",
         get_template("bowl_holder").default_params(dwarf).model_dump(mode="json"), None, "dwarf"),
        ("bottle_stand/syrian_default", "bottle_stand",
         get_template("bottle_stand").default_params(syrian).model_dump(mode="json"), None, "syrian"),
    ]
    return [{"id": i, "template": k, "params": p, "decor": dec, "size": s} for i, k, p, dec, s in cases]


def _two_floor_house(rules) -> dict:
    """드워프 기본 집을 2층 바깥 램프로 (높이는 2층이 들어가도록)."""
    from app.templates.registry import get_template

    t = get_template("house")
    p = t.default_params(rule_ctx(rules, "dwarf")).model_dump(mode="json")
    p["floors"] = {**p["floors"], "count": 2, "climb": "external_ramp", "level_height_mm": 110.0}
    p["height_mm"] = 220.0
    return t.Params.model_validate(p).model_dump(mode="json")


def _version_cases(rules) -> list[dict[str, Any]]:
    """실제 저장 경로로 만드는 설계 버전: 고정 데이터 8개 × 드워프·골든, 은신처(무늬 포함), 2층 바깥 램프 집."""
    from app.templates.registry import get_template

    cases: list[dict[str, Any]] = []
    for path in sorted(FIXTURES.glob("*.json")):
        for size in SIZES:
            cases.append({"id": f"fixture/{path.stem}/{size}", "size": size, "count": 1,
                          "source": {"fixture": path.stem}})
    hide = get_template("hideout")
    for size in SIZES:
        p = hide.default_params(rule_ctx(rules, size)).model_dump(mode="json")
        cases.append({"id": f"hideout/count2_relief/{size}", "size": size, "count": 2,
                      "source": {"item": {"template": "hideout", "params": p, "decor": RELIEF_DECOR}}})
    cases.append({"id": "house/two_floor_external/dwarf", "size": "dwarf", "count": 1,
                  "source": {"item": {"template": "house", "params": _two_floor_house(rules), "decor": None}}})
    return cases


def rule_ctx(rules, size: str | None, count: int = 1):
    """엔진과 같은 규칙 문맥 (EngineContext.rule_ctx). size None 이면 None (장식 없는 기본값)."""
    if size is None:
        return None
    return engine_ctx(rules, size, count).rule_ctx


def engine_ctx(rules, size: str, count: int = 1, cage: tuple[float, float, float] = ROOMY_CAGE):
    from app.domain import Cage
    from app.services.engine import EngineContext

    return EngineContext(cage=Cage(*cage), species="hamster", size=size, count=count, rules=rules)


def build_digests(rules, case: dict) -> dict[str, Any]:
    """저장된 파라미터를 읽는 경로(load_stored_params)로 만든 사용 자세·출력 자세·파트별 출력 메시 해시."""
    from app.domain import PlacementHint
    from app.services.engine import build_item
    from app.templates.registry import get_template

    t = get_template(case["template"])
    it = build_item(0, t, t.load_stored_params(dict(case["params"])), PlacementHint(), rules.printing,
                    case["decor"], rule_ctx(rules, case["size"]))
    out: dict[str, Any] = {"mesh": stl_digest(it.mesh), "print": stl_digest(it.print_mesh),
                           "parts": {p.key: stl_digest(p.print_mesh) for p in it.parts},
                           "decor_issues": sorted(i.code for i in it.decor_issues)}
    return out


def _spec_for(case: dict, rules):
    """기준선 버전의 해석기 출력 명세 (고정 데이터의 spec, 또는 항목 하나짜리 명세)."""
    from app.llm.spec import parse_spec

    src = case["source"]
    if "fixture" in src:
        raw = json.loads((FIXTURES / f"{src['fixture']}.json").read_text())["spec"]
    else:
        it = src["item"]
        raw = {"summary_ko": "기준선", "items": [{
            "template": it["template"], "params": it["params"], "decor": it["decor"],
            "placement": {"zone": "auto", "group": None, "rotation": None, "attach_to": None},
            "reason_ko": "기준선"}], "notes_ko": [], "missing_parts": []}
    return parse_spec(json.dumps(raw, ensure_ascii=False), rules.allowed_templates("hamster"))


def capture_version(rules, case: dict) -> dict[str, Any]:
    """DesignService._generate·_save_version 과 같은 경로로 버전 기록(items)과 파일 해시를 만든다."""
    from app.geometry.fingerprint import file_digest, geometry_fingerprint
    from app.llm.spec import to_item_specs
    from app.modules.structure import ResolvedAssembly
    from app.services.design_service import _cache_files, _version_records
    from app.services.engine import revalidate, run_engine

    ctx = engine_ctx(rules, case["size"], case["count"])
    spec = _spec_for(case, rules)
    engine = run_engine(to_item_specs(spec), ctx)
    items, _ = _version_records(spec.model_dump(mode="json"), engine)
    files = _cache_files(engine.items)
    assemblies = {}
    for it in items:
        if it.get("assembly") is not None:
            r = ResolvedAssembly.from_stored(it["assembly"])
            assemblies[str(it["index"])] = {"digest": r.digest(), "geometry_digest": r.geometry_digest(),
                                            "canonical": r.canonical()}
    re_report = revalidate(engine.items, ctx)
    return {
        **case,
        "cage": list(ROOMY_CAGE),
        "passed": engine.report.passed,
        "error_codes": sorted(i.code for i in engine.report.errors),
        "revalidate_error_codes": sorted(i.code for i in re_report.errors),
        "items": json.loads(json.dumps(items)),  # DB JSON 열에 저장되었다가 읽힌 형태
        "geometry": {"fingerprint": geometry_fingerprint(engine.items, rules.printing),
                     "files": {name: file_digest(data) for name, data in files.items()}},
        "assemblies": assemblies,
    }


# ── 옛 은신처의 연결 지점·특징·제약 ──────────────────────────────

HIDEOUT_CONTRACT_CASES = ("hideout/plain", "hideout/dwarf_default", "hideout/dwarf_count2", "hideout/syrian_default",
                          "hideout/syrian_count2", "hideout/dwarf_min_footprint", "hideout/field_max")
ANCHOR_NAMES = ("front", "back", "left", "right", "top", "bottom")


def _plain(v: Any) -> Any:
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {f.name: _plain(getattr(v, f.name)) for f in dataclasses.fields(v)}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, float):
        return round(v, 9)
    return v


def hideout_contract(rules, params: dict) -> dict[str, Any]:
    """저장된 은신처 파라미터의 연결 지점·면 필드·특징·외형과, 크기·마릿수별 제약(필드·범위·출처·메시지)."""
    from app.templates.registry import get_template

    t = get_template("hideout")
    p = t.load_stored_params(dict(params))
    anchors = t.anchors(p)
    out: dict[str, Any] = {
        "anchors": {n: _plain(anchors[n]) for n in ANCHOR_NAMES},
        "face_fields": {n: _plain(t.face_fields(p, n)) for n in ANCHOR_NAMES},
        "features": _plain(t.features(p)),
        "envelope": _plain(t.envelope(p)),
        "port_anchors": [n for n in ANCHOR_NAMES if t.port_profile(p, n) is not None],
        "constraints": {},
    }
    for size in SIZES:
        for count in (1, 2):
            cons = t.constraints(p, rule_ctx(rules, size, count))
            out["constraints"][f"{size}/{count}"] = [_plain(c) for c in cons]
    return out


# ── 지문 ────────────────────────────────────────────────────

def fingerprint_inputs() -> dict[str, Any]:
    """지문 계산에 들어가는 모듈 해시·라이브러리 버전·글꼴 해시."""
    from app.geometry import fingerprint as fp
    from app.templates.keys import TEMPLATE_MODULES

    modules = sorted(set(fp.SHARED_MODULES) | set(fp.ASSEMBLY_MODULES) | set(TEMPLATE_MODULES.values()))
    return {
        "shared_modules": list(fp.SHARED_MODULES),
        "assembly_modules": list(fp.ASSEMBLY_MODULES),
        "template_modules": dict(TEMPLATE_MODULES),
        "module_digests": {m: fp._module_digest(m) for m in modules},
        "libraries": dict(fp._library_versions()),
        "fonts": dict(fp._font_digests()),
    }


def code_key_fingerprints(rules) -> dict[str, str]:
    from app.geometry.fingerprint import geometry_fingerprint
    from app.templates.keys import TEMPLATE_MODULES

    out = {k: geometry_fingerprint([k], rules.printing) for k in sorted(TEMPLATE_MODULES)}
    out["*all"] = geometry_fingerprint(sorted(TEMPLATE_MODULES), rules.printing)
    return out


# ── 뽑기 ────────────────────────────────────────────────────

def capture(rules) -> dict[str, Any]:
    builds = [{**c, "digests": build_digests(rules, c)} for c in _build_cases(rules)]
    by_id = {b["id"]: b for b in builds}
    return {
        "about": "2단계 기준선 (tests/test_stage2_baseline.py). 수정하지 않은 main 에서 뽑았다.",
        "base_commit": BASE_COMMIT,
        "fingerprint_inputs": fingerprint_inputs(),
        "code_key_fingerprints": code_key_fingerprints(rules),
        "builds": builds,
        "versions": [capture_version(rules, c) for c in _version_cases(rules)],
        "hideout_contract": {i: {"params": by_id[i]["params"], **hideout_contract(rules, by_id[i]["params"])}
                             for i in HIDEOUT_CONTRACT_CASES},
    }


def main(argv: list[str]) -> int:
    from app.config import BACKEND_DIR
    from app.rules.loader import load_rules

    if len(argv) != 2 or argv[0] != "--write":
        print("usage: python -m tests.test_stage2_baseline --write OUT.json", file=sys.stderr)
        return 2
    data = capture(load_rules(BACKEND_DIR / "rules"))
    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(data['builds'])} builds, {len(data['versions'])} versions")
    return 0


# ── 테스트 ───────────────────────────────────────────────────

def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


GOLDEN = _golden() if GOLDEN_PATH.is_file() else {"builds": [], "versions": [], "hideout_contract": {}}
BUILDS = {b["id"]: b for b in GOLDEN["builds"]}
VERSIONS = {v["id"]: v for v in GOLDEN["versions"]}


def test_golden_covers_the_baseline() -> None:
    """설계 문서 §14 기준선: 은신처(출입구 2개·무늬·필드 최솟값·골든 기본값), 2층 바깥 램프 집, 고정 데이터 8개."""
    assert GOLDEN["base_commit"] == BASE_COMMIT
    assert {"hideout/dwarf_count2", "hideout/dwarf_relief", "hideout/field_min", "hideout/syrian_default",
            "house/two_floor_external"} <= set(BUILDS)
    fixtures = {v["source"]["fixture"] for v in VERSIONS.values() if "fixture" in v["source"]}
    assert len(fixtures) == 8
    assert all(f"fixture/{f}/{s}" in VERSIONS for f in fixtures for s in SIZES)
    # 무늬 항목은 실제로 장식이 얹힌 형상이다 (건너뛴 장식이 아니다)
    assert BUILDS["hideout/dwarf_relief"]["digests"]["decor_issues"] == []
    assert BUILDS["hideout/dwarf_relief"]["digests"]["mesh"] != BUILDS["hideout/dwarf_default"]["digests"]["mesh"]
    # 저장된 조립 기록은 모두 통과한 설계다 (다시 검증하는 경로가 실제로 쓰일 수 있는 기록)
    assert all(v["passed"] for v in VERSIONS.values()), [k for k, v in VERSIONS.items() if not v["passed"]]


@pytest.mark.parametrize("case_id", sorted(BUILDS))
def test_template_bytes_unchanged(rules, case_id: str) -> None:
    """저장된 파라미터(2단계 전 필드만) 그대로 다시 만든 메시가 같은 바이트다 (load_stored_params 경로)."""
    case = BUILDS[case_id]
    got = build_digests(rules, case)
    assert got == case["digests"], case_id


def _stored_version(case: dict):
    """DB 에서 읽은 것과 같은 (세션에 넣지 않은) 설계·버전 행."""
    from app.models import Design, DesignVersion, Habitat

    w, d, h = case["cage"]
    habitat = Habitat(species="hamster", size=case["size"], count=case["count"],
                      cage_width_mm=w, cage_depth_mm=d, cage_height_mm=h)
    design = Design(id="stage2baseline" + hashlib.sha1(case["id"].encode()).hexdigest()[:12], habitat=habitat)
    version = DesignVersion(version=1, items=json.loads(json.dumps(case["items"])),
                            geometry=json.loads(json.dumps(case["geometry"])), passed=case["passed"],
                            report={"issues": []})
    return design, version


@pytest.fixture
def no_resolver(monkeypatch):
    """저장된 조립 구조로만 다시 만든다: 조립 해석기를 부르면 실패. 조립 템플릿 캐시도 비운다."""
    from app.modules import compose
    from app.services import engine

    def no_resolve(*a, **k):
        raise AssertionError("다시 만들 때 조립 해석기를 부르면 안 됩니다")

    monkeypatch.setattr(compose, "resolve", no_resolve)
    monkeypatch.setattr(engine, "resolve", no_resolve)
    compose.composed_template.cache_clear()
    yield
    compose.composed_template.cache_clear()


@pytest.mark.parametrize("case_id", sorted(VERSIONS))
def test_stored_version_rebuilds_identically(rules, tmp_path, monkeypatch, no_resolver, case_id: str) -> None:
    """2단계 전에 저장된 버전: 캐시가 빈 새 인스턴스가 DesignService._ensure_meshes 로 다시 만든 파일이
    저장할 때 기록한 해시와 바이트 단위로 같다 (다시 검증 없이). 다시 만든 형상은 그때와 같은 오류로 다시 검증된다."""
    from app.services.design_service import DesignService
    from app.services.engine import revalidate

    case = VERSIONS[case_id]
    svc = DesignService(rules, interpreter=lambda: None, mesh_dir=tmp_path)  # type: ignore[arg-type, return-value]
    built = []
    original_rebuild = svc._rebuild

    def spy_rebuild(design, v, it):
        b = original_rebuild(design, v, it)
        built.append(b)
        return b

    def drift(design, v, changed):
        raise AssertionError(f"{case_id}: 다시 만든 파일이 저장된 해시와 다릅니다: {changed}")

    monkeypatch.setattr(svc, "_rebuild", spy_rebuild)
    monkeypatch.setattr(svc, "_log_drift", drift)
    design, version = _stored_version(case)
    d = svc._ensure_meshes(design, version)
    files = {p.name: sha(p.read_bytes()) for p in sorted(d.glob("*.stl"))}
    assert files == case["geometry"]["files"]
    # 같은 기록을 지금 코드로 다시 검증해도 그때와 같다 (저장된 설계가 새로 막히거나 풀리지 않는다)
    report = revalidate(sorted(built, key=lambda b: b.index), svc._engine_ctx(design.habitat))
    assert sorted(i.code for i in report.errors) == case["revalidate_error_codes"]


@pytest.mark.parametrize("case_id", sorted(VERSIONS))
def test_stored_records_read_back_unchanged(no_resolver, case_id: str) -> None:
    """저장된 기록을 읽는 경로 (형상 없이): 조립 구조의 stored()·digest()·geometry_digest() 가 그대로이고,
    저장된 파라미터를 읽으면 저장된 값이 그대로 나온다 (새 필드는 옛 형상을 내는 값으로만 더해진다)."""
    from app.modules.structure import ResolvedAssembly
    from app.templates.registry import template_for

    case = VERSIONS[case_id]
    for it in case["items"]:
        raw = it.get("assembly")
        if raw is not None:
            r = ResolvedAssembly.from_stored(raw)
            snap = case["assemblies"][str(it["index"])]
            assert r.stored() == raw
            assert r.canonical() == snap["canonical"]
            assert r.digest() == snap["digest"]
            assert r.geometry_digest() == snap["geometry_digest"]
        t = template_for(it)
        p = t.load_stored_params(json.loads(json.dumps(it["params"]))).model_dump(mode="json")
        if raw is not None:
            for pid, stored in it["params"].items():
                assert {k: p[pid][k] for k in stored} == stored, (case_id, pid)
        else:
            assert {k: p[k] for k in it["params"]} == it["params"], case_id


def _patched_fingerprint_inputs(monkeypatch) -> None:
    """지문 계산 입력(모듈 해시·라이브러리·글꼴)을 기준선 값으로 고정한다: 계산 방법만 비교한다."""
    from app.geometry import fingerprint as fp

    inputs = GOLDEN["fingerprint_inputs"]
    real = fp._module_digest
    monkeypatch.setattr(fp, "_module_digest", lambda name: inputs["module_digests"].get(name) or real(name))
    monkeypatch.setattr(fp, "_library_versions", lambda: tuple(inputs["libraries"].items()))
    monkeypatch.setattr(fp, "_font_digests", lambda: tuple(inputs["fonts"].items()))


def test_fingerprint_computation_unchanged(rules, monkeypatch) -> None:
    """같은 입력이면 지문이 같다: 코드 부품 키와 저장된 버전 기록 (조립 항목 포함). 지문 계산을 바꿔도
    코드 부품·저장된 기록의 값은 그대로여야 한다 (설계 문서 §9.4)."""
    from app.geometry.fingerprint import geometry_fingerprint

    _patched_fingerprint_inputs(monkeypatch)
    assert code_key_fingerprints(rules) == GOLDEN["code_key_fingerprints"]
    for vid, v in VERSIONS.items():
        assert geometry_fingerprint(v["items"], rules.printing) == v["geometry"]["fingerprint"], vid


def test_shared_and_assembly_modules_unchanged() -> None:
    """2단계는 공용 형상 코드(SHARED_MODULES), 조립 형상 코드(ASSEMBLY_MODULES), 은신처 밖의 템플릿 모듈을 바꾸지
    않는다 (설계 문서 R1). 바꾸면 저장된 모든 설계의 지문이 바뀐다."""
    from app.geometry import fingerprint as fp
    from app.templates.keys import TEMPLATE_MODULES

    inputs = GOLDEN["fingerprint_inputs"]
    assert list(fp.SHARED_MODULES) == inputs["shared_modules"]
    assert list(fp.ASSEMBLY_MODULES) == inputs["assembly_modules"]
    assert {k: v for k, v in TEMPLATE_MODULES.items() if k in inputs["template_modules"]} == inputs["template_modules"]
    frozen = sorted(m for m in inputs["module_digests"] if m != "app.templates.hideout")
    changed = [m for m in frozen if fp._module_digest(m) != inputs["module_digests"][m]]
    assert changed == []


def test_code_key_fingerprints_unchanged(rules) -> None:
    """은신처 밖의 코드 부품 키 지문은 2단계 전과 같다 (은신처는 옆면 출입구로 모듈이 바뀌어 지문이 바뀐다:
    뷰어 캐시 키와 로그에만 쓰인다, 설계 문서 F9)."""
    from app.geometry.fingerprint import geometry_fingerprint

    golden = GOLDEN["code_key_fingerprints"]
    for key, fp_value in golden.items():
        if key in ("hideout", "*all"):
            continue
        assert geometry_fingerprint([key], rules.printing) == fp_value, key


@pytest.mark.parametrize("case_id", sorted(GOLDEN["hideout_contract"]))
def test_legacy_hideout_contract_unchanged(rules, case_id: str) -> None:
    """2단계 전 은신처 파라미터: 연결 지점·면 필드·특징(출입구 라벨·출입 면·출입구 수)·외형·제약 메시지가 그대로다."""
    case = GOLDEN["hideout_contract"][case_id]
    got = hideout_contract(rules, case["params"])
    expected = {k: v for k, v in case.items() if k != "params"}
    for key, value in expected.items():
        assert got[key] == value, (case_id, key)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
