"""모듈 라이브러리: 라이브러리의 모든 조립 모듈을 기본값과 크기 범위 끝값으로 만들어 기준을 확인한다.

새 모듈 파일(app/modules/library/*.json)을 넣으면 여기서 함께 검사된다.
"""

from __future__ import annotations

import itertools
import json

import numpy as np
import pytest
from build123d import Pos
from pydantic import ValidationError

from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.modules.assembly import OVERLAP_MM, PLATE_MM, AssemblyError, JoinSpec, PartSpec, merge_features, place_parts
from app.modules.definition import ModuleDef, library
from app.modules.module_template import ModuleTemplate
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.domain import Cage
from app.rules.loader import GapTrapRule
from app.templates.base import RuleContext
from app.templates.bottle_stand import BottleStandTemplate
from app.templates.bowl_holder import BowlHolderTemplate
from app.templates.hideout import HideoutParams, HideoutTemplate
from app.templates.registry import get_template, primitives
from app.templates.tunnel import TunnelParams, TunnelTemplate
from app.validation.checks import overhang_area

MODULES = [m.key for m in library()]
HAMSTERS = [("hamster", "syrian"), ("hamster", "dwarf")]


def ctx(rules, species="hamster", size="syrian") -> RuleContext:
    return RuleContext(rules.size_rules(species, size), rules.min_wall_for(species, size))


def _extremes(t: ModuleTemplate):
    """기본값 + 크기 파라미터를 모두 최소/최대로."""
    base = t.Params().model_dump()
    yield base
    for end in ("min", "max"):
        p = dict(base)
        for d in t.defn.params:
            if d.name in t.defn.size_params:
                p[d.name] = getattr(d, end)
        yield p


def test_library_is_not_empty_and_keys_are_unique():
    assert MODULES, "모듈 라이브러리가 비어 있습니다"
    assert len(set(MODULES)) == len(MODULES)
    prims = primitives()
    for m in library():
        assert m.key not in prims
        for part in m.parts:
            assert part.template in prims, f"{m.key}: 부품 {part.template} 이(가) 기본 부품이 아닙니다"


@pytest.mark.parametrize("key", MODULES)
def test_every_module_builds_closed_printable_meshes(key):
    t = get_template(key)
    for raw in _extremes(t):
        p = t.Params.model_validate(raw)
        mesh = part_to_mesh(t.build(p))
        assert mesh_health(mesh).ok, (key, raw)
        for pp in t.print_parts(p):
            pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
            assert mesh_health(pm).ok, (key, pp.key)
            assert pm.bounds[0][2] == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize("key", MODULES)
@pytest.mark.parametrize("species,size", HAMSTERS)
def test_every_module_passes_validation_in_a_roomy_cage(key, species, size, rules):
    """기본 파라미터로 넓은 케이지에 하나만 놓으면 (자동 보정 뒤) 오류 없이 통과해야 한다."""
    t = get_template(key)
    ectx = EngineContext(cage=Cage(1000, 600, 500), species=species, size=size, count=1, rules=rules)
    res = run_engine([ItemSpec(template=key, params=t.Params().model_dump())], ectx)
    errors = [i for i in res.report.errors]
    assert not errors, [(i.code, i.message_ko) for i in errors]
    assert res.items and res.items[0].placement is not None


@pytest.mark.parametrize("key", MODULES)
def test_module_text_has_english(key):
    from app.i18n import catalog

    m = next(d for d in library() if d.key == key)
    cat = catalog()
    for ko in [m.name_ko, m.description_ko, *[p.description_ko for p in m.params]]:
        assert cat.translate(ko) != ko or not any("가" <= c <= "힣" for c in ko), ko


def test_module_constraints_map_part_rules_back_to_module_params(rules):
    """부품의 종별 최소값(출입구·터널 내경)이 묶인 모듈 파라미터의 하한이 되어 자동 보정된다."""
    t = get_template("hideout_with_tunnel")
    c = ctx(rules, size="syrian")
    cons = [k for k in t.constraints(t.Params(entrance_mm=40), c) if k.field == "entrance_mm" and k.min is not None]
    need = max(c.size.entrance_min_diameter_mm, c.size.tunnel_min_inner_diameter_mm)
    assert max(k.min for k in cons) == pytest.approx(need)


