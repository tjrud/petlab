"""형상이 선언과 맞는지 (설계 §7.4): G08 틈 끼임 자가 검사, G09 특징 정직성, G11 넘어짐 각도.

- G08: 표면 600점(seed 0)에서 바깥 법선 방향으로 0.05mm 밖에서 광선을 쏜다. 바닥 0.5mm 안의 점은 건너뛴다
  (바닥에 놓인 면). 거의 마주 보는 면(면 법선 · 광선 < −0.9) 중 가장 가까운 것, 광선이 아래로 가면(dz < −0.5) 가상의 바닥
  평면 z=0 도 맞은편으로 본다. 거리가 (safe_max, passable_min) 사이(끼임 구간)인 점이 3개 이상이면 실패.
  선언하지 않은 홈, 케이지 바닥과의 쐐기, 낮은 아래 틈을 잡는다.
- G09: 오르기 (host·accessory·none; 방(room_host) 지붕은 은신처·집처럼 관례로 빼고, 터널(connector) 지붕도 같다): 위를 향한 면(nz ≥ cos 20°)이
  이어진 영역 중 XY 투영의 최대 내접원 지름이 20mm 이상인 곳을 설 수 있는 곳으로 본다. 가장 높은 곳이 종 최대 턱 높이를
  넘으면 climb_height_mm 를 선언해야 하고 그 높이 − 0.5 이상이어야 한다.
  경사: 턱 높이보다 위에서 5°–80° 로 위를 향한 면이 400mm² 를 넘으면 slope_deg 를 선언해야 하고 면적 가중 90 백분위
  각도 − 0.5 이상이어야 한다 (방은 오르기와 같은 까닭으로 뺀다).
  통로 확인체(DSL passage 개구부의 probe): 폭 size − 0.5 의 통로 단면 기둥이 부품과 1mm³ 미만으로 겹친다.
  환기구·창 크기: DSL 이 자른 단계에서 구한 크기가 features 에 그대로 있는지.
- G11: 바닥(z < 0.5) 꼭짓점의 볼록 껍질 변마다 atan(부피 중심 XY 에서 변까지 거리 / 부피 중심 높이) 의 최솟값.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import numpy as np
import trimesh

from app.library.verify.report import CheckResult, failed, passed
from app.templates.base import Template, TemplateParams

GAP_SAMPLES = 600
GAP_SEED = 0
GAP_START_MM = 0.05
GAP_FLOOR_SKIP_MM = 0.5
# 맞은편 면: 면 법선 · 광선 < 이 값. 설계 §7.4 는 −0.5 였으나, 그 값은 뾰족 아치·집 모양 출입구와 터널 천장 꼭대기의
# V 자 모서리(아래는 통로 폭 그대로 트여 있다)를 틈으로 센다 (tunnel_junction 의 집 모양 출입구도). 거의 마주 보는 면(약 25° 안)만
# 홈으로 센다: 평행한 두 벽 사이 홈(trap_slot)은 그대로 잡힌다. 바닥 평면 쐐기 규칙(FLOOR_DOWN)은 설계대로 −0.5
GAP_FACING = -0.9
FLOOR_DOWN = -0.5
GAP_EPS_MM = 0.05  # GapTrapRule.is_trap 와 같은 계산 허용오차
GAP_MAX_HITS = 3
STAND_COS = math.cos(math.radians(20.0))
STAND_MIN_DIAMETER_MM = 20.0
CLIMB_TOL_MM = 0.5
SLOPE_MIN_DEG, SLOPE_MAX_DEG = 5.0, 80.0
SLOPE_MIN_AREA_MM2 = 400.0
SLOPE_TOL_DEG = 0.5
PROBE_MAX_MM3 = 1.0
# 오르기·경사 정직성에서 빼는 역할: 방(은신처·집 지붕, 설계 관례)과 터널(바깥 지붕도 같은 관례; DSL v1 에는 없는 역할)
CLIMB_EXEMPT_ROLES = ("room_host", "connector")
PROBE_SHRINK_MM = 0.5
TIP_BASE_Z_MM = 0.5
TIP_MIN_DEG = 15.0


# ── G08 ──


def gap_hits(mesh: trimesh.Trimesh, safe_max: float, passable_min: float, samples: int = GAP_SAMPLES,
             seed: int = GAP_SEED) -> list[tuple[np.ndarray, float]]:
    """끼임 구간 거리의 (표본점, 거리) 목록. 메시는 사용 자세 (바닥 z=0)."""
    pts, fidx = trimesh.sample.sample_surface(mesh, samples, seed=seed)
    keep = pts[:, 2] > GAP_FLOOR_SKIP_MM
    pts, fidx = pts[keep], fidx[keep]
    if not len(pts):
        return []
    dirs = mesh.face_normals[fidx]
    origins = pts + dirs * GAP_START_MM
    best = np.full(len(pts), np.inf)
    loc, iray, itri = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)
    if len(loc):
        facing = np.einsum("ij,ij->i", mesh.face_normals[itri], dirs[iray]) < GAP_FACING
        dist = np.linalg.norm(loc - origins[iray], axis=1) + GAP_START_MM
        for k in np.flatnonzero(facing):
            i = iray[k]
            best[i] = min(best[i], dist[k])
    down = dirs[:, 2] < FLOOR_DOWN
    floor = np.where(down, pts[:, 2] / np.maximum(-dirs[:, 2], 1e-9), np.inf)
    best = np.minimum(best, floor)
    trap = (best > safe_max + GAP_EPS_MM) & (best < passable_min - GAP_EPS_MM)
    return [(pts[i], float(best[i])) for i in np.flatnonzero(trap)]


def check_gap_trap(mesh: trimesh.Trimesh, size: Any, variant: str | None = None) -> CheckResult:
    hits = gap_hits(mesh, size.gap_trap.safe_max_mm, size.gap_trap.passable_min_mm)
    if len(hits) >= GAP_MAX_HITS:
        p, d = hits[0]
        return failed("G08", variant, f"{len(hits)} surface points face a gap of {d:.1f} mm (between "
                                      f"{size.gap_trap.safe_max_mm:g} and {size.gap_trap.passable_min_mm:g}) "
                                      f"first at {np.round(p, 1).tolist()}",
                      value=float(len(hits)), limit=float(GAP_MAX_HITS),
                      hint="close the gap below the safe size or open it to the passable size "
                           "(also under a deck: the cage floor counts)")
    return passed("G08", variant, value=float(len(hits)), limit=float(GAP_MAX_HITS))


# ── G09 ──


def _regions(mesh: trimesh.Trimesh, mask: np.ndarray) -> list[np.ndarray]:
    """mask 인 면들을 모서리로 이어진 영역으로 나눈다 (면 번호 배열 목록)."""
    faces = np.flatnonzero(mask)
    if not len(faces):
        return []
    adj = mesh.face_adjacency
    both = mask[adj[:, 0]] & mask[adj[:, 1]]
    groups = trimesh.graph.connected_components(adj[both], nodes=faces, min_len=1)
    return [np.asarray(g, dtype=int) for g in groups]


def _inscribed_diameter(mesh: trimesh.Trimesh, faces: np.ndarray) -> float:
    import shapely
    from shapely.geometry import Polygon

    tris = mesh.vertices[mesh.faces[faces]][:, :, :2]
    polys = [Polygon(t) for t in tris if abs(Polygon(t).area) > 1e-9]
    if not polys:
        return 0.0
    geom = shapely.unary_union([shapely.buffer(p, 1e-4) for p in polys])
    if geom.is_empty or geom.area < 1.0:
        return 0.0
    if geom.geom_type == "MultiPolygon":
        return max(2 * shapely.maximum_inscribed_circle(g, 0.2).length for g in geom.geoms)
    return 2 * shapely.maximum_inscribed_circle(geom, 0.2).length


def standable_height(mesh: trimesh.Trimesh) -> float | None:
    """설 수 있는 영역 중 가장 높은 곳의 높이 (없으면 None)."""
    up = mesh.face_normals[:, 2] >= STAND_COS
    best = None
    for faces in _regions(mesh, up):
        h = float(mesh.vertices[mesh.faces[faces]][:, :, 2].max())
        if best is not None and h <= best:
            continue
        if _inscribed_diameter(mesh, faces) >= STAND_MIN_DIAMETER_MM:
            best = h
    return best


def slope_p90(mesh: trimesh.Trimesh, above_mm: float) -> tuple[float, float]:
    """턱 높이 위의 기운 위향 면: (면적 mm², 면적 가중 90 백분위 각도°)."""
    nz = np.clip(mesh.face_normals[:, 2], -1, 1)
    ang = np.degrees(np.arccos(nz))
    z = mesh.triangles_center[:, 2]
    m = (nz > 0) & (ang >= SLOPE_MIN_DEG) & (ang <= SLOPE_MAX_DEG) & (z > above_mm)
    area = float(mesh.area_faces[m].sum())
    if area <= 0:
        return 0.0, 0.0
    a, w = ang[m], mesh.area_faces[m]
    order = np.argsort(a)
    cum = np.cumsum(w[order]) / w.sum()
    return area, float(a[order][np.searchsorted(cum, 0.9)])


def feature_honesty(t: Template, p: TemplateParams, mesh: trimesh.Trimesh, size: Any, variant: str | None = None
                    ) -> list[CheckResult]:
    """G09. mesh 는 사용 자세 메시 (바닥 z=0)."""
    out: list[CheckResult] = []
    f = t.features(p)
    step = size.max_step_height_mm
    if t.role not in CLIMB_EXEMPT_ROLES and step is not None:
        h = standable_height(mesh)
        if h is not None and h > step + 1e-6:
            if f.climb_height_mm is None or f.climb_height_mm < h - CLIMB_TOL_MM:
                out.append(failed("G09", variant, f"a standable surface at {h:.1f} mm is above the step limit "
                                                  f"{step:g} mm but climb_height is "
                                                  f"{'undeclared' if f.climb_height_mm is None else f'{f.climb_height_mm:g}'}",
                                  path="/features/climb_height", value=f.climb_height_mm, limit=h,
                                  hint="declare features.climb_height as the highest standing surface"))
            else:
                out.append(passed("G09", variant, path="/features/climb_height", value=f.climb_height_mm, limit=h))
        area, p90 = slope_p90(mesh, step)
        if area > SLOPE_MIN_AREA_MM2:
            if f.slope_deg is None or f.slope_deg < p90 - SLOPE_TOL_DEG:
                out.append(failed("G09", variant, f"{area:.0f} mm² of sloped surface (p90 {p90:.1f}°) above the step "
                                                  f"limit but slope_deg is {f.slope_deg}",
                                  path="/features/slope_deg", value=f.slope_deg, limit=p90,
                                  hint="declare features.slope_deg as the steepest walkable slope"))
            else:
                out.append(passed("G09", variant, path="/features/slope_deg", value=f.slope_deg, limit=p90))
    out += _dsl_openings(t, p, variant)
    if not out:
        out.append(passed("G09", variant))
    return out


def _dsl_openings(t: Template, p: TemplateParams, variant: str | None) -> list[CheckResult]:
    """DSL 부품: passage 개구부 확인체가 부품과 겹치지 않는지, 선언한 환기구·창이 features 에 있는지."""
    pf = getattr(t, "part_file", None)
    if pf is None:
        return []
    from app.library import ops
    from app.library.errors import pointer
    from app.library.schema import PassageOpening

    out: list[CheckResult] = []
    env = t._geo(p)  # type: ignore[attr-defined]
    labels = {o.label_ko: o for o in t.features(p).openings}
    solid = None
    for k, o in enumerate(pf.features.openings or []):
        base = f"{pointer('features', 'openings', k)}"
        if not t._when(f"{base}/when", env):  # type: ignore[attr-defined]
            continue
        if isinstance(o, PassageOpening):
            size = t._num(f"{base}/size", env)  # type: ignore[attr-defined]
            at = t._vec(f"{base}/probe/at", env)  # type: ignore[attr-defined]
            length = t._num(f"{base}/probe/length", env)  # type: ignore[attr-defined]
            probe = ops.passage(o.probe.shape, size - PROBE_SHRINK_MM, o.probe.axis, length, at)
            if solid is None:
                solid = t.build(p)
            vol = float((solid & probe).volume) if probe is not None else 0.0
            if vol >= PROBE_MAX_MM3:
                out.append(failed("G09", variant, f"opening {o.label.en!r}: the clearance probe overlaps the part by "
                                                  f"{vol:.1f} mm³", path=f"{base}/probe", value=vol,
                                  limit=PROBE_MAX_MM3, hint="the declared passage is not clear; fix size or probe"))
            else:
                out.append(passed("G09", variant, path=f"{base}/probe", value=vol, limit=PROBE_MAX_MM3))
        else:
            got = labels.get(o.label.ko)
            if got is None or not got.size_mm > 0:
                out.append(failed("G09", variant, f"opening {o.label.en!r} has no derived size", path=base))
            else:
                out.append(passed("G09", variant, path=base))
    return out


# ── G11 ──


def tipping_angle(mesh: trimesh.Trimesh) -> float:
    """정적 안정 각도 (°): 바닥 접촉 꼭짓점의 볼록 껍질 변마다 atan(부피 중심 XY 에서 변까지 / 부피 중심 높이)의 최솟값.
    부피 중심이 껍질 밖이면 음수, 접촉이 선·점뿐이면 0."""
    from shapely.geometry import LineString, MultiPoint, Point

    lo = mesh.bounds[0][2]
    base = mesh.vertices[mesh.vertices[:, 2] < lo + TIP_BASE_Z_MM][:, :2]
    hull = MultiPoint([tuple(v) for v in base]).convex_hull
    if hull.geom_type != "Polygon" or hull.area < 1e-6:
        return 0.0
    c = mesh.center_mass if mesh.is_watertight else mesh.centroid
    cz = float(c[2] - lo)
    if cz <= 1e-9:
        return 90.0
    pt = Point(float(c[0]), float(c[1]))
    inside = hull.contains(pt)
    coords = list(hull.exterior.coords)
    best = math.inf
    for a, b in itertools.pairwise(coords):
        d = LineString([a, b]).distance(pt)
        ang = math.degrees(math.atan2(d if inside else -d, cz))
        best = min(best, ang)
    return float(best)


def check_stability(mesh: trimesh.Trimesh, variant: str | None = None) -> CheckResult:
    ang = tipping_angle(mesh)
    if ang < TIP_MIN_DEG:
        return failed("G11", variant, f"tipping angle {ang:.1f}° is below {TIP_MIN_DEG:g}°", value=ang,
                      limit=TIP_MIN_DEG, hint="widen the base or lower the centre of mass")
    return passed("G11", variant, value=ang, limit=TIP_MIN_DEG)
