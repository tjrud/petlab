"""조립 엔진(app/modules/assembly, AssemblyTemplate): 연결 지점끼리 잇기, 통로, 슬라이드·끼움 결합, 형상 검사.

부품과 결합을 그대로 적은 시험용 조립(Inline)으로 엔진 기능을 본다. 조립 해석기(app/modules/compose)가 고르지 않는
결합(한 덩어리 fused, 문 없는 옆벽에 낸 통로, 띄운 자식 등)도 엔진은 다룰 수 있어야 하므로 해석기를 거치지 않는다.
자유 조립(해석기 → ComposedTemplate)의 안전 기준은 tests/test_presets.py, 결합 표는 tests/test_compose.py 가 본다.
"""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import pytest
from build123d import Pos
from pydantic import ValidationError

from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.modules.assembly import (
    OVERLAP_MM,
    PLATE_MM,
    AssemblyError,
    JoinSpec,
    PartSpec,
    join_problems,
    merge_features,
    place_parts,
    plug_problems,
    slide_problems,
)
from app.modules.module_template import AssemblyTemplate
from app.modules.structure import ResolvedJoin
from app.rules.loader import GapTrapRule
from app.templates.base import RuleContext, TemplateParams
from app.templates.hideout import HideoutParams, HideoutTemplate
from app.templates.registry import primitives
from app.templates.tunnel import TunnelParams, TunnelTemplate
from app.validation.checks import overhang_area

PARTS = primitives()


class NoParams(TemplateParams):
    """시험용 조립은 파라미터가 없다 (부품 값은 정의에 적은 그대로)."""


def _set(values: dict, path: str, value: Any) -> None:
    *heads, last = path.split(".")
    for name in heads:
        values = values[name]
    values[last] = value


class Inline(AssemblyTemplate):
    """부품(템플릿 기본값 + 적은 값, 점 표기 경로 가능)과 결합을 그대로 적은 시험용 조립.

    결합: {"parent": "a.front", "child": "t.end_b", "passage": False | True | "into_child",
           "mount": "fused" | "slide" | "plug", "shift": mm, "lift": mm}.
    규칙: 부품 규칙 + 조립 규칙(연결 지점·슬라이드·끼움), 그것이 맞으면 형상 검사 (ComposedTemplate 과 같은 순서)."""

    key = "inline_test"
    display_name_ko = "시험 조립"
    Params = NoParams

    def __init__(self, parts: list[dict], joins: list[dict] = (), enclosure: bool = False):
        super().__init__()
        self._parts: list[PartSpec] = []
        for d in parts:
            t = PARTS[d["template"]]
            base = t.default_params().model_dump()
            for path, v in d.get("params", {}).items():
                _set(base, path, v)
            self._parts.append(PartSpec(d["id"], t, t.Params.model_validate(base)))
        self._joins = [
            JoinSpec(j["parent"].split(".")[0], j["parent"].split(".")[1], j["child"].split(".")[0],
                     j["child"].split(".")[1], shift=j.get("shift", 0.0), lift=j.get("lift", 0.0),
                     passage=bool(j.get("passage", False)), mount=j.get("mount", "fused"),
                     reverse=j.get("passage") == "into_child")
            for j in joins
        ]
        self._enclosure = enclosure

    def expand(self, p: TemplateParams) -> tuple[list[PartSpec], list[JoinSpec]]:
        return list(self._parts), list(self._joins)

    @property
    def enclosure(self) -> bool:
        return self._enclosure

    @property
    def has_slide(self) -> bool:
        return any(j.slide for j in self._joins)

    @property
    def split(self) -> bool:
        return any(j.mount in ("slide", "plug") for j in self._joins)

    def constraints(self, p: TemplateParams, ctx: RuleContext) -> list:
        return []

    def rule_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        parts, joins = self.expand(p)
        out: list[str] = []
        for q in parts:
            out += [f"{q.template.display_name_ko}({q.id}): {m}" for m in q.template.rule_issues(q.params, ctx)]
        out += join_problems(parts, joins) + slide_problems(parts, joins) + plug_problems(parts, joins)
        if not out:
            out += self._geometry_rule_issues(p, ctx)
        return out


def module(parts: list[dict], joins: list[dict] = ()) -> Inline:
    return Inline(parts, joins)