def test_fixed_part_value_that_breaks_a_species_rule_is_an_error(rules):
    """모듈이 상수로 정한 부품 값이 종 기준을 어기면 자동 보정할 수 없는 오류로 남는다."""
    defn = ModuleDef.model_validate({
        "key": "tiny_tunnel_test", "name_ko": "시험", "name_en": "test", "description_ko": "시험",
        "description_en": "test", "params": [],
        "parts": [{"id": "t", "template": "tunnel", "params": {"inner_diameter_mm": 35}}],
    })
    t = ModuleTemplate(defn, primitives())
    issues = t.rule_issues(t.Params(), ctx(rules, size="syrian"))
    assert any("터널" in m for m in issues)


def test_blocking_an_entrance_without_a_passage_is_an_error(rules):
    defn = ModuleDef.model_validate({
        "key": "blocked_test", "name_ko": "시험", "name_en": "test", "description_ko": "시험",
        "description_en": "test", "params": [],
        "parts": [{"id": "a", "template": "hideout", "params": {}}, {"id": "b", "template": "hideout", "params": {}}],
        "joins": [{"parent": "a.front", "child": "b.left"}],
    })
    t = ModuleTemplate(defn, primitives())
    assert any("막습니다" in m for m in t.rule_issues(t.Params(), ctx(rules)))


def test_join_places_child_face_to_face():
    """자식 연결 지점은 부모 연결 지점에 마주 보게 놓인다 (법선 반대, 위쪽 같음, 기준점 일치)."""
    h = PartSpec("h", HideoutTemplate(), HideoutParams(entrance_count=2))
    t = PartSpec("t", TunnelTemplate(), TunnelParams(length_mm=150, inner_diameter_mm=60))
    for parent_anchor in ("front", "back", "left", "right"):
        placed = place_parts([h, t], [JoinSpec("h", parent_anchor, "t", "end_b", passage=parent_anchor in ("front", "back"))])
        pa = h.template.anchors(h.params)[parent_anchor]
        cb = t.template.anchors(t.params)["end_b"]
        pt = placed["t"]
        n_child = pt.vector(cb.normal)
        assert np.allclose(n_child, -np.asarray(pa.normal), atol=1e-9)
        assert np.allclose(pt.vector(cb.up), pa.up, atol=1e-9)
        assert np.allclose(pt.point(cb.origin), np.asarray(pa.origin) - np.asarray(pa.normal) * 0.3, atol=1e-6)


def test_merged_features_count_only_unjoined_entrances():
    h = PartSpec("h", HideoutTemplate(), HideoutParams(entrance_count=2))
    t = PartSpec("t", TunnelTemplate(), TunnelParams(length_mm=150, inner_diameter_mm=60))
    f = merge_features([h, t], [JoinSpec("h", "front", "t", "end_b", passage=True)], enclosure=True)
    # 은신처 뒷문 + 터널 바깥 끝 = 2
    assert f.entrance_count == 2
    assert set(f.access_sides) == {"front", "back"}


def test_passage_join_opens_the_wall():
    """터널을 문 없는 옆벽에 통로로 이으면 벽이 뚫려 드나들 수 있다."""
    from app.modules.assembly import build_assembly

    h = PartSpec("h", HideoutTemplate(), HideoutParams(width_mm=160, depth_mm=130, height_mm=100))
    t = PartSpec("t", TunnelTemplate(), TunnelParams(length_mm=120, inner_diameter_mm=60))
    mesh = part_to_mesh(build_assembly([h, t], [JoinSpec("h", "right", "t", "end_b", passage=True)]))
    assert mesh_health(mesh).ok
    # 오른쪽 벽 두께 한가운데, 통로 높이 중간: 비어 있어야 한다
    x = 160 / 2 - 1.5
    assert not mesh.contains([[x, 0.0, 25.0]])[0]


