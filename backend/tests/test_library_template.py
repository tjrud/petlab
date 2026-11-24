"""DSL 부품 템플릿 (app/library/template.py, ops.py) 과 레지스트리 (app/templates/registry.py) — 설계 §5.5–§5.9, §9.3.

tests/data/library/*.json (§6 의 초안 세 개) 와 이 파일의 작은 시험 부품으로 Template API 를 확인한다:
Params, 크기별 기본값, 제약과 자리표시, 연결 지점(배치별), 출입구 자르기, open_port, 특징, 외형, 출력 파트·자세,
읽기 실패(fail fast), 레지스트리 순서와 overlay(기억 비우기)."""

from __future__ import annotations

import copy
import json
import math
import pickle
import subprocess
import sys
import time
import typing
from pathlib import Path

import numpy as np
import pytest
from build123d import Vector
from pydantic import ValidationError

from app.geometry.mesh import mesh_health, part_to_mesh
from app.library import index, ops
from app.library.errors import DslError
from app.library.index import LibraryError, dump_index, sha256_bytes
from app.library.template import (
    DOOR_LABEL_KO,
    ROTATIONS,
    DslTemplate,
    camel,
    load_library,
    make_template,
    next_key,
)
from app.templates import registry
from app.templates.base import RuleContext, Template, TemplateParams
from app.templates.tunnel import TunnelParams, inner_profile

DATA = Path(__file__).parent / "data" / "library"
BACKEND = Path(__file__).resolve().parents[1]
CODE_KEYS = ("hideout", "tunnel", "ramp", "sand_bath", "house", "cave", "bowl_holder", "bottle_stand")
# 레지스트리에 들어 있는 것: 코드 부품, 그다음 게시된 라이브러리 부품 (key 순). 지금 색인은 비어 있다
REGISTERED = (*CODE_KEYS, *sorted(index.keys()))
# overlay 시험용 key (게시된 부품과 겹치지 않게)
DRAFT_JUNCTION, DRAFT_DECK = "tunnel_junction@v901", "deck_platform@v901"


def draft(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def published(d: dict, version: int = 1) -> dict:
    """초안 → 게시 파일 (publish 처럼 dsl, key, family, version 순서로)."""
    d = dict(d)
    out = {"dsl": d.pop("dsl"), "key": f"{d['family']}@v{version}", "family": d.pop("family"), "version": version}
    out.update(d)
    return out


def rctx(rules, size: str = "dwarf", count: int = 1) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), count,
                       printing_max_overhang_deg=rules.printing.max_overhang_deg,
                       min_feature_mm=rules.printing.min_feature_mm)


@pytest.fixture(scope="module")
def junction() -> DslTemplate:
    return make_template(draft("tunnel_junction"), key="tunnel_junction@v1")


@pytest.fixture(scope="module")
def deck() -> DslTemplate:
    return make_template(draft("deck_platform"), key="deck_platform@v1")


@pytest.fixture(scope="module")
def draft_junction() -> DslTemplate:
    return make_template(draft("tunnel_junction"), key=DRAFT_JUNCTION)


@pytest.fixture(scope="module")
def draft_deck() -> DslTemplate:
    return make_template(draft("deck_platform"), key=DRAFT_DECK)


@pytest.fixture(scope="module")
def tray() -> DslTemplate:
    return make_template(draft("litter_tray"), key="litter_tray@v1")


# ── 작은 시험 부품 ──

def text(ko: str, en: str) -> dict:
    return {"ko": ko, "en": en}


def room_data(**over) -> dict:
    """뒷문을 낼 수 있는(opens) 시험용 방: bool·integer·choice 파라미터, repeat 환기구, 상자 창, 검사(checks)."""
    d = {
        "dsl": 1, "family": "test_room",
        "name": text("시험 방", "Test room"),
        "description": text("시험용 방.", "A test room."),
        "keywords": {"ko": ["방"], "en": ["room"]},
        "part_id": "troom", "habitats": ["cage"], "role": "room_host",
        "attach_order": {"passage": ["front", "back"]},
        "height_field": "height_mm", "size_fields": ["width_mm"], "door_fields": ["back_door", "shape"],
        "params": {
            "wall_thickness_mm": {"type": "number", "default": 3, "min": 2.3, "max": 6,
                                  "rule_default": "ctx.default_wall_mm", "desc": text("벽 두께 mm", "Wall thickness mm")},
            "width_mm": {"type": "number", "default": 100, "min": 60, "max": 200,
                         "desc": text("외형 가로·세로 mm. 정사각형", "Outer size mm. Square")},
            "height_mm": {"type": "number", "default": 70, "min": 40, "max": 150, "desc": text("높이 mm", "Height mm")},
            "door_mm": {"type": "number", "default": 50, "min": 25, "max": 90,
                        "rule_default": "rule.entrance_min_diameter_mm + 5", "desc": text("출입구 폭 mm", "Door mm")},
            "back_door": {"type": "bool", "default": False, "desc": text("뒷문", "Back door")},
            "vent_count": {"type": "integer", "default": 2, "min": 0, "max": 4,
                           "rule_default": "ctx.count + 0.5", "desc": text("환기구 개수", "Vent count")},
            "shape": {"type": "choice", "choices": ["round_arch", "box"], "default": "round_arch",
                      "desc": text("출입구 모양", "Door shape")},
        },
        "let": [{"name": "W", "expr": "width_mm"}, {"name": "H", "expr": "height_mm"},
                {"name": "t", "expr": "wall_thickness_mm"}],
        "constraints": [
            {"field": "width_mm", "min": "door_mm + 2 * t + 10", "source": "geometry",
             "reason": text("{1} 방 가로는 {0}mm 이상", "{1} room width at least {0} mm")},
            {"field": "door_mm", "max": "W - 2 * t - 10", "source": "geometry", "when": "back_door",
             "blocking": False, "reason": text("뒷문이 있으면 출입구는 {0}mm 이하", "With a back door at most {0} mm")},
            {"field": "height_mm", "min": "door_mm / 3", "source": "geometry",
             "reason": text("높이는 {0}mm 이상", "Height at least {0} mm")},
        ],
        "checks": [{"fail_if": "door_mm > W - 2 * t", "message": text("출입구가 너무 넓어요", "The door is too wide")}],
        "body": [
            {"op": "box", "size": ["W", "W", "H"]},
            {"op": "box", "mode": "cut", "size": ["W - 2 * t", "W - 2 * t", "H - t + 1"], "at": [0, 0, -1]},
            {"op": "cylinder", "mode": "cut", "id": "vent", "r": 2, "h": "t + 2", "axis": "z",
             "at": ["(i - 0.5) * 20", 0, "H - t - 1"], "repeat": {"i": "vent_count"}},
            {"op": "box", "mode": "cut", "id": "win", "size": ["t + 2", 8, 10], "at": ["-W / 2 + t / 2", 0, 20]},
        ],
        "print": [{"key": "body", "name": text("본체", "Body"), "rotation": "inverted"}],
        "anchors": {
            "front": {"origin": [0, "-W / 2", 0], "normal": "-Y", "up": "+Z", "side": "front", "wall": "t",
                      "door": {"when": "True", "width": "door_mm", "profile": "shape"},
                      "fields": {"width": "width_mm", "height": "height_mm", "wall": "wall_thickness_mm",
                                 "port": "door_mm", "profile": "shape"}},
            "back": {"origin": [0, "W / 2", 0], "normal": "+Y", "up": "+Z", "side": "back", "wall": "t",
                     "openable": True, "mount": ["-W / 2", "W / 2", "H"],
                     "door": {"when": "back_door", "width": "door_mm", "profile": "shape"},
                     "fields": {"width": "width_mm", "height": "height_mm", "wall": "wall_thickness_mm",
                                "port": "door_mm", "profile": "shape"}},
            "right": {"origin": ["W / 2", 0, 0], "normal": "+X", "up": "+Z", "mount": ["-W / 2", "W / 2", "H"],
                      "fields": {"width": "width_mm", "height": "height_mm"}},
            "top": {"origin": [0, 0, "H"], "normal": "+Z", "up": "+Y"},
        },
        "opens": [{"anchor": "back", "set": {"back_door": "True"}}],
        "envelope": ["W", "W", "H"],
        "features": {
            "openings": [
                {"kind": "vent", "step": "vent", "label": text("환기구", "Vent"), "when": "vent_count > 0"},
                {"kind": "window", "step": "win", "axis": "x", "label": text("창", "Window")},
            ],
            "access_sides": [{"side": "left", "when": "back_door"}, {"side": "front"}],
        },
    }
    d.update(over)
    return d