def ctx(rules, species="hamster", size="syrian") -> RuleContext:
    return RuleContext(rules.size_rules(species, size), rules.min_wall_for(species, size))


def dwarf(rules) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", "dwarf"), rules.min_wall_for("hamster", "dwarf"),
                       printing_max_overhang_deg=rules.printing.max_overhang_deg)


def _volume(a, b) -> float:
    inter = a & b
    return float(inter.volume) if inter is not None else 0.0


# ── 연결 지점끼리 잇기 ─────────────────────────────────────────

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


@pytest.mark.parametrize("a,b", list(itertools.combinations(["front", "back", "left", "right"], 2)))
def test_side_names_survive_rotation(a, b):
    """옆면 이름 ↔ 방향 변환이 서로 맞다 (조립 특징의 출입 면 계산)."""
    from app.modules.assembly import _SIDE_VEC, _side_of

    assert _side_of(np.asarray(_SIDE_VEC[a], dtype=float)) == a
    assert _side_of(np.asarray(_SIDE_VEC[b], dtype=float)) == b


def test_blocking_an_entrance_without_a_passage_is_an_error(rules):
    t = module([{"id": "a", "template": "hideout"}, {"id": "b", "template": "hideout"}],
               [{"parent": "a.front", "child": "b.left"}])
    assert any("막습니다" in m for m in t.rule_issues(t.Params(), ctx(rules)))


# 1. 통로가 출입구를 다 덮는지

def _tunnel_into(parent: str, parent_params: dict, anchor: str, shape: str, d: float) -> Inline:
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


# 3. 중첩 파라미터(점 표기)로 정한 집 연결부

def _house_with_tunnel(**house) -> Inline:
    """경사 지붕 집의 오른쪽 연결부(점 표기로 정한 중첩 파라미터)에 같은 폭의 뾰족 아치 터널을 한 덩어리 통로로."""
    hp = {"roof.kind": "pitched", "height_mm": 220, "width_mm": 180, "depth_mm": 150, "ports.sides": ["right"],
          "ports.diameter_mm": 60, "doors.width_mm": 60, "walls.thickness_mm": 3, "windows.count": 2, **house}
    return module(
        [{"id": "house", "template": "house", "params": hp},
         {"id": "tube", "template": "tunnel", "params": {"inner_diameter_mm": 60, "shape": "pointed_arch",
                                                         "length_mm": 100, "wall_thickness_mm": 3}}],
        [{"parent": "house.right", "child": "tube.end_b", "passage": True}],
    )


def test_house_tunnel_module_builds_and_passes(rules):
    """경사 지붕 집의 연결부 면에 같은 폭의 뾰족 아치 터널: 통로가 연결부를 덮고, 지붕 뚜껑과 겹치지 않는다."""
    t = _house_with_tunnel()
    p = t.Params()
    assert t.rule_issues(p, dwarf(rules)) == []
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    assert {pp.key for pp in t.print_parts(p)} == {"body", "house_roof"}


# 4. 슬라이드 결합 (따로 출력해 도브테일로 끼운다)


def test_slide_join_spelling():
    """저장 형태의 결합: 슬라이드는 통로가 아니고, 끼움은 통로로만, 모르는 결합 방식은 받지 않는다."""
    with pytest.raises(ValidationError):
        ResolvedJoin(parent="a.right", child="b.back", mount="slide", passage="into_parent")
    with pytest.raises(ValidationError):
        ResolvedJoin(parent="a.right", child="b.back", mount="glued", passage=False)


def _slide(child: str, child_params: dict, *, anchor: str = "right", child_anchor: str = "back",
           hideout: dict | None = None, **join) -> Inline:
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


# 5. 모래목욕통 앞면에 슬라이드로 붙인 턱 높이 램프

