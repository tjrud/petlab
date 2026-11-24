"""은신처 옆면 출입구 (side_doors, 설계 문서 §3.1): 검증, 형상(옆면 출입구를 지나는 광선), 연결 지점·면 필드·open_port,
제약(무리 출입구 수·세로), 특징(출입구 라벨·출입 면·출입구 수), 옛 파라미터가 그대로인지, 새 형상 골든.

옛 은신처(옆면 출입구 없음)의 형상 바이트·연결 지점·제약 메시지는 tests/test_stage2_baseline.py 가 2단계 전 값으로 고정한다.
여기서는 none 이 옛 경로와 같은 dict·씨앗을 내는지와, 옆면 출입구가 있는 은신처의 새 값을 본다.

골든을 다시 뽑을 때 (형상을 일부러 바꿀 때만): uv run python -m tests.test_hideout_side_doors
"""

from __future__ import annotations

import hashlib
import json
import sys

import numpy as np
import pytest
from pydantic import ValidationError

from app.domain import Cage, PlacementHint
from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.templates.base import FaceFields, RuleContext
from app.templates.decor import decor_seed, parse_decor
from app.templates.hideout import HideoutParams, HideoutTemplate, side_door_sides
from app.validation.autofix import clamp_params
from app.validation.checks import overhang_area

HIDEOUT = HideoutTemplate()
SIDES = ("none", "left", "right", "both")
# 옆 출입구 양옆에 벽이 남도록 세로를 d + 4t 이상으로 (기본 출입구 60, 벽 3 → 72)
DEEP = 136.0


def rctx(rules, size: str = "dwarf", count: int = 1) -> RuleContext:
    return RuleContext(rules.size_rules("hamster", size), rules.min_wall_for("hamster", size), count,
                       printing_max_overhang_deg=rules.printing.max_overhang_deg,
                       min_feature_mm=rules.printing.min_feature_mm)


def _p(side_doors: str = "none", **kw) -> HideoutParams:
    return HideoutParams(side_doors=side_doors, **{"depth_mm": DEEP, **kw})


# ── 검증·저장 형태 ─────────────────────────────────────────────


def test_field_values_and_default():
    assert HideoutParams().side_doors == "none"
    for v in SIDES:
        assert HideoutParams(side_doors=v).side_doors == v
    for bad in ("top", "front", "LEFT", 1, None):
        with pytest.raises(ValidationError):
            HideoutParams(side_doors=bad)
    assert [side_door_sides(HideoutParams(side_doors=v)) for v in SIDES] == [(), ("left",), ("right",), ("left", "right")]
    assert HIDEOUT.legacy_defaults == {"entrance_count": 1, "side_doors": "none"}


def test_stored_form_omits_none_and_keeps_other_values():
    """none 은 저장 dict 에서 빠진다: 옆면 출입구가 생기기 전과 같은 dict (장식 씨앗·형상 캐시 키가 그대로)."""
    legacy = HideoutParams()
    assert "side_doors" not in legacy.model_dump()
    assert "side_doors" not in legacy.model_dump(mode="json")
    assert "side_doors" not in json.loads(legacy.model_dump_json())
    assert list(legacy.model_dump()) == ["width_mm", "depth_mm", "height_mm", "entrance_diameter_mm", "entrance_count",
                                         "vent_count", "vent_diameter_mm", "wall_thickness_mm"]
    for v in ("left", "right", "both"):
        d = HideoutParams(side_doors=v).model_dump(mode="json")
        assert d["side_doors"] == v
        assert list(d).index("side_doors") == list(d).index("entrance_count") + 1
        assert HideoutParams.model_validate(d) == HideoutParams(side_doors=v)
    # 옛 저장 파라미터 (필드 없음) → none, 다시 저장해도 같은 dict
    stored = legacy.model_dump(mode="json")
    loaded = HIDEOUT.load_stored_params(dict(stored))
    assert loaded.side_doors == "none" and loaded.model_dump(mode="json") == stored
    # 스키마에는 늘 있다 (해석기가 고를 수 있게)
    assert HideoutParams.model_json_schema()["properties"]["side_doors"]["enum"] == list(SIDES)


