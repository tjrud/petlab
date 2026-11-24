"""Part DSL v1 파일 스키마 (설계 §5.2).

- pydantic 모델(PartFile 등)로 엄격하게 읽는다: 모르는 항목, 형이 다른 값, 허용하지 않은 null 은 모두 오류다.
- 오류는 JSON 포인터 경로를 단 DslError 로 바꾼다 (DSL010 값, DSL011 빠진 항목, DSL012 모르는 항목, DSL013 JSON 형,
  DSL014 게시 파일의 key·version·파일 이름 불일치·지원하지 않는 dsl 버전).
- json_schema() 는 같은 규칙을 JSON Schema(draft 2020-12)로 낸다 (app/library/part.schema.json 을 만드는 데 쓴다).
  JSON Schema 로 적을 수 없는 규칙(기본값이 범위 안, 선택지에 기본값 포함, 게시 파일의 key 와 version)은
  pydantic 쪽에만 있다.

이 모듈은 가볍다 (pydantic 과 표준 라이브러리만): 형상 커널을 불러오지 않는다.
"""

from __future__ import annotations

import copy
import difflib
import json
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic.functional_validators import PlainValidator
from pydantic_core import PydanticCustomError

from app.library.errors import DslError, DslErrors, pointer

DSL_VERSION = 1
SUPPORTED_DSL = (1,)

# ── 기본 형 ──

KEY_PATTERN = r"^[a-z][a-z0-9_]{2,40}@v[1-9][0-9]{0,2}$"
FAMILY_PATTERN = r"^[a-z][a-z0-9_]{2,40}$"
PART_ID_PATTERN = r"^(?!model_)(?!body$)[a-z][a-z0-9_]{0,20}$"
PARAM_NAME_PATTERN = r"^(?!model_)[a-z][a-z0-9_]{0,30}$"
LET_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,30}$"
NAME_PATTERN = r"^[a-z][a-z0-9_]{0,30}$"
PRINT_KEY_PATTERN = r"^[a-z][a-z0-9_]{0,20}$"
ANCHOR_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,20}$"
CHOICE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,20}$"
COLOR_PATTERN = r"^#[0-9a-f]{6}$"
MAX_EXPR_CHARS = 400
NAME_KO_MAX = 20
DESCRIPTION_KO_MAX = 200

Role = Literal["host", "room_host", "accessory", "none"]
AxisName = Literal["+X", "-X", "+Y", "-Y", "+Z", "-Z"]
SideName = Literal["front", "back", "left", "right"]
Rotation = Literal["upright", "inverted", "front_down", "back_down", "left_down", "right_down"]
ProbeShape = Literal["round_arch", "pointed_arch", "box", "house"]
RuleKey = Literal["entrance_min_diameter_mm", "tunnel_min_inner_diameter_mm"]

# null 을 적을 수 있는 자리 (나머지는 null 이 오류다)
NULLABLE_POINTERS = frozenset({"/color", "/level_field", "/height_field", "/face_needs/min", "/face_needs/max"})


def _num(v: object) -> object:
    """수 자리: JSON 숫자 또는 식 문자열 (최대 400자). bool 은 숫자가 아니다."""
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise PydanticCustomError("num_type", "expected a number or an expression string")
    if isinstance(v, str):
        if not v:
            raise PydanticCustomError("string_too_short", "an expression string cannot be empty")
        if len(v) > MAX_EXPR_CHARS:
            raise PydanticCustomError("string_too_long", f"an expression has at most {MAX_EXPR_CHARS} characters")
    return v


Num = Annotated[int | float | str, PlainValidator(_num)]
Expr = Annotated[str, Field(min_length=1, max_length=MAX_EXPR_CHARS)]
Vec3 = Annotated[list[Num], Field(min_length=3, max_length=3)]
Vec2 = Annotated[list[Num], Field(min_length=2, max_length=2)]
Name = Annotated[str, Field(pattern=NAME_PATTERN)]
Word = Annotated[str, Field(min_length=1, max_length=20)]


def _unique(values: list[str] | None) -> list[str] | None:
    if values is not None and len(set(values)) != len(values):
        dup = sorted({v for v in values if values.count(v) > 1})
        raise PydanticCustomError("unique_items", "items must be unique; repeated: {dup}", {"dup": ", ".join(dup)})
    return values


Names = Annotated[list[Name], Field(max_length=12)]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, regex_engine="python-re")


