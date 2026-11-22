"""자유 조립 항목의 구조 계약 (형상 커널을 불러오지 않는다).

조립 항목 = 부품(템플릿) 여러 개를 연결 관계로 이은 나무 구조. 두 가지 형태가 있다.

- AssemblyRequest (해석기 출력 → 엔진 입력): parts(id·template·params)와 connections(part 를 to 의 at 면에 붙인다).
  parts[0] 이 기준(뿌리) 부품이다. at 은 기준 부품 좌표계(케이지 회전 전 항목 좌표계)에서 본 면이고, free_end 는
  아직 쓰지 않은 터널 끝, auto 는 해석기가 고르는 첫 빈 면이다. 결합 방식·자식 연결 지점·맞물리는 치수는 적지 않는다.
- ResolvedAssembly (조립 해석기 app/modules/compose 의 결과, DesignVersion.items[i]["assembly"] 에 저장):
  부품 목록, 연결 지점끼리의 결합(joins), 따라가는 치수(ties), 해석기가 정한 값(fixed), 부품마다 붙은 면(faces).
  다시 만들 때는 저장된 이 형태와 파라미터만 쓴다 (해석기를 다시 돌리지 않는다).

canonical(): 키를 정렬한 압축 JSON. 형상 지문·조립 템플릿 캐시의 키로 쓴다.
AssemblyDisplay: API 응답(ItemOut.assembly)에 싣는 표시용 형태 (부품 이름과 결합 줄).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from app.modules.assembly import JoinSpec

# 조립 항목 하나의 부품 수 (해석기가 끼워 넣는 터널 포함)
MIN_PARTS = 2
MAX_PARTS = 8
# 부품 id: 소문자로 시작, 소문자·숫자·밑줄 (최대 41자). model_ 로 시작하면 조립 파라미터 모델 필드와 겹친다
PART_ID_MAX_LEN = 41
PART_ID_PATTERN = r"^(?!model_)[a-z][a-z0-9_]{0,40}$"
_PART_ID = re.compile(PART_ID_PATTERN)
# "부품id.연결지점" (결합), "부품id.파라미터경로" (ties·fixed: 중첩 파라미터는 점 표기)
_NAME = r"[a-z][a-z0-9_]{0,40}"
_ANCHOR_REF = re.compile(rf"^({_NAME})\.({_NAME})$")
_PARAM_REF = re.compile(rf"^({_NAME})\.({_NAME}(?:\.{_NAME}){{0,3}})$")

RESOLVER = "compose/1"

# 해석기 입력의 면: 기준 부품 좌표계의 옆면, 아직 쓰지 않은 터널 끝, 첫 빈 면
At = Literal["front", "back", "left", "right", "free_end", "auto"]
# 해석한 뒤의 면 (auto 는 실제 면으로 정해진다)
ResolvedAt = Literal["front", "back", "left", "right", "free_end"]
AT_VALUES: tuple[str, ...] = ("front", "back", "left", "right", "free_end", "auto")
Mount = Literal["slide", "plug"]
# 통로 결합: False(통로 아님), into_parent(자식 통로 단면으로 부모 벽을 뚫는다), into_child(부모 통로로 자식 벽을 뚫는다)
Passage = Literal[False, "into_parent", "into_child"]
# fixed 값: 숫자·글·참거짓, 또는 글 목록 (집의 "ports.sides")
FixedValue = bool | int | float | str | list[str]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_json(data: Any) -> str:
    """키를 정렬한 압축 JSON (목록 순서는 그대로). 같은 내용이면 항상 같은 글이다."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode()).hexdigest()


def split_ref(ref: str) -> tuple[str, str]:
    """"부품id.나머지" → (부품id, 나머지). 나머지는 연결 지점 이름이나 파라미터 경로."""
    pid, _, rest = ref.partition(".")
    return pid, rest


