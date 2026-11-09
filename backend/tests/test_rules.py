from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.rules.loader import RuleFileError, load_rules


def test_repo_rules_load(rules):
    hamster = rules.species_file.species["hamster"]
    assert set(hamster.sizes) == {"dwarf", "syrian"}
    syrian = rules.size_rules("hamster", "syrian")
    assert syrian.gap_trap.safe_max_mm < syrian.gap_trap.passable_min_mm
    assert rules.printing.max_overhang_deg == 45


def test_min_wall_is_max_of_species_and_printing(rules):
    s = rules.size_rules("hamster", "dwarf")
    assert rules.min_wall_for("hamster", "dwarf") == max(
        s.min_wall_thickness_mm, rules.printing.min_wall_mm
    )


def test_gap_trap_range(rules):
    gt = rules.size_rules("hamster", "syrian").gap_trap
    assert not gt.is_trap(0)
    assert not gt.is_trap(gt.safe_max_mm)
    assert gt.is_trap((gt.safe_max_mm + gt.passable_min_mm) / 2)
    assert not gt.is_trap(gt.passable_min_mm)


def test_unknown_species_raises(rules):
    with pytest.raises(KeyError):
        rules.size_rules("rabbit", "small")


def test_display_names_fall_back_to_keys(rules):
    assert rules.display_names("hamster", "syrian") == ("햄스터", "골든 (시리안)")
    assert rules.display_names("hamster", "ghost") == ("햄스터", "ghost")
    # 종이 없으면 다른 종에 있는 크기 키라도 키 그대로
    assert rules.display_names("ghost", "syrian") == ("ghost", "syrian")


def _edit_species(rules_dir: Path, fn) -> None:
    p = rules_dir / "species.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    fn(data)
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_replacing_file_changes_values(rules_copy):
    """전문가 검수 후 파일만 교체하면 값이 반영되는지."""
    _edit_species(
        rules_copy,
        lambda d: d["species"]["hamster"]["sizes"]["syrian"].update(entrance_min_diameter_mm=80),
    )
    assert load_rules(rules_copy).size_rules("hamster", "syrian").entrance_min_diameter_mm == 80


def test_typo_key_rejected(rules_copy):
    def typo(d):
        s = d["species"]["hamster"]["sizes"]["dwarf"]
        s["entrance_min_diamter_mm"] = s.pop("entrance_min_diameter_mm")

    _edit_species(rules_copy, typo)
    with pytest.raises(RuleFileError, match="species.yaml"):
        load_rules(rules_copy)


def test_inverted_gap_trap_rejected(rules_copy):
    _edit_species(
        rules_copy,
        lambda d: d["species"]["hamster"]["sizes"]["dwarf"]["gap_trap"].update(safe_max_mm=60),
    )
    with pytest.raises(RuleFileError):
        load_rules(rules_copy)


def test_sourced_values(rules):
    """근거 문서(TVT·DTSchB) 수치가 그대로 들어 있는지. 바꾸려면 species.yaml 의 출처 주석도 함께 고칠 것."""
    for size in ("dwarf", "syrian"):
        s = rules.size_rules("hamster", size)
        assert s.sand_bath_min_inner_mm == (200, 200)
        assert s.enclosure_min_floor_mm == (1000, 500)
        # DTSchB 의 "출입구 최소 2개"는 여러 마리가 함께 지낼 때의 이유라서 그때만 적용한다
        assert (s.hideout_min_entrances.single, s.hideout_min_entrances.group) == (1, 2)
        assert s.hideout_min_entrances.for_count(1) == 1
        assert s.hideout_min_entrances.for_count(2) == 2
        assert s.max_recommended_count == 1
    assert rules.size_rules("hamster", "dwarf").entrance_min_diameter_mm == 50
    assert rules.size_rules("hamster", "syrian").entrance_min_diameter_mm == 70
    # DTSchB: 플라스틱 튜브는 몸길이의 2배 이하 (드워프는 가장 작은 로보로브스키 약 5cm, 골든은 야생 성체 최소 128mm)
    assert rules.size_rules("hamster", "dwarf").tunnel_max_length_mm == 100
    assert rules.size_rules("hamster", "syrian").tunnel_max_length_mm == 250


