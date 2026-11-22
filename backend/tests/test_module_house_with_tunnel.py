"""조립 모듈 house_with_tunnel (터널이 이어진 집): 집 오른쪽 연결부에 뾰족 아치 터널을 끼움 결합으로 잇는다.

기본값·크기 끝값을 햄스터 크기마다 자동 보정한 값에서 형상·규칙·출력 파트를 확인하고, 끼움 턱의 틈새와
모의 해석기 연결을 본다. 라이브러리 전체 검사(tests/test_modules.py)에 더해 이 모듈만의 설계 의도를 고정한다.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from build123d import Pos

from app.domain import Cage
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.modules.assembly import PLUG_CLEARANCE_MM, anchor_frame, place_parts
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.base import RuleContext
from app.templates.registry import get_template
from app.validation.autofix import clamp_params
from app.validation.checks import overhang_area
from app.validation.report import Severity

KEY = "house_with_tunnel"
HAMSTERS = ["dwarf", "syrian"]


def ctx(rules, size: str) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size),
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def fixed(rules, size: str, **over):
    """엔진처럼 자동 보정한 파라미터."""
    t = get_template(KEY)
    p, _ = clamp_params(t, t.Params.model_validate({**t.Params().model_dump(), **over}), ctx(rules, size))
    return t, p


def _size_ends(t, end: str) -> dict:
    return {d.name: getattr(d, end) for d in t.defn.params if d.name in t.defn.size_params}


def _volume(a, b) -> float:
    inter = a & b
    return float(inter.volume) if inter is not None else 0.0


@pytest.mark.parametrize("size", HAMSTERS)
def test_defaults_pass_the_engine(rules, size):
    """넓은 케이지에 기본값으로 하나: 오류·경고 없음 (끼움 턱 1.5mm 는 메시 두께 측정에서 빠진다, PrintPart.thin_ok)."""
    t = get_template(KEY)
    ectx = EngineContext(cage=Cage(1000, 600, 500), species="hamster", size=size, count=1, rules=rules)
    res = run_engine([ItemSpec(template=KEY, params=t.Params().model_dump())], ectx)
    assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]
    warnings = [i for i in res.report.issues if i.severity == Severity.warning]
    assert not warnings, [(i.code, i.message_ko) for i in warnings]
    assert res.items and res.items[0].placement is not None


@pytest.mark.parametrize("size", HAMSTERS)
def test_defaults_build_one_closed_body_and_have_no_rule_issues(rules, size):
    t, p = fixed(rules, size)
    assert t.rule_issues(p, ctx(rules, size)) == []
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    # 드나드는 곳: 집 앞 출입구 + 터널 바깥 끝 (터널을 끼운 연결부는 빠진다)
    f = t.features(p)
    assert f.entrance_count == 2
    assert set(f.access_sides) == {"front", "right"}


def _cases():
    for size in HAMSTERS:
        for roof in ("pitched", "flat"):
            yield size, {"roof": roof}
            yield size, {"roof": roof, "_ends": "min"}
            yield size, {"roof": roof, "_ends": "max"}


@pytest.mark.parametrize("size,over", list(_cases()))
def test_print_parts_fit_and_do_not_intersect(rules, size, over):
    """기본값·크기 끝값(경사·평 지붕)에서 출력 파트마다 닫힌 한 덩어리, 서포트 없이 출력, 220×220×250 안,
    조립 위치에서 서로 겹치지 않는다. 경사 지붕은 본체·지붕 뚜껑·터널 셋, 평 지붕은 본체·터널 둘."""
    t = get_template(KEY)
    over = dict(over)
    end = over.pop("_ends", None)
    if end:
        over.update(_size_ends(t, end))
    t, p = fixed(rules, size, **over)
    assert t.rule_issues(p, ctx(rules, size)) == []
    bx, by, bz = rules.printing.build_volume_mm
    pps = t.print_parts(p)
    keys = {pp.key for pp in pps}
    assert keys == ({"body", "tube", "house_roof"} if p.roof == "pitched" else {"body", "tube"})
    for pp in pps:
        pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
        assert mesh_health(pm).ok and pm.body_count == 1, pp.key
        assert pm.bounds[0][2] == pytest.approx(0, abs=1e-6)
        assert overhang_area(pm, rules.printing.max_overhang_deg) <= rules.printing.overhang_area_tolerance_mm2, pp.key
        assert all(a <= b for a, b in zip(sorted(pm.extents[:2]), sorted([bx, by]))) and pm.extents[2] <= bz, \
            (pp.key, pm.extents)
    for a, b in itertools.combinations(pps, 2):
        assert _volume(a.part, b.part) < 1.0, (a.key, b.key)


def test_tunnel_prints_in_use_pose_with_the_spigot_sideways(rules):
    """뾰족 아치 터널은 사용 자세 그대로 출력한다 (끼움 턱이 옆(−X)을 본다)."""
    t, p = fixed(rules, "syrian")
    tube = next(pp for pp in t.print_parts(p) if pp.key == "tube")
    assert np.allclose(tube.rotation, np.eye(3))


@pytest.mark.parametrize("size", HAMSTERS)
def test_spigot_fits_the_port_hole_with_designed_play(rules, size):
    """끼움 턱과 넓힌 구멍 사이 틈새 PLUG_CLEARANCE_MM(0.2): 0.15mm 옮겨도 겹치지 않고 0.5mm 옮기면 걸린다.
    벽 쪽으로 0.5mm 밀면 터널 끝 고리가 연결부 플랜지 면에 걸린다 (끼움 턱이 구멍 바닥에 닿지 않고 끝 면으로 선다)."""
    t, p = fixed(rules, size)
    pps = {pp.key: pp.part for pp in t.print_parts(p)}
    parts, joins = t.expand(p)
    _, tt, u, n = anchor_frame(place_parts(parts, joins), "house", "right")
    body, tube = pps["body"], pps["tube"]
    assert _volume(body, tube) < 1.0
    for d in (tt, -tt, u):
        assert _volume(body, Pos(*(d * (PLUG_CLEARANCE_MM - 0.05))) * tube) < 1.0
        assert _volume(body, Pos(*(d * 0.5)) * tube) > 1.0
    assert _volume(body, Pos(*(-n * 0.5)) * tube) > 1.0


@pytest.mark.parametrize("size", HAMSTERS)
def test_tunnel_follows_the_species_entrance(rules, size):
    """출입구 폭·연결부·터널 내경이 한 파라미터에 묶여 종별 최소값으로 함께 올라가고, 터널 길이는 종별 기준 안으로 맞춘다."""
    s = rules.size_rules("hamster", size)
    t, p = fixed(rules, size, entrance_mm=50, tunnel_length_mm=200)
    need = max(s.entrance_min_diameter_mm, s.tunnel_min_inner_diameter_mm)
    assert p.entrance_mm == pytest.approx(need)
    parts, _ = t.expand(p)
    house, tube = parts[0].params, parts[1].params
    assert house.doors.width_mm == house.ports.diameter_mm == tube.inner_diameter_mm == pytest.approx(need)
    assert p.tunnel_length_mm <= s.tunnel_max_length_mm + 1e-9
    assert t.rule_issues(p, ctx(rules, size)) == []


@pytest.mark.parametrize("prompt,language", [
    ("터널 달린 집을 왼쪽에 놓아 주세요", "ko"),
    ("터널이 이어진 집 하나 만들어 줘", "ko"),
    ("A house with a tunnel in the left corner, please", "en"),
    ("터널이 붙은 집", "ko"),
    ("터널 연결된 집 만들어 줘", "ko"),
    # hideout_with_tunnel 의 'tunnel attached' 보다 긴 낱말이 이긴다
    ("a house with a tunnel attached", "en"),
])
@pytest.mark.parametrize("size", HAMSTERS)
def test_mock_interpreter_picks_the_module(rules, prompt, language, size):
    req = InterpretRequest(
        prompt=prompt, habitat=HabitatInfo("hamster", "햄스터", size, 1, Cage(1000, 600, 500)),
        size_rules=rules.size_rules("hamster", size), min_wall_mm=rules.min_wall_for("hamster", size),
        language=language, allowed_templates=rules.allowed_templates("hamster"),
    )
    assert KEY in req.allowed_templates
    spec = MockInterpreter().interpret(req).spec
    assert [it.template for it in spec.items] == [KEY]


def test_hideout_keywords_still_pick_the_hideout_module(rules):
    """'터널 달린 은신처'는 그대로 은신처 모듈이다 (집 모듈 낱말과 겹치지 않는다)."""
    req = InterpretRequest(
        prompt="터널 달린 은신처", habitat=HabitatInfo("hamster", "햄스터", "dwarf", 1, Cage(1000, 600, 500)),
        size_rules=rules.size_rules("hamster", "dwarf"), min_wall_mm=rules.min_wall_for("hamster", "dwarf"),
        allowed_templates=rules.allowed_templates("hamster"),
    )
    assert [it.template for it in MockInterpreter().interpret(req).spec.items] == ["hideout_with_tunnel"]


@pytest.mark.parametrize("size", HAMSTERS)
@pytest.mark.parametrize("cage_h", [230, 250])
def test_defaults_fit_a_low_cage(rules, size, cage_h):
    """기본값은 평 지붕 120mm: 깔짚을 깔아 높이가 250mm 쯤인 흔한 케이지에서도 오류가 없다
    (경사 지붕은 190mm 안팎이 필요해 고를 때만 높이를 올린다)."""
    t = get_template(KEY)
    assert t.Params().roof == "flat" and t.Params().height_mm == 120
    ectx = EngineContext(cage=Cage(1000, 500, cage_h), species="hamster", size=size, count=1, rules=rules)
    res = run_engine([ItemSpec(template=KEY, params=t.Params().model_dump())], ectx)
    assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]


def test_pitched_roof_raises_the_height(rules):
    from app.validation.autofix import clamp_params

    t = get_template(KEY)
    c = RuleContext(rules.size_rules("hamster", "syrian"), rules.min_wall_for("hamster", "syrian"), 1)
    p, _ = clamp_params(t, t.Params(roof="pitched"), c)
    assert p.height_mm > 180 and t.rule_issues(p, c) == []
