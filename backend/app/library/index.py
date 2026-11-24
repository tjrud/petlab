"""부품 라이브러리 색인 (app/library/index.json) 과 게시된 부품 파일 읽기 (설계 §9.1, §9.2).

index.json 은 라이브러리에서 유일하게 바뀌는 파일이다. 게시된 부품 파일(parts/<key>.json)은 바꾸거나 지우지 않고,
색인이 그 sha256 을 적어 둔다 (R3). 파일이 색인과 다르면 읽을 때 LibraryError 를 낸다 (R8: 기동·테스트가 멈춘다).

가벼운 모듈이다: json·hashlib·pydantic 만 쓰고 형상 커널(build123d·OCP·trimesh)이나 anthropic 을 불러오지 않는다
(표시 메타데이터·게이팅·지문 계산·관리자 API 가 이 모듈만 쓴다, R9).

시험에서는 LIBRARY_DIR 을 바꿔(monkeypatch) 다른 라이브러리 폴더를 읽게 할 수 있다. 캐시는 폴더 경로별로 따로 둔다.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

LIBRARY_DIR: Path = Path(__file__).resolve().parent
INDEX_FILE = "index.json"
PARTS_DIR = "parts"
REPORTS_DIR = "reports"
INDEX_VERSION = 1
# 라이브러리 부품의 기본 색 (Template.color 가 없을 때 프론트엔드가 쓰는 색과 같다)
DEFAULT_COLOR = "#c8a27a"
KEY_RE = re.compile(r"^(?P<family>[a-z][a-z0-9_]{2,40})@v(?P<version>[1-9][0-9]{0,2})$")

Status = Literal["active", "retired", "blocked"]
STATUSES: tuple[str, ...] = ("active", "retired", "blocked")


class LibraryError(RuntimeError):
    """라이브러리 파일이 색인과 맞지 않거나 읽을 수 없다 (fail fast)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ReasonText(_Strict):
    ko: Annotated[str, Field(min_length=1)]
    en: Annotated[str, Field(min_length=1)]


class Golden(_Strict):
    params: dict[str, Any] = {}
    files: dict[str, str] = {}


class IndexEntry(_Strict):
    """색인 항목 하나 (부품 key 별)."""

    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    status: Status
    published_at: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    family: str
    version: Annotated[int, Field(ge=1, le=999)]
    role: Literal["host", "room_host", "accessory", "none"]
    habitats: Annotated[list[str], Field(min_length=1)]
    verified_for: dict[str, list[str]] = {}
    rule_fields_used: list[str] = []
    rules_digest: dict[str, str] = {}
    golden: dict[str, Golden] = {}
    superseded_by: str | None = None
    reason: ReasonText | None = None
    request_ids: list[str] = []

    @property
    def key(self) -> str:
        return f"{self.family}@v{self.version}"


class IndexFile(_Strict):
    v: Literal[1]
    parts: dict[str, IndexEntry]

    @model_validator(mode="after")
    def _keys_match(self) -> IndexFile:
        for key, e in self.parts.items():
            if not KEY_RE.match(key):
                raise ValueError(f"index key {key!r} is not <family>@v<N>")
            if key != e.key:
                raise ValueError(f"index key {key!r} does not match family@v<version> = {e.key!r}")
        return self