def test_unknown_anchor_is_reported():
    h = PartSpec("h", HideoutTemplate(), HideoutParams())
    t = PartSpec("t", TunnelTemplate(), TunnelParams())
    with pytest.raises(AssemblyError):
        place_parts([h, t], [JoinSpec("h", "nowhere", "t", "end_a")])


def test_module_definition_rejects_dangling_parts():
    with pytest.raises(ValueError):
        ModuleDef.model_validate({
            "key": "bad", "name_ko": "a", "name_en": "a", "description_ko": "a", "description_en": "a",
            "params": [], "parts": [{"id": "a", "template": "hideout"}, {"id": "b", "template": "tunnel"}],
        })


def test_library_files_are_valid_json_with_both_languages():
    from app.modules.definition import LIBRARY_DIR

    for f in LIBRARY_DIR.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["name_en"] and data["description_en"], f.name
        assert all(p.get("description_en") for p in data["params"]), f.name


def test_print_rotation_is_support_light_for_every_module():
    for key in MODULES:
        t = get_template(key)
        p = t.Params()
        pm = to_print_orientation(part_to_mesh(t._body(p)), t.print_rotation(p))
        # 여섯 방향 가운데 가장 나은 자세: 사용 자세보다 나쁘지 않다
        upright = to_print_orientation(part_to_mesh(t._body(p)), np.eye(3))
        assert overhang_area(pm, 45) <= overhang_area(upright, 45) + 1.0, key


@pytest.mark.parametrize("a,b", list(itertools.combinations(["front", "back", "left", "right"], 2)))
def test_side_names_survive_rotation(a, b):
    """옆면 이름 ↔ 방향 변환이 서로 맞다 (조립 특징의 출입 면 계산)."""
    from app.modules.assembly import _SIDE_VEC, _side_of

    assert _side_of(np.asarray(_SIDE_VEC[a], dtype=float)) == a
    assert _side_of(np.asarray(_SIDE_VEC[b], dtype=float)) == b


# ── 조립 엔진 형상 검사·중첩 파라미터·슬라이드 결합 ─────────────────────────

# 그릇 받침·물병 거치대는 레지스트리 등록 전이라 직접 넣는다
PARTS = {**primitives(), "bowl_holder": BowlHolderTemplate(), "bottle_stand": BottleStandTemplate()}


def module(parts, joins=(), params=()) -> ModuleTemplate:
    return ModuleTemplate(ModuleDef.model_validate({
        "key": "engine_test", "name_ko": "시험", "name_en": "test", "description_ko": "시험", "description_en": "test",
        "params": list(params), "parts": parts, "joins": list(joins),
    }), PARTS)


def dwarf(rules) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", "dwarf"), rules.min_wall_for("hamster", "dwarf"),
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def _volume(a, b) -> float:
    inter = a & b
    return float(inter.volume) if inter is not None else 0.0


# 1. 통로가 출입구를 다 덮는지

def _tunnel_into(parent: str, parent_params: dict, anchor: str, shape: str, d: float) -> ModuleTemplate:
    return module(
        [{"id": "a", "template": parent, "params": parent_params},
         {"id": "t", "template": "tunnel", "params": {"length_mm": 100, "inner_diameter_mm": d, "shape": shape,
                                                      "wall_thickness_mm": 3}}],
        [{"parent": f"a.{anchor}", "child": "t.end_b", "passage": True}],
    )


@pytest.mark.parametrize("shape,gap", [("pointed_arch", False), ("round_arch", True), ("tube", True), ("box", True)])
def test_passage_must_cover_house_door(rules, shape, gap):
    """집 출입구(뾰족 아치)에 같은 폭의 둥근 아치·관·네모 터널을 이으면 꼭대기·아래 모서리가 바깥으로 뚫린 채 남는다."""
    t = _tunnel_into("house", {}, "front", shape, 60)
    issues = t.rule_issues(t.Params(), dwarf(rules))
    assert any("틈이 남습니다" in m for m in issues) == gap, issues
    if not gap:
        assert issues == []