def test_slide_ramp_on_sand_bath_front_lands_at_the_lip(rules):
    """앞면 연결판은 턱 높이 아래에서 경사로 끝나 출입 홈을 덮지 않고, 턱 높이 램프의 발판이 턱 윗면 높이에 닿는다.
    출입 면은 모래목욕통 앞면(이어져 빠진다)에서 램프 입구로 넘어간다."""
    from app.modules.assembly import SLOPE_RISE
    from app.templates.sand_bath import SandBathParams

    sp = SandBathParams()
    lip, D, t_w = sp.lip_height_mm, sp.depth_mm, sp.wall_thickness_mm
    t = module([{"id": "bath", "template": "sand_bath", "params": {}},
                {"id": "ramp", "template": "ramp", "params": {"height_mm": lip, "width_mm": 80, "slope_deg": 25}}],
               [{"parent": "bath.front", "child": "ramp.landing", "mount": "slide"}])
    p = t.Params()
    assert t.rule_issues(p, dwarf(rules)) == []
    plan = next(iter(t._layout(p).plans.values()))
    assert plan.top == pytest.approx(lip) and plan.h == pytest.approx(lip - SLOPE_RISE * (PLATE_MM - OVERLAP_MM))
    pps = _check_printable(t, p, rules)
    assert set(pps) == {"body", "ramp"}
    assert pps["ramp"].part.bounding_box().max.Z == pytest.approx(lip, abs=1e-6)  # 발판 = 턱 윗면 높이
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    # 출입 홈(턱 위)과 그 앞은 비어 있다: 연결판이 홈을 덮지 않는다
    y_wall = -D / 2
    probes = [[0, y_wall + t_w / 2, lip + 1], [0, y_wall - 1.0, lip + 1], [0, y_wall - 3.0, lip + 0.5]]
    assert not m.contains(probes).any()
    assert m.contains([[0, y_wall - 1.0, lip - 2.0]])[0]  # 연결판 경사 끝 (벽에서 1mm: 턱 − 1.2mm 높이까지)
    f = t.features(p)
    assert f.access_sides == ("front",)  # 램프 입구 (앞, -Y)
    parts, joins = t.expand(p)
    entry = parts[1].template.anchors(parts[1].params)["entry"]
    assert place_parts(parts, joins)["ramp"].point(entry.origin)[1] < y_wall - 50  # 램프 입구가 앞쪽 바깥에


# 6. 거꾸로 통로 (passage="into_child") 와 끼움 결합 (mount="plug")

def _tunnel(shape: str = "pointed_arch", **kw) -> dict:
    return {"length_mm": 120, "inner_diameter_mm": 60, "shape": shape, "wall_thickness_mm": 3, **kw}


def _twin(shape: str = "pointed_arch", mount: str = "plug", hideout: dict | None = None, **tunnel) -> Inline:
    """은신처 A 앞문 ← 터널 → 은신처 B 앞문. 터널 끝(end_a)이 부모라 B 의 벽은 거꾸로 통로로 뚫는다."""
    h = hideout or {"entrance_count": 2}
    return module([{"id": "a", "template": "hideout", "params": h},
                   {"id": "tube", "template": "tunnel", "params": _tunnel(shape, **tunnel)},
                   {"id": "b", "template": "hideout", "params": h}],
                  [{"parent": "a.front", "child": "tube.end_b", "passage": True, "mount": mount},
                   {"parent": "tube.end_a", "child": "b.front", "passage": "into_child", "mount": mount}])


def test_passage_and_plug_join_spelling():
    """저장 형태의 결합: 거꾸로 통로(into_child)는 reverse, 끼움은 통로가 있어야 하고, 모르는 통로 값은 받지 않는다."""
    j = ResolvedJoin(parent="a.end_a", child="b.front", mount="plug", passage="into_child")
    assert j.reverse and j.join_spec().reverse and j.join_spec().plug and j.join_spec().passage
    assert not ResolvedJoin(parent="a.end_a", child="b.front", mount="plug", passage="into_parent").reverse
    for bad in ({"mount": "plug", "passage": False}, {"mount": "plug", "passage": "sideways"}):
        with pytest.raises(ValidationError):
            ResolvedJoin(parent="a.end_a", child="b.front", **bad)


