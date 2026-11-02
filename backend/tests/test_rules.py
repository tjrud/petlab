from __future__ import annotations

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
