"""회원 비밀번호 해시 (표준 라이브러리 scrypt).

형식: scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading

# OWASP 권장 수준 중 메모리를 적게 쓰는 조합 (N=2^14·r=8 은 16 MiB, p=5 로 계산량을 늘린다).
# 예전 설정(p=1)으로 만든 해시는 로그인에 성공할 때 새 설정으로 다시 만든다 (needs_rehash)
N, R, P, DKLEN = 2**14, 8, 5, 32
_MAXMEM = 64 * 1024 * 1024
# scrypt 는 호출마다 16 MiB·백수십 ms 를 쓴다. 동시에 도는 개수를 묶어 로그인 요청이 몰려도
# 메모리·스레드 풀을 다 차지하지 못하게 한다 (나머지는 잠깐 기다린다).
_SLOTS = threading.BoundedSemaphore(max(2, min(8, os.cpu_count() or 2)))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    with _SLOTS:
        return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=_MAXMEM)


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = _scrypt(password, salt, N, R, P, DKLEN)
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
        digest = _scrypt(password, salt, int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected) and stored is not None


def needs_rehash(stored: str | None) -> bool:
    """지금 설정보다 약한 해시인지 (로그인에 성공했을 때 새로 만든다)"""
    if not stored:
        return False
    try:
        scheme, n, r, p, *_ = stored.split("$")
        return scheme != "scrypt" or (int(n), int(r), int(p)) != (N, R, P)
    except ValueError:
        return True
