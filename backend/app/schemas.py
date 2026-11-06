"""API 요청·응답 스키마."""

from __future__ import annotations

import re
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
ID_RE = re.compile(r"[0-9a-f]{32}")  # 서버 코드에서는 항상 fullmatch 로 쓴다 (파이썬 re 의 $ 는 끝 줄바꿈 앞에서도 맞으므로 ^…$ 로 검사하지 않는다)
ID_PATTERN = rf"^{ID_RE.pattern}$"  # pydantic(rust regex)의 $ 는 문자열 끝에서만 맞는다 → fullmatch 와 같은 집합
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
    email: str | None = None       # 본인에게만 보인다 (로그인 상태 응답)
    email_verified: bool = False   # 관리자는 항상 true


class CaptchaOut(BaseModel):
    provider: Literal["turnstile"]
    site_key: str


class AuthStatusOut(BaseModel):
    auth_enabled: bool
    authenticated: bool
    user: UserOut | None
    signup_enabled: bool
    email_verification: bool = False   # 가입 시 이메일 필수 + 인증 전 설계·글쓰기 제한
    captcha: CaptchaOut | None = None  # 회원가입에 CAPTCHA 가 필요하면 위젯 설정
    verification_email_sent: bool | None = None  # 가입·이메일 변경 응답에서만: 인증 메일을 보냈는지


def _plain_address(v: str) -> str:
    """RFC 2047 인코딩(=?…?=)이 들어간 주소는 받지 않는다 (메일 헤더에서 줄바꿈 등으로 풀릴 수 있다)."""
    if "=?" in v or "?=" in v:
        raise ValueError("이메일 주소에 쓸 수 없는 문자가 있습니다")
    return v


Email = Annotated[EmailStr, Field(max_length=254), AfterValidator(_plain_address)]
CaptchaToken = Annotated[str, Field(max_length=2048)]


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    nickname: Nickname
    password: NewPassword
    email: Email | None = None             # 이메일 인증이 켜져 있으면 필수
    captcha_token: CaptchaToken | None = None  # CAPTCHA 가 켜져 있으면 필수


class VerifyEmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)


class ResendVerificationOut(BaseModel):
    sent: bool
    email: str | None
    message_ko: str


class EmailChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    current_password: str = Field(min_length=1, max_length=200)


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


# ── 가상 케이지 배치안 ─────────────────────────────────────

MAX_LAYOUT_ITEMS = 80


