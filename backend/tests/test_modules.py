"""모듈 라이브러리: 라이브러리의 모든 조립 모듈을 기본값과 크기 범위 끝값으로 만들어 기준을 확인한다.

새 모듈 파일(app/modules/library/*.json)을 넣으면 여기서 함께 검사된다.
"""

from __future__ import annotations

import itertools
import json

import numpy as np
import pytest

from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.modules.assembly import AssemblyError, JoinSpec, PartSpec, merge_features, place_parts
from app.modules.definition import ModuleDef, library
from app.modules.module_template import ModuleTemplate
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.domain import Cage
from app.templates.base import RuleContext
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
