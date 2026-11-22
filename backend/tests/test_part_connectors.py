"""부품 연결 표준 (자유 조립): 템플릿마다의 역할·연결 지점 순서, 면 치수 파라미터(face_fields), 통로 열기(open_port),
해석적 외형(envelope), 붙는 면 높이 조건(face_needs), 조립 때만 더하는 제약.

face_fields 가 가리키는 파라미터가 실제로 그 연결 지점의 치수(연결판 자리·통로 크기·벽 두께)를 움직이는지,
Anchor.profile 이 port_profile 이 만드는 단면과 같은 종류인지, envelope 가 build() 경계 상자와 맞는지를 확인한다."""

from __future__ import annotations

import pytest
from build123d import Align, Rectangle

from app.templates.base import FaceFields, Template
from app.templates.bottle_stand import (
    BottleStandParams,
    BottleStandTemplate,
    total_height,
)
from app.templates.bowl_holder import (
    COLLAR_BELOW_RIM_MM,
    BowlHolderParams,
    BowlHolderTemplate,
)
from app.templates.cave import CaveTemplate
from app.templates.hideout import HideoutParams, HideoutTemplate
from app.templates.house import HouseParams, HouseTemplate
from app.templates.ramp import (
    BED_SLOPE_BASE_DEG,
    BED_SLOPE_PER_MM,
    RampParams,
    RampTemplate,
)
from app.templates.sand_bath import SandBathParams, SandBathTemplate
from app.templates.tunnel import TunnelParams, TunnelTemplate, inner_profile
from app.validation.autofix import get_path, set_path

HIDEOUT, HOUSE, SAND, TUNNEL = HideoutTemplate(), HouseTemplate(), SandBathTemplate(), TunnelTemplate()
BOWL, BOTTLE, RAMP = BowlHolderTemplate(), BottleStandTemplate(), RampTemplate()
SHAPES = ("pointed_arch", "round_arch", "tube", "box", "house")

HOUSE_VARIANTS = {
    "flat_1f": {},
    "ports_right": {"ports": {"sides": ["right"]}, "windows": {"count": 4}},
    "pitched_port_front": {"roof": {"kind": "pitched"}, "doors": {"sides": ["left"]}, "ports": {"sides": ["front"]}},
    "rounded_two_doors": {"roof": {"kind": "rounded"}, "doors": {"sides": ["front", "back"]}},
    "two_internal": {"floors": {"count": 2, "climb": "internal_ramp"}},
    "two_external": {"floors": {"count": 2, "climb": "external_ramp", "exit_side": "back"}},
}


def _house(name: str) -> HouseParams:
    d = HouseParams().model_dump()
    for k, v in HOUSE_VARIANTS[name].items():
        d[k].update(v)
    return HouseParams.model_validate(d)


# (이름, 템플릿, 파라미터): 연결 지점 일관성 검사 대상
CASES: list[tuple[str, Template, object]] = [
    ("hideout_1", HIDEOUT, HideoutParams()),
    ("hideout_2", HIDEOUT, HideoutParams(entrance_count=2)),
    *[(f"house_{n}", HOUSE, _house(n)) for n in HOUSE_VARIANTS],
    ("sand_bath", SAND, SandBathParams()),
    *[(f"tunnel_{s}", TUNNEL, TunnelParams(shape=s)) for s in SHAPES],
    ("tunnel_bent", TUNNEL, TunnelParams(bend_angle_deg=90, shape="round_arch")),
    ("tunnel_s", TUNNEL, TunnelParams(bend_angle_deg=60, path="s_curve", shape="house")),
    ("bowl_holder", BOWL, BowlHolderParams()),
    ("bottle_stand", BOTTLE, BottleStandParams()),
    ("ramp", RAMP, RampParams()),
    ("stairs", RAMP, RampParams(height_mm=90, steps=3, slope_deg=35)),
]
CASE_IDS = [c[0] for c in CASES]


def _bumped(t: Template, p, path: str, delta: float):
    d = p.model_dump()
    set_path(d, path, get_path(d, path) + delta)
    return t.Params.model_validate(d)