@pytest.mark.parametrize("value", [40, 70])
def test_tunnel_max_too_short_rejected(rules_copy, value):
    """최소 내경(50)보다 짧거나, 템플릿 길이 하한(80)보다 짧으면 기동 때 거부한다 (70 은 터널을 만들 수 없다)."""
    _edit_species(
        rules_copy,
        lambda d: d["species"]["hamster"]["sizes"]["dwarf"].update(tunnel_max_length_mm=value),
    )
    with pytest.raises(RuleFileError, match="tunnel_max_length_mm"):
        load_rules(rules_copy)


def test_tunnel_length_floor_matches_template():
    """로더의 길이 하한 상수가 터널 템플릿 length_mm 하한과 같은지 (순환 import 때문에 값을 따로 둔다)."""
    from app.rules.loader import TUNNEL_LENGTH_FIELD_MIN_MM
    from app.templates.tunnel import TunnelParams
    from app.validation.autofix import field_bounds

    assert field_bounds(TunnelParams, "length_mm")[0] == TUNNEL_LENGTH_FIELD_MIN_MM


def test_missing_tunnel_max_rejected(rules_copy):
    _edit_species(rules_copy, lambda d: d["species"]["hamster"]["sizes"]["syrian"].pop("tunnel_max_length_mm"))
    with pytest.raises(RuleFileError, match="tunnel_max_length_mm"):
        load_rules(rules_copy)


def test_reversed_enclosure_floor_rejected(rules_copy):
    _edit_species(
        rules_copy,
        lambda d: d["species"]["hamster"]["sizes"]["dwarf"].update(enclosure_min_floor_mm=[500, 1000]),
    )
    with pytest.raises(RuleFileError, match="긴 변"):
        load_rules(rules_copy)


def test_missing_file(tmp_path):
    with pytest.raises(RuleFileError, match="없습니다"):
        load_rules(tmp_path)


def test_yaml_syntax_error(rules_copy):
    (rules_copy / "printing.yaml").write_text("version: [unclosed", encoding="utf-8")
    with pytest.raises(RuleFileError, match="구문"):
        load_rules(rules_copy)


# ── 사육 환경(케이지·어항)과 만들 수 있는 구조물 ─────────────────


AQUARIUM_SIZES = {"shrimp", "nano_fish", "small_fish", "community"}


def _aq(d: dict, size: str) -> dict:
    return d["species"]["aquarium"]["sizes"][size]


def test_repo_rules_load_aquarium(rules):
    aq = rules.species_entry("aquarium")
    assert set(aq.sizes) == AQUARIUM_SIZES
    assert rules.habitat("aquarium") == "aquarium" and rules.habitat("hamster") == "cage"
    assert rules.allowed_templates("aquarium") == ("cave", "tunnel")
    assert rules.allowed_templates("hamster") == ("hideout", "tunnel", "ramp", "sand_bath")
    assert rules.buoyancy("hamster") is None
    b = rules.buoyancy("aquarium")
    assert b is not None and b.material_density_g_cm3 > b.water_density_g_cm3
    assert aq.max_count == 200 and rules.species_entry("hamster").max_count == 10
    assert aq.print_notes_ko and all(isinstance(n, str) and n for n in aq.print_notes_ko)
    assert rules.species_entry("hamster").print_notes_ko == ()
    for size in AQUARIUM_SIZES:
        s = rules.size_rules("aquarium", size)
        assert s.aquatic is not None
        # 어항에는 램프·모래목욕통·오르기 기준과 터널 길이 상한이 없다
        assert s.tunnel_max_length_mm is None
        assert s.max_ramp_angle_deg is s.max_climb_height_mm is s.max_step_height_mm is None
        assert s.sand_bath_min_inner_mm is None and s.sand_bath_min_depth_mm is None
        assert s.max_recommended_count is None and s.count_warning_ko is None
        assert s.gap_trap.safe_max_mm < s.gap_trap.passable_min_mm
    for size in ("dwarf", "syrian"):
        s = rules.size_rules("hamster", size)
        assert s.aquatic is None and s.min_recommended_count is None and s.min_count_warning_ko is None
    # 어항 최소 벽 = 종 기준 (출력 최소 벽 1.2mm 보다 두껍다)
    assert rules.min_wall_for("aquarium", "nano_fish") == 2.0
    assert rules.min_wall_for("aquarium", "small_fish") == 2.4


