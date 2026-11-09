"""조립형 집 템플릿.

부품(backend/app/templates/parts/)을 LLM 이 고르고 치수를 정하면 템플릿이 조립해 하나의 구조물로 만든다.
  - 벽(walls)·바닥판(floor)·지붕(roof: flat | pitched | rounded)·층(floors: 1 | 2, internal_ramp | external_ramp)
  - 출입구(doors: 1~2개, 면)·창(windows: 0~4)·터널 연결부(ports: 0~2개, 바깥 플랜지)
좌표: 외형 가로 W(X)·세로 D(Y)·높이 H(Z, 지붕 포함), 바닥 Z=0, XY 중심 원점. 앞 = −Y.

출력 파트 (한 덩어리로 서포트 없이 출력되지 않는 조합은 2~3개로 나눠 끼워 맞춘다, 결합부는 설계상 밀착):
  - 본체: 벽(+ 1층 평 지붕이면 지붕까지, 바로 세워 출력하는 경우 바닥판·선반·내부 경사로·착지판까지)
  - 지붕(경사·둥근 지붕, 또는 2층 평 지붕): 벽 바깥을 감싸는 스커트가 달린 뚜껑
  - 층판(2층): 선반 위에 얹는 판
  - 바닥판(1층 평 지붕 + 바닥판): 본체를 뒤집어 출력하므로 따로
출력 자세: 1층 평 지붕 본체는 은신처처럼 뒤집고(지붕이 베드), 그 밖의 본체는 바로 세운다(출입구·창은 뾰족 아치라
어느 자세든 서포트가 필요 없고, 선반 아랫면은 50° 모따기). 평 지붕 뚜껑은 뒤집고, 경사·둥근 지붕 뚜껑은 스커트를
베드에 대고 세운다(경사는 45° 보다 가파르게, 둥근 지붕은 뾰족 아치).
"""

from __future__ import annotations

import math

import numpy as np
from build123d import Part
from pydantic import Field, model_validator

from app.templates.base import (
    DecorZone,
    Features,
    ParamConstraint,
    PrintPart,
    RuleContext,
    Side,
    Template,
    TemplateParams,
)
from app.templates.parts import levels, openings, shell
from app.templates.parts.common import MARGIN_MM, SIDE_KO, Shell, arch_height, lens_height
from app.templates.parts.levels import FloorsPart
from app.templates.parts.openings import DoorsPart, PortsPart, WindowsPart
from app.templates.parts.shell import SKIRT_MM, FloorPart, RoofPart, WallPart

_INVERTED = np.diag([1.0, -1.0, -1.0])
_UPRIGHT = np.eye(3)
WIDTH_MAX_MM = 350.0
DECOR_KEEPOUT_MM = 4.0   # 장식이 개구부·결합부·모서리에서 떨어지는 거리
DECOR_MAX_DEPTH_MM = 1.0  # 장식 홈 깊이·돌기 높이 상한


class HouseParams(TemplateParams):
    width_mm: float = Field(160, ge=80, le=WIDTH_MAX_MM, description="외형 가로(X) mm")
    depth_mm: float = Field(130, ge=80, le=350, description="외형 세로(Y) mm")
    height_mm: float = Field(110, ge=60, le=300, description="외형 높이(Z) mm, 지붕 포함")
    walls: WallPart = Field(default_factory=WallPart, description="벽")
    floor: FloorPart = Field(default_factory=FloorPart, description="바닥판")
    roof: RoofPart = Field(default_factory=RoofPart, description="지붕")
    floors: FloorsPart = Field(default_factory=FloorsPart, description="층 (2층이면 층판과 오르는 수단)")
    doors: DoorsPart = Field(default_factory=DoorsPart, description="출입구")
    windows: WindowsPart = Field(default_factory=WindowsPart, description="창")
    ports: PortsPart = Field(default_factory=PortsPart, description="터널 연결부")

    @model_validator(mode="after")
    def _sides_do_not_collide(self) -> "HouseParams":
        clash = set(self.doors.sides) & set(self.ports.sides)
        if clash:
            raise ValueError(f"{SIDE_KO[clash.pop()]} 면에 출입구와 터널 연결부를 함께 낼 수 없습니다")
        if self.floors.count == 2 and self.floors.climb == "external_ramp":
            if self.floors.exit_side in self.doors.sides or self.floors.exit_side in self.ports.sides:
                raise ValueError("바깥 램프가 닿는 2층 출입구 면에는 1층 출입구·연결부를 낼 수 없습니다 (램프가 앞을 막는다)")
        return self


