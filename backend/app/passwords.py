"""회원 비밀번호 해시 (표준 라이브러리 scrypt).

형식: scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

N, R, P, DKLEN = 2**14, 8, 1, 32
_MAXMEM = 64 * 1024 * 1024


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DKLEN, maxmem=_MAXMEM)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


# 없는 아이디로 로그인할 때도 같은 시간이 걸리도록 비교에 쓰는 더미 해시
_DUMMY = hash_password("dummy-password-for-timing")


def verify_password(password: str, stored: str | None) -> bool:
    """저장된 해시와 비교. stored 가 없으면(없는 회원 등) 더미 해시로 같은 시간을 쓰고 False."""
    target = stored or _DUMMY
    try:
        scheme, n, r, p, salt_b64, hash_b64 = target.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(hash_b64)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p),
                                dklen=len(expected), maxmem=_MAXMEM)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected) and stored is not None