@pytest.mark.parametrize("shape,gap", [("round_arch", False), ("pointed_arch", False), ("tube", True)])
def test_passage_must_cover_hideout_door(rules, shape, gap):
    """은신처 출입구(직사각형 + 반원 = 둥근 아치)는 같은 폭의 둥근·뾰족 아치 터널이 덮고, 관은 아래 모서리를 남긴다."""
    t = _tunnel_into("hideout", {}, "front", shape, 60)
    issues = t.rule_issues(t.Params(), dwarf(rules))
    assert any("틈이 남습니다" in m for m in issues) == gap, issues


def test_narrower_passage_whose_wall_does_not_cover_the_door_is_an_error(rules):
    t = _tunnel_into("hideout", {}, "front", "pointed_arch", 50)  # 바깥 반폭 28 < 출입구 반폭 30
    assert any("틈이 남습니다" in m for m in t.rule_issues(t.Params(), dwarf(rules)))


@pytest.mark.parametrize("shape,d,gap", [("pointed_arch", 56, False), ("round_arch", 56, True), ("box", 56, True)])
def test_hairline_leftover_is_not_an_error(rules, shape, d, gap):
    """60mm 은신처 출입구에 56mm 뾰족 아치 터널: 아치 어깨에 폭 0.3mm 실금(부피 약 12mm³)만 남아 출력하면 메워진다.
    둥근 아치·네모는 폭 1mm 의 틈이 남아 오류."""
    t = _tunnel_into("hideout", {}, "front", shape, d)
    assert any("틈이 남습니다" in m for m in t.rule_issues(t.Params(), dwarf(rules))) == gap


@pytest.mark.parametrize("species,size", HAMSTERS)
def test_library_tunnel_hideout_has_no_geometry_issues(rules, species, size):
    t = get_template("hideout_with_tunnel")
    c = RuleContext(rules.size_rules(species, size), rules.min_wall_for(species, size))
    p = t.Params(entrance_mm=max(60.0, c.size.entrance_min_diameter_mm, c.size.tunnel_min_inner_diameter_mm))
    assert t.rule_issues(p, c) == []


# 2. 따로 출력하는 파트끼리 겹치지 않는지

PITCHED_HOUSE = {"roof.kind": "pitched", "height_mm": 200}


@pytest.mark.parametrize("ramp_h,overlap", [(100, False), (120, True)])
def test_part_joined_into_roof_cap_band_is_an_error(rules, ramp_h, overlap):
    """경사 지붕 집 벽에 붙인 램프가 처마 − 스커트 높이를 넘으면 따로 출력하는 지붕 뚜껑과 겹친다."""
    from app.templates.house import eave_height
    from app.templates.parts.shell import SKIRT_MM

    t = module([{"id": "house", "template": "house", "params": PITCHED_HOUSE},
                {"id": "ramp", "template": "ramp", "params": {"height_mm": ramp_h, "width_mm": 60, "slope_deg": 30}}],
               [{"parent": "house.right", "child": "ramp.landing"}])
    p = t.Params()
    band = eave_height(t.expand(p)[0][0].params) - SKIRT_MM
    assert (ramp_h > band) == overlap
    issues = t.rule_issues(p, dwarf(rules))
    assert any("겹칩니다" in m for m in issues) == overlap, issues
    if not overlap:
        assert issues == []


# 3. 중첩 파라미터(점 표기)

PORT_PARAMS = [
    {"name": "port_mm", "default": 60, "min": 40, "max": 110, "description_ko": "연결부 폭", "description_en": "port"},
    {"name": "wall_mm", "default": 3, "min": 1.5, "max": 6, "description_ko": "벽 두께", "description_en": "wall"},
    {"name": "windows", "default": 2, "min": 0, "max": 4, "description_ko": "창 개수", "description_en": "windows"},
]


