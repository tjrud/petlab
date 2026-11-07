"""ID 로 행 찾기: ID 형식이 틀렸거나, 없거나, 남의 것이면 모두 같은 404 (다른 사람 것이 있는지 알리지 않게)."""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.schemas import ID_RE

M = TypeVar("M")


def get_or_404(db: Session, model: type[M], obj_id: str, message_ko: str, *, owner_id: str | None = None,
               code: str | None = None) -> M:
    """owner_id 를 주면 그 회원의 것만 찾는다 (모델에 owner_id 열이 있어야 한다)."""
    obj = db.get(model, obj_id) if ID_RE.fullmatch(obj_id) else None
    if obj is None or (owner_id is not None and obj.owner_id != owner_id):  # type: ignore[attr-defined]
        raise NotFoundError(message_ko, code=code)
    return obj
