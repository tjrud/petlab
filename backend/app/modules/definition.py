"""조립 모듈 정의 (모듈 라이브러리 JSON 형식). 형상 커널을 불러오지 않는다.

모듈 = 검증된 부품(템플릿)들을 연결 지점끼리 이어 붙인 조립 설계도 + 바깥에 드러낼 파라미터.
  - parts: 부품 목록. 첫 부품이 기준(뿌리)이다. 부품 파라미터는 상수이거나 모듈 파라미터에 묶는다
    (값 = scale × 모듈 파라미터 + offset, scale > 0). 묶은 관계로 부품의 종별 제약을 모듈 파라미터 제약으로 되돌려
    자동 보정한다.
  - joins: "부품id.연결지점" 끼리 잇는다. 자식은 부모의 연결 지점에 마주 보게 붙는다.
    passage=True 면 자식 통로(터널 끝 등)의 단면으로 부모 벽을 뚫어 드나들 수 있게 한다.
    passage="into_child" 면 거꾸로 부모 통로의 단면으로 자식 벽을 뚫는다.
    mount: fused(한 덩어리), slide(따로 출력해 도브테일로 끼움), plug(통로 쪽 부품을 따로 출력해 끼움 턱으로 끼움).
  - limits: 모듈 파라미터끼리의 관계 (예: 은신처 세로 ≥ 그릇 받침 외형 폭 + 여유). 자식 부품이 부모 면 안에 들어가게
    하는 데 쓴다. 자동 보정은 limit 의 param 만 움직인다 (min/max 쪽 파라미터는 그대로).
  - 이름·설명은 한국어와 영어를 함께 둔다 (응답 언어 번역 카탈로그에 더해진다).

저장된 설계는 모듈 key 로 다시 만든다. 그래서 공개한 모듈 파일은 형상이 바뀌게 고치지 않는다:
바꾸려면 새 key(예: _v2)로 새 파일을 만든다 (형상 지문·메시 해시가 바뀐 형상을 막는다).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LIBRARY_DIR = Path(__file__).parent / "library"
_IDENT = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
# 부품 파라미터 이름: 점 표기로 중첩 파라미터를 가리킬 수 있다 ("roof.kind")
_PATH = re.compile(r"^[a-z][a-z0-9_]{0,40}(\.[a-z][a-z0-9_]{0,40}){0,3}$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParamDef(_Strict):
    """모듈이 바깥에 드러내는 파라미터 (LLM 이 정한다)."""

    name: str
    type: Literal["float", "int", "choice"] = "float"
    default: float | int | str
    min: float | None = None
    max: float | None = None
    choices: list[str] | None = None
    description_ko: str
    description_en: str

    @field_validator("name")
    @classmethod
    def _ident(cls, v: str) -> str:
        if not _IDENT.match(v):
            raise ValueError(f"파라미터 이름은 소문자·숫자·밑줄만: {v}")
        return v

    @model_validator(mode="after")
    def _check(self) -> "ParamDef":
        if self.type == "choice":
            if not self.choices or self.default not in self.choices:
                raise ValueError(f"{self.name}: choice 는 choices 와 그 안의 기본값이 필요합니다")
        else:
            if self.min is None or self.max is None or not self.min <= float(self.default) <= self.max:
                raise ValueError(f"{self.name}: 숫자 파라미터는 min ≤ default ≤ max 여야 합니다")
        return self


class Bind(_Strict):
    """부품 파라미터 값 = scale × 모듈 파라미터 + offset (choice 는 그대로)."""

    param: str
    scale: float = Field(1.0, gt=0)
    offset: float = 0.0


# 모듈 limits 의 사슬(한 limit 의 범위가 다른 limit 이 움직이는 파라미터에 기대는 것)의 최대 길이.
# 자동 보정(app/validation/autofix.clamp_params)은 패스마다 그 패스 시작 값으로 제약을 다시 계산하므로 한 패스에
# 사슬 한 고리씩 따라간다. 부품 제약이 먼저 움직이는 패스와 마지막 확인 패스까지 MAX_PASSES(8) 안에 끝나게 둔다
LIMIT_CHAIN_MAX = 4


class LimitDef(_Strict):
    """모듈 파라미터 하나의 범위를 다른 모듈 파라미터로 정한다: min ≤ param ≤ max.

    min·max 는 숫자이거나 다른 모듈 파라미터에 묶은 값(scale × 파라미터 + offset). 자동 보정은 param 을 움직여 맞추고,
    param 의 범위(ParamDef min·max) 안에서 맞출 수 없으면 규칙 오류로 남는다 (묶인 쪽 파라미터는 바꾸지 않는다)."""

    param: str
    min: Bind | float | None = None
    max: Bind | float | None = None
    reason_ko: str
    reason_en: str

    @model_validator(mode="after")
    def _some(self) -> LimitDef:
        if self.min is None and self.max is None:
            raise ValueError(f"limit {self.param}: min 이나 max 가 필요합니다")
        return self


def bound_value(v: Bind | float | None, values: dict[str, float]) -> float | None:
    """limit 의 min·max 값 (values: 모듈 파라미터 이름 → 값)."""
    if v is None:
        return None
    if isinstance(v, Bind):
        return v.scale * float(values[v.param]) + v.offset
    return float(v)


# 상수는 숫자·글·참거짓, 또는 글 목록 (집의 "doors.sides": ["left"] 처럼 면 목록)
PartValue = Bind | float | int | str | bool | list[str]


class PartDef(_Strict):
    id: str
    template: str
    params: dict[str, PartValue] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _ident(cls, v: str) -> str:
        if not _IDENT.match(v):
            raise ValueError(f"부품 id 는 소문자·숫자·밑줄만: {v}")
        return v

    @field_validator("params")
    @classmethod
    def _paths(cls, v: dict[str, PartValue]) -> dict[str, PartValue]:
        for k in v:
            if not _PATH.match(k):
                raise ValueError(f"부품 파라미터 이름은 소문자·숫자·밑줄(중첩은 점 표기)만: {k}")
        heads = {k.split(".")[0] for k in v if "." in k}
        if heads & set(v):
            raise ValueError(f"중첩 파라미터를 통째로와 점 표기로 함께 정할 수 없습니다: {sorted(heads & set(v))}")
        return v


class JoinDef(_Strict):
    parent: str  # "부품id.연결지점"
    child: str
    # 부모 면 위에서 자식을 옮기는 거리 mm: shift = 면의 가로 방향(바깥에서 볼 때 오른쪽 +), lift = 위쪽 +
    shift: float | Bind = 0.0
    lift: float | Bind = 0.0
    # 자식을 연결 면 법선 둘레로 돌리는 각도 (위에 얹는 부품의 방향 등)
    spin: Literal[0, 90, 180, 270] = 0
    # 통로로 잇는다. true(= "into_parent"): 자식 통로(터널 끝 등)의 단면으로 부모 벽을 뚫는다.
    # "into_child": 거꾸로 부모 통로(터널 끝 등)의 단면으로 자식 벽을 뚫는다 (터널 끝에 두 번째 은신처의 출입구를 붙일 때)
    passage: bool | Literal["into_parent", "into_child"] = False
    # fused: 한 덩어리로 붙인다 (기본). slide: 따로 출력해 도브테일로 끼운다 (옆면끼리만, 통로와 함께 쓸 수 없다).
    # plug: 통로 쪽 부품(터널)을 따로 출력해 벽 쪽 부품의 구멍에 끼움 턱으로 끼운다 (통로로만)
    mount: Literal["fused", "slide", "plug"] = "fused"

    @field_validator("parent", "child")
    @classmethod
    def _ref(cls, v: str) -> str:
        if v.count(".") != 1:
            raise ValueError(f"'부품id.연결지점' 형식이어야 합니다: {v}")
        return v

    @model_validator(mode="after")
    def _mount(self) -> "JoinDef":
        if self.mount == "slide" and self.passage:
            raise ValueError(f"슬라이드 결합은 통로로 이을 수 없습니다: {self.parent} → {self.child}")
        if self.mount == "plug" and not self.passage:
            raise ValueError(f"끼움 결합은 통로로만 이을 수 있습니다 (passage 가 필요합니다): {self.parent} → {self.child}")
        return self

    @property
    def into_child(self) -> bool:
        """통로가 자식 벽을 뚫는지 (부모가 통로 쪽)."""
        return self.passage == "into_child"


class ModuleDef(_Strict):
    key: str
    name_ko: str
    name_en: str
    description_ko: str
    description_en: str
    # 모의 해석기·검색용 낱말
    keywords_ko: list[str] = Field(default_factory=list)
    keywords_en: list[str] = Field(default_factory=list)
    color: str | None = None
    params: list[ParamDef]
    parts: list[PartDef] = Field(min_length=1)
    joins: list[JoinDef] = Field(default_factory=list)
    # 케이지 공간이 부족할 때 줄일 크기 파라미터, 케이지 높이에 맞춰 제한할 높이 파라미터
    size_params: list[str] = Field(default_factory=list)
    height_param: str | None = None
    # 출입 기준 (은신처처럼 드나드는 공간이 있는 모듈이면 True: 바깥 출입구 수를 종별 최소 개수와 비교)
    enclosure: bool = False
    # 모듈 파라미터끼리의 범위 관계 (자동 보정·규칙 오류). 아래 _limits 가 불러올 때 검사한다
    limits: list[LimitDef] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def _ident(cls, v: str) -> str:
        if not _IDENT.match(v):
            raise ValueError(f"모듈 key 는 소문자·숫자·밑줄만: {v}")
        return v

    @model_validator(mode="after")
    def _refs(self) -> "ModuleDef":
        names = {p.name for p in self.params}
        if len(names) != len(self.params):
            raise ValueError("파라미터 이름이 겹칩니다")
        ids = [p.id for p in self.parts]
        if len(set(ids)) != len(ids):
            raise ValueError("부품 id 가 겹칩니다")

        def check_bind(v: PartValue | float, where: str) -> None:
            if isinstance(v, Bind) and v.param not in names:
                raise ValueError(f"{where}: 없는 파라미터 {v.param}")

        for part in self.parts:
            for k, v in part.params.items():
                check_bind(v, f"{part.id}.{k}")
        children: set[str] = set()
        for j in self.joins:
            pid, cid = j.parent.split(".")[0], j.child.split(".")[0]
            if pid not in ids or cid not in ids:
                raise ValueError(f"없는 부품을 잇습니다: {j.parent} → {j.child}")
            if cid in children:
                raise ValueError(f"부품 {cid} 를 두 번 이어 붙였습니다 (부품은 부모 하나에만 붙는다)")
            if cid == ids[0]:
                raise ValueError("기준(첫) 부품은 자식이 될 수 없습니다")
            children.add(cid)
            check_bind(j.shift, f"{j.parent}→{j.child}.shift")
            check_bind(j.lift, f"{j.parent}→{j.child}.lift")
        missing = set(ids[1:]) - children
        if missing:
            raise ValueError(f"이어지지 않은 부품: {sorted(missing)}")
        for n in [*self.size_params, *([self.height_param] if self.height_param else [])]:
            if n not in names:
                raise ValueError(f"없는 파라미터: {n}")
        self._limits()
        return self

    def _limits(self) -> None:
        """limits 검사: 파라미터가 있고 숫자인지, 자기 자신에 묶지 않았는지, 사슬이 짧은지,
        기본값에서 min ≤ max 이고 기본값이 범위 안인지 (아니면 기본 설계부터 자동 보정이 값을 바꾼다)."""
        if not self.limits:
            return
        defs = {p.name: p for p in self.params}
        numeric = {n for n, p in defs.items() if p.type != "choice"}
        deps: dict[str, set[str]] = {}
        for lim in self.limits:
            if lim.param not in defs:
                raise ValueError(f"limit: 없는 파라미터 {lim.param}")
            if lim.param not in numeric:
                raise ValueError(f"limit: 숫자 파라미터만 제한할 수 있습니다 ({lim.param})")
            for side in (lim.min, lim.max):
                if not isinstance(side, Bind):
                    continue
                if side.param not in defs:
                    raise ValueError(f"limit {lim.param}: 없는 파라미터 {side.param}")
                if side.param not in numeric:
                    raise ValueError(f"limit {lim.param}: 숫자 파라미터에만 묶을 수 있습니다 ({side.param})")
                if side.param == lim.param:
                    raise ValueError(f"limit {lim.param}: 자기 자신에 묶을 수 없습니다")
                deps.setdefault(lim.param, set()).add(side.param)

        def cycle(n: str, path: tuple[str, ...]) -> tuple[str, ...] | None:
            for m in deps.get(n, ()):
                if m in path:
                    return (*path[path.index(m):], m)
                found = cycle(m, (*path, m))
                if found:
                    return found
            return None

        # 순환(세로 ≥ 그릇 + 10 과 그릇 ≤ 세로 − 10 처럼 같은 관계를 양쪽에서 적은 것 포함)은 받지 않는다: 자동 보정이
        # 묶인 쪽까지 움직여 사용자가 바꾸지 않은 값이 바뀌고, 서로 밀어 올리면 범위 끝까지 달아난다
        for n in deps:
            found = cycle(n, (n,))
            if found:
                raise ValueError(f"limit 이 순환합니다 ({' → '.join(found)}): 한 관계는 한쪽 파라미터에만 적으세요")

        def chain(n: str, seen: frozenset[str]) -> int:
            return max((1 + chain(m, seen | {m}) for m in deps.get(n, ()) if m not in seen), default=0)

        longest = max(chain(n, frozenset({n})) for n in deps) if deps else 0
        if longest > LIMIT_CHAIN_MAX:
            raise ValueError(f"limit 사슬이 너무 깁니다 ({longest} > {LIMIT_CHAIN_MAX}): 자동 보정이 다 따라가지 못합니다")
        values = {n: float(defs[n].default) for n in numeric}
        for name in dict.fromkeys(lim.param for lim in self.limits):
            mine = [lim for lim in self.limits if lim.param == name]
            los = [v for v in (bound_value(lim.min, values) for lim in mine) if v is not None]
            his = [v for v in (bound_value(lim.max, values) for lim in mine) if v is not None]
            lo, hi = max(los, default=None), min(his, default=None)
            if lo is not None and hi is not None and lo > hi + 1e-9:
                raise ValueError(f"limit {name}: 기본값에서 min {lo:g} 이 max {hi:g} 보다 큽니다")
            v = values[name]
            if (lo is not None and v < lo - 1e-9) or (hi is not None and v > hi + 1e-9):
                raise ValueError(f"limit {name}: 기본값 {v:g} 이 기본값에서의 범위 "
                                 f"[{'' if lo is None else f'{lo:g}'}, {'' if hi is None else f'{hi:g}'}] 밖입니다")


def load_module_file(path: Path) -> ModuleDef:
    return ModuleDef.model_validate(json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def library_files() -> dict[str, Path]:
    """모듈 key → 정의 파일 (형상 지문에 쓴다)."""
    out: dict[str, Path] = {}
    for f in sorted(LIBRARY_DIR.glob("*.json")):
        key = json.loads(f.read_text(encoding="utf-8")).get("key")
        if key:
            out[key] = f
    return out


@lru_cache(maxsize=1)
def library() -> tuple[ModuleDef, ...]:
    return tuple(load_module_file(f) for f in library_files().values())


def translations() -> dict[str, str]:
    """모듈 정의의 한국어 → 영어 (응답 번역 카탈로그에 더한다)."""
    out: dict[str, str] = {}
    for m in library():
        out[m.name_ko] = m.name_en
        out[m.description_ko] = m.description_en
        for p in m.params:
            out[p.description_ko] = p.description_en
            # 자동 보정 문구는 설명의 첫 문장(단위 뺀)을 이름으로 쓴다 (app/validation/autofix._desc)
            short_ko = p.description_ko.split(".")[0].replace(" mm", "")
            short_en = p.description_en.split(".")[0].replace(" mm", "")
            out.setdefault(short_ko, short_en)
        for lim in m.limits:
            out[lim.reason_ko] = lim.reason_en
    return out