def test_decor_seed_of_legacy_params_is_unchanged():
    """장식 무늬 씨앗은 파라미터 dict 해시다: none 은 옆면 출입구가 생기기 전 dict 와 같은 씨앗을 낸다."""
    decor = parse_decor({"kind": "pattern", "pattern": "dots", "density": 2, "direction": 0, "depth_mm": 0.6,
                         "face": "walls", "mode": "relief"})
    p = HideoutParams(width_mm=150, entrance_count=2)
    # 2단계 전 HideoutParams.model_dump(mode="json") 그대로 (실수 필드는 실수로)
    pre_field = {"width_mm": 150.0, "depth_mm": 110.0, "height_mm": 90.0, "entrance_diameter_mm": 60.0,
                 "entrance_count": 2, "vent_count": 6, "vent_diameter_mm": 4.0, "wall_thickness_mm": 3.0}
    payload = json.dumps(["hideout", pre_field, decor.model_dump(mode="json")], sort_keys=True, ensure_ascii=False)
    assert decor_seed("hideout", p, decor) == int(hashlib.sha256(payload.encode()).hexdigest()[:8], 16)
    assert decor_seed("hideout", p.model_copy(update={"side_doors": "left"}), decor) != decor_seed("hideout", p, decor)


# ── 형상 ───────────────────────────────────────────────────


def _mesh(p: HideoutParams):
    return part_to_mesh(HIDEOUT.build(p))


def _through_x(m, p: HideoutParams, y: float = 0.0) -> bool:
    """출입구 높이 가운데에서 X 방향으로 은신처를 가로지르는 광선이 벽에 막히지 않는지."""
    z = p.entrance_diameter_mm / 2
    origin = np.array([[-p.width_mm, y, z]])
    return not m.ray.intersects_any(origin, np.array([[1.0, 0.0, 0.0]]))[0]


def _wall_open(m, p: HideoutParams, side: str) -> bool:
    """옆벽 두께 가운데, 출입구 높이 가운데 점이 비어 있는지."""
    x = (-1 if side == "left" else 1) * (p.width_mm / 2 - p.wall_thickness_mm / 2)
    return not m.contains([[x, 0.0, p.entrance_diameter_mm / 2]])[0]


@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("side_doors", SIDES)
def test_geometry_has_a_door_through_each_side_wall(side_doors, count):
    p = _p(side_doors, entrance_count=count)
    m = _mesh(p)
    assert mesh_health(m).ok and m.body_count == 1
    for side in ("left", "right"):
        assert _wall_open(m, p, side) == (side in side_door_sides(p)), side
    # 양쪽에 출입구가 있으면 X 방향 광선이 은신처를 그대로 지나간다
    assert _through_x(m, p) == (side_doors == "both")
    # 아치 꼭대기(출입구 폭 = 높이) 위로는 벽이 남는다
    d = p.entrance_diameter_mm
    for side in side_door_sides(p):
        x = (-1 if side == "left" else 1) * (p.width_mm / 2 - p.wall_thickness_mm / 2)
        assert m.contains([[x, 0.0, d + 2.0]])[0]
        assert m.contains([[x, d / 2 + p.wall_thickness_mm, d / 2]])[0]  # 출입구 옆도 벽
    # 바깥 상자는 그대로 (해석적 외형과 같다)
    W, D, H = p.width_mm, p.depth_mm, p.height_mm
    assert m.bounds.ravel().tolist() == pytest.approx([-W / 2, -D / 2, 0, W / 2, D / 2, H], abs=1e-6)


@pytest.mark.parametrize("side_doors", ["left", "both"])
def test_side_doors_print_inverted_without_overhang(rules, side_doors):
    """지붕을 베드에 대고 뒤집어 출력하면 옆면 아치도 위로 열린 홈이 되어 서포트가 필요 없다."""
    p = _p(side_doors, entrance_count=2)
    printed = to_print_orientation(_mesh(p), HIDEOUT.print_rotation(p))
    assert overhang_area(printed, rules.printing.max_overhang_deg) < 1.0


def test_none_builds_the_same_solid_as_legacy_params():
    a, b = _mesh(HideoutParams()), _mesh(HideoutParams(side_doors="none"))
    assert a.export(file_type="stl") == b.export(file_type="stl")


# ── 연결 지점·면 필드·open_port ────────────────────────────────