def tree_problems(ids: Sequence[str], edges: Sequence[tuple[str, str]]) -> list[str]:
    """부품 id 목록(첫 id 가 뿌리)과 (자식, 부모) 연결이 뿌리에서 이어진 나무인지. 문제 문구 목록 (없으면 빈 목록).

    부품 수 MIN_PARTS..MAX_PARTS, id 형식·중복, 연결이 가리키는 부품, 뿌리는 자식이 아님, 나머지 부품은 꼭 한 번씩
    자식, 순환 없이 모두 뿌리에서 이어짐을 본다. 해석기 출력 검증(app/llm/spec)도 같은 함수를 쓴다."""
    out: list[str] = []
    if not MIN_PARTS <= len(ids) <= MAX_PARTS:
        out.append(f"조립 항목의 부품은 {MIN_PARTS}~{MAX_PARTS}개여야 합니다 (지금 {len(ids)}개)")
    bad = [i for i in ids if not _PART_ID.match(i)]
    if bad:
        out.append(f"부품 id 는 소문자로 시작하는 소문자·숫자·밑줄(최대 {PART_ID_MAX_LEN}자, model_ 로 시작하지 않음)이어야 합니다: {bad}")
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        out.append(f"부품 id 가 겹칩니다: {dup}")
    if not ids:
        return out
    known = set(ids)
    root = ids[0]
    parent: dict[str, str] = {}
    twice: list[str] = []
    for child, to in edges:
        if child not in known or to not in known:
            missing = [x for x in (child, to) if x not in known]
            out.append(f"없는 부품을 잇습니다: {child} → {to} (없는 id: {missing})")
            continue
        if child == to:
            out.append(f"부품을 자기 자신에 붙일 수 없습니다: {child}")
            continue
        if child == root:
            out.append(f"기준(첫) 부품 {root} 은 다른 부품에 붙일 수 없습니다 (parts 의 첫 부품이 기준입니다)")
            continue
        if child in parent:
            twice.append(child)
            continue
        parent[child] = to
    if twice:
        out.append(f"부품은 한 부품에만 붙일 수 있습니다 (두 번 이은 부품: {sorted(set(twice))})")
    unlinked = [i for i in dict.fromkeys(ids[1:]) if i not in parent]
    if unlinked:
        out.append(f"어디에도 붙이지 않은 부품이 있습니다: {unlinked} (connections 에 part 로 한 번씩 적어야 합니다)")
    # 순환: 부모를 따라 올라가 뿌리에 닿지 않는 부품
    cyclic: list[str] = []
    for start in parent:
        seen = {start}
        cur = start
        while cur in parent:
            cur = parent[cur]
            if cur in seen:
                cyclic.append(start)
                break
            seen.add(cur)
    if cyclic:
        out.append(f"연결이 순환합니다 (기준 부품에서 이어지지 않는 부품: {sorted(cyclic)})")
    return out


def link_id(child: str, taken: Sequence[str] | set[str]) -> str:
    """해석기가 끼워 넣는 터널의 id: f"{child}_link" (id 형식·길이에 맞게 줄이고, 겹치면 번호를 붙인다)."""
    base = f"{child[:PART_ID_MAX_LEN - 5]}_link"
    if base not in taken:
        return base
    n = 2
    while True:
        suffix = f"_link{n}"
        cand = f"{child[:PART_ID_MAX_LEN - len(suffix)]}{suffix}"
        if cand not in taken:
            return cand
        n += 1


# --- 해석기 입력 ---


class PartRequest(_Strict):
    """부품 하나: id(조립 안에서 유일), 템플릿 key, 그 템플릿의 파라미터 (엔진이 템플릿 Params 로 검증한다)."""

    id: str
    template: str
    params: dict[str, Any]


class Connection(_Strict):
    """part 를 to 의 at 면에 붙인다 (at 은 기준 부품 좌표계에서 본 면)."""

    part: str
    to: str
    at: At


class AssemblyRequest(_Strict):
    """해석기가 낸 조립 항목 (엔진 입력). parts[0] 이 기준 부품이다."""

    parts: list[PartRequest]
    connections: list[Connection]
    name_ko: str | None = None

    @model_validator(mode="after")
    def _tree(self) -> AssemblyRequest:
        problems = tree_problems([p.id for p in self.parts], [(c.part, c.to) for c in self.connections])
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def root(self) -> str:
        return self.parts[0].id

    def part(self, pid: str) -> PartRequest:
        for p in self.parts:
            if p.id == pid:
                return p
        raise KeyError(pid)

    def parent_of(self, pid: str) -> str | None:
        for c in self.connections:
            if c.part == pid:
                return c.to
        return None

    def children_of(self, pid: str) -> list[Connection]:
        """pid 에 붙는 연결 (connections 순서)."""
        return [c for c in self.connections if c.to == pid]

    def walk(self) -> list[Connection]:
        """뿌리부터 너비 우선 순서의 연결 (같은 부모의 자식끼리는 connections 순서). 해석기가 이 순서로 정한다."""
        order: list[Connection] = []
        queue = [self.root]
        while queue:
            pid = queue.pop(0)
            for c in self.children_of(pid):
                order.append(c)
                queue.append(c.part)
        return order


# --- 해석한 형태 (저장) ---


class ResolvedPart(_Frozen):
    id: str
    template: str


