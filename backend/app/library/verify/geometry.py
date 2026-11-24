"""형상 검사 G01–G07, G10, G12 (설계 §7.2 "Geometry"). G08·G09·G11 은 honesty.py.

변형마다 엔진의 다시 만들기 경로(engine.build_item)로 형상을 만들어 그 결과를 본다:
- G01 만들기 성공, 5초 안
- G02 출력 파트마다 닫힌 메시, 감김 일관, 부피 > 0, 덩어리 하나, 출력 자세 바닥 z=0
- G03 조립 형상 부피 = 출력 파트 부피 합 (0.5% 안)
- G04 출력 공간 (XY 는 짧은 변·긴 변끼리, Z) — 런타임은 경고만 한다
- G05 선언한 출력 자세의 오버행 면적 ≤ printing.overhang_area_tolerance_mm2
- G06 설계 최소 벽 ≥ 적용 최소 벽, 실측 1 백분위 ≥ 0.9 × 최소 벽, 실측 ≥ 0.9 × 선언한 최소 벽 (정직성)
- G07 envelope 가 build() 경계 상자와 축마다 0.5mm 안, host·room_host 는 XY 가운데 0.5mm 안, 바닥 z=0 ± 0.01
- G10 run_engine (넉넉한 케이지) 오류 없음, 안전 경고 없음
- G12 같은 프로세스에서 두 번, 새 프로세스에서 한 번 만든 STL 파일 바이트가 같다 (기본값만; 골든이 된다)
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import trimesh

from app.domain import BuiltItem, Placement, PlacementHint
from app.geometry.mesh import mesh_health
from app.library.verify.report import CheckResult, failed, passed
from app.templates.base import RuleContext, Template, TemplateParams

BUILD_MAX_S = 5.0
VOLUME_TOL = 0.005
ENVELOPE_TOL_MM = 0.5
CENTRE_TOL_MM = 0.5
FLOOR_TOL_MM = 0.01
THIN_FACTOR = 0.9
FORBIDDEN_WARNINGS = ("exceeds_build_volume", "support_needed", "wall_thin_measured", "tip_over_risk",
                      "opening_too_small", "vent_too_large", "window_trap")


@dataclass
class Built:
    """변형 하나의 형상: 엔진 결과(item)와 build() 좌표계 경계 상자(raw_bounds), 걸린 시간."""

    item: BuiltItem | None
    raw_bounds: np.ndarray | None
    seconds: float
    error: str | None = None
    error_code: str | None = None  # DSL 오류 코드 (DSL006: 식 계산 오류 → P4)


def build(t: Template, p: TemplateParams, printing: Any) -> Built:
    """engine.build_item 으로 만든다 (저장된 설계를 다시 만드는 경로와 같다)."""
    from app.services.engine import build_item

    t0 = time.perf_counter()
    try:
        item = build_item(0, t, p, PlacementHint(), printing)
        raw = t.build(p).bounding_box()  # build() 좌표계 (build_item 은 메시를 가운데로 옮긴다). DSL 부품은 기억한 형상
        bounds = np.array([[raw.min.X, raw.min.Y, raw.min.Z], [raw.max.X, raw.max.Y, raw.max.Z]], dtype=float)
    except Exception as e:  # noqa: BLE001 - 형상 커널·식 오류 모두 실패로 적는다 (check_build)
        return Built(None, None, time.perf_counter() - t0, f"{type(e).__name__}: {e}", getattr(e, "code", None))
    return Built(item, bounds, time.perf_counter() - t0)


def check_build(b: Built, variant: str | None = None) -> CheckResult:
    if b.item is None:
        if b.error_code == "DSL006":  # 식 계산 오류 (0 으로 나누기 등)는 P4
            return failed("P4", variant, f"evaluation failed while building: {b.error}",
                          hint="guard the expression for every value in the field bounds")
        return failed("G01", variant, f"build failed: {b.error}", hint="see the error; check cut sizes and overlaps")
    if b.seconds > BUILD_MAX_S:
        return failed("G01", variant, f"build took {b.seconds:.1f} s", value=b.seconds, limit=BUILD_MAX_S,
                      hint="use fewer steps or repeats")
    return passed("G01", variant, value=b.seconds, limit=BUILD_MAX_S)


def check_meshes(it: BuiltItem, variant: str | None = None) -> list[CheckResult]:
    out = []
    for part in it.print_parts:
        ptr = f"/print/{part.key}"
        h = mesh_health(part.mesh)
        problems = []
        if not h.watertight:
            problems.append("not watertight")
        if not h.winding_consistent:
            problems.append("inconsistent winding")
        if h.volume_mm3 <= 0:
            problems.append("no volume")
        bodies = int(part.mesh.body_count)
        if bodies != 1:
            problems.append(f"{bodies} separate bodies")
        zmin = float(part.print_mesh.bounds[0][2])
        if abs(zmin) > FLOOR_TOL_MM:
            problems.append(f"print z-min {zmin:.3f}")
        if problems:
            out.append(failed("G02", variant, f"print part {part.key}: " + ", ".join(problems), path=ptr,
                              hint="every add must overlap the solid it joins; cuts must not split the part"))
        else:
            out.append(passed("G02", variant, path=ptr))
    return out


def check_volume(it: BuiltItem, variant: str | None = None) -> CheckResult:
    parts = it.print_parts
    if len(parts) <= 1:
        return passed("G03", variant, value=0.0, limit=VOLUME_TOL)
    whole = abs(float(it.mesh.volume))
    total = sum(abs(float(p.mesh.volume)) for p in parts)
    rel = abs(whole - total) / max(whole, 1e-9)
    if rel > VOLUME_TOL:
        return failed("G03", variant, f"build volume {whole:.0f} mm³ differs from the print parts' {total:.0f} mm³ "
                                      f"by {rel * 100:.2f} %", value=rel, limit=VOLUME_TOL,
                      hint="every step must belong to exactly one print part and parts must not overlap")
    return passed("G03", variant, value=rel, limit=VOLUME_TOL)


def check_bed(it: BuiltItem, printing: Any, variant: str | None = None) -> list[CheckResult]:
    bx, by, bz = (float(v) for v in printing.build_volume_mm)
    out = []
    for part in it.print_parts:
        ex = part.print_mesh.extents
        lo_xy, hi_xy = sorted((float(ex[0]), float(ex[1])))
        ok = lo_xy <= min(bx, by) + 1e-6 and hi_xy <= max(bx, by) + 1e-6 and ex[2] <= bz + 1e-6
        over = max(lo_xy - min(bx, by), hi_xy - max(bx, by), float(ex[2]) - bz)
        if ok:
            out.append(passed("G04", variant, path=f"/print/{part.key}", value=over, limit=0.0))
        else:
            out.append(failed("G04", variant, f"print part {part.key} is {ex[0]:.0f}×{ex[1]:.0f}×{ex[2]:.0f} mm, the bed "
                                              f"is {bx:g}×{by:g}×{bz:g}", path=f"/print/{part.key}", value=over,
                              limit=0.0, hint="lower the field maximum or split the part"))
    return out


def check_overhang(it: BuiltItem, printing: Any, variant: str | None = None) -> list[CheckResult]:
    from app.validation.checks import overhang_area

    tol = float(printing.overhang_area_tolerance_mm2)
    out = []
    for part in it.print_parts:
        area = overhang_area(part.print_mesh, printing.max_overhang_deg)
        ptr = f"/print/{part.key}"
        if area > tol:
            out.append(failed("G05", variant, f"overhang {area:.0f} mm² facing down in print part {part.key}",
                              path=ptr + "/rotation", value=area, limit=tol,
                              hint=f"choose a rotation where no face points down more than "
                                   f"{printing.max_overhang_deg:g}°, or remove the unsupported roof"))
        else:
            out.append(passed("G05", variant, path=ptr, value=area, limit=tol))
    return out


def check_walls(it: BuiltItem, ctx: RuleContext, variant: str | None = None, measure: bool = True
                ) -> list[CheckResult]:
    from app.validation.checks import measure_thickness

    out = []
    designed = it.features.min_wall_thickness_mm
    if designed < ctx.min_wall_mm - 1e-6:
        out.append(failed("G06", variant, f"designed min wall {designed:g} mm is below {ctx.min_wall_mm:g} mm",
                          path="/features/min_wall", value=designed, limit=ctx.min_wall_mm,
                          hint="raise the wall_thickness_mm minimum or its constraint"))
    if not measure:
        return out or [passed("G06", variant, value=designed, limit=ctx.min_wall_mm)]
    for part in it.print_parts:
        if not part.mesh.is_watertight:
            continue
        th = measure_thickness(part.mesh, exclude=part.thin_ok_mesh)
        if not len(th):
            continue
        p1 = float(np.percentile(th, 1))
        need = THIN_FACTOR * ctx.min_wall_mm
        honest = THIN_FACTOR * designed
        ptr = f"/print/{part.key}"
        if p1 < need - 1e-9:
            out.append(failed("G06", variant, f"measured wall p1 {p1:.2f} mm in {part.key} is below "
                                              f"{need:.2f} mm (0.9 × {ctx.min_wall_mm:g})", path=ptr, value=p1,
                              limit=need, hint="thicken the thin region or avoid knife edges"))
        elif p1 < honest - 1e-9:
            out.append(failed("G06", variant, f"measured wall p1 {p1:.2f} mm in {part.key} is below 0.9 × the declared "
                                              f"min wall {designed:g} mm", path="/features/min_wall", value=p1,
                              limit=honest, hint="declare features.min_wall as the thinnest wall"))
        else:
            out.append(passed("G06", variant, path=ptr, value=p1, limit=need))
    return out or [passed("G06", variant)]


def check_envelope(t: Template, p: TemplateParams, b: Built, variant: str | None = None) -> CheckResult:
    assert b.raw_bounds is not None
    lo, hi = b.raw_bounds
    size = hi - lo
    env = np.asarray(t.envelope(p), dtype=float)
    err = float(np.abs(env - size).max())
    if err > ENVELOPE_TOL_MM:
        return failed("G07", variant, f"envelope {np.round(env, 1).tolist()} differs from the mesh "
                                      f"{np.round(size, 1).tolist()} by {err:.2f} mm", path="/envelope", value=err,
                      limit=ENVELOPE_TOL_MM, hint="envelope must be the outer size of the add steps")
    if abs(float(lo[2])) > FLOOR_TOL_MM:
        return failed("G07", variant, f"the part does not stand on z=0 (z-min {lo[2]:.3f})", value=float(lo[2]),
                      limit=FLOOR_TOL_MM, hint="the lowest add must start at z=0")
    if t.role in ("host", "room_host"):
        off = float(np.abs((lo[:2] + hi[:2]) / 2).max())
        if off > CENTRE_TOL_MM:
            return failed("G07", variant, f"the part is {off:.2f} mm off the XY centre", value=off,
                          limit=CENTRE_TOL_MM, hint="centre the outer box on x=0, y=0")
    return passed("G07", variant, path="/envelope", value=err, limit=ENVELOPE_TOL_MM)


def check_engine(t: Template, p: TemplateParams, rules: Any, species: str, size: str, count: int,
                 variant: str | None = None, extra_keys: tuple[str, ...] = ()) -> CheckResult:
    from app.library.verify.variants import engine_context
    from app.services.engine import ItemSpec, run_engine
    from app.validation.report import Severity

    ctx = engine_context(rules, species, size, count, extra_keys)
    try:
        res = run_engine([ItemSpec(t.key, p.model_dump(mode="json"))], ctx)
    except Exception as e:  # noqa: BLE001
        return failed("G10", variant, f"run_engine raised {type(e).__name__}: {e}")
    bad = [i for i in res.report.issues
           if i.severity == Severity.error or (i.severity == Severity.warning
                                               and (i.code in FORBIDDEN_WARNINGS or i.code.startswith("gap_trap")))]
    if bad:
        return failed("G10", variant, f"engine {bad[0].severity.value} {bad[0].code}: {bad[0].message_ko}",
                      hint="the engine must accept the part without errors or safety warnings")
    return passed("G10", variant)


# ── G12 ──


def item_files(it: BuiltItem) -> dict[str, bytes]:
    """build_item 결과가 캐시에 쓰는 STL 파일 (design_service._mesh_files 와 같은 이름; 가운데 놓은 world_0)."""
    files = {"print_0.stl": it.print_mesh.export(file_type="stl")}
    for part in it.parts[1:]:
        files[f"print_0_{part.key}.stl"] = part.print_mesh.export(file_type="stl")
    placed = dataclasses.replace(it, placement=Placement(0.0, 0.0, 0))
    files["world_0.stl"] = placed.world_mesh().export(file_type="stl")
    return files


def file_digests(it: BuiltItem) -> dict[str, str]:
    import hashlib

    return {k: hashlib.sha256(v).hexdigest() for k, v in sorted(item_files(it).items())}


def check_determinism(t: Template, p: TemplateParams, printing: Any, first: BuiltItem, variant: str | None = None,
                      draft: dict | None = None, subprocess: bool = True) -> tuple[CheckResult, dict[str, str]]:
    """두 번째 같은 프로세스 빌드(형상 기억을 비우고)와 새 프로세스 빌드가 첫 빌드와 같은 바이트인지.
    돌려주는 digests 가 골든이 된다."""
    from app.library.verify.rebuild import clear_build_cache, fresh_process_digests
    from app.services.engine import build_item

    a = file_digests(first)
    clear_build_cache(t)
    second = file_digests(build_item(0, t, p, PlacementHint(), printing))
    if second != a:
        bad = sorted(k for k in a if a.get(k) != second.get(k))
        return failed("G12", variant, f"a second in-process build differs: {bad}",
                      hint="geometry must depend on params only (no randomness, no global state)"), a
    if subprocess:
        try:
            third = fresh_process_digests(t.key, p.model_dump(mode="json"), draft)
        except Exception as e:  # noqa: BLE001
            return failed("G12", variant, f"fresh-process build failed: {e}"), a
        if third != a:
            bad = sorted(k for k in a if a.get(k) != third.get(k))
            return failed("G12", variant, f"a fresh-process build differs: {bad}",
                          hint="geometry must not depend on process state (hash seeds, caches, import order)"), a
    return passed("G12", variant), a


def use_mesh(it: BuiltItem) -> trimesh.Trimesh:
    """사용 자세 메시 (가운데 놓고 바닥 z=0)."""
    return it.mesh
