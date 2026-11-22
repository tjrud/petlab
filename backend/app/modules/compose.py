"""조립 해석기: 해석기 출력(AssemblyRequest)을 저장 형태(ResolvedAssembly)로 정한다. 형상은 만들지 않는다.

해석기(LLM·모의 해석기)는 "어느 부품을 어느 부품의 어느 면에 붙이는지"만 적는다. 여기서 연결 표준(템플릿의 role·
attach_order·연결 지점·face_fields·open_port)으로 다음을 정한다.

  - 자식 연결 지점, 결합 방식(slide·plug), 통로 방향(into_parent·into_child) — 아래 결합 표
  - 막힌 면을 옮기기(join_relocated), 벽에 출입구 내기(port_opened), 방과 방 사이 터널 넣기(tunnel_inserted)
  - 통로로 쓴 방에 나갈 출입구 더하기(exit_added), 통로 단면 모양 맞추기(passage_shape_matched)
  - 맞물리는 치수(ties: 터널 내경·출입구 폭은 주인 값 하나를 따른다), 한 면에 여럿 붙일 때의 가로 위치(shift)

결합 표 (부모 연결 지점 = at 을 기준 부품 좌표계에서 부모 연결 지점으로 옮긴 것, 자식 = 그 역할):
  1. 위·아래 면: at 에 위·아래가 없어 고를 수 없다 (위에 얹기는 2단계). 해석기 출력 검증이 막는다
  2. 출입구(port + 벽) ← 터널: 끼움 결합, 통로가 부모 벽을 뚫는다 (into_parent). 터널 끝은 attach_order 순서(end_b 부터).
     터널 내경은 출입구 폭을 따르고, 터널 단면은 출입구 단면 모양으로 정한다
  3. 터널 끝(port, 벽 없음) ← 방(은신처·집): 끼움 결합, 통로가 자식 벽을 뚫는다 (into_child). 방은 attach_order 의 첫 출입구로
  4. 출입구 ← 방: 사이에 터널(f"{방}_link", 가장 짧은 길이)을 넣고 2·3 으로 잇는다
  5. 터널 끝 ← 터널: 지원하지 않는다 (join_unsupported, 2단계 이음 부품)
  6. 벽뿐인 면 ← 터널: open_port 로 출입구를 낼 수 있으면 내고 2 로, 없으면 빈 출입구 면으로 옮기고, 그것도 없으면 face_unavailable
  7. 연결판 자리(mount, 출입구 아님) ← 받침·거치대·램프: 슬라이드 결합 (통로 아님)
  8. 출입구, 또는 출입 면(side)인데 자식이 출입을 막는 부품 ← 받침·거치대: 오른쪽·왼쪽·뒤·앞 중 첫 빈 연결판 면으로 옮긴다
  9. 그 밖 (모래목욕통·집을 다른 부품에, 받침에 다른 부품을): join_unsupported
(6 을 넓혀, 벽뿐인 면에 방을 붙여도 출입구를 내거나 출입구 면으로 옮긴 뒤 4 로 잇는다.)

derived_constraints 는 조립 항목 템플릿(app/modules/composed.ComposedTemplate)의 제약이다. 자동 보정 패스마다 다시 불러,
부품 제약(따르는 값의 제약은 주인 값으로 옮긴다)과 조립에서 생기는 제약(면 크기·높이, 맞춘 높이, 끼움 벽 두께)을 낸다.

엔진의 조립 항목 순서: 부품 파라미터 검증 → resolve (안에서 부품마다 보정) → composed_template 로 템플릿 →
clamp_params(…, max_passes=ASSEMBLY_MAX_PASSES) → rule_issues. 다시 만들 때는 저장된 ResolvedAssembly 만 쓰고
resolve 를 다시 부르지 않는다 (그래서 이 모듈은 형상 지문에 넣지 않는다).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import ValidationError

from app.modules.assembly import (
    PLUG_CLEARANCE_MM,
    PLUG_MIN_LENGTH_MM,
    PLUG_MIN_RING_MM,
    PLUG_SPIGOT_MM,
    PLUG_TIP_GAP_MM,
    AssemblyError,
    JoinSpec,
    PartSpec,
    place_parts,
)
from app.modules.structure import (
    MAX_PARTS,
    AssemblyRequest,
    Connection,
    FixedValue,
    ResolvedAssembly,
    ResolvedJoin,
    ResolvedPart,
    Tie,
    link_id,
    part_names,
    split_ref,
)
from app.templates.base import (
    Anchor,
    ParamConstraint,
    RuleContext,
    Template,
    TemplateParams,
)
from app.validation.autofix import PART_LABEL_SEP, clamp_params, field_bounds
from app.validation.report import Issue, Severity

if TYPE_CHECKING:
    from app.modules.composed import ComposedTemplate

# 한 면에 여럿 붙일 때 이웃 부품 사이 틈 = 몸이 지나가는 폭(종별 passable_min) + 이 여유.
# 둥근 받침(그릇 받침의 D자 앞쪽)끼리, 또는 램프 옆면과 둥근 받침이 거의 맞닿으면 앞쪽으로 벌어지는 V자 틈이
# 끼임 위험 구간을 지나므로 (slot_gaps), 붙이지 않고 지나갈 수 있게 띄운다
SIBLING_GAP_MM = 1.0
# 면 가장자리와 붙인 부품 사이 최소 여유 (한쪽)
EDGE_MARGIN_MM = 3.0
# 조립 항목 보정 패스 수 (부품 제약 → 따르는 치수 → 부모 면 크기로 사슬이 길다)
ASSEMBLY_MAX_PASSES = 12
# 끼움 결합: 통로 쪽 벽 두께 ≥ 끼움 턱 + 틈새 + 덮는 고리, 벽 쪽 벽 두께 ≥ 끼움 턱 최소 길이 + 끝 여유
PLUG_PORT_WALL_MIN_MM = PLUG_SPIGOT_MM + PLUG_CLEARANCE_MM + PLUG_MIN_RING_MM
PLUG_DOOR_WALL_MIN_MM = PLUG_MIN_LENGTH_MM + PLUG_TIP_GAP_MM

# 오류 코드 (resolve 가 Issue 하나로 돌려준다)
JOIN_UNSUPPORTED = "join_unsupported"
FACE_UNAVAILABLE = "face_unavailable"
TOO_MANY_PARTS = "too_many_parts"
INVALID_PARAMS = "invalid_params"
UNKNOWN_TEMPLATE = "unknown_template"
ERROR_CODES = (JOIN_UNSUPPORTED, FACE_UNAVAILABLE, TOO_MANY_PARTS, INVALID_PARAMS, UNKNOWN_TEMPLATE)
# 안내 코드 (details.part = 그 부품 id)
INFO_CODES = ("join_relocated", "port_opened", "tunnel_inserted", "passage_shape_matched", "exit_added")

# 기준 부품 좌표계의 옆면 방향 (회전 0° 에서 front = −Y)
SIDE_VEC: dict[str, tuple[float, float, float]] = {
    "front": (0.0, -1.0, 0.0), "back": (0.0, 1.0, 0.0), "left": (-1.0, 0.0, 0.0), "right": (1.0, 0.0, 0.0),
}
# auto·옮기기 순서: 받침·거치대·램프는 옆면부터, 통로는 앞·뒤부터 (그다음 터널 남은 끝)
ACCESSORY_SIDES = ("right", "left", "back", "front")
PASSAGE_SIDES = ("front", "back")
_OPPOSITE = {"front": "back", "back": "front", "left": "right", "right": "left"}
SIDE_KO = {"front": "앞", "back": "뒤", "left": "왼쪽", "right": "오른쪽", "free_end": "터널 끝"}
PROFILE_KO = {"round_arch": "둥근 아치", "pointed_arch": "뾰족 아치", "tube": "둥근 관", "box": "네모",
              "house": "집 모양"}
# 방향이 이만큼 맞으면 그 면으로 본다 (휜 터널 끝에 붙은 방처럼 기준 부품과 비스듬한 부품: 가장 가까운 면)
_FACING = 0.7


class ResolveError(Exception):
    """해석할 수 없는 연결 (Issue 하나로 바꿔 돌려준다)."""

    def __init__(self, code: str, message: str, part: str | None = None, **details: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {"part": part, **details} if part is not None else dict(details)


# ── 연결 지점 종류 ──


def is_door(a: Anchor) -> bool:
    """출입구: 통로 자리이면서 뚫을 벽이 있다 (은신처 앞, 집 출입구·연결부)."""
    return a.port is not None and a.wall_mm is not None


def is_end(a: Anchor) -> bool:
    """터널 끝: 통로 자리이고 벽이 없다."""
    return a.port is not None and a.wall_mm is None


def is_plain_wall(a: Anchor) -> bool:
    """벽뿐인 면: 뚫을 수 있지만 통로가 아니다 (출입구를 낼 수 있는지는 open_port 가 정한다)."""
    return a.port is None and a.wall_mm is not None


def can_slide(a: Anchor, child: Template, access: tuple[str, ...] | set[str] = ("front", "back", "left", "right"),
              ) -> bool:
    """슬라이드 결합을 받을 수 있는 면인지: 연결판 자리가 있고, 출입구가 아니고, 출입 면(부모 features().access_sides 에
    든 side)이면 출입을 막지 않는 부품(램프)만. 은신처 뒷면처럼 side 이름만 있고 출입 면이 아닌 벽은 받는다."""
    return a.mount is not None and a.port is None and (a.side is None or a.side not in access or child.passes_access)


_HANGUL_FIRST, _HANGUL_LAST = 0xAC00, 0xD7A3


def _w(word: str, pair: str) -> str:
    """낱말 + 받침에 맞는 조사. pair: "이/가", "을/를", "과/와", "은/는", "으로/로" (앞쪽이 받침 있을 때)."""
    with_b, without = pair.split("/")
    code = ord(word[-1]) if word else 0
    if not _HANGUL_FIRST <= code <= _HANGUL_LAST:
        if word and word[-1].isdigit():  # "은신처 2": 숫자 읽기(이)의 받침
            code = ord("영일이삼사오육칠팔구"[int(word[-1])])
        else:
            return f"{word}{with_b}({without})"
    final = (code - _HANGUL_FIRST) % 28
    if pair == "으로/로":
        return word + ("로" if final in (0, 8) else "으로")
    return word + (with_b if final else without)


def _horizontal(a: Anchor) -> bool:
    return abs(float(a.normal[2])) < 1e-6


def nearest_side(v: np.ndarray) -> str:
    """방향 v 에 가장 가까운 옆면 이름 (기준 부품 좌표계)."""
    return max(SIDE_VEC, key=lambda s: float(np.dot(v, SIDE_VEC[s])))


# ── 해석 중 상태 ──


@dataclass
class _Join:
    parent: str
    parent_anchor: str
    child: str
    child_anchor: str
    mount: str
    passage: Any  # False | "into_parent" | "into_child"
    shift: float = 0.0

    def spec(self) -> JoinSpec:
        return JoinSpec(self.parent, self.parent_anchor, self.child, self.child_anchor, shift=self.shift,
                        passage=self.passage is not False, mount=self.mount, reverse=self.passage == "into_child")

    def resolved(self) -> ResolvedJoin:
        return ResolvedJoin(parent=f"{self.parent}.{self.parent_anchor}", child=f"{self.child}.{self.child_anchor}",
                            mount=self.mount, passage=self.passage, shift=self.shift)  # type: ignore[arg-type]


@dataclass
class _State:
    ctx: RuleContext
    templates: dict[str, Template]
    params: dict[str, TemplateParams]
    order: list[str]
    label: str
    item_index: int | None
    names: dict[str, str] = field(default_factory=dict)
    joins: list[_Join] = field(default_factory=list)
    ties: dict[str, str] = field(default_factory=dict)  # follower → owner (모두 "부품id.경로")
    fixed: dict[str, FixedValue] = field(default_factory=dict)
    faces: dict[str, str] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    inserted: set[str] = field(default_factory=set)

    # ── 조회 ──

    def anchors(self, pid: str) -> dict[str, Anchor]:
        return self.templates[pid].anchors(self.params[pid])

    def used(self, pid: str, anchor: str) -> list[_Join]:
        return [j for j in self.joins
                if (j.parent == pid and j.parent_anchor == anchor) or (j.child == pid and j.child_anchor == anchor)]

    def free(self, pid: str, anchor: str) -> bool:
        return not self.used(pid, anchor)

    def parent_join(self, pid: str) -> _Join | None:
        return next((j for j in self.joins if j.child == pid), None)

    def rotation(self, pid: str) -> np.ndarray:
        """지금까지 이은 부품을 놓았을 때 pid 의 회전 (부품 좌표 → 기준 부품 좌표)."""
        placed_ids = [self.order[0], *(j.child for j in self.joins)]
        parts = [PartSpec(q, self.templates[q], self.params[q]) for q in self.order if q in placed_ids]
        try:
            placed = place_parts(parts, [j.spec() for j in self.joins])
        except AssemblyError as e:  # pragma: no cover - 연결 지점은 해석기가 고른 것만 쓴다
            raise ResolveError(JOIN_UNSUPPORTED, f"{self.label}: {e}", pid) from e
        return placed[pid].rotation

    def anchor_at(self, pid: str, side: str) -> str | None:
        """기준 부품 좌표계의 면 side 를 향하는 pid 의 옆 연결 지점 (위·아래 면은 고르지 않는다). 없으면 None."""
        local = self.rotation(pid).T @ np.asarray(SIDE_VEC[side])
        best, best_dot = None, _FACING
        for name, a in self.anchors(pid).items():
            if not _horizontal(a):
                continue
            d = float(np.dot(np.asarray(a.normal, dtype=float), local))
            if d > best_dot + 1e-9:
                best, best_dot = name, d
        return best

    def side_of(self, pid: str, anchor: str) -> str:
        """pid 의 연결 지점 anchor 가 기준 부품 좌표계에서 향하는 면."""
        n = np.asarray(self.anchors(pid)[anchor].normal, dtype=float)
        return nearest_side(self.rotation(pid) @ n)

    def owner(self, path: str) -> str:
        while path in self.ties:
            path = self.ties[path]
        return path

    # ── 안내 ──

    def info(self, code: str, part: str, message: str, **details: Any) -> None:
        self.issues.append(Issue(code=code, severity=Severity.info, auto_fixed=True, item_index=self.item_index,
                                 message_ko=f"{self.label}: {message}", details={"part": part, **details}))

    # ── 파라미터 바꾸기 ──

    def set_params(self, pid: str, q: TemplateParams) -> None:
        """해석기가 정한 값으로 바꾸고 바뀐 값을 fixed 에 적는다."""
        before = _leaves(self.params[pid].model_dump())
        after = _leaves(q.model_dump())
        for path, v in after.items():
            if before.get(path) != v:
                self.fixed[f"{pid}.{path}"] = v
        self.params[pid] = q

    def set_value(self, pid: str, path: str, value: Any) -> None:
        data = self.params[pid].model_dump()
        _set(data, path, value)
        self.set_params(pid, type(self.params[pid]).model_validate(data))


def _leaves(values: dict, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in values.items():
        if isinstance(v, dict):
            out.update(_leaves(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def _get(obj: Any, path: str) -> Any:
    for name in path.split("."):
        obj = obj[name] if isinstance(obj, dict) else getattr(obj, name)
    return obj


def _set(values: dict, path: str, value: Any) -> None:
    *heads, last = path.split(".")
    for name in heads:
        values = values[name]
    values[last] = value


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ── 해석 ──


def default_templates() -> dict[str, Template]:
    from app.templates.registry import primitives

    return primitives()


def resolve(
    req: AssemblyRequest,
    params: Mapping[str, TemplateParams | Mapping[str, Any]] | None,
    ctx: RuleContext,
    *,
    templates: Mapping[str, Template] | None = None,
    item_index: int | None = None,
    label_ko: str | None = None,
) -> tuple[ResolvedAssembly, dict[str, TemplateParams], list[Issue]] | Issue:
    """해석기 출력 → (저장 형태, 부품 id → 파라미터(끼운 터널 포함), 안내 이슈). 해석할 수 없으면 오류 Issue 하나.

    params: 부품 id → 그 부품 파라미터 (Params 또는 dict). None 이면 req.parts[].params 를 쓴다.
    ctx: 새 설계를 보정하는 규칙 문맥 (엔진의 fit_ctx). 부품마다 먼저 보정해 종 규칙이 정하는 구조 값
    (여러 마리일 때 출입구 2개 등)을 연결 지점을 고르기 전에 정한다. 그 보정 안내(param_adjusted)도 함께 돌려준다.
    형상은 만들지 않는다 (연결 지점 좌표와 해석적 외형 크기만 쓴다)."""
    tmpl = dict(templates) if templates is not None else default_templates()
    label = label_ko or req.name_ko or "조립 구조물"

    def err(code: str, message: str, part: str | None = None, **details: Any) -> Issue:
        d = {"part": part, **details} if part is not None else dict(details)
        return Issue(code=code, severity=Severity.error, item_index=item_index, message_ko=f"{label}: {message}",
                     details=d)

    parts: dict[str, Template] = {}
    values: dict[str, TemplateParams] = {}
    for pr in req.parts:
        t = tmpl.get(pr.template)
        if t is None:
            return err(UNKNOWN_TEMPLATE, f"지원하지 않는 부품입니다 ({pr.template})", pr.id, template=pr.template)
        if not t.composable:
            return err(JOIN_UNSUPPORTED, f"{_w(t.display_name_ko, '은/는')} 다른 부품과 이어 붙일 수 없습니다", pr.id,
                       template=pr.template)
        raw = pr.params if params is None else params.get(pr.id, pr.params)
        try:
            values[pr.id] = raw if isinstance(raw, t.Params) else t.Params.model_validate(dict(raw))
        except ValidationError as e:
            return err(INVALID_PARAMS, f"{t.display_name_ko}({pr.id})의 파라미터가 허용 범위를 벗어났습니다", pr.id,
                       path=pr.id, errors=e.errors(include_url=False, include_context=False))
        parts[pr.id] = t

    st = _State(ctx=ctx, templates=parts, params=values, order=[p.id for p in req.parts], label=label,
                item_index=item_index)
    st.names = _names(st)
    # 1. 부품마다 보정 (구조 값을 먼저 정한다)
    for pid in list(st.order):
        _clamp_part(st, pid)
    try:
        # 2. 뿌리부터 너비 우선, connections 순서로 잇는다
        for c in req.walk():
            _connect(st, c)
        # 3. 통로로 쓴 방에 나갈 출입구
        _fill_exits(st)
        # 5. 한 면에 여럿: 가로 위치
        _layout_siblings(st)
    except ResolveError as e:
        return Issue(code=e.code, severity=Severity.error, item_index=item_index, message_ko=e.message,
                     details=e.details)
    # 6. 저장 형태 (결합은 뿌리부터 너비 우선: 고친 명세를 다시 해석해도 같은 순서가 되게)
    st.joins = _bfs(st.order[0], st.joins)
    resolved = ResolvedAssembly(
        root=st.order[0],
        parts=[ResolvedPart(id=pid, template=st.templates[pid].key) for pid in st.order],
        joins=[j.resolved() for j in st.joins],
        ties=[Tie(follower=f, owner=o) for f, o in st.ties.items()],
        fixed=dict(st.fixed),
        faces=dict(st.faces),  # type: ignore[arg-type]
    )
    return resolved, {pid: st.params[pid] for pid in st.order}, st.issues


def _bfs(root: str, joins: list[_Join]) -> list[_Join]:
    """결합을 뿌리부터 너비 우선 순서로 (같은 부모의 자식끼리는 원래 순서)."""
    out: list[_Join] = []
    queue = [root]
    while queue:
        pid = queue.pop(0)
        for j in joins:
            if j.parent == pid:
                out.append(j)
                queue.append(j.child)
    return out


def _names(st: _State) -> dict[str, str]:
    rp = [ResolvedPart(id=pid, template=st.templates[pid].key) for pid in st.order]
    return part_names(rp, {t.key: t.display_name_ko for t in st.templates.values()})


def _clamp_part(st: _State, pid: str) -> None:
    """부품 하나를 그 부품 제약으로만 보정한다. 안내 문구는 조립 항목 보정과 같은 모양 ("라벨: 부품 · 파라미터 …")."""
    t = st.templates[pid]
    marker = "\x00"
    q, issues = clamp_params(t, st.params[pid], st.ctx, item_index=st.item_index, label_ko=marker)
    st.params[pid] = q
    for i in issues:
        if i.code != "param_adjusted":
            continue  # 부품만으로 풀 수 없는 충돌은 조립 항목 보정이 (따르는 값을 주인으로 옮긴 뒤) 다시 판단한다
        msg = i.message_ko.replace(f"{marker}: ", f"{st.label}: {st.names[pid]}{PART_LABEL_SEP}", 1)
        st.issues.append(i.model_copy(update={
            "message_ko": msg, "details": {**i.details, "field": f"{pid}.{i.details['field']}", "part": pid}}))


def _connect(st: _State, c: Connection) -> None:
    parent, child = c.to, c.part
    tp, tc = st.templates[parent], st.templates[child]
    pn, cn = st.names[parent], st.names[child]
    if tp.role not in ("host", "room_host", "connector"):
        raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: {pn}에는 다른 부품을 붙일 수 없습니다 ({cn})", child,
                           parent=parent)
    if tc.role == "accessory":
        if tp.role == "connector":
            raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: {_w(cn, '은/는')} {pn} 끝이 아니라 은신처·집·모래목욕통 옆면에 "
                                                 "붙입니다", child, parent=parent)
        _attach_accessory(st, parent, child, c.at)
    elif tc.role == "connector":
        if tp.role == "connector":
            raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: {pn} 끝에 {_w(cn, '을/를')} 바로 이을 수는 아직 없습니다", child,
                               parent=parent)
        if tp.role != "room_host":
            raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: {pn}에는 터널을 이을 수 없습니다 (출입구가 없습니다)",
                               child, parent=parent)
        _attach_connector(st, parent, child, c.at)
    elif tc.role == "room_host":
        if tp.role == "connector":
            _attach_room_to_end(st, parent, child, c.at)
        elif tp.role == "room_host":
            _insert_tunnel(st, parent, child, c.at)
        else:
            raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: {pn}에는 {_w(cn, '을/를')} 이을 수 없습니다 (출입구가 없습니다)",
                               child, parent=parent)
    else:
        raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: {_w(cn, '은/는')} 다른 부품에 붙일 수 없어 기준(첫) 부품으로만 씁니다",
                           child, parent=parent)


def _add_join(st: _State, j: _Join, face: str) -> None:
    st.joins.append(j)
    st.faces[j.child] = face


# ── 행 7·8: 받침·거치대·램프 ──


def _attach_accessory(st: _State, parent: str, child: str, at: str) -> None:
    tc = st.templates[child]
    anchors = st.anchors(parent)
    access = set(st.templates[parent].features(st.params[parent]).access_sides)
    rot = st.rotation(parent)
    if not np.allclose(np.abs(rot), np.round(np.abs(rot)), atol=1e-6):
        # 연결판 자리는 조립 좌표의 축 정렬 상자로 정한다 (assembly.slide_plan): 비스듬한 부모면 연결판이 면보다 넓어진다
        raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: 비스듬히 놓인 {st.names[parent]}(휜 터널 끝의 방)에는 "
                                             f"{_w(st.names[child], '을/를')} 끼울 수 없습니다", child, parent=parent)

    def ok(name: str | None) -> bool:
        return name is not None and can_slide(anchors[name], tc, access)

    def unused(name: str | None) -> bool:
        return ok(name) and st.free(parent, name)  # type: ignore[arg-type]

    candidates = [st.anchor_at(parent, s) for s in ACCESSORY_SIDES]
    chosen: str | None = None
    if at in SIDE_VEC:
        want = st.anchor_at(parent, at)
        if ok(want):
            chosen = want  # 같은 면에 여럿 붙이면 나란히 놓는다 (_layout_siblings)
        else:
            chosen = next((n for n in candidates if unused(n)), None)
            if chosen is None:
                raise ResolveError(FACE_UNAVAILABLE, f"{st.label}: {_w(st.names[child], '을/를')} 붙일 빈 옆면이 "
                                                     f"{st.names[parent]}에 없습니다", child, parent=parent)
            why = _why_not_slide(anchors[want] if want else None, tc, access)
            to = st.side_of(parent, chosen)
            st.info("join_relocated", child,
                    f"{_w(st.names[child], '을/를')} {st.names[parent]} {SIDE_KO[at]} 대신 {SIDE_KO[to]}에 붙였습니다. {why}",
                    parent=parent, **{"from": at, "to": to})
    else:
        chosen = next((n for n in candidates if unused(n)), None) or next((n for n in candidates if ok(n)), None)
        if chosen is None:
            raise ResolveError(FACE_UNAVAILABLE, f"{st.label}: {_w(st.names[child], '을/를')} 붙일 옆면이 "
                                                 f"{st.names[parent]}에 없습니다", child, parent=parent)
    slide = tc.attach_order.get("slide", ())
    child_anchor = next((n for n in slide if n in st.anchors(child)), None)
    if child_anchor is None:
        raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: {_w(st.names[child], '은/는')} 옆면에 끼울 수 없습니다", child)
    _add_join(st, _Join(parent, chosen, child, child_anchor, "slide", False), st.side_of(parent, chosen))


def _why_not_slide(a: Anchor | None, child: Template, access: set[str]) -> str:
    if a is None:
        return "그쪽에는 붙일 면이 없습니다."
    if a.port is not None:
        return "출입구 면에는 터널만 이을 수 있습니다."
    if a.side in access and not child.passes_access:
        return "드나드는 면을 막지 않도록 옮겼습니다."
    return "그 면에는 받침을 끼울 연결판 자리가 없습니다."


# ── 행 2·6: 방 출입구에 터널 ──


def _open(st: _State, pid: str, name: str) -> bool:
    """벽뿐인 면 name 에 출입구를 낸다 (open_port). 냈으면 True."""
    t = st.templates[pid]
    q = t.open_port(st.params[pid], name)
    if q is None:
        return False
    a = t.anchors(q).get(name)
    if a is None or not is_door(a):
        return False
    st.set_params(pid, q)
    return True


def _usable_door(st: _State, pid: str, name: str | None, allow_open: bool) -> str | None:
    """name 이 비어 있는 출입구면 "door", (allow_open 이고) 출입구를 낼 수 있는 빈 벽이면 "open", 아니면 None."""
    if name is None or not st.free(pid, name):
        return None
    a = st.anchors(pid)[name]
    if is_door(a):
        return "door"
    if not (allow_open and is_plain_wall(a)):
        return None
    t = st.templates[pid]
    q = t.open_port(st.params[pid], name)
    b = t.anchors(q).get(name) if q is not None else None
    return "open" if b is not None and is_door(b) else None


def _pick_door(st: _State, parent: str, child: str, at: str) -> str:
    """통로를 이을 부모 출입구 (필요하면 출입구를 내고 안내). 행 2·6 과 옮기기."""
    tp = st.templates[parent]
    pn, cn = st.names[parent], st.names[child]
    requested = at in SIDE_VEC
    sides = [at] if requested else list(PASSAGE_SIDES)
    chosen = kind = None
    for s in sides:
        name = st.anchor_at(parent, s)
        k = _usable_door(st, parent, name, allow_open=True)
        if k:
            chosen, kind = name, k
            break
    relocated = False
    if chosen is None:
        # 빈 출입구 면으로 (있는 출입구 먼저, 그다음 출입구를 낼 수 있는 면)
        order = [n for n in tp.attach_order.get("passage", ()) if n in st.anchors(parent)]
        for allow in (False, True):
            for n in order:
                k = _usable_door(st, parent, n, allow_open=allow)
                if k:
                    chosen, kind = n, k
                    break
            if chosen:
                break
        relocated = requested
    if chosen is None:
        raise ResolveError(FACE_UNAVAILABLE, f"{st.label}: {pn}에 {_w(cn, '을/를')} 이을 빈 출입구가 없고 새로 낼 수 있는 "
                                             "면도 없습니다", child, parent=parent)
    if kind == "open":
        _open(st, parent, chosen)
        st.info("port_opened", parent, f"{pn} {SIDE_KO[st.side_of(parent, chosen)]} 면에 출입구를 내고 "
                                       f"{_w(cn, '을/를')} 이었습니다", child=child, anchor=chosen)
    if relocated:
        to = st.side_of(parent, chosen)
        want = st.anchor_at(parent, at)
        why = ("그 면은 이미 다른 부품을 이었습니다." if want is not None and not st.free(parent, want)
               else "그 면에는 출입구를 낼 수 없습니다.")
        st.info("join_relocated", child, f"{_w(cn, '을/를')} {pn} {SIDE_KO[at]} 대신 {SIDE_KO[to]} 출입구에 이었습니다. {why}",
                parent=parent, **{"from": at, "to": to})
    return chosen


def _attach_connector(st: _State, parent: str, child: str, at: str) -> None:
    door = _pick_door(st, parent, child, at)
    tc = st.templates[child]
    end = next((n for n in tc.attach_order.get("passage", ())
                if n in st.anchors(child) and is_end(st.anchors(child)[n]) and st.free(child, n)), None)
    if end is None:
        raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: {st.names[child]}에 이을 끝이 없습니다", child)
    _add_join(st, _Join(parent, door, child, end, "plug", "into_parent"), st.side_of(parent, door))
    _tie_port(st, (parent, door), (child, end))
    _match_profile(st, tunnel=(child, end), door=(parent, door))


# ── 행 3: 터널 끝에 방 ──


def _attach_room_to_end(st: _State, tunnel: str, room: str, at: str) -> None:
    tt = st.templates[tunnel]
    tn, rn = st.names[tunnel], st.names[room]
    anchors = st.anchors(tunnel)
    ends = [n for n in reversed(tt.attach_order.get("passage", ())) if n in anchors and is_end(anchors[n])]
    chosen = face = None
    if at in SIDE_VEC:
        name = st.anchor_at(tunnel, at)
        if name in ends and st.free(tunnel, name):  # type: ignore[arg-type]
            chosen, face = name, at
    if chosen is None:
        chosen = next((n for n in ends if st.free(tunnel, n)), None)
        face = "free_end"
        if chosen is None:
            raise ResolveError(FACE_UNAVAILABLE, f"{st.label}: {tn}의 두 끝을 이미 모두 이어 {_w(rn, '을/를')} 이을 수 없습니다",
                               room, parent=tunnel)
        if at in SIDE_VEC:
            st.info("join_relocated", room, f"{_w(rn, '을/를')} {tn}의 남은 끝에 이었습니다 ({SIDE_KO[at]}에는 {tn} 끝이 "
                                            "없습니다).", parent=tunnel, **{"from": at, "to": "free_end"})
    door = _room_door(st, room, tunnel)
    _add_join(st, _Join(tunnel, chosen, room, door, "plug", "into_child"), face)  # type: ignore[arg-type]
    _tie_port(st, (tunnel, chosen), (room, door))
    _match_profile(st, tunnel=(tunnel, chosen), door=(room, door))


def _room_door(st: _State, room: str, other: str) -> str:
    """방이 터널 끝에 붙을 출입구: attach_order 의 첫 출입구, 없으면 출입구를 낼 수 있는 첫 면."""
    tr = st.templates[room]
    order = [n for n in tr.attach_order.get("passage", ()) if n in st.anchors(room)]
    for n in order:
        if st.free(room, n) and is_door(st.anchors(room)[n]):
            return n
    for n in order:
        if st.free(room, n) and is_plain_wall(st.anchors(room)[n]) and _open(st, room, n):
            st.info("port_opened", room, f"{st.names[room]}에 출입구를 내고 {_w(st.names[other], '을/를')} 이었습니다",
                    child=other, anchor=n)
            return n
    raise ResolveError(FACE_UNAVAILABLE, f"{st.label}: {st.names[room]}에 {_w(st.names[other], '을/를')} 이을 출입구가 없습니다",
                       room, parent=other)


# ── 행 4: 방과 방 사이 터널 ──


def _insert_tunnel(st: _State, parent: str, room: str, at: str) -> None:
    if len(st.order) >= MAX_PARTS:
        raise ResolveError(TOO_MANY_PARTS, f"{st.label}: {_w(st.names[parent], '과/와')} {st.names[room]} 사이에 터널을 넣으면 "
                                           f"부품이 {MAX_PARTS}개를 넘습니다", room, parent=parent)
    tunnel_t = next((t for t in default_templates().values() if t.role == "connector"), None)
    if tunnel_t is None:  # pragma: no cover - 터널 템플릿은 늘 있다
        raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: 방끼리 이을 터널이 없습니다", room)
    door = _pick_door(st, parent, room, at)
    link = link_id(room, set(st.order))
    st.order.insert(st.order.index(room), link)
    st.templates[link] = tunnel_t
    st.inserted.add(link)
    q = tunnel_t.default_params(st.ctx)
    data = q.model_dump()
    lo, _ = field_bounds(tunnel_t.Params, "length_mm")
    if lo is not None:
        data["length_mm"] = lo  # 가장 짧게 (내경에 맞춘 최소 길이는 보정이 올린다)
    pf = st.templates[parent].face_fields(st.params[parent], door)
    tf = tunnel_t.face_fields(q, tunnel_t.attach_order["passage"][0])
    if pf.port and tf.port:
        data[tf.port] = _get(st.params[parent], pf.port)
    st.params[link] = tunnel_t.Params.model_validate(data)
    st.names = _names(st)
    _clamp_part(st, link)
    end = next(n for n in tunnel_t.attach_order["passage"] if n in st.anchors(link))
    _add_join(st, _Join(parent, door, link, end, "plug", "into_parent"), st.side_of(parent, door))
    _tie_port(st, (parent, door), (link, end))
    _match_profile(st, tunnel=(link, end), door=(parent, door))
    st.info("tunnel_inserted", link, f"{_w(st.names[parent], '과/와')} {_w(st.names[room], '을/를')} 터널로 이었습니다 "
                                     "(방끼리는 출입구에 터널을 끼워 잇습니다)", parent=parent, child=room)
    _attach_room_to_end(st, link, room, "free_end")


# ── 맞물리는 치수·단면 ──


def _tie_port(st: _State, upstream: tuple[str, str], downstream: tuple[str, str]) -> None:
    """통로 결합: 아래쪽(새로 붙인) 부품의 통로 크기 ← 위쪽 통로 크기의 주인 값."""
    (up, ua), (down, da) = upstream, downstream
    uf = st.templates[up].face_fields(st.params[up], ua).port
    df = st.templates[down].face_fields(st.params[down], da).port
    if not uf or not df:
        return
    owner = st.owner(f"{up}.{uf}")
    follower = f"{down}.{df}"
    if follower != owner and follower not in st.ties:
        st.ties[follower] = owner


def _match_profile(st: _State, tunnel: tuple[str, str], door: tuple[str, str]) -> None:
    """통로 쪽 단면 모양을 출입구 단면 모양으로 정한다. 터널의 다른 끝이 이미 다른 모양에 맞춰졌으면 오류."""
    (tid, ta), (did, da) = tunnel, door
    profile = st.anchors(did)[da].profile
    pf = st.templates[tid].face_fields(st.params[tid], ta).profile
    if profile is None or pf is None:
        return
    key = f"{tid}.{pf}"
    if key in st.fixed and st.fixed[key] != profile:
        raise ResolveError(JOIN_UNSUPPORTED, f"{st.label}: {st.names[tid]} 양 끝의 출입구 단면 모양이 달라 "
                                             f"({PROFILE_KO.get(str(st.fixed[key]), st.fixed[key])}, "
                                             f"{PROFILE_KO.get(profile, profile)}) 한 터널로 이을 수 없습니다",
                           tid, parent=did)
    old = _get(st.params[tid], pf)
    if old != profile:
        st.set_value(tid, pf, profile)
        if tid not in st.inserted:
            st.info("passage_shape_matched", tid, f"{st.names[tid]} 단면을 {st.names[did]} 출입구와 같은 "
                                                  f"{_w(PROFILE_KO.get(profile, profile), '으로/로')} 바꿨습니다 (출입구 둘레에 틈이 남지 "
                                                  "않게)", **{"from": old, "to": profile})
    st.fixed[key] = profile


# ── 3. 나갈 출입구 ──


def _fill_exits(st: _State) -> None:
    """통로로 출입구를 쓴 방에 비어 있는 출입구가 하나도 없으면, 쓴 출입구의 반대쪽(그다음 attach_order 순서) 빈 벽에
    출입구를 낸다 (은신처: 출입구 2개, 집: 연결부 더하기)."""
    for pid in st.order:
        t = st.templates[pid]
        if t.role != "room_host":
            continue
        anchors = st.anchors(pid)
        through = [n for n, a in anchors.items()
                   if is_door(a) and any(j.passage is not False for j in st.used(pid, n))]
        if not through:
            continue
        if any(a.port is not None and st.free(pid, n) for n, a in anchors.items()):
            continue
        order = [_OPPOSITE[n] for n in through if n in _OPPOSITE] + list(t.attach_order.get("passage", ()))
        for n in dict.fromkeys(order):
            if n in anchors and st.free(pid, n) and is_plain_wall(anchors[n]) and _open(st, pid, n):
                st.info("exit_added", pid, f"{st.names[pid]}의 출입구를 통로로 이어 {SIDE_KO[st.side_of(pid, n)]}에 "
                                           "드나들 출입구를 하나 더 냈습니다", anchor=n)
                break


# ── 5. 한 면에 여럿 ──


def face_width(t: Template, p: TemplateParams, anchor: str) -> float:
    """부품을 연결 지점 anchor 로 붙였을 때 붙는 면의 가로 방향으로 차지하는 폭 (해석적 외형 크기, 축에 나란한 면)."""
    a = t.anchors(p)[anchor]
    n, u = np.asarray(a.normal, dtype=float), np.asarray(a.up, dtype=float)
    tb = np.abs(np.cross(u, n))
    return float(tb @ np.asarray(t.envelope(p), dtype=float))


def _slide_groups(joins: list[Any]) -> dict[tuple[str, str], list[Any]]:
    groups: dict[tuple[str, str], list[Any]] = {}
    for j in joins:
        if j.mount == "slide":
            groups.setdefault((j.parent_id if isinstance(j, ResolvedJoin) else j.parent,
                               j.parent_anchor), []).append(j)
    return groups


def sibling_gap(ctx: RuleContext) -> float:
    """한 면에 나란히 붙인 부품 사이 틈 (끼임 위험 구간을 넘어 몸이 지나갈 수 있는 폭)."""
    return ctx.size.gap_trap.passable_min_mm + SIBLING_GAP_MM


def _layout_siblings(st: _State) -> None:
    """같은 면에 슬라이드로 붙인 부품이 둘 이상이면 connections 순서로 왼쪽부터(바깥에서 볼 때) 나란히,
    가운데 맞춰 sibling_gap 씩 띄운다."""
    gap = sibling_gap(st.ctx)
    for (pid, anchor), group in _slide_groups(st.joins).items():
        if len(group) < 2:
            continue
        a = st.anchors(pid)[anchor]
        center = (a.mount[0] + a.mount[1]) / 2 if a.mount is not None else 0.0
        widths = [face_width(st.templates[j.child], st.params[j.child], j.child_anchor) for j in group]
        total = sum(widths) + gap * (len(group) - 1)
        x = center - total / 2
        for j, w in zip(group, widths):
            j.shift = round(x + w / 2, 3)
            x += w + gap


# ── 조립 항목 제약 (자동 보정 패스마다) ──


@dataclass(frozen=True)
class _Level:
    follower: str          # "램프id.height_mm"
    value: float           # 맞출 높이 = 부모 면 연결판 높이
    owner: str | None      # 부모 면 높이 파라미터 ("hide.height_mm"), 없으면 None
    offset: float          # follower = owner + offset
    parent: str
    child: str


def derived_constraints(resolved: ResolvedAssembly, p: TemplateParams, ctx: RuleContext,
                        templates: Mapping[str, Template] | None = None) -> list[ParamConstraint]:
    """조립 항목의 제약 (ComposedTemplate.constraints). 필드는 "부품id.경로".

    - 부품마다 자기 제약 + assembly_constraints + 붙은 연결 지점마다 joined_constraints. 따르는 값(ties)과 부모 면 높이에
      맞춘 높이(램프 꼭대기)에 걸린 제약은 주인 값으로 옮긴다 (Bind 의 역: 같은 값이므로 같은 범위, 높이는 차이만큼)
    - 끼움 결합 벽 두께 하한 (통로 쪽 PLUG_PORT_WALL_MIN_MM, 벽 쪽 PLUG_DOOR_WALL_MIN_MM)
    - 부모 면 가로: 붙인 부품 폭 합 + 사이 틈(sibling_gap) + 양쪽 여유가 연결판 자리보다 넓으면 그만큼 넓힌다 (늘 키우기만 한다)
    - 부모 면 높이: 붙인 부품의 face_needs (그릇 받침: 최소, 물병 거치대: 최대)
    - 같게: 따르는 값 = 주인 값, 맞춘 높이 = 부모 면 연결판 높이, 해석기가 정한 수 값(fixed)
    - 따르는 값의 필드 범위(Field ge/le)를 주인 값 범위로 (주인이 따르는 쪽이 받을 수 없는 값으로 가지 않게)"""
    tmpl = dict(templates) if templates is not None else default_templates()
    parts = {rp.id: tmpl[rp.template] for rp in resolved.parts}
    q = {pid: getattr(p, pid) for pid in parts}
    names = part_names(resolved.parts, {t.key: t.display_name_ko for t in parts.values()})
    ties = {t.follower: t.owner for t in resolved.ties}
    levels = _levels(resolved, parts, q)
    level_by = {lv.follower: lv for lv in levels}

    def redirect(c: ParamConstraint) -> ParamConstraint:
        if c.field in ties:
            return dataclasses.replace(c, field=ties[c.field])
        lv = level_by.get(c.field)
        if lv is not None and lv.owner is not None:
            return dataclasses.replace(c, field=lv.owner, min=None if c.min is None else c.min - lv.offset,
                                       max=None if c.max is None else c.max - lv.offset)
        return c

    own: list[ParamConstraint] = []
    for pid, t in parts.items():
        cons = list(t.constraints(q[pid], ctx)) + list(t.assembly_constraints(q[pid], ctx))
        for j in resolved.joins:
            if j.child_id == pid:
                cons += t.joined_constraints(q[pid], ctx, j.child_anchor)
            if j.parent_id == pid:
                cons += t.joined_constraints(q[pid], ctx, j.parent_anchor)
        own += [dataclasses.replace(c, field=f"{pid}.{c.field}") for c in cons]
    out = [redirect(c) for c in own]
    out += [redirect(c) for c in _plug_constraints(resolved, parts, q, names)]
    out += [redirect(c) for c in _face_constraints(resolved, parts, q, names, sibling_gap(ctx))]
    out += _equalities(resolved, parts, p, names, levels)
    return out


def _levels(resolved: ResolvedAssembly, parts: Mapping[str, Template], q: Mapping[str, TemplateParams]
            ) -> list[_Level]:
    out: list[_Level] = []
    for j in resolved.joins:
        tc = parts[j.child_id]
        if j.mount != "slide" or not tc.level_field:
            continue
        tp, qp = parts[j.parent_id], q[j.parent_id]
        a = tp.anchors(qp).get(j.parent_anchor)
        if a is None or a.mount is None:
            continue
        h = float(a.mount[2])
        hf = tp.face_fields(qp, j.parent_anchor).height
        cur = _num(_get(qp, hf)) if hf else None
        owner = f"{j.parent_id}.{hf}" if hf and cur is not None else None
        out.append(_Level(f"{j.child_id}.{tc.level_field}", h, owner, h - cur if cur is not None else 0.0,
                          j.parent_id, j.child_id))
    return out


def _wall_field(t: Template, p: TemplateParams, anchor: str) -> str | None:
    f = t.face_fields(p, anchor).wall
    if f:
        return f
    return "wall_thickness_mm" if "wall_thickness_mm" in type(p).model_fields else None


def _plug_constraints(resolved: ResolvedAssembly, parts: Mapping[str, Template], q: Mapping[str, TemplateParams],
                      names: Mapping[str, str]) -> list[ParamConstraint]:
    out: list[ParamConstraint] = []
    for rj in resolved.joins:
        if rj.mount != "plug":
            continue
        j = rj.join_spec()
        (wid, wa), (pid, pa) = j.wall_end, j.port_end
        pf = _wall_field(parts[pid], q[pid], pa)
        if pf:
            out.append(ParamConstraint(
                f"{pid}.{pf}", min=PLUG_PORT_WALL_MIN_MM, source="printing",
                reason_ko=f"{names[pid]} 끝의 끼움 턱과 틈새를 두고도 {names[wid]}의 구멍을 덮도록 벽을 "
                          f"{PLUG_PORT_WALL_MIN_MM:g}mm 이상으로 했습니다"))
        wf = parts[wid].face_fields(q[wid], wa).wall
        if wf:
            out.append(ParamConstraint(
                f"{wid}.{wf}", min=PLUG_DOOR_WALL_MIN_MM, source="printing",
                reason_ko=f"{names[pid]}의 끼움 턱이 자리를 잡도록 {names[wid]} 벽을 {PLUG_DOOR_WALL_MIN_MM:g}mm "
                          "이상으로 했습니다"))
    return out


def _face_constraints(resolved: ResolvedAssembly, parts: Mapping[str, Template], q: Mapping[str, TemplateParams],
                      names: Mapping[str, str], gap: float) -> list[ParamConstraint]:
    """부모 면 가로·높이 (붙인 부품이 들어가고, 붙인 부품이 바라는 면 높이가 되도록)."""
    out: list[ParamConstraint] = []
    for (pid, anchor), group in _slide_groups(resolved.joins).items():
        tp, qp = parts[pid], q[pid]
        a = tp.anchors(qp).get(anchor)
        if a is None or a.mount is None:
            continue
        ff = tp.face_fields(qp, anchor)
        kids = [names[j.child_id] for j in group]
        who = "·".join(kids)
        if ff.width:
            cur = _num(_get(qp, ff.width))
            if cur is not None:
                widths = [face_width(parts[j.child_id], q[j.child_id], j.child_anchor) for j in group]
                need = sum(widths) + gap * (len(group) - 1) + 2 * EDGE_MARGIN_MM
                have = float(a.mount[1] - a.mount[0])
                out.append(ParamConstraint(
                    f"{pid}.{ff.width}", min=cur + max(0.0, need - have),
                    reason_ko=f"{_w(who, '이/가')} 옆면 안에 들어가도록 면을 넓혔습니다"))
        if ff.height:
            cur = _num(_get(qp, ff.height))
            if cur is None:
                continue
            h = float(a.mount[2])
            for j in group:
                lo, hi = parts[j.child_id].face_needs(q[j.child_id])
                if lo is not None:
                    out.append(ParamConstraint(
                        f"{pid}.{ff.height}", min=cur + max(0.0, lo - h),
                        reason_ko=f"{_w(names[j.child_id], '을/를')} 붙인 면이 {lo:g}mm 이상 높도록 높였습니다"))
                if hi is not None:
                    out.append(ParamConstraint(
                        f"{pid}.{ff.height}", max=cur - max(0.0, h - hi),
                        reason_ko=f"{names[j.child_id]}보다 높지 않도록 {names[pid]} 면 높이를 {hi:g}mm 이하로 맞췄습니다"))
    return out


def _equalities(resolved: ResolvedAssembly, parts: Mapping[str, Template], p: TemplateParams,
                names: Mapping[str, str], levels: list[_Level]) -> list[ParamConstraint]:
    from app.modules.composed import tie_constraints

    out: list[ParamConstraint] = []
    # 따르는 값이 받을 수 있는 범위 → 주인 값 범위
    for t in resolved.ties:
        lo, hi = field_bounds(type(getattr(p, t.follower_id)), t.follower_path)
        if lo is not None or hi is not None:
            out.append(ParamConstraint(t.owner, min=lo, max=hi,
                                       reason_ko=f"이어 붙인 {_w(names[t.follower_id], '이/가')} 따를 수 있는 범위로 맞췄습니다"))
    for lv in levels:
        if lv.owner is None:
            continue
        pid, path = split_ref(lv.follower)
        lo, hi = field_bounds(type(getattr(p, pid)), path)
        if lo is not None or hi is not None:
            out.append(ParamConstraint(
                lv.owner, min=None if lo is None else lo - lv.offset, max=None if hi is None else hi - lv.offset,
                reason_ko=f"{names[lv.child]} 꼭대기가 닿을 수 있는 높이로 맞췄습니다"))
    out += tie_constraints(resolved, p)
    for lv in levels:
        out.append(ParamConstraint(
            lv.follower, min=lv.value, max=lv.value,
            reason_ko=f"{names[lv.child]} 꼭대기가 {names[lv.parent]} 면 높이({lv.value:g}mm)와 같도록 맞췄습니다"))
    for k, v in resolved.fixed.items():
        n = _num(v)
        if n is not None:
            out.append(ParamConstraint(k, min=n, max=n, reason_ko="조립 해석기가 정한 값입니다"))
    return out


# ── 조립 항목 템플릿 캐시 ──


@lru_cache(maxsize=32)
def composed_template(canonical: str, name_ko: str | None = None) -> ComposedTemplate:
    """저장 형태의 정규 JSON(ResolvedAssembly.canonical()) → 조립 항목 템플릿. 같은 구조면 같은 인스턴스를 돌려줘
    자동 보정·줄이기·검증·다시 만들기가 형상·검사 캐시를 함께 쓴다."""
    from app.modules.composed import ComposedTemplate

    return ComposedTemplate(ResolvedAssembly.model_validate_json(canonical), name_ko=name_ko)


def template_for(resolved: ResolvedAssembly, name_ko: str | None = None) -> ComposedTemplate:
    return composed_template(resolved.canonical(), name_ko)


def assembly_params(template: Template, params: Mapping[str, TemplateParams | Mapping[str, Any]]) -> TemplateParams:
    """부품 id → 부품 파라미터 를 조립 항목 템플릿의 Params 로."""
    return template.Params.model_validate(
        {pid: v.model_dump() if isinstance(v, TemplateParams) else dict(v) for pid, v in params.items()})
