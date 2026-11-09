"""개구부 부품: 출입구, 창, 터널 연결부.

모두 뾰족 아치(출입구·연결부) 또는 렌즈형(창) 구멍이라 어느 출력 자세에서도 서포트가 필요 없다.
같은 면에는 출입구·연결부가 하나만 올 수 있고(겹침·벽 강도), 창은 면마다 하나씩 위쪽 띠에 낸다.
"""

from __future__ import annotations

from build123d import Part
from pydantic import Field, field_validator

from app.templates.base import Opening, ParamConstraint, RuleContext, Side, TemplateParams
from app.templates.parts.common import (
    CUT,
    SIDE_KO,
    Shell,
    arch_height,
    lens,
    lens_height,
    pointed_arch,
    through_wall,
)


def _unique_sides(v: list[Side]) -> list[Side]:
    if len(set(v)) != len(v):
        raise ValueError("같은 면에 출입구·연결부를 두 개 낼 수 없습니다")
    return v


class DoorsPart(TemplateParams):
    sides: list[Side] = Field(
        ["front"], min_length=1, max_length=2,
        description="출입구를 낼 면 (1~2개, 서로 다른 면). front=앞, back=뒤, left=왼쪽, right=오른쪽. "
                    "여러 마리를 함께 키우면 마주 보는 두 면에 내서 막다른 곳이 없게 한다",
    )
    width_mm: float = Field(60, ge=25, le=150, description="뾰족 아치형 출입구 폭 mm. 종별 최소 출입구 폭 이상")

    _unique = field_validator("sides")(_unique_sides)


class WindowsPart(TemplateParams):
    count: int = Field(0, ge=0, le=4, description="창 개수 (0~4, 앞·뒤·왼쪽·오른쪽 순으로 면마다 하나씩 위쪽에 낸다)")
    diameter_mm: float = Field(4, ge=2, le=10, description="창 지름 mm. 발이 끼지 않도록 종별 안전 틈새 이하")


class PortsPart(TemplateParams):
    sides: list[Side] = Field(
        [], max_length=2,
        description="터널 연결부(바깥 플랜지가 있는 아치)를 낼 면 (0~2개, 출입구와 다른 면). 터널 항목을 같은 group 으로 붙여 놓는다",
    )
    diameter_mm: float = Field(60, ge=35, le=130, description="연결부 아치 폭 mm. 종별 터널 최소 내경 이상")
    flange_mm: float = Field(3, ge=2, le=4, description="바깥 플랜지가 벽에서 튀어나오는 길이 mm. 종별 안전 틈새 이하")

    _unique = field_validator("sides")(_unique_sides)


WINDOW_SIDES: tuple[Side, ...] = ("front", "back", "left", "right")


def window_sides(w: WindowsPart) -> tuple[Side, ...]:
    return WINDOW_SIDES[: w.count]


# ── 제약 ───────────────────────────────────────────────────


def ground_opening_top(shell: Shell, side: Side, doors: DoorsPart, ports: PortsPart) -> float:
    """측면의 1층 개구부(출입구·연결부) 꼭대기 높이 (없으면 0). 1층 개구부는 바닥 Z=0 부터 뚫는다
    (바닥판이 있으면 그 가장자리가 문턱이 된다. 본체를 뒤집어 출력할 때 문턱 윗면이 오버행이 되지 않도록)."""
    top = 0.0
    if side in doors.sides:
        top = max(top, arch_height(doors.width_mm))
    if side in ports.sides:
        top = max(top, arch_height(ports.diameter_mm))
    return top