def test_unknown_species_lookups_raise(rules):
    for f in (rules.species_entry, rules.habitat, rules.allowed_templates, rules.buoyancy):
        with pytest.raises(KeyError):
            f("rabbit")


def test_sourced_aquarium_values(rules):
    """근거 문서(rules/aquarium-evidence.md)의 수치가 그대로 들어 있는지. 바꾸려면 species.yaml 주석·근거 문서도 함께 고칠 것."""
    def s(size):
        return rules.size_rules("aquarium", size)

    # OATA: 소형 새우 무리 10L 이상·5마리 이상. 바닥 기준은 출처가 없어 두지 않는다
    assert s("shrimp").aquatic.min_volume_l == 10
    assert s("shrimp").aquatic.volume_l_per_animal is None
    assert s("shrimp").min_recommended_count == 5
    assert s("shrimp").enclosure_min_floor_mm is None
    assert (s("shrimp").hideout_min_entrances.single, s("shrimp").hideout_min_entrances.group) == (1, 1)
    # THVO-AT·BMEL·BLV: 54L 미만 금지, '60cm' 등급 = 60×30cm 바닥
    for size in ("nano_fish", "small_fish", "community"):
        assert s(size).aquatic.min_volume_l == 54
        assert s(size).enclosure_min_floor_mm == (600, 300)
        # 물고기는 뒤로 잘 빠져나오지 못한다 → 관통형(출입구 2개)
        assert s(size).hideout_min_entrances.for_count(1) == 2
    # TSchV-CH 표 8: 0.5 L/cm × 3cm, 0.75 L/cm × 7.5cm (반올림)
    assert s("nano_fish").aquatic.volume_l_per_animal == 1.5
    assert s("small_fish").aquatic.volume_l_per_animal == 5.6
    assert s("community").aquatic.volume_l_per_animal is None
    # BLV 카디널 10마리 / 무리형 최소 5마리. 합사 수조는 하나로 정할 수 없다
    assert s("nano_fish").min_recommended_count == 10
    assert s("small_fish").min_recommended_count == 5
    assert s("community").min_recommended_count is None and s("community").min_count_warning_ko is None
    # EHEIM: 윗가장자리 약 3cm 아래까지 물
    assert {s(k).aquatic.air_gap_mm for k in AQUARIUM_SIZES} == {30}
    # 출입구·통로 최소 폭과 통과 폭
    assert [s(k).entrance_min_diameter_mm for k in ("shrimp", "nano_fish", "small_fish", "community")] == [15, 20, 45, 45]
    assert [s(k).gap_trap.passable_min_mm for k in ("shrimp", "nano_fish", "small_fish", "community")] == [15, 20, 45, 45]
    # 합사 수조 = 가장 작은 safe_max(새우), 가장 큰 통과 폭(소형 어종)
    assert s("community").gap_trap.safe_max_mm == s("shrimp").gap_trap.safe_max_mm == 1.0
    # 부력: PLA·PETG 보수값 1.24, 25°C 담수 0.997
    b = rules.buoyancy("aquarium")
    assert (b.material_density_g_cm3, b.water_density_g_cm3) == (1.24, 0.997)