def _house_with_tunnel(**house) -> ModuleTemplate:
    hp = {"roof.kind": "pitched", "height_mm": 220, "width_mm": 180, "depth_mm": 150, "ports.sides": ["right"],
          "ports.diameter_mm": {"param": "port_mm"}, "doors.width_mm": {"param": "port_mm"},
          "walls.thickness_mm": {"param": "wall_mm"}, "windows.count": {"param": "windows"}, **house}
    return module(
        [{"id": "house", "template": "house", "params": hp},
         {"id": "tube", "template": "tunnel", "params": {"inner_diameter_mm": {"param": "port_mm"}, "shape": "pointed_arch",
                                                         "length_mm": 100, "wall_thickness_mm": {"param": "wall_mm"}}}],
        [{"parent": "house.right", "child": "tube.end_b", "passage": True}], PORT_PARAMS,
    )


def test_dotted_part_params_set_nested_values(rules):
    t = _house_with_tunnel()
    parts, _ = t.expand(t.Params(port_mm=65.0, wall_mm=4.0, windows=2.4))
    hp = parts[0].params
    assert hp.roof.kind == "pitched" and hp.ports.sides == ["right"] and hp.ports.diameter_mm == 65.0
    assert hp.walls.thickness_mm == 4.0 and hp.doors.width_mm == 65.0
    assert hp.windows.count == 2 and isinstance(hp.windows.count, int)  # 중첩 int 필드로 반올림


def test_dotted_bindings_map_nested_constraints_back(rules):
    """집의 점 표기 제약(ports.diameter_mm, walls.thickness_mm)이 묶인 모듈 파라미터의 하한이 된다."""
    t = _house_with_tunnel()
    c = RuleContext(rules.size_rules("hamster", "syrian"), rules.min_wall_for("hamster", "syrian"))
    cons = t.constraints(t.Params(port_mm=40.0, wall_mm=1.5), c)
    port = max(k.min for k in cons if k.field == "port_mm" and k.min is not None)
    assert port == pytest.approx(max(c.size.tunnel_min_inner_diameter_mm, c.size.entrance_min_diameter_mm))
    assert max(k.min for k in cons if k.field == "wall_mm" and k.min is not None) == pytest.approx(c.min_wall_mm)


def test_house_tunnel_module_builds_and_passes(rules):
    """경사 지붕 집의 연결부 면에 같은 폭의 뾰족 아치 터널: 통로가 연결부를 덮고, 지붕 뚜껑과 겹치지 않는다."""
    t = _house_with_tunnel()
    p = t.Params()
    assert t.rule_issues(p, dwarf(rules)) == []
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    assert {pp.key for pp in t.print_parts(p)} == {"body", "house_roof"}


def test_fixed_nested_value_breaking_a_rule_is_an_error(rules):
    t = _house_with_tunnel(**{"walls.thickness_mm": 1.5})
    assert any("벽 두께" in m for m in t.rule_issues(t.Params(), dwarf(rules)))


@pytest.mark.parametrize("params", [{"roof.knd": "pitched"}, {"roof.kind": "dome"}, {"nope": 1}])
def test_unknown_or_invalid_nested_params_are_rejected_at_load(params):
    with pytest.raises(ValueError):
        module([{"id": "house", "template": "house", "params": params}])


@pytest.mark.parametrize("param,bind", [
    ({"name": "roof", "type": "choice", "choices": ["flat", "dome"], "default": "flat"}, "roof.kind"),
    ({"name": "windows", "type": "int", "default": 2, "min": 0, "max": 9}, "windows.count"),
])
def test_module_param_extremes_must_make_valid_part_params(param, bind):
    """기본값은 맞아도 다른 선택지·최대값이 부품 범위 밖이면 고른 순간 엔진이 멈추므로 불러올 때 거부한다."""
    p = {**param, "description_ko": "x", "description_en": "x"}
    with pytest.raises(ValueError, match=param["name"]):
        module([{"id": "house", "template": "house", "params": {bind: {"param": param["name"]}}}], params=[p])


# 4. 슬라이드 결합 (따로 출력해 도브테일로 끼운다)

def _slide(child: str, child_params: dict, *, anchor: str = "right", child_anchor: str = "back",
           hideout: dict | None = None, **join) -> ModuleTemplate:
    return module([{"id": "hide", "template": "hideout", "params": hideout or {"width_mm": 160, "depth_mm": 130}},
                   {"id": "c", "template": child, "params": child_params}],
                  [{"parent": f"hide.{anchor}", "child": f"c.{child_anchor}", "mount": "slide", **join}])