class ResolvedJoin(_Frozen):
    """연결 지점끼리의 결합. parent·child = "부품id.연결지점".

    mount: slide(따로 출력해 도브테일로 끼운다, 통로 아님) 또는 plug(통로 쪽 부품을 따로 출력해 끼움 턱으로 끼운다).
    shift: 부모 면 위에서 자식을 옮기는 거리 mm (면의 가로, 바깥에서 볼 때 오른쪽 +). 같은 면에 여럿 붙일 때 쓴다."""

    parent: str
    child: str
    mount: Mount
    passage: Passage
    shift: float = 0.0

    @field_validator("parent", "child")
    @classmethod
    def _ref(cls, v: str) -> str:
        if not _ANCHOR_REF.match(v):
            raise ValueError(f"'부품id.연결지점' 형식이어야 합니다: {v}")
        return v

    @field_validator("shift")
    @classmethod
    def _round(cls, v: float) -> float:
        # 부동소수 잡음이 저장·지문에 남지 않게 (−0.0 도 0.0 으로)
        return round(float(v), 6) + 0.0

    @model_validator(mode="after")
    def _mount(self) -> ResolvedJoin:
        if self.mount == "slide" and self.passage is not False:
            raise ValueError(f"슬라이드 결합은 통로로 이을 수 없습니다: {self.parent} → {self.child}")
        if self.mount == "plug" and self.passage is False:
            raise ValueError(f"끼움 결합은 통로로만 이을 수 있습니다: {self.parent} → {self.child}")
        if self.parent_id == self.child_id:
            raise ValueError(f"부품을 자기 자신에 이을 수 없습니다: {self.parent} → {self.child}")
        return self

    @property
    def parent_id(self) -> str:
        return split_ref(self.parent)[0]

    @property
    def parent_anchor(self) -> str:
        return split_ref(self.parent)[1]

    @property
    def child_id(self) -> str:
        return split_ref(self.child)[0]

    @property
    def child_anchor(self) -> str:
        return split_ref(self.child)[1]

    @property
    def reverse(self) -> bool:
        """통로가 자식 벽을 뚫는지 (부모가 통로 쪽)."""
        return self.passage == "into_child"

    def join_spec(self) -> JoinSpec:
        """조립 형상 코드의 결합 (형상 커널을 쓰는 모듈이라 여기서만 불러온다)."""
        from app.modules.assembly import JoinSpec as _JoinSpec

        return _JoinSpec(self.parent_id, self.parent_anchor, self.child_id, self.child_anchor, shift=self.shift,
                        passage=self.passage is not False, mount=self.mount, reverse=self.reverse)


class Tie(_Frozen):
    """follower 값은 owner 값을 그대로 따른다 ("부품id.파라미터경로"). 예: 터널 내경 ← 은신처 출입구 지름.

    owner 는 사슬을 끝까지 따라간 값(다른 값을 따르지 않는 값)이다. 따르는 값에 걸린 제약은 owner 로 옮겨 보정한다."""

    follower: str
    owner: str

    @field_validator("follower", "owner")
    @classmethod
    def _ref(cls, v: str) -> str:
        if not _PARAM_REF.match(v):
            raise ValueError(f"'부품id.파라미터' 형식이어야 합니다: {v}")
        return v

    @model_validator(mode="after")
    def _distinct(self) -> Tie:
        if self.follower == self.owner:
            raise ValueError(f"값이 자기 자신을 따를 수 없습니다: {self.follower}")
        return self

    @property
    def follower_id(self) -> str:
        return split_ref(self.follower)[0]

    @property
    def follower_path(self) -> str:
        return split_ref(self.follower)[1]

    @property
    def owner_id(self) -> str:
        return split_ref(self.owner)[0]

    @property
    def owner_path(self) -> str:
        return split_ref(self.owner)[1]


