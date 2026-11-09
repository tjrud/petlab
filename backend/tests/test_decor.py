"""장식 영역: 무늬 6종·각인이 은신처·집에 얹히고 안전·출력 검사가 그대로 통과하는지, 결정성, 줄임·건너뜀 경고, 글꼴 번들."""

from __future__ import annotations

import copy
import json
import re

import numpy as np
import pytest
from pydantic import ValidationError

from app.domain import Cage, PlacementHint
from app.geometry.mesh import mesh_health
from app.services.engine import EngineContext, ItemSpec, build_item, run_engine
from app.templates import decor as D
from app.templates.registry import get_template
from app.validation.checks import measure_thickness, overhang_area

PATTERNS = ["stripes", "dots", "scales", "brick", "wave", "honeycomb"]


def ctx(rules, cage=Cage(900, 500, 400), size="syrian"):
    return EngineContext(cage, "hamster", size, 1, rules)


def pattern(kind, **kw):
    return {"kind": "pattern", "pattern": kind, "density": 2, "direction": 0, "depth_mm": 0.6, "face": "walls",
            "mode": "engrave", **kw}


def text(t="뽀송이 Mochi-01", **kw):
    return {"kind": "text", "text": t, "face": "left", "height_mm": 15, "depth_mm": 0.6, **kw}


def _house_params(c, **extra):
    d = get_template("house").default_params(c.rule_ctx).model_dump()
    for k, v in extra.items():
        d[k].update(v)
    return d


def _assert_printable(res, rules):
    assert res.report.passed, res.report.errors
    it = res.items[0]
    for part in it.print_parts:
        assert mesh_health(part.mesh).ok, part.key
        assert overhang_area(part.print_mesh, rules.printing.max_overhang_deg) <= rules.printing.overhang_area_tolerance_mm2
        assert np.percentile(measure_thickness(part.mesh), 1) >= 0.9 * rules.min_wall_for("hamster", "syrian"), part.key
    assert not [i for i in res.report.issues if i.code in ("support_needed", "wall_thin_measured")]
    return it


def _features_unchanged(it):
    """장식은 features() 를 바꾸지 않는다 (features 는 파라미터만 본다)."""
    assert it.features == it.template.features(it.params)


@pytest.mark.parametrize("kind", PATTERNS)
def test_patterns_on_hideout_and_house(rules, kind):
    c = ctx(rules)
    for tkey, params in (("hideout", get_template("hideout").default_params(c.rule_ctx).model_dump()),
                         ("house", _house_params(c, roof={"kind": "pitched"}))):
        res = run_engine([ItemSpec(tkey, params, decor=pattern(kind, direction=45 if kind == "stripes" else 0))], c)
        it = _assert_printable(res, rules)
        _features_unchanged(it)
        assert it.decor == pattern(kind, direction=45 if kind == "stripes" else 0)
        # 장식이 실제로 형상을 바꿨다 (장식 없는 같은 파라미터보다 부피가 작다: 파내기)
        plain = build_item(0, it.template, it.params, PlacementHint(), rules.printing)
        assert it.mesh.volume < plain.mesh.volume
        # 벽은 각인 깊이만큼 두꺼워졌다
        wall = it.params.model_dump().get("wall_thickness_mm") or it.params.walls.thickness_mm
        assert wall == pytest.approx(c.min_wall_mm + 0.6)
        assert not [i for i in res.report.issues if i.code == "decor_skipped"]


def test_text_engraving_mixed_hangul_latin_digits(rules):
    c = ctx(rules)
    res = run_engine([ItemSpec("hideout", get_template("hideout").default_params(c.rule_ctx).model_dump(), decor=text())], c)
    it = _assert_printable(res, rules)
    _features_unchanged(it)
    plain = build_item(0, it.template, it.params, PlacementHint(), rules.printing)
    assert it.mesh.volume < plain.mesh.volume
    assert not [i for i in res.report.issues if i.code.startswith("decor")]


def test_text_on_pitched_roof_of_house(rules):
    c = ctx(rules)
    res = run_engine([ItemSpec("house", _house_params(c, roof={"kind": "pitched"}), decor=text("햄스터", face="roof", height_mm=20))], c)
    it = _assert_printable(res, rules)
    roof = next(p for p in it.print_parts if p.key == "roof")
    plain = build_item(0, it.template, it.params, PlacementHint(), rules.printing)
    plain_roof = next(p for p in plain.print_parts if p.key == "roof")
    assert roof.mesh.volume < plain_roof.mesh.volume
    body = next(p for p in it.print_parts if p.key == "body")
    plain_body = next(p for p in plain.print_parts if p.key == "body")
    assert body.mesh.volume == pytest.approx(plain_body.mesh.volume, rel=1e-6)  # 본체는 그대로