# ── 역할·연결 지점 순서 ─────────────────────────────────────


def test_roles_and_attach_orders():
    assert (HIDEOUT.role, HOUSE.role, SAND.role, TUNNEL.role) == ("room_host", "room_host", "host", "connector")
    assert BOWL.role == BOTTLE.role == RAMP.role == "accessory"
    assert CaveTemplate().role == "none" and not CaveTemplate().composable
    assert HIDEOUT.attach_order == {"passage": ("front", "back")}
    assert TUNNEL.attach_order == {"passage": ("end_b", "end_a")}
    assert BOWL.attach_order == BOTTLE.attach_order == {"slide": ("back",)}
    assert RAMP.attach_order == {"slide": ("landing",)}
    assert RAMP.passes_access and RAMP.level_field == "height_mm"
    assert not any(t.passes_access for t in (HIDEOUT, HOUSE, SAND, TUNNEL, BOWL, BOTTLE))
    assert all(t.level_field is None for t in (HIDEOUT, HOUSE, SAND, TUNNEL, BOWL, BOTTLE))


@pytest.mark.parametrize(("name", "t", "p"), CASES, ids=CASE_IDS)
def test_attach_order_names_existing_anchors(name, t, p):
    anchors = t.anchors(p)
    for kind, names in t.attach_order.items():
        for a in names:
            assert a in anchors, (name, kind, a)
            if kind == "slide":
                # 자식 쪽 슬라이드 면: 통로가 아닌 바닥 높이의 세로 면
                assert anchors[a].port is None and anchors[a].normal[2] == 0
    # 드나드는 방은 통로 순서 안에 지금 열린 출입구가 적어도 하나 있다 (해석기가 port 가 있는 것만 고른다)
    if t.role == "room_host":
        assert any(anchors[a].port is not None for a in t.attach_order["passage"]), name


# ── face_fields: 통로·단면·벽 ────────────────────────────────


@pytest.mark.parametrize(("name", "t", "p"), CASES, ids=CASE_IDS)
def test_port_and_profile_fields_match_anchor(name, t, p):
    d = p.model_dump()
    for aname, a in t.anchors(p).items():
        ff = t.face_fields(p, aname)
        assert (ff.port is None) == (a.port is None), (name, aname)
        assert (a.profile is None) == (a.port is None), (name, aname)
        if ff.port is not None:
            assert get_path(d, ff.port) == pytest.approx(a.port), (name, aname)
            # 통로 크기 파라미터를 바꾸면 그 연결 지점의 통로 크기가 같이 바뀐다
            q = _bumped(t, p, ff.port, 4.0)
            assert t.anchors(q)[aname].port == pytest.approx(a.port + 4.0), (name, aname)
        if ff.profile is not None:
            assert get_path(d, ff.profile) == a.profile, (name, aname)


@pytest.mark.parametrize(("name", "t", "p"), CASES, ids=CASE_IDS)
def test_wall_field_matches_anchor(name, t, p):
    d = p.model_dump()
    for aname, a in t.anchors(p).items():
        ff = t.face_fields(p, aname)
        assert (ff.wall is None) == (a.wall_mm is None), (name, aname)
        if ff.wall is None:
            continue
        # 벽 파라미터 ≤ 뚫는 깊이 (집 연결부 면은 플랜지가 더해진다), 벽을 두껍게 하면 그만큼 깊어진다
        assert get_path(d, ff.wall) <= a.wall_mm + 1e-9
        q = _bumped(t, p, ff.wall, 0.5)
        assert t.anchors(q)[aname].wall_mm == pytest.approx(a.wall_mm + 0.5), (name, aname)


