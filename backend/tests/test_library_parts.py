"""게시된 라이브러리 부품 (설계 문서 §6, §14 "Stored rebuild e2e"; T12–T14: 터널 갈림길, 발판 플랫폼, 화장실 트레이).

저장소 라이브러리(app/library)의 부품이 레지스트리에 등록되고 종에 허용되며, 조립에서 설계 문서대로 이어지고,
그 부품을 쓴 설계를 저장한 뒤 메시 캐시를 지우고 조립 해석기를 막아도 같은 바이트로 다시 만들어지는지 본다.

부품 파일·골든·게이팅 자체의 검사는 tests/test_library_published.py (audit) 가 한다. 여기는 부품마다의 동작이다.
부품을 더 게시하면 아래 표들(PUBLISHED, STORED_FIXTURES)에 한 줄씩 더하고 부품별 시험을 덧붙인다.

화장실 트레이(T14)는 게시했지만 햄스터에 허용하지 않았다: 넣으면 햄스터 구조화 출력 스키마가 29,000자 한도(R12)를
넘는다 (검증 보고서 gate_ok false). 카탈로그 좁히기(2c) 뒤에 게이팅한다. 그래서 트레이 저장·다시 만들기 시험은
트레이를 허용한 규칙 사본으로 돌린다.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import BACKEND_DIR
from app.geometry.fingerprint import geometry_fingerprint
from app.library import index
from app.llm.base import InterpretRequest, InterpretResult
from app.llm.spec import api_schema, parse_spec
from app.main import create_app
from app.models import DesignVersion
from app.modules import compose
from app.modules.structure import AssemblyRequest
from app.services import design_service
from app.templates.base import RuleContext
from app.templates.registry import primitives
from app.validation.autofix import clamp_params
from app.validation.report import Issue, Severity
from tests.api_helpers import create_habitat, make_settings

JUNCTION = "tunnel_junction@v1"
DECK = "deck_platform@v1"
TRAY = "litter_tray@v1"
# 게시된 부품: key → (이름, 역할, 햄스터에 허용)
PUBLISHED = {JUNCTION: ("터널 갈림길", "room_host", True), DECK: ("발판 플랫폼", "host", True),
             TRAY: ("화장실 트레이", "accessory", False)}
FIXTURES = Path(__file__).parent / "data" / "compositions"
# 저장·다시 만들기를 보는 고정 데이터: 고정 데이터 이름 → (크기 구분, 들어 있어야 하는 라이브러리 부품)
STORED_FIXTURES = {"junction_network": ("dwarf", {"hub": JUNCTION}),
                   "platform_with_ramps": ("syrian", {"deck": DECK})}
ROOMY = {"width_mm": 1000, "depth_mm": 600, "height_mm": 400}
SCHEMA_GATE = 29_000  # R12: 햄스터 구조화 출력 스키마 게이팅 한도 (tests/test_llm.py 의 30,000 보다 낮다)


def rctx(rules, size: str, count: int = 1) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), count,
                       printing_max_overhang_deg=rules.printing.max_overhang_deg,
                       min_feature_mm=rules.printing.min_feature_mm)


def dp(key: str, ctx: RuleContext, **over) -> dict:
    return {**primitives()[key].default_params(ctx).model_dump(mode="json"), **over}


def resolve(parts: list[tuple], conns: list[tuple], ctx: RuleContext):
    req = AssemblyRequest(parts=[{"id": a, "template": b, "params": c} for a, b, c in parts],
                          connections=[{"part": a, "to": b, "at": c} for a, b, c in conns])
    return compose.resolve(req, None, ctx)


def resolve_ok(parts: list[tuple], conns: list[tuple], ctx: RuleContext):
    out = resolve(parts, conns, ctx)
    assert not isinstance(out, Issue), out
    return out


def joins(res) -> list[tuple[str, str, str]]:
    return [(j.parent, j.child, j.mount) for j in res.joins]


def settle_passes(res, params, ctx: RuleContext) -> list[Issue]:
    """엔진과 같은 길: 조립 항목 템플릿 → 조립 제약으로 보정 → 규칙·형상 검사. 문제 목록."""
    t = compose.template_for(res)
    p, issues = clamp_params(t, compose.assembly_params(t, params), ctx, max_passes=compose.ASSEMBLY_MAX_PASSES)
    return [i for i in issues if i.severity == Severity.error] + t.rule_issues(p, ctx)


# ── 등록·게이팅 ───────────────────────────────────────────────


@pytest.mark.parametrize("key", sorted(PUBLISHED))
def test_published_part_is_registered_and_offered(rules, key) -> None:
    name, role, gated = PUBLISHED[key]
    e = index.entry(key)
    assert e is not None and e.status == "active"
    assert set(e.verified_for["hamster"]) == set(rules.species_entry("hamster").sizes)
    t = primitives()[key]
    assert type(t).__module__ == "app.library.template"
    assert (t.key, t.display_name_ko, t.role) == (key, name, role)
    # 코드 부품 뒤에 온다 (조립 해석기는 터널을 key 로 찾으므로 순서에 기대지 않는다)
    order = list(primitives())
    assert all(order.index(k) < order.index(key) for k in order if "@" not in k)
    assert (key in rules.allowed_templates("hamster")) is gated
    assert (key in rules.offered_templates("hamster")) is gated


def test_hamster_schema_stays_under_the_gating_budget(rules) -> None:
    """R12: 게이팅한 부품을 넣은 햄스터 구조화 출력 스키마는 29,000자 이하."""
    n = len(json.dumps(api_schema(rules.offered_templates("hamster")), ensure_ascii=False))
    assert n <= SCHEMA_GATE, n


@pytest.mark.parametrize("key", sorted(PUBLISHED))
def test_gating_follows_the_verify_report(rules, key) -> None:
    """햄스터 허용 여부는 마지막 검증 보고서의 gate_ok(R01, R12)를 따른다. 화장실 트레이는 넣으면 스키마가
    한도를 넘어(gate_ok false) 허용하지 않았고, 다른 부품은 한도 안이라 허용했다 (설계 §6.3)."""
    report = json.loads((index.library_dir() / index.REPORTS_DIR / f"{key}.json").read_text(encoding="utf-8"))[-1]
    assert report["result"] == "pass" and report["profile"] == "full"
    assert report["schema"]["chars_added"] <= 2_300
    gate_ok = report["schema"]["gate_ok"]["hamster"]
    assert gate_ok is PUBLISHED[key][2]
    if not gate_ok:
        assert report["schema"]["totals"]["hamster"] > SCHEMA_GATE


# ── tunnel_junction@v1 (설계 문서 §6.1) ───────────────────────────


@pytest.mark.parametrize(("size", "door", "side", "height"), [("dwarf", 55, 81, 69), ("syrian", 75, 101, 89)])
def test_junction_defaults_per_size(rules, size, door, side, height) -> None:
    t = primitives()[JUNCTION]
    ctx = rctx(rules, size)
    p = t.default_params(ctx)
    assert p.model_dump() == {"wall_thickness_mm": 3.0, "layout": "T", "door_width_mm": door,
                              "door_shape": "round_arch", "size_mm": side, "height_mm": height}
    p2, issues = clamp_params(t, p, ctx)
    assert p2 == p and issues == []  # 기본값은 보정 없이 맞는다 (P1)
    assert t.rule_issues(p, ctx) == []
    f = t.features(p)
    assert f.entrance_count == 3 and set(f.access_sides) == {"front", "left", "right"}


@pytest.mark.parametrize(("layout", "doors"), [("I", {"front", "back"}), ("L", {"front", "left"}),
                                               ("T", {"front", "left", "right"}),
                                               ("X", {"front", "back", "left", "right"})])
def test_junction_layout_decides_the_doors(rules, layout, doors) -> None:
    """출입구가 아닌 옆면은 받침면이다 (벽 없음: 터널을 이으려고 뚫지 않는다, 설계 §6.1)."""
    t = primitives()[JUNCTION]
    p = t.Params.model_validate({**dp(JUNCTION, rctx(rules, "dwarf")), "layout": layout})
    anchors = t.anchors(p)
    assert {n for n, a in anchors.items() if compose.is_door(a)} == doors
    for side in {"front", "back", "left", "right"} - doors:
        a = anchors[side]
        assert a.port is None and a.wall_mm is None and a.mount is not None
        assert t.open_port(p, side) is None
    assert t.features(p).entrance_count == len(doors)


def test_junction_network_shares_one_width_and_shape(rules) -> None:
    """은신처 → 터널 → 갈림길 → 터널 두 개 → 은신처 두 개: 지름이 첫 은신처 출입구 하나로 묶이고 단면은 둥근 아치."""
    ctx = rctx(rules, "syrian")
    hide = dp("hideout", ctx)
    tube = dp("tunnel", ctx, shape="tube")
    res, params, issues = resolve_ok(
        [("hide", "hideout", hide), ("tube", "tunnel", tube), ("hub", JUNCTION, dp(JUNCTION, ctx)),
         ("tube2", "tunnel", tube), ("hide2", "hideout", hide), ("tube3", "tunnel", tube), ("hide3", "hideout", hide)],
        [("tube", "hide", "front"), ("hub", "tube", "free_end"), ("tube2", "hub", "left"),
         ("hide2", "tube2", "free_end"), ("tube3", "hub", "right"), ("hide3", "tube3", "free_end")], ctx)
    ties = {t["follower"]: t["owner"] for t in res.stored()["ties"]}
    for path in ("tube.inner_diameter_mm", "hub.door_width_mm", "tube2.inner_diameter_mm", "tube3.inner_diameter_mm",
                 "hide2.entrance_diameter_mm", "hide3.entrance_diameter_mm"):
        assert ties[path] == "hide.entrance_diameter_mm", path
    assert len({params["hub"].door_width_mm, params["tube2"].inner_diameter_mm, params["hide3"].entrance_diameter_mm,
                params["hide"].entrance_diameter_mm}) == 1
    assert {params[p].shape for p in ("tube", "tube2", "tube3")} == {"round_arch"}  # 둥근 관 → 은신처 단면
    assert params["hub"].door_shape == "round_arch" and res.stored()["fixed"]["hub.layout"] == "T"
    assert all(i.severity == Severity.info for i in issues)


def test_junction_adopts_the_house_tunnel_shape(rules) -> None:
    """집(뾰족 아치) → 터널 → 갈림길: 갈림길 출입구 단면이 터널에 맞춰 뾰족 아치가 되고, 높이가 그만큼 자란다."""
    ctx = rctx(rules, "dwarf")
    res, params, issues = resolve_ok(
        [("house", "house", dp("house", ctx)), ("tube", "tunnel", dp("tunnel", ctx)),
         ("hub", JUNCTION, dp(JUNCTION, ctx))],
        [("tube", "house", "front"), ("hub", "tube", "free_end")], ctx)
    assert params["tube"].shape == "pointed_arch" and params["hub"].door_shape == "pointed_arch"
    assert res.stored()["fixed"]["hub.door_shape"] == "pointed_arch"
    (matched,) = [i for i in issues if i.code == "passage_shape_matched"]
    assert matched.details["part"] == "hub" and matched.details["to"] == "pointed_arch"
    assert "뾰족 아치" in matched.message_ko
    assert settle_passes(res, params, ctx) == []


def test_junction_room_at_a_closed_face_is_relocated_and_accessories_slide_on(rules) -> None:
    """T 배치의 뒷면(닫힌 면)에 잇는 터널은 빈 출입구로 옮기고, 그릇 받침은 닫힌 면에 끼운다."""
    ctx = rctx(rules, "dwarf")
    res, _, issues = resolve_ok(
        [("hub", JUNCTION, dp(JUNCTION, ctx)), ("tube", "tunnel", dp("tunnel", ctx)),
         ("bowl", "bowl_holder", dp("bowl_holder", ctx))],
        [("tube", "hub", "back"), ("bowl", "hub", "back")], ctx)
    assert joins(res) == [("hub.front", "tube.end_b", "plug"), ("hub.back", "bowl.back", "slide")]
    assert [i.details["part"] for i in issues if i.code == "join_relocated"] == ["tube"]


def test_junction_cannot_mix_house_and_hideout_doors(rules) -> None:
    """알려진 한계 (설계 §6.1, port_adapter 는 2c): 둥근 아치 은신처와 뾰족 아치 집을 한 갈림길에 이을 수 없다."""
    ctx = rctx(rules, "dwarf")
    out = resolve(
        [("hide", "hideout", dp("hideout", ctx)), ("tube", "tunnel", dp("tunnel", ctx)),
         ("hub", JUNCTION, dp(JUNCTION, ctx)), ("tube2", "tunnel", dp("tunnel", ctx)),
         ("house", "house", dp("house", ctx))],
        [("tube", "hide", "front"), ("hub", "tube", "free_end"), ("tube2", "hub", "left"),
         ("house", "tube2", "free_end")], ctx)
    assert isinstance(out, Issue) and out.code == compose.JOIN_UNSUPPORTED


def test_mock_reads_three_hideouts_off_a_junction(rules) -> None:
    """모의 해석기: "갈림길로 은신처 세 개" → 은신처 → 터널 → 갈림길 → 터널 두 개 → 은신처 두 개 (해석기로 풀린다)."""
    from app.llm.mock import MockInterpreter
    from tests.test_mock_compose import _req

    spec = MockInterpreter().interpret(_req(rules, "갈림길로 은신처 세 개")).spec
    (it,) = spec.items
    assert [(p.id, p.template) for p in it.parts] == [
        ("hide", "hideout"), ("tube", "tunnel"), ("hub", JUNCTION), ("tube2", "tunnel"), ("tube3", "tunnel"),
        ("hide2", "hideout"), ("hide3", "hideout")]
    res, _, _ = resolve_ok([(p.id, p.template, p.params.model_dump(mode="json")) for p in it.parts],
                           [(c.part, c.to, c.at) for c in it.connections], rctx(rules, "dwarf"))
    assert sum(1 for j in res.joins if j.parent.startswith("hub.")) == 2


# ── deck_platform@v1 (설계 문서 §6.2) ─────────────────────────────


@pytest.mark.parametrize(("size", "height_min", "height_max", "width_min"), [("dwarf", 54, 120, 56),
                                                                            ("syrian", 74, 150, 76)])
def test_deck_defaults_per_size(rules, size, height_min, height_max, width_min) -> None:
    """기본값은 두 크기 모두 160 × 120 × 100 (발판 4, 옆벽 3). 높이 한도는 종별 통과 폭 + 발판 두께 ~ 최대 오르기 높이."""
    t = primitives()[DECK]
    ctx = rctx(rules, size)
    p = t.default_params(ctx)
    assert p.model_dump() == {"wall_thickness_mm": 3.0, "width_mm": 160.0, "depth_mm": 120.0, "height_mm": 100.0,
                              "deck_thickness_mm": 4.0}
    p2, issues = clamp_params(t, p, ctx)
    assert p2 == p and issues == []  # 기본값은 보정 없이 맞는다 (P1)
    assert t.rule_issues(p, ctx) == []
    bounds = {(c.field, "min" if c.min is not None else "max"): c.min if c.min is not None else c.max
              for c in t.constraints(p, ctx)}
    assert bounds[("height_mm", "min")] == height_min and bounds[("height_mm", "max")] == height_max
    assert bounds[("width_mm", "min")] == width_min and bounds[("depth_mm", "min")] == 50  # 넘어지지 않게 0.5·높이
    f = t.features(p)
    assert f.climb_height_mm == 100 and f.access_sides == ("front", "back") and f.entrance_count is None
    (under,) = f.openings
    assert (under.kind, under.size_mm, under.rule_key) == ("passage", 96.0, "entrance_min_diameter_mm")


def test_deck_too_high_is_lowered_to_the_climb_limit(rules) -> None:
    """드워프 최대 오르기 높이(120)보다 높은 발판은 120 으로 낮춘다."""
    t = primitives()[DECK]
    ctx = rctx(rules, "dwarf")
    p, issues = clamp_params(t, t.Params.model_validate({**dp(DECK, ctx), "height_mm": 160}), ctx)
    assert p.height_mm == 120 and [i.details["field"] for i in issues if i.code == "param_adjusted"] == ["height_mm"]


def test_deck_sides_are_mounts_and_never_doors(rules) -> None:
    """옆면 두 곳은 발판 높이까지의 받침면(벽 필드 없음, 출입구 없음), 앞뒤는 트여 있어 연결 지점이 없다."""
    t = primitives()[DECK]
    p = t.default_params(rctx(rules, "dwarf"))
    anchors = t.anchors(p)
    assert set(anchors) == {"left", "right", "top", "bottom"}
    for side, x, n in (("left", -80.0, (-1.0, 0.0, 0.0)), ("right", 80.0, (1.0, 0.0, 0.0))):
        a = anchors[side]
        assert (a.origin, a.normal, a.mount) == ((x, 0.0, 0.0), n, (-60.0, 60.0, 100.0))
        assert a.port is None and a.wall_mm is None and a.side is None and not compose.is_door(a)
        ff = t.face_fields(p, side)
        assert (ff.width, ff.height, ff.wall, ff.port) == ("depth_mm", "height_mm", None, None)
        assert t.open_port(p, side) is None


def test_ramp_on_the_deck_rises_to_the_deck_height(rules) -> None:
    """램프는 옆면에 끼우고, 꼭대기 높이가 발판 높이를 따른다 (발판을 80 으로 낮추면 램프도 80)."""
    ctx = rctx(rules, "dwarf")
    res, params, issues = resolve_ok([("deck", DECK, dp(DECK, ctx, height_mm=80)),
                                      ("ramp", "ramp", dp("ramp", ctx, height_mm=60))], [("ramp", "deck", "right")], ctx)
    assert joins(res) == [("deck.right", "ramp.landing", "slide")] and issues == []
    t = compose.template_for(res)
    p, adjusted = clamp_params(t, compose.assembly_params(t, params), ctx, max_passes=compose.ASSEMBLY_MAX_PASSES)
    assert p.ramp.height_mm == p.deck.height_mm == 80
    assert [i.details["field"] for i in adjusted if i.code == "param_adjusted"] == ["ramp.height_mm"]
    assert all(i.severity == Severity.info for i in adjusted)
    assert settle_passes(res, params, ctx) == []


def test_deck_takes_ramps_on_both_sides_and_relocates_a_front_request(rules) -> None:
    """양옆에 램프 둘. 앞(트인 면)에 달라고 한 그릇 받침은 붙일 수 있는 옆면으로 옮긴다."""
    ctx = rctx(rules, "syrian")
    res, params, issues = resolve_ok([("deck", DECK, dp(DECK, ctx)), ("ramp", "ramp", dp("ramp", ctx)),
                                      ("ramp2", "ramp", dp("ramp", ctx))],
                                     [("ramp", "deck", "left"), ("ramp2", "deck", "right")], ctx)
    assert joins(res) == [("deck.left", "ramp.landing", "slide"), ("deck.right", "ramp2.landing", "slide")]
    assert settle_passes(res, params, ctx) == []
    res, _, issues = resolve_ok([("deck", DECK, dp(DECK, ctx)), ("bowl", "bowl_holder", dp("bowl_holder", ctx))],
                                [("bowl", "deck", "front")], ctx)
    assert joins(res) == [("deck.right", "bowl.back", "slide")]
    assert [i.details["part"] for i in issues if i.code == "join_relocated"] == ["bowl"]


def test_deck_is_a_root_only_host_without_doors(rules) -> None:
    """host: 터널을 이을 출입구가 없고, 다른 부품에 붙는 자식이 될 수 없다 (설계 §3.3)."""
    ctx = rctx(rules, "dwarf")
    out = resolve([("deck", DECK, dp(DECK, ctx)), ("tube", "tunnel", dp("tunnel", ctx))],
                  [("tube", "deck", "left")], ctx)
    assert isinstance(out, Issue) and out.code == compose.JOIN_UNSUPPORTED
    out = resolve([("hide", "hideout", dp("hideout", ctx)), ("deck", DECK, dp(DECK, ctx))],
                  [("deck", "hide", "right")], ctx)
    assert isinstance(out, Issue) and out.code == compose.JOIN_UNSUPPORTED


def test_mock_reads_a_platform_with_a_ramp_and_a_bottle_stand(rules) -> None:
    """모의 해석기: "플랫폼 오른쪽에 램프, 왼쪽에 물병 거치대" → 발판 + 오른쪽 램프 + 왼쪽 물병 거치대."""
    from app.llm.mock import MockInterpreter
    from tests.test_mock_compose import _req

    spec = MockInterpreter().interpret(_req(rules, "플랫폼 오른쪽에 램프, 왼쪽에 물병 거치대")).spec
    (it,) = spec.items
    assert [(p.id, p.template) for p in it.parts] == [("deck", DECK), ("ramp", "ramp"), ("bottle", "bottle_stand")]
    assert [(c.part, c.to, c.at) for c in it.connections] == [("ramp", "deck", "right"), ("bottle", "deck", "left")]
    ctx = rctx(rules, "dwarf")
    res, params, _ = resolve_ok([(p.id, p.template, p.params.model_dump(mode="json")) for p in it.parts],
                                [(c.part, c.to, c.at) for c in it.connections], ctx)
    assert joins(res) == [("deck.right", "ramp.landing", "slide"), ("deck.left", "bottle.back", "slide")]
    assert settle_passes(res, params, ctx) == []


# ── litter_tray@v1 (설계 문서 §6.3; 게시만 하고 햄스터에는 아직 허용하지 않음) ─────────────


@pytest.mark.parametrize(("size", "side", "lip_max", "side_min"), [("dwarf", 130, 35, 106), ("syrian", 146, 45, 146)])
def test_tray_defaults_per_size(rules, size, side, lip_max, side_min) -> None:
    """기본값: 드워프 130 × 130 × 30, 골든 146 × 146 × 30 (2·통과 폭 + 2·벽). 턱은 종별 최대 턱 높이 이하."""
    t = primitives()[TRAY]
    ctx = rctx(rules, size)
    p = t.default_params(ctx)
    assert p.model_dump() == {"wall_thickness_mm": 3.0, "width_mm": side, "depth_mm": side, "lip_height_mm": 30.0}
    p2, issues = clamp_params(t, p, ctx)
    assert p2 == p and issues == []  # 기본값은 보정 없이 맞는다 (P1)
    assert t.rule_issues(p, ctx) == []
    bounds = {(c.field, "min" if c.min is not None else "max"): c.min if c.min is not None else c.max
              for c in t.constraints(p, ctx)}
    assert bounds[("lip_height_mm", "max")] == lip_max and bounds[("lip_height_mm", "min")] == 15  # 벽 + 12
    assert bounds[("width_mm", "min")] == bounds[("depth_mm", "min")] == side_min
    f = t.features(p)
    assert f.step_height_mm == 30 and f.climb_height_mm is None and f.access_sides == ("front",)
    assert f.openings == () and f.entrance_count is None and f.min_wall_thickness_mm == 3
    assert t.envelope(p) == (side, side, 30.0)


def test_tray_lip_and_size_are_clamped_to_the_species(rules) -> None:
    """드워프: 턱 60 → 최대 턱 높이 35, 가로 80 → 안에서 돌아설 수 있는 106 (2·50 + 2·3)."""
    t = primitives()[TRAY]
    ctx = rctx(rules, "dwarf")
    p, issues = clamp_params(t, t.Params.model_validate({**dp(TRAY, ctx), "lip_height_mm": 60, "width_mm": 80}), ctx)
    assert (p.lip_height_mm, p.width_mm, p.depth_mm) == (35, 106, 130)
    assert sorted(i.details["field"] for i in issues if i.code == "param_adjusted") == ["lip_height_mm", "width_mm"]


def test_tray_has_one_slide_anchor_at_the_back(rules) -> None:
    """뒷면 아래 가운데의 슬라이드 연결 지점 하나 (출입구·받침면·벽 필드 없음). 다른 부품을 받지 않는다."""
    t = primitives()[TRAY]
    p = t.default_params(rctx(rules, "dwarf"))
    anchors = t.anchors(p)
    assert set(anchors) == {"back", "bottom"} and t.attach_order == {"slide": ("back",)}
    a = anchors["back"]
    assert (a.origin, a.normal, a.up) == ((0.0, 65.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    assert a.port is None and a.wall_mm is None and a.mount is None and a.side is None
    assert t.open_port(p, "back") is None and not compose.is_door(a)


@pytest.mark.parametrize(("parent", "at", "mount"), [("hideout", "auto", "right"), ("hideout", "left", "left"),
                                                     ("house", "right", "right"), ("sand_bath", "back", "back"),
                                                     (DECK, "left", "left")])
def test_tray_slides_onto_hosts_and_rooms(rules, parent, at, mount) -> None:
    """은신처·집·모래목욕통·발판 플랫폼 옆면에 끼운다 (설명 그대로). 조립은 규칙·형상 검사를 통과한다."""
    ctx = rctx(rules, "dwarf")
    pid = "deck" if parent == DECK else parent
    res, params, issues = resolve_ok([(pid, parent, dp(parent, ctx)), ("toilet", TRAY, dp(TRAY, ctx))],
                                     [("toilet", pid, at)], ctx)
    assert joins(res) == [(f"{pid}.{mount}", "toilet.back", "slide")] and issues == []
    assert settle_passes(res, params, ctx) == []


def test_tray_with_a_bowl_holder_beside_a_hideout(rules) -> None:
    """은신처 오른쪽에 트레이, 왼쪽에 그릇 받침. 출입구 면(앞)에 달라고 하면 빈 옆면으로 옮긴다."""
    ctx = rctx(rules, "syrian")
    res, params, issues = resolve_ok([("hide", "hideout", dp("hideout", ctx)), ("toilet", TRAY, dp(TRAY, ctx)),
                                      ("bowl", "bowl_holder", dp("bowl_holder", ctx))],
                                     [("toilet", "hide", "front"), ("bowl", "hide", "left")], ctx)
    assert sorted(joins(res)) == [("hide.left", "bowl.back", "slide"), ("hide.right", "toilet.back", "slide")]
    assert [i.details["part"] for i in issues if i.code == "join_relocated"] == ["toilet"]
    assert settle_passes(res, params, ctx) == []


def test_tray_is_not_a_parent_or_a_tunnel_end(rules) -> None:
    """accessory: 다른 부품을 받지 않고, 터널 끝에 이을 수 없다 (설계 §3.3)."""
    ctx = rctx(rules, "dwarf")
    out = resolve([("toilet", TRAY, dp(TRAY, ctx)), ("bowl", "bowl_holder", dp("bowl_holder", ctx))],
                  [("bowl", "toilet", "auto")], ctx)
    assert isinstance(out, Issue) and out.code == compose.JOIN_UNSUPPORTED
    out = resolve([("hide", "hideout", dp("hideout", ctx)), ("tube", "tunnel", dp("tunnel", ctx)),
                   ("toilet", TRAY, dp(TRAY, ctx))],
                  [("tube", "hide", "front"), ("toilet", "tube", "free_end")], ctx)
    assert isinstance(out, Issue) and out.code == compose.JOIN_UNSUPPORTED


def test_tray_reasons_read_in_english(rules) -> None:
    """영어 사유는 크기 이름에 이미 "hamster" 가 있어 "{1} hamster" 로 겹쳐 쓰지 않는다."""
    from app.i18n import catalog

    t = primitives()[TRAY]
    ctx = rctx(rules, "syrian")
    en = [catalog().translate(c.reason_ko) for c in t.constraints(t.default_params(ctx), ctx)]
    assert "The lip must be at most 45 mm so a Golden (Syrian) hamster can step in" in en
    assert "The tray must be at least 146 mm wide so the animal can turn around inside" in en
    assert catalog().translate("화장실 트레이") == "Litter tray" and catalog().translate("턱 높이") == "lip height"


def test_mock_uses_the_tray_only_where_it_is_offered(rules) -> None:
    """모의 해석기: "은신처 옆에 화장실" → 트레이를 허용한 요청이면 은신처 + 트레이(auto). 햄스터에는 아직 내놓지
    않으므로 기본 요청에서는 은신처만 만든다."""
    from app.llm.mock import MockInterpreter
    from tests.test_mock_compose import _req

    spec = MockInterpreter().interpret(_req(rules, "은신처 옆에 화장실")).spec
    assert [it.template for it in spec.items] == ["hideout"]
    allowed = (*rules.allowed_templates("hamster"), TRAY)
    spec = MockInterpreter().interpret(_req(rules, "은신처 옆에 화장실", allowed=allowed)).spec
    (it,) = spec.items
    assert [(p.id, p.template) for p in it.parts] == [("hide", "hideout"), ("toilet", TRAY)]
    assert [(c.part, c.to, c.at) for c in it.connections] == [("toilet", "hide", "auto")]
    ctx = rctx(rules, "dwarf")
    res, params, _ = resolve_ok([(p.id, p.template, p.params.model_dump(mode="json")) for p in it.parts],
                                [(c.part, c.to, c.at) for c in it.connections], ctx)
    assert joins(res) == [("hide.right", "toilet.back", "slide")]
    assert settle_passes(res, params, ctx) == []


# ── 저장된 설계 다시 만들기 (설계 §14 "Stored rebuild e2e") ─────────────────


class FixtureInterpreter:
    """고정 데이터의 spec 을 그대로 돌려주는 해석기 (해석기 출력 계약은 그대로 통과시킨다)."""

    name = "fixture"

    def __init__(self, spec: dict):
        self.raw = json.dumps(spec, ensure_ascii=False)

    def interpret(self, req: InterpretRequest) -> InterpretResult:
        return InterpretResult(spec=parse_spec(self.raw, req.allowed_templates), provider=self.name, attempts=1)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cached(mesh_dir: Path, design_id: str) -> dict[str, bytes]:
    vd = mesh_dir / design_id / "v1"
    return {p.name: p.read_bytes() for p in sorted(vd.glob("*.stl"))} if vd.is_dir() else {}


def _exported(r) -> dict[str, bytes]:
    """STL 내보내기의 파트 파일들 (zip 은 시각을 담으므로 묶음이 아니라 파일끼리 비교한다)."""
    assert r.status_code == 200, r.text
    if r.content[:2] != b"PK":
        return {"part": r.content}
    with zipfile.ZipFile(BytesIO(r.content)) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def _check_stored_rebuild(tmp_path, monkeypatch, spec: dict, prompt: str, size: str, lib_parts: dict[str, str],
                          expected: dict | None = None, **settings) -> dict:
    """라이브러리 부품을 쓴 조립 설계를 저장하고, 메시 캐시·조립 템플릿 캐시·부품 형상 캐시를 비우고 조립 해석기를
    막아도 저장된 해시와 같은 바이트로 다시 만들고 같은 파일을 내보내는지 본다 (다시 검증 없이). 저장된 조립 구조."""
    from app.services import engine

    revalidations: list[int] = []
    real_revalidate = design_service.revalidate

    def spy(items, ctx):
        revalidations.append(len(items))
        return real_revalidate(items, ctx)

    monkeypatch.setattr(design_service, "revalidate", spy)
    mesh_dir = tmp_path / "meshes"
    app = create_app(make_settings(tmp_path, **settings), interpreter=FixtureInterpreter(spec))
    with TestClient(app) as c:
        hid = create_habitat(c, ROOMY, size=size)
        r = c.post("/designs", json={"habitat_id": hid, "prompt": prompt})
        assert r.status_code == 201, r.text
        d = r.json()
        cur = d["current"]
        assert cur["validation"]["passed"] and cur["export_allowed"], cur["validation"]
        (item,) = cur["items"]
        assert item["template"] == "assembly"
        templates = {p["id"]: p["template"] for p in item["assembly"]["parts"]}
        assert {pid: templates[pid] for pid in lib_parts} == lib_parts
        with c.app.state.session_factory() as db:
            row = db.query(DesignVersion).one()
        # 저장된 구조는 고정 데이터의 해석 결과와 같다
        for k, v in (expected or {}).items():
            assert row.items[0]["assembly"][k] == v, k
        files = _cached(mesh_dir, d["id"])
        assert files and {n: _sha(b) for n, b in files.items()} == row.geometry["files"]
        assert row.geometry["fingerprint"] == geometry_fingerprint(row.items, c.app.state.rules.printing)
        exported = _exported(c.get(f"/designs/{d['id']}/export?format=stl"))
        assert len(exported) == len(row.items[0]["parts"])

        # 새 인스턴스처럼: 캐시를 모두 비우고, 조립 해석기를 부르면 실패하게 한다
        def no_resolve(*a, **k):
            raise AssertionError("다시 만들 때 조립 해석기를 부르면 안 됩니다")

        monkeypatch.setattr(compose, "resolve", no_resolve)
        monkeypatch.setattr(engine, "resolve", no_resolve)
        compose.composed_template.cache_clear()
        for key in set(lib_parts.values()):
            primitives()[key]._cache.clear()  # DslTemplate 형상 캐시 (같은 파라미터의 build 결과)
        shutil.rmtree(mesh_dir)
        assert _exported(c.get(f"/designs/{d['id']}/export?format=stl")) == exported
        assert _cached(mesh_dir, d["id"]) == files
        assert revalidations == []  # 바이트가 같으면 다시 검증하지 않는다
        assert c.get(f"/designs/{d['id']}").json()["current"]["items"][0]["assembly"] == item["assembly"]
        return row.items[0]["assembly"]


@pytest.mark.parametrize("fixture", sorted(STORED_FIXTURES))
def test_stored_library_design_rebuilds_byte_identically(tmp_path, monkeypatch, fixture) -> None:
    """고정 데이터(갈림길 네트워크, 램프 달린 발판 플랫폼)를 저장하고 캐시를 비운 뒤 같은 바이트로 다시 만든다."""
    size, lib_parts = STORED_FIXTURES[fixture]
    fx = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    _check_stored_rebuild(tmp_path, monkeypatch, fx["spec"], fx["prompt_ko"], size, lib_parts, fx["expected"])


def _rules_gating(tmp_path: Path, key: str) -> Path:
    """저장소 규칙 사본에 라이브러리 부품 하나를 햄스터 허용 목록에 더한다 (아직 게이팅하지 않은 부품의 시험용)."""
    dst = tmp_path / "rules"
    shutil.copytree(BACKEND_DIR / "rules", dst)
    species = dst / "species.yaml"
    data = yaml.safe_load(species.read_text(encoding="utf-8"))
    data["species"]["hamster"]["templates"] = [*data["species"]["hamster"]["templates"], key]
    species.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dst


def test_stored_tray_design_rebuilds_byte_identically(tmp_path, monkeypatch, rules) -> None:
    """화장실 트레이를 은신처 오른쪽에 끼운 설계: 트레이를 허용한 규칙 사본으로 저장하고, 캐시를 비운 뒤 같은
    바이트로 다시 만든다 (저장소 규칙에서는 아직 허용하지 않으므로, 설계 §6.3)."""
    ctx = rctx(rules, "dwarf")
    spec = {"summary_ko": "은신처 오른쪽에 화장실 트레이를 끼웠습니다.",
            "items": [{"template": "assembly", "name_ko": "화장실 트레이를 단 은신처",
                       "parts": [{"id": "hide", "template": "hideout", "params": dp("hideout", ctx)},
                                 {"id": "toilet", "template": TRAY, "params": dp(TRAY, ctx)}],
                       "connections": [{"part": "toilet", "to": "hide", "at": "right"}],
                       "placement": {"zone": "auto", "group": None, "rotation": None, "attach_to": None},
                       "reason_ko": "트레이 뒷면을 은신처 오른쪽 벽에 끼웠습니다."}],
            "notes_ko": [], "missing_parts": []}
    expected = {"joins": [{"parent": "hide.right", "child": "toilet.back", "mount": "slide", "passage": False,
                           "shift": 0.0}],
                "faces": {"toilet": "right"}}
    _check_stored_rebuild(tmp_path, monkeypatch, spec, "은신처 오른쪽에 화장실", "dwarf", {"toilet": TRAY}, expected,
                          rules_dir=_rules_gating(tmp_path, TRAY))
