"""경사로 달린 은신처 (hideout_with_ramp): 은신처 오른쪽 옆면에 지붕까지 오르는 경사로(계단)를 슬라이드 결합으로 끼운 모듈.

라이브러리 공통 검사(tests/test_modules.py)에 더해 이 모듈의 설계 의도를 확인한다:
발판이 지붕과 같은 높이, 종별 기준(오르는 높이·경사·끼임 틈)을 기본값에서 보정 없이 통과,
따로 출력하는 경사로가 프린터에 들어가는 경사(limits), 도브테일 틈새, 밟는 지붕의 환기구 크기, 모의 해석기 낱말.
"""

from __future__ import annotations

import numpy as np
import pytest
from build123d import Pos

from app.domain import Cage, PlacementHint
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.modules.assembly import OVERLAP_MM, PLATE_MM
from app.services.engine import EngineContext, ItemSpec, build_item, run_engine
from app.templates.base import RuleContext
from app.templates.registry import get_template
from app.validation.autofix import clamp_params
from app.validation.checks import check_build_volume, overhang_area
from app.validation.report import Severity

KEY = "hideout_with_ramp"
SIZES = ["dwarf", "syrian"]


@pytest.fixture(scope="module")
def t():
    return get_template(KEY)


def rctx(rules, size: str) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size),
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def fixed(t, rules, size: str, **over):
    """엔진처럼 자동 보정한 파라미터."""
    p, _ = clamp_params(t, t.Params(**over), rctx(rules, size))
    return p


def test_defaults_build_one_watertight_body(t):
    p = t.Params()
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    # 경사로 꼭대기 = 은신처 지붕 높이
    assert m.bounds[1][2] == pytest.approx(p.height_mm, abs=1e-6)


@pytest.mark.parametrize("size", SIZES)
def test_defaults_pass_the_engine_without_fixes_or_warnings(t, rules, size):
    """API 와 같은 엔진(자동 보정·배치·검증)으로 넓은 케이지에 하나: 오류·경고 없고 보정할 값도 없다."""
    ectx = EngineContext(cage=Cage(1000, 600, 500), species="hamster", size=size, count=1, rules=rules)
    res = run_engine([ItemSpec(template=KEY, params=t.Params().model_dump())], ectx)
    assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]
    noisy = [i for i in res.report.issues if i.severity != Severity.info or i.code == "param_adjusted"]
    assert not noisy, [(i.code, i.message_ko) for i in noisy]
    assert res.items[0].placement is not None
    assert t.rule_issues(t.Params(), rctx(rules, size)) == []


@pytest.mark.parametrize("size", SIZES)
def test_two_hamsters_get_a_back_door(t, rules, size):
    """여러 마리면 은신처 출입구가 2개로 보정된다 (경사로는 옆면이라 뒷문과 겹치지 않는다)."""
    ectx = EngineContext(cage=Cage(1000, 600, 500), species="hamster", size=size, count=2, rules=rules)
    res = run_engine([ItemSpec(template=KEY, params=t.Params().model_dump())], ectx)
    assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]
    assert res.items[0].params.entrance_count == 2
    assert t.features(res.items[0].params).entrance_count == 2


def test_landing_is_flush_with_the_roof(t):
    """연결판이 지붕 높이까지 경사 없이 올라가고, 경사로 발판·연결판·지붕이 같은 높이."""
    p = t.Params()
    layout = t._layout(p)
    plan = next(iter(layout.plans.values()))
    assert plan.h == pytest.approx(p.height_mm) and plan.top == pytest.approx(p.height_mm)
    pps = {pp.key: pp for pp in t.print_parts(p)}
    assert set(pps) == {"body", "ramp"}
    for pp in pps.values():
        assert pp.part.bounding_box().max.Z == pytest.approx(p.height_mm, abs=1e-6)
    # 경사로 발판 끝면이 연결판 바깥면에 맞닿는다 (은신처 오른쪽 벽 + PLATE_MM − OVERLAP_MM)
    ramp_bb = pps["ramp"].part.bounding_box()
    face = p.width_mm / 2 + PLATE_MM - OVERLAP_MM
    assert ramp_bb.min.X < face  # 혀가 홈 속으로
    probe = part_to_mesh(pps["ramp"].part)
    assert probe.contains([[face + 0.5, 20.0, p.height_mm - 1]])[0]  # 혀가 없는 곳도 발판이 연결판에 닿는다
    assert not probe.contains([[face - 0.5, 20.0, p.height_mm - 1]])[0]


def _cases(t):
    """기본값, 크기 파라미터 끝값, 가장 높은·가장 완만한 요청, 계단."""
    sizes = {d.name: d for d in t.defn.params if d.name in t.defn.size_params}
    yield {}
    yield {n: d.min for n, d in sizes.items()}
    yield {n: d.max for n, d in sizes.items()}
    yield {"height_mm": 100}
    yield {"slope_deg": 15}
    yield {"steps": 4, "height_mm": 100}
    yield {"entrance_mm": 90, "entrance_count": 2}