@pytest.mark.parametrize(("name", "t", "p"), CASES, ids=CASE_IDS)
def test_face_fields_grow_the_mount_rectangle(name, t, p):
    """width 를 늘리면 연결판 자리(mount)의 가로가 같은 만큼, height 를 올리면 높이가 같은 만큼 커진다 (가운데 정렬 유지).
    (집의 경사 지붕은 세로가 늘면 지붕이 높아져 처마가 내려가므로 width 를 늘릴 때의 높이는 보지 않는다)"""
    checked = 0
    for aname, a in t.anchors(p).items():
        ff = t.face_fields(p, aname)
        if a.mount is None:
            continue
        left, right, h = a.mount
        if ff.width is not None:
            m = t.anchors(_bumped(t, p, ff.width, 10.0))[aname].mount
            assert m is not None
            assert m[1] - m[0] == pytest.approx(right - left + 10.0), (name, aname)
            assert m[0] + m[1] == pytest.approx(left + right), (name, aname)
            checked += 1
        if ff.height is not None:
            m = t.anchors(_bumped(t, p, ff.height, 10.0))[aname].mount
            assert m is not None
            assert m[2] == pytest.approx(h + 10.0), (name, aname)
            assert (m[0], m[1]) == pytest.approx((left, right)), (name, aname)
            checked += 1
    if t.role in ("room_host", "host"):
        assert checked, name


def test_face_fields_per_side():
    assert HIDEOUT.face_fields(HideoutParams(), "left") == FaceFields("depth_mm", "height_mm", "wall_thickness_mm")
    assert HIDEOUT.face_fields(HideoutParams(), "back") == FaceFields("width_mm", "height_mm", "wall_thickness_mm")
    assert HIDEOUT.face_fields(HideoutParams(entrance_count=2), "back").port == "entrance_diameter_mm"
    assert HIDEOUT.face_fields(HideoutParams(), "top") == FaceFields()
    hp = HouseParams()
    assert HOUSE.face_fields(hp, "right") == FaceFields(width="depth_mm", wall="walls.thickness_mm")
    assert HOUSE.face_fields(hp, "front") == FaceFields(width="width_mm", wall="walls.thickness_mm", port="doors.width_mm")
    assert HOUSE.face_fields(_house("ports_right"), "right").port == "ports.diameter_mm"
    sp = SandBathParams()
    assert SAND.face_fields(sp, "front") == FaceFields(width="width_mm", height="lip_height_mm")
    assert SAND.face_fields(sp, "left") == FaceFields(width="depth_mm")
    assert SAND.face_fields(sp, "back") == FaceFields(width="width_mm")
    assert TUNNEL.face_fields(TunnelParams(), "end_a") == FaceFields(port="inner_diameter_mm", profile="shape")
    for t, p in ((BOWL, BowlHolderParams()), (BOTTLE, BottleStandParams()), (RAMP, RampParams())):
        assert all(t.face_fields(p, a) == FaceFields() for a in t.anchors(p))


# ── Anchor.profile = port_profile 단면의 종류 ─────────────────


def _above_floor_iou(a, b) -> float:
    floor = Rectangle(1000, 1000, align=(Align.CENTER, Align.MIN))
    a, b = a & floor, b & floor
    inter = (a & b).area
    return inter / (a.area + b.area - inter)


DOOR_CASES = [
    ("hideout_front", HIDEOUT, HideoutParams(entrance_diameter_mm=60), "front"),
    ("hideout_back", HIDEOUT, HideoutParams(entrance_count=2, entrance_diameter_mm=45), "back"),
    ("house_door", HOUSE, HouseParams(), "front"),
    ("house_narrow_door", HOUSE, HouseParams(doors={"width_mm": 40}), "front"),
    ("house_port", HOUSE, _house("ports_right"), "right"),
    *[(f"tunnel_{s}", TUNNEL, TunnelParams(shape=s, inner_diameter_mm=55), "end_a") for s in SHAPES],
]


