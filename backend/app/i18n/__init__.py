"""언어 (한국어·영어).

요청마다 언어를 정하고(헤더 X-Lang, 없으면 쿠키 lang), 영어면 응답 JSON 의 한국어 문구를 영어로 바꾼다.
문구는 코드·규칙 파일·DB(검증 보고서)에 한국어로 있으므로, 응답을 보낼 때 카탈로그(app/i18n/en/*.json)에서
찾아 바꾼다. 카탈로그 열쇠는 한국어 원문이고, 바뀌는 값은 {0}, {1} … 자리표시로 둔다
(예: "{0}: 높이 {1}mm 가 케이지 내부 높이 {2}mm 보다 높습니다." → "{0}: height {1} mm exceeds …").
자리에 들어간 값에 한국어가 있으면(구조물 이름 등) 그 값도 카탈로그로 바꾼다.

카탈로그에 없는 문구는 한국어 그대로 둔다 (LLM 이 쓴 설명·회원이 쓴 글처럼 원래 언어로 남는 것도 있다).
"""

from __future__ import annotations

import contextvars
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

Lang = Literal["ko", "en"]
LANGS: tuple[Lang, ...] = ("ko", "en")
DEFAULT_LANG: Lang = "ko"
LANG_HEADER = "x-lang"
LANG_COOKIE = "lang"

_current: contextvars.ContextVar[Lang] = contextvars.ContextVar("lang", default=DEFAULT_LANG)

HANGUL = re.compile(r"[가-힣]")
_PLACEHOLDER = re.compile(r"\{(\d+)\}")


def get_lang() -> Lang:
    return _current.get()


def set_lang(lang: Lang) -> contextvars.Token:
    return _current.set(lang)


def reset_lang(token: contextvars.Token) -> None:
    _current.reset(token)


def parse_lang(header: str | None, cookie: str | None) -> Lang:
    for v in (header, cookie):
        if v:
            v = v.strip().lower()[:2]
            if v in LANGS:
                return v  # type: ignore[return-value]
    return DEFAULT_LANG


class Catalog:
    """한국어 원문(자리표시 포함) → 영어. 자리표시가 없는 문구는 사전으로, 있는 문구는 정규식으로 찾는다."""

    def __init__(self, entries: dict[str, str]):
        self.exact: dict[str, str] = {}
        # 첫 글자가 같은 것끼리 묶어 맞춰 볼 후보를 줄인다 (첫 조각이 자리표시면 "" 묶음)
        self.templates: dict[str, list[tuple[re.Pattern[str], str]]] = {}
        for ko, en in entries.items():
            if not _PLACEHOLDER.search(ko):
                self.exact[ko] = en
                continue
            parts = _PLACEHOLDER.split(ko)  # [글, 번호, 글, 번호, …, 글]
            pattern, order = "", []
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    pattern += re.escape(part)
                else:
                    order.append(int(part))
                    pattern += f"(?P<p{part}_{len(order)}>.+?)"
            rx = re.compile(pattern, re.DOTALL)
            head = parts[0][:1]
            self.templates.setdefault(head, []).append((rx, en))
        # 글자가 긴(구체적인) 틀부터 맞춘다
        for k in self.templates:
            self.templates[k].sort(key=lambda t: -len(_PLACEHOLDER.sub("", t[0].pattern)))

    def translate(self, s: str, depth: int = 0) -> str:
        if not s or not HANGUL.search(s) or depth > 4:
            return s
        hit = self.exact.get(s)
        if hit is not None:
            return hit
        stripped = s.strip()
        if stripped != s and stripped in self.exact:
            return s.replace(stripped, self.exact[stripped])
        for head in (s[:1], ""):
            for rx, en in self.templates.get(head, ()):
                m = rx.fullmatch(s)
                if m is None:
                    continue
                values: dict[str, str] = {}
                for name, val in m.groupdict().items():
                    idx = name[1:].split("_")[0]
                    values.setdefault(idx, self.translate(val, depth + 1))
                return _PLACEHOLDER.sub(lambda mm: values.get(mm.group(1), mm.group(0)), en)
        # "A, B" 처럼 이어 붙인 목록
        for sep in (", ", " · ", "\n"):
            if sep in s:
                parts = s.split(sep)
                out = [self.translate(p, depth + 1) for p in parts]
                if out != parts:
                    return sep.join(out)
        return s


_CATALOG_DIR = Path(__file__).parent / "en"


@lru_cache(maxsize=1)
def catalog() -> Catalog:
    entries: dict[str, str] = {}
    for f in sorted(_CATALOG_DIR.glob("*.json")):
        entries.update(json.loads(f.read_text(encoding="utf-8")))
    return Catalog(entries)


def tr(s: str) -> str:
    """지금 요청 언어로 바꾼다 (한국어면 그대로)."""
    if get_lang() == "ko":
        return s
    return catalog().translate(s)


# ── 응답 JSON 바꾸기 ──

# 이 열쇠의 값만 바꾼다: 서버가 만든 문구. 회원이 쓴 글·제목·닉네임·파일 이름 등은 그대로 둔다
_KEY_SUFFIX = "_ko"
_KEYS = {"display_name", "item_labels"}
# 다른 열쇠라도 이 값이면 서버가 넣은 기본값이라 바꾼다 (예: 제목이 없는 설계)
_SYSTEM_VALUES = {"맞춤 설계"}


def _should(key: str | None) -> bool:
    return key is not None and (key.endswith(_KEY_SUFFIX) or key in _KEYS)


def translate_json(data: object, cat: Catalog | None = None, key: str | None = None) -> object:
    cat = cat or catalog()
    if isinstance(data, dict):
        return {k: translate_json(v, cat, k) for k, v in data.items()}
    if isinstance(data, list):
        return [translate_json(v, cat, key) for v in data]
    if isinstance(data, str):
        if _should(key) or data in _SYSTEM_VALUES:
            return cat.translate(data)
    return data