def shelf_data(**over) -> dict:
    """출력 파트가 둘인 시험용 부속품 (prism, 가로 원기둥, face_needs)."""
    d = {
        "dsl": 1, "family": "test_shelf",
        "name": text("시험 선반", "Test shelf"),
        "description": text("시험용 선반.", "A test shelf."),
        "keywords": {"ko": ["선반"], "en": ["shelf"]},
        "part_id": "tshelf", "habitats": ["cage"], "role": "accessory",
        "attach_order": {"slide": ["back"]},
        "params": {
            "wall_thickness_mm": {"type": "number", "default": 3, "min": 1.2, "max": 6, "desc": text("두께 mm", "T mm")},
            "width_mm": {"type": "number", "default": 80, "min": 40, "max": 120, "desc": text("가로 mm", "Width mm")},
            "height_mm": {"type": "number", "default": 40, "min": 20, "max": 80, "desc": text("높이 mm", "Height mm")},
        },
        "body": [
            {"op": "box", "size": ["width_mm", 40, "height_mm"]},
            {"op": "prism", "part": "peg", "plane": "xz", "points": [[0, 0], [10, 0], [0, 10]], "depth": 6,
             "at": [0, 30, 0]},
            {"op": "cylinder", "part": "peg", "r": 3, "h": 20, "axis": "x", "at": [5, 30, 0]},
        ],
        "print": [{"key": "body", "name": text("본체", "Body"), "rotation": "upright"},
                  {"key": "peg", "name": text("못", "Peg"), "rotation": "left_down"}],
        "anchors": {"back": {"origin": [0, 20, 0], "normal": "+Y", "up": "+Z"}},
        "envelope": ["width_mm", 40, "height_mm"],
        "face_needs": {"min": "height_mm + 5", "max": None},
        "features": {"step_height": "height_mm", "min_wall": "wall_thickness_mm / 2"},
    }
    d.update(over)
    return d


@pytest.fixture(scope="module")
def room() -> DslTemplate:
    return make_template(room_data(), key="test_room@v1")


@pytest.fixture(scope="module")
def shelf() -> DslTemplate:
    return make_template(shelf_data(), key="test_shelf@v1")


def inside(part, xyz) -> bool:
    return bool(part.is_inside(Vector(*xyz)))


# ── 만들기, Params ──

def test_make_template_class_and_members(junction: DslTemplate) -> None:
    assert type(junction).__name__ == "LibTunnelJunctionV1"
    assert type(junction).__module__ == "app.library.template"
    assert isinstance(junction, Template)
    assert junction.key == "tunnel_junction@v1"
    assert junction.display_name_ko == "터널 갈림길"
    assert junction.description_ko.startswith("터널 여러 개가 만나는 작은 방")
    assert junction.color == "#c9a46e"
    assert junction.role == "room_host"
    assert junction.attach_order == {"passage": ("front", "back", "left", "right")}
    assert junction.height_field == "height_mm" and junction.size_fields == ("size_mm",)
    assert junction.door_fields == ("layout", "door_shape")
    assert junction.standalone and not junction.cutter and junction.legacy_defaults == {}
    assert junction.level_field is None and junction.passes_access is False
    assert junction.retired is False and junction.status == "active"
    assert camel("tunnel_junction") == "TunnelJunction"


def test_color_defaults_and_attach_order(deck: DslTemplate, tray: DslTemplate) -> None:
    assert deck.attach_order == {}
    assert tray.attach_order == {"slide": ("back",)}
    no_color = make_template({**draft("litter_tray"), "color": None}, key="litter_tray@v1")
    assert no_color.color == index.DEFAULT_COLOR == "#c8a27a"


def test_params_model(junction: DslTemplate) -> None:
    P = junction.Params
    assert P.__name__ == "LibTunnelJunctionV1Params" and issubclass(P, TemplateParams)
    assert list(P.model_fields) == ["wall_thickness_mm", "layout", "door_width_mm", "door_shape", "size_mm", "height_mm"]
    f = P.model_fields
    assert f["door_width_mm"].annotation is float
    assert typing.get_args(f["layout"].annotation) == ("I", "L", "T", "X")
    assert typing.get_args(f["door_shape"].annotation) == ("round_arch", "pointed_arch", "box", "house")
    assert f["door_width_mm"].description == "출입구 폭 mm. 종별 최소 출입구 폭 이상이며 이은 터널 안지름과 같아진다"
    assert P().model_dump() == {"wall_thickness_mm": 3.0, "layout": "T", "door_width_mm": 60.0,
                                "door_shape": "round_arch", "size_mm": 90.0, "height_mm": 80.0}
    with pytest.raises(ValidationError):
        P(door_width_mm=101)  # le=max
    with pytest.raises(ValidationError):
        P(size_mm=59)  # ge=min
    with pytest.raises(ValidationError):
        P(layout="Y")
    with pytest.raises(ValidationError):
        P(extra_field=1)  # TemplateParams: extra forbid
    schema = P.model_json_schema()
    assert schema["properties"]["door_width_mm"]["minimum"] == 25
    assert schema["properties"]["door_width_mm"]["maximum"] == 100


