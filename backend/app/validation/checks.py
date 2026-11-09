"""설계 자동 검증.

모든 기준값은 rules/species.yaml, rules/printing.yaml 에서 온다 (코드 하드코딩 금지).
각 검사 함수는 Issue 목록을 반환한다.

어항 크기 구분(size.aquatic 이 있음)에서는 Cage 가 수조 안쪽(가로·세로)과 물 깊이(바닥재 위 ~ 수면)를 뜻한다.
바닥·부피 기준만 겉 크기로 적혀 있어, 그 둘을 비교할 때는 유리 두께 어림을 더한 겉 크기를 쓴다.
문구에 '케이지' 대신 '수조'를 쓰고, 천장 틈 검사 대신 수조 부피·넘어짐·물속 무게·터널 공기 안내를 더한다.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import trimesh
from shapely.geometry import box

from app.domain import BuiltItem, Cage, access_strip
from app.geometry.mesh import mesh_health
from app.rules.loader import BuoyancyRules, PrintingRules, SizeRules
from app.validation.report import Issue, Severity

OVERLAP_AREA_TOL_MM2 = 1.0  # 수치 오차 허용 (규칙이 아닌 계산 허용오차)
ON_BED_Z_TOL_MM = 0.01


def _err(code: str, msg: str, **kw) -> Issue:
    return Issue(code=code, severity=Severity.error, message_ko=msg, **kw)


def _warn(code: str, msg: str, **kw) -> Issue:
    return Issue(code=code, severity=Severity.warning, message_ko=msg, **kw)


def _info(code: str, msg: str, **kw) -> Issue:
    return Issue(code=code, severity=Severity.info, message_ko=msg, **kw)


def is_aquarium(size: SizeRules) -> bool:
    """어항(물속) 크기 구분인지."""
    return size.aquatic is not None


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


def check_fit(items: list[BuiltItem], cage: Cage, aquarium: bool = False) -> list[Issue]:
    out = []
    for it in items:
        if it.height_mm > cage.height_mm + 1e-6:
            out.append(_err(
                "too_tall",
                f"{it.label_ko}: 높이 {it.height_mm:.0f}mm 가 물 깊이 {cage.height_mm:.0f}mm 보다 높습니다." if aquarium
                else f"{it.label_ko}: 높이 {it.height_mm:.0f}mm 가 케이지 내부 높이 {cage.height_mm:.0f}mm 보다 높습니다.",
                item_index=it.index,
            ))
        if it.placement is None:
            out.append(_err(
                "cannot_place",
                f"{it.label_ko}: 수조 안에 안전하게 놓을 자리가 없습니다. 구조물 수나 크기를 줄여 주세요." if aquarium
                else f"{it.label_ko}: 케이지 안에 안전하게 놓을 자리가 없습니다. 구조물 수나 크기를 줄여 주세요.",
                item_index=it.index,
            ))
            continue
        x0, y0, x1, y1 = it.world_footprint.bounds
        tol = 1e-3
        if x0 < -tol or y0 < -tol or x1 > cage.width_mm + tol or y1 > cage.depth_mm + tol:
            out.append(_err(
                "out_of_cage",
                f"{it.label_ko}: 수조 바닥 밖으로 벗어납니다." if aquarium else f"{it.label_ko}: 케이지 바닥 밖으로 벗어납니다.",
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
    """끼임 틈새: safe_max < 틈 < passable_min 이면 발·몸이 낄 수 있다.

    어항에는 천장 틈 검사가 없다: 구조물 위는 수면까지 물이고, 엔진 높이 제한이 구조물 위 물 깊이를 남긴다."""
    gt = size.gap_trap
    aquarium = is_aquarium(size)
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
                    f"{it.label_ko} 와(과) {name} 수조 벽 사이 틈 {g:.1f}mm 가 끼임 위험 구간({rng})에 있습니다." if aquarium
                    else f"{it.label_ko} 와(과) {name} 벽 사이 틈 {g:.1f}mm 가 끼임 위험 구간({rng})에 있습니다.",
                    item_index=it.index, details={"gap_mm": g, "wall": name},
                ))
    if aquarium:
        return out
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
                wall = "수조 벽" if is_aquarium(size) else "케이지 벽"
                by = wall if blocked_by_wall else ", ".join(o.label_ko for o in blockers)
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
            # 어항 물고기 구분은 혼자여도 관통형(출입구 2개)이 기준이라 마릿수 대신 까닭을 적는다
            msg = (f"{it.label_ko}: 출입구가 {n}개뿐입니다. 물고기는 좁은 곳에서 뒤로 잘 빠져나오지 못해 "
                   f"{need}개 이상(앞뒤로 뚫린 관통형)이어야 합니다." if is_aquarium(size)
                   else f"{it.label_ko}: 출입구가 {n}개뿐입니다. {count}마리가 함께 지내면 서로 피할 수 있도록 "
                        f"{need}개 이상이어야 합니다.")
            out.append(_err(
                "too_few_entrances", msg,
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
    """오르기 기준 (기준 값이 없는 크기 구분(어항)은 그 항목을 건너뛴다)."""
    out = []
    for it in items:
        f = it.features
        if (f.climb_height_mm is not None and size.max_climb_height_mm is not None
                and f.climb_height_mm > size.max_climb_height_mm + 1e-6):
            out.append(_err("climb_too_high",
                            f"{it.label_ko}: 높이 {f.climb_height_mm:g}mm 가 낙상 안전 기준 {size.max_climb_height_mm:g}mm 를 넘습니다.",
                            item_index=it.index))
        if (f.slope_deg is not None and size.max_ramp_angle_deg is not None
                and f.slope_deg > size.max_ramp_angle_deg + 1e-6):
            out.append(_err("slope_too_steep",
                            f"{it.label_ko}: 경사 {f.slope_deg:g}° 가 기준 {size.max_ramp_angle_deg:g}° 보다 가파릅니다.",
                            item_index=it.index))
        if (f.step_height_mm is not None and size.max_step_height_mm is not None
                and f.step_height_mm > size.max_step_height_mm + 1e-6):
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


def check_wall_thickness(items: list[BuiltItem], min_wall_mm: float, measure: bool = True,
                         aquarium: bool = False) -> list[Issue]:
    out = []
    for it in items:
        designed = it.features.min_wall_thickness_mm
        if designed < min_wall_mm - 1e-6:
            out.append(_err(
                "wall_too_thin",
                f"{it.label_ko}: 벽 두께 {designed:g}mm 가 최소 기준 {min_wall_mm:g}mm 보다 얇습니다 (물속 내구성·출력 기준)."
                if aquarium else
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
            out.append(_warn(
                "support_needed",
                f"{it.label_ko}: {printing.max_overhang_deg:g}° 를 넘는 오버행 {area:.0f}mm² 가 있어 서포트 없이 출력하기 어렵습니다.",
                item_index=it.index, details={"overhang_area_mm2": area},
            ))
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
    """케이지(수조) 바닥이 최소 기준보다 작으면 경고 (긴 변·짧은 변끼리 비교, 설계는 막지 않음). 기준이 없으면 건너뛴다.
    어항: 기준('60cm' 등급 60×30cm)은 수조 겉 크기라, 입력한 안쪽 가로·세로에 유리 두께 어림을 더해 비교한다."""
    if size.enclosure_min_floor_mm is None:
        return []
    need_long, need_short = size.enclosure_min_floor_mm
    w, d = tank_outer_floor_mm(cage, size) if is_aquarium(size) else (cage.width_mm, cage.depth_mm)
    long_side = max(w, d)
    short_side = min(w, d)
    if long_side + 1e-6 < need_long or short_side + 1e-6 < need_short:
        details: dict = {"floor_mm": [cage.width_mm, cage.depth_mm], "recommended_mm": [need_long, need_short]}
        if is_aquarium(size):
            g = size.aquatic.glass_thickness_assumed_mm
            msg = (f"수조 겉 크기가 약 {w:g}×{d:g}mm(안쪽 {cage.width_mm:g}×{cage.depth_mm:g}mm에 유리 두께 {g:g}mm를 "
                   f"더해 어림)로 {size.display_name} 최소 기준 {need_long:g}×{need_short:g}mm 보다 작습니다. "
                   "더 큰 수조를 권장합니다.")
            details |= {"outer_floor_mm": [w, d], "glass_mm": g}
        else:
            msg = (f"케이지 바닥 {cage.width_mm:g}×{cage.depth_mm:g}mm 가 {size.display_name} 사육장 최소 기준 "
                   f"{need_long:g}×{need_short:g}mm 보다 작습니다. 더 넓은 사육장을 권장합니다.")
        return [_warn("cage_below_recommended", msg, details=details)]
    return []


def tank_outer_floor_mm(cage: Cage, size: SizeRules) -> tuple[float, float]:
    """어항: 수조 겉 가로·세로 어림 (mm) = 입력한 안쪽 치수 + 유리 2장.
    바닥·부피 기준은 겉 크기로 적혀 있고, 입력(과 배치·틈 검사)은 안쪽 치수라 비교할 때만 바꾼다."""
    aq = size.aquatic
    assert aq is not None
    g = aq.glass_thickness_assumed_mm
    return cage.width_mm + 2 * g, cage.depth_mm + 2 * g


def tank_volume_l(cage: Cage, size: SizeRules) -> float:
    """수조 부피 어림 (L), 겉 크기 기준: (안쪽 가로·세로 + 유리 2장) × (물 깊이 + 바닥재 어림 두께 + 수면 위 여유 + 바닥 유리).
    표준 부피(예: 60×30×30cm = 54L)는 겉 치수로 계산한 총부피인데, 입력은 수조 안쪽 가로·세로와
    바닥재 위 ~ 수면 물 깊이라 둘을 더한다."""
    aq = size.aquatic
    assert aq is not None
    w, d = tank_outer_floor_mm(cage, size)
    h = cage.height_mm + aq.substrate_depth_assumed_mm + aq.air_gap_mm + aq.glass_thickness_assumed_mm
    return w * d * h / 1e6


def check_tank_volume(cage: Cage, size: SizeRules, count: int = 1) -> list[Issue]:
    """어항: 수조 부피가 최소 부피·마리당 부피 × 마릿수보다 작으면 경고 (설계는 막지 않음).
    최소 부피는 하한일 뿐이라, 규칙 파일에 종별 권장 부피 안내(volume_note_ko)가 있고 수조가 그 기준보다 작으면 참고로 덧붙인다."""
    aq = size.aquatic
    if aq is None:
        return []
    volume = tank_volume_l(cage, size)
    out: list[Issue] = []
    per_animal = aq.volume_l_per_animal
    by_count = count * per_animal if per_animal is not None else 0.0
    need = max(aq.min_volume_l, by_count)
    if volume < need - 1e-9:
        s, a, g = aq.substrate_depth_assumed_mm, aq.air_gap_mm, aq.glass_thickness_assumed_mm
        # 부피는 내려서 보인다: 반올림하면 53.8L 가 '약 54L … 최소 54L 보다 작습니다'처럼 스스로 어긋나 보인다
        shown = math.floor(volume)
        # 부피 기준이 겉 크기라 어림 방법을 함께 적는다 (안쪽 치수 + 유리, 물 깊이 + 바닥재·윗여유·바닥 유리)
        if by_count > aq.min_volume_l:
            msg = (f"수조 부피가 약 {shown}L(안쪽 치수에 유리 두께 {g:g}mm, 물 깊이에 바닥재 {s:g}mm·윗여유 {a:g}mm를 "
                   f"더한 겉 크기로 어림)로 {count}마리 기준 권장 최소 {need:g}L 보다 작습니다.")
        else:
            # 최소 부피는 법령·감정서의 하한이라 '권장'이 아니라 '최소 기준'이라고 쓴다 (종별 권장치는 아래 안내)
            msg = (f"수조 부피가 약 {shown}L(안쪽 치수에 유리 두께 {g:g}mm, 물 깊이에 바닥재 {s:g}mm·윗여유 {a:g}mm를 "
                   f"더한 겉 크기로 어림)로 {size.display_name} 최소 기준 {need:g}L 보다 작습니다.")
        out.append(_warn("tank_volume_below_recommended", msg,
                         details={"volume_l": volume, "need_l": need, "per_animal_l": per_animal}))
    if aq.volume_note_ko is not None and aq.volume_note_below_l is not None and volume < aq.volume_note_below_l - 1e-9:
        out.append(_info("tank_volume_species_note", aq.volume_note_ko,
                         details={"volume_l": volume, "note_below_l": aq.volume_note_below_l}))
    return out


def check_count(count: int, size: SizeRules) -> list[Issue]:
    """권장 마릿수 (최대: 단독 사육 종, 최소: 무리 짓는 종). 기준이 없으면 건너뛴다."""
    if size.max_recommended_count is not None and count > size.max_recommended_count:
        return [_warn("count_exceeds", f"{count}마리: {size.count_warning_ko}",
                      details={"count": count, "max": size.max_recommended_count})]
    if size.min_recommended_count is not None and count < size.min_recommended_count:
        return [_warn("count_below_recommended", f"{count}마리: {size.min_count_warning_ko}",
                      details={"count": count, "min": size.min_recommended_count})]
    return []


# ── 어항: 넘어짐 / 물속 무게 / 터널 속 공기 ───────────────────


def check_tip_over(items: list[BuiltItem], size: SizeRules) -> list[Issue]:
    """어항: 높이 ÷ 바닥 짧은 변이 기준을 넘으면 물살·물고기에 넘어지기 쉽다 (경고).
    출력물은 물속에서 아주 가벼워(마른 무게의 약 20%) 케이지보다 쉽게 넘어진다."""
    aq = size.aquatic
    if aq is None:
        return []
    r = aq.max_height_to_base_ratio
    out = []
    for it in items:
        x0, y0, x1, y1 = it.footprint.bounds
        base = min(x1 - x0, y1 - y0)
        h = it.height_mm
        if base <= 0 or h / base > r + 1e-9:
            # 높이는 올리고 바닥은 내려서 보인다: 반올림하면 90.4/60.2 가 '90mm … 60mm 의 1.5배를 넘어'처럼
            # 기준과 같은 비율로 보일 수 있다 (올린 높이 ÷ 내린 바닥은 언제나 실제 비율 이상)
            h_shown, base_shown = math.ceil(h - 1e-9), math.floor(base + 1e-9)
            out.append(_warn(
                "tip_over_risk",
                f"{it.label_ko}: 높이 {h_shown}mm 가 바닥 짧은 변 {base_shown}mm 의 {r:g}배를 넘어 물속에서 넘어지기 쉽습니다. "
                "바닥을 넓히거나 높이를 낮춰 주세요.",
                item_index=it.index,
                details={"height_mm": h, "base_mm": base, "ratio": h / base if base > 0 else None, "max_ratio": r},
            ))
    return out


def check_underwater_weight(items: list[BuiltItem], size: SizeRules, buoyancy: BuoyancyRules | None) -> list[Issue]:
    """어항: 출력물 전체의 물속 무게(무게 − 부력)를 알려 준다 (채움 100% 가정, 안내)."""
    if size.aquatic is None or buoyancy is None:
        return []
    solid = [it for it in items if it.mesh.is_watertight]
    if not solid:
        return []
    rho_m, rho_w = buoyancy.material_density_g_cm3, buoyancy.water_density_g_cm3
    per_item = [{"index": it.index, "grams": abs(float(it.mesh.volume)) / 1000 * (rho_m - rho_w)} for it in solid]
    total = sum(p["grams"] for p in per_item)
    pct = (rho_m - rho_w) / rho_m * 100
    return [_info(
        "underwater_weight",
        f"출력물의 물속 무게는 모두 합쳐 약 {total:.0f}g 이에요(채움 100% 기준, 마른 무게의 약 {pct:.0f}%). "
        "가벼워서 물살이나 물고기에 밀릴 수 있으니 설치 뒤 하루 동안 뜨거나 밀리지 않는지 지켜봐 주세요.",
        details={"total_g": total, "percent_of_dry": pct, "items": per_item,
                 "material_density_g_cm3": rho_m, "water_density_g_cm3": rho_w},
    )]


def check_tunnel_air(items: list[BuiltItem], size: SizeRules) -> list[Issue]:
    """어항: 수평 터널은 꼭대기를 따라 공기 띠가 남을 수 있어 설치 안내를 띄운다 (형상으로 막지 않음)."""
    if size.aquatic is None:
        return []
    return [_info(
        "tunnel_trapped_air",
        f"{it.label_ko}: 수평으로 놓으면 꼭대기를 따라 공기가 남아 뜰 수 있어요. 물속에서 한쪽 끝을 들어 공기를 뺀 뒤 놓아 주세요.",
        item_index=it.index,
    ) for it in items if it.key == "tunnel"]


def validate_all(
    items: list[BuiltItem], cage: Cage, size: SizeRules, printing: PrintingRules,
    min_wall_mm: float, count: int = 1, measure_thickness_mesh: bool = True,
    buoyancy: BuoyancyRules | None = None,
) -> list[Issue]:
    aquarium = is_aquarium(size)
    issues: list[Issue] = []
    issues += check_count(count, size)
    issues += check_enclosure(cage, size)
    issues += check_tank_volume(cage, size, count)
    issues += check_mesh(items)
    issues += check_fit(items, cage, aquarium=aquarium)
    issues += check_overlap(items)
    issues += check_gaps(items, cage, size)
    issues += check_access(items, cage, size)
    issues += check_openings(items, size, count)
    issues += check_climb(items, size)
    issues += check_wall_thickness(items, min_wall_mm, measure=measure_thickness_mesh, aquarium=aquarium)
    issues += check_overhang(items, printing)
    issues += check_build_volume(items, printing)
    issues += check_tip_over(items, size)
    issues += check_underwater_weight(items, size, buoyancy)
    issues += check_tunnel_air(items, size)
    return issues
