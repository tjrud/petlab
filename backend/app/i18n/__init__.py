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


# 이보다 긴 문구는 틀에 맞춰 보지 않는다 (LLM 이 쓴 설명 같은 자유 글: 틀에 맞을 일이 없고, 길면 정규식이 느리다)
MAX_TEMPLATE_INPUT = 600


class _Template:
    __slots__ = ("parts", "literals", "en", "rx", "literal_len", "starts_with_literal", "ends_with_literal")

    def __init__(self, ko: str, en: str):
        self.parts = _PLACEHOLDER.split(ko)  # [글, 번호, 글, 번호, …, 글]
        self.literals = [p for i, p in enumerate(self.parts) if i % 2 == 0]
        self.en = en
        self.rx = _compile(self.parts, ())
        self.literal_len = sum(len(p) for p in self.literals)
        self.starts_with_literal = bool(self.parts[0])
        self.ends_with_literal = bool(self.parts[-1])

    def anchor(self, s: str) -> int | None:
        """글 조각이 차례대로 다 들어 있으면 첫 글 조각의 위치 (없으면 None). 정규식보다 훨씬 싸게 걸러낸다."""
        if self.starts_with_literal and not s.startswith(self.parts[0]):
            return None
        if self.ends_with_literal and not s.endswith(self.parts[-1]):
            return None
        pos, first = 0, None
        for lit in self.literals:
            if not lit:
                continue
            i = s.find(lit, pos)
            if i < 0:
                return None
            if first is None:
                first = i
            pos = i + len(lit)
        return first if first is not None else 0


def _compile(parts: list[str], greedy: tuple[int, ...]) -> re.Pattern[str]:
    """자리표시는 기본으로 가장 짧게 잡는다. greedy 에 든 순번의 자리표시는 가장 길게."""
    pattern, n = "", 0
    for i, part in enumerate(parts):
        if i % 2 == 0:
            pattern += re.escape(part)
        else:
            n += 1
            pattern += f"(?P<p{part}_{n}>.+{'' if n in greedy else '?'})"
    return re.compile(pattern, re.DOTALL)


class Catalog:
    """한국어 원문(자리표시 포함) → 영어. 자리표시가 없는 문구는 사전으로, 있는 문구는 틀(정규식)로 찾는다.

    여러 틀이 맞으면 바깥 문장 틀을 고른다: 첫 글 조각이 가장 앞에 나오는 틀(자리표시가 다른 문장을 품는 경우
    "{0}: {1} … 보정했습니다. {4}" 처럼 바깥 틀의 글이 먼저 나온다), 같으면 글 조각이 긴 틀."""

    def __init__(self, entries: dict[str, str]):
        self.exact: dict[str, str] = {}
        self.templates: list[_Template] = []
        for ko, en in entries.items():
            if _PLACEHOLDER.search(ko):
                self.templates.append(_Template(ko, en))
            else:
                self.exact[ko] = en
        self._cache: dict[str, str] = {}

    def translate(self, s: str) -> str:
        hit = self._cache.get(s)
        if hit is None:
            hit = self._translate(s, 0)
            if len(self._cache) > 20_000:
                self._cache.clear()
            self._cache[s] = hit
        return hit

    def _fill(self, m: re.Match[str], en: str, depth: int) -> str:
        values: dict[str, str] = {}
        for name, val in m.groupdict().items():
            idx = name[1:].split("_")[0]
            values.setdefault(idx, self._translate(val, depth + 1))
        return _PLACEHOLDER.sub(lambda mm: values.get(mm.group(1), mm.group(0)), en)

    def _translate(self, s: str, depth: int) -> str:
        if not s or not HANGUL.search(s) or depth > 4:
            return s
        hit = self.exact.get(s)
        if hit is not None:
            return hit
        stripped = s.strip()
        if stripped != s and stripped in self.exact:
            return s.replace(stripped, self.exact[stripped])
        if len(s) <= MAX_TEMPLATE_INPUT:
            cands = []
            for t in self.templates:
                a = t.anchor(s)
                if a is not None:
                    cands.append((a, -t.literal_len, t))
            cands.sort(key=lambda c: (c[0], c[1]))
            for _, _, t in cands:
                m = t.rx.fullmatch(s)
                if m is None:
                    continue
                return self._best_split(t, s, self._fill(m, t.en, depth), depth)
        # "A, B" 처럼 이어 붙인 목록
        for sep in (", ", " · ", "\n"):
            if sep in s:
                parts = s.split(sep)
                out = [self._translate(p, depth + 1) for p in parts]
                if out != parts:
                    return sep.join(out)
        return s

    def _best_split(self, t: _Template, s: str, best: str, depth: int) -> str:
        """자리표시 둘이 빈칸 하나로만 나뉘면("{1} {2}") 어디서 끊을지 모호하다: 한국어가 남으면 다른 끊기도 해 본다."""
        n = (len(t.parts) - 1) // 2
        if not HANGUL.search(best) or not 1 < n <= 6:
            return best
        for mask in range(1, 2 ** n):
            greedy = tuple(i + 1 for i in range(n) if mask >> i & 1)
            alt = _compile(t.parts, greedy).fullmatch(s)
            if alt is None:
                continue
            cand = self._fill(alt, t.en, depth)
            if len(HANGUL.findall(cand)) < len(HANGUL.findall(best)):
                best = cand
                if not HANGUL.search(best):
                    break
        return best


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
