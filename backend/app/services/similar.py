"""Task 24: «Схожі канали» for the channel page.

Candidates: public listings only (approved, not in a bundle, seller not
blocked), same category, not the channel itself. Excluded: pricing verdict
"inflated" (Task 21). Ranking:
  1. "close" candidates first: subscribers within SUBS_FACTOR of the base and,
     when both sides have a fresh price-per-view, $/view within PPV_FACTOR;
  2. higher quality_score first (NULL = no data -> after scored ones);
  3. smaller log-distance in subscribers and $/view.
"""
from __future__ import annotations

import math

from sqlalchemy import select

from app.models.channel import Channel, ChannelStatus
from app.schemas.channel import ChannelResponse
from app.services.moderation import not_blocked_seller
from app.services.pricing import VERDICT_INFLATED, apply_estimate

SUBS_FACTOR = 3.0
PPV_FACTOR = 3.0
MAX_ITEMS = 6
CANDIDATE_LIMIT = 300


def _logdist(a, b) -> float | None:
    if not a or not b or a <= 0 or b <= 0:
        return None
    return abs(math.log(a / b))


def rank(base: dict, cands: list[dict], limit: int = MAX_ITEMS) -> list[dict]:
    """base/cands: dicts with id, subscribers_count, price_per_view, quality_score, price_verdict."""
    out = []
    for c in cands:
        if c["id"] == base["id"] or c.get("price_verdict") == VERDICT_INFLATED:
            continue
        ds = _logdist(c.get("subscribers_count"), base.get("subscribers_count"))
        dv = _logdist(c.get("price_per_view"), base.get("price_per_view"))
        close = ds is not None and ds <= math.log(SUBS_FACTOR) and (dv is None or dv <= math.log(PPV_FACTOR))
        dist = (ds if ds is not None else 5.0) + (dv if dv is not None else 0.5)
        q = c.get("quality_score")
        out.append(((0 if close else 1, 0 if q is not None else 1, -(q or 0), dist, -c["id"]), c))
    out.sort(key=lambda t: t[0])
    return [c for _, c in out[:limit]]


async def find_similar(db, base: Channel, market, limit: int = MAX_ITEMS) -> list[dict]:
    from app.models.bundle import BundleChannel
    bundled = select(BundleChannel.channel_id).scalar_subquery()
    rows = (await db.execute(
        select(Channel).where(
            Channel.status == ChannelStatus.approved,
            Channel.category == base.category,
            Channel.id != base.id,
            ~Channel.id.in_(bundled),
            not_blocked_seller(Channel.seller_id),
        ).order_by(Channel.quality_score.desc().nulls_last(), Channel.id.desc()).limit(CANDIDATE_LIMIT)
    )).scalars().all()
    b = apply_estimate(ChannelResponse.model_validate(base), market)
    resp = {c.id: apply_estimate(ChannelResponse.model_validate(c), market) for c in rows}
    as_dict = lambda r: {"id": r.id, "subscribers_count": r.subscribers_count, "price_per_view": r.price_per_view,
                         "quality_score": r.quality_score, "price_verdict": r.price_verdict}
    picked = rank(as_dict(b), [as_dict(r) for r in resp.values()], limit=limit)
    out = []
    for p in picked:
        r = resp[p["id"]]
        out.append({
            "id": r.id, "channel_name": r.channel_name, "avatar_url": r.avatar_url, "category": r.category,
            "subscribers_count": r.subscribers_count, "avg_views": r.avg_views, "price": r.price,
            "price_per_view": round(r.price_per_view, 4) if r.price_per_view is not None else None,
            "price_verdict": r.price_verdict, "quality_score": r.quality_score,
            "quality_health": r.quality_health, "listing_type": r.listing_type,
        })
    return out