def _check_printable(t, p, rules, fit: bool = True) -> dict:
    bx, by, bz = rules.printing.build_volume_mm
    out = {}
    for pp in t.print_parts(p):
        pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
        assert mesh_health(pm).ok and pm.body_count == 1, pp.key
        assert overhang_area(pm, rules.printing.max_overhang_deg) <= rules.printing.overhang_area_tolerance_mm2, pp.key
        if fit:
            assert all(a <= b for a, b in zip(sorted(pm.extents[:2]), sorted([bx, by]))) and pm.extents[2] <= bz, pp.key
        out[pp.key] = pp
    return out


def test_slide_definition_rules():
    base = {"key": "s", "name_ko": "a", "name_en": "a", "description_ko": "a", "description_en": "a", "params": [],
            "parts": [{"id": "a", "template": "hideout"}, {"id": "b", "template": "bowl_holder"}]}
    with pytest.raises(ValidationError):
        ModuleDef.model_validate({**base, "joins": [{"parent": "a.right", "child": "b.back", "mount": "slide",
                                                     "passage": True}]})
    with pytest.raises(ValidationError):
        ModuleDef.model_validate({**base, "joins": [{"parent": "a.right", "child": "b.back", "mount": "glued"}]})


def test_slide_bowl_holder_on_hideout(rules):
    t = _slide("bowl_holder", {})
    p = t.Params()
    assert t.rule_issues(p, dwarf(rules)) == []
    # 조립 형상: 은신처 ∪ 연결판 ∪ 그릇 받침 한 덩어리
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    x_face = 160 / 2
    assert m.contains([[x_face + PLATE_MM / 2, 0, 10]])[0]  # 연결판 속
    # 출력 파트: 은신처(+연결판·홈), 그릇 받침(+혀). 각각 서포트 없이 출력
    pps = _check_printable(t, p, rules)
    assert set(pps) == {"body", "c"} and pps["c"].name_ko == "그릇 받침"
    body, bowl = pps["body"].part, pps["c"].part
    assert _volume(body, bowl) < 1.0                               # 혀는 틈새를 두고 홈 안에
    assert bowl.bounding_box().min.X < x_face + PLATE_MM - OVERLAP_MM - 2.0  # 혀가 홈 깊이만큼 벽 쪽으로 나와 있다
    for dy in (0.5, -0.5):
        assert _volume(body, Pos(0, dy, 0) * bowl) > 1.0           # 옆 틈새 ≤ 0.5mm
    assert _volume(body, Pos(1.0, 0, 0) * bowl) > 1.0               # 바깥으로 당겨도 빠지지 않는다 (도브테일)
    assert _volume(body, Pos(0, 0, 60) * bowl) < 1.0                # 위로는 빠진다 (홈 위아래가 트였다)
    # 특징: 연결 지점은 쓰인 것으로, 출입 면은 돌려서
    f = t.features(p)
    assert "right" in f.access_sides and "front" in f.access_sides


def test_slide_child_wider_than_face_is_an_error(rules):
    t = _slide("bowl_holder", {"bowl_diameter_mm": 140})  # 외형 폭 148 > 은신처 옆면 130
    assert any("넓거나" in m for m in t.rule_issues(t.Params(), dwarf(rules)))


def test_slide_on_door_face_or_top_is_an_error(rules):
    t = _slide("bowl_holder", {}, anchor="front")
    assert t.rule_issues(t.Params(), dwarf(rules))
    t = _slide("bowl_holder", {}, anchor="top", child_anchor="bottom")
    assert any("옆면끼리만" in m for m in t.rule_issues(t.Params(), dwarf(rules)))
    with pytest.raises(AssemblyError):
        t.build(t.Params())
    t = _slide("bowl_holder", {}, lift=10)
    assert any("같은 바닥" in m for m in t.rule_issues(t.Params(), dwarf(rules)))


