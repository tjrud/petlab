"""물속 동굴(cave) 템플릿 테스트: 닫힌 한 덩어리, 무서포트 출력, 공기 갇힘 없음, 출입구·꼭대기 구멍, 종별 제약."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from app.geometry.mesh import mesh_health, part_to_mesh, to_print_orientation
from app.templates.base import ParamConstraint, RuleContext
from app.templates.cave import (
    CaveParams,
    CaveTemplate,
    door_top,
    eave_height,
    face_slope_deg,
    inner_size,
    max_top_opening,
    min_height,
    roof_top_height,
    top_opening_inner,
)
from app.validation.autofix import clamp_params
from app.validation.checks import measure_thickness, overhang_area

T = CaveTemplate()
AQUARIUM_SIZES = ("shrimp", "nano_fish", "small_fish", "community")


def ctx(rules, size: str, count: int = 1) -> RuleContext:
    return RuleContext(rules.size_rules("aquarium", size), rules.min_wall_for("aquarium", size), count)


def violated(p, c) -> set[str]:
    return {k.field for k in T.constraints(p, c) if k.violates(getattr(p, k.field))}


def geometry_ok(p: CaveParams) -> bool:
    """종 규칙과 상관없는 기하 조건 (출입구 양옆 벽, 꼭대기 구멍 둘레 지붕, 출입구 위 벽)."""
    t, d = p.wall_thickness_mm, p.entrance_diameter_mm
    return (p.width_mm >= d + 4 * t - 1e-9 and p.depth_mm >= d + 2 * t - 1e-9
            and p.top_opening_mm <= max_top_opening(p) + 1e-9 and p.height_mm >= min_height(p) - 1e-9)


def with_min_height(**kw) -> CaveParams:
    p = CaveParams(**kw)
    return p.model_copy(update={"height_mm": max(p.height_mm, math.ceil(min_height(p) * 10) / 10)})


def mesh_of(p: CaveParams):
    return part_to_mesh(T.build(p))


def assert_sound(p: CaveParams, rules) -> None:
    """닫힌 한 덩어리 + 외형 = W×D×H + 서포트 불필요 + 측정 두께 ≥ t."""
    part = T.build(p)
    assert part.is_valid
    assert len(part.solids()) == 1
    m = part_to_mesh(part)
    h = mesh_health(m)
    assert h.ok, h
    np.testing.assert_allclose(m.extents, [p.width_mm, p.depth_mm, p.height_mm], atol=0.05)
    lo, hi = m.bounds
    assert abs(lo[2]) < 1e-6
    np.testing.assert_allclose((lo[:2] + hi[:2]) / 2, [0, 0], atol=1e-6)
    pm = to_print_orientation(m, T.print_rotation(p))
    assert overhang_area(pm, rules.printing.max_overhang_deg) <= rules.printing.overhang_area_tolerance_mm2
    # 경사 지붕도 법선 방향 두께가 벽 두께와 같고, 꼭대기 테두리 덕분에 칼날처럼 얇은 곳이 없다
    th = measure_thickness(m)
    assert np.percentile(th, 1) >= p.wall_thickness_mm - 0.1
    assert np.min(th) >= p.wall_thickness_mm - 0.1


# ── 기본값 ──────────────────────────────────────────────────


@pytest.mark.parametrize("size", AQUARIUM_SIZES)
def test_defaults_build_and_satisfy_rules(rules, size):
    c = ctx(rules, size)
    p = T.default_params(c)
    assert violated(p, c) == set()
    assert geometry_ok(p)
    assert_sound(p, rules)
    # 두 마리 이상이어도 기본값은 그대로 맞다 (출입구 2개)
    assert violated(p, ctx(rules, size, 10)) == set()


@pytest.mark.parametrize("size,expected", [
    ("shrimp", (80, 70, 63, 20, 20)),
    ("nano_fish", (80, 70, 66, 25, 25)),
    ("small_fish", (102, 86, 92, 50, 50)),
    ("community", (102, 86, 92, 50, 50)),
])
def test_default_dimensions(rules, size, expected):
    p = T.default_params(ctx(rules, size))
    assert (p.width_mm, p.depth_mm, p.height_mm, p.entrance_diameter_mm, p.top_opening_mm) == expected
    assert p.height_mm == math.ceil(min_height(p) - 1e-9)
    assert p.entrance_count == 2 and p.roof_slope_deg == 45 and p.wall_thickness_mm == 3


def test_default_without_context_is_valid_geometry(rules):
    p = T.default_params()
    assert geometry_ok(p)
    assert_sound(p, rules)


# ── 경계값 ──────────────────────────────────────────────────


@pytest.mark.parametrize("kw", [
    # 가장 작은 조합
    dict(width_mm=50, depth_mm=50, entrance_diameter_mm=12, top_opening_mm=10, roof_slope_deg=40, wall_thickness_mm=1.2),
    # 가장 가파른 지붕·두꺼운 벽, 출입구 하나
    dict(width_mm=80, depth_mm=70, entrance_diameter_mm=25, top_opening_mm=25, roof_slope_deg=65,
         wall_thickness_mm=3.2, entrance_count=1),
    # 가장 큰 바닥·꼭대기 구멍 (높이 250 안에 들어가는 출입구)
    dict(width_mm=300, depth_mm=300, height_mm=250, entrance_diameter_mm=80, top_opening_mm=150, roof_slope_deg=40,
         wall_thickness_mm=3.2),
    # 길쭉한 형태 (가로 ≫ 세로): 네 지붕 면의 수평 거리가 같아 꼭대기 구멍도 길쭉하다
    dict(width_mm=240, depth_mm=60, entrance_diameter_mm=20, top_opening_mm=20, roof_slope_deg=50, wall_thickness_mm=2),
    # 세로 ≫ 가로
    dict(width_mm=70, depth_mm=200, entrance_diameter_mm=45, top_opening_mm=45, roof_slope_deg=45, wall_thickness_mm=2.4),
])
def test_field_boundaries_build(rules, kw):
    p = with_min_height(**kw)
    assert p.height_mm <= 250
    assert geometry_ok(p)
    assert_sound(p, rules)


def test_volume_matches_analytic(rules):
    """상자 + 사각뿔대 지붕 + 꼭대기 테두리 − 안쪽 − 물방울형 출입구 2개 (해석적 부피)."""
    p = CaveParams()
    W, D, H, t = p.width_mm, p.depth_mm, p.height_mm, p.wall_thickness_mm
    wi, di = inner_size(p)
    ai, bi = top_opening_inner(p)
    b = math.radians(face_slope_deg(p))
    ao, bo = ai + 2 * t / math.sin(b), bi + 2 * t / math.sin(b)
    z0, zt = eave_height(p), roof_top_height(p)
    z0o = z0 + t * (1 - math.sin(b)) / math.cos(b)

    def frustum(a1, b1, a2, b2, h):  # 각뿔대 (prismatoid 공식)
        return h / 6 * (a1 * b1 + 4 * (a1 + a2) / 2 * (b1 + b2) / 2 + a2 * b2)

    outer = W * D * z0o + frustum(W, D, ao, bo, zt - z0o) + ao * bo * (H - zt)
    cavity = wi * di * z0 + frustum(wi, di, ai, bi, zt - z0) + ai * bi * (H - zt)
    r, a = p.entrance_diameter_mm / 2, math.radians(50)
    door = (2 * r * r + math.pi * r * r / 2
            + r * math.sin(a) * (r / math.cos(a) - r * math.cos(a)) - r * r * (a - math.sin(a) * math.cos(a)))
    assert T.build(p).volume == pytest.approx(outer - cavity - 2 * door * t, rel=1e-4)


# ── 공기 갇힘 없음 (안쪽 천장이 꼭대기 구멍까지 계속 오른다) ─────────


def _ceiling_hits(m, xy: np.ndarray, z: float = 1.0) -> np.ndarray:
    """(x, y, z) 에서 위로 쏜 광선이 처음 닿는 높이. 닿지 않으면 inf."""
    origins = np.column_stack([xy, np.full(len(xy), z)])
    dirs = np.tile([0.0, 0.0, 1.0], (len(xy), 1))
    loc, iray, _ = m.ray.intersects_location(origins, dirs, multiple_hits=False)
    out = np.full(len(xy), np.inf)
    out[iray] = loc[:, 2]
    return out


@pytest.mark.parametrize("kw", [
    dict(),
    dict(width_mm=102, depth_mm=86, height_mm=92, entrance_diameter_mm=50, top_opening_mm=50),
    dict(width_mm=240, depth_mm=60, entrance_diameter_mm=20, top_opening_mm=20, roof_slope_deg=50, wall_thickness_mm=2),
    dict(roof_slope_deg=65, height_mm=110, entrance_count=1),
])
def test_no_trapped_air_pocket(kw):
    p = with_min_height(**kw)
    m = mesh_of(p)
    wi, di = inner_size(p)
    ai, bi = top_opening_inner(p)
    z0, zt = eave_height(p), roof_top_height(p)
    tan_b = math.tan(math.radians(face_slope_deg(p)))

    # 안쪽 바닥(z=1mm) 격자에서 위로: 천장은 처마 높이 이상이고, 꼭대기 구멍 아래는 아무것도 없다
    xs = np.linspace(-wi / 2 + 0.5, wi / 2 - 0.5, 25)
    ys = np.linspace(-di / 2 + 0.5, di / 2 - 0.5, 25)
    xy = np.array([(x, y) for x in xs for y in ys])
    hits = _ceiling_hits(m, xy)
    under_opening = (np.abs(xy[:, 0]) < ai / 2 - 0.1) & (np.abs(xy[:, 1]) < bi / 2 - 0.1)
    assert np.all(np.isinf(hits[under_opening]))
    roof = hits[~under_opening]
    assert np.all(np.isfinite(roof))
    assert np.all(roof >= z0 - 0.1) and np.all(roof <= zt + 0.1)
    # 해석적 천장 높이: 가장 가까운 안쪽 벽에서 떨어진 거리 × tan(면 경사)
    inset = np.minimum(wi / 2 - np.abs(xy[:, 0]), di / 2 - np.abs(xy[:, 1]))[~under_opening]
    np.testing.assert_allclose(roof, np.minimum(z0 + inset * tan_b, zt), atol=0.05)

    # 벽에서 가운데로 가는 광선마다 천장 높이가 줄지 않는다 (공기가 머물 오목한 곳이 없다)
    for ang in np.linspace(0, 2 * math.pi, 24, endpoint=False):
        dx, dy = math.cos(ang), math.sin(ang)
        reach = min((wi / 2 - 0.5) / abs(dx) if abs(dx) > 1e-9 else math.inf,
                    (di / 2 - 0.5) / abs(dy) if abs(dy) > 1e-9 else math.inf)
        s = np.linspace(reach, 0, 40)
        h = _ceiling_hits(m, np.column_stack([s * dx, s * dy]))
        assert np.isinf(h[-1])  # 가운데는 꼭대기 구멍
        h = np.where(np.isinf(h), 1e9, h)  # 뚫린 곳(닿지 않음)은 가장 높은 것으로 본다
        assert np.all(np.diff(h) >= -1e-6), (ang, h)


@pytest.mark.parametrize("slope", [40, 45, 52.5, 65])
def test_diagonal_slope_equals_roof_slope(slope):
    """가장 완만한 선(안쪽 모서리선)의 경사가 roof_slope_deg 와 같다."""
    p = with_min_height(width_mm=100, depth_mm=90, top_opening_mm=25, roof_slope_deg=slope)
    m = mesh_of(p)
    wi, di = inner_size(p)
    ai, bi = top_opening_inner(p)
    # 안쪽 모서리 (wi/2, di/2) 에서 꼭대기 구멍 모서리 (ai/2, bi/2) 로 가는 대각선 (평면에서 45°)
    f = np.linspace(0.1, 0.9, 9)
    xy = np.column_stack([wi / 2 - f * (wi - ai) / 2, di / 2 - f * (di - bi) / 2])
    z = _ceiling_hits(m, xy - np.sign(xy) * 1e-3)  # 모서리선 바로 안쪽
    run = np.hypot(*(xy[0] - xy[-1]))
    measured = math.degrees(math.atan((z[-1] - z[0]) / run))
    assert measured == pytest.approx(slope, abs=1.0)
    # 면 경사(가장 가파른 선)는 더 가파르고, 오버행(90° − 면 경사)은 출력 한계 45° 아래
    assert 90 - face_slope_deg(p) < 45 - 4


# ── 출입구 ──────────────────────────────────────────────────


def _x_hits(m, y: float, z: float) -> np.ndarray:
    """(−∞→+∞) X 방향 광선이 벽을 드나드는 X 좌표들."""
    loc, _, _ = m.ray.intersects_location([[-1000.0, y, z]], [[1.0, 0.0, 0.0]], multiple_hits=True)
    return np.sort(loc[:, 0])


@pytest.mark.parametrize("d", [15, 25, 45])
def test_door_width_and_through_type(d):
    p = with_min_height(width_mm=d + 60, depth_mm=80, entrance_diameter_mm=d, top_opening_mm=20)
    m = mesh_of(p)
    t, D, r = p.wall_thickness_mm, p.depth_mm, d / 2
    for wall_y in (-D / 2 + t / 2, D / 2 - t / 2):
        xs = _x_hits(m, wall_y, r)
        assert len(xs) == 4
        np.testing.assert_allclose(xs, [-p.width_mm / 2, -r, r, p.width_mm / 2], atol=0.06)
        # 꼭대기 직선부 아래(접점 높이)도 열려 있고, 꼭대기 위는 벽이다
        assert len(_x_hits(m, wall_y, r + r * math.cos(math.radians(50)) - 0.2)) == 4
        assert len(_x_hits(m, wall_y, door_top(d) + 0.3)) == 2


def test_single_entrance_has_no_back_door():
    p = with_min_height(entrance_count=1)
    m = mesh_of(p)
    t, D, r = p.wall_thickness_mm, p.depth_mm, p.entrance_diameter_mm / 2
    assert len(_x_hits(m, -D / 2 + t / 2, r)) == 4   # 앞 출입구
    assert len(_x_hits(m, D / 2 - t / 2, r)) == 2    # 뒷벽은 막혀 있다
    f = T.features(p)
    assert f.access_sides == ("front",) and f.entrance_count == 1
    assert [o.label_ko for o in f.openings] == ["출입구", "꼭대기 구멍"]


def test_features():
    p = CaveParams(entrance_diameter_mm=30, top_opening_mm=22, wall_thickness_mm=2.4)
    f = T.features(p)
    assert f.min_wall_thickness_mm == 2.4
    assert f.access_sides == ("front", "back") and f.entrance_count == 2
    assert [(o.kind, o.size_mm, o.label_ko, o.rule_key) for o in f.openings] == [
        ("passage", 30, "앞 출입구", "entrance_min_diameter_mm"),
        ("passage", 30, "뒤 출입구", "entrance_min_diameter_mm"),
        ("passage", 22, "꼭대기 구멍", None),  # 통과 폭(gap_trap.passable_min_mm) 기준
    ]
    assert f.extra == {"air_release": "top_opening"}
    assert f.climb_height_mm is None and f.slope_deg is None and f.step_height_mm is None
    np.testing.assert_array_equal(T.print_rotation(p), np.eye(3))  # 열린 바닥을 베드에 대고 그대로 출력
    assert T.height_field == "height_mm" and T.size_fields == ("width_mm", "depth_mm", "height_mm")
    assert T.legacy_defaults == {}


# ── 종별 제약 ───────────────────────────────────────────────


def test_constraints_flag_species_rules(rules):
    c = ctx(rules, "nano_fish")
    s = c.size
    good = T.default_params(c)
    assert violated(good, c) == set()
    # 꼭대기 구멍이 통과 폭보다 작으면 끼임 구간
    assert "top_opening_mm" in violated(good.model_copy(update={"top_opening_mm": s.gap_trap.passable_min_mm - 5}), c)
    # 종 기준(45°)보다 완만한 지붕
    assert "roof_slope_deg" in violated(good.model_copy(update={"roof_slope_deg": 42}), c)
    # 물고기는 출입구 하나인 동굴에 끼일 수 있다
    assert "entrance_count" in violated(good.model_copy(update={"entrance_count": 1}), c)
    # 높이가 지붕 경사·출입구를 담지 못함
    assert "height_mm" in violated(good.model_copy(update={"height_mm": min_height(good) - 1}), c)
    # 출입구가 종 최소보다 좁음
    assert "entrance_diameter_mm" in violated(good.model_copy(update={"entrance_diameter_mm": 15}), c)
    # 벽이 종 최소보다 얇음
    assert "wall_thickness_mm" in violated(good.model_copy(update={"wall_thickness_mm": 1.5}), c)
    # 꼭대기 구멍이 너무 커서 지붕 경사면이 남지 않음
    assert "top_opening_mm" in violated(good.model_copy(update={"top_opening_mm": max_top_opening(good) + 1}), c)


def test_shrimp_allows_single_entrance_and_print_limit_slope(rules):
    """새우는 출입구 하나도 되고(뒤로 튀어 나간다), 종 기준 30° 보다 출력 한계 40° 가 앞선다."""
    c = ctx(rules, "shrimp")
    p = T.default_params(c).model_copy(update={"entrance_count": 1, "roof_slope_deg": 40})
    p = p.model_copy(update={"height_mm": math.ceil(min_height(p))})
    assert violated(p, c) == set()
    assert not [k for k in T.constraints(p, c) if k.field in ("entrance_count", "roof_slope_deg")]
    with pytest.raises(ValidationError):
        CaveParams(roof_slope_deg=35)


def test_constraint_reasons(rules):
    c = ctx(rules, "small_fish")
    s = c.size
    p = T.default_params(c).model_copy(update={"height_mm": 40})
    cons = {(k.field, k.min is not None): k for k in T.constraints(p, c)}
    assert cons[("wall_thickness_mm", True)].reason_ko == \
        f"벽 두께는 최소 {c.min_wall_mm:g}mm 이상이어야 합니다 (물속 내구성·출력 기준)"
    # 은신처와 같은 출입구 문구 (영어 카탈로그도 같은 것을 쓴다)
    assert cons[("entrance_diameter_mm", True)].reason_ko == \
        f"{s.display_name} 출입구는 최소 {s.entrance_min_diameter_mm:g}mm 이상이어야 합니다"
    assert cons[("entrance_count", True)].reason_ko == \
        "물고기는 좁은 곳에서 뒤로 잘 빠져나오지 못해 동굴 출입구는 2개 이상(앞뒤로 뚫린 관통형)이어야 합니다"
    assert cons[("top_opening_mm", True)].reason_ko == \
        "물속에서 공기가 빠지고 몸이 끼지 않도록 꼭대기 구멍은 최소 45mm 이상이어야 합니다"
    h = cons[("height_mm", True)]
    assert h.min == pytest.approx(math.ceil(min_height(p) * 10) / 10)
    assert h.min >= min_height(p) - 1e-9
    assert h.reason_ko == f"출입구 위로 벽이 남고 지붕 경사가 들어가도록 높이는 {h.min:g}mm 이상이어야 합니다"
    assert all(k.blocking for k in T.constraints(p, c))
    # 종 기준(30°)이 출력 한계(40°)보다 완만하면 지붕 경사 제약을 따로 두지 않는다
    assert ("roof_slope_deg", True) not in cons
    nano = T.constraints(T.default_params(ctx(rules, "nano_fish")), ctx(rules, "nano_fish"))
    slope = [k for k in nano if k.field == "roof_slope_deg"]
    assert len(slope) == 1 and slope[0].min == 45 and slope[0].source == "species"
    assert slope[0].reason_ko == "안쪽 천장에 공기가 남지 않도록 지붕 경사는 45° 이상이어야 합니다"


@pytest.mark.parametrize("size", AQUARIUM_SIZES)
@pytest.mark.parametrize("start", [
    # 모든 값이 너무 작은 설계
    dict(width_mm=50, depth_mm=50, height_mm=30, entrance_diameter_mm=12, entrance_count=1, top_opening_mm=10,
         roof_slope_deg=40, wall_thickness_mm=1.2),
    # 꼭대기 구멍이 너무 큼 + 낮음
    dict(width_mm=80, depth_mm=70, height_mm=40, entrance_diameter_mm=25, top_opening_mm=150, roof_slope_deg=65),
    # 세로가 출입구에는 넉넉하지만 꼭대기 구멍 둘레 지붕이 남지 않음 (소형 어종 45mm 구멍)
    dict(width_mm=120, depth_mm=55, height_mm=80, entrance_diameter_mm=45, top_opening_mm=45),
])
def test_autofix_converges_without_conflict(rules, size, start):
    """서로 얽힌 제약(벽 두께 → 지붕 높이, 꼭대기 구멍 ↔ 가로·세로)도 보정 반복으로 충돌 없이 맞춰진다."""
    c = ctx(rules, size)
    fixed, issues = clamp_params(T, CaveParams(**start), c)
    assert not [i for i in issues if i.code == "param_conflict"], issues
    assert violated(fixed, c) == set()
    assert geometry_ok(fixed)
    assert mesh_health(mesh_of(fixed)).ok
    # 꼭대기 구멍은 요청한 폭을 (커진) 가로·세로가 허용하는 만큼 지킨다: 보정 순서 때문에 더 줄지 않는다
    P = c.size.gap_trap.passable_min_mm
    assert fixed.top_opening_mm == pytest.approx(max(P, min(start["top_opening_mm"], max_top_opening(fixed))))


def test_top_opening_max_uses_the_footprint_other_constraints_set(rules):
    """세로가 출입구 때문에 60 → 66 으로 커지면 꼭대기 구멍 상한도 66 기준(50)이다 (예전: 60 기준 44 로 줄였다가 최소 45 로
    다시 올려 '60 → 45 … 최소 45mm 이상이어야' 라는 어긋난 문구가 났다)."""
    c = ctx(rules, "small_fish")
    start = CaveParams(width_mm=80, depth_mm=60, entrance_diameter_mm=60, top_opening_mm=60, wall_thickness_mm=3)
    fixed, issues = clamp_params(T, start, c)
    assert fixed.depth_mm == 66
    assert fixed.top_opening_mm == 50 == min(60, max_top_opening(fixed))
    [msg] = [i.message_ko for i in issues if i.details["field"] == "top_opening_mm"]
    assert msg == ("물속 동굴: 꼭대기 구멍 폭 60 → 50 로 보정했습니다. "
                   "지붕 경사면이 남도록 꼭대기 구멍은 안쪽 폭보다 10mm 이상 작아야 합니다")
    assert violated(fixed, c) == set()


def test_min_height_mm_is_lowest_cave_the_rules_allow(rules):
    """가장 낮은 동굴: 종별 최소 출입구·적용 최소 벽·최소 지붕 경사(출력 40° 이상)에 꼭대기 구멍을 가장 넓힌 것."""
    for size in AQUARIUM_SIZES:
        c = ctx(rules, size)
        s = c.size
        slope = max(40.0, s.aquatic.ceiling_min_slope_deg)
        P = s.gap_trap.passable_min_mm
        t = c.min_wall_mm
        side = max(50.0, P + 2 * t + 10, s.entrance_min_diameter_mm + 4 * t)  # 필드 하한 50
        lowest = CaveParams(width_mm=side, depth_mm=side, entrance_diameter_mm=s.entrance_min_diameter_mm,
                            top_opening_mm=side - 2 * t - 10, roof_slope_deg=slope, wall_thickness_mm=t)
        # 외형 높이 필드 하한(30mm)보다 낮게는 만들지 않는다 (새우)
        assert T.min_height_mm(c) == pytest.approx(max(30.0, math.ceil(min_height(lowest) * 10 - 1e-6) / 10))
        lowest = lowest.model_copy(update={"height_mm": T.min_height_mm(c)})
        assert violated(lowest, c) == set()


@pytest.mark.parametrize("size", AQUARIUM_SIZES)
@pytest.mark.parametrize("extra", [0.0, 3.0, 12.0, 40.0])
def test_height_limit_fits_default_cave_without_conflict(rules, size, extra):
    """높이 한도(어항: 물 깊이 − 구조물 위 물 깊이)가 가장 낮은 동굴 이상이면 기본 동굴을 충돌 없이 그 안에 맞춘다."""
    base = ctx(rules, size, count=6)
    limit = T.min_height_mm(base) + extra
    c = RuleContext(base.size, base.min_wall_mm, 6, height_limit_mm=limit)
    height_max = ParamConstraint("height_mm", max=limit)
    fixed, issues = clamp_params(T, T.default_params(base), c, [height_max])
    assert not [i for i in issues if i.code == "param_conflict"], issues
    assert fixed.height_mm <= limit + 1e-9 and min_height(fixed) <= limit + 1e-9
    assert violated(fixed, base) == set()  # 한도 없이 다시 검증해도 (저장된 버전 재검증) 통과
    assert geometry_ok(fixed)


def test_height_limit_below_lowest_cave_changes_nothing(rules):
    """가장 낮은 동굴도 들어가지 않으면 템플릿은 지붕을 바꾸지 않는다 (엔진이 필요한 물 깊이를 한 번만 알린다)."""
    base = ctx(rules, "small_fish", count=6)
    c = RuleContext(base.size, base.min_wall_mm, 6, height_limit_mm=T.min_height_mm(base) - 0.5)
    p = T.default_params(base)
    assert T.constraints(p, c) == T.constraints(p, base)


def test_params_reject_out_of_range():
    for kw in (dict(width_mm=40), dict(depth_mm=301), dict(height_mm=20), dict(entrance_diameter_mm=10),
               dict(entrance_count=0), dict(entrance_count=3), dict(top_opening_mm=5), dict(roof_slope_deg=30),
               dict(roof_slope_deg=70), dict(wall_thickness_mm=1.0), dict(wall_thickness_mm=4), dict(vent_count=2)):
        with pytest.raises(ValidationError):
            CaveParams(**kw)


def test_registered():
    from app.templates.keys import TEMPLATE_MODULES
    from app.templates.registry import get_template

    assert isinstance(get_template("cave"), CaveTemplate)
    assert TEMPLATE_MODULES["cave"] == "app.templates.cave"
    assert T.display_name_ko == "물속 동굴"