# ── 파생 치수 ───────────────────────────────────────────────


def is_cap(p: HouseParams) -> bool:
    return shell.roof_is_cap(p.roof, p.floors.count)


def inset(p: HouseParams) -> float:
    """벽 고리가 외형보다 안쪽으로 들어간 양 (지붕 뚜껑의 스커트 두께)."""
    return p.walls.thickness_mm if is_cap(p) else 0.0


def roof_rise(p: HouseParams) -> float:
    return shell.roof_rise(p.roof, p.floors.count, p.depth_mm, p.walls.thickness_mm)


def eave_height(p: HouseParams) -> float:
    """처마(벽 꼭대기 중 가장 낮은 곳) 높이."""
    return p.height_mm - roof_rise(p)


def z_floor(p: HouseParams) -> float:
    return p.floor.thickness_mm if p.floor.enabled else 0.0


def top_clearance(p: HouseParams) -> float:
    """벽 꼭대기 아래에서 개구부가 피해야 하는 띠: 지붕판 두께(한 덩어리) 또는 뚜껑 스커트 높이, 그리고 여유."""
    return (SKIRT_MM if is_cap(p) else p.walls.thickness_mm) + MARGIN_MM


def make_shell(p: HouseParams) -> Shell:
    i = inset(p)
    return Shell(wx=p.width_mm - 2 * i, wy=p.depth_mm - 2 * i, t=p.walls.thickness_mm, z_floor=z_floor(p),
                 wall_top=eave_height(p))


def body_inverted(p: HouseParams) -> bool:
    """본체를 뒤집어 출력하는지 (1층 평 지붕: 지붕이 본체에 붙어 있다)."""
    return not is_cap(p)


def upper_door(p: HouseParams) -> tuple[Side, float, float] | None:
    if p.floors.count == 2 and p.floors.climb == "external_ramp":
        return (p.floors.exit_side, p.floors.level_height_mm, p.doors.width_mm)
    return None


def window_bottom(p: HouseParams) -> float:
    """창 아래 끝: 벽 꼭대기 아래 띠."""
    return eave_height(p) - top_clearance(p) - lens_height(p.windows.diameter_mm)


def _occupied_top(p: HouseParams, sh: Shell, side: Side) -> float:
    """측면에서 창 아래에 있어야 하는 개구부의 꼭대기 (1층 출입구·연결부, 2층 출입구)."""
    top = openings.ground_opening_top(sh, side, p.doors, p.ports)
    ud = upper_door(p)
    if ud is not None and ud[0] == side:
        top = max(top, ud[1] + arch_height(ud[2]))
    return top