class Text(_Strict):
    ko: Annotated[str, Field(min_length=1, max_length=240)]
    en: Annotated[str, Field(min_length=1, max_length=240)]


class NameText(Text):
    ko: Annotated[str, Field(min_length=1, max_length=NAME_KO_MAX)]


class DescriptionText(Text):
    ko: Annotated[str, Field(min_length=1, max_length=DESCRIPTION_KO_MAX)]


class Keywords(_Strict):
    ko: Annotated[list[Word], Field(max_length=8)]
    en: Annotated[list[Word], Field(max_length=8)]


class AttachOrder(_Strict):
    slide: Names | None = None
    passage: Names | None = None

    @field_validator("slide", "passage")
    @classmethod
    def _unique_names(cls, v: list[str] | None) -> list[str] | None:
        return _unique(v)


# ── 파라미터 ──

class _Bounded(_Strict):
    @model_validator(mode="after")
    def _check_bounds(self):  # type: ignore[no-untyped-def]
        lo, hi, d = self.min, self.max, self.default  # type: ignore[attr-defined]
        if lo >= hi:
            raise PydanticCustomError("bounds", "min ({lo}) must be less than max ({hi})", {"lo": lo, "hi": hi})
        if not lo <= d <= hi:
            raise PydanticCustomError("bounds", "default ({d}) must be within [min, max] = [{lo}, {hi}]",
                                      {"d": d, "lo": lo, "hi": hi})
        return self


class NumberParam(_Bounded):
    type: Literal["number"]
    default: float
    min: float
    max: float
    rule_default: Expr | None = None
    desc: Text


class IntegerParam(_Bounded):
    type: Literal["integer"]
    default: int
    min: int
    max: int
    rule_default: Expr | None = None
    desc: Text


class ChoiceParam(_Strict):
    type: Literal["choice"]
    default: str
    choices: Annotated[list[Annotated[str, Field(pattern=CHOICE_PATTERN)]], Field(min_length=2, max_length=6)]
    choice_labels: dict[str, Text] | None = None
    desc: Text

    @field_validator("choices")
    @classmethod
    def _unique_choices(cls, v: list[str]) -> list[str]:
        return _unique(v)  # type: ignore[return-value]

    @model_validator(mode="after")
    def _check_choices(self) -> ChoiceParam:
        if self.default not in self.choices:
            raise PydanticCustomError("choice_default", "default '{d}' is not one of the choices: {c}",
                                      {"d": self.default, "c": ", ".join(self.choices)})
        extra = sorted(set(self.choice_labels or {}) - set(self.choices))
        if extra:
            raise PydanticCustomError("choice_labels", "choice_labels has keys that are not choices: {k}",
                                      {"k": ", ".join(extra)})
        return self


class BoolParam(_Strict):
    type: Literal["bool"]
    default: bool
    desc: Text


Param = Annotated[NumberParam | IntegerParam | ChoiceParam | BoolParam, Field(discriminator="type")]


class Let(_Strict):
    name: Annotated[str, Field(pattern=LET_NAME_PATTERN)]
    expr: Expr


class Constraint(_Strict):
    field: str
    min: Expr | None = None
    max: Expr | None = None
    source: Literal["species", "printing", "geometry"]
    reason: Text
    blocking: bool = True
    when: Expr | None = None

    @model_validator(mode="after")
    def _one_bound(self) -> Constraint:
        if (self.min is None) == (self.max is None):
            raise PydanticCustomError("one_bound", "a constraint has exactly one of min or max")
        return self


class Check(_Strict):
    fail_if: Expr
    message: Text


# ── 형상 단계 ──

class _Step(_Strict):
    mode: Literal["add", "cut"] = "add"
    part: Annotated[str, Field(pattern=PRINT_KEY_PATTERN)] = "body"
    when: Expr | None = None
    repeat: Annotated[dict[Literal["i", "j"], Num], Field(min_length=1, max_length=2)] | None = None
    id: Annotated[str, Field(pattern=NAME_PATTERN)] | None = None
    note: Annotated[str, Field(max_length=200)] | None = None


class BoxStep(_Step):
    op: Literal["box"]
    size: Vec3
    at: Vec3 | None = None
    align: Literal["bottom", "center"] = "bottom"


class CylinderStep(_Step):
    op: Literal["cylinder"]
    r: Num
    h: Num
    axis: Literal["x", "y", "z"]
    at: Vec3 | None = None
    align: Literal["bottom", "center"] = "bottom"


