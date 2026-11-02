"""사용량 상한: 확인과 기록을 한 트랜잭션에서 (동시에 몰린 요청이 상한을 넘지 못하게).

설계 요청은 LLM 호출 전에 1회를 '예약'(기록)한다. LLM 이 실패해도 비용은 들었으므로 되돌리지 않는다.
글·댓글은 지워도 기록이 남아, 지우고 다시 쓰는 방법으로 상한을 피할 수 없다.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.errors import QuotaExceededError
from app.models import UsageEvent, User

WINDOW = timedelta(hours=24)

# Postgres advisory lock 키 (db.init_db 의 727274 와 겹치지 않게). 종류별로 따로 직렬화한다.
_LOCK_NS = 727275
_KIND_IDS = {"design": 1, "post": 2, "comment": 3, "habitat": 4, "waitlist": 5, "email": 6}
_local_lock = threading.Lock()  # SQLite(로컬·테스트, 단일 프로세스)용


@dataclass(frozen=True)
class Cap:
    limit: int
    message_ko: str
    code: str


def count(db: Session, kind: str, *, user_id: str | None = None, ip_key: str | None = None,
          window: timedelta = WINDOW) -> int:
    start = datetime.now(timezone.utc) - window
    q = select(func.count(UsageEvent.id)).where(UsageEvent.kind == kind, UsageEvent.created_at >= start)
    if user_id is not None:
        q = q.where(UsageEvent.user_id == user_id)
    if ip_key is not None:
        q = q.where(UsageEvent.ip_key == ip_key)
    return db.scalar(q) or 0


@contextmanager
def _serialized(db: Session, kind: str) -> Iterator[None]:
    if db.get_bind().dialect.name == "postgresql":
        # 트랜잭션이 끝나면(커밋·롤백) 풀린다. 여러 인스턴스 사이에서도 직렬화된다
        db.execute(text("SELECT pg_advisory_xact_lock(:ns, :k)"), {"ns": _LOCK_NS, "k": _KIND_IDS[kind]})
        yield
    else:
        with _local_lock:
            yield


def reserve(db: Session, kind: str, user: User, *, per_user: Cap | None = None, per_ip: Cap | None = None,
            global_: Cap | None = None, ip_key: str | None = None,
            cooldown: tuple[timedelta, Cap] | None = None) -> None:
    """상한을 확인하고 사용 1회를 기록한 뒤 커밋한다. 상한에 닿았으면 QuotaExceededError (기록하지 않음).

    앞서 열린 읽기 트랜잭션은 먼저 끝낸다. 잠금은 확인·기록 사이에만 잡으므로 짧다."""
    db.commit()
    try:
        with _serialized(db, kind):
            checks = (
                # cooldown: 같은 회원이 짧은 시간(window) 안에 limit 번 넘게 하지 못하게 (예: 메일 60초에 1통)
                (cooldown[1] if cooldown else None, {"user_id": user.id, "window": cooldown[0]} if cooldown else None),
                (per_user, {"user_id": user.id}),
                (per_ip, {"ip_key": ip_key} if ip_key else None),
                (global_, {}),
            )
            for cap, where in checks:
                if cap is not None and where is not None and count(db, kind, **where) >= cap.limit:
                    raise QuotaExceededError(cap.message_ko, code=cap.code)
            db.add(UsageEvent(user_id=user.id, kind=kind, ip_key=ip_key))
            db.commit()
    except BaseException:
        db.rollback()
        raise