class ResolvedAssembly(_Frozen):
    """조립 해석기의 결과 (저장 형태). 다시 만들 때는 parts·joins 와 저장된 파라미터만 쓴다.

    - ties·fixed: 다시 검증·규칙 안내에 쓴다 (형상에는 쓰지 않는다)
    - fixed: 해석기가 정한 값 ("부품id.파라미터경로" → 값). 예: 터널 단면 모양, 출입구 수
    - faces: 기준 부품이 아닌 부품마다 붙은 면 (기준 부품 좌표계, 옮긴 뒤의 면). 고친 명세의 connections.at 이 된다"""

    v: Literal[1] = 1
    resolver: str = RESOLVER
    root: str
    parts: list[ResolvedPart]
    joins: list[ResolvedJoin]
    ties: list[Tie] = Field(default_factory=list)
    fixed: dict[str, FixedValue] = Field(default_factory=dict)
    faces: dict[str, ResolvedAt] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> ResolvedAssembly:
        ids = [p.id for p in self.parts]
        problems = tree_problems(ids, [(j.child_id, j.parent_id) for j in self.joins])
        if ids and self.root != ids[0]:
            problems.append(f"root({self.root})는 첫 부품({ids[0]})이어야 합니다")
        known = set(ids)
        for t in self.ties:
            for pid in (t.follower_id, t.owner_id):
                if pid not in known:
                    problems.append(f"ties: 없는 부품 {pid} ({t.follower} ← {t.owner})")
        followers = [t.follower for t in self.ties]
        dup = sorted({f for f in followers if followers.count(f) > 1})
        if dup:
            problems.append(f"ties: 한 값이 둘 이상을 따릅니다: {dup}")
        chained = sorted({t.owner for t in self.ties} & set(followers))
        if chained:
            problems.append(f"ties: owner 는 다른 값을 따르지 않는 값이어야 합니다: {chained}")
        for k in self.fixed:
            m = _PARAM_REF.match(k)
            if not m:
                problems.append(f"fixed: '부품id.파라미터' 형식이어야 합니다: {k}")
            elif m.group(1) not in known:
                problems.append(f"fixed: 없는 부품 {m.group(1)}")
        if set(self.faces) != set(ids[1:]):
            problems.append(f"faces 는 기준 부품이 아닌 부품마다 하나씩이어야 합니다 (지금 {sorted(self.faces)})")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @classmethod
    def from_stored(cls, raw: Mapping[str, Any]) -> ResolvedAssembly:
        return cls.model_validate(raw)

    def stored(self) -> dict[str, Any]:
        """저장 형태 (JSON 으로 그대로 쓸 수 있는 dict)."""
        return self.model_dump(mode="json")

    def canonical(self) -> str:
        """전체 구조의 정규 JSON (조립 템플릿 캐시 키: ties·fixed 도 제약에 쓰므로 함께 넣는다)."""
        return canonical_json(self.stored())

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()

    def geometry_canonical(self) -> str:
        """형상을 정하는 부분(parts·joins)만의 정규 JSON (형상 지문용)."""
        data = self.stored()
        return canonical_json({"parts": data["parts"], "joins": data["joins"]})

    def geometry_digest(self) -> str:
        return hashlib.sha256(self.geometry_canonical().encode()).hexdigest()

    @property
    def part_ids(self) -> list[str]:
        return [p.id for p in self.parts]

    def template_of(self, pid: str) -> str:
        for p in self.parts:
            if p.id == pid:
                return p.template
        raise KeyError(pid)

    def join_to(self, pid: str) -> ResolvedJoin | None:
        """부품 pid 를 부모에 붙인 결합 (기준 부품이면 None)."""
        for j in self.joins:
            if j.child_id == pid:
                return j
        return None

    def to_request(self, params: Mapping[str, Mapping[str, Any]], name_ko: str | None = None) -> AssemblyRequest:
        """고친 명세(effective spec)의 조립 항목: 보정한 파라미터, 해석기가 끼운 터널도 보통 부품으로,
        at 은 실제로 붙은 면(faces)으로."""
        return AssemblyRequest(
            parts=[PartRequest(id=p.id, template=p.template, params=dict(params.get(p.id, {}))) for p in self.parts],
            connections=[Connection(part=j.child_id, to=j.parent_id, at=self.faces[j.child_id]) for j in self.joins],
            name_ko=name_ko,
        )


# --- API 표시 형태 (ItemOut.assembly) ---


class DisplayPart(_Strict):
    id: str
    template: str
    name_ko: str  # 템플릿이 여러 번 나오면 둘째부터 번호를 붙인다 ("은신처 2")


class DisplayJoin(_Strict):
    """part 를 to 의 at 면에 붙였다 (at: 기준 부품 좌표계의 면 또는 free_end)."""

    part: str
    to: str
    at: ResolvedAt
    mount: Mount
    passage: Passage


class AssemblyDisplay(_Strict):
    """API 응답의 조립 항목 구조. 프론트엔드 Item.assembly 와 같은 모양이다.
    이때 ItemOut.params 는 부품 id → 그 부품의 파라미터다."""

    parts: list[DisplayPart]
    joins: list[DisplayJoin]


def part_names(parts: Sequence[ResolvedPart], template_names: Mapping[str, str]) -> dict[str, str]:
    """부품 id → 화면 이름. 같은 템플릿이 여러 번 나오면 둘째부터 번호를 붙인다 ("은신처", "은신처 2").
    template_names: 템플릿 key → 이름 (없는 key 는 key 그대로)."""
    seen: dict[str, int] = {}
    out: dict[str, str] = {}
    for p in parts:
        n = seen.get(p.template, 0) + 1
        seen[p.template] = n
        name = template_names.get(p.template, p.template)
        out[p.id] = name if n == 1 else f"{name} {n}"
    return out


def assembly_display(resolved: ResolvedAssembly, template_names: Mapping[str, str]) -> AssemblyDisplay:
    names = part_names(resolved.parts, template_names)
    return AssemblyDisplay(
        parts=[DisplayPart(id=p.id, template=p.template, name_ko=names[p.id]) for p in resolved.parts],
        joins=[DisplayJoin(part=j.child_id, to=j.parent_id, at=resolved.faces[j.child_id], mount=j.mount,
                           passage=j.passage) for j in resolved.joins],
    )