class PrismStep(_Step):
    op: Literal["prism"]
    plane: Literal["xz", "yz", "xy"]
    points: Annotated[list[Vec2], Field(min_length=3, max_length=32)]
    depth: Num
    at: Vec3 | None = None


class PassageStep(_Step):
    op: Literal["passage"]
    mode: Literal["cut"]  # 필수: 통로는 자르기만 한다
    shape: Expr
    width: Num
    axis: Literal["x", "y"]
    length: Num
    at: Vec3 | None = None


Step = Annotated[BoxStep | CylinderStep | PrismStep | PassageStep, Field(discriminator="op")]


class PrintPart(_Strict):
    key: Annotated[str, Field(pattern=PRINT_KEY_PATTERN)]
    name: Text
    rotation: Rotation


# ── 연결 지점 ──

class Door(_Strict):
    when: Expr
    width: Num
    profile: Expr


class AnchorFields(_Strict):
    width: str | None = None
    height: str | None = None
    wall: str | None = None
    port: str | None = None
    profile: str | None = None


class Anchor(_Strict):
    origin: Vec3
    normal: AxisName
    up: AxisName
    part: str = "body"
    side: SideName | None = None
    wall: Num | None = None
    door: Door | None = None
    mount: Vec3 | None = None
    openable: bool = False
    fields: AnchorFields | None = None


class Open(_Strict):
    anchor: str
    when: Expr | None = None
    set: Annotated[dict[str, Num], Field(min_length=1)]


class FaceNeeds(_Strict):
    min: Num | None = None
    max: Num | None = None


# ── 특징 ──

class AccessSide(_Strict):
    side: SideName
    when: Expr | None = None


class VentOpening(_Strict):
    kind: Literal["vent", "window"]
    step: str
    axis: Literal["x", "y", "z"] | None = None
    label: Text
    when: Expr | None = None


class Probe(_Strict):
    shape: ProbeShape
    axis: Literal["x", "y"]
    at: Vec3
    length: Num


class PassageOpening(_Strict):
    kind: Literal["passage"]
    size: Num
    rule_key: RuleKey | None = None
    label: Text
    when: Expr | None = None
    probe: Probe


Opening = Annotated[VentOpening | PassageOpening, Field(discriminator="kind")]


class Features(_Strict):
    min_wall: Num | None = None
    access_sides: Annotated[list[AccessSide], Field(max_length=4)] | None = None
    climb_height: Num | None = None
    slope_deg: Num | None = None
    step_height: Num | None = None
    openings: Annotated[list[Opening], Field(max_length=8)] | None = None


# ── 파일 ──

class PartFile(_Strict):
    """부품 파일 한 개. 초안(draft)은 key·version 이 없고, 게시 파일은 둘 다 있다 (parse_part(published=True))."""

    dsl: Literal[1]
    family: Annotated[str, Field(pattern=FAMILY_PATTERN)]
    version: Annotated[int, Field(ge=1, le=999)] | None = None
    key: Annotated[str, Field(pattern=KEY_PATTERN)] | None = None
    name: NameText
    description: DescriptionText
    keywords: Keywords
    fulfills: Annotated[list[Annotated[str, Field(min_length=1, max_length=60)]], Field(max_length=8)] = []
    part_id: Annotated[str, Field(pattern=PART_ID_PATTERN)]
    color: Annotated[str, Field(pattern=COLOR_PATTERN)] | None = None
    habitats: Annotated[list[Literal["cage"]], Field(min_length=1, max_length=1)]
    role: Role
    attach_order: AttachOrder = AttachOrder()
    passes_access: bool = False
    level_field: str | None = None
    height_field: str | None = None
    size_fields: Names = []
    door_fields: Names = []
    params: Annotated[dict[Annotated[str, Field(pattern=PARAM_NAME_PATTERN)], Param],
                      Field(min_length=1, max_length=12)]
    let: Annotated[list[Let], Field(max_length=24)] = []
    constraints: Annotated[list[Constraint], Field(max_length=24)] = []
    checks: Annotated[list[Check], Field(max_length=8)] = []
    body: Annotated[list[Step], Field(min_length=1, max_length=48)]
    print: Annotated[list[PrintPart], Field(min_length=1, max_length=3)]
    anchors: Annotated[dict[Annotated[str, Field(pattern=ANCHOR_NAME_PATTERN)], Anchor],
                       Field(max_length=12)] = {}
    opens: Annotated[list[Open], Field(max_length=8)] = []
    envelope: Vec3 | None = None
    face_needs: FaceNeeds | None = None
    features: Features

    @field_validator("size_fields", "door_fields")
    @classmethod
    def _unique_names(cls, v: list[str]) -> list[str]:
        return _unique(v)  # type: ignore[return-value]

    @model_validator(mode="after")
    def _key_matches(self) -> PartFile:
        if self.key is not None and self.version is not None and self.key != f"{self.family}@v{self.version}":
            raise PydanticCustomError("key_mismatch", "key '{k}' must equal family@v<version> = '{w}'",
                                      {"k": self.key, "w": f"{self.family}@v{self.version}"})
        if (self.key is None) != (self.version is None):
            raise PydanticCustomError("key_mismatch", "key and version are set together (publish injects both)")
        return self

    @property
    def is_published(self) -> bool:
        return self.key is not None