def parse_key(key: str) -> tuple[str, int] | None:
    """'tunnel_junction@v1' → ('tunnel_junction', 1). 라이브러리 키 꼴이 아니면 None."""
    m = KEY_RE.match(key)
    if m is None:
        return None
    return m.group("family"), int(m.group("version"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump_index(index: IndexFile | dict) -> str:
    """index.json 의 정규 문자열 (항목은 key 순, 들여쓰기 2, 끝에 줄바꿈). 게시·폐기 도구가 쓴다."""
    data = index.model_dump(mode="json") if isinstance(index, IndexFile) else index
    data = {"v": data["v"], "parts": {k: data["parts"][k] for k in sorted(data["parts"])}}
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# ── 읽기 (폴더별 캐시) ──

class _Library:
    def __init__(self, root: Path):
        self.root = root
        path = root / INDEX_FILE
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raise LibraryError(f"library index missing: {path}") from None
        try:
            self.index = IndexFile.model_validate(json.loads(raw))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise LibraryError(f"{path}: invalid JSON: {e}") from None
        except ValidationError as e:
            raise LibraryError(f"{path}: invalid index: {e}") from None
        # 항목을 key 순으로
        self.entries: dict[str, IndexEntry] = {k: self.index.parts[k] for k in sorted(self.index.parts)}
        self._bytes: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def part_path(self, key: str) -> Path:
        return self.root / PARTS_DIR / f"{key}.json"

    def part_bytes(self, key: str) -> bytes:
        """색인의 sha256 과 맞는지 확인한 부품 파일 바이트."""
        with self._lock:
            cached = self._bytes.get(key)
        if cached is not None:
            return cached
        e = self.entries.get(key)
        if e is None:
            raise LibraryError(f"{key!r} is not in the library index")
        path = self.part_path(key)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            raise LibraryError(f"{key}: part file missing: {path}") from None
        digest = sha256_bytes(data)
        if digest != e.sha256:
            raise LibraryError(f"{key}: part file sha256 {digest} does not match the index ({e.sha256}); "
                               "published files are never edited (publish a new version instead)")
        with self._lock:
            self._bytes[key] = data
        return data


@lru_cache(maxsize=8)
def _load(root: str) -> _Library:
    return _Library(Path(root))


def _lib() -> _Library:
    return _load(str(LIBRARY_DIR))


def clear_cache() -> None:
    """색인·부품 파일 캐시를 비운다 (게시 도구가 index.json 을 바꾼 뒤, 시험)."""
    _load.cache_clear()


def library_dir() -> Path:
    return Path(LIBRARY_DIR)


# ── 공개 API ──

def entries() -> dict[str, IndexEntry]:
    """key → 색인 항목 (key 순). 상태(active·retired·blocked)와 상관없이 모두."""
    return dict(_lib().entries)


def entry(key: str) -> IndexEntry | None:
    return _lib().entries.get(key)


def keys() -> tuple[str, ...]:
    return tuple(_lib().entries)


def is_library_key(key: str) -> bool:
    return key in _lib().entries


def status(key: str) -> str | None:
    e = entry(key)
    return e.status if e is not None else None


def part_path(key: str) -> Path:
    return _lib().part_path(key)


def read_part(key: str) -> dict:
    """게시된 부품 파일(JSON dict, 새 사본). 파일이 없거나 sha256 이 색인과 다르면 LibraryError."""
    data = _lib().part_bytes(key)
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LibraryError(f"{key}: invalid JSON: {e}") from None


def hidden_keys() -> frozenset[str]:
    """새 설계에 내놓지 않는 부품 (폐기 retired ∪차단 blocked). 등록·allowed_templates 에는 남는다 (R7)."""
    return frozenset(k for k, e in _lib().entries.items() if e.status != "active")


def blocked_keys() -> frozenset[str]:
    """안전 문제로 내려받기를 막은 부품."""
    return frozenset(k for k, e in _lib().entries.items() if e.status == "blocked")


def active_keys() -> tuple[str, ...]:
    return tuple(k for k, e in _lib().entries.items() if e.status == "active")


def desc_head(text: str) -> str:
    """파라미터 설명의 첫 문장에서 단위를 뺀 것 (app.validation.autofix._desc 와 같은 규칙: 보정 문구의 파라미터 이름)."""
    return text.split(".")[0].replace(" mm", "")


def _unit(field: str) -> str | None:
    if field.endswith("_mm"):
        return "mm"
    if field.endswith("_deg"):
        return "deg"
    return None


def display_meta() -> dict[str, dict]:
    """key → 프론트엔드 표시 정보 {name_ko, color, status, params: {필드: {label_ko, unit}},
    choices: {필드: {값: {label_ko}}}}. 저장된 설계를 보여 줘야 하므로 폐기·차단 부품도 넣는다."""
    out: dict[str, dict] = {}
    for key, e in _lib().entries.items():
        part = read_part(key)
        params: dict[str, dict] = {}
        choices: dict[str, dict] = {}
        for name, spec in (part.get("params") or {}).items():
            params[name] = {"label_ko": desc_head(spec["desc"]["ko"]), "unit": _unit(name)}
            labels = spec.get("choice_labels") or {}
            if spec.get("type") == "choice" and labels:
                choices[name] = {v: {"label_ko": labels[v]["ko"]} for v in spec.get("choices", []) if v in labels}
        out[key] = {"name_ko": part["name"]["ko"], "color": part.get("color") or DEFAULT_COLOR, "status": e.status,
                    "params": params, "choices": choices}
    return out


def part_pairs(part: dict) -> list[tuple[str, str]]:
    """부품 파일 하나의 한국어 → 영어 문구 짝: 이름, 설명, 파라미터 설명 첫 문장(_desc), 선택지 이름, 제약 까닭,
    검사 메시지, 출력 파트 이름, 구멍 이름. 초안에도 쓸 수 있다 (S06·R02 검사)."""
    pairs: list[tuple[str, str]] = []

    def add(t: object) -> None:
        if isinstance(t, dict) and isinstance(t.get("ko"), str) and isinstance(t.get("en"), str):
            pairs.append((t["ko"], t["en"]))

    add(part.get("name"))
    add(part.get("description"))
    for spec in (part.get("params") or {}).values():
        d = spec.get("desc") or {}
        if isinstance(d.get("ko"), str) and isinstance(d.get("en"), str):
            pairs.append((desc_head(d["ko"]), desc_head(d["en"])))
        for label in (spec.get("choice_labels") or {}).values():
            add(label)
    for c in part.get("constraints") or []:
        add(c.get("reason"))
    for c in part.get("checks") or []:
        add(c.get("message"))
    for pp in part.get("print") or []:
        add(pp.get("name"))
    for o in (part.get("features") or {}).get("openings") or []:
        add(o.get("label"))
    return pairs


def i18n_pairs() -> dict[str, str]:
    """게시된 모든 부품(상태 무관)의 한국어 → 영어 문구 (app/i18n/en/library.json 의 내용). 폐기·차단 까닭도 넣는다.
    같은 한국어가 여러 번 나오면 key 순으로 처음 것을 쓴다 (서로 다른 영어는 R02 가 막는다). 한국어 순으로 정렬."""
    pairs: dict[str, str] = {}
    for key, e in _lib().entries.items():
        for ko, en in part_pairs(read_part(key)):
            pairs.setdefault(ko, en)
        if e.reason is not None:
            pairs.setdefault(e.reason.ko, e.reason.en)
    return {k: pairs[k] for k in sorted(pairs)}


def i18n_conflicts() -> list[tuple[str, str, str]]:
    """같은 한국어에 다른 영어를 단 경우 (한국어, 처음 영어, 다른 영어)."""
    seen: dict[str, str] = {}
    out: list[tuple[str, str, str]] = []
    for key in _lib().entries:
        for ko, en in part_pairs(read_part(key)):
            if ko in seen and seen[ko] != en:
                out.append((ko, seen[ko], en))
            seen.setdefault(ko, en)
    return out


def keywords() -> dict[str, dict[str, list[str]]]:
    """활성 부품의 key → {"ko": [...], "en": [...]} (모의 해석기의 낱말 찾기)."""
    out: dict[str, dict[str, list[str]]] = {}
    for key, e in _lib().entries.items():
        if e.status == "active":
            kw = read_part(key).get("keywords") or {}
            out[key] = {"ko": list(kw.get("ko") or []), "en": list(kw.get("en") or [])}
    return out


def part_ids() -> dict[str, str]:
    """key → 조립에서 쓰는 기본 부품 id (상태 무관)."""
    return {key: read_part(key)["part_id"] for key in _lib().entries}


def fulfills() -> dict[str, list[str]]:
    """활성 부품의 key → 이 부품이 채우는 부품 요청 이름(name_key) 목록 (관리자 화면의 fulfilled_by)."""
    return {key: list(read_part(key).get("fulfills") or []) for key, e in _lib().entries.items()
            if e.status == "active"}


def integrity_problems() -> list[str]:
    """색인과 부품 파일이 맞지 않는 곳 (sha 불일치, 파일 없음, 파일의 key 가 파일 이름과 다름, 색인에 없는 파일).
    예외를 내지 않고 목록으로 돌려준다 (audit·시험)."""
    try:
        lib = _lib()
    except LibraryError as e:
        return [str(e)]
    problems: list[str] = []
    for key, e in lib.entries.items():
        path = lib.part_path(key)
        if not path.is_file():
            problems.append(f"{key}: part file missing ({path.name})")
            continue
        data = path.read_bytes()
        if sha256_bytes(data) != e.sha256:
            problems.append(f"{key}: sha256 mismatch ({path.name} was edited)")
        try:
            obj = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            problems.append(f"{key}: invalid JSON")
            continue
        if not isinstance(obj, dict):
            problems.append(f"{key}: not a JSON object")
            continue
        if obj.get("key") != path.stem:
            problems.append(f"{key}: file key {obj.get('key')!r} does not match the file name {path.stem!r}")
        if obj.get("family") != e.family or obj.get("version") != e.version:
            problems.append(f"{key}: family/version in the file differ from the index")
    parts_dir = lib.root / PARTS_DIR
    if parts_dir.is_dir():
        for f in sorted(parts_dir.glob("*.json")):
            if f.stem not in lib.entries:
                problems.append(f"{f.name}: not in the index")
    return problems