def test_aquarium_size_without_aquatic_rejected(rules_copy):
    _edit_species(rules_copy, lambda d: _aq(d, "shrimp").pop("aquatic"))
    with pytest.raises(RuleFileError, match=r"(?s)species\.aquarium.*'shrimp'.*aquatic"):
        load_rules(rules_copy)


def test_aquatic_keys_are_required(rules_copy):
    # volume_l_per_animal 은 null 일 수 있지만 키를 빼면 안 된다 (오타·누락을 기동 때 잡는다)
    _edit_species(rules_copy, lambda d: _aq(d, "shrimp")["aquatic"].pop("volume_l_per_animal"))
    with pytest.raises(RuleFileError, match="volume_l_per_animal"):
        load_rules(rules_copy)


@pytest.mark.parametrize("key,value", [("ceiling_min_slope_deg", 90), ("min_volume_l", 0),
                                       ("max_height_to_base_ratio", 0), ("air_gap_mm", -1),
                                       ("glass_thickness_assumed_mm", -1)])
def test_aquatic_value_ranges(rules_copy, key, value):
    _edit_species(rules_copy, lambda d: _aq(d, "nano_fish")["aquatic"].update({key: value}))
    with pytest.raises(RuleFileError, match=key):
        load_rules(rules_copy)


def test_aquatic_glass_thickness_is_required(rules_copy):
    """입력(안쪽 치수)과 바닥·부피 기준(겉 크기)을 맞추는 유리 두께 어림은 빠뜨리면 기동 때 잡는다."""
    _edit_species(rules_copy, lambda d: _aq(d, "nano_fish")["aquatic"].pop("glass_thickness_assumed_mm"))
    with pytest.raises(RuleFileError, match="glass_thickness_assumed_mm"):
        load_rules(rules_copy)


def test_tank_glass_thickness_assumption(rules):
    """[임시] 흔한 30~60cm 수조 유리 5T·6T 중 두꺼운 쪽: 안쪽을 잰 표준 60×30cm 수조가 기준 미달로 나오지 않게."""
    for size in AQUARIUM_SIZES:
        assert rules.size_rules("aquarium", size).aquatic.glass_thickness_assumed_mm == 6


def test_print_notes_follow_post_10(rules):
    """출력·설치 안내는 커뮤니티 글10(content/community-drafts/10-aquarium.md)의 조건과 같다."""
    notes = rules.species_entry("aquarium").print_notes_ko

    def note(head: str) -> str:
        [n] = [n for n in notes if n.startswith(f"{head}:")]
        return n

    # 글10 '수조별로': 새우·달팽이는 무착색 PETG 와 스테인리스·티타늄 노즐만 (달팽이는 물고기 수조에도 흔하다)
    assert "새우·달팽이가 있는 수조" in note("소재") and "무착색 PETG로 출력하세요" in note("소재")
    assert "스테인리스나 티타늄" in note("노즐") and "새우·달팽이가 있는 수조라면 꼭 바꾸세요" in note("노즐")
    # 사포질은 씻고 담그기 전에: 가루와 새로 드러난 면도 담가 두는 동안 빠지게 (글10: PLA 미세입자는 해롭다)
    before = note("넣기 전")
    assert before.index("사포") < before.index("물로만 씻") < before.index("담갔다가")
    # 근거 문서 placement_on_base_glass: 바닥을 파는 물고기면 바닥 유리에 놓고, 출입구가 묻히지 않게
    placing = note("바닥에 놓기")
    assert "코리도라스" in placing and "바닥 유리에 바로 놓고" in placing and "출입구가 묻히지 않게" in placing
    assert "위에 돌을 얹지" in placing
    heads = [n.split(":")[0] for n in notes[1:]]
    assert heads.index("넣기 전") < heads.index("넣을 때") < heads.index("바닥에 놓기") < heads.index("넣은 뒤")
    # 글10 의 입장: '안전하다'가 아니라 '위험이 낮아 보인다'
    assert notes[0].startswith("어항 수질에 안전하다고 증명된 3D 출력 소재는 없어요")


