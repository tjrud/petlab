"""API 요청·응답 스키마."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
)

from app.names import normalize_nickname

# DB 에 저장되는 값의 형식 (Postgres 는 NUL 문자·int4 범위를 넘는 정수를 거부하므로 입력 단계에서 막는다)
ID_PATTERN = r"^[0-9a-f]{32}$"
MAX_INT4 = 2**31 - 1
EntityId = Annotated[str, Field(pattern=ID_PATTERN)]
VersionNo = Annotated[int, Field(ge=1, le=MAX_INT4)]


def _no_nul(v: str) -> str:
    if "\x00" in v:
        raise ValueError("문자열에 허용되지 않는 문자(NUL)가 있습니다")
    return v


Prompt = Annotated[str, Field(min_length=1, max_length=2000), AfterValidator(_no_nul)]


# 글자 표시 방향을 강제로 바꾸는 문자 (뒤에 오는 글·닉네임 순서를 뒤집어 보이게 할 수 있음)
_BIDI_CONTROLS = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _clean_text(v: str) -> str:
    """앞뒤 공백 제거, 줄바꿈·탭 외 제어 문자와 방향 제어 문자 거부."""
    if not isinstance(v, str):
        return v
    v = v.strip()
    if any((unicodedata.category(c) in ("Cc", "Cs") and c not in "\n\t") or c in _BIDI_CONTROLS for c in v):
        raise ValueError("허용되지 않는 문자가 있습니다")
    return v


def _single_line(v: str) -> str:
    if "\n" in v or "\t" in v:
        raise ValueError("한 줄로 입력해 주세요")
    return v


Text1 = BeforeValidator(_clean_text)
Username = Annotated[str, BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v),
                     Field(pattern=r"^[a-z0-9_]{4,20}$", description="영문 소문자·숫자·밑줄 4~20자")]
# NFKC 정규화 후 한글·영문·숫자·공백·_-. 만 (app/names.py)
Nickname = Annotated[str, BeforeValidator(normalize_nickname), Field(min_length=2, max_length=20)]
NewPassword = Annotated[str, Field(min_length=8, max_length=128)]
Title = Annotated[str, Text1, Field(min_length=1, max_length=100), AfterValidator(_single_line)]


class CageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width_mm: float = Field(ge=200, le=2000, description="케이지 내부 가로 mm")
    depth_mm: float = Field(ge=200, le=2000, description="케이지 내부 세로 mm")
    height_mm: float = Field(ge=100, le=1000, description="케이지 내부 높이 mm")


class HabitatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    species: str = Field(max_length=32, examples=["hamster"])
    size: str = Field(max_length=32, examples=["syrian"])
    count: int = Field(ge=1, le=10)
    cage: CageIn
    pet_id: EntityId | None = Field(default=None, description="내 반려동물 정보로 등록할 때")


class HabitatOut(BaseModel):
    id: str
    pet_id: str | None = None
    species: str
    species_name_ko: str
    size: str
    size_name_ko: str
    count: int
    cage: CageIn
    created_at: datetime


class DesignCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    habitat_id: EntityId
    prompt: Prompt


class DesignReviseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: Prompt
    base_version: VersionNo | None = Field(default=None, description="수정의 기준 버전 (기본: 최신)")


class PlacementOut(BaseModel):
    x_mm: float
    y_mm: float
    rotation_deg: int


class ItemOut(BaseModel):
    index: int
    template: str
    label_ko: str
    params: dict
    reason_ko: str
    placement: PlacementOut | None
    size_mm: list[float]           # 사용 자세 [가로, 세로, 높이]
    print_size_mm: list[float]     # 출력 자세 [X, Y, Z]
    mesh_url: str | None           # 케이지 좌표계로 배치된 STL (배치 실패 시 null)


class VersionSummary(BaseModel):
    version: int
    prompt: str
    passed: bool
    provider: str
    created_at: datetime


class VersionOut(BaseModel):
    version: int
    prompt: str
    provider: str
    summary_ko: str
    notes_ko: list[str]
    items: list[ItemOut]
    validation: dict
    export_allowed: bool
    created_at: datetime


class DesignOut(BaseModel):
    id: str
    title: str
    habitat: HabitatOut
    versions: list[VersionSummary]
    current: VersionOut
    is_owner: bool          # 수정·공유는 소유자만 (관리자는 볼 수만 있다. 소유자가 없는 옛 설계는 관리자가 소유자)
    shared: bool            # 커뮤니티 글에 첨부된 버전이 있는지
    shared_versions: list[int] = []  # 커뮤니티 글에 첨부되어 누구나 볼 수 있는 버전. 다른 사람에게는 이 버전만 보인다
    owner_nickname: str | None


class WaitlistIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    design_id: EntityId | None = None
    version: VersionNo | None = None


class WaitlistOut(BaseModel):
    ok: bool
    message_ko: str



class DesignListItem(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    version_count: int
    latest_version: int
    latest_passed: bool
    habitat: HabitatOut
    pet_name: str | None
    shared: bool


class DesignListOut(BaseModel):
    items: list[DesignListItem]
    total: int
    page: int
    page_size: int


# ── 회원 ───────────────────────────────────────────────────


class UserOut(BaseModel):
    id: str
    username: str
    nickname: str
    role: Literal["member", "admin"]
    created_at: datetime


class AuthStatusOut(BaseModel):
    auth_enabled: bool
    authenticated: bool
    user: UserOut | None
    signup_enabled: bool


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    nickname: Nickname
    password: NewPassword


class ProfileUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: Nickname


class PasswordChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: NewPassword


class MeOut(BaseModel):
    user: UserOut
    stats: dict[str, int]
    design_quota: dict[str, int | None]


# ── 반려동물 ───────────────────────────────────────────────


def _past_date(v: date | None) -> date | None:
    if v is not None and (v > date.today() or v < date(1990, 1, 1)):
        raise ValueError("생일은 1990-01-01 부터 오늘 사이로 입력해 주세요")
    return v


class PetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Text1, Field(min_length=1, max_length=40), AfterValidator(_single_line)]
    species: str = Field(max_length=32, examples=["hamster"])
    size: str = Field(max_length=32, examples=["syrian"])
    sex: Literal["male", "female", "unknown"] = "unknown"
    birth_date: Annotated[date | None, AfterValidator(_past_date)] = None
    # 제약은 str 쪽에만 건다 (str | None 전체에 걸면 null 이 올 때 검증 단계에서 500)
    notes: Annotated[str, Text1, Field(max_length=500)] | None = None
    cage: CageIn | None = None


class PetOut(BaseModel):
    id: str
    name: str
    species: str
    species_name_ko: str
    size: str
    size_name_ko: str
    sex: str
    birth_date: date | None
    notes: str | None
    cage: CageIn | None
    created_at: datetime
    updated_at: datetime


# ── 커뮤니티 ───────────────────────────────────────────────


class AuthorOut(BaseModel):
    nickname: str
    role: Literal["member", "admin"]


class PostIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    body: Annotated[str, Text1, Field(min_length=1, max_length=5000)]
    design_id: EntityId | None = None
    design_version: VersionNo | None = None


class PostUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    body: Annotated[str, Text1, Field(min_length=1, max_length=5000)] | None = None


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Text1, Field(min_length=1, max_length=1000)]


class CommentOut(BaseModel):
    id: str
    body: str
    author: AuthorOut
    created_at: datetime
    can_delete: bool


class SharedDesignOut(BaseModel):
    id: str
    version: int
    title: str
    summary_ko: str
    item_labels: list[str]
    passed: bool
    habitat: HabitatOut


class PostSummary(BaseModel):
    id: str
    title: str
    excerpt: str
    author: AuthorOut
    created_at: datetime
    comment_count: int
    has_design: bool


class PostListOut(BaseModel):
    items: list[PostSummary]
    total: int
    page: int
    page_size: int


class PostOut(BaseModel):
    id: str
    title: str
    body: str
    author: AuthorOut
    created_at: datetime
    updated_at: datetime
    design: SharedDesignOut | None
    comments: list[CommentOut]  # 최근 댓글 최대 200개 (오래된 것부터)
    comment_total: int           # 전체 댓글 수
    can_edit: bool
    can_delete: bool
