"""여러 부품(템플릿)을 이어 붙인 조립을 템플릿처럼 쓰게 하는 기반 (AssemblyTemplate).

엔진(보정·배치·검증·저장·내려받기)은 템플릿만 안다. 조립 하나를 템플릿 하나로 감싸면
  - expand(p): 파라미터 → 부품 목록(PartSpec)과 연결 지점끼리의 결합(JoinSpec). 하위 클래스가 정한다
    (자유 조립 항목 app/modules/composed.ComposedTemplate)
  - Params·constraints: 하위 클래스가 정한다 (ComposedTemplate 은 조립 해석기의 derived_constraints)
  - build: 부품을 조립한 형상
  - features: 부품 특징을 합친 것 (출입 면·출입구 수·통로 크기 등)
  - print_parts / print_rotation: 부품끼리 붙은 본체는 여섯 방향으로 눕혀 보고 서포트가 가장 적은 자세로,
    부품이 따로 출력하는 파트(집의 지붕 뚜껑 등)는 그 부품이 정한 자세 그대로.
    슬라이드 결합(mount="slide")·끼움 결합(mount="plug")이 있으면 한 덩어리로 붙은 부품 묶음마다 출력 파트 하나 (연결판의
    도브테일 홈·자식의 도브테일 혀, 끼움 구멍의 틈새·아래를 보는 끼움 턱 둘레 깔때기는 출력 파트에만 있다).
    홈·혀가 있는 묶음은 도브테일이 세로로 서는 두 자세(사용·뒤집기) 중에서 고른다
  - rule_issues: 하위 클래스의 규칙 + 형상 검사 (잇지 않은 부품의 마주 보는 면 사이 끼임 틈(slot_gaps), 통로가 출입구를
    다 덮는지(끼움 결합은 넓힌 구멍까지), 따로 출력하는 파트끼리 겹치는지, 슬라이드 결합 연결판 자리·끼임 틈)
가 되어 기존 흐름을 그대로 탄다.
"""

from __future__ import annotations

import threading
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

from app.modules.assembly import (
    DOVETAIL_MIN_LENGTH_MM,
    OVERLAP_MM,
    PLATE_MM,
    AssemblyError,
    JoinSpec,
    PartSpec,
    SlidePlan,
    _bounds,
    _plane,
    _project,
    _side_profile_solid,
    anchor_frame,
    build_assembly,
    dovetail_centers,
    dovetail_fits,
    leftover_width,
    merge_features,
    part_meshes,
    passage_cutter,
    passage_leftover,
    place_parts,
    plate_gaps,
    plate_solid,
    plug_chamfer,
    slide_plan,
    slot_cutters,
    slot_gaps,
    spigot_solid,
    tongue_solid,
)
from app.templates.base import (
    Features,
    PrintPart,
    RuleContext,
    Template,
    TemplateParams,
)

# 통로가 출입구를 덮고 남긴 빈 곳, 따로 출력하는 파트끼리 겹친 부피가 이보다 크면 오류 (mm³, 형상 커널 오차 여유)
LEFTOVER_MAX_MM3 = 1.0
# 남은 빈 곳이 있어도 가장 넓은 폭이 이보다 좁으면 출력하면 메워지는 실금이라 세지 않는다 (노즐 0.4mm 의 선 폭보다 좁다)
LEFTOVER_MIN_WIDTH_MM = 0.5
OVERLAP_MAX_MM3 = 1.0
_CACHE_SIZE = 16

# 출력 자세 후보: 어느 면을 베드에 댈지 (위쪽 축을 아래로 보내는 회전)
_DOWN_ROTATIONS: tuple[np.ndarray, ...] = (
    np.eye(3),                                                   # 바닥이 아래 (사용 자세)
    np.diag([1.0, -1.0, -1.0]),                                  # 뒤집기 (지붕이 아래)
    np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]]),          # 앞면이 아래
    np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]]),          # 뒷면이 아래
    np.array([[0, 0, 1.0], [0, 1.0, 0], [-1.0, 0, 0]]),          # 왼쪽이 아래
    np.array([[0, 0, -1.0], [0, 1.0, 0], [1.0, 0, 0]]),          # 오른쪽이 아래
)
# 서포트 면적이 이 비율 안에서 비슷하면 사용 자세·낮은 자세를 앞세운다
_TIE = 1.05
# 슬라이드 결합 도브테일(세로 홈·혀)이 있는 묶음의 출력 자세 후보: 도브테일이 세로로 서는 자세만 (눕히면 홈 옆면이 오버행)
_VERTICAL_ROTATIONS: tuple[np.ndarray, ...] = _DOWN_ROTATIONS[:2]