def test_aquarium_size_hint_and_nano_label(rules):
    """나노 어종 이름은 길이 기준(꼬리지느러미 뺀 몸길이)과 하한(2cm)을 적고 보라라스 속 전체를 넣지 않는다.
    SL 20mm 미만 종은 끼임 기준이 더 엄격한 합사 수조로 안내한다 (근거 문서 [nano_fish] gap_trap.safe_max_mm)."""
    aq = rules.species_entry("aquarium")
    nano = rules.size_rules("aquarium", "nano_fish")
    community = rules.size_rules("aquarium", "community")
    assert "꼬리지느러미 뺀 몸길이 2~3cm" in nano.display_name and "보라라스" not in nano.display_name
    assert aq.size_hint_ko is not None
    assert "꼬리지느러미를 뺀 길이" in aq.size_hint_ko and "보라라스 마이크로스" in aq.size_hint_ko
    assert f"'{community.display_name.split(' (')[0]}'" in aq.size_hint_ko  # '합사 수조'
    # 보라라스 마이크로스(SL 13mm)의 끼임 어림(체고의 40%) 약 1.3mm: 합사 수조 기준은 그보다 작고 나노 어종 기준은 크다
    assert community.gap_trap.safe_max_mm < 1.3 < nano.gap_trap.safe_max_mm
    assert rules.species_entry("hamster").size_hint_ko is None


def test_aquarium_requires_buoyancy(rules_copy):
    _edit_species(rules_copy, lambda d: d["species"]["aquarium"].pop("buoyancy"))
    with pytest.raises(RuleFileError, match="buoyancy"):
        load_rules(rules_copy)


def test_buoyancy_material_must_be_denser_than_water(rules_copy):
    _edit_species(rules_copy, lambda d: d["species"]["aquarium"]["buoyancy"].update(material_density_g_cm3=0.9))
    with pytest.raises(RuleFileError, match="material_density_g_cm3"):
        load_rules(rules_copy)


@pytest.mark.parametrize("templates", [["cave", "tunnel", "ramp"], ["hideout"], ["cave", "sand_bath"]])
def test_cage_templates_in_aquarium_rejected(rules_copy, templates):
    """바닥이 열린 은신처(물속에서 공기가 갇힘)·램프·모래목욕통은 어항에 만들 수 없다."""
    _edit_species(rules_copy, lambda d: d["species"]["aquarium"].update(templates=templates))
    with pytest.raises(RuleFileError, match="habitat aquarium"):
        load_rules(rules_copy)


def test_cave_in_cage_rejected(rules_copy):
    _edit_species(rules_copy, lambda d: d["species"]["hamster"].update(templates=["hideout", "cave"]))
    with pytest.raises(RuleFileError, match=r"(?s)species\.hamster.*cave.*habitat cage"):
        load_rules(rules_copy)


@pytest.mark.parametrize("templates,match", [(["hideout", "burrow"], "알 수 없는 템플릿 키"),
                                             ([], "비어 있습니다"), (["cave", "cave"], "두 번")])
def test_bad_template_lists_rejected(rules_copy, templates, match):
    _edit_species(rules_copy, lambda d: d["species"]["aquarium"].update(templates=templates))
    with pytest.raises(RuleFileError, match=match):
        load_rules(rules_copy)


def test_aquarium_must_list_templates(rules_copy):
    _edit_species(rules_copy, lambda d: d["species"]["aquarium"].pop("templates"))
    with pytest.raises(RuleFileError, match="templates"):
        load_rules(rules_copy)


