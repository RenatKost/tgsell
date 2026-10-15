"""Honest channel-stats time series (Task 20).

* ``save_stats_history`` — the single writer for ``channel_stats``:
  - retro points rebuilt from posts carry post metrics ONLY
    (subscribers / ER = NULL — the historical subscriber count is unknown);
  - today's row is a real snapshot (subscribers / avg_views / ER right now);
  - rows of the last ``OVERWRITE_DAYS`` days are refreshed on every run
    (upsert on the unique (channel_id, date) key), older ones are only inserted.
* ``compute_growth`` — daily / 7d / 30d subscriber growth from real snapshots
  only; ``None`` (not 0) when there is no snapshot far enough back.

All writes go through plain Core statements with ids passed in explicitly, so
nothing lazy-loads an expired ORM attribute after a commit (cf. PR #27 greenlet).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel, ChannelStats
from app.utils.timeutil import utcnow_naive

OVERWRITE_DAYS = 3
# (days back, max extra tolerance in days) for picking the comparison snapshot
GROWTH_WINDOWS = {"daily_growth": (1, 1), "growth_7d": (7, 3), "growth_30d": (30, 7)}


def _day(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day)


def _upsert(values: dict, update_cols: list[str], only_if_recent: datetime | None):
    stmt = pg_insert(ChannelStats).values(**values)
    if not update_cols:
        return stmt.on_conflict_do_nothing(index_elements=["channel_id", "date"])
    set_ = {c: stmt.excluded[c] for c in update_cols}
    set_["recorded_at"] = func.now()
    kwargs = {}
    if only_if_recent is not None:
        kwargs["where"] = ChannelStats.date >= only_if_recent
    return stmt.on_conflict_do_update(index_elements=["channel_id", "date"], set_=set_, **kwargs)


async def save_stats_history(
    db: AsyncSession, channel_id: int, stats: dict, now: datetime | None = None
) -> int:
    """Write retro post-metric points + today's real snapshot. Returns rows written
    (inserted or refreshed). Does not commit."""
    now = now or utcnow_naive()
    today = _day(now)
    recent_from = today - timedelta(days=OVERWRITE_DAYS)
    written = 0

    post_cols = ["avg_views", "avg_reach", "post_count", "avg_forwards", "avg_reactions"]
    today_retro: dict | None = None
    for ds in stats.get("daily_stats") or []:
        try:
            day = datetime.strptime(ds["date"], "%Y-%m-%d")
        except (KeyError, ValueError, TypeError):
            continue
        values = {
            "channel_id": channel_id,
            "date": day,
            "subscribers": None,
            "er": None,
            "avg_views": ds.get("avg_views") or 0,
            "avg_reach": ds.get("avg_views") or 0,
            "post_count": ds.get("post_count") or 0,
            "avg_forwards": ds.get("avg_forwards") or 0,
            "avg_reactions": ds.get("avg_reactions") or 0,
        }
        if day >= today:
            today_retro = values  # merged into today's snapshot below
            continue
        # Only post metrics are refreshed for recent days; a real snapshot's
        # subscribers / ER on that day are never wiped by a retro point.
        res = await db.execute(_upsert(values, post_cols, recent_from))
        written += res.rowcount or 0

    subs = stats.get("subscribers_count") or None
    avg_views = stats.get("avg_views") or 0
    er = stats.get("er")
    if subs is None:
        er = None  # ER without a real subscriber count is not honest
    if subs is not None or avg_views or today_retro:
        snap = {
            "channel_id": channel_id,
            "date": today,
            "subscribers": subs,
            "er": er if er is not None else None,
            "avg_views": avg_views,
            "avg_reach": avg_views,
            "post_count": (today_retro or {}).get("post_count", 0),
            "avg_forwards": stats.get("avg_forwards") or 0,
            "avg_reactions": stats.get("avg_reactions") or 0,
        }
        stmt = pg_insert(ChannelStats).values(**snap)
        ex = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["channel_id", "date"],
            set_={
                # keep a known value if this run could not read it
                "subscribers": func.coalesce(ex.subscribers, ChannelStats.subscribers),
                "er": func.coalesce(ex.er, ChannelStats.er),
                "avg_views": ex.avg_views,
                "avg_reach": ex.avg_reach,
                "post_count": ex.post_count,
                "avg_forwards": ex.avg_forwards,
                "avg_reactions": ex.avg_reactions,
                "recorded_at": func.now(),
            },
        )
        res = await db.execute(stmt)
        written += res.rowcount or 0
    return written


async def compute_growth(db: AsyncSession, channel_id: int) -> dict:
    """{daily_growth, growth_7d, growth_30d} from real snapshots; None when unknown."""
    rows = (
        await db.execute(
            select(ChannelStats.date, ChannelStats.subscribers)
            .where(
                ChannelStats.channel_id == channel_id,
                ChannelStats.subscribers.is_not(None),
                ChannelStats.subscribers > 0,
            )
            .order_by(ChannelStats.date.desc())
        )
    ).all()
    out = {k: None for k in GROWTH_WINDOWS}
    if len(rows) < 2:
        return out
    latest_date, latest_subs = _day(rows[0][0]), rows[0][1]
    for key, (days, tol) in GROWTH_WINDOWS.items():
        target = latest_date - timedelta(days=days)
        oldest_ok = target - timedelta(days=tol)
        for d, s in rows[1:]:
            d = _day(d)
            if d <= target:
                if d >= oldest_ok:
                    out[key] = latest_subs - s
                break
    return out


async def refresh_channel_growth(db: AsyncSession, channel_id: int) -> dict:
    """Recompute growth fields and store them on the channel row. Does not commit."""
    from sqlalchemy import update

    g = await compute_growth(db, channel_id)
    await db.execute(update(Channel).where(Channel.id == channel_id).values(**g))
    return g


async def record_stats(db: AsyncSession, channel_id: int, stats: dict) -> int:
    """save_stats_history + refresh_channel_growth. Does not commit."""
    written = await save_stats_history(db, channel_id, stats)
    await refresh_channel_growth(db, channel_id)
    return written