def test_reverse_passage_cuts_the_child_wall_and_counts_exits(rules):
    """터널 끝(부모)에 이은 은신처 B(자식)의 앞벽을 터널 통로 단면으로 뚫는다. 이은 출입구·터널 끝은 바깥 출입구에서 빠진다."""
    t = _twin(mount="fused")
    p = t.Params()
    assert t.rule_issues(p, dwarf(rules)) == []
    parts, joins = t.expand(p)
    placed = place_parts(parts, joins)
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    # B 앞벽 두께 가운데, 은신처 출입구(둥근 아치, 높이 60) 위 뾰족 아치 터널 통로 높이: 뚫려 있어야 한다
    b = placed["b"]
    wall = b.point((0, -110 / 2 + 1.5, 68))
    assert not m.contains([wall])[0]
    assert m.contains([b.point((0, -110 / 2 + 1.5, 82))])[0]  # 터널 꼭대기 위는 벽
    f = merge_features(parts, joins, enclosure=True)
    assert f.entrance_count == 2  # 두 은신처의 뒷문
    # 방향을 반대로 적으면 (터널 끝은 뚫을 수 없고, 은신처 앞면은 벽이 통로 쪽이 된다) 오류
    wrong = module([{"id": "tube", "template": "tunnel", "params": _tunnel()}, {"id": "b", "template": "hideout"}],
                   [{"parent": "tube.end_a", "child": "b.front", "passage": True}])
    assert any("뚫을 수 없습니다" in m for m in wrong.rule_issues(wrong.Params(), dwarf(rules)))


@pytest.mark.parametrize("shape,gap", [("pointed_arch", False), ("tube", True)])
def test_reverse_passage_must_cover_the_child_door(rules, shape, gap):
    """거꾸로 통로도 자식 출입구를 덮는지 본다: 관은 은신처 출입구(둥근 아치) 아래 모서리를 남긴다."""
    t = module([{"id": "tube", "template": "tunnel", "params": _tunnel(shape)}, {"id": "b", "template": "hideout"}],
               [{"parent": "tube.end_a", "child": "b.front", "passage": "into_child"}])
    issues = t.rule_issues(t.Params(), dwarf(rules))
    assert any("틈이 남습니다" in m for m in issues) == gap, issues


def _check_tunnel_printable(t, p, rules, overhang: bool = True) -> dict:
    """출력 파트마다 닫힌 한 덩어리·프린터 크기, 터널 파트는 오버행까지. 은신처 옆벽에 낸 둥근 구멍(관)은 뒤집어 출력하면
    구멍 위쪽이 오버행이라 (통로 연결 자체의 문제) 은신처 파트의 오버행은 보지 않는다."""
    bx, by, bz = rules.printing.build_volume_mm
    out = {}
    for pp in t.print_parts(p):
        pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
        assert mesh_health(pm).ok and pm.body_count == 1, pp.key
        assert all(a <= b for a, b in zip(sorted(pm.extents[:2]), sorted([bx, by]))) and pm.extents[2] <= bz, pp.key
        if overhang and pp.key == "tube":
            assert overhang_area(pm, rules.printing.max_overhang_deg) <= rules.printing.overhang_area_tolerance_mm2
        out[pp.key] = pp
    return out


def _pairwise_overlap(pps) -> float:
    return max((_volume(a.part, b.part) for a, b in itertools.combinations(pps, 2)), default=0.0)


def test_plug_twin_hideouts_print_as_three_parts(rules):
    """은신처 110 + 터널 120 + 은신처 110mm 는 한 덩어리로 출력할 수 없다: 터널을 따로 출력해 양쪽 출입구에 끼운다."""
    t = _twin()
    p = t.Params()
    assert t.rule_issues(p, dwarf(rules)) == []
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1 and len(t.build(p).solids()) == 1
    pps = _check_printable(t, p, rules)
    assert set(pps) == {"body", "tube", "b"} and pps["tube"].name_ko == "터널" and pps["b"].name_ko == "은신처"
    assert _pairwise_overlap(list(pps.values())) < 1.0
    # 터널은 뾰족 아치라 사용 자세 그대로 (끼움 턱이 옆을 본다), 은신처는 뒤집어
    assert np.allclose(pps["tube"].rotation, np.eye(3)) and np.allclose(pps["b"].rotation, np.diag([1.0, -1.0, -1.0]))
    # 끼움 턱이 은신처 벽 속으로 (벽 두께 − 0.3) 들어간다: 터널 출력 파트가 은신처 앞면보다 2.7mm 벽 쪽으로
    from app.modules.assembly import PLUG_TIP_GAP_MM

    parts, joins = t.expand(p)
    tube_bb = pps["tube"].part.bounding_box()
    a_front_y = place_parts(parts, joins)["a"].point((0, -110 / 2, 0))[1]
    assert tube_bb.max.Y == pytest.approx(a_front_y + 3 - PLUG_TIP_GAP_MM, abs=0.05)
    f = merge_features(parts, joins, enclosure=True)
    assert f.entrance_count == 2