@pytest.mark.parametrize(("name", "t", "p", "aname"), DOOR_CASES, ids=[c[0] for c in DOOR_CASES])
def test_anchor_profile_is_the_port_profile_family(name, t, p, aname):
    """출입구 단면(바닥 위 부분)이 같은 폭의 터널 안쪽 단면 다섯 종류 중 anchor.profile 과 가장 닮았다."""
    a = t.anchors(p)[aname]
    prof = t.port_profile(p, aname)
    scores = {
        s: _above_floor_iou(prof, inner_profile(TunnelParams(inner_diameter_mm=a.port, shape=s, wall_thickness_mm=3)))
        for s in SHAPES
    }
    assert max(scores, key=scores.get) == a.profile, scores
    assert scores[a.profile] > 0.97, scores


# ── open_port ───────────────────────────────────────────────


def test_hideout_open_port():
    p = HideoutParams()
    q = HIDEOUT.open_port(p, "back")
    assert q is not None and q.entrance_count == 2
    a = HIDEOUT.anchors(q)["back"]
    assert a.port == q.entrance_diameter_mm and a.profile == "round_arch" and a.mount is None
    assert HIDEOUT.open_port(q, "back") == q          # 이미 열린 면은 그대로
    assert HIDEOUT.open_port(p, "front") == p
    for side in ("left", "right", "top", "bottom", "nowhere"):
        assert HIDEOUT.open_port(p, side) is None


def test_house_open_port_adds_a_tunnel_port():
    p = HouseParams()
    q = HOUSE.open_port(p, "left")
    assert q is not None and q.ports.sides == ["left"]
    a = HOUSE.anchors(q)["left"]
    assert a.port == q.ports.diameter_mm and a.profile == "pointed_arch"
    assert a.wall_mm == pytest.approx(q.walls.thickness_mm + q.ports.flange_mm)
    assert HOUSE.face_fields(q, "left").port == "ports.diameter_mm"
    assert HOUSE.open_port(p, "front") == p           # 출입구 면은 이미 열려 있다
    assert HOUSE.open_port(q, "left") == q
    assert HOUSE.open_port(p, "top") is None and HOUSE.open_port(p, "bottom") is None
    # 연결부는 2개까지
    two = HOUSE.open_port(q, "right")
    assert two is not None and two.ports.sides == ["left", "right"]
    assert HOUSE.open_port(two, "back") is None


def test_house_open_port_refuses_porch_and_unpierceable_sides():
    ext = _house("two_external")       # 바깥 램프 착지판 면 = back
    assert HOUSE.open_port(ext, "back") is None
    assert HOUSE.open_port(ext, "left") is not None
    internal = _house("two_internal")  # 안쪽 경사로가 뒷벽에 붙어 뚫을 수 없다
    assert HOUSE.open_port(internal, "back") is None
    assert HOUSE.open_port(internal, "right") is not None


@pytest.mark.parametrize(("t", "p"), [(SAND, SandBathParams()), (TUNNEL, TunnelParams()), (BOWL, BowlHolderParams()),
                                      (BOTTLE, BottleStandParams()), (RAMP, RampParams())])
def test_parts_without_doors_cannot_open_ports(t, p):
    assert all(t.open_port(p, a) is None for a in t.anchors(p))


# ── envelope ────────────────────────────────────────────────

ENVELOPE_CASES: list[tuple[Template, object]] = [
    *[(TUNNEL, TunnelParams(length_mm=200 if bend <= 90 else 300, inner_diameter_mm=d, wall_thickness_mm=t,
                            bend_angle_deg=bend, path=path, shape=shape))
      for shape in SHAPES
      for bend, path, d, t in ((0, "arc", 50, 3), (60, "arc", 40, 2), (135, "arc", 60, 4), (180, "arc", 50, 3),
                               (45, "s_curve", 50, 3), (90, "s_curve", 30, 6))],
    *[(BOWL, BowlHolderParams(bowl_diameter_mm=d, bowl_height_mm=h, collar_height_mm=c, wall_thickness_mm=t))
      for d, h, c, t in ((60, 35, 25, 2), (90, 45, 27, 3), (160, 80, 75, 8))],
    (BOTTLE, BottleStandParams()),
    (BOTTLE, BottleStandParams(base_width_mm=60, base_depth_mm=60)),
    (BOTTLE, BottleStandParams(bottle_diameter_mm=90, cap_diameter_mm=60, wall_thickness_mm=6, holder_height_mm=150)),
    *[(RAMP, RampParams(height_mm=h, width_mm=w, slope_deg=s, steps=n))
      for h, w, s, n in ((20, 40, 10, 0), (60, 80, 25, 0), (200, 250, 45, 0), (60, 80, 25, 3), (120, 60, 30, 8))],
    (HIDEOUT, HideoutParams()),
    (HIDEOUT, HideoutParams(entrance_count=2, width_mm=60, depth_mm=60, entrance_diameter_mm=50)),
    (SAND, SandBathParams()),
    (SAND, SandBathParams(lip_height_mm=100, basin_depth_mm=20, wall_thickness_mm=8)),
]