def test_params_integer_and_bool(room: DslTemplate) -> None:
    f = room.Params.model_fields
    assert f["vent_count"].annotation is int and f["back_door"].annotation is bool
    p = room.Params()
    assert p.vent_count == 2 and p.back_door is False and p.wall_thickness_mm == 3.0
    with pytest.raises(ValidationError):
        room.Params(vent_count=5)


def test_params_pickle(room: DslTemplate) -> None:
    """검증기가 프로세스 사이로 넘길 수 있게 동적 클래스를 모듈 이름으로 찾을 수 있다."""
    p = room.Params(width_mm=120)
    assert pickle.loads(pickle.dumps(p)) == p


def test_params_class_names_unique_in_llm_schema(draft_junction: DslTemplate, draft_deck: DslTemplate) -> None:
    from app.llm import spec

    with registry.overlay({DRAFT_JUNCTION: draft_junction, DRAFT_DECK: draft_deck}):
        schema = json.dumps(spec.api_schema(["hideout", DRAFT_JUNCTION, DRAFT_DECK]), ensure_ascii=False)
    assert "LibTunnelJunctionV901" in schema and "LibDeckPlatformV901" in schema
    assert "door_width_mm" in schema and "deck_thickness_mm" in schema


def test_next_key_for_drafts() -> None:
    top = max((e.version for e in index.entries().values() if e.family == "tunnel_junction"), default=0)
    assert next_key("tunnel_junction") == f"tunnel_junction@v{top + 1}"
    assert make_template(draft("tunnel_junction")).key == f"tunnel_junction@v{top + 1}"


def test_make_template_key_mismatch_rejected() -> None:
    with pytest.raises(DslError) as e:
        make_template(published(draft("tunnel_junction")), key="tunnel_junction@v2")
    assert e.value.code == "DSL014"
    with pytest.raises(DslError) as e:
        make_template(draft("tunnel_junction"), key="deck_platform@v1")
    assert e.value.code == "DSL014"
    with pytest.raises(DslError) as e:
        make_template(draft("tunnel_junction"), key="tunnel_junction@v1", published=True)
    assert e.value.code == "DSL014"
    assert make_template(published(draft("tunnel_junction")), key="tunnel_junction@v1", published=True).key == \
        "tunnel_junction@v1"


# ── 기본값 ──

@pytest.mark.parametrize("size, expect", [
    ("dwarf", {"wall_thickness_mm": 3.0, "layout": "T", "door_width_mm": 55.0, "door_shape": "round_arch",
               "size_mm": 81.0, "height_mm": 69.0}),
    ("syrian", {"wall_thickness_mm": 3.0, "layout": "T", "door_width_mm": 75.0, "door_shape": "round_arch",
                "size_mm": 101.0, "height_mm": 89.0}),
])
def test_junction_default_params_per_size(rules, junction: DslTemplate, size: str, expect: dict) -> None:
    """§6.1 표: 드워프 55/81/69, 골든 75/101/89."""
    assert junction.default_params(rctx(rules, size)).model_dump() == expect
    assert junction.default_params().model_dump() == junction.Params().model_dump()


def test_deck_and_tray_default_params(rules, deck: DslTemplate, tray: DslTemplate) -> None:
    for size in ("dwarf", "syrian"):
        p = deck.default_params(rctx(rules, size))
        assert (p.width_mm, p.depth_mm, p.height_mm, p.deck_thickness_mm, p.wall_thickness_mm) == (160, 120, 100, 4, 3)
    assert tray.default_params(rctx(rules, "dwarf")).model_dump() == {
        "wall_thickness_mm": 3.0, "width_mm": 130.0, "depth_mm": 130.0, "lip_height_mm": 30.0}
    assert tray.default_params(rctx(rules, "syrian")).model_dump() == {
        "wall_thickness_mm": 3.0, "width_mm": 146.0, "depth_mm": 146.0, "lip_height_mm": 30.0}


def test_default_params_round_and_clip(rules, room: DslTemplate) -> None:
    """정수 rule_default 는 0.5 올림 반올림, 모든 값은 필드 범위로 자른다."""
    assert room.default_params(rctx(rules, "dwarf", count=1)).vent_count == 2  # 1.5 → 2
    assert room.default_params(rctx(rules, "dwarf", count=2)).vent_count == 3  # 2.5 → 3
    assert room.default_params(rctx(rules, "dwarf", count=9)).vent_count == 4  # 9.5 → 10 → max 4
    big = make_template(room_data(params={**room_data()["params"], "door_mm": {
        "type": "number", "default": 50, "min": 25, "max": 60, "rule_default": "rule.entrance_min_diameter_mm * 3",
        "desc": text("출입구 폭 mm", "Door mm")}}), key="test_room@v1")
    assert big.default_params(rctx(rules, "dwarf")).door_mm == 60


# ── 제약, 검사 ──

def test_constraints_and_placeholders(rules, junction: DslTemplate) -> None:
    ctx = rctx(rules, "dwarf")
    p = junction.default_params(ctx)
    cs = junction.constraints(p, ctx)
    assert cs[0] == ctx.wall_thickness_constraint()
    by = {(c.field, c.min is not None): c for c in cs[1:]}
    door = by[("door_width_mm", True)]
    assert door.min == 50 and door.source == "species" and door.blocking
    assert door.reason_ko == f"{ctx.size.display_name} 갈림길 출입구는 최소 50mm 이상이어야 합니다"
    assert by[("size_mm", True)].min == 55 + 6 + 8
    assert by[("size_mm", True)].reason_ko == "모서리에 벽이 남도록 갈림길 가로·세로는 69mm 이상이어야 합니다"
    assert by[("height_mm", True)].min == pytest.approx(55 + 6)
    # 뾰족 아치: 경계값은 0.1 단위로 반올림해 적는다
    q = p.model_copy(update={"door_shape": "pointed_arch"})
    h = next(c for c in junction.constraints(q, ctx) if c.field == "height_mm")
    assert h.min == pytest.approx(55 / 2 + 55 / 2 / math.cos(math.radians(50)) + 6)
    assert h.reason_ko == f"출입구 위로 벽이 남도록 갈림길 높이는 {round(h.min, 1):g}mm 이상이어야 합니다"