def _get_path(obj: Any, path: str) -> Any:
    for name in path.split("."):
        obj = getattr(obj, name)
    return obj






@dataclass(frozen=True)
class _Contact:
    """슬라이드 결합에서 자식 뒷면이 연결판에 닿는 곳 (도브테일 혀를 붙이는 자식 출력 파트)."""

    t0: float
    t1: float
    u0: float
    u1: float
    ok: bool  # 도브테일이 들어가는 폭·높이인지


@dataclass(frozen=True)
class _Layout:
    """슬라이드 결합이 있는 모듈의 출력 파트와 결합 정보."""

    parts: tuple[PrintPart, ...]
    plans: dict[int, SlidePlan]      # 결합 번호 → 연결판 자리
    contacts: dict[int, _Contact | None]
    owners: tuple[frozenset[str], ...] = ()  # 출력 파트마다 그 파트를 이루는 부품 id


class AssemblyTemplate(Template):
    """부품 여러 개를 연결 지점끼리 이어 붙인 조립 템플릿의 기반 (인스턴스마다 key·Params 가 다르다).

    하위 클래스가 정할 것: expand(p) → (부품, 결합), enclosure(드나드는 공간이 있는 조립인지), has_slide, split,
    Params·constraints·rule_issues. 이 클래스는 형상(build·print_parts·print_rotation), 특징(features)과
    형상 검사(_gap_issues·_geometry_issues)를 맡는다."""

    def __init__(self) -> None:
        self._shapes: dict[str, object] = {}  # 같은 파라미터로 여러 번 부르는 build() (출력 자세·파트) 결과
        self._cache: dict[tuple[str, str], Any] = {}  # 출력 파트·형상 검사 결과 (파라미터별)
        self._lock = threading.Lock()

    def _cached(self, name: str, p: TemplateParams, fn: Callable[[], Any]) -> Any:
        k = (name, _key(p))
        with self._lock:
            if k in self._cache:
                return self._cache[k]
        v = fn()
        with self._lock:
            if len(self._cache) >= _CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[k] = v
        return v

    # ── 하위 클래스가 정한다 ──

    @abstractmethod
    def expand(self, p: TemplateParams) -> tuple[list[PartSpec], list[JoinSpec]]:
        """파라미터 → (부품 목록(첫 부품이 기준), 연결 지점끼리의 결합)."""

    @property
    @abstractmethod
    def enclosure(self) -> bool:
        """드나드는 공간이 있는 조립인지 (바깥 출입구 수를 종별 최소 개수와 비교한다)."""

    @property
    @abstractmethod
    def has_slide(self) -> bool:
        """슬라이드 결합이 있는지."""

    @property
    @abstractmethod
    def split(self) -> bool:
        """따로 출력하는 결합(슬라이드·끼움)이 있어 출력 파트를 묶음마다 나누는지."""

    def part_names(self, parts: list[PartSpec]) -> dict[str, str]:
        """부품 id → 검사 문구·출력 파트 이름에 쓰는 부품 이름. 기본: 템플릿 이름."""
        return {q.id: q.template.display_name_ko for q in parts}

    # ── 형상 검사 ──

    def _geometry_rule_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        """형상으로만 알 수 있는 규칙 위반: 잇지 않은 부품 사이 끼임 틈 + 형상 사실 (조립 규칙이 맞을 때만 부른다)."""
        try:
            out = self._gap_issues(p, ctx)
        except AssemblyError as e:
            return [str(e)]
        return out + self._geometry_issues(p, ctx)

    def _gap_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        """서로 잇지 않은 부품의 마주 보는 면 사이 틈이 끼임 위험 구간이면 오류 (assembly.slot_gaps).
        열린 모서리를 사이에 둔 부품처럼 마주 보는 면이 없는 자리는 세지 않는다."""
        parts, joins = self.expand(p)
        solids = [q for q in parts if not q.template.cutter]
        if len(solids) < 3:
            return []  # 형상 부품이 둘이면 둘은 반드시 이어져 있다
        meshes = self._cached("meshes", p, lambda: part_meshes(parts, joins))
        gt = ctx.size.gap_trap
        names = self.part_names(parts)
        return [f"{names[a]}({a})와 {names[b]}({b}) 사이 틈 {g:.1f}mm 가 끼임 위험 구간"
                f"({gt.safe_max_mm:g}~{gt.passable_min_mm:g}mm)에 있습니다"
                for a, b, g in slot_gaps(parts, joins, meshes, gt)]

    # ── 형상 검사 (파라미터별로 한 번만 계산해 둔다) ──

    def _geometry_issues(self, p: TemplateParams, ctx: RuleContext) -> list[str]:
        gt = ctx.size.gap_trap
        out: list[str] = []
        try:
            facts = self._cached("geometry", p, lambda: self._geometry_facts(p))
        except AssemblyError as e:
            return [str(e)]
        for fact in facts:
            kind, args = fact[0], fact[1:]
            if kind == "leftover":
                a, b, vol = args
                out.append(f"{a}의 출입구가 {b}의 통로보다 커서 틈이 남습니다 (약 {vol:.0f}mm³). "
                           "통로 단면 모양과 폭을 출입구에 맞추세요")
            elif kind == "plug_leftover":
                a, b, vol = args
                out.append(f"{b}의 벽이 {a}의 출입구·끼움 구멍을 다 덮지 못해 틈이 남습니다 (약 {vol:.0f}mm³). "
                           "통로 단면 모양과 폭을 출입구에 맞추세요")
            elif kind == "overlap":
                a, b, vol = args
                out.append(f"따로 출력하는 파트 {a}와(과) {b}이(가) 겹칩니다 (약 {vol:.0f}mm³). "
                           "부품 위치나 크기를 바꾸세요")
            elif kind == "slide_wide":
                a, b, face = args
                out.append(f"{b}이(가) {a}의 '{face}' 면에서 연결판을 붙일 수 있는 곳보다 넓거나 벗어납니다. "
                           "부품이 면 밖으로 튀어나오지 않게 크기나 위치를 바꾸세요")
            elif kind == "slide_floor":
                a, b = args
                out.append(f"슬라이드 결합으로 붙이는 {b}은(는) {a}와(과) 같은 바닥에 서야 합니다")
            elif kind == "slide_contact":
                a, b = args
                out.append(f"{b}의 뒷면이 {a}의 연결판에 닿는 곳이 좁거나 낮아 도브테일을 낼 수 없습니다")
            elif kind == "slide_gap":
                a, b, gaps = args
                trapped = [g for g in gaps if gt.is_trap(g)]
                if trapped and max(trapped) <= PLATE_MM - OVERLAP_MM + 0.1:  # 연결판이 띄운 만큼의 틈 (벽 앞·경사 앞)
                    gap = max(trapped)
                    out.append(f"{a}의 연결판 위로 벽과 {b} 사이에 {gap:.1f}mm 틈이 생겨 끼임 위험 구간"
                               f"({gt.safe_max_mm:g}~{gt.passable_min_mm:g}mm)에 있습니다")
                elif trapped:
                    lo, hi = min(trapped), max(trapped)
                    out.append(f"{b}의 뒷면과 {a}의 벽·지붕 사이에 폭이 {lo:.1f}~{hi:.1f}mm 로 벌어지는 틈이 생겨 "
                               f"끼임 위험 구간({gt.safe_max_mm:g}~{gt.passable_min_mm:g}mm)에 있습니다. "
                               f"{b}을(를) {a}의 처마보다 낮게 하거나 지붕이 기울지 않은 면에 붙이세요")
        return out

    def _geometry_facts(self, p: TemplateParams) -> list[tuple]:
        """종별 기준과 상관없는 형상 사실 (메시지는 _geometry_issues 가 종별 기준으로 만든다)."""
        parts, joins = self.expand(p)
        placed = place_parts(parts, joins)
        names = self.part_names(parts)
        by_id = {q.id: q for q in parts}
        facts: list[tuple] = []
        # 1. 출입구·터널 끝에 통로로 이은 부품이 개구부를 다 덮는지 (끼움 결합은 넓힌 구멍까지)
        for j in joins:
            if not j.passage:
                continue
            wid, pid = j.wall_end[0], j.port_end[0]
            port = by_id[pid]
            if port.template.cutter:
                continue
            left = passage_leftover(placed, j, _plane(placed[pid]) * port.template.build(port.params))
            if left is not None and left.volume > LEFTOVER_MAX_MM3 \
                    and leftover_width(left, placed, j) > LEFTOVER_MIN_WIDTH_MM:
                facts.append(("plug_leftover" if j.plug else "leftover", names[wid], names[pid], float(left.volume)))
        # 2. 슬라이드 결합 연결판 자리
        printable = True
        if self.has_slide:
            layout = self._layout(p)
            for ji, plan in layout.plans.items():
                j = joins[ji]
                a, b = names[j.parent], names[j.child]
                if plan.mount is not None:
                    left_, right_, _ = plan.mount
                    if plan.t0 < left_ - 0.01 or plan.t1 > right_ + 0.01:
                        facts.append(("slide_wide", a, b, j.parent_anchor))
                if abs(plan.child_u[0]) > 0.5:
                    facts.append(("slide_floor", a, b))
                contact = layout.contacts.get(ji)
                if contact is None or not contact.ok:
                    facts.append(("slide_contact", a, b))
                    printable = False
                gaps = self._plate_gaps(layout, plan, joins[ji], parts, joins)
                if gaps:
                    facts.append(("slide_gap", a, b, gaps))
        # 3. 따로 출력하는 파트끼리 겹치지 않는지 (지붕 뚜껑에 닿은 부품, 도브테일 틈새 등)
        if printable:
            pps = self.print_parts(p)
            boxes = [_bounds(pp.part) for pp in pps]
            for i in range(len(pps)):
                for k in range(i + 1, len(pps)):
                    (alo, ahi), (blo, bhi) = boxes[i], boxes[k]
                    if np.any(alo > bhi - 0.01) or np.any(blo > ahi - 0.01):
                        continue
                    vol = float((pps[i].part & pps[k].part).volume)
                    if vol > OVERLAP_MAX_MM3:
                        facts.append(("overlap", pps[i].name_ko, pps[k].name_ko, vol))
        return facts

    # ── 형상 ──

    def build(self, p: TemplateParams):  # noqa: ANN201
        key = _key(p)
        hit = self._shapes.get(key)
        if hit is not None:
            return hit
        parts, joins = self.expand(p)
        try:
            shape = build_assembly(parts, joins)
        except AssemblyError:
            raise
        except Exception as e:  # noqa: BLE001 (형상 커널 오류)
            raise AssemblyError(f"조립 형상을 만들지 못했습니다 ({type(e).__name__})") from e
        if len(self._shapes) >= 8:
            self._shapes.pop(next(iter(self._shapes)))
        self._shapes[key] = shape
        return shape

    def features(self, p: TemplateParams) -> Features:
        parts, joins = self.expand(p)
        return merge_features(parts, joins, self.enclosure)

    def print_rotation(self, p: TemplateParams) -> np.ndarray:
        """여섯 방향으로 눕혀 보고 서포트(오버행) 면적이 가장 작은 자세. 비슷하면 사용 자세·낮은 자세.
        따로 출력하는 결합(슬라이드·끼움)이 있으면 기준 부품 묶음(첫 출력 파트)의 자세."""
        if self.split:
            return self._layout(p).parts[0].rotation
        from app.geometry.mesh import part_to_mesh

        return self._cached("rotation", p, lambda: _best_rotation(part_to_mesh(self._body(p))))

    def print_parts(self, p: TemplateParams, built=None) -> list[PrintPart]:  # noqa: ANN001
        """부품끼리 붙은 본체 하나 + 부품이 따로 출력하는 파트들 (조립 위치 그대로, 출력 자세는 부품이 정한 대로).
        따로 출력하는 결합(슬라이드·끼움)이 있으면 한 덩어리로 붙은 부품 묶음마다 하나 (+ 부품이 따로 출력하는 파트들)."""
        if self.split:
            return list(self._layout(p).parts)
        extras = self._extra_parts(p)
        if not extras:
            body = built if built is not None else self.build(p)
            return [PrintPart("본체", body, self.print_rotation(p))]
        return [PrintPart("본체", self._body(p), self.print_rotation(p)), *extras]

    def _body(self, p: TemplateParams):  # noqa: ANN202
        """부품마다 첫 출력 파트(본체)만 모아 조립한 형상. 따로 출력하는 파트가 없으면 build() 와 같다.
        따로 출력하는 결합이 있으면 기준 부품 묶음의 출력 파트 (연결판·도브테일 홈·끼움 구멍 포함)."""
        if self.split:
            return self._layout(p).parts[0].part
        if not self._extra_parts(p):
            return self.build(p)
        return self._cached("body", p, lambda: self._fused_body(p))

    def _fused_body(self, p: TemplateParams):  # noqa: ANN202
        parts, joins = self.expand(p)
        placed = place_parts(parts, joins)
        mains = {q.id: _plane(placed[q.id]) * q.template.print_parts(q.params)[0].part
                 for q in parts if not q.template.cutter}
        return _group_body([q.id for q in parts], mains, parts, joins, placed)

    def _extra_parts(self, p: TemplateParams) -> list[PrintPart]:
        return self._cached("extras", p, lambda: self._make_extra_parts(p))

    def _make_extra_parts(self, p: TemplateParams) -> list[PrintPart]:
        parts, joins = self.expand(p)
        out: list[PrintPart] = []
        placed = None
        names = self.part_names(parts)
        for part in parts:
            if part.template.cutter:
                continue
            pps = part.template.print_parts(part.params)
            if len(pps) <= 1:
                continue
            placed = placed or place_parts(parts, joins)
            pl = placed[part.id]
            for pp in pps[1:]:
                # 부품 좌표의 출력 자세 회전을 조립 좌표에 맞게: 조립 좌표 → 부품 좌표(회전의 역) → 출력 자세
                out.append(PrintPart(f"{names[part.id]} {pp.name_ko}", _plane(pl) * pp.part,
                                     pp.rotation @ pl.rotation.T, key=f"{part.id}_{pp.key}"))
        return out

    # ── 슬라이드·끼움 결합: 묶음별 출력 파트 ──

    def _layout(self, p: TemplateParams) -> _Layout:
        return self._cached("layout", p, lambda: self._make_layout(p))

    def _make_layout(self, p: TemplateParams) -> _Layout:
        """한 덩어리로 붙은 부품 묶음(fused 결합의 연결 성분)마다 출력 파트 하나.

        - 묶음 본체 = 묶음 부품들의 첫 출력 파트 합 − 빼는 모양(창) − 통로 + (부모 쪽이면) 연결판(출력용: 자식 뒷면에서 끝남)
        - 끼움 결합: 벽 쪽 묶음은 넓힌 구멍으로 뚫고, 통로 쪽 묶음에 끼움 턱을 붙인다 (자세는 여섯 방향 중 서포트가
          가장 적은 쪽이라 세워 출력하는 터널은 끼움 턱이 위를 보게 선다)
        - 부품이 따로 출력하는 파트(집 지붕 등)는 그대로 따로
        - 자세: 홈·혀가 있는 묶음은 도브테일이 세로로 서는 사용·뒤집기 자세 중, 그 밖의 묶음은 여섯 방향 중 서포트가 가장 적은 쪽
        - 도브테일: 연결판에 홈, 자식 출력 파트 중 연결판에 가장 넓게 닿는 파트의 뒷면에 혀 (출력 자세에서 아래를 보는
          끝은 경사로 깎는다)"""
        from app.geometry.mesh import part_to_mesh

        parts, joins = self.expand(p)
        placed = place_parts(parts, joins)
        by_id = {q.id: q for q in parts}
        names = self.part_names(parts)
        groups = fused_groups(parts, joins)
        group_of = {pid: gi for gi, g in enumerate(groups) for pid in g}
        bounds = {pid: (np.asarray(lo), np.asarray(hi)) for pid, (lo, hi) in _part_bounds(self, _key(p)).items()}

        mains: dict[str, Any] = {}
        extras: dict[str, list[list[Any]]] = {}  # 부품 id → [[이름, key, 솔리드, 자세], …]
        for q in parts:
            if q.template.cutter:
                continue
            pl = placed[q.id]
            pps = q.template.print_parts(q.params)
            mains[q.id] = _plane(pl) * pps[0].part
            extras[q.id] = [[f"{names[q.id]} {pp.name_ko}", f"{q.id}_{pp.key}", _plane(pl) * pp.part,
                             pp.rotation @ pl.rotation.T] for pp in pps[1:]]
        bodies: list[Any] = [_group_body(g, mains, parts, joins, placed) for g in groups]
        plans: dict[int, SlidePlan] = {}
        for ji, j in enumerate(joins):
            if not j.slide:
                continue
            plan = slide_plan(placed, j, bounds[j.parent], bounds[j.child])
            plans[ji] = plan
            if plan.h > 0.5:
                gi = group_of[j.parent]
                bodies[gi] = bodies[gi] + plate_solid(plan, for_print=True)
        dovetailed = {group_of[joins[ji].parent] for ji in plans} | {group_of[joins[ji].child] for ji in plans}
        rots = [_best_rotation(part_to_mesh(b), _VERTICAL_ROTATIONS if gi in dovetailed else _DOWN_ROTATIONS)
                for gi, b in enumerate(bodies)]
        # 일부러 얇게 만든 결합 모양 (묶음 번호 또는 따로 출력하는 파트 → 솔리드): 메시 두께 실측에서 뺀다 (PrintPart.thin_ok)
        thin: dict[Any, list[Any]] = {}
        # 끼움 턱이 출력 자세에서 아래를 보면(세워 출력하는 터널의 아래 끝) 그 둘레 끝 면이 아래를 보는 턱이 되므로 깔때기로 깎는다
        for j in joins:
            if j.plug:
                gp = group_of[j.port_end[0]]
                thin.setdefault(gp, []).append(spigot_solid(placed, j))
                _, _, _, n = anchor_frame(placed, *j.port_end)
                if float((rots[gp] @ n)[2]) < -0.5:
                    chamfer = plug_chamfer(placed, j)
                    bodies[gp] = bodies[gp] - chamfer
                    thin[gp].append(chamfer)

        contacts: dict[int, _Contact | None] = {}
        for ji, plan in plans.items():
            j = joins[ji]
            contact, target = self._contact(plan, mains[j.child], extras[j.child], bodies, rots, group_of[j.child])
            contacts[ji] = contact
            if contact is None or not contact.ok or plan.h <= 0.5:
                continue
            centers = dovetail_centers(contact.t0, contact.t1)
            u_lo, u_hi = max(0.0, contact.u0), min(plan.h, contact.u1)
            solid, rot = target
            plo, phi = _project(*_bounds(solid), plan.origin, plan.u)
            down_top = float((rot @ plan.u)[2]) < -0.5
            down_bottom = float((rot @ -plan.u)[2]) < -0.5
            tongue = tongue_solid(plan, centers, u_lo, u_hi,
                                  slope_top=down_top and u_hi < phi - 0.05,
                                  slope_bottom=down_bottom and u_lo > plo + 0.05)
            owner = self._attach(target, tongue, bodies, extras[j.child], group_of[j.child])
            thin.setdefault(group_of[j.child] if owner is None else id(owner), []).append(tongue)
            gi = group_of[j.parent]
            for cut in slot_cutters(plan, centers):
                bodies[gi] = bodies[gi] - cut

        out: list[PrintPart] = []
        owners: list[frozenset[str]] = [frozenset(g) for g in groups]
        separate_children = {j.child for j in joins if j.separate}
        for gi, g in enumerate(groups):
            if gi == 0:
                out.append(PrintPart("본체", bodies[gi], rots[gi], key="body", thin_ok=tuple(thin.get(gi, ()))))
                continue
            head = next((pid for pid in g if pid in separate_children), g[0])
            q = by_id[head]
            pps = q.template.print_parts(q.params)
            if len(pps) > 1:
                name, key = f"{names[q.id]} {pps[0].name_ko}", f"{q.id}_{pps[0].key}"
            else:
                name, key = names[q.id], q.id
            out.append(PrintPart(name, bodies[gi], rots[gi], key=key, thin_ok=tuple(thin.get(gi, ()))))
        for q in parts:
            for e in extras.get(q.id, []):
                name, key, solid, rot = e
                out.append(PrintPart(name, solid, rot, key=key, thin_ok=tuple(thin.get(id(e), ()))))
                owners.append(frozenset({q.id}))
        return _Layout(tuple(out), plans, contacts, tuple(owners))

    @staticmethod
    def _plate_gaps(layout: _Layout, plan: SlidePlan, j: JoinSpec, parts: list[PartSpec],
                    joins: list[JoinSpec]) -> tuple[float, ...]:
        """연결판 위 자식 뒷면과 그 뒤 사이 틈 (assembly.plate_gaps). 자식 쪽 = 자식과 한 덩어리인 부품들의 출력 파트."""
        import trimesh

        from app.geometry.mesh import part_to_mesh

        if plan.child_u[1] <= plan.h + 0.5:
            return ()
        group = next(g for g in fused_groups(parts, joins) if j.child in g)
        mine = [pp for pp, own in zip(layout.parts, layout.owners) if own <= set(group)]
        rest = [pp for pp, own in zip(layout.parts, layout.owners) if not own <= set(group)]
        if not mine or not rest:
            return ()
        child_mesh = trimesh.util.concatenate([part_to_mesh(pp.part) for pp in mine])
        other_mesh = trimesh.util.concatenate([part_to_mesh(pp.part) for pp in rest])
        return plate_gaps(plan, child_mesh, other_mesh)

    @staticmethod
    def _contact(plan: SlidePlan, main, extras, bodies, rots, child_group):  # noqa: ANN001, ANN205
        """자식 출력 파트 가운데 연결판에 가장 넓게 닿는 것과 그 닿는 범위. 돌려주는 target = (솔리드, 출력 자세 회전)
        (자식 본체면 묶음 본체·묶음 자세)."""
        f = plan.face_d
        if plan.h <= 0.5:
            return None, None
        slab = _side_profile_solid(plan, [(f, 0.0), (f + 1.0, 0.0), (f + 1.0, plan.h), (f, plan.h)], plan.t0, plan.t1)
        best = None
        for idx, solid in enumerate([main, *[e[2] for e in extras]]):
            inter = solid & slab
            vol = float(inter.volume) if inter is not None else 0.0
            if vol > 1e-3 and (best is None or vol > best[0]):
                best = (vol, idx, inter)
        if best is None:
            return None, None
        _, idx, inter = best
        lo, hi = _bounds(inter)
        t0, t1 = _project(lo, hi, plan.origin, plan.t)
        u0, u1 = _project(lo, hi, plan.origin, plan.u)
        u0, u1 = max(0.0, u0), min(plan.h, u1)
        ok = dovetail_fits(t0, t1) and u1 - u0 >= DOVETAIL_MIN_LENGTH_MM
        contact = _Contact(t0, t1, u0, u1, ok)
        if idx == 0:
            return contact, (bodies[child_group], rots[child_group])
        return contact, (extras[idx - 1][2], extras[idx - 1][3])

    @staticmethod
    def _attach(target, tongue, bodies, extras, child_group) -> list[Any] | None:  # noqa: ANN001
        """혀를 붙인다. 붙인 곳이 따로 출력하는 파트면 그 항목, 묶음 본체면 None."""
        solid = target[0]
        if solid is bodies[child_group]:
            bodies[child_group] = bodies[child_group] + tongue
            return None
        for e in extras:
            if e[2] is solid:
                e[2] = e[2] + tongue
                return e
        return None