class HouseTemplate(Template):
    key = "house"
    display_name_ko = "집"
    description_ko = (
        "부품을 골라 조립하는 집. 벽·바닥판·지붕(평/경사/둥근)·층(1~2층, 내부 경사로 또는 바깥 램프)·출입구(1~2면)·창·"
        "터널 연결부를 중첩 파라미터로 정한다. 2층·경사 지붕·터널 연결·창 요청은 이 템플릿으로 표현한다. "
        "지붕이나 층판이 따로 출력되는 조합은 2~3개 파트로 나뉜다."
    )
    Params = HouseParams
    height_field = "height_mm"
    size_fields = ("width_mm", "depth_mm", "height_mm")

    def default_params(self, ctx: RuleContext | None = None) -> HouseParams:
        if ctx is None:
            return HouseParams()
        s = ctx.size
        t = ctx.default_wall_mm
        d = float(math.ceil(s.entrance_min_diameter_mm + 5))
        return HouseParams(
            width_mm=max(160.0, d + 4 * t + 50),
            depth_mm=max(130.0, d + 2 * t + 50),
            height_mm=max(110.0, float(math.ceil(arch_height(d) + 2 * t + 2 * MARGIN_MM))),
            walls=WallPart(thickness_mm=t),
            floor=FloorPart(thickness_mm=t),
            floors=FloorsPart(plate_thickness_mm=t, ramp_width_mm=float(math.ceil(s.gap_trap.passable_min_mm + 10)),
                              slope_deg=s.max_ramp_angle_deg,  # 내부 경사로는 완만할수록 집이 길어지므로 종별 최대 경사
                              level_height_mm=min(100.0, s.max_climb_height_mm)),
            doors=DoorsPart(width_mm=d),
            windows=WindowsPart(diameter_mm=min(4.0, s.gap_trap.safe_max_mm)),
            ports=PortsPart(diameter_mm=float(math.ceil(s.tunnel_min_inner_diameter_mm + 5)),
                            flange_mm=min(3.0, s.gap_trap.safe_max_mm)),
        )

    # ── 제약 ──

    def constraints(self, p: HouseParams, ctx: RuleContext) -> list[ParamConstraint]:
        s = ctx.size
        P = s.gap_trap.passable_min_mm
        t = max(p.walls.thickness_mm, ctx.min_wall_mm)
        i = inset(p)
        sh = make_shell(p)
        R = roof_rise(p)
        tc = top_clearance(p)
        wall = ctx.wall_thickness_constraint()
        out = [
            ParamConstraint("walls.thickness_mm", min=wall.min, source=wall.source, reason_ko=wall.reason_ko),
        ]
        if p.floor.enabled:
            out.append(ParamConstraint("floor.thickness_mm", min=ctx.min_wall_mm, source=wall.source,
                                       reason_ko=wall.reason_ko))
        if p.floors.count == 2:
            out.append(ParamConstraint("floors.plate_thickness_mm", min=ctx.min_wall_mm, source=wall.source,
                                       reason_ko=wall.reason_ko))
        out += openings.opening_constraints(p.doors, p.windows, p.ports, ctx, i, t)
        out += shell.roof_constraints(p.roof, ctx.printing_max_overhang_deg)
        ground_top = max(openings.ground_opening_top(sh, side, p.doors, p.ports) for side in ("front", "back", "left", "right"))
        out += levels.floors_constraints(p.floors, ctx, i, t, sh.z_floor, ground_top, WIDTH_MAX_MM)
        # 높이: 1층 개구부 위로 벽이 남도록 / 2층 머리 공간·2층 출입구 / 창 띠
        out.append(ParamConstraint(
            "height_mm", min=R + ground_top + tc,
            reason_ko="출입구·연결부 아치 위로 벽이 남도록 높이가 충분히 커야 합니다",
        ))
        if p.floors.count == 2:
            lvl = p.floors.level_height_mm
            out.append(ParamConstraint(
                "height_mm", min=R + lvl + P + tc,
                reason_ko=f"2층 바닥 위로 몸이 지나갈 높이({P:g}mm)가 남아야 합니다 (처마 기준)",
            ))
            if upper_door(p) is not None:
                out.append(ParamConstraint(
                    "height_mm", min=R + lvl + arch_height(max(p.doors.width_mm, s.entrance_min_diameter_mm)) + tc,
                    reason_ko="2층 출입구 아치 위로 벽이 남도록 높이가 충분히 커야 합니다",
                ))
        if p.windows.count > 0:
            occ = max(_occupied_top(p, sh, side) for side in openings.window_sides(p.windows))
            out.append(ParamConstraint(
                "height_mm", min=R + occ + MARGIN_MM + lens_height(p.windows.diameter_mm) + tc,
                reason_ko="창이 출입구 위 벽 띠에 들어가도록 높이가 충분히 커야 합니다",
            ))
        return out

    # ── 형상 ──

    def _body(self, p: HouseParams, sh: Shell) -> Part:
        t = p.walls.thickness_mm
        if body_inverted(p):
            body = shell.flat_roof_body(p.width_mm, p.depth_mm, p.height_mm, t)
        else:
            body = shell.wall_ring(sh.wx, sh.wy, t, sh.wall_top)
            if p.floor.enabled:
                body = body + shell.floor_plate(sh.wx, sh.wy, t, p.floor.thickness_mm)
        body = openings.cut_openings(body, sh, p.doors, p.windows, p.ports, window_bottom(p), upper_door(p))
        if p.floors.count == 2:
            body = body + levels.ledges(p.floors, sh)
            if p.floors.climb == "internal_ramp":
                body = body + levels.internal_ramp(p.floors, sh)
            else:
                body = body + levels.porch(p.floors, sh)
        return body

    def print_parts(self, p: HouseParams, built: Part | None = None) -> list[PrintPart]:
        sh = make_shell(p)
        t = p.walls.thickness_mm
        parts = [PrintPart("본체", self._body(p, sh), _INVERTED if body_inverted(p) else _UPRIGHT, key="body")]
        if is_cap(p):
            cap = shell.roof_cap(p.roof, p.width_mm, p.depth_mm, t, sh.wall_top)
            parts.append(PrintPart("지붕", cap, _INVERTED if p.roof.kind == "flat" else _UPRIGHT, key="roof"))
        if p.floors.count == 2:
            parts.append(PrintPart("2층 바닥판", levels.upper_plate(p.floors, sh), _UPRIGHT, key="floor2"))
        if p.floor.enabled and body_inverted(p):
            parts.append(PrintPart("바닥판", shell.floor_plate(sh.wx, sh.wy, t, p.floor.thickness_mm), _UPRIGHT, key="floor"))
        return parts

    def build(self, p: HouseParams) -> Part:
        parts = self.print_parts(p)
        assembled = parts[0].part
        for pp in parts[1:]:
            assembled = assembled + pp.part
        return assembled

    def print_rotation(self, p: HouseParams) -> np.ndarray:
        return _INVERTED if body_inverted(p) else _UPRIGHT

    # ── Features ──

    def features(self, p: HouseParams) -> Features:
        ud = upper_door(p)
        thin = [p.walls.thickness_mm]
        if p.floor.enabled:
            thin.append(p.floor.thickness_mm)
        if p.floors.count == 2:
            thin.append(p.floors.plate_thickness_mm)
        two = p.floors.count == 2
        internal = two and p.floors.climb == "internal_ramp"
        extra: dict = {"roof": p.roof.kind, "floors": p.floors.count, "part_count": len(self._part_keys(p))}
        if two:
            extra["climb"] = p.floors.climb
            if not internal:
                extra["attach_side"] = p.floors.exit_side
                extra["landing_height_mm"] = p.floors.level_height_mm
        return Features(
            min_wall_thickness_mm=min(thin),
            openings=tuple(openings.opening_features(p.doors, p.windows, p.ports, ud[0] if ud else None)),
            access_sides=openings.access_sides(p.doors, p.ports),
            climb_height_mm=p.floors.level_height_mm if two else None,
            slope_deg=p.floors.slope_deg if internal else None,
            entrance_count=len(p.doors.sides) + len(p.ports.sides),
            extra=extra,
        )

    # ── 장식 영역 ──

    def decor_zones(self, p: HouseParams) -> list[DecorZone]:
        """바깥 벽 네 면(파내기·돋을새김)과, 경사·둥근 지붕이면 지붕 윗면 앞·뒤 경사면(파내기만).
        평 지붕 윗면은 (뒤집어 출력하므로) 베드에 닿는 면이라 뺀다."""
        sh = make_shell(p)
        t = p.walls.thickness_mm
        v1 = sh.wall_top - top_clearance(p) + MARGIN_MM  # 스커트·지붕판 아래 (keepout 이 다시 띄운다)
        wb = window_bottom(p)
        ud = upper_door(p)
        zones: list[DecorZone] = []
        for face in ("front", "back", "left", "right"):
            length = sh.wall_length(face)
            cx, cy = sh.wall_center(face)
            ox, oy = sh.outward(face)
            surface = (cx + ox * t / 2, cy + oy * t / 2, 0.0)
            obstacles: list[tuple[float, float, float, float]] = []
            if face in p.doors.sides:
                r = p.doors.width_mm / 2
                obstacles.append((-r, 0.0, r, arch_height(p.doors.width_mm)))
            if face in p.ports.sides:
                r = p.ports.diameter_mm / 2 + t  # 플랜지 고리 포함
                obstacles.append((-r, 0.0, r, arch_height(2 * r)))
            if face in openings.window_sides(p.windows):
                rw = p.windows.diameter_mm / 2
                obstacles.append((-rw, wb, rw, wb + lens_height(p.windows.diameter_mm)))
            if ud is not None and ud[0] == face:
                r = ud[2] / 2
                obstacles.append((-r, ud[1], r, ud[1] + arch_height(ud[2])))
                obstacles.append((-length / 2, 0.0, length / 2, ud[1]))  # 착지판이 아래를 덮는다
            zones.append(DecorZone(
                face=face, mode="relief", max_depth_mm=DECOR_MAX_DEPTH_MM, keepout_mm=DECOR_KEEPOUT_MM,
                u0=-length / 2, u1=length / 2, v0=0.0, v1=v1, obstacles=tuple(obstacles), part_key="body",
                print_inverted=body_inverted(p), thickness_field="walls.thickness_mm", surface=surface,
            ))
        if is_cap(p) and p.roof.kind == "pitched":
            # 경사 지붕 앞·뒤 경사면을 기울어진 벽으로: u = 용마루 방향(바깥에서 읽는 방향), v = 처마에서 용마루 쪽으로
            # (둥근 지붕은 곡면이라 홈 벽과 표면이 예각을 이루어 지원하지 않는다)
            a = math.radians(p.roof.pitch_deg)
            z_eave = eave_height(p) + shell.pitched_eave_lift(t, p.roof.pitch_deg)
            slope_len = (p.depth_mm / 2) / math.cos(a)
            k = max(DECOR_KEEPOUT_MM, t)
            for sign, x_sign in ((-1.0, 1.0), (1.0, -1.0)):  # 앞 경사면(−Y 쪽), 뒤 경사면(+Y 쪽)
                zones.append(DecorZone(
                    face="roof", mode="engrave", max_depth_mm=DECOR_MAX_DEPTH_MM, keepout_mm=0.0,
                    u0=-p.width_mm / 2 + k, u1=p.width_mm / 2 - k, v0=k, v1=slope_len - k, part_key="roof",
                    print_inverted=False, thickness_field="walls.thickness_mm",
                    surface=(0.0, sign * p.depth_mm / 2, z_eave),
                    x_dir=(x_sign, 0.0, 0.0),
                    z_dir=(0.0, sign * math.sin(a), math.cos(a)),
                ))
        return zones

    @staticmethod
    def _part_keys(p: HouseParams) -> list[str]:
        keys = ["body"]
        if is_cap(p):
            keys.append("roof")
        if p.floors.count == 2:
            keys.append("floor2")
        if p.floor.enabled and body_inverted(p):
            keys.append("floor")
        return keys