def test_constraint_when_blocking_and_checks(rules, room: DslTemplate) -> None:
    ctx = rctx(rules, "syrian")
    p = room.Params()
    fields = [c.field for c in room.constraints(p, ctx)]
    assert fields == ["wall_thickness_mm", "width_mm", "height_mm"]  # when: back_door 거짓이면 빠진다
    q = p.model_copy(update={"back_door": True})
    cs = room.constraints(q, ctx)
    c = next(c for c in cs if c.field == "door_mm")
    assert c.max == 100 - 6 - 10 and c.blocking is False and c.reason_ko == "뒷문이 있으면 출입구는 84mm 이하"
    w = next(c for c in cs if c.field == "width_mm")
    assert w.reason_ko == f"{ctx.size.display_name} 방 가로는 66mm 이상"
    assert room.rule_issues(p, ctx) == []
    assert room.rule_issues(p.model_copy(update={"door_mm": 90, "width_mm": 60}), ctx) == ["출입구가 너무 넓어요"]


def test_constraint_with_null_rule_field_raises_dsl006(rules) -> None:
    """값이 없는(null) 규칙을 읽으면 DSL006 (검증기가 그 크기를 verified_for 에서 뺀다)."""
    t = make_template(room_data(constraints=[{"field": "height_mm", "max": "rule.max_climb_height_mm",
                                              "source": "species", "reason": text("높이 {0}", "Height {0}")}]),
                      key="test_room@v1")
    ctx = rctx(rules, "dwarf")
    size = ctx.size.model_copy(update={"max_climb_height_mm": None})
    with pytest.raises(DslError) as e:
        t.constraints(t.Params(), RuleContext(size, ctx.min_wall_mm))
    assert e.value.code == "DSL006" and e.value.path == "/constraints/0/max"


# ── 연결 지점 ──

LAYOUT_DOORS = {"I": {"front", "back"}, "L": {"front", "left"}, "T": {"front", "left", "right"},
                "X": {"front", "back", "left", "right"}}


@pytest.mark.parametrize("layout", ["I", "L", "T", "X"])
def test_junction_anchors_per_layout(junction: DslTemplate, layout: str) -> None:
    p = junction.Params(layout=layout, door_shape="pointed_arch", door_width_mm=55, size_mm=81, height_mm=80)
    a = junction.anchors(p)
    assert set(a) == {"front", "back", "left", "right", "top", "bottom"}
    S, H = 81.0, 80.0
    expect_origin = {"front": (0, -S / 2, 0), "back": (0, S / 2, 0), "left": (-S / 2, 0, 0), "right": (S / 2, 0, 0)}
    expect_normal = {"front": (0, -1, 0), "back": (0, 1, 0), "left": (-1, 0, 0), "right": (1, 0, 0)}
    for side in ("front", "back", "left", "right"):
        x = a[side]
        assert x.origin == pytest.approx(expect_origin[side]) and x.normal == expect_normal[side]
        assert x.up == (0, 0, 1)
        ff = junction.face_fields(p, side)
        if side in LAYOUT_DOORS[layout]:
            assert (x.side, x.port, x.wall_mm, x.profile, x.mount) == (side, 55, 3, "pointed_arch", None)
            assert ff.port == "door_width_mm" and ff.profile == "door_shape" and ff.wall == "wall_thickness_mm"
        else:
            # 닫힌 면: 연결판 자리만 (뚫을 수 없는 면, 출입 면 아님)
            assert (x.side, x.port, x.wall_mm, x.profile) == (None, None, None, None)
            assert x.mount == pytest.approx((-S / 2, S / 2, H))
            assert ff.port is None and ff.profile is None and ff.wall is None
        assert ff.width == "size_mm" and ff.height == "height_mm"
        # 단계 1 계약: face_fields.port 가 있으면 anchor.port 도 있다
        assert (ff.port is None) == (x.port is None)
    assert a["top"].origin == (0, 0, H) and a["top"].normal == (0, 0, 1) and a["top"].up == (0, 1, 0)
    assert a["bottom"].origin == (0, 0, 0) and a["bottom"].normal == (0, 0, -1) and a["bottom"].up == (0, 1, 0)
    assert junction.face_fields(p, "top").port is None and junction.face_fields(p, "nope").width is None


def test_deck_anchors(deck: DslTemplate) -> None:
    p = deck.Params()
    a = deck.anchors(p)
    assert set(a) == {"left", "right", "top", "bottom"}
    for side, x in (("left", -80.0), ("right", 80.0)):
        assert a[side].origin == (x, 0, 0) and a[side].mount == (-60, 60, 100)
        assert (a[side].side, a[side].port, a[side].wall_mm) == (None, None, None)
        assert deck.face_fields(p, side).height == "height_mm" and deck.face_fields(p, side).width == "depth_mm"


def test_declared_bottom_not_duplicated() -> None:
    d = room_data()
    d["anchors"] = {**d["anchors"], "bottom": {"origin": [0, 0, 0], "normal": "-Z", "up": "+X"}}
    t = make_template(d, key="test_room@v1")
    assert t.anchors(t.Params())["bottom"].up == (1, 0, 0)


def test_openable_anchor_and_open_port(room: DslTemplate) -> None:
    p = room.Params()
    back = room.anchors(p)["back"]
    # 문이 닫힌 openable 면: 벽(뚫을 수 있음)과 연결판 자리, side 없음
    assert (back.port, back.side, back.wall_mm, back.mount) == (None, None, 3.0, (-50, 50, 70))
    assert room.face_fields(p, "back").wall == "wall_thickness_mm" and room.face_fields(p, "back").port is None
    # openable 이 아닌 면은 벽이 없다
    assert room.anchors(p)["right"].wall_mm is None
    assert room.open_port(p, "front") is p
    q = room.open_port(p, "back")
    assert q is not None and q.back_door is True and q.width_mm == p.width_mm
    assert room.anchors(q)["back"].port == 50 and room.anchors(q)["back"].side == "back"
    assert room.open_port(q, "back") is q
    assert room.open_port(p, "right") is None  # opens 항목 없음
    assert room.open_port(p, "top") is None and room.open_port(p, "nowhere") is None


def test_open_port_when_and_failed_open() -> None:
    d = room_data()
    d["opens"] = [{"anchor": "back", "when": "width_mm > 150", "set": {"back_door": "True"}},
                  {"anchor": "back", "set": {"door_mm": "door_mm + 1"}}]  # 두 번째는 문을 열지 못한다
    t = make_template(d, key="test_room@v1")
    p = t.Params()
    assert t.open_port(p, "back") is None
    q = t.open_port(p.model_copy(update={"width_mm": 160}), "back")
    assert q is not None and q.back_door
    d["opens"] = [{"anchor": "back", "set": {"door_mm": "200", "back_door": "True"}}]  # 범위 밖 → None
    assert make_template(d, key="test_room@v1").open_port(p, "back") is None