# ── 오류 변환 ──

# 모든 모델의 필드 이름 (모르는 항목의 "did you mean" 후보)
_MODELS: tuple[type[BaseModel], ...] = (
    Text, Keywords, AttachOrder, NumberParam, IntegerParam, ChoiceParam, BoolParam, Let, Constraint, Check,
    BoxStep, CylinderStep, PrismStep, PassageStep, PrintPart, Door, AnchorFields, Anchor, Open, FaceNeeds,
    AccessSide, VentOpening, Probe, PassageOpening, Features, PartFile,
)
_ALL_FIELDS = sorted({f for m in _MODELS for f in m.model_fields})
_DISCRIMINATORS = ("type", "op", "kind")
_TYPE_ERRORS = {"model_type", "model_attributes_type", "dict_type", "list_type", "string_type", "float_type",
                "int_type", "bool_type", "num_type", "int_from_float", "literal_error_type"}
_CODE_BY_ERROR = {"missing": "DSL011", "extra_forbidden": "DSL012", "key_mismatch": "DSL014"}


def _loc_pointer(loc: tuple[Any, ...], data: object) -> str:
    """pydantic loc → 입력 데이터의 JSON 포인터. 판별 유니언의 태그('number', 'box' 등)와 '[key]' 는 건너뛴다."""
    parts: list[object] = []
    node: object = data
    for i, el in enumerate(loc):
        last = i == len(loc) - 1
        if isinstance(node, dict):
            if el in node:
                parts.append(el)
                node = node[el]
                continue
            if isinstance(el, str) and any(node.get(d) == el for d in _DISCRIMINATORS):
                continue
            if el == "[key]":
                continue
            if last or isinstance(el, str):
                parts.append(el)
                node = None
            continue
        if isinstance(node, list) and isinstance(el, int) and 0 <= el < len(node):
            parts.append(el)
            node = node[el]
            continue
        if el == "[key]":
            continue
        if isinstance(el, (str, int)) and node is not None:
            parts.append(el)
            node = None
    return pointer(*parts)


def _hint(err: dict, ptr: str) -> str:
    t = err["type"]
    if t == "extra_forbidden":
        name = ptr.rsplit("/", 1)[-1]
        close = difflib.get_close_matches(name, _ALL_FIELDS, n=1, cutoff=0.6)
        return f"did you mean {close[0]!r}?" if close else "remove the field"
    if t == "missing":
        return "add the field"
    if t == "union_tag_invalid":
        return "check the spelling of the type/op/kind value"
    if t in ("string_pattern_mismatch",):
        return "use lower-case letters, digits and _ (see the pattern)"
    return ""


def _from_validation(e: ValidationError, data: object) -> list[DslError]:
    out: list[DslError] = []
    seen: set[tuple[str, str]] = set()
    for err in e.errors(include_url=False):
        ptr = _loc_pointer(tuple(err["loc"]), data)
        t = err["type"]
        if t == "key_mismatch":
            ptr = "/key"
        if ptr == "/dsl" and t.startswith("literal_error"):
            code, msg = "DSL014", (f"unsupported dsl version {err.get('input')!r}; this server supports "
                                   f"{', '.join(map(str, SUPPORTED_DSL))}")
        else:
            code = _CODE_BY_ERROR.get(t) or ("DSL013" if t in _TYPE_ERRORS or t.endswith("_type") else "DSL010")
            msg = err["msg"]
            if t == "missing":
                msg = f"missing required field '{ptr.rsplit('/', 1)[-1]}'"
            elif t == "extra_forbidden":
                msg = f"unknown field '{ptr.rsplit('/', 1)[-1]}'"
        if (ptr, code) in seen:
            continue
        seen.add((ptr, code))
        out.append(DslError(code, ptr, msg, _hint(err, ptr)))
    return out