@pytest.mark.parametrize("size", SIZES)
def test_print_parts_fit_the_printer_and_print_without_support(t, rules, size):
    """보정한 값마다 출력 파트(은신처 본체, 경사로)가 220×220×250 에 들어가고, 닫힌 한 덩어리이며, 오버행이 허용 면적 안.
    경사로는 도브테일이 세로로 서는 사용·뒤집기 자세로만 출력한다."""
    tol = rules.printing.overhang_area_tolerance_mm2
    for over in _cases(t):
        p = fixed(t, rules, size, **over)
        assert t.rule_issues(p, rctx(rules, size)) == [], over
        item = build_item(0, t, p, PlacementHint(), rules.printing)
        assert check_build_volume([item], rules.printing) == [], over
        for pp in t.print_parts(p):
            assert abs(pp.rotation[2, 2]) == pytest.approx(1.0), (over, pp.key)
            pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
            assert mesh_health(pm).ok and pm.body_count == 1, (over, pp.key)
            assert overhang_area(pm, rules.printing.max_overhang_deg) <= tol, (over, pp.key)


def test_slide_fit_has_play_but_locks_sideways(t):
    """조립 위치의 출력 파트는 겹치지 않고, 도브테일 혀는 홈 속에서 옆으로 0.25mm 남짓 놀다가 걸린다
    (밀어 내리는 방향(위아래)으로만 빠진다)."""
    p = t.Params()
    pps = {pp.key: pp.part for pp in t.print_parts(p)}
    body, ramp = pps["body"], pps["ramp"]

    def overlap(dy: float) -> float:
        inter = body & (Pos(0, dy, 0) * ramp)
        return float(inter.volume) if inter is not None else 0.0

    assert overlap(0.0) < 1e-3
    assert overlap(0.2) < 1e-3 and overlap(-0.2) < 1e-3
    assert overlap(0.6) > 1.0 and overlap(-0.6) > 1.0


def test_roof_vents_are_small_enough_to_walk_on(t, rules):
    """지붕을 밟고 다니므로 환기구는 두 크기 구분의 안전 틈새보다 작게 (상수 3mm)."""
    parts, _ = t.expand(t.Params())
    hide = next(q for q in parts if q.id == "hide")
    assert hide.params.vent_count > 0
    for size in SIZES:
        assert hide.params.vent_diameter_mm < rules.size_rules("hamster", size).gap_trap.safe_max_mm


@pytest.mark.parametrize("size", SIZES)
def test_ramp_follows_species_climb_rules(t, rules, size):
    s = rules.size_rules("hamster", size)
    p = fixed(t, rules, size, height_mm=100, steps=0)
    f = t.features(p)
    assert f.climb_height_mm == pytest.approx(p.height_mm) and p.height_mm <= s.max_climb_height_mm
    assert f.slope_deg <= s.max_ramp_angle_deg
    stairs = fixed(t, rules, size, steps=1)  # 한 단이면 단 높이를 넘으니 늘린다
    assert t.features(stairs).step_height_mm <= s.max_step_height_mm


def test_limits_keep_the_ramp_printable_and_on_the_face(t, rules):
    """높은 은신처는 경사를 올려 경사로를 프린터에 맞추고, 은신처 세로보다 넓은 경사로는 줄인다."""
    p = fixed(t, rules, "syrian", height_mm=100, slope_deg=15)
    assert p.slope_deg > 29 and p.slope_deg <= 30
    p = fixed(t, rules, "syrian", depth_mm=90, ramp_width_mm=120)
    assert p.ramp_width_mm == pytest.approx(90)
    assert t.rule_issues(p, rctx(rules, "syrian")) == []


def _req(rules, prompt: str, size: str = "syrian", language: str = "ko") -> InterpretRequest:
    entry = rules.species_entry("hamster")
    return InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo("hamster", entry.display_name, size, 1, Cage(800, 500, 400), habitat=entry.habitat),
        size_rules=rules.size_rules("hamster", size),
        min_wall_mm=rules.min_wall_for("hamster", size),
        language=language,
        allowed_templates=rules.allowed_templates("hamster"),  # 서비스처럼 조립 모듈 포함
    )


@pytest.mark.parametrize("prompt,language", [
    ("옥상으로 올라가는 경사로 달린 은신처 만들어줘", "ko"),
    ("지붕에 올라가는 은신처가 필요해요", "ko"),
    ("계단 달린 은신처", "ko"),
    ("A hideout with a ramp up to the roof please", "en"),
])
def test_mock_interpreter_picks_the_module(rules, prompt, language):
    spec = MockInterpreter().interpret(_req(rules, prompt, language=language)).spec
    assert [it.template for it in spec.items] == [KEY]