def test_cage_templates_default(rules_copy):
    """케이지 종은 templates 를 빼면 케이지 기본 구조물 4종, 사육 환경도 빼면 cage, 최대 마릿수 10."""
    def strip(d):
        for k in ("templates", "habitat", "max_count"):
            d["species"]["hamster"].pop(k)

    _edit_species(rules_copy, strip)
    rb = load_rules(rules_copy)
    assert rb.habitat("hamster") == "cage"
    assert rb.allowed_templates("hamster") == ("hideout", "tunnel", "ramp", "sand_bath")
    assert rb.species_entry("hamster").max_count == 10


def test_cage_size_missing_climb_fields_rejected_only_with_ramp(rules_copy):
    """램프를 만들 수 있으면 오르기 기준이 있어야 하고, 램프를 빼면 그 값 없이도 읽힌다."""
    _edit_species(rules_copy, lambda d: d["species"]["hamster"]["sizes"]["dwarf"].pop("max_climb_height_mm"))
    with pytest.raises(RuleFileError, match=r"(?s)'dwarf'.*max_climb_height_mm"):
        load_rules(rules_copy)

    def no_ramp(d):
        d["species"]["hamster"]["templates"] = ["hideout", "tunnel", "sand_bath"]
        d["species"]["hamster"]["sizes"]["syrian"].pop("max_climb_height_mm")

    _edit_species(rules_copy, no_ramp)
    rb = load_rules(rules_copy)
    assert rb.allowed_templates("hamster") == ("hideout", "tunnel", "sand_bath")
    assert rb.size_rules("hamster", "dwarf").max_climb_height_mm is None


def test_cage_size_missing_sand_bath_fields_rejected(rules_copy):
    _edit_species(rules_copy, lambda d: d["species"]["hamster"]["sizes"]["syrian"].pop("sand_bath_min_depth_mm"))
    with pytest.raises(RuleFileError, match=r"(?s)'syrian'.*sand_bath_min_depth_mm"):
        load_rules(rules_copy)


def test_cage_size_requires_enclosure_and_count_rules(rules_copy):
    _edit_species(rules_copy, lambda d: d["species"]["hamster"]["sizes"]["syrian"].pop("enclosure_min_floor_mm"))
    with pytest.raises(RuleFileError, match="enclosure_min_floor_mm"):
        load_rules(rules_copy)


@pytest.mark.parametrize("edit,match", [
    (lambda d: d["species"]["hamster"]["sizes"]["dwarf"].pop("count_warning_ko"), "count_warning_ko"),
    (lambda d: _aq(d, "shrimp").update(min_count_warning_ko=None), "min_count_warning_ko"),
    (lambda d: _aq(d, "community").update(min_recommended_count=3), "min_count_warning_ko"),
])
def test_count_rule_pairs(rules_copy, edit, match):
    """마릿수 기준과 경고 문구는 둘 다 있거나 둘 다 없어야 한다."""
    _edit_species(rules_copy, edit)
    with pytest.raises(RuleFileError, match=match):
        load_rules(rules_copy)


@pytest.mark.parametrize("field,value", [("max_ramp_angle_deg", 20), ("max_step_height_mm", 10),
                                         ("sand_bath_min_inner_mm", [100, 100])])
def test_aquarium_rejects_cage_only_fields(rules_copy, field, value):
    _edit_species(rules_copy, lambda d: _aq(d, "nano_fish").update({field: value}))
    with pytest.raises(RuleFileError, match=field):
        load_rules(rules_copy)


def test_cage_rejects_aquatic(rules_copy):
    def edit(d):
        d["species"]["hamster"]["sizes"]["dwarf"]["aquatic"] = dict(_aq(d, "shrimp")["aquatic"])

    _edit_species(rules_copy, edit)
    with pytest.raises(RuleFileError, match="aquatic"):
        load_rules(rules_copy)


def test_aquarium_tunnel_max_length_optional_but_checked(rules_copy):
    """어항 터널은 길이 상한이 없다(null). 적으면 케이지와 같은 하한 검사를 받는다."""
    _edit_species(rules_copy, lambda d: _aq(d, "nano_fish").update(tunnel_max_length_mm=50))
    with pytest.raises(RuleFileError, match="tunnel_max_length_mm"):
        load_rules(rules_copy)