def test_port_profile_and_cutter(junction: DslTemplate) -> None:
    for shape in ("round_arch", "pointed_arch", "box", "house"):
        p = junction.Params(door_shape=shape, door_width_mm=55, height_mm=90)
        prof = junction.port_profile(p, "front")
        ref = inner_profile(TunnelParams.model_construct(inner_diameter_mm=55, shape=shape, wall_thickness_mm=3))
        assert prof.area == pytest.approx(ref.area, rel=1e-9)
        assert (prof - ref).area == pytest.approx(0, abs=1e-6)
        cut = junction.port_cutter(p, "front", 10)
        bb = cut.bounding_box()
        # 기준점(y=-45)에서 0.5mm 안쪽부터 10mm 바깥까지, 폭 55
        assert (bb.min.Y, bb.max.Y) == pytest.approx((-55, -44.5))
        assert (bb.min.X, bb.max.X) == pytest.approx((-27.5, 27.5))
    p = junction.Params(layout="T")
    assert junction.port_profile(p, "back") is None and junction.port_cutter(p, "back", 5) is None
    assert junction.port_profile(p, "top") is None and junction.port_profile(p, "nope") is None


# ── 형상 ──

@pytest.mark.parametrize("layout", ["I", "L", "T", "X"])
def test_junction_door_cut_through_wall(junction: DslTemplate, layout: str) -> None:
    p = junction.Params(layout=layout)
    S, t = p.size_mm, p.wall_thickness_mm
    part = junction.build(p)
    mesh = part_to_mesh(part)
    h = mesh_health(mesh)
    assert h.watertight and h.winding_consistent and mesh.body_count == 1
    mid = S / 2 - t / 2  # 벽 두께 가운데
    probes = {"front": (0, -mid, 10), "back": (0, mid, 10), "left": (-mid, 0, 10), "right": (mid, 0, 10)}
    for side, xyz in probes.items():
        assert inside(part, xyz) is (side not in LAYOUT_DOORS[layout]), side
    assert inside(part, (S / 2 - 1, -mid, 10))  # 출입구 옆 벽은 남는다
    assert inside(part, (0, 0, p.height_mm - t / 2))  # 지붕


