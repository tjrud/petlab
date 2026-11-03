"""사용량 상한(usage.reserve): 어떤 상한이 먼저 걸리는지와 IP 키가 없을 때의 동작을 고정한다."""

from __future__ import annotations

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.errors import QuotaExceededError
from app.models import UsageEvent, User
from app.services import usage
from app.services.usage import Cap


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'usage.db'}")
    init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def user(db):
    u = User(username="user1", nickname="닉네임", nickname_key="닉네임", role="member")
    db.add(u)
    db.commit()
    return u


def caps(limit: int = 1) -> dict[str, Cap]:
    return {
        "per_user": Cap(limit, "회원 상한", "user_cap"),
        "per_ip": Cap(limit, "IP 상한", "ip_cap"),
        "global_": Cap(limit, "전체 상한", "global_cap"),
    }


def test_first_cap_hit_decides_the_error(db, user):
    """회원별·IP 별·전체 상한에 모두 닿으면 회원별 상한의 문구가 나간다 (확인 순서: 회원 → IP → 전체)."""
    usage.reserve(db, "design", user, ip_key="ip1", **caps())
    with pytest.raises(QuotaExceededError) as e:
        usage.reserve(db, "design", user, ip_key="ip1", **caps())
    assert e.value.code == "user_cap"
    assert db.query(UsageEvent).count() == 1  # 걸리면 기록하지 않는다

    # 회원별 상한이 없으면 IP 별 상한이 먼저 걸린다
    c = caps()
    del c["per_user"]
    with pytest.raises(QuotaExceededError) as e:
        usage.reserve(db, "design", user, ip_key="ip1", **c)
    assert e.value.code == "ip_cap"


def test_empty_ip_key_skips_per_ip_cap(db, user):
    """IP 키가 없거나 빈 값이면 IP 별 상한은 건너뛴다 (다른 상한은 그대로)."""
    ip_cap = Cap(1, "IP 상한", "ip_cap")
    usage.reserve(db, "design", user, ip_key="", per_ip=ip_cap)
    usage.reserve(db, "design", user, ip_key="", per_ip=ip_cap)
    usage.reserve(db, "design", user, ip_key=None, per_ip=ip_cap)
    assert db.query(UsageEvent).count() == 3
