"""Task 22: channel quality index (0-100) from honest, already collected data.

No Telethon calls here: inputs are the channel row (subscribers, avg_views,
views_hidden, last_post_date), ``channel_posts`` of the last 30 days and the
real subscriber snapshots in ``channel_stats`` (Task 20; retro points carry
subscribers = NULL and are ignored).

Components (max points):
  er          30  fresh views of posts in the last 30 days / subscribers
  regularity  25  active posting days in 30 days + evenness of gaps
  growth      20  subscriber growth over ~30 (or 7) days from real snapshots
  integrity   25  Task 21 "inflated" verdict (MAX_VIEW_RATIO 150%) and sharp
                  subscriber jumps between real snapshots

ER and regularity are required; growth / integrity may be missing and then
the score is rescaled over the components that are known. Not enough data
-> score None, health "insufficient" (UI: «мало даних»). Inflated -> score is
capped at INFLATED_CAP.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from statistics import mean, pstdev

from sqlalchemy import insert, select, update

from app.services.pricing import MAX_VIEW_RATIO, MIN_VIEW_RATIO, VERDICT_INFLATED
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

WINDOW_DAYS = 30
MIN_POSTS = 3
MIN_SUBS = 1
ER_FULL = 0.30          # views/subs >= 30% -> full ER points
GROWTH_FULL = 0.10      # +10%/month -> full growth points; -10% -> 0
JUMP_REL = 0.15         # >15% subscriber change per day between snapshots...
JUMP_ABS = 300          # ...and at least 300 subscribers -> sharp jump
JUMP_PENALTY = 15
INFLATED_CAP = 25
RECOMPUTE_HOURS = 6
WEIGHTS = {"er": 30, "regularity": 25, "growth": 20, "integrity": 25}

HEALTH_CLEAN = "clean"
HEALTH_SUSPICIOUS = "suspicious"
HEALTH_INSUFFICIENT = "insufficient"


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_channel(*, subscribers, is_closed=False, views_hidden=False,
                  posts: list[tuple[datetime, int]], snapshots: list[tuple[datetime, int]],
                  growth_30d=None, growth_7d=None, now: datetime | None = None,
                  price_verdict: str | None = None) -> dict:
    """posts: (date, views) of the last WINDOW_DAYS; snapshots: (day, subscribers) real only."""
    now = now or utcnow_naive()
    since = now - timedelta(days=WINDOW_DAYS)
    posts = [(d, v or 0) for d, v in posts if d is not None and d >= since]
    comps: dict[str, dict] = {}
    reasons: list[str] = []

    # ER (fresh views over 30 days)
    viewed = [v for _, v in posts if v > 0]
    ratio = None
    if is_closed or not subscribers or subscribers < MIN_SUBS:
        reasons.append("no_subscribers")
    elif views_hidden:
        reasons.append("views_hidden")
    elif len(viewed) < MIN_POSTS:
        reasons.append("few_posts_30d")
    else:
        ratio = mean(viewed) / subscribers
        if ratio > MAX_VIEW_RATIO:
            pts = 0.0
        else:
            pts = WEIGHTS["er"] * _clamp(ratio / ER_FULL)
        comps["er"] = {"points": round(pts, 1), "max": WEIGHTS["er"], "value": round(ratio * 100, 1),
                       "posts": len(viewed)}

    # Regularity
    if len(posts) >= MIN_POSTS:
        days = sorted({datetime(d.year, d.month, d.day) for d, _ in posts})
        freq = _clamp(len(days) / 15)
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        even = _clamp(1 - pstdev(gaps) / mean(gaps) / 2) if len(gaps) >= 2 and mean(gaps) > 0 else 0.5
        pts = WEIGHTS["regularity"] * (0.6 * freq + 0.4 * even)
        comps["regularity"] = {"points": round(pts, 1), "max": WEIGHTS["regularity"],
                               "active_days": len(days), "posts": len(posts)}
    elif "few_posts_30d" not in reasons:
        reasons.append("few_posts_30d")

    # Growth (real snapshots only)
    g, span = None, None
    if growth_30d is not None:
        g, span = growth_30d, 30
    elif growth_7d is not None:
        g, span = growth_7d, 7
    if g is not None and subscribers:
        base = max(subscribers - g, 1)
        monthly = (g / base) * (30 / span)
        pts = WEIGHTS["growth"] * _clamp((monthly + GROWTH_FULL) / (2 * GROWTH_FULL))
        comps["growth"] = {"points": round(pts, 1), "max": WEIGHTS["growth"],
                           "value": round(monthly * 100, 1), "days": span}

    # Integrity
    # Task 21 pricing verdict (channel avg_views, fresh only) is authoritative;
    # the post-based ratio is a fallback when no verdict is passed in.
    if price_verdict is not None:
        inflated = price_verdict == VERDICT_INFLATED
    else:
        inflated = ratio is not None and (ratio < MIN_VIEW_RATIO or ratio > MAX_VIEW_RATIO)
    snaps = sorted((datetime(d.year, d.month, d.day), s) for d, s in snapshots if s)
    jumps = 0
    for (d1, s1), (d2, s2) in zip(snaps, snaps[1:]):
        days = max((d2 - d1).days, 1)
        delta = abs(s2 - s1) / days
        if delta >= JUMP_ABS and delta / max(s1, 1) > JUMP_REL:
            jumps += 1
    if ratio is not None or len(snaps) >= 2 or inflated:
        pts = 0.0 if inflated else max(0, WEIGHTS["integrity"] - JUMP_PENALTY * jumps)
        comps["integrity"] = {"points": round(pts, 1), "max": WEIGHTS["integrity"],
                              "inflated": inflated, "jumps": jumps}

    suspicious = inflated or jumps > 0
    if "er" not in comps or "regularity" not in comps:
        return {"score": None, "health": HEALTH_SUSPICIOUS if suspicious else HEALTH_INSUFFICIENT,
                "breakdown": {"components": comps, "reasons": sorted(set(reasons))}}
    got = sum(c["points"] for c in comps.values())
    mx = sum(c["max"] for c in comps.values())
    score = round(100 * got / mx)
    if inflated:
        score = min(score, INFLATED_CAP)
    return {"score": int(score), "health": HEALTH_SUSPICIOUS if suspicious else HEALTH_CLEAN,
            "breakdown": {"components": comps, "reasons": sorted(set(reasons)),
                          "missing": [k for k in WEIGHTS if k not in comps]}}


async def compute_for_channel(db, channel_id: int, now: datetime | None = None) -> dict | None:
    """Score one channel from DB data, store on channels + history. Does not commit."""
    from app.models.channel import Channel, ChannelPost, ChannelQualityHistory, ChannelStats

    now = now or utcnow_naive()
    row = (await db.execute(
        select(Channel.subscribers_count, Channel.is_closed, Channel.views_hidden,
               Channel.growth_30d, Channel.growth_7d, Channel.category, Channel.price,
               Channel.avg_views, Channel.last_post_date).where(Channel.id == channel_id)
    )).first()
    if row is None:
        return None
    posts = (await db.execute(
        select(ChannelPost.date, ChannelPost.views).where(
            ChannelPost.channel_id == channel_id,
            ChannelPost.is_deleted.is_(False),
            ChannelPost.date >= now - timedelta(days=WINDOW_DAYS),
        )
    )).all()
    snaps = (await db.execute(
        select(ChannelStats.date, ChannelStats.subscribers).where(
            ChannelStats.channel_id == channel_id,
            ChannelStats.subscribers.is_not(None),
            ChannelStats.date >= now - timedelta(days=60),
        )
    )).all()
    from app.services.pricing import build_market, estimate

    verdict = estimate(build_market(), category=row[5], price=row[6] or 0, subscribers=row[0],
                       avg_views=row[7], is_closed=bool(row[1]), views_hidden=bool(row[2]),
                       last_post_date=row[8], now=now)["price_verdict"]
    r = score_channel(subscribers=row[0], price_verdict=verdict, is_closed=bool(row[1]), views_hidden=bool(row[2]),
                      growth_30d=row[3], growth_7d=row[4],
                      posts=[(p[0], p[1]) for p in posts], snapshots=[(s[0], s[1]) for s in snaps], now=now)
    await db.execute(update(Channel).where(Channel.id == channel_id).values(
        quality_score=r["score"], quality_health=r["health"], quality_breakdown=r["breakdown"],
        quality_updated_at=now))
    await db.execute(insert(ChannelQualityHistory).values(
        channel_id=channel_id, computed_at=now, score=r["score"], health=r["health"],
        breakdown=r["breakdown"]))
    return r


async def recompute_due(min_age_hours: float = RECOMPUTE_HOURS, now: datetime | None = None) -> int:
    """Recompute channels whose score is older than min_age_hours (or never computed)."""
    from app.database import async_session
    from app.models.channel import Channel, ChannelStatus

    now = now or utcnow_naive()
    cutoff = now - timedelta(hours=min_age_hours)
    async with async_session() as db:
        ids = (await db.execute(select(Channel.id).where(
            Channel.status.in_([ChannelStatus.approved, ChannelStatus.pending]),
            (Channel.quality_updated_at.is_(None)) | (Channel.quality_updated_at <= cutoff),
        ))).scalars().all()
    done = 0
    for cid in ids:
        try:
            async with async_session() as db:
                await compute_for_channel(db, cid, now=now)
                await db.commit()
                done += 1
        except Exception as e:  # one bad channel must not stop the batch
            logger.error("[QUALITY] channel #%s failed: %s", cid, e)
    logger.info("[QUALITY] recomputed %s/%s channels", done, len(ids))
    return done


async def run_quality_scorer(startup_delay_sec: int = 60, interval_hours: float = RECOMPUTE_HOURS):
    """Background loop: once shortly after startup, then every interval_hours."""
    await asyncio.sleep(startup_delay_sec)
    while True:
        try:
            await recompute_due(min_age_hours=interval_hours)
        except Exception as e:
            logger.error("[QUALITY] scorer error: %s", e)
        await asyncio.sleep(interval_hours * 3600)