def test_slide_ramp_landing_flush_with_hideout_roof(rules):
    """은신처 높이와 같은 램프: 연결판 윗면이 은신처 지붕·램프 발판과 같은 높이 (경사 없이)."""
    t = _slide("ramp", {"height_mm": 90, "width_mm": 70, "slope_deg": 30}, child_anchor="landing",
               hideout={"width_mm": 140, "depth_mm": 110, "height_mm": 90})
    p = t.Params()
    assert t.rule_issues(p, dwarf(rules)) == []
    plan = next(iter(t._layout(p).plans.values()))
    assert plan.top == pytest.approx(90) and plan.h == pytest.approx(90)
    pps = _check_printable(t, p, rules)
    bb = pps["body"].part.bounding_box()
    assert bb.max.Z == pytest.approx(90, abs=1e-6) and bb.max.X == pytest.approx(70 + PLATE_MM - OVERLAP_MM, abs=1e-3)
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1 and m.bounds[1][2] == pytest.approx(90, abs=1e-6)


def test_slide_bottle_stand_tongue_on_holder_part(rules):
    """물병 거치대: 혀는 연결판에 가장 넓게 닿는 물병 컵(뒤판) 파트에 붙고, 받침판은 그대로."""
    t = _slide("bottle_stand", {})
    p = t.Params()
    assert t.rule_issues(p, dwarf(rules)) == []
    pps = _check_printable(t, p, rules)
    assert set(pps) == {"body", "c_base", "c_holder"}
    back = 160 / 2 + PLATE_MM - OVERLAP_MM
    assert pps["c_holder"].part.bounding_box().min.X < back - 2.0
    assert pps["c_base"].part.bounding_box().min.X == pytest.approx(back, abs=1e-3)
    for key in ("c_base", "c_holder"):
        assert _volume(pps["body"].part, pps[key].part) < 1.0
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1


def test_slide_gap_above_plate_follows_species_rule(rules):
    """연결판보다 높은 부품: 연결판 위로 벽과 부품 뒷면 사이에 PLATE − OVERLAP 틈이 남는다. 햄스터 기준(4mm)보다 작고,
    더 엄격한 기준이면 오류."""
    t = module([{"id": "house", "template": "house", "params": PITCHED_HOUSE},
                {"id": "ramp", "template": "ramp", "params": {"height_mm": 120, "width_mm": 60, "slope_deg": 30}}],
               [{"parent": "house.right", "child": "ramp.landing", "mount": "slide"}])
    p = t.Params()
    c = dwarf(rules)
    assert t.rule_issues(p, c) == []
    strict = RuleContext(c.size.model_copy(update={"gap_trap": GapTrapRule(safe_max_mm=2.0, passable_min_mm=50)}),
                         c.min_wall_mm)
    assert any("끼임 위험" in m for m in t._geometry_issues(p, strict))
    _check_printable(t, p, rules, fit=False)  # 120mm 램프는 길이가 출력 공간보다 길다 (램프 자체의 문제)


@pytest.mark.parametrize("anchor,trap", [("back", True), ("right", False)])
def test_slide_child_above_sloped_roof_eave_is_a_trap(rules, anchor, trap):
    """경사 지붕 집의 처마 쪽 면(뒤)에 처마보다 높은 물병 거치대: 지붕 경사면과 거치대 뒷면 사이에 위로 벌어지는 쐐기 틈
    (지붕에서 미끄러진 다리가 낀다). 박공 면(오른쪽)은 박공판이 스커트와 같은 면이라 틈이 0.7mm 로 좁다."""
    t = module([{"id": "house", "template": "house",
                 "params": {"roof.kind": "pitched", "height_mm": 200, "width_mm": 180, "depth_mm": 150}},
                {"id": "c", "template": "bottle_stand", "params": {}}],
               [{"parent": f"house.{anchor}", "child": "c.back", "mount": "slide"}])
    issues = t.rule_issues(t.Params(), dwarf(rules))
    assert any("벌어지는 틈" in m for m in issues) == trap, issues
    if not trap:
        assert issues == []