def test_envelope_equals_bbox(junction: DslTemplate, deck: DslTemplate, tray: DslTemplate, room: DslTemplate) -> None:
    for t, p in ((junction, junction.Params(layout="X", door_shape="house")), (deck, deck.Params()),
                 (tray, tray.Params(width_mm=150)), (room, room.Params(back_door=True))):
        bb = t.build(p).bounding_box()
        assert t.envelope(p) == pytest.approx((bb.size.X, bb.size.Y, bb.size.Z), abs=1e-6)
        assert (bb.min.Z, (bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2) == pytest.approx((0, 0, 0), abs=1e-6)


def test_envelope_fallback_for_role_none() -> None:
    d = shelf_data(role="none", attach_order={}, anchors={}, face_needs=None)
    del d["envelope"]
    d = {k: v for k, v in d.items() if v is not None}
    t = make_template(d, key="test_shelf@v1")
    p = t.Params()
    bb = t.build(p).bounding_box()
    assert t.envelope(p) == pytest.approx((bb.size.X, bb.size.Y, bb.size.Z))


def test_build_is_cached_but_returns_copies(junction: DslTemplate) -> None:
    p = junction.Params(layout="L")
    a, b = junction.build(p), junction.build(p)
    assert a is not b and a.wrapped is not b.wrapped
    assert a.volume == pytest.approx(b.volume)
    ma, mb = part_to_mesh(a), part_to_mesh(b)
    assert np.array_equal(ma.vertices, mb.vertices) and np.array_equal(ma.faces, mb.faces)


def test_build_deterministic_across_fresh_templates() -> None:
    """같은 파라미터 → 같은 메시 바이트 (기억 없이 새로 만든 템플릿끼리도)."""
    a = make_template(draft("tunnel_junction"), key="tunnel_junction@v1")
    b = make_template(draft("tunnel_junction"), key="tunnel_junction@v1")
    p = a.Params(layout="X", door_shape="pointed_arch")
    ma, mb = part_to_mesh(a.build(p)), part_to_mesh(b.build(b.Params(**p.model_dump())))
    assert ma.vertices.tobytes() == mb.vertices.tobytes() and ma.faces.tobytes() == mb.faces.tobytes()


def test_repeat_and_when(room: DslTemplate) -> None:
    """repeat 개수만큼 지붕 환기구가 뚫린다 (i 는 0부터). vent_count 0 이면 없다."""
    for n in (0, 1, 2, 3):
        p = room.Params(vent_count=n)
        part = room.build(p)
        holes = [inside(part, ((i - 0.5) * 20, 0, p.height_mm - 1.5)) for i in range(3)]
        assert holes == [i >= n for i in range(3)], n
    d = room_data()
    d["body"][2]["when"] = "i != 1"
    t = make_template(d, key="test_room@v1")
    part = t.build(t.Params(vent_count=3))
    assert [inside(part, ((i - 0.5) * 20, 0, 68.5)) for i in range(3)] == [False, True, False]


def test_repeat_count_must_be_whole_and_bounded() -> None:
    d = room_data()
    d["body"][2]["repeat"] = {"i": "vent_count + 0.5"}
    t = make_template(d, key="test_room@v1")
    with pytest.raises(DslError) as e:
        t.build(t.Params())
    assert e.value.code == "DSL006" and e.value.path == "/body/2/repeat/i"
    d["body"][2]["repeat"] = {"i": 9, "j": 8}
    t = make_template(d, key="test_room@v1")
    with pytest.raises(DslError) as e:
        t.build(t.Params())
    assert e.value.code == "DSL006" and "limit is 64" in e.value.message


def test_cut_before_add_is_dsl020() -> None:
    d = room_data()
    d["body"] = [d["body"][1], d["body"][0]]
    with pytest.raises(DslError) as e:
        make_template(d, key="test_room@v1")
    assert any(x.code == "DSL020" and x.path == "/body/0/mode" for x in e.value.errors)
    # 실행할 때: 유일한 add 가 when 으로 빠지면 DSL020
    d = room_data()
    d["body"][0]["when"] = "width_mm < 70"
    t = make_template(d, key="test_room@v1")
    with pytest.raises(DslError) as e:
        t.build(t.Params())
    assert e.value.code == "DSL020"


def test_print_parts_single(junction: DslTemplate) -> None:
    p = junction.Params()
    built = junction.build(p)
    pp = junction.print_parts(p, built=built)
    assert len(pp) == 1 and pp[0].part is built and pp[0].key == "body" and pp[0].name_ko == "본체"
    assert np.array_equal(pp[0].rotation, np.diag([1.0, -1.0, -1.0]))
    assert np.array_equal(junction.print_rotation(p), pp[0].rotation)
    assert pp[0].thin_ok == ()
    assert junction.print_parts(p)[0].part.volume == pytest.approx(built.volume)


def test_print_parts_multi(shelf: DslTemplate) -> None:
    p = shelf.Params()
    pp = shelf.print_parts(p)
    assert [(x.key, x.name_ko) for x in pp] == [("body", "본체"), ("peg", "못")]
    assert np.array_equal(pp[0].rotation, np.eye(3)) and np.array_equal(pp[1].rotation, ROTATIONS["left_down"])
    assert np.array_equal(shelf.print_rotation(p), np.eye(3))
    union = shelf.build(p)
    assert union.volume == pytest.approx(pp[0].part.volume + pp[1].part.volume, rel=1e-6)  # 서로 떨어져 있다
    # peg: prism (xz, 넓이 50, 두께 6) + x 축 원기둥 (r 3, 길이 20; 아래 끝 z=0)
    peg = pp[1].part.bounding_box()
    assert (peg.min.X, peg.max.X) == pytest.approx((-5, 15))
    assert (peg.min.Y, peg.max.Y) == pytest.approx((27, 33))
    assert (peg.min.Z, peg.max.Z) == pytest.approx((0, 10))
    assert shelf.face_needs(p) == (45, None)


@pytest.mark.parametrize("name", list(ROTATIONS))
def test_rotation_puts_named_face_on_bed(name: str) -> None:
    R = ROTATIONS[name]
    assert np.allclose(R @ np.asarray(ops.BED_FACE_NORMALS[name]), (0, 0, -1))
    assert np.allclose(R @ R.T, np.eye(3)) and np.linalg.det(R) == pytest.approx(1)


# ── 특징 ──

@pytest.mark.parametrize("layout", ["I", "L", "T", "X"])
def test_junction_features(junction: DslTemplate, layout: str) -> None:
    p = junction.Params(layout=layout, door_width_mm=58)
    f = junction.features(p)
    order = [s for s in ("front", "back", "left", "right") if s in LAYOUT_DOORS[layout]]
    assert [(o.kind, o.size_mm, o.label_ko, o.rule_key) for o in f.openings] == [
        ("passage", 58, DOOR_LABEL_KO[s], "entrance_min_diameter_mm") for s in order]
    assert f.access_sides == tuple(order)
    assert f.entrance_count == len(order)
    assert f.min_wall_thickness_mm == 3 and f.extra == {}
    assert (f.climb_height_mm, f.slope_deg, f.step_height_mm) == (None, None, None)


def test_deck_and_tray_features(deck: DslTemplate, tray: DslTemplate) -> None:
    p = deck.Params(wall_thickness_mm=5, deck_thickness_mm=4)
    f = deck.features(p)
    assert f.min_wall_thickness_mm == 4 and f.climb_height_mm == 100 and f.entrance_count is None
    assert f.access_sides == ("front", "back")
    assert [(o.kind, o.size_mm, o.label_ko, o.rule_key) for o in f.openings] == [
        ("passage", 96, "발판 아래 통로", "entrance_min_diameter_mm")]
    t = tray.features(tray.Params())
    assert (t.step_height_mm, t.access_sides, t.openings, t.entrance_count) == (30, ("front",), (), None)


def test_room_features_derived_openings(room: DslTemplate) -> None:
    f = room.features(room.Params())
    assert [(o.kind, o.size_mm, o.label_ko) for o in f.openings] == [
        ("passage", 50, "앞 출입구"), ("vent", 4, "환기구"), ("window", 8, "창")]
    assert f.access_sides == ("front",) and f.entrance_count == 1
    g = room.features(room.Params(back_door=True, vent_count=0))
    assert [(o.kind, o.label_ko) for o in g.openings] == [
        ("passage", "앞 출입구"), ("passage", "뒤 출입구"), ("window", "창")]
    assert g.access_sides == ("front", "back", "left") and g.entrance_count == 2
    s = make_template(shelf_data(), key="test_shelf@v1")
    assert s.features(s.Params()).min_wall_thickness_mm == 1.5


def test_vent_size_from_passage_step() -> None:
    d = room_data()
    d["body"].append({"op": "passage", "mode": "cut", "id": "hall", "shape": "shape", "width": "door_mm - 10",
                      "axis": "x", "length": 20, "at": [0, 0, 0]})
    d["features"]["openings"] = [{"kind": "window", "step": "hall", "label": text("창", "Window")}]
    t = make_template(d, key="test_room@v1")
    assert [o.size_mm for o in t.features(t.Params()).openings if o.kind == "window"] == [40]


# ── ops ──

def test_ops_box_and_cylinder_alignment() -> None:
    bb = ops.box((10, 20, 30), (1, 2, 3), "bottom").bounding_box()
    assert (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z) == pytest.approx((-4, 6, -8, 12, 3, 33))
    bb = ops.box((10, 20, 30), (1, 2, 3), "center").bounding_box()
    assert (bb.min.Z, bb.max.Z) == pytest.approx((-12, 18))
    for axis, ext in (("x", (20, 10, 10)), ("y", (10, 20, 10)), ("z", (10, 10, 20))):
        bb = ops.cylinder(5, 20, axis, (1, 2, 3), "bottom").bounding_box()
        assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx(ext)
        assert bb.min.Z == pytest.approx(3)
        assert ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2) == pytest.approx((1, 2))
        bb = ops.cylinder(5, 20, axis, (1, 2, 3), "center").bounding_box()
        assert ((bb.min.Z + bb.max.Z) / 2) == pytest.approx(3)
    with pytest.raises(DslError) as e:
        ops.box((10, 0, 3), (0, 0, 0), "bottom", "/body/4")
    assert e.value.code == "DSL006" and e.value.path == "/body/4/size/1"


def test_ops_prism_planes_winding_and_simple_polygon() -> None:
    tri = [(0, 0), (10, 0), (0, 10)]
    for plane, ext in (("xz", (10, 4, 10)), ("yz", (4, 10, 10)), ("xy", (10, 10, 4))):
        a = ops.prism(plane, tri, 4, (1, 2, 3))
        b = ops.prism(plane, list(reversed(tri)), 4, (1, 2, 3))  # 감는 방향은 맞춰진다
        assert a.volume == pytest.approx(200) and b.volume == pytest.approx(200)
        bb = a.bounding_box()
        assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx(ext)
    bb = ops.prism("xz", tri, 4, (1, 2, 3)).bounding_box()
    assert (bb.min.X, bb.min.Y, bb.max.Y, bb.min.Z) == pytest.approx((1, 0, 4, 3))  # 깊이는 at 에 대칭
    with pytest.raises(DslError) as e:
        ops.prism("xz", [(0, 0), (10, 10), (10, 0), (0, 10)], 4, (0, 0, 0), "/body/1")  # 나비넥타이
    assert e.value.code == "DSL006" and e.value.path == "/body/1/points"
    with pytest.raises(DslError):
        ops.prism("xz", [(0, 0), (5, 0), (10, 0)], 4, (0, 0, 0))  # 넓이 0