# ── 템플릿 필드 범위와 규칙 값 (규칙 파일만 바꿔도 구조물을 하나도 못 만들게 되는 값을 기동 때 잡는다) ──


def test_template_field_limits_match_templates():
    """로더의 템플릿 필드 상한 상수가 동굴·터널 템플릿 필드와 같은지 (순환 import 때문에 값을 따로 둔다)."""
    from app.rules import loader
    from app.templates.cave import CaveParams
    from app.templates.tunnel import TunnelParams
    from app.validation.autofix import field_bounds

    assert field_bounds(CaveParams, "wall_thickness_mm")[1] == loader.CAVE_WALL_FIELD_MAX_MM
    assert field_bounds(CaveParams, "entrance_count")[1] == loader.CAVE_ENTRANCE_COUNT_FIELD_MAX
    assert field_bounds(CaveParams, "roof_slope_deg")[1] == loader.CAVE_ROOF_SLOPE_FIELD_MAX_DEG
    assert field_bounds(CaveParams, "entrance_diameter_mm")[1] == loader.CAVE_ENTRANCE_FIELD_MAX_MM
    assert field_bounds(CaveParams, "top_opening_mm")[1] == loader.CAVE_TOP_OPENING_FIELD_MAX_MM
    assert field_bounds(TunnelParams, "inner_diameter_mm")[1] == loader.TUNNEL_INNER_FIELD_MAX_MM
    assert field_bounds(TunnelParams, "wall_thickness_mm")[1] == loader.TUNNEL_WALL_FIELD_MAX_MM


@pytest.mark.parametrize("size,edit,key", [
    ("small_fish", lambda s: s.update(min_wall_thickness_mm=4), "min_wall_thickness_mm"),
    ("nano_fish", lambda s: s["hideout_min_entrances"].update(single=3, group=3), "hideout_min_entrances.single"),
    ("nano_fish", lambda s: s["hideout_min_entrances"].update(group=3), "hideout_min_entrances.group"),
    ("nano_fish", lambda s: s["aquatic"].update(ceiling_min_slope_deg=70), "aquatic.ceiling_min_slope_deg"),
    # 기본 출입구는 최소 + 5mm 라 필드 상한(120) − 5 를 넘으면 기본 동굴도 만들 수 없다
    ("nano_fish", lambda s: s.update(entrance_min_diameter_mm=116), "entrance_min_diameter_mm"),
    ("small_fish", lambda s: s["gap_trap"].update(passable_min_mm=146), "gap_trap.passable_min_mm"),
    ("small_fish", lambda s: s.update(tunnel_min_inner_diameter_mm=126), "tunnel_min_inner_diameter_mm"),
])
def test_aquarium_values_outside_cave_and_tunnel_fields_rejected(rules_copy, size, edit, key):
    """동굴·터널 필드 범위를 넘는 값이면 그 크기 구분의 모든 동굴이 보정 충돌로 막힌다: 서버가 기동하지 않게 한다."""
    _edit_species(rules_copy, lambda d: edit(_aq(d, size)))
    with pytest.raises(RuleFileError, match=rf"(?s)'{size}'.*{re.escape(key)}"):
        load_rules(rules_copy)


def test_hamster_tunnel_inner_outside_field_rejected(rules_copy):
    _edit_species(rules_copy, lambda d: d["species"]["hamster"]["sizes"]["syrian"].update(
        tunnel_min_inner_diameter_mm=126, tunnel_max_length_mm=400))
    with pytest.raises(RuleFileError, match=r"(?s)'syrian'.*tunnel_min_inner_diameter_mm"):
        load_rules(rules_copy)