@pytest.mark.parametrize(("t", "p"), ENVELOPE_CASES)
def test_analytic_envelope_matches_build_bbox(t, p):
    size = t.build(p).bounding_box().size
    assert t.envelope(p) == pytest.approx((size.X, size.Y, size.Z), abs=0.5)


def test_envelope_is_analytic_for_parts():
    """조립 해석기가 형상 없이 면 크기를 정하도록 부품·은신처·모래목욕통의 envelope 는 build() 를 부르지 않는다."""
    for t in (TUNNEL, BOWL, BOTTLE, RAMP, HIDEOUT, SAND):
        assert type(t).envelope is not Template.envelope, type(t).__name__


# ── face_needs·조립 제약 ─────────────────────────────────────


def test_face_needs():
    b = BowlHolderParams(bowl_height_mm=40)
    assert BOWL.face_needs(b) == (55.0, None)
    s = BottleStandParams()
    assert BOTTLE.face_needs(s) == (None, pytest.approx(total_height(s)))
    assert BOTTLE.face_needs(s)[1] == pytest.approx(BOTTLE.envelope(s)[2])
    for t, p in ((HIDEOUT, HideoutParams()), (SAND, SandBathParams()), (TUNNEL, TunnelParams()), (RAMP, RampParams())):
        assert t.face_needs(p) == (None, None)


def test_bowl_joined_collar_meets_the_rim_band(rules):
    from app.templates.base import RuleContext

    c = RuleContext(rules.size_rules("hamster", "dwarf"), rules.min_wall_for("hamster", "dwarf"))
    p = BowlHolderParams(bowl_height_mm=50, collar_height_mm=20)
    joined = BOWL.joined_constraints(p, c, "back")
    assert [(x.field, x.min) for x in joined] == [("collar_height_mm", 50 - COLLAR_BELOW_RIM_MM)]
    own_max = next(x.max for x in BOWL.constraints(p, c) if x.field == "collar_height_mm")
    assert own_max == joined[0].min  # 혼자 쓸 때의 상한과 함께 턱 = 테두리 − 5mm
    assert joined[0].violates(p.collar_height_mm)
    assert BOWL.joined_constraints(p, c, "bottom") == []
    assert BOWL.assembly_constraints(p, c) == []


def test_ramp_assembly_slope_fits_the_bed(rules):
    from app.templates.base import RuleContext

    c = RuleContext(rules.size_rules("hamster", "syrian"), rules.min_wall_for("hamster", "syrian"))
    p = RampParams(height_mm=85, slope_deg=20)
    out = RAMP.assembly_constraints(p, c)
    assert [(x.field, x.source) for x in out] == [("slope_deg", "printing")]
    assert out[0].min == pytest.approx(BED_SLOPE_PER_MM * 85 + BED_SLOPE_BASE_DEG)
    # 혼자 쓰는 램프는 이 제약이 없다
    assert all(x.field != "slope_deg" or x.min is None for x in RAMP.constraints(p, c))
    assert RAMP.joined_constraints(p, c, "landing") == []
    # 그 경사에서 따로 출력하는 램프 길이가 출력 공간(220mm) 안에 든다
    q = p.model_copy(update={"slope_deg": out[0].min})
    assert RAMP.envelope(q)[1] <= 220.0