def fused_groups(parts: list[PartSpec], joins: list[JoinSpec]) -> list[list[str]]:
    """한 덩어리로 붙는(fused 결합으로 이어진) 부품 묶음. 기준 부품의 묶음이 처음, 나머지는 부품 순서대로.
    슬라이드·끼움 결합은 묶음을 나눈다."""
    root = {p.id: p.id for p in parts}

    def find(x: str) -> str:
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x

    for j in joins:
        if not j.separate:
            a, b = find(j.parent), find(j.child)
            if a != b:
                root[b] = a
    groups: dict[str, list[str]] = {}
    for p in parts:
        groups.setdefault(find(p.id), []).append(p.id)
    first = find(parts[0].id)
    return [groups[first], *[g for r, g in groups.items() if r != first]]


def _group_body(ids: list[str], mains: dict[str, Any], parts: list[PartSpec], joins: list[JoinSpec],
                placed: dict) -> Any:
    """한 덩어리로 붙는 부품 묶음(ids)의 출력 형상: 첫 출력 파트 합 − 빼는 모양(창) − 통로 (+ 끼움 턱, − 끼움 구멍).

    build_assembly 처럼 형상 커널이 닫히지 않은 형상을 내면 (세 부품 이상, 휜 터널의 통로) 통로를 합치기 전에 벽 쪽 부품마다
    조금 넓혀 뚫고 다시 합친다. 처음 방식이 성하면 그대로 둔다."""
    from app.geometry.mesh import mesh_health, part_to_mesh

    mine = set(ids)

    def fuse(cut_first: bool) -> Any:
        shaped = {pid: mains[pid] for pid in ids if pid in mains}
        if cut_first:
            for j in joins:
                if j.passage and not j.plug and j.wall_end[0] in shaped:
                    shaped[j.wall_end[0]] = shaped[j.wall_end[0]] - passage_cutter(placed, j, widen=True)
        body = None
        for solid in shaped.values():
            body = solid if body is None else body + solid
        for q in parts:
            if q.template.cutter and q.id in mine:
                body = body - _plane(placed[q.id]) * q.template.build(q.params)
        for j in joins:
            if not j.passage:
                continue
            if j.wall_end[0] in mine and (j.plug or not cut_first):
                body = body - passage_cutter(placed, j)
            if j.plug and j.port_end[0] in mine:
                body = body + spigot_solid(placed, j)
        return body

    body = fuse(cut_first=False)
    if any(j.passage and not j.plug and j.wall_end[0] in mine for j in joins) \
            and not mesh_health(part_to_mesh(body)).ok:
        other = fuse(cut_first=True)
        if mesh_health(part_to_mesh(other)).ok:
            body = other
    return body


