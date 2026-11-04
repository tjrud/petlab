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
_KIND_IDS = {"design": 1, "post": 2, "comment": 3, "habitat": 4, "waitlist": 5, "email": 6, "email_change": 7,
             "email_fail": 8}
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
            cooldown: tuple[timedelta, Cap] | None = None) -> int:
    """상한을 확인하고 사용 1회를 기록한 뒤 커밋한다 (기록 id 를 돌려준다). 상한에 닿았으면 QuotaExceededError (기록하지 않음).

    앞서 열린 읽기 트랜잭션은 먼저 끝낸다. 잠금은 확인·기록 사이에만 잡으므로 짧다."""
    db.commit()
    try:
        with _serialized(db, kind):
            # 처음 걸린 상한이 오류 문구를 정하므로 순서가 중요하다: cooldown → 회원별 → IP 별 → 서비스 전체
            checks: list[tuple[Cap, dict]] = []
            if cooldown:
                # cooldown: 같은 회원이 짧은 시간(window) 안에 limit 번 넘게 하지 못하게 (예: 메일 60초에 1통)
                window, cap = cooldown
                checks.append((cap, {"user_id": user.id, "window": window}))
            if per_user is not None:
                checks.append((per_user, {"user_id": user.id}))
            if per_ip is not None and ip_key:  # IP 키가 없으면(헤더 미설정 등) IP 별 상한은 건너뛴다
                checks.append((per_ip, {"ip_key": ip_key}))
            if global_ is not None:
                checks.append((global_, {}))
            for cap, where in checks:
                if count(db, kind, **where) >= cap.limit:
                    raise QuotaExceededError(cap.message_ko, code=cap.code)
            event = UsageEvent(user_id=user.id, kind=kind, ip_key=ip_key)
            db.add(event)
            db.commit()
            return event.id
    except BaseException:
        db.rollback()
        raise


def reserve_per_member(db: Session, kind: str, user: User, limit: int, message_ko: str, code: str) -> None:
    """회원별 24시간 상한 하나만 확인하고 기록한다 (reserve 와 같이 커밋한다).
    관리자는 세지도 기록하지도 않는다: 커밋도 하지 않으므로 열린 읽기 트랜잭션은 그대로다."""
    if not user.is_admin:
        reserve(db, kind, user, per_user=Cap(limit, message_ko, code))
