"""옛 고정 조립 세트 8개를 옮긴 고정 데이터(tests/data/compositions)로 자유 조립의 안전 기준을 확인한다.

고정 데이터는 해석기 출력 꼴(조립 항목 하나)이다. 제품에 있는 메뉴나 프리셋이 아니라 시험 자료다: 손으로 만들었던
세트와 같은 결합으로 풀리는지는 tests/test_compose.py 가 보고, 여기서는 옛 세트별 테스트(test_module_*.py)가 지키던
안전 기준을 조립 해석기 → 자동 보정 → 규칙·형상 검사 길에서 다시 확인한다.

  - 공통: 햄스터 두 크기에서 기본값과 크기 끝값(옛 세트의 크기 범위)으로 닫힌 메시, 넓은 케이지에서 오류·경고 없음,
    출력 파트마다 닫힌 한 덩어리·서포트 없이·기준 프린터 안 (exceeds_build_volume 없음)
  - 그릇 받침: 도브테일 끼움 틈새, 그릇과 벽 사이 홈 5mm, 그릇보다 높은 은신처, 큰 그릇에 맞춰 넓히는 세로
  - 물병 거치대: 연결판이 지붕까지, 가장 낮은 거치대에도 틈이 없는 높이, 바닥판에 맞춰 넓히는 세로
  - 램프: 발판이 지붕(면 꼭대기)과 같은 높이, 종별 오르기 기준, 밟는 지붕의 환기구
  - 모래목욕통 램프: 발판이 턱 윗면, 출입 홈이 비어 있음
  - 터널(끼움): 출력 파트 셋(은신처·터널·은신처 2), 끼움 턱 틈새, 종별 최소 내경이 주인 값으로
  - 모의 해석기: 옛 세트를 고르던 요청이 같은 구조의 조립 항목이 되는지
  - 영어: 조립 구조물 이름·부품·출력 파트 이름과 해석기·자동 보정 안내가 모두 영어로 바뀌는지
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from build123d import Pos

from app.domain import Cage, PlacementHint
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.i18n import catalog
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.llm.spec import to_item_specs
from app.modules import compose
from app.modules.assembly import (
    OVERLAP_MM,
    PLATE_MM,
    PLUG_CLEARANCE_MM,
    SLOPE_RISE,
    anchor_frame,
    merge_features,
    place_parts,
)
from app.modules.composed import ComposedTemplate
from app.modules.structure import AssemblyRequest
from app.services.engine import EngineContext, ItemSpec, build_item, run_engine
from app.templates.base import RuleContext, TemplateParams
from app.templates.bottle_stand import total_height
from app.templates.bowl_holder import outer_radius
from app.templates.ramp import (
    BED_SLOPE_BASE_DEG,
    BED_SLOPE_PER_MM,
    TOP_LANDING_MM,
    run_length,
)
from app.templates.sand_bath import entry_width
from app.validation.autofix import clamp_params
from app.validation.checks import check_build_volume, overhang_area
from app.validation.report import Issue, Severity

FIXTURES = Path(__file__).parent / "data" / "compositions"
# 옛 세트를 옮긴 고정 데이터만 (library: 손으로 만든 결합 목록). 라이브러리 부품 조립(junction_network 등)은
# tests/test_compose.py·tests/test_library_parts.py 가 본다
KEYS = sorted(p.stem for p in FIXTURES.glob("*.json") if "library" in json.loads(p.read_text(encoding="utf-8")))
SIZES = ("dwarf", "syrian")
FACE = PLATE_MM - OVERLAP_MM  # 연결판 바깥면이 부모 옆면에서 나온 거리

# 옛 세트의 크기 파라미터 범위 (세트 JSON 의 size_params min·max 를 부품 파라미터로 옮긴 것).
# 부품 템플릿의 범위(은신처 최대 350mm 등)는 혼자 쓸 때도 프린터를 넘으니, 세트가 약속하던 범위에서 본다.
# 터널 길이 끝값은 세워 출력하는 끼움 터널이 출력 높이(250mm) 안에 드는 200mm 까지 (열린 문제: 그보다 긴 터널은 경고)
EXTREMES: dict[str, dict[str, dict[str, float]]] = {
    "dining_hideout": {"min": {"hide.width_mm": 90, "hide.depth_mm": 100},
                       "max": {"hide.width_mm": 200, "hide.depth_mm": 200}},
    "hideout_with_bottle": {"min": {"hide.width_mm": 100, "hide.depth_mm": 90, "bottle.base_width_mm": 80,
                                    "bottle.base_depth_mm": 80},
                            "max": {"hide.width_mm": 200, "hide.depth_mm": 200, "bottle.base_width_mm": 160,
                                    "bottle.base_depth_mm": 160}},
    "hideout_with_bowl": {"min": {"hide.width_mm": 90, "hide.depth_mm": 80},
                          "max": {"hide.width_mm": 200, "hide.depth_mm": 200}},
    "hideout_with_ramp": {"min": {"hide.width_mm": 80, "hide.depth_mm": 80, "ramp.width_mm": 50},
                          "max": {"hide.width_mm": 200, "hide.depth_mm": 200, "ramp.width_mm": 150}},
    "hideout_with_tunnel": {"min": {"hide.width_mm": 90, "hide.depth_mm": 80, "tube.length_mm": 80},
                            "max": {"hide.width_mm": 220, "hide.depth_mm": 200, "tube.length_mm": 200}},
    "house_with_tunnel": {"min": {"house.width_mm": 110, "house.depth_mm": 110, "tube.length_mm": 80},
                          "max": {"house.width_mm": 210, "house.depth_mm": 180, "tube.length_mm": 200}},
    "sand_bath_with_ramp": {"min": {"bath.width_mm": 206, "bath.depth_mm": 206},
                            "max": {"bath.width_mm": 220, "bath.depth_mm": 216}},
    "twin_hideouts": {"min": {"hide.width_mm": 100, "hide.depth_mm": 90, "hide2.width_mm": 100, "hide2.depth_mm": 90,
                              "tube.length_mm": 80},
                      "max": {"hide.width_mm": 200, "hide.depth_mm": 200, "hide2.width_mm": 200,
                              "hide2.depth_mm": 200, "tube.length_mm": 200}},
}
ENDS = ("default", "min", "max")

# 출입구가 있는 방(은신처·집)이 기준 부품인 고정 데이터
ROOMS = [k for k in KEYS if k != "sand_bath_with_ramp"]


# ── 고정 데이터 → 조립 항목 ──


def fixture(key: str) -> dict:
    return json.loads((FIXTURES / f"{key}.json").read_text(encoding="utf-8"))


def _set(values: dict, path: str, value: Any) -> None:
    *heads, last = path.split(".")
    for h in heads:
        values = values.setdefault(h, {})
    values[last] = value


def request(key: str, over: dict[str, Any] | None = None, *, named: bool = True) -> AssemblyRequest:
    """고정 데이터의 조립 항목. over: {"부품id.파라미터경로": 값} 으로 해석기 입력 파라미터를 바꾼다."""
    it = fixture(key)["spec"]["items"][0]
    parts = json.loads(json.dumps(it["parts"]))
    by_id = {p["id"]: p for p in parts}
    for path, v in (over or {}).items():
        pid, field = path.split(".", 1)
        _set(by_id[pid]["params"], field, v)
    return AssemblyRequest(parts=parts, connections=it["connections"], name_ko=it["name_ko"] if named else None)


def rctx(rules, size: str, count: int = 1) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), count,
                       printing_max_overhang_deg=rules.printing.max_overhang_deg,
                       min_feature_mm=rules.printing.min_feature_mm)


_SETTLED: dict[tuple, tuple[ComposedTemplate, TemplateParams, list[Issue]]] = {}


def settle(rules, key: str, size: str = "dwarf", count: int = 1, **over: Any
           ) -> tuple[ComposedTemplate, TemplateParams, list[Issue]]:
    """엔진과 같은 길: 해석(부품마다 보정 포함) → 조립 항목 템플릿 → 조립 제약으로 보정. 해석 오류면 실패.
    over 의 열쇠는 "부품id__파라미터" ("hide__depth_mm", 점 표기는 "house__roof__kind")."""
    cache_key = (key, size, count, tuple(sorted(over.items())))
    if cache_key not in _SETTLED:
        ctx = rctx(rules, size, count)
        out = compose.resolve(request(key, {k.replace("__", "."): v for k, v in over.items()}), None, ctx)
        assert not isinstance(out, Issue), out.message_ko
        res, params, issues = out
        t = compose.template_for(res)
        p, adj = clamp_params(t, compose.assembly_params(t, params), ctx, max_passes=compose.ASSEMBLY_MAX_PASSES)
        _SETTLED[cache_key] = (t, p, issues + adj)
    return _SETTLED[cache_key]


def at_end(rules, key: str, size: str, end: str) -> tuple[ComposedTemplate, TemplateParams, list[Issue]]:
    over = {} if end == "default" else {k.replace(".", "__"): v for k, v in EXTREMES[key][end].items()}
    return settle(rules, key, size, **over)


def errors(issues: list[Issue]) -> list[str]:
    return [i.message_ko for i in issues if i.severity == Severity.error]


def engine_ctx(rules, size: str, count: int = 1, cage: Cage | None = None) -> EngineContext:
    return EngineContext(cage=cage or Cage(1000, 600, 500), species="hamster", size=size, count=count, rules=rules)


def assembly_spec(req: AssemblyRequest) -> ItemSpec:
    return ItemSpec("assembly", {p.id: p.params for p in req.parts}, assembly=req)


def _volume(a, b) -> float:
    try:
        inter = a & b
    except Exception:  # noqa: BLE001 - 겹침이 없으면 빈 형상
        return 0.0
    return float(inter.volume) if inter is not None else 0.0


def printable(t: ComposedTemplate, p: TemplateParams, rules) -> dict:
    """출력 파트마다 출력 자세로: 닫힌 한 덩어리, 베드 위, 오버행 허용 면적 안, 기준 프린터 안."""
    bx, by, bz = rules.printing.build_volume_mm
    out = {}
    for pp in t.print_parts(p):
        pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
        assert mesh_health(pm).ok and pm.body_count == 1, pp.key
        assert pm.bounds[0][2] == pytest.approx(0, abs=1e-6), pp.key
        assert overhang_area(pm, rules.printing.max_overhang_deg) <= rules.printing.overhang_area_tolerance_mm2, pp.key
        assert all(a <= b for a, b in zip(sorted(pm.extents[:2]), sorted([bx, by]), strict=True)), (pp.key, pm.extents)
        assert pm.extents[2] <= bz, (pp.key, pm.extents)
        out[pp.key] = pp
    return out


def plan_for(t: ComposedTemplate, p: TemplateParams, child: str):
    """child 를 붙인 슬라이드 결합의 연결판 자리와 결합 번호."""
    layout = t._layout(p)
    _, joins = t.expand(p)
    (ji,) = [i for i in layout.plans if joins[i].child == child]
    return layout, layout.plans[ji], ji


# ── 공통: 모든 고정 데이터 ──


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("key", KEYS)
def test_preset_passes_the_engine_in_a_roomy_cage(rules, key, size):
    """API 와 같은 길(run_engine: 해석·자동 보정·배치·검증)로 넓은 케이지에 하나: 오류도 경고도 없고
    (exceeds_build_volume 포함), 저장되는 구조가 고정 데이터의 결합과 같다."""
    res = run_engine([assembly_spec(request(key))], engine_ctx(rules, size))
    bad = [(i.severity.value, i.code, i.message_ko) for i in res.report.issues if i.severity != Severity.info]
    assert not bad, bad
    (item,) = res.items
    assert item.placement is not None
    assert item.assembly.stored()["joins"] == fixture(key)["expected"]["joins"]


@pytest.mark.parametrize("end", ENDS)
@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("key", KEYS)
def test_preset_is_closed_and_printable_at_size_ends(rules, key, size, end):
    """기본값과 옛 세트의 크기 끝값을 자동 보정한 값에서: 보정 오류·규칙 위반 없음, 조립 형상은 닫힌 한 덩어리,
    출력 파트마다 서포트 없이 기준 프린터 안 (엔진의 check_build_volume 으로도)."""
    t, p, issues = at_end(rules, key, size, end)
    assert not errors(issues), errors(issues)
    assert t.rule_issues(p, rctx(rules, size)) == []
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    printable(t, p, rules)
    assert check_build_volume([build_item(0, t, p, PlacementHint(), rules.printing)], rules.printing) == []


@pytest.mark.parametrize("key", KEYS)
def test_print_rotation_is_no_worse_than_upright(key, rules):
    """조립 형상 전체의 출력 자세는 여섯 방향 가운데 가장 나은 것: 사용 자세보다 서포트 면적이 넓지 않다."""
    t, p, _ = settle(rules, key)
    body = part_to_mesh(t._body(p))
    best = overhang_area(to_print_orientation(body, t.print_rotation(p)), 45)
    upright = overhang_area(to_print_orientation(body, np.eye(3)), 45)
    assert best <= upright + 1.0


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("key", ROOMS)
def test_two_animals_get_two_entrances(rules, key, size):
    """여러 마리면 방마다 출입구 2개 기준: 바깥 출입구가 2개 이상이고 규칙 위반이 없다 (옆면의 받침·거치대·램프는 그대로)."""
    c = rctx(rules, size, count=2)
    t, p, issues = settle(rules, key, size, count=2)
    assert not errors(issues), errors(issues)
    assert t.rule_issues(p, c) == []
    parts, joins = t.expand(p)
    assert merge_features(parts, joins, enclosure=True).entrance_count >= 2
    assert t.resolved.stored()["joins"] == fixture(key)["expected"]["joins"]


# ── 그릇 받침 ──


def test_bowl_slides_on_with_dovetail_play(rules):
    """출력 파트 둘(은신처 본체 + 연결판·홈, 그릇 받침 + 혀). 혀는 틈새를 두고 홈 안에 있고, 옆·바깥으로는
    0.5·1mm 만 움직여도 걸리며(도브테일), 위로는 빠진다 (홈 위아래가 트였다)."""
    t, p, _ = settle(rules, "hideout_with_bowl")
    pps = printable(t, p, rules)
    assert set(pps) == {"body", "bowl"} and pps["bowl"].name_ko == "그릇 받침"
    body, bowl = pps["body"].part, pps["bowl"].part
    x_face = p.hide.width_mm / 2
    assert _volume(body, bowl) < 1.0
    assert bowl.bounding_box().min.X < x_face + FACE - 2.0  # 혀가 홈 깊이만큼 벽 쪽으로
    for dy in (0.5, -0.5):
        assert _volume(body, Pos(0, dy, 0) * bowl) > 1.0
    assert _volume(body, Pos(1.0, 0, 0) * bowl) > 1.0
    assert _volume(body, Pos(0, 0, 60) * bowl) < 1.0
    # 받침은 사용 자세(바닥판이 베드), 은신처는 뒤집어(지붕이 베드) 출력한다
    assert pps["bowl"].rotation[2][2] == pytest.approx(1.0)
    assert pps["body"].rotation[2][2] == pytest.approx(-1.0)


@pytest.mark.parametrize("bowl_height", [35, 40, 60])
@pytest.mark.parametrize("key", ["hideout_with_bowl", "dining_hideout"])
def test_bowl_collar_leaves_only_a_shallow_groove_and_the_hideout_is_taller(rules, key, bowl_height):
    """사서 쓰는 그릇은 형상에 없어 그릇과 은신처 벽 사이 홈은 엔진이 재지 않는다: 벽에 붙인 받침은 턱을
    테두리 − 5mm 까지 올려 그 홈을 5mm 깊이로 줄이고, 은신처는 그릇 테두리보다 15mm 이상 높다."""
    t, p, issues = settle(rules, key, bowl__bowl_height_mm=bowl_height, bowl__collar_height_mm=10,
                          hide__height_mm=60)
    assert not errors(issues), errors(issues)
    assert p.bowl.bowl_height_mm == bowl_height
    assert p.bowl.bowl_height_mm - p.bowl.collar_height_mm <= 5.0 + 1e-9
    assert p.hide.height_mm >= bowl_height + 15 - 1e-9
    assert t.rule_issues(p, rctx(rules, "dwarf")) == []


def test_side_grows_for_a_big_bowl(rules):
    """그릇 받침이 옆면 안에 들어가게 은신처 세로를 받침 폭 + 양쪽 여유(3mm)까지 넓힌다."""
    t, p, issues = settle(rules, "hideout_with_bowl", bowl__bowl_diameter_mm=130, hide__depth_mm=100)
    assert p.bowl.bowl_diameter_mm == 130
    assert 2 * outer_radius(p.bowl) == pytest.approx(138)
    assert p.hide.depth_mm == pytest.approx(138 + 2 * compose.EDGE_MARGIN_MM)
    assert any(i.code == "param_adjusted" and "세로" in i.message_ko for i in issues)
    assert t.rule_issues(p, rctx(rules, "dwarf")) == []


# ── 물병 거치대 ──


def test_bottle_stand_slides_on_and_the_plate_reaches_the_roof(rules):
    """출력 파트 셋(본체, 거치대 받침판, 물병 컵 + 혀). 혀는 연결판에 가장 넓게 닿는 물병 컵(뒤판)에 붙고 받침판은 연결판에
    맞닿기만 한다. 거치대가 은신처보다 높아 연결판은 지붕 높이에서 평평하게 끝나고, 그 위로 끼임 틈이 없다."""
    t, p, _ = settle(rules, "hideout_with_bottle")
    pps = printable(t, p, rules)
    assert set(pps) == {"body", "bottle_base", "bottle_holder"}
    for a, b in itertools.combinations(pps.values(), 2):
        assert _volume(a.part, b.part) < 1.0, (a.key, b.key)
    body, holder = pps["body"].part, pps["bottle_holder"].part
    face = -p.hide.width_mm / 2 - FACE  # 연결판 바깥면 (은신처 왼쪽 = -X)
    assert holder.bounding_box().max.X > face + 2.0
    assert pps["bottle_base"].part.bounding_box().max.X == pytest.approx(face, abs=1e-3)
    for dy in (0.5, -0.5):
        assert _volume(body, Pos(0, dy, 0) * holder) > 1.0
    assert _volume(body, Pos(-1.0, 0, 0) * holder) > 1.0
    assert _volume(body, Pos(0, 0, p.hide.height_mm) * holder) < 1.0
    assert total_height(p.bottle) > p.hide.height_mm
    layout, plan, ji = plan_for(t, p, "bottle")
    assert plan.h == pytest.approx(p.hide.height_mm) and plan.top == pytest.approx(p.hide.height_mm)
    assert plan.t1 - plan.t0 == pytest.approx(p.bottle.base_width_mm, abs=0.01)
    parts, joins = t.expand(p)
    assert t._plate_gaps(layout, plan, joins[ji], parts, joins) == ()


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("key,over", [
    # 옛 세트의 가장 높은 은신처(110)와 가장 낮은 거치대 (물병 거치대 세트: 30 + 40 + 45 = 115)
    ("hideout_with_bottle", {"bottle__spout_drop_mm": 40, "bottle__holder_height_mm": 45}),
    # 가장 넓은 출입구(100)에 가장 낮은 거치대 (식당 세트: 30 + 30 + 50 = 110)
    ("dining_hideout", {"hide__entrance_diameter_mm": 100, "bottle__spout_drop_mm": 30, "bottle__holder_height_mm": 50}),
])
def test_hideout_is_no_taller_than_the_shortest_stand(rules, key, over, size):
    """은신처가 거치대보다 높으면 연결판이 거치대 높이에서 끝나 그 위로 물병(형상에 없음)과 은신처 벽 사이에 틈이 남는다.
    가장 높은 은신처에 가장 낮은 거치대를 붙여도 보정 뒤 거치대가 지붕보다 낮지 않고 연결판 위 틈이 없다."""
    c = rctx(rules, size)
    t, p, issues = settle(rules, key, size, hide__height_mm=110, bottle__spout_height_mm=30, **over)
    assert not errors(issues), errors(issues)
    assert t.rule_issues(p, c) == []
    assert total_height(p.bottle) >= p.hide.height_mm - 1e-9
    layout, plan, ji = plan_for(t, p, "bottle")
    parts, joins = t.expand(p)
    assert plan.h == pytest.approx(p.hide.height_mm)
    assert t._plate_gaps(layout, plan, joins[ji], parts, joins) == ()


def test_side_grows_for_a_wide_bottle_base(rules):
    """물병 거치대 바닥판이 옆면 안에 들어가게 은신처 세로를 바닥판 + 양쪽 여유(3mm)까지 넓힌다."""
    t, p, _ = settle(rules, "hideout_with_bottle", hide__depth_mm=90, bottle__base_width_mm=130,
                     bottle__base_depth_mm=130)
    assert p.bottle.base_width_mm == 130
    assert p.hide.depth_mm == pytest.approx(130 + 2 * compose.EDGE_MARGIN_MM)
    assert t.rule_issues(p, rctx(rules, "dwarf")) == []


def test_tall_bottle_stand_widens_its_base_and_the_side(rules):
    """물병 거치대 바닥판은 넘어지지 않게 전체 높이의 절반 이상이어야 한다 (거치대 자신의 제약). 넓어진 바닥판에
    맞춰 은신처 세로도 넓어지고, 250mm 거치대도 프린터에 들어간다."""
    t, p, issues = settle(rules, "dining_hideout", hide__depth_mm=104, bottle__spout_height_mm=80,
                          bottle__spout_drop_mm=85, bottle__holder_height_mm=85)
    assert total_height(p.bottle) == pytest.approx(250)
    assert p.bottle.base_width_mm >= 125 - 1e-9
    assert p.hide.depth_mm >= p.bottle.base_width_mm + 2 * compose.EDGE_MARGIN_MM - 1e-9
    assert any(i.code == "param_adjusted" and "넘어지지 않도록" in i.message_ko for i in issues)
    assert t.rule_issues(p, rctx(rules, "dwarf")) == []
    printable(t, p, rules)


def test_dining_hideout_prints_four_parts_on_both_sides(rules):
    """그릇 받침은 오른쪽(+X), 물병 거치대는 왼쪽(-X). 은신처는 뒤집어, 그릇 받침·받침판은 사용 자세로, 물병 컵은
    뒤집어(컵 입구가 베드) 출력한다."""
    t, p, _ = settle(rules, "dining_hideout")
    pps = printable(t, p, rules)
    assert set(pps) == {"body", "bowl", "bottle_base", "bottle_holder"}
    back = p.hide.width_mm / 2 + FACE
    assert pps["bowl"].part.bounding_box().min.X < back - 2.0
    assert pps["bottle_holder"].part.bounding_box().max.X > -back + 2.0
    assert pps["bottle_base"].part.bounding_box().max.X == pytest.approx(-back, abs=1e-3)
    assert pps["body"].rotation[2][2] == pytest.approx(-1.0)
    assert pps["bowl"].rotation[2][2] == pytest.approx(1.0)
    assert pps["bottle_base"].rotation[2][2] == pytest.approx(1.0)
    assert pps["bottle_holder"].rotation[2][2] == pytest.approx(-1.0)
    # 가장 높은 곳은 물병 컵 입구
    m = part_to_mesh(t.build(p))
    assert m.extents[2] == pytest.approx(total_height(p.bottle), abs=1e-3)


# ── 램프 (은신처 지붕으로) ──


def test_ramp_landing_is_flush_with_the_roof(rules):
    """램프 높이는 붙인 면의 꼭대기(은신처 지붕)를 따른다. 연결판이 지붕 높이까지 경사 없이 올라가고, 램프 발판·연결판·
    지붕이 같은 높이이며, 발판 끝면이 연결판 바깥면에 맞닿는다."""
    t, p, _ = settle(rules, "hideout_with_ramp", hide__height_mm=95, ramp__height_mm=40)
    h = p.hide.height_mm
    assert p.ramp.height_mm == pytest.approx(h)
    _, plan, _ = plan_for(t, p, "ramp")
    assert plan.h == pytest.approx(h) and plan.top == pytest.approx(h)
    pps = {pp.key: pp for pp in t.print_parts(p)}
    assert set(pps) == {"body", "ramp"}
    for pp in pps.values():
        assert pp.part.bounding_box().max.Z == pytest.approx(h, abs=1e-6)
        assert abs(pp.rotation[2, 2]) == pytest.approx(1.0), pp.key  # 도브테일이 세로로 서는 자세만
    face = p.hide.width_mm / 2 + FACE
    assert pps["ramp"].part.bounding_box().min.X < face  # 혀가 홈 속으로
    probe = part_to_mesh(pps["ramp"].part)
    assert probe.contains([[face + 0.5, 20.0, h - 1]])[0]  # 혀가 없는 곳도 발판이 연결판에 닿는다
    assert not probe.contains([[face - 0.5, 20.0, h - 1]])[0]
    m = part_to_mesh(t.build(p))
    assert m.bounds[1][2] == pytest.approx(h, abs=1e-6)


def test_ramp_slide_fit_has_play_but_locks_sideways(rules):
    """도브테일 혀는 홈 속에서 옆으로 0.25mm 남짓 놀다가 걸린다 (밀어 내리는 방향으로만 빠진다)."""
    t, p, _ = settle(rules, "hideout_with_ramp")
    pps = {pp.key: pp.part for pp in t.print_parts(p)}
    body, ramp = pps["body"], pps["ramp"]
    assert _volume(body, ramp) < 1e-3
    assert _volume(body, Pos(0, 0.2, 0) * ramp) < 1e-3 and _volume(body, Pos(0, -0.2, 0) * ramp) < 1e-3
    assert _volume(body, Pos(0, 0.6, 0) * ramp) > 1.0 and _volume(body, Pos(0, -0.6, 0) * ramp) > 1.0


@pytest.mark.parametrize("size", SIZES)
def test_ramp_follows_species_climb_rules_and_fits_the_printer(rules, size):
    """높은 은신처: 램프는 지붕 높이까지 오르고 종별 오르기 높이·경사 기준 안이며, 따로 출력하는 램프가 프린터에 들어가도록
    경사를 높이에 맞춰 가파르게 한다. 계단 한 단이면 단 높이 기준을 넘으니 단을 늘린다."""
    s = rules.size_rules("hamster", size)
    c = rctx(rules, size)
    t, p, issues = settle(rules, "hideout_with_ramp", size, hide__height_mm=100, ramp__slope_deg=20)
    assert not errors(issues), errors(issues)
    f = p.ramp
    assert f.height_mm == pytest.approx(p.hide.height_mm) and f.height_mm <= s.max_climb_height_mm
    assert f.slope_deg >= BED_SLOPE_PER_MM * f.height_mm + BED_SLOPE_BASE_DEG - 1e-6
    assert f.slope_deg <= s.max_ramp_angle_deg
    assert t.rule_issues(p, c) == []
    printable(t, p, rules)
    t, p, _ = settle(rules, "hideout_with_ramp", size, ramp__steps=1)
    assert t.part_template("ramp").features(p.ramp).step_height_mm <= s.max_step_height_mm


def test_ramp_wider_than_the_side_widens_the_hideout(rules):
    """은신처 세로보다 넓은 램프: 옆면 안에 들어가게 은신처 세로를 넓힌다."""
    t, p, _ = settle(rules, "hideout_with_ramp", "syrian", hide__depth_mm=90, ramp__width_mm=120)
    assert p.ramp.width_mm == 120
    assert p.hide.depth_mm >= 120 + 2 * compose.EDGE_MARGIN_MM - 1e-9
    assert t.rule_issues(p, rctx(rules, "syrian")) == []


@pytest.mark.parametrize("size", SIZES)
def test_roof_vents_are_small_enough_to_walk_on(rules, size):
    """램프로 지붕에 올라가므로 환기구는 발이 끼지 않는 크기 이하로 줄인다 (은신처 자신의 종별 제약)."""
    _, p, _ = settle(rules, "hideout_with_ramp", size, hide__vent_diameter_mm=8)
    assert p.hide.vent_count > 0
    assert p.hide.vent_diameter_mm <= rules.size_rules("hamster", size).gap_trap.safe_max_mm + 1e-9


# ── 램프 (모래목욕통 턱으로) ──


@pytest.mark.parametrize("over", [{}, {"ramp__steps": 2}, {"bath__lip_height_mm": 20}, {"bath__lip_height_mm": 35}])
def test_sand_bath_ramp_lands_at_the_lip(rules, over):
    """램프 높이 = 턱 높이. 발판은 턱 윗면 높이에서 끝나고 출입 홈 바로 앞에 놓인다. 연결판은 턱 높이 아래에서 경사로
    끝나 출입 홈(턱 위)을 덮지 않는다. 출입 면은 모래목욕통 앞면(이어져 빠진다)에서 램프 입구로 넘어간다."""
    c = rctx(rules, "dwarf")
    t, p, issues = settle(rules, "sand_bath_with_ramp", **over)
    assert not errors(issues), errors(issues)
    bath, ramp = p.bath, p.ramp
    lip = bath.lip_height_mm
    assert ramp.height_mm == pytest.approx(lip)
    _, plan, _ = plan_for(t, p, "ramp")
    assert plan.top == pytest.approx(lip) and plan.h == pytest.approx(lip - SLOPE_RISE * FACE)
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    y_wall = -bath.depth_mm / 2
    half = min(entry_width(bath), ramp.width_mm) / 2
    # 발판 윗면 = 턱 윗면 높이, 그 위와 출입 홈은 비어 있다
    assert m.contains([[0, y_wall - FACE - 2, lip - 0.5], [half - 2, y_wall - FACE - 2, lip - 0.5]]).all()
    assert not m.contains([[0, y_wall - FACE - 2, lip + 0.5], [0, y_wall + 1.5, lip + 0.5],
                           [0, y_wall - 1.0, lip + 0.3]]).any()
    parts, joins = t.expand(p)
    entry = t.part_template("ramp").anchors(ramp)["entry"]
    assert place_parts(parts, joins)["ramp"].point(entry.origin)[1] < y_wall - 50
    assert t.features(p).access_sides == ("front",)
    assert t.rule_issues(p, c) == []


def test_sand_bath_ramp_slides_on_with_dovetail_play(rules):
    """출력 파트 둘(모래목욕통 본체 + 연결판, 램프 + 혀). 옆(X)·바깥(−Y)으로 0.5·1mm 만 움직여도 걸리고 위로는 빠진다.
    둘 다 사용 자세로 출력한다."""
    t, p, _ = settle(rules, "sand_bath_with_ramp")
    pps = printable(t, p, rules)
    assert set(pps) == {"body", "ramp"}
    body, ramp = pps["body"].part, pps["ramp"].part
    y_face = -p.bath.depth_mm / 2 - FACE
    assert _volume(body, ramp) < 1.0
    assert ramp.bounding_box().max.Y > y_face + 2.0
    for dx in (0.5, -0.5):
        assert _volume(body, Pos(dx, 0, 0) * ramp) > 1.0
    assert _volume(body, Pos(0, -1.0, 0) * ramp) > 1.0
    assert _volume(body, Pos(0, 0, p.bath.lip_height_mm + 1) * ramp) < 1.0
    for key in ("body", "ramp"):
        assert pps[key].rotation[2][2] == pytest.approx(1.0), key
    assert ramp.bounding_box().max.Z == pytest.approx(p.bath.lip_height_mm, abs=1e-6)
    m = part_to_mesh(t.build(p))
    assert m.extents[1] == pytest.approx(p.bath.depth_mm + FACE + run_length(p.ramp) + TOP_LANDING_MM, abs=0.1)


def test_dwarf_lip_is_lowered_and_the_ramp_follows(rules):
    """드워프 햄스터의 턱은 종별 단 높이(35mm)로 낮아지고, 램프 높이도 함께 낮아진다."""
    _, p, _ = settle(rules, "sand_bath_with_ramp", bath__lip_height_mm=45, ramp__height_mm=45)
    assert p.bath.lip_height_mm == pytest.approx(rules.size_rules("hamster", "dwarf").max_step_height_mm)
    assert p.ramp.height_mm == pytest.approx(p.bath.lip_height_mm)


def test_steep_short_stairs_get_fewer_steps(rules):
    """낮은 턱·가파른 경사의 계단은 디딤판이 충분히 깊도록 단 수가 줄어든다 (램프 자신의 제약)."""
    _, p, issues = settle(rules, "sand_bath_with_ramp", bath__lip_height_mm=20, ramp__slope_deg=30, ramp__steps=3)
    assert p.ramp.steps < 3
    assert any(i.code == "param_adjusted" for i in issues)


# ── 터널 (끼움 결합) ──


def _spigot_play(t: ComposedTemplate, p: TemplateParams, body_key: str, room: str, door: str) -> None:
    """끼움 턱과 넓힌 구멍 사이 틈새 PLUG_CLEARANCE_MM: 조금(틈새 − 0.05) 옮겨도 겹치지 않고 0.5mm 옮기면 걸린다."""
    pps = {pp.key: pp.part for pp in t.print_parts(p)}
    parts, joins = t.expand(p)
    _, tt, u, _n = anchor_frame(place_parts(parts, joins), room, door)
    body, tube = pps[body_key], pps["tube"]
    assert _volume(body, tube) < 1.0
    for d in (tt, -tt, u):
        assert _volume(body, Pos(*(d * (PLUG_CLEARANCE_MM - 0.05))) * tube) < 1.0, (room, d)
        assert _volume(body, Pos(*(d * 0.5)) * tube) > 1.0, (room, d)


def test_twin_hideouts_print_as_three_plugged_parts(rules):
    """은신처 + 터널 + 은신처는 한 덩어리로 출력할 수 없다: 터널을 따로 출력해 양쪽 출입구에 끼운다. 두 번째 은신처는
    번호를 붙인 이름으로, 바깥 출입구는 두 은신처의 뒷문 둘."""
    t, p, _ = settle(rules, "twin_hideouts")
    pps = t.print_parts(p)
    assert [pp.key for pp in pps] == ["body", "tube", "hide2"]
    assert [pp.name_ko for pp in pps][1:] == ["터널", "은신처 2"]
    assert max(_volume(a.part, b.part) for a, b in itertools.combinations(pps, 2)) < 1.0
    parts, joins = t.expand(p)
    assert merge_features(parts, joins, enclosure=True).entrance_count == 2
    assert p.tube.inner_diameter_mm == p.hide.entrance_diameter_mm == p.hide2.entrance_diameter_mm
    _spigot_play(t, p, "body", "hide", "front")
    _spigot_play(t, p, "hide2", "hide2", "front")


@pytest.mark.parametrize("size", SIZES)
def test_tunnel_follows_the_species_entrance(rules, size):
    """종별 최소 출입구·터널 내경은 주인 값(은신처 출입구)으로 옮겨 올리고, 터널 내경과 두 번째 은신처 출입구가 따라간다.
    터널 길이는 종별 기준(내경의 1.5배 이상, 최대 길이 이하) 안으로."""
    s = rules.size_rules("hamster", size)
    t, p, issues = settle(rules, "twin_hideouts", size, hide__entrance_diameter_mm=50, tube__length_mm=200)
    assert not errors(issues), errors(issues)
    need = max(s.entrance_min_diameter_mm, s.tunnel_min_inner_diameter_mm)
    assert p.hide.entrance_diameter_mm == pytest.approx(need)
    assert p.tube.inner_diameter_mm == p.hide2.entrance_diameter_mm == p.hide.entrance_diameter_mm
    assert p.tube.length_mm <= s.tunnel_max_length_mm + 1e-9
    assert p.tube.length_mm >= 1.5 * p.tube.inner_diameter_mm - 1e-9
    assert t.rule_issues(p, rctx(rules, size)) == []


def test_hideout_tunnel_is_plugged_not_fused(rules):
    """옛 세트는 은신처와 터널이 한 덩어리라 골든 햄스터 기본값(세로 110 + 터널 120)부터 출력 공간을 넘었다
    (KNOWN_OVERSIZE). 끼움 결합이면 둘을 따로 출력해 들어가고, 터널 단면은 은신처 출입구(둥근 아치)에 맞춘다."""
    t, p, issues = settle(rules, "hideout_with_tunnel", "syrian", hide__depth_mm=110, tube__length_mm=120)
    assert [j.mount for j in t.resolved.joins] == ["plug"]
    assert any(i.code == "passage_shape_matched" for i in issues)
    assert p.tube.shape == "round_arch"
    assert set(printable(t, p, rules)) == {"body", "tube"}
    _spigot_play(t, p, "body", "hide", "front")


@pytest.mark.parametrize("size", SIZES)
def test_house_tunnel_plugs_into_the_port(rules, size):
    """집 오른쪽 연결부에 뾰족 아치 터널을 끼운다: 출력 파트 둘(평 지붕), 터널은 사용 자세 그대로(끼움 턱이 옆을 본다),
    끼움 턱 틈새, 바깥 출입구는 집 앞문 + 터널 끝."""
    t, p, _ = settle(rules, "house_with_tunnel", size)
    pps = printable(t, p, rules)
    assert set(pps) == {"body", "tube"}
    assert np.allclose(pps["tube"].rotation, np.eye(3))
    _spigot_play(t, p, "body", "house", "right")
    f = t.features(p)
    assert f.entrance_count == 2
    assert set(f.access_sides) == {"front", "right"}


def test_house_tunnel_follows_the_species_port(rules):
    """골든 햄스터: 집 연결부 지름(주인 값)이 종별 최소 터널 내경으로 올라가고 터널 내경이 따라간다."""
    s = rules.size_rules("hamster", "syrian")
    t, p, issues = settle(rules, "house_with_tunnel", "syrian", house__ports__diameter_mm=50,
                          house__doors__width_mm=50, tube__inner_diameter_mm=50)
    assert not errors(issues), errors(issues)
    assert p.house.ports.diameter_mm == p.tube.inner_diameter_mm >= s.tunnel_min_inner_diameter_mm - 1e-9
    assert p.house.doors.width_mm >= s.entrance_min_diameter_mm - 1e-9
    assert t.rule_issues(p, rctx(rules, "syrian")) == []


def test_pitched_house_roof_prints_separately(rules):
    """경사 지붕 집: 높이를 올리고 지붕 뚜껑을 따로 출력한다 (본체·지붕 뚜껑·터널 셋)."""
    t, p, issues = settle(rules, "house_with_tunnel", "syrian", house__roof__kind="pitched")
    assert not errors(issues), errors(issues)
    assert p.house.height_mm > 180
    assert t.rule_issues(p, rctx(rules, "syrian")) == []
    assert set(printable(t, p, rules)) == {"body", "tube", "house_roof"}


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("cage_h", [230, 250])
def test_house_tunnel_fits_a_low_cage(rules, size, cage_h):
    """평 지붕 120mm 집은 깔짚을 깔아 높이가 250mm 쯤인 흔한 케이지에서도 오류가 없다."""
    res = run_engine([assembly_spec(request("house_with_tunnel"))], engine_ctx(rules, size, cage=Cage(1000, 500, cage_h)))
    assert not res.report.errors, [(i.code, i.message_ko) for i in res.report.errors]


# ── 영어 ──

HANGUL = re.compile(r"[가-힣]")


def _english(texts: list[str]) -> list[tuple[str, str]]:
    """영어로 바꾼 뒤에도 한국어가 남는 문구 (원문, 바꾼 것)."""
    cat = catalog()
    return [(s, cat.translate(s)) for s in dict.fromkeys(texts) if HANGUL.search(cat.translate(s))]


@pytest.mark.parametrize("key", KEYS)
def test_preset_text_has_english(rules, key):
    """이름 없이(조립 구조물이 지은 이름) 골든 햄스터 두 마리로 보정한 고정 데이터: 이름·부품 이름·출력 파트 이름·
    해석기와 자동 보정 안내가 모두 영어로 바뀐다 (조사·번호를 붙인 부품 이름, 조립 구조물 이름을 앞에 단 안내 포함)."""
    ctx = rctx(rules, "syrian", count=2)
    out = compose.resolve(request(key, named=False), None, ctx)
    assert not isinstance(out, Issue), out.message_ko
    res, params, issues = out
    t = compose.template_for(res)
    _, adj = clamp_params(t, compose.assembly_params(t, params), ctx, max_passes=compose.ASSEMBLY_MAX_PASSES)
    texts = [i.message_ko for i in issues + adj] + [t.display_name_ko, t.description_ko, *t.names.values()]
    t1, p1, _ = settle(rules, key, "syrian")  # 출력 파트 (형상은 앞의 테스트가 만들어 둔 것)
    texts += [pp.name_ko for pp in t1.print_parts(p1)]
    assert texts and not _english(texts), _english(texts)


def test_resolver_notices_have_english(rules):
    """옮기기·출입구 내기·터널 넣기·단면 맞추기·나갈 출입구 안내와 결합 오류도 영어로 바뀐다."""
    from app.templates.registry import primitives

    prim = primitives()

    def dp(k: str) -> dict:
        return prim[k].default_params().model_dump()

    cases = [
        ([("hide", "hideout"), ("bowl", "bowl_holder")], [("bowl", "hide", "front")]),
        ([("hide", "hideout"), ("hide2", "hideout")], [("hide2", "hide", "front")]),
        ([("hide", "hideout"), ("tube", "tunnel"), ("tube2", "tunnel")], [("tube", "hide", "back"), ("tube2", "hide", "front")]),
        ([("house", "house"), ("tube", "tunnel")], [("tube", "house", "left")]),
        ([("tube", "tunnel"), ("hide", "hideout"), ("bowl", "bowl_holder")], [("hide", "tube", "front"), ("bowl", "tube", "auto")]),
        ([("bath", "sand_bath"), ("tube", "tunnel")], [("tube", "bath", "front")]),
        ([("hide", "hideout")] + [(f"b{i}", "bottle_stand") for i in range(5)],
         [("b0", "hide", "left"), ("b1", "hide", "left"), ("b2", "hide", "right"), ("b3", "hide", "back"), ("b4", "hide", "front")]),
    ]
    texts: list[str] = []
    codes: set[str] = set()
    for parts, conns in cases:
        req = AssemblyRequest(parts=[{"id": a, "template": b, "params": dp(b)} for a, b in parts],
                              connections=[{"part": a, "to": b, "at": c} for a, b, c in conns])
        out = compose.resolve(req, None, rctx(rules, "syrian"))
        if isinstance(out, Issue):
            texts.append(out.message_ko)
            codes.add(out.code)
            continue
        texts += [i.message_ko for i in out[2]] + [compose.template_for(out[0]).display_name_ko]
        codes |= {i.code for i in out[2]}
    assert {"join_relocated", "tunnel_inserted", "port_opened", "passage_shape_matched", "exit_added",
            "join_unsupported", "face_unavailable"} <= codes
    assert not _english(texts), _english(texts)


# ── 모의 해석기: 옛 세트를 고르던 요청 ──


def interpret(rules, prompt: str, size: str = "dwarf"):
    entry = rules.species_entry("hamster")
    req = InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo("hamster", entry.display_name, size, 1, Cage(1000, 600, 500), habitat=entry.habitat),
        size_rules=rules.size_rules("hamster", size), min_wall_mm=rules.min_wall_for("hamster", size),
        language="en" if prompt.isascii() else "ko", allowed_templates=rules.allowed_templates("hamster"),
    )
    return MockInterpreter().interpret(req).spec


def structure(rules, prompt: str) -> list[str]:
    """요청 → 항목마다 일반 항목은 템플릿 키, 조립 항목은 해석기가 정한 결합 ("부모 < 자식 : 결합")."""
    out = []
    spec = interpret(rules, prompt)
    for it, its in zip(spec.items, to_item_specs(spec), strict=True):
        if it.template != "assembly":
            out.append(it.template)
            continue
        res = compose.resolve(its.assembly, None, rctx(rules, "dwarf"))
        assert not isinstance(res, Issue), res.message_ko
        out.append(" ".join(f"{j.parent}<{j.child}:{j.mount}" for j in res[0].joins))
    return out


BOWL = "hide.right<bowl.back:slide"
BOTTLE_R = "hide.right<bottle.back:slide"
DINING = "hide.right<bowl.back:slide hide.left<bottle.back:slide"
RAMP = "hide.right<ramp.landing:slide"
BATH_RAMP = "bath.front<ramp.landing:slide"
TUNNEL = "hide.front<tube.end_b:plug"
TWIN = "hide.front<tube.end_b:plug tube.end_a<hide2.front:plug"


@pytest.mark.parametrize("prompt,expected", [
    ("밥그릇과 물병이 달린 은신처 만들어 주세요", [DINING]),
    ("밥그릇하고 물병이 달린 은신처", [DINING]),
    ("a hideout with a food bowl and a water bottle, please", [DINING]),
    ("물병과 밥그릇이 달린 은신처를 오른쪽에 놓아 주세요", ["hide.right<bottle.back:slide hide.left<bowl.back:slide"]),
    ("밥그릇 달린 은신처 만들어 주세요", [BOWL]),
    ("먹이그릇이 붙은 은신처를 왼쪽에 넣어 주세요", [BOWL]),
    ("a hideout with a food bowl, please", [BOWL]),
    ("a bowl attached to the hideout", [BOWL]),
    ("숨숨집에 밥그릇 붙여 주세요", [BOWL]),
    ("물병 달린 은신처 만들어 주세요", [BOTTLE_R]),
    ("급수기 붙은 은신처가 필요해요", [BOTTLE_R]),
    ("I'd like a hideout with a water bottle stand", [BOTTLE_R]),
    ("물병 거치대가 붙은 숨숨집", [BOTTLE_R]),
    ("옥상으로 올라가는 경사로 달린 은신처 만들어줘", [RAMP]),
    ("계단 달린 은신처", [RAMP]),
    ("A hideout with a ramp up to the roof please", [RAMP]),
    ("a ramp up to the roof of the hideout", [RAMP]),
    ("계단 달린 모래목욕통 만들어 주세요", [BATH_RAMP]),
    ("램프 달린 모래 목욕통", [BATH_RAMP]),
    ("a dust bath with stairs", [BATH_RAMP]),
    ("터널 달린 은신처", [TUNNEL]),
    ("은신처 두 개를 터널로 이어 주세요", [TWIN]),
    ("Two hideouts connected by a tunnel, please", [TWIN]),
    ("터널로 이은 쌍둥이 은신처", [TWIN]),
    # 붙인다는 말 없이 나열하면 따로 놓는 구조물
    ("은신처랑 밥그릇 넣어 주세요", ["hideout", "bowl_holder"]),
    ("은신처와 물병 거치대를 만들어 주세요", ["hideout", "bottle_stand"]),
    ("모래목욕통이랑 경사로 넣어 주세요", ["sand_bath", "ramp"]),
    ("I need a bowl and water bottle attached to the cage wall", ["bowl_holder", "bottle_stand"]),
    ("a ramp with a bowl attached", ["ramp", "bowl_holder"]),
    ("은신처를 왼쪽에 놓아 주세요", ["hideout"]),
    # 옛 세트를 고르던 요청 중 아직 그 구조가 되지 않는 것 (모의 해석기 문법의 남은 일)
    pytest.param("은신처에 밥그릇과 물병을 따로 놓아 주세요", ["hideout", "bowl_holder", "bottle_stand"],
                 marks=pytest.mark.xfail(strict=True, reason="'따로' 가 있어도 붙인다")),
    pytest.param("은신처 왼쪽 벽에 물병 거치대를 달아줘", ["hide.left<bottle.back:slide"],
                 marks=pytest.mark.xfail(strict=True, reason="'은신처 왼쪽 벽' 을 케이지 자리로 읽는다")),
    pytest.param("쌍둥이 은신처를 오른쪽에 놓아 주세요", [TWIN],
                 marks=pytest.mark.xfail(strict=True, reason="'쌍둥이 은신처' 만으로는 둘을 잇지 않는다")),
    pytest.param("a two-story house with a ramp up to the roof", ["house", "ramp"],
                 marks=pytest.mark.xfail(strict=True, reason="2층 집 바깥 램프(attach_to)를 옆면 결합으로 붙인다")),
])
def test_mock_reads_old_set_requests_as_the_same_structure(rules, prompt, expected):
    assert structure(rules, prompt) == expected


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("prompt", [
    "밥그릇과 물병이 달린 은신처 만들어 주세요",
    "계단 달린 은신처",
    "경사로가 달린 모래 목욕통을 오른쪽에 넣어 주세요",
    "two hideouts connected with a tunnel",
])
def test_mock_design_runs_through_the_engine(rules, prompt, size):
    spec = interpret(rules, prompt, size)
    res = run_engine(to_item_specs(spec), engine_ctx(rules, size))
    assert res.report.passed, [(i.code, i.message_ko) for i in res.report.errors]
    assert [it.key for it in res.items] == ["assembly"] and res.items[0].placement is not None
    if "오른쪽" in prompt:
        assert spec.items[0].placement.zone == "right"
    if "계단" in prompt:
        assert res.items[0].params.ramp.steps > 0
