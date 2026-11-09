"""설계 자동 검증.

모든 기준값은 rules/species.yaml, rules/printing.yaml 에서 온다 (코드 하드코딩 금지).
각 검사 함수는 Issue 목록을 반환한다.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import trimesh
from shapely.geometry import box

from app.domain import BuiltItem, Cage, access_strip
from app.geometry.mesh import mesh_health
from app.rules.loader import PrintingRules, SizeRules
from app.validation.report import Issue, Severity

OVERLAP_AREA_TOL_MM2 = 1.0  # 수치 오차 허용 (규칙이 아닌 계산 허용오차)
ON_BED_Z_TOL_MM = 0.01


def _err(code: str, msg: str, **kw) -> Issue:
    return Issue(code=code, severity=Severity.error, message_ko=msg, **kw)


def _warn(code: str, msg: str, **kw) -> Issue:
    return Issue(code=code, severity=Severity.warning, message_ko=msg, **kw)


# ── 메시 건전성 ─────────────────────────────────────────────


def check_mesh(items: list[BuiltItem]) -> list[Issue]:
    out = []
    for it in items:
        h = mesh_health(it.mesh)
        if not h.ok:
            reasons = []
            if not h.watertight:
                reasons.append("닫힌 형태(watertight)가 아님")
            if not h.winding_consistent:
                reasons.append("면 방향 불일치")
            if h.watertight and h.volume_mm3 <= 0:
                reasons.append("부피가 0 이하")
            out.append(_err(
                "mesh_invalid",
                f"{it.label_ko}: 메시에 결함이 있어 출력 파일로 쓸 수 없습니다 ({', '.join(reasons)}).",
                item_index=it.index, details={"watertight": h.watertight, "winding": h.winding_consistent},
            ))
    return out


# ── 케이지 적합 / 겹침 / 틈새 / 출입구 ─────────────────────────


def check_fit(items: list[BuiltItem], cage: Cage) -> list[Issue]:
    out = []
    for it in items:
        if it.height_mm > cage.height_mm + 1e-6:
            out.append(_err(
                "too_tall",
                f"{it.label_ko}: 높이 {it.height_mm:.0f}mm 가 케이지 내부 높이 {cage.height_mm:.0f}mm 보다 높습니다.",
                item_index=it.index,
            ))
        if it.placement is None:
            out.append(_err(
                "cannot_place",
                f"{it.label_ko}: 케이지 안에 안전하게 놓을 자리가 없습니다. 구조물 수나 크기를 줄여 주세요.",
                item_index=it.index,
            ))
            continue
        x0, y0, x1, y1 = it.world_footprint.bounds
        tol = 1e-3
        if x0 < -tol or y0 < -tol or x1 > cage.width_mm + tol or y1 > cage.depth_mm + tol:
            out.append(_err(
                "out_of_cage",
                f"{it.label_ko}: 케이지 바닥 밖으로 벗어납니다.",
                item_index=it.index,
                details={"bounds": [x0, y0, x1, y1]},
            ))
    return out


def _placed(items: list[BuiltItem]) -> list[BuiltItem]:
    return [it for it in items if it.placement is not None]


def check_overlap(items: list[BuiltItem]) -> list[Issue]:
    out = []
    placed = _placed(items)
    fps = {it.index: it.world_footprint for it in placed}
    for a, b in itertools.combinations(placed, 2):
        area = fps[a.index].intersection(fps[b.index]).area
        if area > OVERLAP_AREA_TOL_MM2:
            out.append(_err(
                "overlap",
                f"{a.label_ko} 와(과) {b.label_ko} 이(가) 겹칩니다 (겹친 면적 {area:.0f}mm²).",
                item_index=a.index, related_index=b.index, details={"area_mm2": area},
            ))
    return out


def check_gaps(items: list[BuiltItem], cage: Cage, size: SizeRules) -> list[Issue]:
    """끼임 틈새: safe_max < 틈 < passable_min 이면 발·몸이 낄 수 있다."""
    gt = size.gap_trap
    rng = f"{gt.safe_max_mm:g}~{gt.passable_min_mm:g}mm"
    out = []
    placed = _placed(items)
    fps = {it.index: it.world_footprint for it in placed}
    for a, b in itertools.combinations(placed, 2):
        g = fps[a.index].distance(fps[b.index])
        if gt.is_trap(g):
            out.append(_err(
                "gap_trap",
                f"{a.label_ko} 와(과) {b.label_ko} 사이 틈 {g:.1f}mm 가 끼임 위험 구간({rng})에 있습니다.",
                item_index=a.index, related_index=b.index, details={"gap_mm": g},
            ))
    walls = ("왼쪽", "오른쪽", "앞쪽", "뒤쪽")
    for it in placed:
        x0, y0, x1, y1 = fps[it.index].bounds
        for name, g in zip(walls, (x0, cage.width_mm - x1, y0, cage.depth_mm - y1)):
            if gt.is_trap(g):
                out.append(_err(
                    "gap_trap_wall",
                    f"{it.label_ko} 와(과) {name} 벽 사이 틈 {g:.1f}mm 가 끼임 위험 구간({rng})에 있습니다.",
                    item_index=it.index, details={"gap_mm": g, "wall": name},
                ))
    for it in items:
        g = cage.height_mm - it.height_mm
        if g >= 0 and gt.is_trap(g):
            out.append(_err(
                "gap_trap_ceiling",
                f"{it.label_ko} 윗면과 케이지 천장 사이 틈 {g:.1f}mm 가 끼임 위험 구간({rng})에 있습니다.",
                item_index=it.index, details={"gap_mm": g},
            ))
    return out


def check_access(items: list[BuiltItem], cage: Cage, size: SizeRules) -> list[Issue]:
    """출입구 앞이 passable_min 깊이만큼 비어 있는지."""
    P = size.gap_trap.passable_min_mm
    out = []
    placed = _placed(items)
    cage_box = box(0, 0, cage.width_mm, cage.depth_mm)
    for it in placed:
        for dv in it.access_directions(it.placement.rotation_deg):  # type: ignore[union-attr]
            s = access_strip(it.world_rect, dv, P)
            strip = box(s.x0, s.y0, s.x1, s.y1)
            blocked_by_wall = strip.difference(cage_box).area > OVERLAP_AREA_TOL_MM2
            blockers = [
                o for o in placed
                if o.index != it.index and o.world_footprint.intersection(strip).area > OVERLAP_AREA_TOL_MM2
            ]
            if blocked_by_wall or blockers:
                by = "케이지 벽" if blocked_by_wall else ", ".join(o.label_ko for o in blockers)
                out.append(_err(
                    "access_blocked",
                    f"{it.label_ko}: 출입구 앞 {P:g}mm 공간이 {by}에 막혀 있습니다.",
                    item_index=it.index,
                ))
    return out


# ── 개구부 / 오르기 ─────────────────────────────────────────


def check_openings(items: list[BuiltItem], size: SizeRules, count: int = 1) -> list[Issue]:
    out = []
    gt = size.gap_trap
    need = size.hideout_min_entrances.for_count(count)
    for it in items:
        n = it.features.entrance_count
        if n is not None and n < need:
            out.append(_err(
                "too_few_entrances",
                f"{it.label_ko}: 출입구가 {n}개뿐입니다. {count}마리가 함께 지내면 서로 피할 수 있도록 "
                f"{need}개 이상이어야 합니다.",
                item_index=it.index, details={"count": n, "required": need, "animals": count},
            ))
        for op in it.features.openings:
            if op.kind == "passage":
                req = float(getattr(size, op.rule_key)) if op.rule_key else gt.passable_min_mm
                if op.size_mm < req - 1e-6:
                    out.append(_err(
                        "opening_too_small",
                        f"{it.label_ko}: {op.label_ko} {op.size_mm:g}mm 가 {size.display_name} 기준 최소 {req:g}mm 보다 작습니다.",
                        item_index=it.index, details={"size_mm": op.size_mm, "required_mm": req},
                    ))
            elif op.size_mm > gt.safe_max_mm + 1e-6:
                out.append(_err(
                    "vent_too_large",
                    f"{it.label_ko}: {op.label_ko} {op.size_mm:g}mm 가 끼임 안전 기준 {gt.safe_max_mm:g}mm 보다 큽니다.",
                    item_index=it.index, details={"size_mm": op.size_mm, "max_mm": gt.safe_max_mm},
                ))
    return out


def check_climb(items: list[BuiltItem], size: SizeRules) -> list[Issue]:
    out = []
    for it in items:
        f = it.features
        if f.climb_height_mm is not None and f.climb_height_mm > size.max_climb_height_mm + 1e-6:
            out.append(_err("climb_too_high",
                            f"{it.label_ko}: 높이 {f.climb_height_mm:g}mm 가 낙상 안전 기준 {size.max_climb_height_mm:g}mm 를 넘습니다.",
                            item_index=it.index))
        if f.slope_deg is not None and f.slope_deg > size.max_ramp_angle_deg + 1e-6:
            out.append(_err("slope_too_steep",
                            f"{it.label_ko}: 경사 {f.slope_deg:g}° 가 기준 {size.max_ramp_angle_deg:g}° 보다 가파릅니다.",
                            item_index=it.index))
        if f.step_height_mm is not None and f.step_height_mm > size.max_step_height_mm + 1e-6:
            out.append(_err("step_too_high",
                            f"{it.label_ko}: 턱(단) 높이 {f.step_height_mm:g}mm 가 기준 {size.max_step_height_mm:g}mm 보다 높습니다.",
                            item_index=it.index))
    return out


# ── 출력성: 벽 두께 / 오버행 / 출력 공간 ──────────────────────


def measure_thickness(mesh: trimesh.Trimesh, samples: int = 1500, seed: int = 0) -> np.ndarray:
    """표면 샘플점에서 안쪽 법선 방향으로 광선을 쏘아 반대편 면까지 거리(국소 두께)를 잰다."""
    pts, fidx = trimesh.sample.sample_surface(mesh, samples, seed=seed)
    n = mesh.face_normals[fidx]
    origins = pts - n * 1e-3
    loc, iray, _ = mesh.ray.intersects_location(origins, -n, multiple_hits=False)
    if len(loc) == 0:
        return np.array([])
    return np.linalg.norm(loc - origins[iray], axis=1) + 1e-3


def check_wall_thickness(items: list[BuiltItem], min_wall_mm: float, measure: bool = True) -> list[Issue]:
    out = []
    for it in items:
        designed = it.features.min_wall_thickness_mm
        if designed < min_wall_mm - 1e-6:
            out.append(_err(
                "wall_too_thin",
                f"{it.label_ko}: 벽 두께 {designed:g}mm 가 최소 기준 {min_wall_mm:g}mm 보다 얇습니다 (갉음 내구성·출력 기준).",
                item_index=it.index, details={"designed_mm": designed, "min_mm": min_wall_mm},
            ))
            continue
        if measure and it.mesh.is_watertight:
            t = measure_thickness(it.mesh)
            if len(t):
                p1 = float(np.percentile(t, 1))
                if p1 < 0.9 * min_wall_mm:
                    out.append(_warn(
                        "wall_thin_measured",
                        f"{it.label_ko}: 메시 측정 결과 일부 두께가 약 {p1:.1f}mm 로 기준 {min_wall_mm:g}mm 보다 얇습니다.",
                        item_index=it.index, details={"measured_p1_mm": p1, "min_mm": min_wall_mm},
                    ))
    return out


def overhang_area(mesh: trimesh.Trimesh, max_overhang_deg: float) -> float:
    """출력 자세 메시에서 서포트가 필요한 하향 면적 (베드에 닿은 면 제외).
    오버행 각도는 수직면=0°, 수평 천장=90° 기준."""
    nz = mesh.face_normals[:, 2]
    steep = nz < -math.sin(math.radians(max_overhang_deg)) + 1e-9
    on_bed = mesh.vertices[mesh.faces][:, :, 2].max(axis=1) < ON_BED_Z_TOL_MM
    return float(mesh.area_faces[steep & ~on_bed].sum())


def check_overhang(items: list[BuiltItem], printing: PrintingRules) -> list[Issue]:
    out = []
    for it in items:
        area = overhang_area(it.print_mesh, printing.max_overhang_deg)
        if area > printing.overhang_area_tolerance_mm2:
            # 휜 터널의 둥근·네모 단면처럼 세워서 출력할 수 없어 서포트가 필요한 경우는 고를 수 있는 대안을 알려 준다
            msg = (f"{it.label_ko}: 휜 터널을 이 단면으로 만들면 지붕 안쪽에 서포트가 필요해요 (오버행 {area:.0f}mm²). "
                   "서포트 없이 출력하려면 끝이 뾰족한 아치나 집 모양 단면을 고르세요."
                   if it.features.extra.get("bent_needs_support") else
                   f"{it.label_ko}: {printing.max_overhang_deg:g}° 를 넘는 오버행 {area:.0f}mm² 가 있어 서포트 없이 출력하기 어렵습니다.")
            out.append(_warn("support_needed", msg, item_index=it.index, details={"overhang_area_mm2": area}))
    return out


def check_build_volume(items: list[BuiltItem], printing: PrintingRules) -> list[Issue]:
    out = []
    bx, by, bz = printing.build_volume_mm
    for it in items:
        ex = it.print_mesh.extents
        # 판 위에서 90° 돌려 놓을 수 있으므로 짧은 변·긴 변끼리 비교
        fits_xy = min(ex[:2]) <= min(bx, by) + 1e-6 and max(ex[:2]) <= max(bx, by) + 1e-6
        if not fits_xy or ex[2] > bz + 1e-6:
            out.append(_warn(
                "exceeds_build_volume",
                f"{it.label_ko}: 출력 크기 {ex[0]:.0f}×{ex[1]:.0f}×{ex[2]:.0f}mm 가 기준 프린터 출력 공간 "
                f"{bx:g}×{by:g}×{bz:g}mm 를 넘습니다.",
                item_index=it.index, details={"extents_mm": [float(e) for e in ex]},
            ))
    return out


def check_enclosure(cage: Cage, size: SizeRules) -> list[Issue]:
    """케이지 바닥이 최소 기준보다 작으면 경고 (긴 변·짧은 변끼리 비교, 설계는 막지 않음)."""
    need_long, need_short = size.enclosure_min_floor_mm
    long_side = max(cage.width_mm, cage.depth_mm)
    short_side = min(cage.width_mm, cage.depth_mm)
    if long_side + 1e-6 < need_long or short_side + 1e-6 < need_short:
        return [_warn(
            "cage_below_recommended",
            f"케이지 바닥 {cage.width_mm:g}×{cage.depth_mm:g}mm 가 {size.display_name} 사육장 최소 기준 "
            f"{need_long:g}×{need_short:g}mm 보다 작습니다. 더 넓은 사육장을 권장합니다.",
            details={"floor_mm": [cage.width_mm, cage.depth_mm], "recommended_mm": [need_long, need_short]},
        )]
    return []


def check_count(count: int, size: SizeRules) -> list[Issue]:
    if count > size.max_recommended_count:
        return [_warn("count_exceeds", f"{count}마리: {size.count_warning_ko}",
                      details={"count": count, "max": size.max_recommended_count})]
    return []


def validate_all(
    items: list[BuiltItem], cage: Cage, size: SizeRules, printing: PrintingRules,
    min_wall_mm: float, count: int = 1, measure_thickness_mesh: bool = True,
) -> list[Issue]:
    issues: list[Issue] = []
    issues += check_count(count, size)
    issues += check_enclosure(cage, size)
    issues += check_mesh(items)
    issues += check_fit(items, cage)
    issues += check_overlap(items)
    issues += check_gaps(items, cage, size)
    issues += check_access(items, cage, size)
    issues += check_openings(items, size, count)
    issues += check_climb(items, size)
    issues += check_wall_thickness(items, min_wall_mm, measure=measure_thickness_mesh)
    issues += check_overhang(items, printing)
    issues += check_build_volume(items, printing)
    return issues
