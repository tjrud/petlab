"""닉네임 정규화·비교.

보기에는 같은데 코드값이 다른 닉네임(전각 문자, 결합형 한글, 보이지 않는 문자, 다른 문자 체계의 비슷한 글자)으로
운영자나 다른 회원을 사칭하지 못하게 한다.
- 입력은 NFKC 로 정규화하고, 한글·영문·숫자·공백·`_ - .` 만 허용한다.
- 유일성은 nickname_key(대소문자·공백·구분 기호 무시)로 확인한다 (DB 의 users.nickname_key UNIQUE).
- 예약어 확인은 nickname_key 에 숫자·기호 닮은꼴(0→o, 1→l 등)까지 접어서 한다.
"""

from __future__ import annotations

import re
import unicodedata

# 한글 채움 문자(보이지 않음)는 허용 범위(ㄱ-ㆎ) 안에 있으므로 따로 막는다
_FILLERS = {"ㅤ", "ᅟ", "ᅠ", "ﾠ"}
_ALLOWED = re.compile(r"[가-힣ㄱ-ㆎA-Za-z0-9 _.\-]*")
_SPACES = re.compile(r"[^\S\n\r\t\v\f]+")  # 줄바꿈·탭을 뺀 공백 (전각·NBSP 등은 NFKC 가 일반 공백으로 바꾼다)
_KEY_DROP = re.compile(r"[\s_.\-]+")
_LOOKALIKE = str.maketrans({"0": "o", "1": "l", "i": "l", "|": "l", "3": "e", "4": "a", "5": "s", "7": "t"})


_COMPAT_JAMO = re.compile(r"([ㄱ-ㆎ]+)")


def _nfkc_keep_jamo(v: str) -> str:
    """NFKC 로 정규화하되 한글 낱자(ㄱ-ㆎ, 예: ㅋㅋ)는 그대로 둔다.
    NFKC 는 낱자를 조합용 자모(U+1100 대)로 바꿔 화면에 이상하게 보이게 하기 때문이다.
    (낱자는 앞뒤 글자와 합쳐지지 않으므로 나머지 부분만 정규화해도 결과가 같다. 비교 키는 전체 NFKC 를 쓴다)"""
    return "".join(seg if _COMPAT_JAMO.fullmatch(seg) else unicodedata.normalize("NFKC", seg)
                   for seg in _COMPAT_JAMO.split(v))


def normalize_nickname(v: object) -> object:
    """pydantic BeforeValidator: 정규화한 닉네임을 돌려주고, 허용하지 않는 문자가 있으면 ValueError."""
    if not isinstance(v, str):
        return v
    v = _nfkc_keep_jamo(v).strip()
    if any(c in "\n\r\t\v\f" for c in v):
        raise ValueError("한 줄로 입력해 주세요")
    v = _SPACES.sub(" ", v)
    if any(c in _FILLERS for c in v) or not _ALLOWED.fullmatch(v):
        raise ValueError("닉네임은 한글·영문·숫자·공백과 _ - . 만 쓸 수 있어요")
    return v


def nickname_key(nickname: str) -> str:
    """유일성 비교용 키: 대소문자, 공백·밑줄·하이픈·마침표를 무시한다."""
    return _KEY_DROP.sub("", unicodedata.normalize("NFKC", nickname).casefold())[:40]


def lookalike_key(nickname: str) -> str:
    """예약어 확인용: nickname_key 에 숫자·기호 닮은꼴을 접는다 (NestF0rge → nestforge)."""
    return nickname_key(nickname).translate(_LOOKALIKE)


_GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def email_key(email: str) -> str:
    """이메일 비교용 키: 소문자, 주소 뒤 +태그 무시, Gmail 은 점(.) 무시.
    한 사람이 user+1@…, u.s.e.r@gmail.com 처럼 주소를 바꿔 가며 계정을 여러 개 인증하지 못하게 한다."""
    local, _, domain = unicodedata.normalize("NFKC", email).strip().casefold().rpartition("@")
    local = local.split("+", 1)[0]
    if domain in _GMAIL_DOMAINS:
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}"[:320]