def test_ops_passage() -> None:
    cut = ops.passage("round_arch", 40, "y", 30, (0, 5, 10))
    bb = cut.bounding_box()
    assert (bb.min.X, bb.max.X) == pytest.approx((-20, 20))
    assert (bb.min.Y, bb.max.Y) == pytest.approx((-10, 20))
    assert (bb.min.Z, bb.max.Z) == pytest.approx((9, 50))  # 바닥 at.z 의 1mm 아래부터, 높이 = 폭
    bb = ops.passage("box", 40, "x", 30, (0, 0, 0)).bounding_box()
    assert (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y) == pytest.approx((-15, 15, -20, 20))
    with pytest.raises(DslError):
        ops.passage("tube", 40, "x", 30, (0, 0, 0))


# ── 구조 검사 (읽을 때) ──

@pytest.mark.parametrize("mutate, code, path", [
    (lambda d: d["print"].__setitem__(0, {**d["print"][0], "key": "main"}), "DSL010", "/print/0/key"),
    (lambda d: d["body"][0].__setitem__("part", "lid"), "DSL002", "/body/0/part"),
    (lambda d: d["anchors"]["front"].pop("wall"), "DSL011", "/anchors/front/wall"),
    (lambda d: d["anchors"]["front"].pop("side"), "DSL011", "/anchors/front/side"),
    (lambda d: d["anchors"]["top"].__setitem__("up", "+Z"), "DSL010", "/anchors/top/up"),
    (lambda d: d["anchors"]["front"]["fields"].__setitem__("port", "door_width"), "DSL002",
     "/anchors/front/fields/port"),
    (lambda d: d.__setitem__("size_fields", ["shape"]), "DSL003", "/size_fields/0"),
    (lambda d: d.__setitem__("height_field", "tall_mm"), "DSL002", "/height_field"),
    (lambda d: d["constraints"][0].__setitem__("field", "nope_mm"), "DSL002", "/constraints/0/field"),
    (lambda d: d.__setitem__("attach_order", {"passage": ["side"]}), "DSL002", "/attach_order/passage/0"),
    (lambda d: d["opens"][0].__setitem__("anchor", "right"), "DSL010", "/opens/0/anchor"),
    (lambda d: d["features"]["openings"][1].pop("axis"), "DSL011", "/features/openings/1/axis"),
    (lambda d: d["features"]["openings"][0].__setitem__("step", "vents"), "DSL002", "/features/openings/0/step"),
    (lambda d: d.pop("envelope"), "DSL011", "/envelope"),
    (lambda d: (d["params"].__setitem__("wall_mm", d["params"].pop("wall_thickness_mm")),
                d["let"][2].__setitem__("expr", "wall_mm"),
                d["checks"][0].__setitem__("fail_if", "door_mm > W - 2 * t")), "DSL011", "/params/wall_thickness_mm"),
])
def test_structure_errors(mutate, code: str, path: str) -> None:
    d = copy.deepcopy(room_data())
    mutate(d)
    with pytest.raises(DslError) as e:
        make_template(d, key="test_room@v1")
    assert (code, path) in [(x.code, x.path) for x in e.value.errors], e.value


def test_schema_and_expression_errors_surface() -> None:
    with pytest.raises(DslError) as e:
        make_template({**room_data(), "colour": "#ffffff"}, key="test_room@v1")
    assert e.value.code == "DSL012"
    d = room_data()
    d["anchors"]["front"]["door"]["profile"] = "'tube'"
    with pytest.raises(DslError) as e:
        make_template(d, key="test_room@v1")
    assert e.value.code == "DSL003"


# ── 라이브러리 읽기 (fail fast) ──

def write_library(root: Path, parts: list[tuple[dict, str]], *, raw: dict[str, bytes] | None = None,
                  index_over: dict[str, dict] | None = None) -> Path:
    """parts: (게시 파일 dict, 상태). raw: key → 바꿔 쓸 파일 바이트 (색인 sha 는 원래 파일 기준)."""
    (root / "parts").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    entries = {}
    for obj, status in parts:
        key = obj["key"]
        data = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode()
        (root / "parts" / f"{key}.json").write_bytes((raw or {}).get(key, data))
        entries[key] = {"sha256": sha256_bytes(data), "status": status, "published_at": "2026-12-03",
                        "family": obj["family"], "version": obj["version"], "role": obj["role"],
                        "habitats": obj["habitats"], **(index_over or {}).get(key, {})}
    (root / "index.json").write_text(dump_index({"v": 1, "parts": entries}), encoding="utf-8")
    return root


@pytest.fixture
def libdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def use(parts, **kw) -> Path:
        root = write_library(tmp_path / "lib", parts, **kw)
        monkeypatch.setattr(index, "LIBRARY_DIR", root)
        index.clear_cache()
        return root

    yield use
    index.clear_cache()


def test_load_library_reads_every_status_in_key_order(libdir) -> None:
    libdir([(published(draft("tunnel_junction")), "active"), (published(draft("deck_platform")), "retired"),
            (published(draft("litter_tray"), 2), "blocked"), (published(room_data()), "active")])
    t0 = time.perf_counter()
    lib = load_library()
    elapsed = time.perf_counter() - t0
    assert list(lib) == ["deck_platform@v1", "litter_tray@v2", "test_room@v1", "tunnel_junction@v1"]
    assert type(lib["litter_tray@v2"]).__name__ == "LibLitterTrayV2"
    assert [(t.status, t.retired, t.blocked) for t in lib.values()] == [
        ("retired", True, False), ("blocked", True, True), ("active", False, False), ("active", False, False)]
    assert all(type(t).__module__ == "app.library.template" for t in lib.values())
    assert elapsed < 0.3, elapsed  # 부품마다 ≤ 30 ms 예산 (넉넉히 4개에 0.3 s)
    assert next_key("litter_tray") == "litter_tray@v3"


def test_load_library_empty_index(libdir) -> None:
    libdir([])
    assert index.keys() == ()
    assert load_library() == {}


def test_load_library_sha_mismatch_fails(libdir) -> None:
    obj = published(draft("deck_platform"))
    edited = (json.dumps({**obj, "color": "#000000"}, ensure_ascii=False, indent=2) + "\n").encode()
    libdir([(obj, "active")], raw={obj["key"]: edited})
    with pytest.raises(LibraryError, match="sha256"):
        load_library()


def test_load_library_invalid_file_fails(libdir) -> None:
    bad = published(room_data())
    bad["anchors"]["front"].pop("wall")
    libdir([(bad, "active")])
    with pytest.raises(LibraryError, match="DSL011"):
        load_library()