@pytest.mark.parametrize("side_doors", SIDES)
def test_anchors_and_face_fields(side_doors):
    p = _p(side_doors)
    a = HIDEOUT.anchors(p)
    W, D, H, t, d = p.width_mm, p.depth_mm, p.height_mm, p.wall_thickness_mm, p.entrance_diameter_mm
    for side, x, nx in (("left", -W / 2, -1), ("right", W / 2, 1)):
        s = a[side]
        assert s.origin == pytest.approx((x, 0, 0)) and s.normal == (nx, 0, 0) and s.up == (0.0, 0.0, 1.0)
        assert s.wall_mm == t
        ff = HIDEOUT.face_fields(p, side)
        if side in side_door_sides(p):
            assert (s.side, s.port, s.profile, s.mount) == (side, d, "round_arch", None)
            assert ff == FaceFields("depth_mm", "height_mm", "wall_thickness_mm", port="entrance_diameter_mm")
            assert HIDEOUT.port_profile(p, side) is not None
            assert HIDEOUT.port_cutter(p, side, 10.0) is not None
        else:
            assert (s.side, s.port, s.profile, s.mount) == (None, None, None, (-D / 2, D / 2, H))
            assert ff == FaceFields("depth_mm", "height_mm", "wall_thickness_mm")
            assert HIDEOUT.port_profile(p, side) is None
    # 앞·뒤·위·아래는 옆면 출입구와 상관없다 (뒷면은 출입구가 아니어도 side="back")
    legacy = HIDEOUT.anchors(HideoutParams(depth_mm=DEEP))
    for name in ("front", "back", "top", "bottom"):
        assert a[name] == legacy[name], name
    assert HIDEOUT.attach_order == {"passage": ("front", "back", "left", "right")}


def test_side_door_port_cutter_opens_the_side_wall():
    """옆면 출입구의 통로 자르개(터널을 끼울 때 벽을 뚫는 모양)는 옆벽의 출입구 자리를 지난다."""
    p = _p("left")
    cutter = part_to_mesh(HIDEOUT.port_cutter(p, "left", 20.0))
    lo, hi = cutter.bounds
    assert hi[1] == pytest.approx(p.entrance_diameter_mm / 2, abs=0.05)
    assert lo[1] == pytest.approx(-p.entrance_diameter_mm / 2, abs=0.05)
    assert hi[2] == pytest.approx(p.entrance_diameter_mm, abs=0.05)
    assert lo[0] < -p.width_mm / 2 < hi[0]


@pytest.mark.parametrize(("start", "anchor", "expected"), [
    ("none", "left", "left"), ("none", "right", "right"),
    ("left", "right", "both"), ("right", "left", "both"),
    ("left", "left", "left"), ("right", "right", "right"), ("both", "left", "both"), ("both", "right", "both"),
])
def test_open_port_adds_side_doors(start, anchor, expected):
    p = _p(start)
    q = HIDEOUT.open_port(p, anchor)
    assert q is not None and q.side_doors == expected
    assert q.entrance_count == p.entrance_count
    if start == expected:
        assert q == p
    a = HIDEOUT.anchors(q)[anchor]
    assert a.port is not None and a.wall_mm is not None and a.side == anchor


def test_open_port_on_other_faces_is_unchanged():
    p = _p("left")
    assert HIDEOUT.open_port(p, "front") == p
    back = HIDEOUT.open_port(p, "back")
    assert back is not None and back.entrance_count == 2 and back.side_doors == "left"
    assert HIDEOUT.open_port(p, "top") is None and HIDEOUT.open_port(p, "bottom") is None


# ── 제약 ───────────────────────────────────────────────────


def _cons(p, ctx) -> dict[str, list]:
    out: dict[str, list] = {}
    for c in HIDEOUT.constraints(p, ctx):
        out.setdefault(c.field, []).append(c)
    return out


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_group_rule_counts_side_doors(rules, size):
    """여러 마리면 출입구가 2개 이상: 옆면 출입구도 센다 (앞 하나 + 옆 하나면 앞·뒤 출입구 수 규칙이 없다)."""
    group = rctx(rules, size, count=2)
    assert group.hideout_min_entrances == 2
    legacy = _cons(_p("none"), group)["entrance_count"]
    assert [c.min for c in legacy] == [2]
    assert "출입구는 2개 이상이어야 합니다" in legacy[0].reason_ko
    for v in ("left", "right", "both"):
        assert "entrance_count" not in _cons(_p(v), group)
    # 보정: 옆면 출입구가 있으면 출입구를 2개로 늘리지 않는다
    q, issues = clamp_params(HIDEOUT, _p("left"), group)
    assert q.entrance_count == 1 and not [i for i in issues if i.code == "param_conflict"]
    q, _ = clamp_params(HIDEOUT, _p("none"), group)
    assert q.entrance_count == 2