def test_plug_spigot_fits_the_hole_with_clearance(rules):
    """끼움 턱과 넓힌 구멍 사이 틈새 PLUG_CLEARANCE_MM: 0.15mm 옮겨도 겹치지 않고 0.5mm 옮기면 걸린다.
    터널 쪽으로 벽에 0.5mm 밀면 끝 고리가 벽 면에 걸린다."""
    from app.modules.assembly import PLUG_CLEARANCE_MM, anchor_frame

    assert PLUG_CLEARANCE_MM == pytest.approx(0.2)
    t = _twin()
    p = t.Params()
    pps = {pp.key: pp.part for pp in t.print_parts(p)}
    parts, joins = t.expand(p)
    _, tt, u, n = anchor_frame(place_parts(parts, joins), "a", "front")
    body, tube = pps["body"], pps["tube"]
    for d in (tt, -tt, u):
        assert _volume(body, Pos(*(d * 0.15)) * tube) < 1.0
        assert _volume(body, Pos(*(d * 0.5)) * tube) > 1.0
    assert _volume(body, Pos(*(-n * 0.5)) * tube) > 1.0


def test_plug_into_a_too_wide_door_is_an_error(rules):
    """터널 벽 고리가 출입구를 덮지 못하면 (60mm 출입구에 바깥 반폭 28mm 터널) 끼움 결합도 틈 오류."""
    t = _twin(inner_diameter_mm=50)
    assert any("끼움 구멍을 다 덮지 못해" in m for m in t.rule_issues(t.Params(), dwarf(rules)))


def test_plug_rule_issues_for_thin_walls(rules):
    """터널 벽이 끼움 턱 + 틈새 + 고리(2.2mm)보다 얇거나, 은신처 벽이 얇아 끼움 턱이 2mm 보다 짧으면 오류."""
    t = _twin(wall_thickness_mm=2.0)
    assert any("끼움 턱과 틈새" in m for m in t.rule_issues(t.Params(), dwarf(rules)))
    t = _twin(hideout={"entrance_count": 2, "wall_thickness_mm": 2.0})
    assert any("끼움 턱이 너무 짧습니다" in m for m in t.rule_issues(t.Params(), dwarf(rules)))


@pytest.mark.parametrize("shape", ["pointed_arch", "round_arch", "tube", "box", "house"])
@pytest.mark.parametrize("bend", [0, 90])
def test_plug_each_tunnel_shape(rules, shape, bend):
    """출입구 없는 은신처 옆벽에 터널을 끼움 결합으로: 넓힌 구멍은 어느 단면이든 터널 벽 고리가 덮는다.
    곧은 둥근 아치·관·네모는 세워 출력하고 끼움 턱이 위를 본다. 휘면 세울 수 없어 서포트가 필요한 단면은 오버행을 보지 않는다."""
    from app.templates.tunnel import NEEDS_STANDING

    t = module([{"id": "h", "template": "hideout", "params": {"depth_mm": 110}},
                {"id": "tube", "template": "tunnel", "params": _tunnel(shape, bend_angle_deg=bend)}],
               [{"parent": "h.right", "child": "tube.end_b", "passage": True, "mount": "plug"}])
    p = t.Params()
    issues = t.rule_issues(p, dwarf(rules))
    if bend == 0:
        assert issues == []
    else:
        # 90° 휜 터널 안쪽과 은신처 옆벽 사이 주머니는 끼임 틈이다 (slot_gaps 는 이은 쌍도 이은 자리만 빼고 본다)
        assert issues and all("끼임 위험" in m for m in issues), issues
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    _check_tunnel_printable(t, p, rules, overhang=not (shape in NEEDS_STANDING and bend > 0))
    pps = t.print_parts(p)
    assert len(pps) == 2 and _pairwise_overlap(pps) < 1.0
    tube = next(pp for pp in pps if pp.key == "tube")
    if shape in NEEDS_STANDING and bend == 0:
        # 끼움 턱(조립 좌표 −X 쪽 끝)이 출력 자세에서 위를 본다
        assert float((tube.rotation @ np.array([-1.0, 0, 0]))[2]) > 0.5