def opening_constraints(doors: DoorsPart, windows: WindowsPart, ports: PortsPart, ctx: RuleContext,
                        inset: float, t: float) -> list[ParamConstraint]:
    """종 규칙(출입구·연결부 최소 폭, 창·플랜지 최대) + 면 폭(개구부 양옆에 벽이 남도록)."""
    s = ctx.size
    out = [
        ParamConstraint(
            "doors.width_mm", min=s.entrance_min_diameter_mm, source="species",
            reason_ko=f"{s.display_name} 출입구는 최소 {s.entrance_min_diameter_mm:g}mm 이상이어야 합니다",
        ),
        ParamConstraint(
            "windows.diameter_mm", max=s.gap_trap.safe_max_mm, source="species",
            reason_ko=f"창 지름이 {s.gap_trap.safe_max_mm:g}mm 를 넘으면 발이 낄 수 있습니다",
        ),
    ]
    if ports.sides:
        out += [
            ParamConstraint(
                "ports.diameter_mm", min=s.tunnel_min_inner_diameter_mm, source="species",
                reason_ko=f"{s.display_name} 터널 연결부는 터널 최소 내경 {s.tunnel_min_inner_diameter_mm:g}mm 이상이어야 합니다",
            ),
            ParamConstraint(
                "ports.flange_mm", max=s.gap_trap.safe_max_mm, source="species",
                reason_ko=f"연결부 플랜지가 {s.gap_trap.safe_max_mm:g}mm 보다 튀어나오면 터널과의 틈에 발이 낄 수 있습니다",
            ),
        ]
    # 면 폭: 개구부 양옆에 벽이 벽 두께의 1.5배씩 남도록 (은신처와 같은 기준)
    for field, sides in (("width_mm", ("front", "back")), ("depth_mm", ("left", "right"))):
        need = 0.0
        for side in sides:
            if side in doors.sides:
                need = max(need, max(doors.width_mm, s.entrance_min_diameter_mm))
            if side in ports.sides:
                need = max(need, max(ports.diameter_mm, s.tunnel_min_inner_diameter_mm) + 2 * t)  # 플랜지 고리 포함
        if need > 0:
            out.append(ParamConstraint(
                field, min=need + 4 * t + 2 * inset,
                reason_ko="출입구·연결부 양옆에 벽이 남도록 그 면의 폭이 개구부보다 충분히 커야 합니다",
            ))
    return out


# ── 형상 ───────────────────────────────────────────────────


def cut_openings(body: Part, shell: Shell, doors: DoorsPart, windows: WindowsPart, ports: PortsPart,
                 window_bottom: float, upper_door: tuple[Side, float, float] | None = None) -> Part:
    """출입구·창·연결부를 벽에서 뚫고 연결부 플랜지를 덧붙인다.

    window_bottom: 창의 아래 끝 높이 (위쪽 띠). upper_door: (면, 바닥 높이, 폭) — 2층 바깥 램프용 출입구."""
    through = shell.t + 2 * CUT
    for side in doors.sides:
        body = body - through_wall(pointed_arch(doors.width_mm / 2, -CUT), side, shell, through)
    if upper_door is not None:
        side, z0, width = upper_door
        body = body - through_wall(pointed_arch(width / 2, z0), side, shell, through)
    r_w = windows.diameter_mm / 2
    for side in window_sides(windows):
        body = body - through_wall(lens(r_w, window_bottom + lens_height(windows.diameter_mm) / 2), side, shell, through)
    for side in ports.sides:
        r = ports.diameter_mm / 2
        body = body - through_wall(pointed_arch(r, -CUT), side, shell, through)
        # 바깥 플랜지: 아치 둘레 벽 두께만큼의 고리를 벽 바깥면에서 flange_mm 튀어나오게 (벽 안으로 조금 겹쳐 붙인다)
        ring = pointed_arch(r + shell.t, 0.0) - pointed_arch(r, -CUT)
        depth = ports.flange_mm + 0.5
        body = body + through_wall(ring, side, shell, depth, offset=shell.t / 2 + depth / 2 - 0.5)
    return body


# ── Features 조각 ───────────────────────────────────────────


def opening_features(doors: DoorsPart, windows: WindowsPart, ports: PortsPart,
                     upper_door_side: Side | None) -> list[Opening]:
    out = []
    for side in doors.sides:
        label = f"{SIDE_KO[side]} 출입구" if len(doors.sides) > 1 or ports.sides or upper_door_side else "출입구"
        out.append(Opening("passage", doors.width_mm, label, rule_key="entrance_min_diameter_mm"))
    if upper_door_side is not None:
        out.append(Opening("passage", doors.width_mm, "2층 출입구", rule_key="entrance_min_diameter_mm"))
    for side in ports.sides:
        out.append(Opening("passage", ports.diameter_mm, f"{SIDE_KO[side]} 터널 연결부", rule_key="tunnel_min_inner_diameter_mm"))
    if windows.count > 0:
        out.append(Opening("vent", windows.diameter_mm, "창"))
    return out


def access_sides(doors: DoorsPart, ports: PortsPart) -> tuple[Side, ...]:
    return tuple(dict.fromkeys([*doors.sides, *ports.sides]))

