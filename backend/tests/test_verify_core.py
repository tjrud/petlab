"""검증기 핵심 (app/library/verify): 검사마다 일부러 만든 작은 템플릿(상자, 홈, 열린 연결판, 떠 있는 연결 지점,
넘어지는 벽 …)으로 통과·실패를 확인한다. 코드 부품 전체의 계약 검사는 tests/test_part_contract.py."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest
from build123d import Align, Box, Part, Pos
from pydantic import Field

from app.library.verify import anchors as A
from app.library.verify import geometry as G
from app.library.verify import honesty as H
from app.library.verify import report as Rep
from app.library.verify import run as R
from app.library.verify import trials as T
from app.library.verify import variants as V
from app.library.verify.engine_ctx import VerifyEngineContext
from app.templates.base import (
    Anchor,
    FaceFields,
    Features,
    ParamConstraint,
    RuleContext,
    Template,
    TemplateParams,
)

BOTTOM = (Align.CENTER, Align.CENTER, Align.MIN)
INVERTED = np.diag([1.0, -1.0, -1.0])
LIB_DATA = Path(__file__).parent / "data" / "library"


class BoxParams(TemplateParams):
    width_mm: float = Field(80.0, ge=40, le=150, description="가로 mm")
    depth_mm: float = Field(60.0, ge=40, le=150, description="세로 mm")
    height_mm: float = Field(40.0, ge=10, le=200, description="높이 mm")
    wall_thickness_mm: float = Field(3.0, ge=1.0, le=8, description="벽 두께 mm")


def _box(p: BoxParams) -> Part:
    return Box(p.width_mm, p.depth_mm, p.height_mm, align=BOTTOM)


def _side_anchors(p: BoxParams, *, out_mm: float = 0.0) -> dict[str, Anchor]:
    w, d, h = p.width_mm, p.depth_mm, p.height_mm
    return {
        "left": Anchor((-w / 2 - out_mm, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), mount=(-d / 2, d / 2, h)),
        "right": Anchor((w / 2, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), mount=(-d / 2, d / 2, h)),
        "top": Anchor((0.0, 0.0, h), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        "bottom": Anchor((0.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    }


def synthetic(build: Callable[[BoxParams], Part], *, role: str = "host", key: str = "synthetic",
              anchors: Callable[[BoxParams], dict[str, Anchor]] | None = None,
              envelope: Callable[[BoxParams], tuple[float, float, float]] | None = None,
              rotation: np.ndarray | None = None, features: Callable[[BoxParams], Features] | None = None,
              face_fields: Callable[[BoxParams, str], FaceFields] | None = None,
              attach_order: dict | None = None, params_cls: type[TemplateParams] = BoxParams,
              constraints: Callable[[Any, RuleContext], list[ParamConstraint]] | None = None,
              **members: Any) -> Template:
    """시험용 템플릿 (기본: 바닥에 놓인 속이 찬 상자, 옆면 연결판 자리 둘, 해석적 외형)."""
    ns: dict[str, Any] = {
        "key": key, "display_name_ko": "시험 상자", "description_ko": "검증기 시험용", "Params": params_cls,
        "role": role, "attach_order": attach_order or {}, "habitats": ("cage",),
        "constraints": lambda self, p, ctx: (constraints(p, ctx) if constraints else []),
        "build": lambda self, p: build(p),
        "features": lambda self, p: (features(p) if features else Features(min_wall_thickness_mm=p.wall_thickness_mm)),
        "anchors": lambda self, p: (anchors(p) if anchors else _side_anchors(p)),
        "face_fields": lambda self, p, a: (face_fields(p, a) if face_fields else
                                           FaceFields(width="depth_mm", height="height_mm")
                                           if a in ("left", "right") else FaceFields()),
        **members,
    }
    if envelope is not False:
        ns["envelope"] = (lambda self, p: envelope(p)) if envelope else \
            (lambda self, p: (p.width_mm, p.depth_mm, p.height_mm))
    if rotation is not None:
        ns["print_rotation"] = lambda self, p: rotation
    return type("Synthetic", (Template,), ns)()


GOOD = synthetic(_box)


@pytest.fixture(scope="module")
def ctx(rules) -> RuleContext:
    return V.rule_ctx(rules, "hamster", "dwarf")


def _built(t: Template, rules, p: TemplateParams | None = None) -> G.Built:
    b = G.build(t, p or t.Params(), rules.printing)
    assert b.item is not None, b.error
    return b


def _ok(results) -> bool:
    return all(r.ok for r in results)


# ── 보고서·면제 ──


def test_check_result_dict_and_waivers():
    r = Rep.failed("G05", "hamster/dwarf/c1/default", "overhang", value=120.0, limit=100.0)
    assert r.as_dict() == {"id": "G05", "ok": False, "variant": "hamster/dwarf/c1/default", "value": 120.0,
                           "limit": 100.0, "message": "overhang"}
    waived = Rep.apply_waivers([r, Rep.passed("G04")], {"G05": "printed with supports on purpose"})
    assert all(x.ok for x in waived) and waived[0].waived == "printed with supports on purpose"
    with pytest.raises(ValueError):
        Rep.apply_waivers([r], {"G05": "  "})


def test_report_shape_and_text():
    run = Rep.RunSummary(key="x@v1", profile="quick", results=[Rep.passed("G05", "a", value=10.0, limit=100.0),
                                                               Rep.failed("G11", "b", "tippy", value=3.0, limit=15.0)],
                         variants=2, started_at=Rep.now_iso())
    rep = Rep.build_report(run, file_sha256="abc", dsl=1)
    assert rep["result"] == "fail" and rep["counts"] == {"variants": 2, "unreachable": 0, "checks": 2, "failed": 1}
    assert rep["worst"]["G11"] == {"variant": "b", "value": 3.0, "limit": 15.0}
    assert set(rep["libraries"]) == {"build123d", "cadquery-ocp", "trimesh", "numpy"}
    assert set(rep["code"]) == set(Rep.DSL_CODE_MODULES)
    text = Rep.format_text(run)
    assert "result=FAIL" in text and "FAIL G11 b value=3 limit=15: tippy" in text


def test_rules_digest_ignores_unrelated_fields(rules):
    a = Rep.rules_digest(rules, "hamster", "dwarf", ["entrance_min_diameter_mm"])
    assert a == Rep.rules_digest(rules, "hamster", "dwarf", ["entrance_min_diameter_mm"])
    assert a != Rep.rules_digest(rules, "hamster", "syrian", ["entrance_min_diameter_mm"])
    assert a != Rep.rules_digest(rules, "hamster", "dwarf", ["entrance_min_diameter_mm", "max_climb_height_mm"])


# ── 변형·P 검사 ──


def test_variants_cover_defaults_bounds_choices_and_seeds(rules):
    from app.templates.registry import get_template

    t = get_template("tunnel")
    full = V.generate(t, rules, "full")
    ids = {v.id for v in full} | {a for v in full for a in v.aliases}
    for size in ("dwarf", "syrian"):
        base = f"hamster/{size}"
        assert {f"{base}/c1/default", f"{base}/c2/default", f"{base}/c1/min:length_mm", f"{base}/c1/max:length_mm",
                f"{base}/c1/choice:shape=tube", f"{base}/c1/seed0", f"{base}/c1/seed3"} <= ids
    # 터널은 어항에도 쓰인다 (코드 부품: 그 부품을 허용하는 종)
    assert any(v.species == "aquarium" for v in full)
    quick = V.generate(t, rules, "quick")
    assert {v.kind for v in quick} == {"default", "choice"}
    # 같은 씨앗은 같은 값 (결정적)
    again = V.generate(t, rules, "full")
    assert [v.dump() for v in full] == [v.dump() for v in again]


def test_nested_leaves_use_dotted_paths():
    from app.templates.house import HouseParams

    paths = {leaf.path: leaf for leaf in V.leaves(HouseParams)}
    assert paths["roof.kind"].kind == "choice" and "pitched" in paths["roof.kind"].choices
    assert paths["walls.thickness_mm"].kind == "number" and paths["walls.thickness_mm"].lo is not None
    assert "doors.sides" not in paths  # 목록 필드는 변형하지 않는다


def test_param_checks_catch_infeasible_defaults_and_rule_issues(rules):
    def need_wide(p, c):
        return [ParamConstraint("width_mm", min=100.0, reason_ko="넓어야 합니다")]

    t = synthetic(_box, constraints=need_wide, rule_issues=lambda self, p, c: ["고칠 수 없는 문제"])
    vs = V.generate(t, rules, "quick", species="hamster")
    res = V.param_checks(t, rules, vs)
    p1 = [r for r in res if r.id == "P1"]
    assert p1 and not any(r.ok for r in p1)
    assert "width_mm" in p1[0].message and p1[0].path == "/params/width_mm"
    assert not any(r.ok for r in res if r.id == "P3")
    good = V.param_checks(GOOD, rules, V.generate(GOOD, rules, "quick", species="hamster"))
    assert _ok(good)


def test_unreachable_variants_skip_geometry(rules):
    def impossible(p, c):
        return [ParamConstraint("width_mm", min=200.0, reason_ko="불가능")]

    t = synthetic(_box, constraints=impossible)
    vs = V.generate(t, rules, "quick", species="hamster")
    assert vs and all(v.unreachable and v.unreachable.startswith("param_conflict") for v in vs)
    assert V.reachable(vs) == []


def test_evaluation_errors_fail_p4(rules):
    def broken(p):
        raise ZeroDivisionError("width - 80")

    t = synthetic(_box, features=broken)
    v = V.reachable(V.generate(t, rules, "quick", species="hamster"))[0]
    r = V._evaluation(t, v, V.fit_ctx(rules, v.species, v.size))
    assert not r.ok and r.id == "P4" and "ZeroDivisionError" in r.message


# ── 형상 G ──


def test_good_box_passes_geometry(rules, ctx):
    b = _built(GOOD, rules)
    p = GOOD.Params()
    assert G.check_build(b).ok
    assert _ok(G.check_meshes(b.item)) and G.check_volume(b.item).ok and _ok(G.check_bed(b.item, rules.printing))
    assert _ok(G.check_overhang(b.item, rules.printing)) and _ok(G.check_walls(b.item, ctx))
    assert G.check_envelope(GOOD, p, b).ok
    assert H.check_gap_trap(b.item.mesh, ctx.size).ok
    assert H.check_stability(b.item.mesh).ok


def test_build_failure_is_g01(rules):
    def boom(p):
        raise RuntimeError("kernel")

    b = G.build(synthetic(boom), BoxParams(), rules.printing)
    r = G.check_build(b)
    assert not r.ok and "RuntimeError" in r.message


def test_two_bodies_fail_g02(rules):
    t = synthetic(lambda p: Pos(-30, 0, 0) * Box(20, 20, 20, align=BOTTOM) + Pos(30, 0, 0) * Box(20, 20, 20, align=BOTTOM))
    res = G.check_meshes(_built(t, rules).item)
    assert not res[0].ok and "2 separate bodies" in res[0].message


def test_bed_overflow_fails_g04(rules):
    t = synthetic(lambda p: Box(240, 40, 20, align=BOTTOM), envelope=lambda p: (240, 40, 20))
    res = G.check_bed(_built(t, rules).item, rules.printing)
    assert not res[0].ok and res[0].value == pytest.approx(20.0, abs=0.01)


def _hollow(p: BoxParams) -> Part:
    t = p.wall_thickness_mm
    return _box(p) - Pos(0, 0, -1) * Box(p.width_mm - 2 * t, p.depth_mm - 2 * t, p.height_mm - t + 1, align=BOTTOM)


def test_upright_roof_overhang_fails_g05_and_inverted_passes(rules):
    upright = G.check_overhang(_built(synthetic(_hollow), rules).item, rules.printing)
    assert not upright[0].ok and upright[0].value > 1000
    inverted = G.check_overhang(_built(synthetic(_hollow, rotation=INVERTED), rules).item, rules.printing)
    assert inverted[0].ok and inverted[0].value == pytest.approx(0.0)


def test_thin_and_lying_walls_fail_g06(rules, ctx):
    thin = synthetic(_hollow, rotation=INVERTED)
    res = G.check_walls(_built(thin, rules, BoxParams(wall_thickness_mm=1.0)).item, ctx)
    assert any(not r.ok and r.path == "/features/min_wall" for r in res)  # 설계 벽이 최소보다 얇다
    # 선언은 3mm 인데 실제 벽은 1.5mm (정직성)
    lying = synthetic(lambda p: _hollow(BoxParams(**{**p.model_dump(), "wall_thickness_mm": 1.5})), rotation=INVERTED,
                      features=lambda p: Features(min_wall_thickness_mm=3.0))
    res = G.check_walls(_built(lying, rules).item, V.rule_ctx(rules, "hamster", "dwarf"))
    assert any(not r.ok for r in res)


def test_envelope_and_centring_fail_g07(rules):
    off = synthetic(_box, envelope=lambda p: (p.width_mm - 10, p.depth_mm, p.height_mm))
    r = G.check_envelope(off, BoxParams(), _built(off, rules))
    assert not r.ok and r.value == pytest.approx(10.0, abs=0.01)
    shifted = synthetic(lambda p: Pos(5, 0, 0) * _box(p))
    r = G.check_envelope(shifted, BoxParams(), _built(shifted, rules))
    assert not r.ok and "off the XY centre" in r.message
    # 액세서리는 가운데가 아니어도 된다
    acc = synthetic(lambda p: Pos(5, 0, 0) * _box(p), role="accessory")
    assert G.check_envelope(acc, BoxParams(), _built(acc, rules)).ok


def test_engine_run_g10_on_code_part(rules):
    from app.templates.registry import get_template

    t = get_template("hideout")
    p = t.default_params(V.fit_ctx(rules, "hamster", "dwarf"))
    assert G.check_engine(t, p, rules, "hamster", "dwarf", 1).ok


def test_determinism_g12_in_process_and_detects_noise(rules):
    b = _built(GOOD, rules)
    r, files = G.check_determinism(GOOD, BoxParams(), rules.printing, b.item, subprocess=False)
    assert r.ok and set(files) == {"print_0.stl", "world_0.stl"}
    counter = iter(range(1000))
    noisy = synthetic(lambda p: Box(p.width_mm + next(counter) * 0.01, p.depth_mm, p.height_mm, align=BOTTOM))
    b = _built(noisy, rules)
    r, _ = G.check_determinism(noisy, BoxParams(), rules.printing, b.item, subprocess=False)
    assert not r.ok and "second in-process build" in r.message


def test_fresh_process_rebuild_matches(rules):
    """새 프로세스(python -I)에서 같은 코드 부품을 만들면 같은 바이트."""
    from app.library.verify.rebuild import fresh_process_digests
    from app.templates.registry import get_template

    t = get_template("ramp")
    p = t.default_params(V.fit_ctx(rules, "hamster", "dwarf"))
    b = _built(t, rules, p)
    assert fresh_process_digests("ramp", p.model_dump(mode="json")) == G.file_digests(b.item)


# ── 정직성 G08 G09 G11 ──


def _slot(p: BoxParams) -> Part:
    """바닥판 위에 20mm 떨어진 두 벽 (끼임 홈)."""
    base = Box(80, 60, 5, align=BOTTOM)
    wall = Box(10, 60, 60, align=BOTTOM)
    return base + Pos(-15, 0, 0) * wall + Pos(15, 0, 0) * wall


def test_slot_and_low_deck_fail_g08(rules, ctx):
    r = H.check_gap_trap(_built(synthetic(_slot, envelope=lambda p: (40, 60, 60)), rules).item.mesh, ctx.size)
    assert not r.ok and "20.0 mm" in r.message
    # 바닥에서 15mm 떠 있는 발판: 케이지 바닥 평면과의 틈
    deck = synthetic(lambda p: Pos(0, 0, 15) * Box(120, 80, 4, align=BOTTOM)
                     + Pos(-55, 0, 0) * Box(10, 80, 19, align=BOTTOM) + Pos(55, 0, 0) * Box(10, 80, 19, align=BOTTOM))
    r = H.check_gap_trap(_built(deck, rules).item.mesh, ctx.size)
    assert not r.ok and "15.0 mm" in r.message


def test_vents_below_safe_size_and_wide_doors_are_not_traps(rules, ctx):
    from app.templates.registry import get_template

    t = get_template("hideout")
    p = t.default_params(ctx)
    hits = H.gap_hits(_built(t, rules, p).item.mesh, ctx.size.gap_trap.safe_max_mm, ctx.size.gap_trap.passable_min_mm)
    assert hits == []


def test_climb_and_slope_honesty_g09(rules, ctx):
    deck = synthetic(lambda p: Box(120, 80, 100, align=BOTTOM), envelope=lambda p: (120, 80, 100))
    p = BoxParams()
    res = H.feature_honesty(deck, p, _built(deck, rules).item.mesh, ctx.size)
    assert not _ok(res) and res[0].path == "/features/climb_height"
    honest = synthetic(lambda p: Box(120, 80, 100, align=BOTTOM), envelope=lambda p: (120, 80, 100),
                       features=lambda p: Features(min_wall_thickness_mm=3.0, climb_height_mm=100.0))
    assert _ok(H.feature_honesty(honest, p, _built(honest, rules).item.mesh, ctx.size))
    # 방(room_host)은 지붕 높이를 오르기로 보지 않는다 (관례)
    room = synthetic(lambda p: Box(120, 80, 100, align=BOTTOM), role="room_host")
    assert _ok(H.feature_honesty(room, p, _built(room, rules).item.mesh, ctx.size))
    # 좁은 띠는 설 수 없다 (최대 내접원 < 20mm)
    rail = synthetic(lambda p: Box(120, 8, 100, align=BOTTOM))
    assert H.standable_height(_built(rail, rules).item.mesh) is None


def test_ramp_slope_must_be_declared(rules, ctx):
    from build123d import Plane, Polyline, extrude, make_face

    def wedge(p):
        face = make_face(Polyline((-100, 0), (100, 0), (100, 80), (-100, 0)))
        return extrude(Plane.XZ * face, amount=30, both=True)

    t = synthetic(wedge, role="accessory", envelope=lambda p: (200, 60, 80),
                  features=lambda p: Features(min_wall_thickness_mm=3.0, climb_height_mm=80.0))
    res = H.feature_honesty(t, BoxParams(), _built(t, rules).item.mesh, ctx.size)
    slope = [r for r in res if r.path == "/features/slope_deg"]
    assert slope and not slope[0].ok and slope[0].limit == pytest.approx(21.8, abs=0.5)


def test_tipping_angle_g11(rules):
    assert H.tipping_angle(_built(GOOD, rules).item.mesh) == pytest.approx(np.degrees(np.arctan(30 / 20)), abs=0.5)
    tippy = synthetic(lambda p: Box(100, 10, 200, align=BOTTOM))
    r = H.check_stability(_built(tippy, rules).item.mesh)
    assert not r.ok and r.value == pytest.approx(np.degrees(np.arctan(5 / 100)), abs=0.5)


# ── 연결 지점 C ──


def test_good_box_passes_connection_checks(rules):
    assert _ok(A.connection_checks(GOOD, BoxParams()))


def test_off_surface_and_inward_anchors_fail_c02():
    off = synthetic(_box, anchors=lambda p: _side_anchors(p, out_mm=5.0))
    res = A.check_anchors(off, BoxParams())
    assert any(not r.ok and r.id == "C02" and r.path == "/anchors/left" for r in res)

    def inward(p):
        a = _side_anchors(p)
        a["right"] = Anchor((p.width_mm / 2, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        return a

    res = A.check_anchors(synthetic(_box, anchors=inward), BoxParams())
    assert any(not r.ok and "points into the part" in r.message for r in res)


def test_bad_frames_fail_c01():
    def skew(p):
        a = _side_anchors(p)
        a["left"] = Anchor((-p.width_mm / 2, 0, 0), (-1.0, 0, 0), (0.6, 0, 0.8))
        a["bottom"] = Anchor((0, 0, 5.0), (0, 0, -1.0), (0, 1.0, 0))
        return a

    res = A.check_frames(synthetic(_box, anchors=skew), BoxParams(), A.build_mesh(GOOD, BoxParams()))
    bad = {r.path for r in res if not r.ok}
    assert bad == {"/anchors/left", "/anchors/bottom"}


def test_mount_over_air_fails_c03():
    def open_side(p):
        return _box(p) - Pos(p.width_mm / 2, 0, p.height_mm / 2) * Box(10, 30, 20)

    res = A.check_mounts(synthetic(open_side), BoxParams(), A.build_mesh(synthetic(open_side), BoxParams()))
    right = next(r for r in res if r.path == "/anchors/right/mount")
    left = next(r for r in res if r.path == "/anchors/left/mount")
    assert left.ok and not right.ok


class DoorParams(BoxParams):
    # 둥근 아치 50mm 출입구(높이 50mm)가 지붕을 뚫지 않도록 방은 더 높다
    height_mm: float = Field(70.0, ge=10, le=200, description="높이 mm")
    door_width_mm: float = Field(50.0, ge=30, le=60, description="출입구 폭 mm")
    door_count: int = Field(1, ge=1, le=2, description="출입구 개수")


def _room(block: bool = False, profile_shape: str = "round_arch"):
    from app.templates.base import cutter_at
    from app.templates.tunnel import TunnelParams, inner_profile

    def door(p, name="front"):
        y = -p.depth_mm / 2 if name == "front" else p.depth_mm / 2
        n = -1.0 if name == "front" else 1.0
        return Anchor((0.0, y, 0.0), (0.0, n, 0.0), (0.0, 0.0, 1.0), side=name, port=p.door_width_mm,
                      wall_mm=p.wall_thickness_mm, profile="round_arch")

    def prof(p):
        return inner_profile(TunnelParams.model_construct(inner_diameter_mm=p.door_width_mm, shape=profile_shape,
                                                          wall_thickness_mm=p.wall_thickness_mm))

    def anchors(p):
        out = {"front": door(p)}
        if p.door_count == 2:
            out["back"] = door(p, "back")
        else:
            out["back"] = Anchor((0.0, p.depth_mm / 2, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
                                 wall_mm=p.wall_thickness_mm, mount=(-p.width_mm / 2, p.width_mm / 2, p.height_mm))
        return out

    def build(p):
        t = p.wall_thickness_mm
        part = _hollow(p)
        for a in anchors(p).values():
            if a.port is not None:
                o = np.asarray(a.origin) - np.asarray(a.normal) * (t + 1)
                part = part - cutter_at(Anchor(tuple(o), a.normal, a.up), prof(p), t + 2)
        if block:
            part = part + Pos(0, -p.depth_mm / 2 + t + 5 + 5, 0) * Box(30, 10, p.height_mm - t + 0.5, align=BOTTOM)
        return part

    def face_fields(p, name):
        if name == "front" or (name == "back" and p.door_count == 2):
            return FaceFields("width_mm", None, "wall_thickness_mm", port="door_width_mm")
        if name == "back":
            return FaceFields("width_mm", "height_mm", "wall_thickness_mm")
        return FaceFields()

    def open_port(self, p, name):
        if name == "back":
            return p.model_copy(update={"door_count": 2})
        return p if name == "front" else None

    return synthetic(build, role="room_host", params_cls=DoorParams, anchors=anchors, rotation=INVERTED,
                     attach_order={"passage": ("front", "back")}, face_fields=face_fields,
                     features=lambda p: Features(min_wall_thickness_mm=p.wall_thickness_mm,
                                                 access_sides=("front", "back")[:p.door_count]),
                     port_profile=lambda self, p, name: prof(p) if name == "front" or p.door_count == 2 else None,
                     open_port=open_port)


def test_room_with_door_passes_connection_checks():
    room = _room()
    for p in (DoorParams(), DoorParams(door_count=2)):
        res = A.connection_checks(room, p)
        assert _ok(res), [(r.id, r.path, r.message) for r in res if not r.ok]


def test_block_behind_door_fails_c04():
    res = A.check_doors_open(_room(block=True), DoorParams(), A.build_mesh(_room(block=True), DoorParams()))
    # C04 는 바깥 면에서 잰다: 벽 3mm + 안쪽 5mm
    assert not res[0].ok and res[0].value == pytest.approx(8.0, abs=0.2)


def test_wrong_profile_family_fails_c05():
    res = A.check_profiles(_room(profile_shape="box"), DoorParams())
    assert not res[0].ok and "best 'box'" in res[0].message


def test_face_fields_must_move_the_anchor_c06():
    assert _ok(A.check_face_fields(_room(), DoorParams()))
    assert _ok(A.check_face_fields(_room(), DoorParams(door_count=2)))
    # 가로 파라미터가 연결판 자리를 키우지 않는 템플릿
    stuck = synthetic(_box, face_fields=lambda p, a: FaceFields(width="width_mm") if a in ("left", "right")
                      else FaceFields())
    res = A.check_face_fields(stuck, BoxParams())
    assert any(not r.ok and "width width_mm" in r.message for r in res)


def test_open_port_must_open_a_door_c07():
    room = _room()
    assert _ok(A.check_open_port(room, DoorParams()))

    class Liar(type(room)):
        def open_port(self, p, name):
            return p if name == "front" else (p.model_copy(update={"height_mm": 50.0}) if name == "back" else None)

    res = A.check_open_port(Liar(), DoorParams())
    assert any(not r.ok and r.path == "/opens/back" for r in res)


def test_attach_order_and_envelope_c08(rules):
    acc = synthetic(_box, role="accessory", attach_order={"slide": ("top",)})
    res = A.check_attach(acc, BoxParams())
    assert any(not r.ok and "slide anchor top" in r.message for r in res)
    bbox = synthetic(_box, envelope=False)
    res = A.check_attach(bbox, BoxParams())
    assert any(not r.ok and "not analytic" in r.message for r in res)
    # 모든 변형에서 닫힌 통로 자리
    room = _room()
    vs = V.reachable(V.generate(room, rules, "quick", species="hamster"))
    assert _ok(R._passage_coverage(room, vs))

    class Closed(type(room)):
        attach_order: ClassVar[dict] = {"passage": ("front", "left")}

    res = R._passage_coverage(Closed(), vs)
    assert [r.path for r in res if not r.ok] == ["/attach_order/passage/left"]


# ── 시험 조립 ──


def test_trials_respect_profiles_and_ids(rules):
    from app.templates.registry import primitives

    prim = primitives()
    ctx = V.fit_ctx(rules, "hamster", "dwarf")
    hide = T.generate("hideout", prim["hideout"], prim, ctx)
    names = [t.name for t in hide]
    # 은신처(둥근 아치)와 집(뾰족 아치)은 터널 하나로 잇지 않는다
    assert not any("house" in n for n in names)
    for tr in hide:
        ids = [pid for pid, _ in tr.parts]
        assert len(ids) == len(set(ids)), tr
    house = T.generate("house", prim["house"], prim, ctx)
    assert all(k in ("house", "tunnel", "bowl_holder") for tr in house for _, k in tr.parts)
    assert T._compatible(prim["hideout"], prim["hideout"].default_params(ctx), prim["hideout"], ctx)
    assert not T._compatible(prim["hideout"], prim["hideout"].default_params(ctx), prim["house"], ctx)


def test_accessory_trials_pass_for_bowl_holder(rules):
    from app.templates.registry import primitives

    prim = primitives()
    ctx = V.fit_ctx(rules, "hamster", "dwarf")
    trials = T.generate("bowl_holder", prim["bowl_holder"], prim, ctx)
    assert [t.name for t in trials][:4] == ["bowl@hideout.right", "bowl@hideout.left", "bowl@hideout.back",
                                            "bowl@hideout.auto"]
    res = [T.run_trial(t, prim, rules, "hamster", "dwarf") for t in trials[:2]]
    assert all(r.ok for r in res), [r.message for r in res]
    assert res[0].joins == ["hide.right>bowl.back slide"]
    assert _ok(T.trial_checks(res)) and _ok(T.engine_check(res, "bowl_holder", rules))


# ── 엔진 문맥·규칙 필드·스키마 ──


def test_verify_engine_context_allows_the_draft(rules):
    from app.domain import Cage

    ctx = VerifyEngineContext(Cage(1000, 600, 400), "hamster", "dwarf", 1, rules, extra_templates=("draft@v1",))
    assert ctx.allowed_templates == rules.allowed_templates("hamster") + ("draft@v1",)
    assert ctx.rule_ctx == V.rule_ctx(rules, "hamster", "dwarf")


def test_rule_fields_used_for_code_parts(rules):
    from app.templates.registry import get_template

    cases = V.size_cases(get_template("ramp"), rules)
    used = R.rule_fields_used(get_template("ramp"), rules, cases)
    assert {"max_ramp_angle_deg", "max_climb_height_mm"} <= used
    assert "display_name" not in used and "aquatic" not in used


def test_schema_contract_r01_for_a_code_part(rules):
    from app.templates.registry import get_template

    t = get_template("bowl_holder")
    res, schema = R.schema_contract(t, rules, V.size_cases(t, rules))
    assert _ok(res)
    assert 0 < schema["chars_added"] <= R.SCHEMA_PART_MAX
    assert schema["gate_ok"] == {"hamster": True} and schema["totals"]["hamster"] < 30_000


# ── 전체 실행 ──


def test_verify_runs_every_check_on_a_registered_code_part(rules):
    from app.templates.registry import get_template

    run = R.verify(get_template("bowl_holder"), rules=rules, profile="quick", jobs=1, subprocess=False,
                   trial_mode="quick")
    ids = {r.id for r in run.results}
    assert ids >= {"P1", "P2", "P3", "P4", "G01", "G02", "G05", "G07", "G08", "G10", "G11", "G12", "C01", "C08",
                   "T01", "T02", "R01", "R03", "R04"}
    assert run.ok, Rep.format_text(run)
    assert run.verified_for == {"hamster": ["dwarf", "syrian"]}
    assert set(run.golden) == {"hamster/dwarf/default", "hamster/syrian/default"}
    assert set(run.rules_digest) == {"hamster/dwarf", "hamster/syrian"}
    rep = Rep.build_report(run)
    assert rep["result"] == "pass" and rep["trials"] and json.dumps(rep)


def test_verify_a_draft_under_overlay_with_worker_processes(rules):
    """초안(등록되지 않은 key)은 overlay 로 잠시 등록되고, 작업 프로세스도 부품 파일로 같은 템플릿을 만든다."""
    from app.library.template import make_template
    from app.templates.registry import primitives

    draft = json.loads((LIB_DATA / "deck_platform.json").read_text(encoding="utf-8"))
    draft["family"] = "verify_core_deck"  # make_template: key 의 family 가 부품 family 와 같아야 한다
    t = make_template(draft, key="verify_core_deck@v1")
    run = R.verify(t, rules=rules, profile="quick", jobs=2, draft=draft, species="hamster",
                   checks=("G01", "G02", "G05", "G07", "G08", "G11", "G12", "C03"), trials=False)
    assert run.ok, Rep.format_text(run)
    assert {r.id for r in run.results} == {"G01", "G02", "G05", "G07", "G08", "G11", "G12", "C03"}
    assert t.key not in primitives()  # overlay 는 끝나면 풀린다
