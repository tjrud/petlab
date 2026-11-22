"""모듈 라이브러리 전체에 걸친 검사: 모의 해석기 낱말 충돌, 모듈 색, 허용 목록, 일부러 얇게 만든 결합 모양의 두께 측정,
공간 보정이 규칙을 어기는 크기를 고르지 않는지."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
import trimesh

from app.domain import Cage
from app.geometry.mesh import part_to_mesh
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.modules.definition import library
from app.services.engine import EngineContext, ItemSpec, run_engine
from app.templates.registry import get_template
from app.validation.checks import measure_thickness

FRONTEND_TEMPLATES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "templates.ts"


def _interpret(rules, prompt: str, language: str = "ko", size: str = "dwarf") -> list[str]:
    entry = rules.species_entry("hamster")
    req = InterpretRequest(
        prompt=prompt,
        habitat=HabitatInfo("hamster", entry.display_name, size, 1, Cage(800, 500, 400), habitat=entry.habitat),
        size_rules=rules.size_rules("hamster", size), min_wall_mm=rules.min_wall_for("hamster", size),
        language=language, allowed_templates=rules.allowed_templates("hamster"),
    )
    return [it.template for it in MockInterpreter().interpret(req).spec.items]


def test_every_library_module_is_allowed_for_hamsters(rules):
    """모듈은 쓰는 부품이 모두 허용된 종에 함께 허용된다 (햄스터 케이지는 모든 부품을 쓴다)."""
    allowed = rules.allowed_templates("hamster")
    assert {m.key for m in library()} <= set(allowed)
    assert not {m.key for m in library()} & set(rules.allowed_templates("aquarium"))


@pytest.mark.parametrize("prompt,expected", [
    # 기본 부품 낱말만 있으면 기본 부품
    ("은신처", ["hideout"]),
    ("터널", ["tunnel"]),
    ("모래목욕통", ["sand_bath"]),
    ("은신처 두 개", ["hideout"]),
    ("2층 집", ["house"]),
    ("집 모양 터널", ["tunnel"]),
    # 붙인다는 말이 없으면 따로 놓는 구조물
    ("밥그릇이랑 은신처", ["bowl_holder", "hideout"]),
    ("은신처와 물병 거치대를 만들어 주세요", ["hideout", "bottle_stand"]),
    ("모래목욕통이랑 경사로", ["sand_bath", "ramp"]),
    ("2층 집에 물병 거치대 붙여 주세요", ["house", "bottle_stand"]),
    ("경사로 달린 집", ["ramp", "hideout"]),
    # 모듈
    ("밥그릇 달린 은신처", ["hideout_with_bowl"]),
    ("물병 달린 은신처", ["hideout_with_bottle"]),
    ("밥그릇과 물병 달린 은신처", ["dining_hideout"]),
    ("물병과 밥그릇이 달린 은신처", ["dining_hideout"]),
    ("물병이랑 그릇 붙은 은신처", ["dining_hideout"]),
    ("터널 달린 은신처", ["hideout_with_tunnel"]),
    ("터널로 이은 쌍둥이 은신처", ["twin_hideouts"]),
    ("터널 달린 집", ["house_with_tunnel"]),
    ("경사로 달린 은신처", ["hideout_with_ramp"]),
    ("경사로 달린 모래목욕통", ["sand_bath_with_ramp"]),
    # 모듈 여럿
    ("터널 달린 은신처와 밥그릇과 물병이 달린 은신처", ["hideout_with_tunnel", "dining_hideout"]),
    ("물병 달린 은신처랑 터널 달린 은신처", ["hideout_with_bottle", "hideout_with_tunnel"]),
])
def test_mock_keywords_do_not_collide_ko(rules, prompt, expected):
    assert _interpret(rules, prompt) == expected


@pytest.mark.parametrize("prompt,expected", [
    ("a hideout", ["hideout"]),
    ("a tunnel", ["tunnel"]),
    ("a sand bath", ["sand_bath"]),
    ("a hideout with a bowl", ["hideout_with_bowl"]),
    ("hideout with a bowl and a water bottle", ["dining_hideout"]),
    ("a ramp with a bowl attached", ["ramp", "bowl_holder"]),
    ("Twin hideouts joined by a tunnel", ["twin_hideouts"]),
    ("a house with a tunnel attached", ["house_with_tunnel"]),
    ("a hideout with a tunnel", ["hideout_with_tunnel"]),
    ("a ramp up to the roof of the hideout", ["hideout_with_ramp"]),
    ("house with a ramp to the roof", ["hideout", "ramp"]),
    ("a sandbath with a ramp", ["sand_bath_with_ramp"]),
])
def test_mock_keywords_do_not_collide_en(rules, prompt, expected):
    assert _interpret(rules, prompt, language="en") == expected


def _lab(color: str) -> np.ndarray:
    rgb = np.array([int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    lin = np.where(rgb > 0.04045, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    xyz = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]) @ lin
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def test_module_colors_are_distinct():
    """뷰어에서 구조물을 색으로 가려 보도록 모듈 색은 서로, 그리고 기본 부품 색(프런트엔드 TEMPLATE_COLORS)과 다르다
    (CIE76 색 차이 15 이상: 같은 계열로 보이지 않는 정도)."""
    colors = {m.key: m.color for m in library()}
    assert all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in colors.values()), colors
    others = dict(colors)
    if FRONTEND_TEMPLATES.exists():
        block = FRONTEND_TEMPLATES.read_text().split("TEMPLATE_COLORS")[1].split("};")[0]
        others |= {k: c for k, c in re.findall(r"(\w+): \"(#[0-9a-f]{6})\"", block)}
    for key, c in colors.items():
        for other, c2 in others.items():
            # 처음 공개한 터널 달린 은신처는 은신처 계열 색 그대로 둔다 (기본 부품 색과의 비교만 빼고 다른 모듈과는 비교한다)
            if other != key and not (key == "hideout_with_tunnel" and other not in colors):
                assert np.linalg.norm(_lab(c) - _lab(c2)) >= 15, (key, c, other, c2)


def test_thickness_measure_skips_only_designed_thin_features():
    """끼움 턱·도브테일 혀처럼 일부러 얇게 만든 모양(PrintPart.thin_ok)의 표면 샘플만 뺀다: 같은 얇은 지느러미도 빼라고
    준 모양이 아니면 그대로 잡힌다."""
    plate = trimesh.creation.box((40, 40, 6))
    fin = trimesh.creation.box((1.2, 20, 10))
    fin.apply_translation([0, 0, 8])  # 판 윗면(z=3)에 선 1.2mm 지느러미 (광선 두께 측정에는 두 메시를 이어 붙이면 된다)
    mesh = trimesh.util.concatenate([plate, fin])
    far = trimesh.creation.box((5, 5, 5))
    far.apply_translation([100, 0, 0])
    assert np.percentile(measure_thickness(mesh), 1) < 2.0
    assert np.percentile(measure_thickness(mesh, exclude=far), 1) < 2.0
    assert np.percentile(measure_thickness(mesh, exclude=fin), 1) > 5.0


@pytest.mark.parametrize("key,part,count", [
    ("twin_hideouts", "tube", 3),          # 양 끝 끼움 턱 + 세워 출력하는 아래 끝 깔때기
    ("house_with_tunnel", "tube", 1),      # 끼움 턱
    ("hideout_with_bowl", "bowl", 1),      # 도브테일 혀
    ("hideout_with_bottle", "bottle_holder", 1),  # 혀는 연결판에 가장 넓게 닿는 물병 컵에
])
def test_print_parts_carry_their_thin_joint_features(rules, key, part, count):
    t = get_template(key)
    pps = {pp.key: pp for pp in t.print_parts(t.Params())}
    assert len(pps[part].thin_ok) == count
    assert all(not pp.thin_ok for k, pp in pps.items() if k != part)
    # 뺀 샘플은 파트 표면의 일부뿐이고, 남은 샘플의 1% 두께는 설계 벽 두께다
    m = part_to_mesh(pps[part].part)
    ex = trimesh.util.concatenate([part_to_mesh(s) for s in pps[part].thin_ok])
    kept = measure_thickness(m, exclude=ex)
    assert len(kept) > 0.85 * len(measure_thickness(m))
    assert np.percentile(kept, 1) >= 0.9 * 3.0


def test_shrink_to_fit_skips_sizes_that_break_part_rules(rules, monkeypatch):
    """공간 보정은 보정으로 고칠 수 없는 규칙(rule_issues)을 어기는 줄인 크기를 쓰지 않는다 (run_engine 은 규칙 검사를
    줄이기 전에만 하므로, 쓰면 저장된 설계를 다시 검증할 때 오류가 난다)."""
    t = get_template("hideout")
    monkeypatch.setattr(type(t), "rule_issues", lambda self, p, ctx: ["줄이면 안 됨"] if p.width_mm < 299 else [])
    ectx = EngineContext(cage=Cage(260, 230, 300), species="hamster", size="syrian", count=1, rules=rules)
    res = run_engine([ItemSpec("hideout", {"width_mm": 300, "depth_mm": 250, "height_mm": 150, "entrance_diameter_mm": 75})],
                     ectx)
    assert not [i for i in res.report.issues if i.code == "resized_to_fit"]
    assert res.items[0].params.width_mm == 300
