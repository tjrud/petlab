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


# 이름 뒤에 붙는 조사 (받침에 따라 고른 것과 받침을 모를 때 둘 다 적은 것). 긴 것부터 뗀다
_PARTICLES = ("이(가)", "을(를)", "은(는)", "와(과)", "과(와)", "으로", "이", "가", "을", "를", "은", "는", "과", "와", "로")

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
        """글 조각이 차례대로 다 들어 있으면 첫 글 조각의 위치 (없으면 None). 정규식보다 훨씬 싸게 걸러낸다.

        빈칸뿐인 글 조각("{0} {1} 대신 …" 의 첫 빈칸)은 위치로 치지 않는다: 바깥 문장("{0}: {1}")의 자리표시에 든
        빈칸에서도 맞아 바깥 틀보다 앞서기 때문이다 (빈칸뿐인 틀은 첫 빈칸 위치)."""
        if self.starts_with_literal and not s.startswith(self.parts[0]):
            return None
        if self.ends_with_literal and not s.endswith(self.parts[-1]):
            return None
        pos, first, solid = 0, None, None
        for lit in self.literals:
            if not lit:
                continue
            i = s.find(lit, pos)
            if i < 0:
                return None
            if first is None:
                first = i
            if solid is None and lit.strip():
                solid = i
            pos = i + len(lit)
        if solid is not None:
            return solid
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


# 자리표시가 품으면 그 틀을 뒤로 미루는 구분 말 (틀의 글 조각에 없을 때). " · " 는 조립 항목 보정 문구의 "부품 · 파라미터"
_SEPARATORS = (": ", ", ", " · ")


def _spans_separator(t: _Template, m: re.Match[str]) -> bool:
    """틀의 글 조각에 없는 구분 말(': '·', ')을 자리표시가 품는지. "{0}이(가) 달린 {1}" 의 {1} 이 "은신처 #1: 안내 …" 를
    잡거나, "{0} → {1} 왼쪽" 의 {1} 이 "A 오른쪽, B → C" 처럼 목록을 넘어 잡은 경우다. 이런 맞춤은 다른 틀과 목록 나누기보다
    뒤로 미룬다 (조립 항목 이름 틀이 안내 문구를 삼키지 않게, 연결 목록을 하나씩 바꾸게)."""
    lits = "".join(t.literals)
    seps = [sep for sep in _SEPARATORS if sep not in lits and sep.strip() not in lits]
    if not seps:
        return False
    return any(v is not None and any(sep in v for sep in seps) for v in m.groupdict().values())


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
        bare = self._without_particle(s, depth)
        if bare is not None:
            return bare
        if len(s) <= MAX_TEMPLATE_INPUT:
            cands = []
            for t in self.templates:
                a = t.anchor(s)
                if a is not None:
                    cands.append((a, -t.literal_len, t))
            cands.sort(key=lambda c: (c[0], c[1]))
            fallback: tuple[_Template, re.Match[str]] | None = None
            for _, _, t in cands:
                m = t.rx.fullmatch(s)
                if m is None:
                    continue
                if _spans_separator(t, m):
                    fallback = fallback or (t, m)
                    continue
                return self._best_split(t, s, self._fill(m, t.en, depth), depth)
            if fallback is not None:
                listed = self._split_list(s, depth)
                if listed is not None and not HANGUL.search(listed):
                    return listed
                t, m = fallback
                return self._best_split(t, s, self._fill(m, t.en, depth), depth)
        listed = self._split_list(s, depth)
        return listed if listed is not None else s

    def _split_list(self, s: str, depth: int) -> str | None:
        """"A, B" 처럼 이어 붙인 목록. 붙여 쓴 가운뎃점("그릇 받침·물병 거치대")은 영어에서 쉼표로. 바뀐 게 없으면 None."""
        first: str | None = None
        for sep, joiner in ((", ", ", "), (" · ", " · "), ("\n", "\n"), ("·", ", ")):
            if sep in s:
                parts = s.split(sep)
                if sep == "·" and any(not p or p != p.strip() for p in parts):
                    continue  # 낱말끼리 붙여 쓴 가운뎃점만 (" · " 를 잘못 끊은 조각이 아니게)
                out = [self._translate(p, depth + 1) for p in parts]
                if out != parts:
                    joined = joiner.join(out)
                    if not HANGUL.search(joined):
                        return joined  # 다 바뀐 나누기를 먼저 ("집 · 외형 높이(Z), 지붕 포함" 은 " · " 로)
                    first = first or joined
        return first

    def _without_particle(self, s: str, depth: int) -> str | None:
        """조사를 붙여 문장에 넣은 이름("그릇 받침을", "터널과", "은신처 2이(가)"): 조사를 뗀 이름이 영어로 다 바뀌면
        그 영어 (영어 문장 틀에는 조사 자리가 없다). 다 바뀌지 않으면 None (한국어 문구를 자르지 않는다)."""
        for suffix in _PARTICLES:
            if len(s) > len(suffix) and s.endswith(suffix):
                stem = s[: -len(suffix)]
                out = self._translate(stem, depth + 1)
                if out != stem and not HANGUL.search(out):
                    return out
        return None

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
        if _should(key):
            # "…_ko" 열쇠 아래의 사전(파라미터 이름 등)은 값을 바꾼다 (안쪽 열쇠는 이름이라 그대로)
            return {k: cat.translate(v) if isinstance(v, str) else translate_json(v, cat, k) for k, v in data.items()}
        return {k: translate_json(v, cat, k) for k, v in data.items()}
    if isinstance(data, list):
        return [translate_json(v, cat, key) for v in data]
    if isinstance(data, str):
        if _should(key) or data in _SYSTEM_VALUES:
            return cat.translate(data)
    return data