def _nulls(data: object, ptr: str = "") -> list[DslError]:
    """허용하지 않은 자리의 null."""
    out: list[DslError] = []
    if isinstance(data, dict):
        for k, v in data.items():
            p = f"{ptr}/{pointer(k)[1:]}"
            if v is None:
                if p not in NULLABLE_POINTERS:
                    out.append(DslError("DSL013", p, "null is not allowed here", "remove the field to use its default"))
            else:
                out += _nulls(v, p)
    elif isinstance(data, list):
        for i, v in enumerate(data):
            p = f"{ptr}/{i}"
            if v is None:
                out.append(DslError("DSL013", p, "null is not allowed here"))
            else:
                out += _nulls(v, p)
    return out


def parse_part(data: object, *, published: bool = False, stem: str | None = None) -> PartFile:
    """부품 파일(JSON 을 읽은 dict)을 엄격하게 읽는다 (S01). 오류는 모두 모아 DslErrors 로 낸다.

    published=True 면 게시 파일 규칙을 더한다: key·version 이 있어야 하고, stem(파일 이름에서 .json 을 뺀 것)을
    주면 key 와 같아야 한다."""
    if not isinstance(data, dict):
        raise DslErrors.of([DslError("DSL013", "", f"a part file is a JSON object, got {type(data).__name__}")])
    errors = _nulls(data)
    if errors:
        raise DslErrors.of(errors)
    try:
        part = PartFile.model_validate(data)
    except ValidationError as e:
        raise DslErrors.of(_from_validation(e, data)) from None
    if published:
        if part.key is None:
            raise DslErrors.of([DslError("DSL014", "/key", "a published file needs key and version",
                                         "publish injects them; do not write them by hand")])
        if stem is not None and stem != part.key:
            raise DslErrors.of([DslError("DSL014", "/key", f"key {part.key!r} does not match the file name "
                                                           f"{stem!r}.json")])
    return part


