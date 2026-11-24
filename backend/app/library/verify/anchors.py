"""연결 지점 검사 C01–C08 (설계 §7.2 "Connection")와 시험 파일이 함께 쓰는 도우미.

어느 Template 에도 쓴다 (DSL 부품과 코드 부품). 연결 지점은 build() 좌표계에 있으므로 메시도 build() 형상을 그대로
(가운데 맞추기 없이) 바꾼 것을 쓴다 (build_mesh).

- C01 좌표틀: normal·up 이 단위 벡터이고 서로 수직, side 가 있는 자리는 옆을 향함, bottom 은 메시 바닥 높이·외곽 안
- C02 표면·방향: 확인점이 표면에서 0.5mm 안, 법선 쪽 1mm 는 형상 밖, 안쪽 0.4mm 는 형상 안 (옆면 연결판 자리는 0.5mm
  올려서), 출입구의 side 는 출입 면. 출입구·통로 자리의 확인점은 개구부 꼭대기 바로 위 벽
- C03 받쳐진 연결판 자리: 자리 안 5×5 격자에서 바깥 2mm 에서 쏜 광선이 면 평면(±0.2mm)의 평평한 면(법선 · n ≥ 0.99)에 닿는다
- C04 출입구 안쪽이 비었는지: 바깥 2mm 에서 개구부 높이 가운데·좌우 ¼ 지점으로 쏜 광선이 벽 + 20mm (또는 맞은편 벽 앞)
  까지 아무것에도 닿지 않는다
- C05 출입구 단면이 선언한 단면 종류와 같은 종류 (터널 안쪽 단면 다섯 종류와의 IoU 중 가장 크고 0.97 초과)
- C06 면 치수 파라미터를 바꾸면 연결 지점이 그만큼 바뀐다 (통로 +4, 벽 +0.5, 가로 +10 가운데 유지, 높이 +10)
- C07 open_port 가 출입구를 만들고, 이미 출입구인 자리는 그대로 돌려준다
- C08 attach_order 의 자리가 결합 종류에 맞고, envelope 가 해석적이며 1ms 안에 계산된다
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import numpy as np
import trimesh

from app.geometry.mesh import part_to_mesh
from app.library.verify.report import CheckResult, failed, passed
from app.templates.base import Anchor, Template, TemplateParams
from app.validation.autofix import get_path, set_path

SURFACE_TOL_MM = 0.5
OUTSIDE_MM = 1.0
INSIDE_MM = 0.4
SIDE_MOUNT_LIFT_MM = 0.5
PROBE_ABOVE_PORT_MM = 2.0
MOUNT_INSET_MM = 2.0
MOUNT_GRID = 5
MOUNT_RAY_START_MM = 2.0
MOUNT_PLANE_TOL_MM = 0.2
MOUNT_FLAT_DOT = 0.99
DOOR_RAY_START_MM = 2.0
DOOR_CLEAR_MM = 20.0
PROFILE_IOU_MIN = 0.97
ENVELOPE_MAX_S = 0.001
SHAPES = ("pointed_arch", "round_arch", "tube", "box", "house")
BUMPS = {"port": 4.0, "wall": 0.5, "width": 10.0, "height": 10.0}


def build_mesh(t: Template, p: TemplateParams) -> trimesh.Trimesh:
    """build() 좌표계 그대로의 메시 (연결 지점과 같은 좌표)."""
    return part_to_mesh(t.build(p))


def _v(x: Any) -> np.ndarray:
    return np.asarray(x, dtype=float)


def tangent(a: Anchor) -> np.ndarray:
    """면 좌표의 가로 방향 t = up × normal (바깥에서 볼 때 오른쪽)."""
    return np.cross(_v(a.up), _v(a.normal))


def is_door(a: Anchor) -> bool:
    return a.port is not None and a.wall_mm is not None


def port_top(t: Template, p: TemplateParams, name: str, a: Anchor) -> float:
    """통로 자리의 개구부 꼭대기 높이 (기준점에서 up 방향). port_profile 단면의 위 끝, 없으면 터널 단면 높이 공식."""
    prof = t.port_profile(p, name)
    if prof is not None:
        return float(prof.bounding_box().max.Y)
    from app.templates.tunnel import height_for

    return height_for(a.profile or "round_arch", float(a.port or 0.0), 0.0)


def face_extent(mesh: trimesh.Trimesh, origin: np.ndarray, direction: np.ndarray) -> float:
    """메시 경계 상자가 origin 에서 direction 쪽으로 뻗은 길이 (꼭짓점 투영의 최댓값)."""
    lo, hi = mesh.bounds
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    return float(((corners - origin) @ direction).max())


def surface_probe(t: Template, p: TemplateParams, name: str, a: Anchor, mesh: trimesh.Trimesh) -> np.ndarray:
    """기준점 근처에서 형상 표면 위에 있어야 하는 점. 통로가 아니면 기준점, 통로 자리는 개구부 꼭대기 위
    min(2, (면 높이 − 개구부 높이)/2) mm (개구부 위 벽·플랜지 고리 가운데쯤)."""
    o, up = _v(a.origin), _v(a.up)
    if a.port is None:
        return o
    ph = port_top(t, p, name, a)
    h_face = face_extent(mesh, o, up)
    return o + up * (ph + min(PROBE_ABOVE_PORT_MM, max(h_face - ph, 0.0) / 2))


# ── C01, C02 ──


def check_frames(t: Template, p: TemplateParams, mesh: trimesh.Trimesh, variant: str | None = None
                 ) -> list[CheckResult]:
    out: list[CheckResult] = []
    lo, hi = mesh.bounds
    for name, a in t.anchors(p).items():
        n, up = _v(a.normal), _v(a.up)
        ptr = f"/anchors/{name}"
        if abs(np.linalg.norm(n) - 1) > 1e-6 or abs(np.linalg.norm(up) - 1) > 1e-6:
            out.append(failed("C01", variant, f"anchor {name}: normal and up must be unit vectors", path=ptr))
            continue
        if abs(float(n @ up)) > 1e-6:
            out.append(failed("C01", variant, f"anchor {name}: normal and up are not perpendicular", path=ptr,
                              hint="choose up along +Z for side faces and +Y for top/bottom"))
            continue
        if a.side is not None and abs(float(n[2])) > 1e-6:
            out.append(failed("C01", variant, f"anchor {name}: a side anchor must face sideways", path=ptr))
            continue
        if name == "bottom":
            o = _v(a.origin)
            if abs(o[2] - lo[2]) > 1e-6 or np.any(o[:2] < lo[:2] - 1e-6) or np.any(o[:2] > hi[:2] + 1e-6):
                out.append(failed("C01", variant, f"anchor bottom {tuple(o)} is not on the floor inside the bounds",
                                  path=ptr, value=float(o[2] - lo[2]), limit=0.0))
                continue
        out.append(passed("C01", variant, path=ptr))
    return out


def check_anchors(t: Template, p: TemplateParams, mesh: trimesh.Trimesh | None = None, variant: str | None = None
                  ) -> list[CheckResult]:
    """C01 과 C02 (일반화한 연결 지점 표면 검사). 시험 파일(test_anchors_existing)도 이 함수를 쓴다."""
    mesh = mesh if mesh is not None else build_mesh(t, p)
    out = check_frames(t, p, mesh, variant)
    if any(not r.ok for r in out):
        return out
    access = set(t.features(p).access_sides)
    for name, a in t.anchors(p).items():
        if name == "bottom":
            continue
        ptr = f"/anchors/{name}"
        n, up = _v(a.normal), _v(a.up)
        q = surface_probe(t, p, name, a, mesh)
        _, dist, _ = mesh.nearest.on_surface([q])
        if dist[0] > SURFACE_TOL_MM:
            out.append(failed("C02", variant, f"anchor {name}: probe {np.round(q, 2).tolist()} is {dist[0]:.2f} mm "
                                              "from the surface", path=ptr, value=float(dist[0]), limit=SURFACE_TOL_MM,
                              hint="put the origin on the outer face (bottom centre for side faces)"))
            continue
        lift = SIDE_MOUNT_LIFT_MM if abs(n[2]) < 0.5 and a.port is None else 0.0
        s = q + up * lift
        if mesh.contains([s + n * OUTSIDE_MM])[0]:
            out.append(failed("C02", variant, f"anchor {name}: the normal points into the part", path=ptr,
                              hint="the normal must point out of the face"))
            continue
        if not mesh.contains([s - n * INSIDE_MM])[0]:
            out.append(failed("C02", variant, f"anchor {name}: the origin is not on the outer face", path=ptr,
                              hint="move the origin onto the face, with material behind it"))
            continue
        # 출입구의 side 는 출입 면 (은신처 뒷면은 출입구가 아니어도 side="back" 을 단다: 슬라이드 결합용, F18)
        if a.side is not None and a.port is not None and a.side not in access:
            out.append(failed("C02", variant, f"anchor {name}: door side {a.side!r} is not in access_sides", path=ptr))
            continue
        out.append(passed("C02", variant, path=ptr))
    return out


# ── C03 ──


def check_mounts(t: Template, p: TemplateParams, mesh: trimesh.Trimesh, variant: str | None = None
                 ) -> list[CheckResult]:
    out: list[CheckResult] = []
    for name, a in t.anchors(p).items():
        if a.mount is None:
            continue
        ptr = f"/anchors/{name}/mount"
        left, right, h = a.mount
        n, up, tt, o = _v(a.normal), _v(a.up), tangent(a), _v(a.origin)
        us = np.linspace(left + MOUNT_INSET_MM, right - MOUNT_INSET_MM, MOUNT_GRID)
        vs = np.linspace(MOUNT_INSET_MM, h - MOUNT_INSET_MM, MOUNT_GRID)
        pts = np.array([o + tt * u + up * v for u in us for v in vs])
        origins = pts + n * MOUNT_RAY_START_MM
        dirs = np.tile(-n, (len(origins), 1))
        loc, iray, itri = mesh.ray.intersects_location(origins, dirs, multiple_hits=False)
        hit = {int(i): (loc[k], int(itri[k])) for k, i in enumerate(iray)}
        bad = None
        worst = 0.0
        for i in range(len(origins)):
            if i not in hit:
                bad = (pts[i], "no material behind the mount")
                break
            point, tri = hit[i]
            d = float(np.linalg.norm(point - origins[i])) - MOUNT_RAY_START_MM
            worst = max(worst, abs(d))
            if abs(d) > MOUNT_PLANE_TOL_MM:
                bad = (pts[i], f"the face is {d:+.2f} mm off the mount plane")
                break
            if float(mesh.face_normals[tri] @ n) < MOUNT_FLAT_DOT:
                bad = (pts[i], "the face under the mount is not flat")
                break
        if bad is not None:
            out.append(failed("C03", variant, f"mount {name} at {np.round(bad[0], 1).tolist()}: {bad[1]}", path=ptr,
                              hint="a mount must cover a solid flat wall; shrink it or close the face"))
        else:
            out.append(passed("C03", variant, path=ptr, value=worst, limit=MOUNT_PLANE_TOL_MM))
    return out


# ── C04 ──


def check_doors_open(t: Template, p: TemplateParams, mesh: trimesh.Trimesh, variant: str | None = None
                     ) -> list[CheckResult]:
    out: list[CheckResult] = []
    for name, a in t.anchors(p).items():
        if not is_door(a):
            continue
        assert a.port is not None and a.wall_mm is not None
        ptr = f"/anchors/{name}/door"
        n, up, tt, o = _v(a.normal), _v(a.up), tangent(a), _v(a.origin)
        ph = port_top(t, p, name, a)
        h = min(a.port / 2, ph / 2)
        depth = face_extent(mesh, o, -n)
        reach = min(a.wall_mm + DOOR_CLEAR_MM, depth - a.wall_mm - 0.5)
        origins = np.array([o + up * h + tt * lat + n * DOOR_RAY_START_MM for lat in (-a.port / 4, 0.0, a.port / 4)])
        loc, iray, _ = mesh.ray.intersects_location(origins, np.tile(-n, (3, 1)), multiple_hits=False)
        blocked = [float(np.linalg.norm(loc[k] - origins[i])) - DOOR_RAY_START_MM for k, i in enumerate(iray)]
        near = [d for d in blocked if d < reach]
        if near:
            out.append(failed("C04", variant, f"door {name}: material {min(near):.1f} mm behind the face "
                                              f"(must be clear for {reach:.1f} mm)", path=ptr,
                              value=min(near), limit=reach, hint="keep the space behind a door empty"))
        else:
            out.append(passed("C04", variant, path=ptr))
    return out


# ── C05 ──


def _above_floor(face):
    from build123d import Align, Rectangle

    return face & Rectangle(1000, 1000, align=(Align.CENTER, Align.MIN))


def profile_iou(a, b) -> float:
    """두 2D 단면의 바닥(y=0) 위 부분 IoU."""
    a, b = _above_floor(a), _above_floor(b)
    inter = (a & b).area
    union = a.area + b.area - inter
    return float(inter / union) if union > 0 else 0.0


def profile_scores(prof, width: float) -> dict[str, float]:
    """출입구 단면과 같은 폭의 터널 안쪽 단면 다섯 종류의 IoU (관은 단면이 떠 있는 높이를 벽 두께로 본다)."""
    from app.templates.tunnel import TunnelParams, inner_profile

    raise_mm = float(prof.bounding_box().min.Y)
    tube_wall = raise_mm if raise_mm > 0.5 else 3.0
    return {s: profile_iou(prof, inner_profile(TunnelParams.model_construct(
        inner_diameter_mm=width, shape=s, wall_thickness_mm=tube_wall if s == "tube" else 3.0))) for s in SHAPES}


def check_profiles(t: Template, p: TemplateParams, variant: str | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    for name, a in t.anchors(p).items():
        if a.port is None:
            continue
        ptr = f"/anchors/{name}/door/profile"
        prof = t.port_profile(p, name)
        if prof is None or a.profile is None:
            out.append(failed("C05", variant, f"anchor {name}: a port needs port_profile and profile", path=ptr))
            continue
        scores = profile_scores(prof, a.port)
        best = max(scores, key=scores.__getitem__)
        if best != a.profile or scores[a.profile] <= PROFILE_IOU_MIN:
            out.append(failed("C05", variant, f"anchor {name}: profile {a.profile!r} scores {scores[a.profile]:.3f}, "
                                              f"best {best!r} {scores[best]:.3f}", path=ptr,
                              value=scores[a.profile], limit=PROFILE_IOU_MIN))
        else:
            out.append(passed("C05", variant, path=ptr, value=scores[a.profile], limit=PROFILE_IOU_MIN))
    return out


# ── C06 ──


def bumped(t: Template, p: TemplateParams, path: str, delta: float) -> TemplateParams:
    """path 값을 delta 만큼 바꾼 파라미터 (검증 실패면 pydantic.ValidationError)."""
    d = p.model_dump()
    set_path(d, path, get_path(d, path) + delta)
    return t.Params.model_validate(d)


def _bump(t: Template, p: TemplateParams, path: str, delta: float) -> tuple[TemplateParams, float] | None:
    """+delta 가 범위를 벗어나면 −delta. 둘 다 안 되면 None."""
    from pydantic import ValidationError

    for d in (delta, -delta):
        try:
            return bumped(t, p, path, d), d
        except ValidationError:
            continue
    return None


def check_face_fields(t: Template, p: TemplateParams, variant: str | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    d = p.model_dump()
    anchors = t.anchors(p)
    for name, a in anchors.items():
        ff = t.face_fields(p, name)
        ptr = f"/anchors/{name}/fields"
        problems: list[str] = []
        if (ff.port is None) != (a.port is None):
            problems.append("fields.port must be set exactly when the anchor is a port")
        if (a.profile is None) != (a.port is None):
            problems.append("profile must be set exactly when the anchor is a port")
        if (ff.wall is None) != (a.wall_mm is None):
            problems.append("fields.wall must be set exactly when the anchor has a wall")
        if ff.port is not None and a.port is not None and abs(float(get_path(d, ff.port)) - a.port) > 1e-6:
            problems.append(f"fields.port {ff.port} = {get_path(d, ff.port)} but the anchor port is {a.port}")
        if ff.profile is not None and a.profile is not None and get_path(d, ff.profile) != a.profile:
            problems.append(f"fields.profile {ff.profile} = {get_path(d, ff.profile)!r} but the anchor has {a.profile!r}")
        if ff.wall is not None and a.wall_mm is not None and float(get_path(d, ff.wall)) > a.wall_mm + 1e-9:
            problems.append(f"fields.wall {ff.wall} is thicker than the anchor wall {a.wall_mm}")
        problems += _bump_problems(t, p, name, a, ff)
        if problems:
            out.append(failed("C06", variant, f"anchor {name}: " + "; ".join(problems), path=ptr,
                              hint="fields.* must name the params that size this face"))
        else:
            out.append(passed("C06", variant, path=ptr))
    return out


def _bump_problems(t: Template, p: TemplateParams, name: str, a: Anchor, ff: Any) -> list[str]:
    out: list[str] = []
    if ff.port is not None and a.port is not None:
        b = _bump(t, p, ff.port, BUMPS["port"])
        if b is not None:
            q, dl = b
            got = t.anchors(q)[name].port
            if got is None or abs(got - (a.port + dl)) > 1e-6:
                out.append(f"port {ff.port} {dl:+g} moved the port to {got}, not {a.port + dl:g}")
    if ff.wall is not None and a.wall_mm is not None:
        b = _bump(t, p, ff.wall, BUMPS["wall"])
        if b is not None:
            q, dl = b
            got = t.anchors(q)[name].wall_mm
            if got is None or abs(got - (a.wall_mm + dl)) > 1e-6:
                out.append(f"wall {ff.wall} {dl:+g} moved wall_mm to {got}, not {a.wall_mm + dl:g}")
    if a.mount is not None:
        left, right, h = a.mount
        if ff.width is not None:
            b = _bump(t, p, ff.width, BUMPS["width"])
            if b is not None:
                q, dl = b
                m = t.anchors(q)[name].mount
                if m is None or abs((m[1] - m[0]) - (right - left + dl)) > 1e-6 or abs((m[0] + m[1]) - (left + right)) > 1e-6:
                    out.append(f"width {ff.width} {dl:+g} gave mount {m}, not {right - left + dl:g} wide and centred")
        if ff.height is not None:
            b = _bump(t, p, ff.height, BUMPS["height"])
            if b is not None:
                q, dl = b
                m = t.anchors(q)[name].mount
                if m is None or abs(m[2] - (h + dl)) > 1e-6 or abs(m[0] - left) > 1e-6 or abs(m[1] - right) > 1e-6:
                    out.append(f"height {ff.height} {dl:+g} gave mount {m}, not height {h + dl:g}")
    return out


# ── C07 ──


def _dsl_open_entries(t: Template, p: TemplateParams) -> dict[str, bool]:
    """DSL 부품: anchor → 그 자리에 when 이 참인 opens 항목이 있는지."""
    pf = getattr(t, "part_file", None)
    if pf is None:
        return {}
    from app.library.errors import pointer

    env = t._geo(p)  # type: ignore[attr-defined]
    out: dict[str, bool] = {}
    for idx, o in enumerate(pf.opens):
        if t._when(f"{pointer('opens', idx)}/when", env):  # type: ignore[attr-defined]
            out[o.anchor] = True
    return out


def check_open_port(t: Template, p: TemplateParams, variant: str | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    entries = _dsl_open_entries(t, p)
    for name, a in t.anchors(p).items():
        ptr = f"/anchors/{name}"
        try:
            q = t.open_port(p, name)
        except Exception as e:  # noqa: BLE001
            out.append(failed("C07", variant, f"open_port({name}) raised {type(e).__name__}: {e}", path=ptr))
            continue
        if is_door(a):
            if t.role == "room_host" and q != p:
                out.append(failed("C07", variant, f"open_port({name}) on an open door must return the params unchanged",
                                  path=ptr))
                continue
        elif q is not None:
            b = t.anchors(q).get(name)
            if b is None or not is_door(b):
                out.append(failed("C07", variant, f"open_port({name}) returned params that do not open a door there",
                                  path=f"/opens/{name}", hint="the set values must make door.when true"))
                continue
        elif entries.get(name):
            out.append(failed("C07", variant, f"the opens entry for {name} does not make a valid door",
                              path=f"/opens/{name}", hint="the set values must be valid params that make door.when true"))
            continue
        out.append(passed("C07", variant, path=ptr))
    return out


# ── C08 ──


def check_attach(t: Template, p: TemplateParams, variant: str | None = None) -> list[CheckResult]:
    from app.templates.base import Template as Base

    out: list[CheckResult] = []
    anchors = t.anchors(p)
    for kind, names in t.attach_order.items():
        for name in names:
            ptr = f"/attach_order/{kind}"
            a = anchors.get(name)
            if a is None:
                out.append(failed("C08", variant, f"attach_order.{kind} names missing anchor {name!r}", path=ptr))
                continue
            if kind == "slide":
                n = _v(a.normal)
                if a.port is not None or abs(n[2]) > 1e-6 or not np.allclose(_v(a.up), (0, 0, 1)):
                    out.append(failed("C08", variant, f"slide anchor {name} must be a plain side face with up +Z",
                                      path=ptr))
                    continue
            elif kind == "passage":
                # 닫힌 면(출입구 배치에 따라 닫힌 갈림길 면, 2층 집의 뒷면)은 이 변형에서 통로가 아닐 수 있다.
                # 적어도 한 변형에서 통로이거나 열 수 있는지는 run.passage_coverage 가 변형을 모아 본다
                if abs(float(_v(a.normal)[2])) > 1e-6:
                    out.append(failed("C08", variant, f"passage anchor {name} must face sideways", path=ptr))
                    continue
                if a.port is not None and a.wall_mm is None and t.role == "room_host":
                    out.append(failed("C08", variant, f"passage anchor {name} of a room is a port without a wall",
                                      path=ptr, hint="a room door needs wall (the wall the plug goes through)"))
                    continue
            out.append(passed("C08", variant, path=ptr))
    if t.role == "room_host":
        ok = any(anchors[n].port is not None for n in t.attach_order.get("passage", ()) if n in anchors)
        out.append(passed("C08", variant, path="/attach_order/passage") if ok else
                   failed("C08", variant, "a room_host needs an open door in attach_order.passage",
                          path="/attach_order/passage"))
    if t.composable:
        if type(t).envelope is Base.envelope:
            out.append(failed("C08", variant, "envelope is not analytic (falls back to the bbox of build)",
                              path="/envelope", hint="compute the outer size from params without building"))
        else:
            out.append(_envelope_speed(t, p, variant))
    return out


def _envelope_speed(t: Template, p: TemplateParams, variant: str | None) -> CheckResult:
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        t.envelope(p)
        times.append(time.perf_counter() - t0)
    med = sorted(times)[len(times) // 2]
    if med > ENVELOPE_MAX_S:
        return failed("C08", variant, f"envelope takes {med * 1000:.2f} ms", path="/envelope",
                      value=med * 1000, limit=ENVELOPE_MAX_S * 1000)
    return passed("C08", variant, path="/envelope", value=med * 1000, limit=ENVELOPE_MAX_S * 1000)


def connection_checks(t: Template, p: TemplateParams, mesh: trimesh.Trimesh | None = None,
                      variant: str | None = None, only: Mapping[str, bool] | None = None) -> list[CheckResult]:
    """C01–C08 (조립 부품만; role none 은 C01 만). only: 돌릴 검사 id (None: 모두)."""
    want = (lambda cid: True) if only is None else (lambda cid: bool(only.get(cid)))
    mesh = mesh if mesh is not None else build_mesh(t, p)
    out: list[CheckResult] = []
    if want("C01") or want("C02"):
        res = check_anchors(t, p, mesh, variant)
        out += [r for r in res if want(r.id)]
    if not t.composable:
        return out
    if want("C03"):
        out += check_mounts(t, p, mesh, variant)
    if want("C04"):
        out += check_doors_open(t, p, mesh, variant)
    if want("C05"):
        out += check_profiles(t, p, variant)
    if want("C06"):
        out += check_face_fields(t, p, variant)
    if want("C07"):
        out += check_open_port(t, p, variant)
    if want("C08"):
        out += check_attach(t, p, variant)
    return out


def passage_capable(t: Template, p: TemplateParams) -> set[str]:
    """attach_order.passage 중 이 파라미터에서 통로이거나 열 수 있는 자리."""
    anchors = t.anchors(p)
    out = set()
    for name in t.attach_order.get("passage", ()):
        a = anchors.get(name)
        if a is not None and (a.port is not None or t.open_port(p, name) is not None):
            out.add(name)
    return out
