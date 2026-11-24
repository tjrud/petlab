"""부품 검증기의 DSL 연결 (설계 §7.2 S/L 검사, §7.8 변이 묶음).

- tests/data/library_bad/*.json: 일부러 망가뜨린 초안. 파일마다 "_expect"(걸려야 하는 검사 id)가 있고, 검증기는 정확히 그
  검사로 실패해야 한다. "_also" 는 같은 문제를 다시 알리는 검사만 적는다: 엔진의 런타임 경고(G10), 바닥과의 틈이 뚫린
  구멍으로도 보이는 경우(G13). "_profile" 이 full 이면
  최솟값·최댓값 변형이 있어야 드러나는 문제다.
- tests/data/library/*.json (§6 초안 세 개)은 정적 검사가 깨끗하고 `verify --quick` 을 통과한다.
- 정적 검사(check)는 형상 커널 없이 1초 안에 끝난다.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.library.verify.dsl_checks import (
    PLUG_DOOR_WALL_MIN_MM,
    mock_part_ids,
    static_checks,
    verify_draft,
)

BACKEND = Path(__file__).resolve().parents[1]
GOOD = BACKEND / "tests" / "data" / "library"
BAD = BACKEND / "tests" / "data" / "library_bad"
GOOD_NAMES = ("tunnel_junction", "deck_platform", "litter_tray")

# 설계 §7.8 의 표: 파일 → 걸려야 하는 검사
MUTATIONS = {
    "thin_wall": "G06", "upright_roof": "G05", "trap_slot": "G08", "low_deck": "G08", "lying_min_wall": "G06",
    "lying_climb": "G09", "envelope_off": "L06", "coplanar_cut": "L04", "touching_union": "L03",
    "rule_in_geometry": "L02", "anchor_off_surface": "C02", "mount_over_air": "C03", "door_into_block": "C04",
    "bed_overflow": "G04", "infeasible_defaults": "P1", "div_zero_extreme": "P4", "tippy": "G11",
    "tube_door": "S04", "hangul_en": "S06", "schema_bloat": "R01", "unreachable_step": "L05",
    "bad_choice_literal": "S02", "small_hole": "G13",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_mutation_files_match_the_design_table():
    files = {p.stem: _load(p) for p in sorted(BAD.glob("*.json"))}
    assert set(files) == set(MUTATIONS)
    for name, data in files.items():
        assert data["_expect"] == MUTATIONS[name], name
        assert set(data.get("_also", [])) <= {"G10", "G13"}, name  # 같은 문제를 다시 알리는 검사만


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_mutation_fails_with_exactly_its_check(name):
    data = _load(BAD / f"{name}.json")
    assert data["family"] == name  # 초안 파일 이름 = family (L10)
    run = verify_draft(data, key=f"{name}@v1", stem=name, profile=data.get("_profile", "quick"),
                       jobs=1, subprocess=False, trials=False)
    ids = {r.id for r in run.failures}
    assert data["_expect"] in ids, (name, ids, [r.message for r in run.failures][:5])
    assert ids <= {data["_expect"], *data.get("_also", [])}, (name, sorted(ids),
                                                              [f"{r.id}: {r.message}" for r in run.failures][:5])
    assert not run.ok
    bad_sizes = {"/".join(r.variant.split("/")[:2]) for r in run.failures if r.variant and r.variant.count("/") >= 2}
    assert not any(f"{sp}/{s}" in bad_sizes for sp, sizes in run.verified_for.items() for s in sizes)


def test_expect_keys_are_stripped_before_the_schema_check():
    data = _load(BAD / "hangul_en.json")
    ids = {r.id for r in static_checks(data) if not r.ok}
    assert "S01" not in ids and ids == {"S06"}


@pytest.mark.parametrize("name", GOOD_NAMES)
def test_section6_drafts_are_statically_clean(name):
    raw = (GOOD / f"{name}.json").read_bytes()
    res = static_checks(json.loads(raw), stem=name, raw_size=len(raw))
    assert [r for r in res if not r.ok] == []
    ids = {r.id for r in res}
    assert {f"S0{n}" for n in range(1, 9)} <= ids
    assert {f"L{n:02d}" for n in range(2, 13)} <= ids
    assert "L01" not in ids  # 식 컴파일은 S02 가 맡는다


@pytest.mark.parametrize("name", GOOD_NAMES)
def test_section6_drafts_pass_quick_verify(name):
    data = _load(GOOD / f"{name}.json")
    t0 = time.perf_counter()
    # key 는 라이브러리의 다음 버전 (게시된 tunnel_junction@v1 이 있으면 @v2: 등록된 부품과 겹치지 않는다)
    run = verify_draft(data, stem=name, profile="quick")
    assert run.ok, [f"{r.id} {r.variant}: {r.message}" for r in run.failures][:10]
    assert time.perf_counter() - t0 < 90  # §15 verify --quick 예산
    assert run.verified_for == {"hamster": ["dwarf", "syrian"]}
    assert set(run.golden) == {"hamster/dwarf/default", "hamster/syrian/default"}
    for g in run.golden.values():
        assert {"print_0.stl", "world_0.stl"} <= set(g["files"])
    assert run.schema["chars_added"] <= 2_300
    ran = {r.id for r in run.results}
    assert {"S01", "S02", "P1", "G02", "G05", "G12", "C02", "T01", "R01", "R02", "R03", "R04"} <= ran


def test_static_errors_stop_before_the_kernel():
    data = _load(BAD / "coplanar_cut.json")
    run = verify_draft(data, key="coplanar_cut@v1")
    assert run.profile == "static"
    assert {r.id for r in run.results} <= {f"S0{n}" for n in range(1, 9)} | {f"L{n:02d}" for n in range(1, 13)}


def test_schema_errors_are_s01_with_pointers():
    data = _load(GOOD / "litter_tray.json")
    data["params"]["lip_height_mm"]["mn"] = 3
    data.pop("print")
    res = [r for r in static_checks(data) if not r.ok]
    assert {r.id for r in res} == {"S01"}
    paths = {r.path for r in res}
    assert "/print" in paths and "/params/lip_height_mm/mn" in paths
    assert all(r.message.startswith("DSL01") for r in res)


def test_reference_and_name_checks():
    data = _load(GOOD / "tunnel_junction.json")
    data["door_fields"] = ["layout"]  # door_shape 가 문 모양을 바꾸는데 빠졌다
    data["size_fields"] = ["size_mm", "door_width_mm"]  # 출입구 폭은 크기 맞춤 필드가 아니다
    data["part_id"] = "hide"  # 모의 해석기의 은신처 id
    data["family"] = "hideout"  # 코드 부품 key
    res = [r for r in static_checks(data) if not r.ok]
    s03 = [r.message for r in res if r.id == "S03"]
    assert any("door_shape" in m and "door_fields" in m for m in s03)
    assert any("door_width_mm" in m and "door width" in m for m in s03)
    s05 = [r.message for r in res if r.id == "S05"]
    assert any("code part key" in m for m in s05) and any("'hide'" in m for m in s05)


def test_door_wall_and_width_bounds():
    data = _load(GOOD / "tunnel_junction.json")
    data["params"]["wall_thickness_mm"]["min"] = 2.0
    data["params"]["door_width_mm"]["max"] = 140
    msgs = [r.message for r in static_checks(data) if not r.ok and r.id == "S04"]
    assert any("below 2.3 mm" in m for m in msgs)
    assert any("tunnel range" in m for m in msgs)


def test_i18n_placeholders_and_desc_heads():
    data = _load(GOOD / "deck_platform.json")
    data["constraints"][0]["reason"]["en"] = "The deck must be thick"
    data["params"]["depth_mm"]["desc"]["en"] = ". depth"
    msgs = [(r.path, r.message) for r in static_checks(data) if not r.ok and r.id == "S06"]
    assert any(p == "/constraints/0/reason/en" and "placeholders" in m for p, m in msgs)
    assert any(p == "/params/depth_mm/desc/en" for p, _ in msgs)


def test_limits_count_repeat_expansion():
    data = _load(GOOD / "deck_platform.json")
    data["params"]["leg_count"] = {"type": "integer", "default": 2, "min": 1, "max": 64,
                                   "desc": {"ko": "다리 개수", "en": "number of legs"}}
    data["body"].append({"op": "box", "size": [3, 3, 3], "at": [0, 0, 0], "repeat": {"i": "leg_count", "j": 9}})
    res = [r for r in static_checks(data) if not r.ok and r.id == "S07"]
    assert res and res[0].value == 64 * 9 + 3


def test_plug_wall_constant_matches_compose():
    from app.modules.compose import PLUG_DOOR_WALL_MIN_MM as compose_min

    assert compose_min == pytest.approx(PLUG_DOOR_WALL_MIN_MM)


def test_mock_part_ids_are_read_without_importing_the_mock():
    from app.llm.mock import PART_IDS

    assert mock_part_ids() == frozenset(PART_IDS.values())


def test_check_is_kernel_free_and_fast():
    code = (
        "import json, sys, time\n"
        "t0 = time.perf_counter()\n"
        "from app.library.verify.dsl_checks import static_checks\n"
        "for n in ('tunnel_junction', 'deck_platform', 'litter_tray'):\n"
        "    d = json.load(open(f'tests/data/library/{n}.json'))\n"
        "    assert all(r.ok for r in static_checks(d, stem=n)), n\n"
        "heavy = sorted(m for m in sys.modules if m.split('.')[0] in "
        "('build123d', 'OCP', 'trimesh', 'shapely', 'numpy', 'anthropic'))\n"
        "print(json.dumps({'heavy': heavy, 'seconds': time.perf_counter() - t0}))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["heavy"] == []
    assert res["seconds"] < 3.0  # 세 파일 (파일 하나 < 1 s)


# ── S07: 고체 수 한도는 필드 범위 전체에서, 만들 때도 ──


def _ribbed_deck(peak: str) -> dict:
    """반복 횟수가 정수 필드의 가운데 값에서 가장 큰 발판 (끝값에서는 둘)."""
    d = _load(GOOD / "deck_platform.json")
    d["params"]["rib_count"] = {"type": "integer", "default": 0, "min": 0, "max": 63,
                                "desc": {"ko": "갈빗대 수", "en": "rib count"}}
    for k in range(8):
        d["body"].append({"op": "box", "size": [1.5, "D - 2", 2], "repeat": {"i": peak},
                          "at": ["-W / 2 + t + 1 + i * (W - 2 * t - 2) / 64", 0, f"H - dt - 1.5 - {k} * 0.01"]})
    return d


def test_s07_bounds_a_non_monotone_repeat_over_the_whole_integer_range():
    from app.library.verify.dsl_checks import SOLIDS_MAX

    bad = [r for r in static_checks(_ribbed_deck("64 - 2 * abs(rib_count - 32)"), stem="deck_platform")
           if r.id == "S07" and not r.ok]
    assert len(bad) == 1 and bad[0].value > SOLIDS_MAX and "rib_count=32" in bad[0].message
    ok = [r for r in static_checks(_ribbed_deck("min(rib_count, 8)"), stem="deck_platform") if r.id == "S07"]
    assert ok and all(r.ok for r in ok)


def test_runtime_solid_cap_refuses_any_params_over_the_limit():
    from app.library.errors import DslError
    from app.library.template import SOLIDS_MAX, make_template
    from app.library.verify import dsl_checks

    assert dsl_checks.SOLIDS_MAX == SOLIDS_MAX
    t = make_template(_ribbed_deck("64 - 2 * abs(rib_count - 32)"), key="deck_platform@v9")
    with pytest.raises(DslError) as e:
        t.build(t.Params.model_validate({**t.Params().model_dump(), "rib_count": 32}))
    assert e.value.code == "DSL006" and str(SOLIDS_MAX) in e.value.message