@pytest.mark.parametrize("shape", ["tube", "round_arch", "box"])
def test_plug_both_ends_of_a_standing_tunnel(rules, shape):
    """양 끝을 끼우는 곧은 관·둥근 아치·네모 터널: 세우면 한쪽 끼움 턱이 아래를 본다. 그 끝 둘레는 깔때기로 깎아 서포트 없이
    출력하고, 넓힌 구멍 가장자리에는 틈새만큼의 실금만 남는다 (출입구 없는 옆벽끼리라 출입구 모양 차이는 없다)."""
    side = {"entrance_count": 1, "depth_mm": 110}
    t = module([{"id": "a", "template": "hideout", "params": side},
                {"id": "tube", "template": "tunnel", "params": _tunnel(shape)},
                {"id": "b", "template": "hideout", "params": side}],
               [{"parent": "a.right", "child": "tube.end_b", "passage": True, "mount": "plug"},
                {"parent": "tube.end_a", "child": "b.left", "passage": "into_child", "mount": "plug"}])
    p = t.Params()
    assert t.rule_issues(p, dwarf(rules)) == []
    pps = _check_tunnel_printable(t, p, rules)
    assert _pairwise_overlap(list(pps.values())) < 1.0
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    # 세워 출력하는 터널: 한쪽 끼움 턱은 위, 다른 쪽(깔때기로 깎은 끝)은 아래
    from app.modules.assembly import anchor_frame

    parts, joins = t.expand(p)
    placed = place_parts(parts, joins)
    rot = pps["tube"].rotation
    zs = sorted(float((rot @ anchor_frame(placed, *j.port_end)[3])[2]) for j in joins)
    assert zs[0] < -0.5 and zs[1] > 0.5
    # 깎은 끝도 출력 파트 그대로 넓힌 구멍을 덮는다 (남는 곳은 틈새 폭의 실금)
    from app.modules.assembly import leftover_width, passage_leftover
    from app.modules.module_template import LEFTOVER_MIN_WIDTH_MM

    for j in joins:
        left = passage_leftover(placed, j, pps["tube"].part)
        assert left.volume < 1.0 or leftover_width(left, placed, j) <= LEFTOVER_MIN_WIDTH_MM


@pytest.mark.parametrize("reverse", [False, True])
def test_fused_passage_into_a_bent_tunnel_is_watertight(rules, reverse):
    """휜 터널 끝은 안쪽 곡면이 곧은 통로 기둥과 맞닿아 형상 커널이 닫히지 않은 형상을 낸다: 통로를 합치기 전에 조금 넓혀
    뚫는 방식으로 다시 만든다 (조립 형상과, 따로 출력하는 묶음이 있으면 그 출력 파트도)."""
    tp = _tunnel(bend_angle_deg=90)
    if reverse:
        t = module([{"id": "tube", "template": "tunnel", "params": tp},
                    {"id": "b", "template": "hideout", "params": {"entrance_count": 2}}],
                   [{"parent": "tube.end_a", "child": "b.front", "passage": "into_child"}])
    else:
        t = module([{"id": "a", "template": "hideout", "params": {"entrance_count": 2}},
                    {"id": "tube", "template": "tunnel", "params": tp}],
                   [{"parent": "a.front", "child": "tube.end_b", "passage": True}])
    p = t.Params()
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
    assert t.rule_issues(p, dwarf(rules)) == []


def test_bent_fused_passage_inside_a_plug_group_prints_closed(rules):
    """은신처 A ← (끼움) 휜 터널 → (한 덩어리, 거꾸로 통로) 은신처 B: 터널·B 묶음 출력 파트도 닫힌 한 덩어리."""
    t = module([{"id": "a", "template": "hideout", "params": {"entrance_count": 2}},
                {"id": "tube", "template": "tunnel", "params": _tunnel(bend_angle_deg=90)},
                {"id": "b", "template": "hideout", "params": {"entrance_count": 2}}],
               [{"parent": "a.front", "child": "tube.end_b", "passage": True, "mount": "plug"},
                {"parent": "tube.end_a", "child": "b.front", "passage": "into_child"}])
    p = t.Params()
    pps = {pp.key: pp for pp in t.print_parts(p)}
    assert set(pps) == {"body", "tube"}
    for pp in pps.values():
        pm = to_print_orientation(part_to_mesh(pp.part), pp.rotation)
        assert mesh_health(pm).ok and pm.body_count == 1, pp.key
    assert _pairwise_overlap(list(pps.values())) < 1.0
    m = part_to_mesh(t.build(p))
    assert mesh_health(m).ok and m.body_count == 1
