"""조립 모듈 정의 (모듈 라이브러리 JSON 형식). 형상 커널을 불러오지 않는다.

모듈 = 검증된 부품(템플릿)들을 연결 지점끼리 이어 붙인 조립 설계도 + 바깥에 드러낼 파라미터.
  - parts: 부품 목록. 첫 부품이 기준(뿌리)이다. 부품 파라미터는 상수이거나 모듈 파라미터에 묶는다
    (값 = scale × 모듈 파라미터 + offset, scale > 0). 묶은 관계로 부품의 종별 제약을 모듈 파라미터 제약으로 되돌려
    자동 보정한다.
  - joins: "부품id.연결지점" 끼리 잇는다. 자식은 부모의 연결 지점에 마주 보게 붙는다.
    passage=True 면 자식 통로(터널 끝 등)의 단면으로 부모 벽을 뚫어 드나들 수 있게 한다.
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


PartValue = Bind | float | int | str | bool


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


class JoinDef(_Strict):
    parent: str  # "부품id.연결지점"
    child: str
    # 부모 면 위에서 자식을 옮기는 거리 mm: shift = 면의 가로 방향(바깥에서 볼 때 오른쪽 +), lift = 위쪽 +
    shift: float | Bind = 0.0
    lift: float | Bind = 0.0
    # 자식을 연결 면 법선 둘레로 돌리는 각도 (위에 얹는 부품의 방향 등)
    spin: Literal[0, 90, 180, 270] = 0
    # 자식 통로(터널 끝 등)의 단면으로 부모 벽을 뚫는다
    passage: bool = False

    @field_validator("parent", "child")
    @classmethod
    def _ref(cls, v: str) -> str:
        if v.count(".") != 1:
            raise ValueError(f"'부품id.연결지점' 형식이어야 합니다: {v}")
        return v


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
        return self


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
    return out