class LayoutItemIn(BaseModel):
    """배치한 에셋 하나. 좌표는 케이지 좌표계(mm, 원점=앞-왼쪽 바닥 모서리)의 에셋 바닥 중심."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$", description="화면이 붙인 항목 ID (배치안 안에서 유일)")
    asset: str = Field(pattern=r"^[a-z0-9_]{1,40}$", description="에셋 카탈로그 키")
    x_mm: float = Field(ge=-500, le=2500)
    y_mm: float = Field(ge=-500, le=2500)
    rotation_deg: float = Field(ge=0, lt=360)


def _unique_item_ids(items: list[LayoutItemIn]) -> list[LayoutItemIn]:
    if len({i.id for i in items}) != len(items):
        raise ValueError("항목 ID 가 겹칩니다")
    return items


class CageLayoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Text1, Field(min_length=1, max_length=40), AfterValidator(_single_line)]
    species: str = Field(max_length=32, examples=["hamster"])
    size: str = Field(max_length=32, examples=["syrian"])
    cage: CageIn
    pet_id: EntityId | None = None
    items: Annotated[list[LayoutItemIn], Field(max_length=MAX_LAYOUT_ITEMS), AfterValidator(_unique_item_ids)] = []


class CageLayoutSummary(BaseModel):
    id: str
    name: str
    species: str
    size: str
    size_name_ko: str
    pet_id: str | None
    cage: CageIn
    item_count: int
    created_at: datetime
    updated_at: datetime


class CageLayoutOut(CageLayoutSummary):
    items: list[LayoutItemIn]


# ── 커뮤니티 ───────────────────────────────────────────────


class AuthorOut(BaseModel):
    nickname: str
    role: Literal["member", "admin"]


MAX_POST_IMAGES = 4
_Line = lambda n: Annotated[str, Text1, Field(min_length=1, max_length=n), AfterValidator(_single_line)]  # noqa: E731


class PostImage(BaseModel):
    """글에 넣는 사진. 사이트에 함께 배포한 파일(frontend/public/community-images/)만 쓰고,
    촬영자·라이선스·원본 주소를 함께 보여 준다 (CC 라이선스의 출처 표시)."""

    model_config = ConfigDict(extra="forbid")

    src: str = Field(pattern=r"^/community-images/[a-z0-9][a-z0-9-]{0,60}\.(webp|jpg|png)$")
    alt: _Line(120)
    width: int = Field(ge=1, le=4000)
    height: int = Field(ge=1, le=4000)
    credit: _Line(200)
    license: _Line(60)
    source_url: str = Field(pattern=r"^https://[^\s]{1,490}$")


PostImages = Annotated[list[PostImage], Field(max_length=MAX_POST_IMAGES)]


class PostIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    body: Annotated[str, Text1, Field(min_length=1, max_length=5000)]
    design_id: EntityId | None = None
    design_version: VersionNo | None = None
    images: PostImages = Field(default=[], description="사진 (운영팀만)")


class PostUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    body: Annotated[str, Text1, Field(min_length=1, max_length=5000)] | None = None
    images: PostImages | None = Field(default=None, description="사진 전체를 바꾼다 (운영팀만, 빈 목록이면 모두 뺀다)")


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


# ── 탐색 ───────────────────────────────────────────────

MARKET_CATEGORIES = {
    "hideout": "은신처", "tunnel": "터널", "ramp": "경사로·계단", "sand_bath": "모래목욕통",
    "cage": "케이지 전체", "layout": "가상 케이지 배치", "etc": "기타",
}
MAX_ITEM_FILES = 5


class UploadStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, Text1, Field(min_length=1, max_length=120), AfterValidator(_single_line)]
    size: int = Field(ge=1, le=2**31 - 1)
    kind: Literal["model", "image"] = "model"


class UploadStartOut(BaseModel):
    id: str
    chunk_bytes: int
    chunks: int


class MarketFileOut(BaseModel):
    id: str
    kind: Literal["model", "image"]
    filename: str
    format: str
    size: int
    sha256: str
    # 내려받기·보기 주소. "/" 로 시작하면 API 기준 경로, 아니면 공개 주소(Blob)
    download_url: str
    view_url: str | None = None
    # STL·3MF: 외곽 크기 [x, y, z] mm 와 3D 로 불러올 주소 (가상 케이지에 놓을 때). SKP 는 없음
    dims_mm: list[float] | None = None
    mesh_url: str | None = None
    attached: bool = False  # 작품에 붙었거나 공유한 배치에 들어 있어 누구나 볼 수 있는지


class LayoutSnapshot(BaseModel):
    """탐색에 공유한 가상 케이지 배치 (공유할 때의 배치안 사본)"""

    name: str
    species: str
    size: str
    size_name_ko: str = ""
    cage: CageIn
    items: list[LayoutItemIn]


class MarketItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    description: Annotated[str, Text1, Field(min_length=1, max_length=3000)]
    category: Literal["hideout", "tunnel", "ramp", "sand_bath", "cage", "layout", "etc"]
    file_ids: Annotated[list[EntityId], Field(max_length=MAX_ITEM_FILES)] = []
    image_file_id: EntityId | None = None
    design_id: EntityId | None = None
    design_version: VersionNo | None = None
    layout_id: EntityId | None = Field(default=None, description="공유할 내 가상 케이지 배치안")
    post_to_community: bool = True


class MarketItemUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: Annotated[str, Text1, Field(min_length=1, max_length=3000)] | None = None
    category: Literal["hideout", "tunnel", "ramp", "sand_bath", "cage", "layout", "etc"] | None = None


class MarketItemSummary(BaseModel):
    id: str
    title: str
    category: str
    category_name_ko: str
    author: AuthorOut
    formats: list[str]
    image: MarketFileOut | None
    has_design: bool
    has_layout: bool = False
    download_count: int
    created_at: datetime
    reason_ko: str | None = None  # 추천 목록에서만: 추천한 까닭


class MarketItemOut(MarketItemSummary):
    description: str
    files: list[MarketFileOut]
    design: SharedDesignOut | None
    layout: LayoutSnapshot | None = None
    post_id: str | None
    updated_at: datetime
    can_edit: bool
    can_delete: bool


class MarketListOut(BaseModel):
    items: list[MarketItemSummary]
    total: int
    page: int
    page_size: int


class MarketItemBrief(BaseModel):
    """커뮤니티 글에 붙여 보여 주는 공유 작품 요약"""

    id: str
    title: str
    formats: list[str]
    image: MarketFileOut | None


class PostSummary(BaseModel):
    id: str
    title: str
    excerpt: str
    author: AuthorOut
    created_at: datetime
    comment_count: int
    has_design: bool
    thumbnail: PostImage | None = None  # 첫 사진 (목록에 작게 보여 준다)
    market_item_id: str | None = None  # 공유 작품 소개 글이면 그 작품 ID


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
    images: list[PostImage] = []
    market_item: MarketItemBrief | None = None  # 공유 작품 소개 글이면 그 작품
    comments: list[CommentOut]  # 최근 댓글 최대 200개 (오래된 것부터)
    comment_total: int           # 전체 댓글 수
    can_edit: bool
    can_delete: bool