def test_relief_dots_on_walls(rules):
    c = ctx(rules)
    res = run_engine([ItemSpec("hideout", get_template("hideout").default_params(c.rule_ctx).model_dump(),
                               decor=pattern("dots", density=3, mode="relief"))], c)
    it = _assert_printable(res, rules)
    plain = build_item(0, it.template, it.params, PlacementHint(), rules.printing)
    assert it.mesh.volume > plain.mesh.volume  # 돋을새김은 재료를 더한다
    assert it.params.wall_thickness_mm == plain.params.wall_thickness_mm  # 벽을 두껍게 하지 않는다


def test_same_input_gives_identical_bytes(rules):
    c = ctx(rules)
    t = get_template("hideout")
    p = t.default_params(c.rule_ctx).model_copy(update={"wall_thickness_mm": 3.6})
    a = build_item(0, t, p, PlacementHint(), rules.printing, pattern("honeycomb"), c.rule_ctx)
    b = build_item(0, t, copy.deepcopy(p), PlacementHint(), rules.printing, json.loads(json.dumps(pattern("honeycomb"))), c.rule_ctx)
    assert a.mesh.export(file_type="stl") == b.mesh.export(file_type="stl")
    # 장식 명세가 다르면(밀도) 형상도 다르다
    d = build_item(0, t, p, PlacementHint(), rules.printing, pattern("honeycomb", density=3), c.rule_ctx)
    assert d.mesh.export(file_type="stl") != a.mesh.export(file_type="stl")
    assert D.decor_seed("hideout", p, D.parse_decor(pattern("honeycomb"))) != D.decor_seed("hideout", p, D.parse_decor(pattern("dots")))


def test_no_decor_path_is_unchanged(rules):
    """decor 가 없으면 예전과 같은 경로: 장식 없는 build_item 결과와 바이트가 같다 (drift 테스트가 전체를 고정한다)."""
    c = ctx(rules)
    t = get_template("hideout")
    p = t.default_params(c.rule_ctx)
    a = build_item(0, t, p, PlacementHint(), rules.printing)
    b = build_item(0, t, p, PlacementHint(), rules.printing, None, c.rule_ctx)
    assert a.mesh.export(file_type="stl") == b.mesh.export(file_type="stl")
    assert b.decor is None and b.decor_issues == []


def test_thin_wall_reduces_depth_or_skips(rules):
    """벽을 더 두껍게 할 수 없으면(필드 상한) 깊이를 줄이고, 그래도 안 되면 뺀다."""
    c = ctx(rules)
    t = get_template("hideout")
    p = t.default_params(c.rule_ctx).model_copy(update={"wall_thickness_mm": 3.2})
    # 엔진을 거치지 않고(벽 보정 없이) 바로 얹으면 깊이가 0.2 로 줄어야 하는데 0.3 미만이라 건너뛴다
    parts, issues = D.apply_decor(t.print_parts(p), t, p, D.parse_decor(pattern("stripes")), c.rule_ctx)
    assert [i.code for i in issues] == ["decor_skipped"] and "최소 두께" in issues[0].message_ko
    assert parts[0].part.volume == pytest.approx(t.build(p).volume)
    p2 = p.model_copy(update={"wall_thickness_mm": 3.4})
    parts2, issues2 = D.apply_decor(t.print_parts(p2), t, p2, D.parse_decor(pattern("stripes")), c.rule_ctx)
    assert any(i.code == "decor_reduced" and i.details.get("to") == pytest.approx(0.4) for i in issues2)
    assert parts2[0].part.volume < t.build(p2).volume
    assert all(i.severity.value == "warning" for i in issues + issues2)


def test_small_text_is_enlarged_and_long_text_is_skipped(rules):
    c = ctx(rules)
    t = get_template("hideout")
    p = t.default_params(c.rule_ctx).model_copy(update={"wall_thickness_mm": 3.6})
    _, issues = D.apply_decor(t.print_parts(p), t, p, D.parse_decor(text("Mochi", height_mm=8)), c.rule_ctx)
    grown = [i for i in issues if i.code == "decor_reduced" and i.details.get("field") == "height_mm"]
    assert grown and grown[0].details["to"] == pytest.approx(rules.printing.min_feature_mm / D.FONT_MIN_STROKE_RATIO, abs=0.1)
    _, issues = D.apply_decor(t.print_parts(p), t, p, D.parse_decor(text("ABCDEFGHIJKL", height_mm=40, face="front")), c.rule_ctx)
    assert any(i.code == "decor_skipped" for i in issues)


