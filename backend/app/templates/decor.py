"""장식 영역(decor zone): 안전과 무관한 면에 무늬·이름 각인을 얹는다.

LLM 은 장식 **명세**만 낸다 (무늬 종류·밀도·방향·깊이, 또는 글귀·위치·글자 높이). 형상은 여기서만 만든다.
  - 무늬: stripes | dots | scales | brick | wave | honeycomb. 격자 위상(시작 위치)은 (템플릿 키, 정렬된 파라미터 JSON, 장식 JSON)
    해시를 시드로 정한다 → 같은 입력이면 같은 형상.
  - 각인: 한글(완성형 음절)·영문 대소문자·숫자·공백·하이픈 최대 12자. 번들 글꼴(app/assets/fonts, OFL)만 쓴다.
    글꼴에 없는 문자가 있으면 각인을 건너뛰고 경고한다.

보장(코드로 강제):
  - 각인 깊이를 뺀 벽 두께 ≥ 최소 벽. 엔진이 먼저 벽을 두껍게 보정하고, 그래도 모자라면 깊이를 줄이고, 그래도 안 되면 건너뛴다.
  - 선 폭·점 지름·글자 획 ≥ printing.yaml min_feature_mm. 글자는 높이를 키워 맞추고, 영역에 들어가지 않으면 건너뛴다.
  - 돋을새김 돌기 사이 간격 ≤ gap_trap.safe_max_mm (끼임 틈 없음). 지붕 윗면은 각인만.
  - 출력 자세에서 오버행이 생기지 않게: 홈·돌기는 "곧은 압출 ∩ 비스듬한 압출" 로 만들어 출력 자세에서 천장이 되는 면을
    (최대 오버행 − 5°) 까지만 기울이고 다른 면은 곧게 둔다 (단순 전단은 표면 모서리를 칼날처럼 얇게 만든다).
    홈이 깊이 방향으로 좁아지므로 깊이는 가장 가는 요소 폭에 맞춰 줄인다. 경사 지붕 면은 기울어진 벽으로 다룬다
    (곧은 홈의 오르막 벽 오버행 = 경사각이라 그만큼만 기울이면 된다).
  - 장식은 features() 를 바꾸지 않는다 (features 는 파라미터만 본다).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Union

from build123d import (
    Compound,
    Plane,
    Polygon,
    Pos,
    Rectangle,
    RegularPolygon,
    Rot,
    Text,
    Vector,
    extrude,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.templates.base import DecorZone, PrintPart, RuleContext, Template, TemplateParams
from app.validation.report import Issue, Severity

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_FILE = FONT_DIR / "Pretendard-Bold.otf"
FONT_LICENSE_FILE = FONT_DIR / "OFL-Pretendard.txt"
# 글꼴에서 가장 가는 획 ≈ 글자 높이의 이 비율 (Pretendard Bold 를 재서 보수적으로 정함). 최소 글자 높이 = min_feature / 비율
FONT_MIN_STROKE_RATIO = 0.08
TEXT_MAX_LEN = 12
TEXT_PATTERN = r"^[가-힣A-Za-z0-9 \-]{1,12}$"
_TEXT_RE = re.compile(TEXT_PATTERN)

Pattern = Literal["stripes", "dots", "scales", "brick", "wave", "honeycomb"]
DecorFace = Literal["front", "back", "left", "right", "roof"]
# 밀도 → 무늬 피치(mm)
PITCH_BY_DENSITY = {1: 12.0, 2: 8.0, 3: 5.5}
FEATURE_RATIO = 0.3   # 선 폭·점 지름 = 피치 × 비율 (min_feature 이상)
CUT = 1.0
# 홈 천장·돌기 아랫면의 목표 오버행 = 최대 오버행 − 이 여유 (경계값 판정이 흔들리지 않게)
TILT_MARGIN_DEG = 5.0
# 홈 바닥(또는 돌기 바깥면)에 남는 요소 폭의 최소 비율: 깊이 ≤ (1 − 비율) × 요소 폭 / tan(기울기)
FLOOR_RATIO = 0.4
# 영역 하나의 무늬 요소 수 상한 (불리언 연산 시간). 넘으면 피치를 넓힌다
MAX_ELEMENTS = 120


class PatternDecor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["pattern"] = Field(description="무늬")
    pattern: Pattern = Field(description="무늬 종류. stripes=줄무늬, dots=점, scales=비늘, brick=벽돌, wave=물결, honeycomb=벌집")
    density: Literal[1, 2, 3] = Field(description="밀도. 1=성김, 2=보통, 3=촘촘")
    direction: Literal[0, 45, 90] = Field(description="무늬 방향(도). 0=가로, 45=대각선, 90=세로")
    depth_mm: float = Field(0.6, ge=0.3, le=2.0, description="홈 깊이 또는 돌기 높이 mm (영역 최대 이하로 줄어들 수 있음)")
    face: Literal["walls", "front", "back", "left", "right", "roof"] = Field(
        "walls", description="무늬를 넣을 면. walls=바깥 벽 전부, front/back/left/right=한 벽, roof=지붕 윗면(경사·둥근 지붕만, 파내기만)"
    )
    mode: Literal["engrave", "relief"] = Field("engrave", description="engrave=파내기, relief=돋을새김(세로 벽에서만, 지붕은 파내기)")


class TextDecor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = Field(description="글귀 각인")
    text: str = Field(
        min_length=1, max_length=TEXT_MAX_LEN, pattern=TEXT_PATTERN,
        description="새길 글귀. 한글(완성형)·영문 대소문자·숫자·공백·하이픈만, 최대 12자 (예: '뽀송이 집', 'Mochi-01')",
    )
    face: DecorFace = Field("left", description="새길 면. front/back/left/right=바깥 벽, roof=지붕 윗면(경사·둥근 지붕만)")
    height_mm: float = Field(15, ge=8, le=40, description="글자 높이 mm. 획이 출력 최소 두께 이상이 되도록 커질 수 있음")
    depth_mm: float = Field(0.6, ge=0.3, le=2.0, description="각인 깊이 mm (영역 최대 이하로 줄어들 수 있음)")

    @field_validator("text")
    @classmethod
    def _allowed_chars(cls, v: str) -> str:
        if not _TEXT_RE.fullmatch(v):
            raise ValueError("각인은 한글·영문·숫자·공백·하이픈 1~12자만 쓸 수 있습니다")
        return v


DecorSpec = Annotated[Union[PatternDecor, TextDecor], Field(discriminator="kind")]


def parse_decor(raw: dict | None) -> PatternDecor | TextDecor | None:
    if raw is None:
        return None
    if raw.get("kind") == "text":
        return TextDecor.model_validate(raw)
    return PatternDecor.model_validate(raw)


# ── 글꼴 ──────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def font_codepoints() -> frozenset[int]:
    from fontTools.ttLib import TTFont

    return frozenset(TTFont(str(FONT_FILE)).getBestCmap().keys())


def missing_glyphs(text: str) -> list[str]:
    cps = font_codepoints()
    return sorted({c for c in text if c != " " and ord(c) not in cps})


# ── 결정성 ────────────────────────────────────────────────────


def decor_seed(template_key: str, params: TemplateParams, decor: BaseModel) -> int:
    payload = json.dumps([template_key, params.model_dump(mode="json"), decor.model_dump(mode="json")],
                         sort_keys=True, ensure_ascii=False)
    return int(hashlib.sha256(payload.encode()).hexdigest()[:8], 16)


# ── 무늬 2D (u, v 평면) ─────────────────────────────────────────


def _lines(w: float, pitch: float, span: float, phase: float, vertical: bool) -> list:
    out = []
    n = int(span / pitch) + 3
    for i in range(-n, n + 1):
        c = i * pitch + phase
        if vertical:
            out.append(Pos(c, 0) * Rectangle(w, span * 2))
        else:
            out.append(Pos(0, c) * Rectangle(span * 2, w))
    return out


def _grid(pitch: float, span: float, phase: tuple[float, float], stagger: bool):
    n = int(span / pitch) + 3
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x = i * pitch + phase[0] + (pitch / 2 if stagger and j % 2 else 0)
            yield x, j * pitch + phase[1]


def _half_ring(r: float, w: float, n_seg: int = 10):
    """아래 반원 고리(비늘 윤곽) 다각형: 바깥 호 + 안쪽 호."""
    outer = [(r * math.cos(math.pi + k * math.pi / n_seg), r * math.sin(math.pi + k * math.pi / n_seg)) for k in range(n_seg + 1)]
    inner = [((r - w) * math.cos(math.pi + k * math.pi / n_seg), (r - w) * math.sin(math.pi + k * math.pi / n_seg))
             for k in range(n_seg, -1, -1)]
    return Polygon(*(outer + inner), align=None)


def pattern_shapes(pattern: Pattern, pitch: float, w: float, span: float, phase: tuple[float, float]):
    """무늬 요소 (2D, 원점 주변 ±span 범위를 넉넉히 덮는다). w = 선 폭·점 지름(≥ min_feature).

    되풀이되는 요소(점·비늘·벌집)는 (원형 요소 하나, 위치 목록)으로 돌려줘 3D 홈을 하나만 만들고 복사한다.
    선 요소(줄·벽돌·물결)는 면 목록으로 돌려준다. 반환: (proto | None, offsets, faces)."""
    if pattern == "stripes":
        return None, [], _lines(w, pitch, span, phase[1], vertical=False)
    if pattern == "dots":
        # 원 대신 12각형: 테셀레이션 삼각형 수를 줄인다 (지름 2~4mm 에서 차이가 보이지 않는다)
        return RegularPolygon(w / 2, 12), list(_grid(pitch, span, phase, stagger=True)), []
    if pattern == "brick":
        rows = _lines(w, pitch, span, phase[1], vertical=False)
        n = int(span / pitch) + 3
        joints = []
        for j in range(-n, n + 1):
            y = j * pitch + phase[1] + pitch / 2
            off = pitch if j % 2 else 0
            for i in range(-n, n + 1):
                joints.append(Pos(i * 2 * pitch + off + phase[0], y) * Rectangle(w, pitch))
        return None, [], rows + joints
    if pattern == "honeycomb":
        # 중심이 삼각 격자(간격 pitch)인 육각 고리. 이웃 고리 사이에 선 폭만큼 땅을 남겨 서로 닿지 않게 한다
        # (닿으면 면이 겹쳐 불리언이 느리고 메시가 닫히지 않는다)
        r_out = (pitch - w) / math.sqrt(3)  # 안반지름 = (pitch − w) / 2
        n = int(span / pitch) + 3
        offsets = []
        for j in range(-n, n + 1):
            for i in range(-n, n + 1):
                x = i * pitch + (pitch / 2 if j % 2 else 0) + phase[0]
                y = j * pitch * math.sqrt(3) / 2 + phase[1]
                if abs(x) <= span * 1.2 and abs(y) <= span * 1.2:
                    offsets.append((x, y))
        return RegularPolygon(r_out, 6) - RegularPolygon(r_out - w, 6), offsets, []
    if pattern == "scales":
        # 엇갈린 아래 반원 고리. 이웃·윗줄과 겹치지 않게 반지름을 줄이고 줄 간격을 띄운다
        r = (pitch - w) / 2
        dy = r + w
        n = int(span / min(pitch, dy)) + 3
        offsets = [(i * pitch + (pitch / 2 if j % 2 else 0) + phase[0], j * dy + phase[1])
                   for j in range(-n, n + 1) for i in range(-n, n + 1)]
        return _half_ring(r, w), offsets, []
    # wave: 사인 곡선 띠 (다각형 근사)
    out = []
    lam, amp = 2 * pitch, pitch / 3
    n = int(span / pitch) + 3
    steps = 48
    for j in range(-n, n + 1):
        y0 = j * pitch + phase[1]
        xs = [-span * 1.2 + k * (2.4 * span / steps) for k in range(steps + 1)]
        top = [(x, y0 + amp * math.sin(2 * math.pi * (x + phase[0]) / lam) + w / 2) for x in xs]
        bottom = [(x, y0 + amp * math.sin(2 * math.pi * (x + phase[0]) / lam) - w / 2) for x in reversed(xs)]
        out.append(Polygon(*(top + bottom), align=None))
    return None, [], out


class _Clipped:
    """영역 안에 남은 무늬 요소: 그대로 쓰는 원형 요소의 위치(offsets)와, 경계에서 잘라낸 개별 면(faces)."""

    def __init__(self, proto, offsets: list[tuple[float, float]], faces: list):
        self.proto = proto
        self.offsets = offsets
        self.faces = faces

    def count(self) -> int:
        return len(self.offsets) + len(self.faces)


def _clip(proto, offsets: list[tuple[float, float]], shapes: list, region, zone: DecorZone) -> _Clipped:
    """영역 안의 요소만 남긴다. 영역 사각형(keepout 안쪽) 안에 완전히 들어가고 장애물에 닿지 않으면 그대로(위치만),
    경계에 걸치면 2D 교집합으로 자른 면을, 밖이면 버린다 (요소마다 불리언을 하지 않게)."""
    k = zone.keepout_mm
    u0, u1, v0, v1 = zone.u0 + k, zone.u1 - k, zone.v0 + k, zone.v1 - k
    obs = [(a - k, b - k, c + k, d + k) for a, b, c, d in zone.obstacles]
    kept: list[tuple[float, float]] = []
    faces: list = []

    def place(x0, y0, x1, y1, make_shape, keep):
        if x1 <= u0 or x0 >= u1 or y1 <= v0 or y0 >= v1:
            return
        inside = x0 >= u0 and x1 <= u1 and y0 >= v0 and y1 <= v1
        touches = any(x0 < c and x1 > a and y0 < d and y1 > b for a, b, c, d in obs)
        if inside and not touches:
            keep()
            return
        clipped = make_shape() & region
        if clipped is not None and clipped.area > 1e-6:
            faces.extend(f for f in clipped.faces() if f.area > 1e-6)

    if proto is not None:
        # 되풀이 요소는 경계·장애물에 걸치면 자르지 않고 뺀다 (요소마다 불리언을 하지 않게. 가장자리가 조금 들쭉날쭉해진다)
        pb = proto.bounding_box()
        for ox, oy in offsets:
            x0, y0, x1, y1 = pb.min.X + ox, pb.min.Y + oy, pb.max.X + ox, pb.max.Y + oy
            inside = x0 >= u0 and x1 <= u1 and y0 >= v0 and y1 <= v1
            touches = any(x0 < c and x1 > a and y0 < d and y1 > b for a, b, c, d in obs)
            if inside and not touches:
                kept.append((ox, oy))
    for sh in shapes:
        bb = sh.bounding_box()
        place(bb.min.X, bb.min.Y, bb.max.X, bb.max.Y, lambda sh=sh: sh, lambda sh=sh: faces.append(sh))
    return _Clipped(proto, kept, faces)


def zone_region(zone: DecorZone, inset: float = 0.0):
    """영역 2D: 사각형에서 장애물(keepout 만큼 넓힘)을 뺀 면. inset 만큼 가장자리를 더 비울 수 있다."""
    k = zone.keepout_mm + inset
    u0, u1, v0, v1 = zone.u0 + k, zone.u1 - k, zone.v0 + k, zone.v1 - k
    if u1 - u0 <= 0 or v1 - v0 <= 0:
        return None
    region = Pos((u0 + u1) / 2, (v0 + v1) / 2) * Rectangle(u1 - u0, v1 - v0)
    for ox0, oy0, ox1, oy1 in zone.obstacles:
        ox0, oy0, ox1, oy1 = ox0 - zone.keepout_mm, oy0 - zone.keepout_mm, ox1 + zone.keepout_mm, oy1 + zone.keepout_mm
        region = region - Pos((ox0 + ox1) / 2, (oy0 + oy1) / 2) * Rectangle(ox1 - ox0, oy1 - oy0)
    return region if region.area > 1e-6 else None


def free_bands(zone: DecorZone) -> list[tuple[float, float, float, float]]:
    """글귀를 놓을 수 있는 빈 가로 띠 후보 (u0, v0, u1, v1): 장애물 위·아래·옆. 큰 것부터."""
    k = zone.keepout_mm
    u0, u1, v0, v1 = zone.u0 + k, zone.u1 - k, zone.v0 + k, zone.v1 - k
    if not zone.obstacles:
        return [(u0, v0, u1, v1)]
    bands = []
    top = max(o[3] for o in zone.obstacles) + k
    bottom = min(o[1] for o in zone.obstacles) - k
    left = min(o[0] for o in zone.obstacles) - k
    right = max(o[2] for o in zone.obstacles) + k
    bands.append((u0, top, u1, v1))
    bands.append((u0, v0, u1, bottom))
    bands.append((u0, v0, left, v1))
    bands.append((right, v0, u1, v1))
    bands = [b for b in bands if b[2] - b[0] > 0 and b[3] - b[1] > 0]
    return sorted(bands, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))


# ── 3D 적용 ────────────────────────────────────────────────────

_U_DIR = {"front": (1, 0, 0), "back": (-1, 0, 0), "left": (0, -1, 0), "right": (0, 1, 0)}
_NORMAL = {"front": (0, -1, 0), "back": (0, 1, 0), "left": (-1, 0, 0), "right": (1, 0, 0)}


def _face_plane(zone: DecorZone) -> Plane:
    """면 좌표(u, v) → 월드. 원점은 면 바깥 표면 위의 점(u=0, v=0), x = u 방향, z = 바깥 법선, y = 위쪽(경사면은 오르는 쪽)."""
    x_dir = Vector(*(zone.x_dir or _U_DIR[zone.face]))
    z_dir = Vector(*(zone.z_dir or _NORMAL[zone.face]))
    return Plane(origin=zone.surface, x_dir=x_dir, z_dir=z_dir)



def _target_overhang_deg(ctx: RuleContext) -> float:
    """홈 천장·돌기 아랫면이 가져도 되는 오버행: 최대 오버행보다 TILT_MARGIN 만큼 작게."""
    max_over = ctx.printing_max_overhang_deg if ctx.printing_max_overhang_deg is not None else 45.0
    return max_over - TILT_MARGIN_DEG


def _shear_deg(zone: DecorZone, plane: Plane, target_overhang_deg: float) -> float:
    """홈·돌기의 가장 나쁜 면(세로 벽: 홈 천장/돌기 아랫면, 경사면: 오르막 쪽 벽)을 목표 오버행까지 기울이는 데 필요한
    전단 각도. 곧은 홈의 그 면 오버행 = 90° − (출력 자세 기준 바깥 법선의 고도각)."""
    up_sign = -1.0 if zone.print_inverted else 1.0
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, plane.z_dir.Z * up_sign))))
    return max(0.0, (90.0 - elevation) - target_overhang_deg)


def _surface_solids(zone: DecorZone, clipped: _Clipped, depth: float, into: bool, target_overhang_deg: float) -> list:
    """면(세로 벽 또는 경사면)의 홈(into) 또는 돌기 솔리드: 곧은 압출 ∩ 비스듬한 압출.
    비스듬한 쪽은 출력 자세에서 천장이 되는 면을 목표 오버행까지 기울인다 (홈: 내리막으로 내려감, 돌기: 바깥쪽으로 올라감).
    다른 면은 곧게 남아 표면 모서리가 모두 둔각이다. 되풀이되는 원형 요소는 홈을 하나만 만들어 위치마다 복사한다."""
    plane = _face_plane(zone)
    n = plane.z_dir * (-1.0 if into else 1.0)
    down = plane.y_dir * (-1.0 if not zone.print_inverted else 1.0)  # 출력 자세 기준 아래쪽 (면 안의 방향)
    shear = math.radians(_shear_deg(zone, plane, target_overhang_deg))
    sign = 1.0 if into else -1.0  # 홈은 아래로, 돌기는 위로
    oblique = n * math.cos(shear) + down * (sign * math.sin(shear))
    start = plane.offset(CUT if into else -CUT)
    amount = depth + CUT

    def pocket(face):
        placed = start * face
        straight = extrude(placed, amount=amount, dir=n)
        if shear < 1e-9:
            return straight
        sheared = extrude(placed, amount=amount / math.cos(shear), dir=oblique)
        solid = straight & sheared
        return solid if solid is not None and solid.volume > 1e-9 else None

    out = []
    if clipped.proto is not None and clipped.offsets:
        base = pocket(clipped.proto)
        if base is not None:
            for ox, oy in clipped.offsets:
                out.append(base.translate(plane.x_dir * ox + plane.y_dir * oy))
    for f in clipped.faces:
        solid = pocket(f)
        if solid is not None:
            out.append(solid)
    return out


def _depth_cap(depth: float, min_width: float, shear_deg: float) -> float:
    """홈이 깊이 방향으로 좁아지므로 바닥에 요소 폭의 FLOOR_RATIO 가 남도록 깊이를 제한한다."""
    if shear_deg < 1e-9:
        return depth
    return min(depth, (1 - FLOOR_RATIO) * min_width / math.tan(math.radians(shear_deg)))


def apply_decor(
    parts: list[PrintPart], template: Template, p: TemplateParams, decor: PatternDecor | TextDecor | None,
    ctx: RuleContext, item_index: int | None = None, label_ko: str | None = None,
) -> tuple[list[PrintPart], list[Issue]]:
    """출력 파트에 장식을 얹는다. 장식은 파트 분할 뒤 파트별로 적용한다(조립 형상은 그 파트들의 합).

    돌려주는 이슈: decor_reduced(깊이·크기를 줄임, warning), decor_skipped(장식을 뺌, warning)."""
    if decor is None:
        return parts, []
    label = label_ko or template.display_name_ko
    issues: list[Issue] = []
    if ctx.min_feature_mm is None:
        return parts, [_skip(label, "출력 최소 형상 크기(min_feature_mm)가 없어 장식을 뺐습니다.", item_index)]
    zones = template.decor_zones(p)
    if not zones:
        return parts, [_skip(label, "이 구조물에는 장식을 넣을 수 있는 면이 없어 장식을 뺐습니다.", item_index)]
    wanted = [z for z in zones if _matches(z, decor)]
    if isinstance(decor, TextDecor):
        wanted = wanted[:1]  # 글귀는 그 면의 첫 영역(지붕이면 앞 경사면)에만
    if not wanted:
        return parts, [_skip(label, "요청한 면에는 장식을 넣을 수 없어 장식을 뺐습니다 (출입구·결합부를 피한 빈 면이 없거나, 그 면이 없습니다).",
                             item_index)]
    seed = decor_seed(template.key, p, decor)
    new_parts = list(parts)
    applied = 0
    # 파트별로 홈(파내기)·돌기(돋을새김) 솔리드를 모아 불리언을 한 번씩만 한다
    tools: dict[int, dict[str, list]] = {}
    for zone in wanted:
        idx = next((i for i, pp in enumerate(new_parts) if pp.key == zone.part_key), None)
        if idx is None:
            continue
        cutter, zone_issues = _zone_cutter(zone, template, p, decor, ctx, seed, label, item_index)
        issues.extend(zone_issues)
        if cutter is None:
            continue
        mode = "engrave" if zone.face == "roof" else decor.mode if isinstance(decor, PatternDecor) else "engrave"
        if mode == "relief" and zone.mode != "relief":
            mode = "engrave"
        tools.setdefault(idx, {"engrave": [], "relief": []})[mode].extend(cutter.solids())
        applied += 1
    for idx, by_mode in tools.items():
        part = new_parts[idx]
        shape = part.part
        if by_mode["engrave"]:
            shape = shape - Compound(children=by_mode["engrave"])
        if by_mode["relief"]:
            shape = shape + Compound(children=by_mode["relief"])
        new_parts[idx] = PrintPart(part.name_ko, shape, part.rotation, key=part.key)
    if applied == 0 and not any(i.code == "decor_skipped" for i in issues):
        issues.append(_skip(label, "장식을 넣을 빈 자리가 없어 장식을 뺐습니다.", item_index))
    # 같은 까닭의 경고는 면마다 되풀이하지 않는다 (벽 네 면이 같은 이유로 빠지면 한 번만)
    seen: set[tuple[str, str]] = set()
    unique = [i for i in issues if not ((i.code, i.message_ko) in seen or seen.add((i.code, i.message_ko)))]
    return new_parts, unique


def _matches(zone: DecorZone, decor: PatternDecor | TextDecor) -> bool:
    if decor.face == "walls":
        return zone.face != "roof"
    return zone.face == decor.face


def _skip(label: str, why: str, item_index: int | None) -> Issue:
    return Issue(code="decor_skipped", severity=Severity.warning, item_index=item_index, message_ko=f"{label}: {why}")


def _reduced(label: str, why: str, item_index: int | None, **details) -> Issue:
    return Issue(code="decor_reduced", severity=Severity.warning, item_index=item_index, message_ko=f"{label}: {why}",
                 details=details)


def _depth_for(zone: DecorZone, requested: float, p: TemplateParams, ctx: RuleContext, mode: str,
               label: str, item_index: int | None, issues: list[Issue]) -> float | None:
    """허용 깊이: 영역 최대 이하, 파내기는 남는 벽 ≥ 최소 벽. 0.3mm 미만이면 None (건너뜀)."""
    depth = min(requested, zone.max_depth_mm)
    if mode == "engrave" and zone.thickness_field:
        t = p
        for name in zone.thickness_field.split("."):
            t = getattr(t, name)
        depth = min(depth, float(t) - ctx.min_wall_mm)
    if depth < 0.3 - 1e-9:
        issues.append(_skip(label, f"각인 깊이를 빼면 벽이 최소 두께 {ctx.min_wall_mm:g}mm 보다 얇아져 장식을 뺐습니다. "
                                   "벽을 더 두껍게 하면 넣을 수 있어요.", item_index))
        return None
    if depth < requested - 1e-9:
        issues.append(_reduced(label, f"벽 두께를 지키도록 장식 깊이를 {requested:g}mm 에서 {depth:.1f}mm 로 줄였습니다.",
                               item_index, field="depth_mm", **{"from": requested, "to": round(depth, 2)}))
    return depth


def _zone_cutter(zone: DecorZone, template: Template, p: TemplateParams, decor: PatternDecor | TextDecor,
                 ctx: RuleContext, seed: int, label: str, item_index: int | None):
    issues: list[Issue] = []
    mode = "engrave" if zone.face == "roof" or isinstance(decor, TextDecor) else decor.mode
    if zone.face != "roof" and mode == "relief" and zone.mode != "relief":
        mode = "engrave"
        issues.append(_reduced(label, "이 면에는 돋을새김을 넣을 수 없어 파내기로 바꿨습니다.", item_index))
    depth = _depth_for(zone, decor.depth_mm, p, ctx, mode, label, item_index, issues)
    if depth is None:
        return None, issues
    made = (_text_sketch(zone, decor, ctx, label, item_index, issues) if isinstance(decor, TextDecor)
            else _pattern_sketch(zone, decor, ctx, seed, mode, label, item_index, issues))
    if made is None:
        return None, issues
    clipped, min_width = made
    target = _target_overhang_deg(ctx)
    shear = _shear_deg(zone, _face_plane(zone), target)
    capped = _depth_cap(depth, min_width, shear)
    if capped < depth - 1e-9:
        if capped < 0.3 - 1e-9:
            issues.append(_skip(label, "무늬·글자 획이 너무 가늘어 홈을 낼 수 없어 장식을 뺐습니다.", item_index))
            return None, issues
        issues.append(_reduced(label, f"가는 요소의 홈 바닥이 남도록 장식 깊이를 {depth:.1f}mm 에서 {capped:.1f}mm 로 줄였습니다.",
                               item_index, field="depth_mm", **{"from": round(depth, 2), "to": round(capped, 2)}))
        depth = capped
    solids = _surface_solids(zone, clipped, depth, mode == "engrave", target)
    return (Compound(children=solids) if solids else None), issues


def _pattern_sketch(zone: DecorZone, decor: PatternDecor, ctx: RuleContext, seed: int, mode: str,
                    label: str, item_index: int | None, issues: list[Issue]):
    assert ctx.min_feature_mm is not None
    pitch = PITCH_BY_DENSITY[decor.density]
    w = max(ctx.min_feature_mm, FEATURE_RATIO * pitch)
    if mode == "relief":
        # 돋을새김 돌기 사이 간격 ≤ 끼임 안전 틈 (passable_min 이상으로 벌릴 만큼 넓은 면은 없다)
        gap_max = ctx.size.gap_trap.safe_max_mm
        if pitch - w > gap_max:
            pitch = w + gap_max
    region = zone_region(zone)
    if region is None:
        return None
    bb = region.bounding_box()
    # 요소 수 상한: 영역 넓이에 비해 피치가 너무 촘촘하면 넓힌다 (불리언 연산 시간)
    per_element = {"stripes": pitch * max(bb.size.X, bb.size.Y), "brick": pitch * pitch * 0.5}.get(decor.pattern, pitch * pitch)
    est = bb.size.X * bb.size.Y / per_element
    if est > MAX_ELEMENTS:
        pitch *= math.sqrt(est / MAX_ELEMENTS)
    span = max(bb.size.X, bb.size.Y) * 0.75 + pitch
    rng = seed % 1000 / 1000.0
    phase = (rng * pitch, ((seed // 1000) % 1000 / 1000.0) * pitch)
    proto, offsets, shapes = pattern_shapes(decor.pattern, pitch, w, span, phase)
    cx, cy = bb.center().X, bb.center().Y
    # 방향: 원형 요소는 요소를 돌리고 위치를 회전·이동, 선 요소는 면을 돌리고 이동
    a = math.radians(decor.direction)
    if proto is not None:
        proto = Rot(0, 0, decor.direction) * proto
        offsets = [(cx + ox * math.cos(a) - oy * math.sin(a), cy + ox * math.sin(a) + oy * math.cos(a)) for ox, oy in offsets]
    shapes = [Pos(cx, cy) * (Rot(0, 0, decor.direction) * sh) for sh in shapes]
    clipped = _clip(proto, offsets, shapes, region, zone)
    if clipped.count() == 0:
        return None
    return clipped, w


def _text_sketch(zone: DecorZone, decor: TextDecor, ctx: RuleContext, label: str, item_index: int | None,
                 issues: list[Issue]):
    assert ctx.min_feature_mm is not None
    missing = missing_glyphs(decor.text)
    if missing:
        issues.append(_skip(label, f"글꼴에 없는 문자({''.join(missing)})가 있어 각인을 뺐습니다.", item_index))
        return None
    min_h = ctx.min_feature_mm / FONT_MIN_STROKE_RATIO
    height = decor.height_mm
    if height < min_h:
        issues.append(_reduced(label, f"글자 획이 출력 최소 두께 {ctx.min_feature_mm:g}mm 이상이 되도록 글자 높이를 "
                                      f"{height:g}mm 에서 {min_h:.0f}mm 로 키웠습니다.", item_index,
                               field="height_mm", **{"from": height, "to": round(min_h, 1)}))
        height = min_h
    text = Text(decor.text, font_size=10.0, font_path=str(FONT_FILE))
    bb = text.bounding_box()
    if bb.size.Y <= 0 or bb.size.X <= 0:
        return None
    scale = height / bb.size.Y
    width = bb.size.X * scale
    bands = free_bands(zone)
    fit = next((b for b in bands if b[2] - b[0] >= width and b[3] - b[1] >= height), None)
    if fit is None:
        # 영역에 맞게 줄여 본다 (최소 글자 높이까지)
        best = max(bands, key=lambda b: min((b[2] - b[0]) / width, (b[3] - b[1]) / height), default=None)
        if best is None:
            issues.append(_skip(label, "글귀를 넣을 빈 면이 없어 각인을 뺐습니다.", item_index))
            return None
        f = min((best[2] - best[0]) / width, (best[3] - best[1]) / height)
        if height * f < min_h - 1e-6:
            issues.append(_skip(label, f"'{decor.text}' 이(가) 출입구를 피한 빈 면에 들어가지 않아 각인을 뺐습니다. "
                                       "글귀를 줄이거나 다른 면을 고르세요.", item_index))
            return None
        issues.append(_reduced(label, f"빈 면에 맞춰 글자 높이를 {height:g}mm 에서 {height * f:.0f}mm 로 줄였습니다.",
                               item_index, field="height_mm", **{"from": height, "to": round(height * f, 1)}))
        height *= f
        scale *= f
        fit = best
    cx, cy = (fit[0] + fit[2]) / 2, (fit[1] + fit[3]) / 2
    centered = Pos(-bb.center().X, -bb.center().Y) * text
    placed = Pos(cx, cy) * centered.scale(scale)
    return _Clipped(None, [], [f for f in placed.faces() if f.area > 1e-6]), height * FONT_MIN_STROKE_RATIO