def _best_rotation(mesh, candidates: tuple[np.ndarray, ...] = _DOWN_ROTATIONS) -> np.ndarray:  # noqa: ANN001
    from app.geometry.mesh import to_print_orientation
    from app.validation.checks import overhang_area

    best: tuple[float, float, int] | None = None
    best_rot = candidates[0]
    for i, rot in enumerate(candidates):
        m = to_print_orientation(mesh, rot)
        area = overhang_area(m, 45.0)
        key = (area, float(m.extents[2]), i)
        if best is None or area < best[0] / _TIE - 1.0 or (area <= best[0] * _TIE + 1.0 and key[1:] < best[1:]):
            best, best_rot = key, rot
    return best_rot


def _key(p: TemplateParams) -> str:
    return p.model_dump_json()






@lru_cache(maxsize=64)
def _part_bounds_cached(module: AssemblyTemplate, params_json: str) -> dict[str, tuple]:
    p = module.Params.model_validate_json(params_json)
    parts, joins = module.expand(p)
    placed = place_parts(parts, joins)
    out = {}
    for part in parts:
        if part.template.cutter:
            continue
        bb = (_plane(placed[part.id]) * part.template.build(part.params)).bounding_box()
        out[part.id] = ((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z))
    return out


def _part_bounds(module: AssemblyTemplate, params_json: str) -> dict[str, tuple]:
    return _part_bounds_cached(module, params_json)