@pytest.mark.parametrize("bad", ["😀집", "뽀송이!", "ABCDEFGHIJKLM", "", "日本語", "a\nb"])
def test_disallowed_text_rejected_by_schema(bad):
    with pytest.raises(ValidationError):
        D.TextDecor(kind="text", text=bad, face="left", height_mm=15, depth_mm=0.6)
    assert re.fullmatch(D.TEXT_PATTERN, "가-Z 09") is not None


def test_missing_glyph_is_skipped_with_warning(rules, monkeypatch):
    c = ctx(rules)
    t = get_template("hideout")
    p = t.default_params(c.rule_ctx).model_copy(update={"wall_thickness_mm": 3.6})
    monkeypatch.setattr(D, "font_codepoints", lambda: frozenset(ord(ch) for ch in "Mochi"))
    _, issues = D.apply_decor(t.print_parts(p), t, p, D.parse_decor(text("뽀송이")), c.rule_ctx)
    assert [i.code for i in issues] == ["decor_skipped"] and "글꼴에 없는 문자" in issues[0].message_ko and "뽀" in issues[0].message_ko


def test_decor_zones_avoid_openings_and_bed_faces(rules):
    c = ctx(rules)
    hide = get_template("hideout")
    zones = hide.decor_zones(hide.default_params(c.rule_ctx).model_copy(update={"entrance_count": 2}))
    assert [z.face for z in zones] == ["front", "back", "left", "right"]  # 지붕 윗면(베드 면)은 없다
    assert all(z.obstacles for z in zones if z.face in ("front", "back"))
    house = get_template("house")
    flat = house.decor_zones(house.Params())
    assert all(z.face != "roof" for z in flat)
    pitched = house.decor_zones(house.Params(roof={"kind": "pitched"}, height_mm=200))
    assert [z.face for z in pitched].count("roof") == 2 and all(z.mode == "engrave" for z in pitched if z.face == "roof")
    assert all(z.part_key == "roof" and z.z_dir is not None and z.z_dir[2] > 0 for z in pitched if z.face == "roof")
    rounded = house.decor_zones(house.Params(roof={"kind": "rounded"}, height_mm=220))
    assert all(z.face != "roof" for z in rounded)  # 곡면은 지원하지 않는다
    ext = house.decor_zones(house.Params(floors={"count": 2, "climb": "external_ramp", "exit_side": "back", "level_height_mm": 110},
                                         height_mm=230))
    back = next(z for z in ext if z.face == "back")
    assert any(o[1] == 0.0 and o[3] == 110 for o in back.obstacles)  # 착지판이 덮는 아래쪽
    # 요청한 면이 없으면 건너뛰기 경고
    p = house.Params(**{**house.default_params(c.rule_ctx).model_dump(), "walls": {"thickness_mm": 3.6}})
    _, issues = D.apply_decor(house.print_parts(p), house, p, D.parse_decor(pattern("dots", face="roof")), c.rule_ctx)
    assert [i.code for i in issues] == ["decor_skipped"]


def test_unsupported_template_skips_decor(rules):
    c = ctx(rules)
    res = run_engine([ItemSpec("tunnel", get_template("tunnel").default_params(c.rule_ctx).model_dump(), decor=pattern("dots"))], c)
    assert res.report.passed
    assert [i.code for i in res.report.issues if i.code.startswith("decor")] == ["decor_skipped"]


def test_font_is_bundled_with_license():
    assert D.FONT_FILE.is_file() and D.FONT_FILE.stat().st_size > 100_000
    assert D.FONT_LICENSE_FILE.is_file()
    lic = D.FONT_LICENSE_FILE.read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in lic and "Pretendard" in lic
    cps = D.font_codepoints()
    assert all(ord(ch) in cps for ch in "가힣AZaz09-")
    assert D.missing_glyphs("뽀송이 Mochi-01") == []


def test_font_digest_is_part_of_fingerprint(rules, monkeypatch):
    from app.geometry import fingerprint as fp

    before = fp.geometry_fingerprint(["hideout"], rules.printing)
    monkeypatch.setattr(fp, "_font_digests", lambda: (("Pretendard-Bold.otf", "0" * 64),))
    assert fp.geometry_fingerprint(["hideout"], rules.printing) != before