def test_values_at_field_limits_still_load_and_make_a_cave(rules_copy):
    """경계 값(필드 상한 그대로)은 받고, 그 값으로도 기본 동굴이 보정 충돌 없이 만들어진다."""
    from app.templates.base import RuleContext
    from app.templates.cave import CaveTemplate
    from app.validation.autofix import clamp_params

    def edit(d):
        s = _aq(d, "nano_fish")
        s.update(min_wall_thickness_mm=3.2, entrance_min_diameter_mm=115)
        s["hideout_min_entrances"].update(single=2, group=2)
        s["aquatic"].update(ceiling_min_slope_deg=65)
        s["gap_trap"].update(passable_min_mm=145)
    _edit_species(rules_copy, edit)
    rb = load_rules(rules_copy)
    ctx = RuleContext(rb.size_rules("aquarium", "nano_fish"), rb.min_wall_for("aquarium", "nano_fish"), 10)
    t = CaveTemplate()
    _, issues = clamp_params(t, t.default_params(ctx), ctx)
    assert not [i for i in issues if i.code == "param_conflict"], issues


def test_printing_min_wall_above_cave_wall_limit_rejected(rules_copy):
    """적용 최소 벽 = max(종 기준, 출력 최소 벽): 출력 최소 벽이 동굴 벽 두께 상한을 넘어도 동굴을 만들 수 없다."""
    p = rules_copy / "printing.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data["min_wall_mm"] = 3.5
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(RuleFileError, match=r"(?s)printing\.yaml.*min_wall_mm 3\.5.*cave.*3\.2"):
        load_rules(rules_copy)


def test_max_count_bounded_by_api_cap(rules_copy):
    """규칙 파일의 최대 마릿수가 API 전체 상한(200)을 넘으면 /species 가 API 가 거부하는 마릿수를 알리게 된다."""
    from app.rules.loader import MAX_HABITAT_COUNT
    from app.schemas import HabitatIn

    assert HabitatIn.model_fields["count"].metadata[-1].le == MAX_HABITAT_COUNT  # API 와 같은 상수
    _edit_species(rules_copy, lambda d: d["species"]["aquarium"].update(max_count=MAX_HABITAT_COUNT))
    assert load_rules(rules_copy).species_entry("aquarium").max_count == MAX_HABITAT_COUNT
    _edit_species(rules_copy, lambda d: d["species"]["aquarium"].update(max_count=MAX_HABITAT_COUNT + 1))
    with pytest.raises(RuleFileError, match=r"(?s)species\.aquarium\.max_count"):
        load_rules(rules_copy)


def test_volume_note_values(rules):
    """종별 권장 부피 안내 (54L 는 하한일 뿐): 나노·소형·합사 수조에만 있고 100L 미만에서 안내한다."""
    for size in ("nano_fish", "small_fish", "community"):
        aq = rules.size_rules("aquarium", size).aquatic
        assert aq.volume_note_below_l == 100 and aq.volume_note_ko.startswith("54L는 최소 기준일 뿐이에요.")
    small = rules.size_rules("aquarium", "small_fish").aquatic.volume_note_ko
    assert "코리도라스 무리는 80L 이상" in small and "160L" in small and "100L 이상" in small
    shrimp = rules.size_rules("aquarium", "shrimp").aquatic
    assert shrimp.volume_note_ko is None and shrimp.volume_note_below_l is None


@pytest.mark.parametrize("edit,match", [
    (lambda a: a.pop("volume_note_below_l"), "volume_note_ko 와 volume_note_below_l"),
    (lambda a: a.pop("volume_note_ko"), "volume_note_ko 와 volume_note_below_l"),
    (lambda a: a.update(volume_note_below_l=54), "volume_note_below_l 은 min_volume_l 보다"),
])
def test_volume_note_pair_rules(rules_copy, edit, match):
    _edit_species(rules_copy, lambda d: edit(_aq(d, "small_fish")["aquatic"]))
    with pytest.raises(RuleFileError, match=match):
        load_rules(rules_copy)