def test_depth_rule_with_side_doors(rules):
    ctx = rctx(rules, "syrian")
    for v in SIDES:
        p = HideoutParams(side_doors=v)
        (depth,) = _cons(p, ctx)["depth_mm"]
        t = max(p.wall_thickness_mm, ctx.min_wall_mm)
        d = max(p.entrance_diameter_mm, ctx.size.entrance_min_diameter_mm)
        if v == "none":
            assert depth.min == pytest.approx(d + 2 * t)
            assert depth.reason_ko == "내부 공간 확보를 위해 세로가 출입구 폭보다 커야 합니다"
        else:
            assert depth.min == pytest.approx(d + 4 * t)
            assert depth.reason_ko == "옆 출입구 양옆에 벽이 남도록 세로가 출입구 폭보다 충분히 커야 합니다"
    # 좁은 은신처에 옆면 출입구를 내면 세로를 늘린다
    q, issues = clamp_params(HIDEOUT, HideoutParams(side_doors="both", depth_mm=60, entrance_diameter_mm=75), ctx)
    assert q.depth_mm >= q.entrance_diameter_mm + 4 * q.wall_thickness_mm - 1e-6
    assert any(i.code == "param_adjusted" and i.details["field"] == "depth_mm" for i in issues)


# ── 특징 ───────────────────────────────────────────────────


@pytest.mark.parametrize(("side_doors", "count", "labels", "access"), [
    ("none", 1, ["출입구"], ("front",)),
    ("none", 2, ["앞 출입구", "뒤 출입구"], ("front", "back")),
    ("left", 1, ["앞 출입구", "왼쪽 출입구"], ("front", "left")),
    ("right", 2, ["앞 출입구", "뒤 출입구", "오른쪽 출입구"], ("front", "back", "right")),
    ("both", 1, ["앞 출입구", "왼쪽 출입구", "오른쪽 출입구"], ("front", "left", "right")),
    ("both", 2, ["앞 출입구", "뒤 출입구", "왼쪽 출입구", "오른쪽 출입구"], ("front", "back", "left", "right")),
])
def test_features(side_doors, count, labels, access):
    p = _p(side_doors, entrance_count=count)
    f = HIDEOUT.features(p)
    doors = [o for o in f.openings if o.kind == "passage"]
    assert [o.label_ko for o in doors] == labels
    assert all(o.size_mm == p.entrance_diameter_mm and o.rule_key == "entrance_min_diameter_mm" for o in doors)
    assert [o.label_ko for o in f.openings if o.kind == "vent"] == ["환기구"]
    assert f.access_sides == access
    assert f.entrance_count == len(labels)
    # 출입구 면 = 통로 자리 (연결 지점의 port 와 같은 면)
    anchors = HIDEOUT.anchors(p)
    assert {n for n, a in anchors.items() if a.port is not None} == set(access)


def test_decor_zones_keep_out_of_side_doors():
    p = _p("left")
    zones = {z.face: z for z in HIDEOUT.decor_zones(p)}
    r = p.entrance_diameter_mm / 2
    assert zones["left"].obstacles == ((-r, 0.0, r, 2 * r),)
    assert zones["right"].obstacles == ()
    legacy = {z.face: z for z in HIDEOUT.decor_zones(HideoutParams(depth_mm=DEEP))}
    for face in ("front", "back", "right"):
        assert zones[face] == legacy[face], face


def test_legacy_params_give_identical_contract(rules):
    """side_doors 를 적지 않은 파라미터와 none 을 적은 파라미터는 연결 지점·면 필드·특징·제약·장식 자리가 모두 같다
    (2단계 전 값과 같은지는 tests/test_stage2_baseline.py 가 본다)."""
    for kw in ({}, {"entrance_count": 2}, {"width_mm": 60, "depth_mm": 60, "entrance_diameter_mm": 50}):
        a, b = HideoutParams(**kw), HideoutParams(side_doors="none", **kw)
        assert a.model_dump() == b.model_dump()
        assert HIDEOUT.anchors(a) == HIDEOUT.anchors(b)
        assert HIDEOUT.features(a) == HIDEOUT.features(b)
        assert HIDEOUT.decor_zones(a) == HIDEOUT.decor_zones(b)
        names = ("front", "back", "left", "right", "top", "bottom")
        assert [HIDEOUT.face_fields(a, n) for n in names] == [HIDEOUT.face_fields(b, n) for n in names]
        for size in ("dwarf", "syrian"):
            for count in (1, 2):
                ctx = rctx(rules, size, count)
                assert HIDEOUT.constraints(a, ctx) == HIDEOUT.constraints(b, ctx)


