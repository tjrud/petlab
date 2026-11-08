"""탐색 맞춤 추천.

회원마다 분류(은신처·터널·경사로·모래목욕통·케이지 전체·가상 케이지 배치·기타)별 관심도를 계산해 작품 점수에 더한다.
  - 내 설계에 들어 있는 구조물 (템플릿 → 분류)
  - 내 가상 케이지 배치안에 놓은 에셋 (에셋 키 → 분류), 배치안이 있으면 "가상 케이지 배치"
  - 등록한 반려동물 (있으면 "케이지 전체"·"가상 케이지 배치", 배치 예시의 종·크기가 같으면 더)
  - 탐색에서 본·내려받은·담아 온 작품의 분류 (최근 90일)
여기에 인기(내려받기 수)와 새로움(30일 기준 감쇠)을 더하고, 내 작품은 빼고, 이미 내려받은 작품은 낮춘다.
로그인하지 않았으면 인기와 새로움만 쓴다.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import CageLayout, Design, DesignVersion, MarketEvent, MarketItem, Pet, User
from app.schemas import MARKET_CATEGORIES

TEMPLATE_CATEGORY = {"hideout": "hideout", "tunnel": "tunnel", "ramp": "ramp", "sand_bath": "sand_bath"}
CATEGORY_NAME = MARKET_CATEGORIES
EVENT_WEIGHT = {"view": 1.0, "download": 3.0, "copy": 3.0}


def _iga(word: str) -> str:
    """받침에 맞춰 이/가"""
    code = ord(word[-1]) if word else 0
    return word + ("이" if 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 else "가")


def asset_category(key: str) -> str | None:
    """가상 케이지 에셋 키 → 탐색 분류"""
    if key.startswith("hideout_") or key == "toilet_corner":
        return "hideout"
    if key.startswith("tunnel"):
        return "tunnel"
    if key in ("ramp", "platform", "bridge", "stone_step"):
        return "ramp"
    if key == "sand_bath":
        return "sand_bath"
    return None


def _norm(c: Counter) -> dict[str, float]:
    top = max(c.values(), default=0)
    return {k: v / top for k, v in c.items()} if top else {}


def profile(db: Session, user: User) -> dict:
    """관심도 (출처별로 따로 둔다: 추천 까닭을 말하려고)"""
    designs = Counter()
    latest = (
        select(DesignVersion.items)
        .join(Design, Design.id == DesignVersion.design_id)
        .where(Design.owner_id == user.id)
        .order_by(DesignVersion.created_at.desc())
        .limit(50)
    )
    for items in db.scalars(latest):
        for it in items or []:
            cat = TEMPLATE_CATEGORY.get(it.get("template", ""))
            if cat:
                designs[cat] += 1

    layouts = Counter()
    for items in db.scalars(select(CageLayout.items).where(CageLayout.owner_id == user.id).limit(50)):
        layouts["layout"] += 1
        for it in items or []:
            cat = asset_category(it.get("asset", ""))
            if cat:
                layouts[cat] += 1

    pets = db.execute(select(Pet.species, Pet.size).where(Pet.owner_id == user.id)).all()

    events = Counter()
    since = datetime.now(timezone.utc) - timedelta(days=90)
    rows = db.execute(
        select(MarketEvent.kind, MarketItem.category, func.count())
        .join(MarketItem, MarketItem.id == MarketEvent.item_id)
        .where(MarketEvent.user_id == user.id, MarketEvent.created_at >= since)
        .group_by(MarketEvent.kind, MarketItem.category)
    ).all()
    for kind, cat, n in rows:
        events[cat] += EVENT_WEIGHT.get(kind, 0.0) * n
    downloaded = set(db.scalars(select(MarketEvent.item_id).where(MarketEvent.user_id == user.id,
                                                                  MarketEvent.kind.in_(("download", "copy")))))
    return {
        "designs": _norm(designs), "layouts": _norm(layouts), "events": _norm(events),
        "pet_sizes": {(sp, sz) for sp, sz in pets}, "has_pets": bool(pets), "downloaded": downloaded,
    }


def _age_days(item: MarketItem, now: datetime) -> float:
    created = item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - created).total_seconds() / 86400)


VIEWABLE_FORMATS = {"stl", "3mf"}


def _hands_on(item: MarketItem) -> float:
    """바로 써 볼 수 있는 작품에 주는 점수: 3D 로 미리 보고 가상 케이지에 놓아 볼 수 있으면(STL·3MF·배치) 크게,
    미리보기 이미지가 있으면 조금 (SKP 만 있는 작품은 내려받아 SketchUp 으로 열어야 보인다)"""
    viewable = bool(item.layout) or any(f.kind == "model" and f.format in VIEWABLE_FORMATS and f.dims_mm for f in item.files)
    has_image = any(f.kind == "image" for f in item.files)
    return (1.0 if viewable else 0.0) + (0.3 if has_image else 0.0)


def recommend(db: Session, user: User | None, limit: int = 12) -> list[tuple[MarketItem, str]]:
    items = db.scalars(
        select(MarketItem).options(selectinload(MarketItem.owner), selectinload(MarketItem.files))
        .order_by(MarketItem.created_at.desc()).limit(300)
    ).all()
    now = datetime.now(timezone.utc)
    prof = profile(db, user) if user else None
    scored: list[tuple[float, MarketItem, str]] = []
    mine: list[tuple[float, MarketItem, str]] = []
    for it in items:
        popular = 0.6 * math.log1p(it.download_count)
        fresh = math.exp(-_age_days(it, now) / 30)
        hands_on = _hands_on(it)
        score = popular + fresh + hands_on
        reason = "많이 내려받은 작품" if popular > fresh else "새로 올라온 작품"
        if hands_on >= 1.0 and hands_on > popular:
            reason = "3D로 보고 가상 케이지에 놓아 볼 수 있어요"
        if user and it.owner_id == user.id:
            # 내 작품은 다른 사람 작품으로 다 채우지 못할 때만 뒤에 붙인다
            mine.append((score, it, "내가 올린 작품"))
            continue
        if prof:
            parts = {
                "designs": 2.0 * prof["designs"].get(it.category, 0.0),
                "layouts": 1.6 * prof["layouts"].get(it.category, 0.0),
                "events": 1.4 * prof["events"].get(it.category, 0.0),
                "pets": 0.0,
            }
            if prof["has_pets"] and it.category in ("cage", "layout"):
                parts["pets"] += 0.6
            lay = it.layout or {}
            if lay and (lay.get("species"), lay.get("size")) in prof["pet_sizes"]:
                parts["pets"] += 1.2
            best = max(parts, key=parts.get)
            score += sum(parts.values())
            if parts[best] > 0.3:
                name = CATEGORY_NAME.get(it.category, it.category)
                reason = {
                    "designs": f"내 설계에 {name} 구조물이 있어요",
                    "layouts": "내 가상 케이지 배치와 비슷해요" if it.category == "layout" else f"내 배치안에 {_iga(name)} 있어요",
                    "events": f"자주 본 {name} 분류예요",
                    "pets": "내 반려동물과 같은 종·크기의 배치예요" if lay else "반려동물 케이지에 맞는 작품이에요",
                }[best]
            if it.id in prof["downloaded"]:
                score -= 1.5
        scored.append((score, it, reason))
    scored.sort(key=lambda t: (-t[0], t[1].id))
    mine.sort(key=lambda t: (-t[0], t[1].id))
    return [(it, reason) for _, it, reason in (scored + mine)[:limit]]