def test_load_library_schema_error_fails(libdir) -> None:
    libdir([({**published(draft("deck_platform")), "colour": "#000000"}, "active")])
    with pytest.raises(LibraryError, match="DSL012"):
        load_library()


def test_load_library_draft_file_fails(libdir) -> None:
    """게시 파일에는 key·version 이 있어야 한다."""
    obj = published(draft("deck_platform"))
    data = (json.dumps(draft("deck_platform"), ensure_ascii=False, indent=2) + "\n").encode()
    root = libdir([(obj, "active")])
    (root / "parts" / "deck_platform@v1.json").write_bytes(data)
    idx = json.loads((root / "index.json").read_text())
    idx["parts"]["deck_platform@v1"]["sha256"] = sha256_bytes(data)
    (root / "index.json").write_text(dump_index(idx))
    index.clear_cache()
    with pytest.raises(LibraryError, match="DSL014"):
        load_library()


def test_load_library_index_mismatch_fails(libdir) -> None:
    obj = published(draft("deck_platform"))
    libdir([(obj, "active")], index_over={obj["key"]: {"role": "accessory"}})
    with pytest.raises(LibraryError, match="differ from the index"):
        load_library()


# ── 레지스트리 ──

def test_registry_code_parts_first_then_index() -> None:
    """코드 부품(지금 순서) 다음에 색인의 부품. 색인이 비어 있으면 코드 부품뿐이다 (단계 1 과 같은 레지스트리)."""
    assert tuple(registry.primitives()) == REGISTERED
    assert registry.code_keys() == CODE_KEYS
    assert [t.key for t in registry.all_templates()] == list(REGISTERED)


def _run_registry(root: Path) -> subprocess.CompletedProcess:
    code = (
        "import sys; from pathlib import Path; from app.library import index; "
        f"index.LIBRARY_DIR = Path({str(root)!r}); "
        "from app.templates import registry; "
        "print(','.join(registry.primitives())); "
        "print(type(registry.get_template('tunnel_junction@v1')).__name__)"
    )
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=120,
                          check=False)


def test_registry_order_code_then_library(tmp_path: Path) -> None:
    root = write_library(tmp_path / "lib", [(published(draft("tunnel_junction")), "active"),
                                            (published(draft("deck_platform")), "retired")])
    r = _run_registry(root)
    assert r.returncode == 0, r.stderr
    keys, cls = r.stdout.strip().splitlines()
    assert keys.split(",") == [*CODE_KEYS, "deck_platform@v1", "tunnel_junction@v1"]
    assert cls == "LibTunnelJunctionV1"


def test_registry_import_fails_fast_on_bad_library(tmp_path: Path) -> None:
    obj = published(draft("deck_platform"))
    root = write_library(tmp_path / "lib", [(obj, "active")], raw={obj["key"]: b"{}\n"})
    r = _run_registry(root)
    assert r.returncode != 0 and "LibraryError" in r.stderr and "sha256" in r.stderr


def test_spec_caches_list_matches_module() -> None:
    """overlay 가 비우는 목록이 app.llm.spec 의 lru_cache 함수 전부와 같다 (함수가 늘면 목록도 늘려야 한다)."""
    from app.llm import spec

    cached = {name for name, f in vars(spec).items()
              if callable(f) and hasattr(f, "cache_clear") and getattr(f, "__module__", "") == spec.__name__}
    assert cached == set(registry.SPEC_CACHES)


def test_overlay_adds_and_removes_with_cache_clearing(draft_junction: DslTemplate) -> None:
    from app.llm import spec
    from app.modules import compose

    junction = draft_junction
    spec.api_schema()  # 기억을 채운다
    assert spec._api_schema_cached.cache_info().currsize > 0
    with registry.overlay({junction.key: junction}):
        assert spec._api_schema_cached.cache_info().currsize == 0
        assert compose.composed_template.cache_info().currsize == 0
        assert registry.get_template(junction.key) is junction
        assert list(registry.primitives())[-1] == junction.key
        assert junction in registry.all_templates()
        assert junction.key in spec.template_keys()
        assert "LibTunnelJunctionV901" in json.dumps(spec.api_schema())
    assert junction.key not in registry.primitives()
    with pytest.raises(KeyError):
        registry.get_template(junction.key)
    assert tuple(registry.primitives()) == REGISTERED
    assert spec._api_schema_cached.cache_info().currsize == 0
    assert "LibTunnelJunctionV901" not in json.dumps(spec.api_schema())
    with pytest.raises(ValueError):
        spec.template_keys([junction.key])


def test_overlay_rejects_clash_and_restores_on_error(draft_junction: DslTemplate) -> None:
    junction = draft_junction
    with pytest.raises(ValueError, match="already registered"), registry.overlay({"hideout": junction}):
        pass
    with pytest.raises(RuntimeError), registry.overlay({junction.key: junction}):
        raise RuntimeError("boom")
    assert tuple(registry.primitives()) == REGISTERED


def test_overlay_composes_with_library_parts(rules, draft_junction: DslTemplate, draft_deck: DslTemplate) -> None:
    """초안이 등록된 동안 조립 해석기가 키로 찾는다: 은신처 → 터널 → 갈림길 (단면 맞춤), 플랫폼 + 램프."""
    from app.modules import compose
    from app.modules.structure import AssemblyRequest
    from app.validation.report import Issue

    ctx = rctx(rules, "dwarf")
    junction, deck = draft_junction, draft_deck
    with registry.overlay({junction.key: junction, deck.key: deck}):
        tm = registry.primitives()

        def req(parts, conns) -> AssemblyRequest:
            return AssemblyRequest(
                parts=[{"id": a, "template": b, "params": tm[b].default_params(ctx).model_dump()} for a, b in parts],
                connections=[{"part": a, "to": b, "at": c} for a, b, c in conns])

        out = compose.resolve(req([("house", "house"), ("tube", "tunnel"), ("hub", junction.key)],
                                  [("tube", "house", "front"), ("hub", "tube", "free_end")]), None, ctx, templates=tm)
        assert not isinstance(out, Issue), out.message_ko
        res, params, issues = out
        assert ("tube.end_a", "hub.front", "plug", "into_child") in [
            (j.parent, j.child, j.mount, j.passage) for j in res.joins]
        assert params["hub"].door_shape == "pointed_arch"
        assert "passage_shape_matched" in [i.code for i in issues]
        out = compose.resolve(req([("deck", deck.key), ("ramp", "ramp")], [("ramp", "deck", "right")]),
                              None, ctx, templates=tm)
        assert not isinstance(out, Issue), out.message_ko
        assert [(j.parent, j.child, j.mount) for j in out[0].joins] == [("deck.right", "ramp.landing", "slide")]