# ── 엔진: 무리용 네 갈래 은신처 ────────────────────────────────


@pytest.mark.parametrize("size", ["dwarf", "syrian"])
def test_engine_passes_a_four_door_hideout(rules, size):
    from app.services.engine import EngineContext, ItemSpec, run_engine

    ctx = EngineContext(cage=Cage(800, 500, 400), species="hamster", size=size, count=2, rules=rules)
    p = HIDEOUT.default_params(ctx.rule_ctx).model_copy(update={"side_doors": "both"}).model_dump(mode="json")
    res = run_engine([ItemSpec("hideout", p)], ctx)
    assert res.report.passed, [i.message_ko for i in res.report.errors]
    (item,) = res.items
    assert item.params.side_doors == "both" and item.features.entrance_count == 4
    assert item.params.depth_mm >= item.params.entrance_diameter_mm + 4 * item.params.wall_thickness_mm - 1e-6


# ── 골든 (옆면 출입구가 있는 새 형상) ─────────────────────────────

GOLDEN_CASES = {
    f"{side}/c{count}": {"side_doors": side, "entrance_count": count}
    for side in ("left", "both") for count in (1, 2)
}
# build_item 으로 만든 메시 해시 (드워프 기본값 + 옆면 출입구, 보정 뒤 파라미터). 형상을 일부러 바꿀 때만 다시 뽑는다
GOLDEN: dict[str, dict[str, str]] = {
    "both/c1": {"mesh": "ce87c0ee0a916b5cba1ee2283d60528d4a62f1386b972e6eabe5bc198158fa99",
                "print": "f001eb38d6a97e395391622d54662e7c20d9524fb2d01c3d54946a744f66365b"},
    "both/c2": {"mesh": "cc2a82e06ec104065c7fa7210892f5a8944ba3e99b0b20aff67d9c4e67df5e61",
                "print": "59f6418005754e1fecdf80265358690a46438bc3c928d51cc90cf4bb339962ef"},
    "left/c1": {"mesh": "ba7a25d3fe011646139f56d6f9e6d23279b1642feef815254b73c5e98f5ed57c",
                "print": "e9f4eb788d7793994690b9bff1f2839a14c5bb06ae1aa606d1777959cfccbdd6"},
    "left/c2": {"mesh": "748845a482af8d3c0cb2fa1d8e9db30a4930fa3c212146c8ccfaf16038133ad6",
                "print": "e12af439aba038f2877b6269da9c43c7ee2c217408bc6ad336786a51e31ac3e6"},
}


def golden_params(rules, case: str) -> HideoutParams:
    ctx = rctx(rules, "dwarf")
    p = HIDEOUT.default_params(ctx).model_copy(update=GOLDEN_CASES[case])
    q, issues = clamp_params(HIDEOUT, p, ctx)
    assert not [i for i in issues if i.code == "param_conflict"], issues
    return q


def golden_digests(rules, case: str) -> dict[str, str]:
    from app.services.engine import build_item

    p = HIDEOUT.load_stored_params(golden_params(rules, case).model_dump(mode="json"))
    it = build_item(0, HIDEOUT, p, PlacementHint(), rules.printing, None, rctx(rules, "dwarf"))
    sha = lambda m: hashlib.sha256(m.export(file_type="stl")).hexdigest()
    return {"mesh": sha(it.mesh), "print": sha(it.print_mesh)}


@pytest.mark.parametrize("case", sorted(GOLDEN_CASES))
def test_side_door_goldens(rules, case):
    assert set(GOLDEN) == set(GOLDEN_CASES)
    assert golden_digests(rules, case) == GOLDEN[case], case


def main() -> int:
    from app.config import BACKEND_DIR
    from app.rules.loader import load_rules

    rules = load_rules(BACKEND_DIR / "rules")
    out = {case: golden_digests(rules, case) for case in sorted(GOLDEN_CASES)}
    print(json.dumps(out, indent=4))
    return 0


if __name__ == "__main__":
    raise SystemExit(main() if sys.argv[1:] == [] else 2)