def load_part_json(text: str | bytes, *, published: bool = False, stem: str | None = None) -> PartFile:
    """JSON 문자열을 읽어 parse_part. JSON 문법 오류도 DslError (DSL010) 로 낸다."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise DslErrors.of([DslError("DSL010", "", f"invalid JSON: {e}")]) from None
    return parse_part(data, published=published, stem=stem)


# ── JSON Schema ──

# 설계 §5.2 의 규범 스키마. 덧붙인 것: name.ko ≤ 20자, description.ko ≤ 200자 (설명에 적힌 한도를 규칙으로),
# 그리고 각 항목 설명(description). pydantic 모델과 같은지는 tests/test_library_schema.py 가 확인한다.
_SCHEMA_JSON = r"""
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://nestforge.local/part-dsl-v1.schema.json",
  "title": "NestForge Part DSL v1",
  "description": "A part for the NestForge library. Coordinates are mm in the use pose: Z up, floor at Z = 0, X right, Y back (front is -Y). Expression slots are strings in a small Python-like language; numeric slots also accept JSON numbers.",
  "type": "object",
  "additionalProperties": false,
  "required": ["dsl", "family", "name", "description", "keywords", "part_id", "habitats", "role",
               "params", "body", "print", "features"],
  "properties": {
    "dsl": {"const": 1, "description": "DSL version"},
    "family": {"type": "string", "pattern": "^[a-z][a-z0-9_]{2,40}$", "description": "lineage name; not a code template key"},
    "version": {"type": "integer", "minimum": 1, "maximum": 999, "description": "set by publish"},
    "key": {"type": "string", "pattern": "^[a-z][a-z0-9_]{2,40}@v[1-9][0-9]{0,2}$", "description": "family@v<version>, set by publish"},
    "name": {"$ref": "#/$defs/nameText", "description": "display name; ko <= 20 chars"},
    "description": {"$ref": "#/$defs/descriptionText", "description": "catalog text; ko <= 200 chars, en <= 240"},
    "keywords": {"type": "object", "additionalProperties": false, "required": ["ko", "en"],
                 "properties": {"ko": {"$ref": "#/$defs/words"}, "en": {"$ref": "#/$defs/words"}}},
    "fulfills": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1, "maxLength": 60},
                 "description": "normalised part-request names this part answers"},
    "part_id": {"type": "string", "pattern": "^(?!model_)(?!body$)[a-z][a-z0-9_]{0,20}$", "description": "default part id in assemblies"},
    "color": {"type": ["string", "null"], "pattern": "^#[0-9a-f]{6}$", "default": null},
    "habitats": {"type": "array", "minItems": 1, "maxItems": 1, "items": {"const": "cage"}},
    "role": {"enum": ["host", "room_host", "accessory", "none"],
             "description": "host: mounts only, root of an assembly; room_host: >= 1 door; accessory: slide child; none: standalone only"},
    "attach_order": {"type": "object", "additionalProperties": false, "default": {},
                     "properties": {"slide": {"$ref": "#/$defs/names"}, "passage": {"$ref": "#/$defs/names"}}},
    "passes_access": {"type": "boolean", "default": false},
    "level_field": {"type": ["string", "null"], "default": null},
    "height_field": {"type": ["string", "null"], "default": null},
    "size_fields": {"$ref": "#/$defs/names", "default": []},
    "door_fields": {"$ref": "#/$defs/names", "default": []},
    "params": {"type": "object", "minProperties": 1, "maxProperties": 12,
               "propertyNames": {"pattern": "^(?!model_)[a-z][a-z0-9_]{0,30}$"},
               "additionalProperties": {"$ref": "#/$defs/param"},
               "description": "ordered; wall_thickness_mm is required; lengths end _mm, angles _deg, counts _count"},
    "let": {"type": "array", "maxItems": 24, "default": [],
            "items": {"type": "object", "additionalProperties": false, "required": ["name", "expr"],
                      "properties": {"name": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]{0,30}$"},
                                     "expr": {"$ref": "#/$defs/expr"}}}},
    "constraints": {"type": "array", "maxItems": 24, "default": [], "items": {"$ref": "#/$defs/constraint"}},
    "checks": {"type": "array", "maxItems": 8, "default": [], "items": {"$ref": "#/$defs/check"}},
    "body": {"type": "array", "minItems": 1, "maxItems": 48, "items": {"$ref": "#/$defs/step"}},
    "print": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"$ref": "#/$defs/print"}},
    "anchors": {"type": "object", "maxProperties": 12, "default": {},
                "propertyNames": {"pattern": "^[a-z][a-z0-9_]{0,20}$"},
                "additionalProperties": {"$ref": "#/$defs/anchor"}},
    "opens": {"type": "array", "maxItems": 8, "default": [], "items": {"$ref": "#/$defs/open"}},
    "envelope": {"$ref": "#/$defs/vec3", "description": "analytic outer size (x, y, z) in use pose"},
    "face_needs": {"type": "object", "additionalProperties": false,
                   "properties": {"min": {"$ref": "#/$defs/numOrNull"}, "max": {"$ref": "#/$defs/numOrNull"}}},
    "features": {"$ref": "#/$defs/features"}
  },
  "$defs": {
    "expr": {"type": "string", "minLength": 1, "maxLength": 400},
    "num": {"type": ["number", "string"], "minLength": 1, "maxLength": 400},
    "numOrNull": {"type": ["number", "string", "null"], "minLength": 1, "maxLength": 400},
    "vec3": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"$ref": "#/$defs/num"}},
    "names": {"type": "array", "maxItems": 12, "uniqueItems": true,
              "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,30}$"}},
    "words": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1, "maxLength": 20}},
    "text": {"type": "object", "additionalProperties": false, "required": ["ko", "en"],
             "properties": {"ko": {"type": "string", "minLength": 1, "maxLength": 240},
                            "en": {"type": "string", "minLength": 1, "maxLength": 240}}},
    "nameText": {"type": "object", "additionalProperties": false, "required": ["ko", "en"],
                 "properties": {"ko": {"type": "string", "minLength": 1, "maxLength": 20},
                                "en": {"type": "string", "minLength": 1, "maxLength": 240}}},
    "descriptionText": {"type": "object", "additionalProperties": false, "required": ["ko", "en"],
                        "properties": {"ko": {"type": "string", "minLength": 1, "maxLength": 200},
                                       "en": {"type": "string", "minLength": 1, "maxLength": 240}}},
    "axisName": {"enum": ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]},
    "side": {"enum": ["front", "back", "left", "right"]},
    "param": {
      "type": "object",
      "required": ["type", "default", "desc"],
      "oneOf": [
        {"properties": {"type": {"const": "number"}, "default": {"type": "number"},
                        "min": {"type": "number"}, "max": {"type": "number"},
                        "rule_default": {"$ref": "#/$defs/expr"}, "desc": {"$ref": "#/$defs/text"}},
         "required": ["min", "max"], "additionalProperties": false},
        {"properties": {"type": {"const": "integer"}, "default": {"type": "integer"},
                        "min": {"type": "integer"}, "max": {"type": "integer"},
                        "rule_default": {"$ref": "#/$defs/expr"}, "desc": {"$ref": "#/$defs/text"}},
         "required": ["min", "max"], "additionalProperties": false},
        {"properties": {"type": {"const": "choice"}, "default": {"type": "string"},
                        "choices": {"type": "array", "minItems": 2, "maxItems": 6, "uniqueItems": true,
                                    "items": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]{0,20}$"}},
                        "choice_labels": {"type": "object", "additionalProperties": {"$ref": "#/$defs/text"}},
                        "desc": {"$ref": "#/$defs/text"}},
         "required": ["choices"], "additionalProperties": false},
        {"properties": {"type": {"const": "bool"}, "default": {"type": "boolean"},
                        "desc": {"$ref": "#/$defs/text"}},
         "additionalProperties": false}
      ]
    },
    "constraint": {"type": "object", "additionalProperties": false,
                   "required": ["field", "source", "reason"],
                   "properties": {"field": {"type": "string"}, "min": {"$ref": "#/$defs/expr"},
                                  "max": {"$ref": "#/$defs/expr"},
                                  "source": {"enum": ["species", "printing", "geometry"]},
                                  "reason": {"$ref": "#/$defs/text"}, "blocking": {"type": "boolean", "default": true},
                                  "when": {"$ref": "#/$defs/expr"}},
                   "oneOf": [{"required": ["min"], "not": {"required": ["max"]}},
                             {"required": ["max"], "not": {"required": ["min"]}}]},
    "check": {"type": "object", "additionalProperties": false, "required": ["fail_if", "message"],
              "properties": {"fail_if": {"$ref": "#/$defs/expr"}, "message": {"$ref": "#/$defs/text"}}},
    "stepCommon": {"properties": {"mode": {"enum": ["add", "cut"], "default": "add"},
                                  "part": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,20}$", "default": "body"},
                                  "when": {"$ref": "#/$defs/expr"},
                                  "repeat": {"type": "object", "maxProperties": 2, "minProperties": 1,
                                             "propertyNames": {"enum": ["i", "j"]},
                                             "additionalProperties": {"$ref": "#/$defs/num"}},
                                  "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,30}$"},
                                  "note": {"type": "string", "maxLength": 200}}},
    "step": {"oneOf": [
      {"allOf": [{"$ref": "#/$defs/stepCommon"}], "type": "object", "required": ["op", "size"],
       "properties": {"op": {"const": "box"}, "size": {"$ref": "#/$defs/vec3"}, "at": {"$ref": "#/$defs/vec3"},
                      "align": {"enum": ["bottom", "center"], "default": "bottom"},
                      "mode": {}, "part": {}, "when": {}, "repeat": {}, "id": {}, "note": {}},
       "additionalProperties": false},
      {"allOf": [{"$ref": "#/$defs/stepCommon"}], "type": "object", "required": ["op", "r", "h", "axis"],
       "properties": {"op": {"const": "cylinder"}, "r": {"$ref": "#/$defs/num"}, "h": {"$ref": "#/$defs/num"},
                      "axis": {"enum": ["x", "y", "z"]}, "at": {"$ref": "#/$defs/vec3"},
                      "align": {"enum": ["bottom", "center"], "default": "bottom"},
                      "mode": {}, "part": {}, "when": {}, "repeat": {}, "id": {}, "note": {}},
       "additionalProperties": false},
      {"allOf": [{"$ref": "#/$defs/stepCommon"}], "type": "object", "required": ["op", "plane", "points", "depth"],
       "properties": {"op": {"const": "prism"}, "plane": {"enum": ["xz", "yz", "xy"]},
                      "points": {"type": "array", "minItems": 3, "maxItems": 32,
                                 "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"$ref": "#/$defs/num"}}},
                      "depth": {"$ref": "#/$defs/num"}, "at": {"$ref": "#/$defs/vec3"},
                      "mode": {}, "part": {}, "when": {}, "repeat": {}, "id": {}, "note": {}},
       "additionalProperties": false},
      {"allOf": [{"$ref": "#/$defs/stepCommon"}], "type": "object",
       "required": ["op", "shape", "width", "axis", "length", "mode"],
       "properties": {"op": {"const": "passage"}, "shape": {"$ref": "#/$defs/expr"}, "width": {"$ref": "#/$defs/num"},
                      "axis": {"enum": ["x", "y"]}, "length": {"$ref": "#/$defs/num"}, "at": {"$ref": "#/$defs/vec3"},
                      "mode": {"const": "cut"}, "part": {}, "when": {}, "repeat": {}, "id": {}, "note": {}},
       "additionalProperties": false}
    ]},
    "print": {"type": "object", "additionalProperties": false, "required": ["key", "name", "rotation"],
              "properties": {"key": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,20}$"},
                             "name": {"$ref": "#/$defs/text"},
                             "rotation": {"enum": ["upright", "inverted", "front_down", "back_down",
                                                  "left_down", "right_down"]}}},
    "anchor": {"type": "object", "additionalProperties": false, "required": ["origin", "normal", "up"],
               "properties": {
                 "origin": {"$ref": "#/$defs/vec3"},
                 "normal": {"$ref": "#/$defs/axisName"}, "up": {"$ref": "#/$defs/axisName"},
                 "part": {"type": "string", "default": "body"},
                 "side": {"$ref": "#/$defs/side"},
                 "wall": {"$ref": "#/$defs/num"},
                 "door": {"type": "object", "additionalProperties": false, "required": ["when", "width", "profile"],
                          "properties": {"when": {"$ref": "#/$defs/expr"}, "width": {"$ref": "#/$defs/num"},
                                         "profile": {"$ref": "#/$defs/expr"}}},
                 "mount": {"$ref": "#/$defs/vec3"},
                 "openable": {"type": "boolean", "default": false},
                 "fields": {"type": "object", "additionalProperties": false,
                            "properties": {"width": {"type": "string"}, "height": {"type": "string"},
                                           "wall": {"type": "string"}, "port": {"type": "string"},
                                           "profile": {"type": "string"}}}}},
    "open": {"type": "object", "additionalProperties": false, "required": ["anchor", "set"],
             "properties": {"anchor": {"type": "string"}, "when": {"$ref": "#/$defs/expr"},
                            "set": {"type": "object", "minProperties": 1, "additionalProperties": {"$ref": "#/$defs/num"}}}},
    "features": {"type": "object", "additionalProperties": false,
                 "properties": {
                   "min_wall": {"$ref": "#/$defs/num"},
                   "access_sides": {"type": "array", "maxItems": 4,
                                    "items": {"type": "object", "additionalProperties": false, "required": ["side"],
                                              "properties": {"side": {"$ref": "#/$defs/side"},
                                                             "when": {"$ref": "#/$defs/expr"}}}},
                   "climb_height": {"$ref": "#/$defs/num"}, "slope_deg": {"$ref": "#/$defs/num"},
                   "step_height": {"$ref": "#/$defs/num"},
                   "openings": {"type": "array", "maxItems": 8, "items": {"oneOf": [
                     {"type": "object", "additionalProperties": false, "required": ["kind", "step", "label"],
                      "properties": {"kind": {"enum": ["vent", "window"]}, "step": {"type": "string"},
                                     "axis": {"enum": ["x", "y", "z"]}, "label": {"$ref": "#/$defs/text"},
                                     "when": {"$ref": "#/$defs/expr"}}},
                     {"type": "object", "additionalProperties": false, "required": ["kind", "size", "label", "probe"],
                      "properties": {"kind": {"const": "passage"}, "size": {"$ref": "#/$defs/num"},
                                     "rule_key": {"enum": ["entrance_min_diameter_mm", "tunnel_min_inner_diameter_mm"]},
                                     "label": {"$ref": "#/$defs/text"}, "when": {"$ref": "#/$defs/expr"},
                                     "probe": {"type": "object", "additionalProperties": false,
                                               "required": ["shape", "axis", "at", "length"],
                                               "properties": {"shape": {"enum": ["round_arch", "pointed_arch", "box", "house"]},
                                                              "axis": {"enum": ["x", "y"]}, "at": {"$ref": "#/$defs/vec3"},
                                                              "length": {"$ref": "#/$defs/num"}}}}}
                   ]}}}}
  }
}
"""


@lru_cache(maxsize=1)
def _schema() -> dict:
    return json.loads(_SCHEMA_JSON)


def json_schema() -> dict:
    """Part DSL v1 의 JSON Schema (draft 2020-12). 사본을 돌려준다."""
    return copy.deepcopy(_schema())
