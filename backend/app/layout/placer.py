"""결정적 배치기.

LLM 은 좌표를 정하지 않고 zone(영역)·group(함께 몰기)·rotation 힌트만 준다.
배치기는 벽과 이미 놓인 구조물의 모서리에 스냅되는 후보 위치를 만든다.
그중 안전 조건을 만족하는 위치에서 zone 목표점에 가장 가까운 곳을 고른다.

안전 조건:
  - 케이지 안
  - 다른 구조물과 겹치지 않음
  - 벽·구조물 사이 틈이 끼임 구간(safe_max < 틈 < passable_min)에 들지 않음
  - 출입구 앞(access side)은 passable_min 깊이만큼 비어 있음
후보는 밀착(0) 또는 passable_min 간격 위치로 만들므로 틈은 자연스럽게 안전 구간에 놓인다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain import BuiltItem, Cage, Placement, Rect, access_strip
from app.rules.loader import GapTrapRule

ROTATIONS = (0, 90, 180, 270)
EPS = 1e-6


@dataclass(frozen=True)
class _Placed:
    rect: Rect
    strips: tuple[Rect, ...]
    group: str | None


def zone_target(zone: str, cage: Cage, w: float, d: float) -> tuple[float, float] | None:
    """zone 에 해당하는 목표 중심점. auto 는 목표 없음."""
    W, D = cage.width_mm, cage.depth_mm
    left, right, cx = w / 2, W - w / 2, W / 2
    front, back, cy = d / 2, D - d / 2, D / 2
    return {
        "left": (left, cy), "right": (right, cy),
        "front": (cx, front), "back": (cx, back), "center": (cx, cy),
        "front_left": (left, front), "front_right": (right, front),
        "back_left": (left, back), "back_right": (right, back),
    }.get(zone)


def _inside(r: Rect, cage: Cage) -> bool:
    return r.x0 >= -EPS and r.y0 >= -EPS and r.x1 <= cage.width_mm + EPS and r.y1 <= cage.depth_mm + EPS


def wall_gaps(r: Rect, cage: Cage) -> list[float]:
    return [r.x0, cage.width_mm - r.x1, r.y0, cage.depth_mm - r.y1]


def _valid(
    rect: Rect, strips: list[Rect], placed: list[_Placed], cage: Cage, gap: GapTrapRule
) -> bool:
    if not _inside(rect, cage):
        return False
    if any(gap.is_trap(g) for g in wall_gaps(rect, cage)):
        return False
    for s in strips:
        if not _inside(s, cage):
            return False
    for o in placed:
        if rect.intersects(o.rect):
            return False
        if gap.is_trap(rect.distance(o.rect)):
            return False
        if any(rect.intersects(s) for s in o.strips):
            return False
        if any(s.intersects(o.rect) for s in strips):
            return False
    return True


def _axis_candidates(size: float, limit: float, P: float, target: float | None,
                     others: list[tuple[float, float]]) -> list[float]:
    c = {0.0, limit - size, P, limit - size - P}
    if target is not None:
        c.add(target - size / 2)
    for lo, hi in others:
        c.update({hi, hi + P, lo - size, lo - size - P, lo, hi - size})
    return sorted(v for v in c if -EPS <= v <= limit - size + EPS)


def _score(item: BuiltItem, rect: Rect, rot: int, placed: list[_Placed], cage: Cage) -> float:
    hint = item.hint
    w, d = rect.w, rect.h
    score = 0.0
    target = zone_target(hint.zone, cage, w, d)
    if target is not None:
        score += math.hypot(rect.cx - target[0], rect.cy - target[1])
    if hint.group:
        mates = [o for o in placed if o.group == hint.group]
        score += 2.0 * sum(rect.distance(o.rect) for o in mates)
    if target is None and not hint.group:
        # 특별한 요청이 없으면 벽에 붙여 가운데 공간을 넓게 남긴다
        score += min(wall_gaps(rect, cage))
    # 출입구가 케이지 중앙을 향하도록 약하게 선호
    for dx, dy in item.access_directions(rot):
        to_center = (cage.width_mm / 2 - rect.cx, cage.depth_mm / 2 - rect.cy)
        score -= 0.01 * (dx * to_center[0] + dy * to_center[1])
    return score


def candidates(item: BuiltItem, placed: list[_Placed], cage: Cage, gap: GapTrapRule,
               limit: int | None = None) -> list[tuple[float, int, float, float]]:
    """유효한 후보 (점수, 회전, x0, y0) 를 점수 순으로. 같은 사각형은 가장 좋은 회전만 남긴다."""
    P = gap.passable_min_mm
    rotations = (item.hint.rotation,) if item.hint.rotation is not None else ROTATIONS
    found: dict[tuple[float, float, float, float], tuple[float, int, float, float]] = {}
    for rot in rotations:
        w, d = item.size_xy(rot)
        if w > cage.width_mm + EPS or d > cage.depth_mm + EPS:
            continue
        target = zone_target(item.hint.zone, cage, w, d)
        xs = _axis_candidates(w, cage.width_mm, P, target[0] if target else None,
                              [(o.rect.x0, o.rect.x1) for o in placed])
        ys = _axis_candidates(d, cage.depth_mm, P, target[1] if target else None,
                              [(o.rect.y0, o.rect.y1) for o in placed])
        dirs = item.access_directions(rot)
        for x0 in xs:
            for y0 in ys:
                rect = Rect(x0, y0, x0 + w, y0 + d)
                strips = [access_strip(rect, dv, P) for dv in dirs]
                if not _valid(rect, strips, placed, cage, gap):
                    continue
                cand = (round(_score(item, rect, rot, placed, cage), 6), rot, round(x0, 6), round(y0, 6))
                rkey = (round(rect.x0, 6), round(rect.y0, 6), round(rect.x1, 6), round(rect.y1, 6))
                if rkey not in found or cand < found[rkey]:
                    found[rkey] = cand
    out = sorted(found.values())
    return out[:limit] if limit else out


def _to_placement(item: BuiltItem, cand: tuple[float, int, float, float]) -> Placement:
    _, rot, x0, y0 = cand
    w, d = item.size_xy(rot)
    return Placement(x_mm=x0 + w / 2, y_mm=y0 + d / 2, rotation_deg=rot)  # type: ignore[arg-type]


def placement_order(items: list[BuiltItem]) -> list[BuiltItem]:
    """zone 지정 항목 → group 항목 → 나머지 순, 같은 순위에서는 큰 것부터."""

    def key(it: BuiltItem):
        w, d = it.size_xy(0)
        has_zone = it.hint.zone != "auto"
        return (not has_zone, it.hint.group is None, -w * d, it.index)

    return sorted(items, key=key)


def _placed_at(item: BuiltItem, placement: Placement, P: float) -> _Placed:
    """placement 에 놓인 item 의 사각형·출입 공간. item.placement 는 읽지도 바꾸지도 않는다."""
    # world_rect 와 같은 계산(rect_at). 후보의 Rect(x0, y0, x0+w, y0+d) 를 재사용하면 1 ulp 달라질 수 있다.
    rect = item.rect_at(placement.x_mm, placement.y_mm, placement.rotation_deg)
    strips = tuple(access_strip(rect, dv, P) for dv in item.access_directions(placement.rotation_deg))
    return _Placed(rect, strips, item.hint.group)


BEAM_WIDTH = 6
UNPLACED_PENALTY = 1e6


def place_all(items: list[BuiltItem], cage: Cage, gap: GapTrapRule, beam: int = BEAM_WIDTH) -> list[BuiltItem]:
    """모든 항목을 배치한다(제자리 갱신). 배치하지 못한 항목 목록을 반환한다.

    탐욕 배치는 앞 항목의 위치 때문에 뒤 항목이 붙을 자리를 잃을 수 있다
    (예: 벽 가운데 놓인 은신처 옆 남은 틈이 끼임 구간). 그래서 항목마다 상위 후보 몇 개를 유지하는
    빔 탐색으로 전체 점수(배치 실패는 큰 벌점)가 가장 낮은 조합을 고른다. 결과는 결정적이다.
    """
    P = gap.passable_min_mm
    # 상태: (누적 점수, 놓인 항목들, {index: Placement | None})
    states: list[tuple[float, list[_Placed], dict[int, Placement | None]]] = [(0.0, [], {})]
    for item in placement_order(items):
        expanded = []
        for total, placed, plc in states:
            cands = candidates(item, placed, cage, gap, limit=beam)
            if not cands:
                expanded.append((total + UNPLACED_PENALTY, placed, {**plc, item.index: None}))
                continue
            for cand in cands:
                placement = _to_placement(item, cand)
                expanded.append((total + cand[0], placed + [_placed_at(item, placement, P)], {**plc, item.index: placement}))
        expanded.sort(key=lambda s: (round(s[0], 6), _state_key(s[2])))
        states = expanded[:beam]

    _, _, best = states[0]
    failed = []
    for item in items:
        item.placement = best.get(item.index)
        if item.placement is None:
            failed.append(item)
    return failed


def _state_key(plc: dict[int, Placement | None]) -> tuple:
    return tuple(
        (i, (p.rotation_deg, round(p.x_mm, 6), round(p.y_mm, 6)) if p else (-1, 0.0, 0.0))
        for i, p in sorted(plc.items())
    )
