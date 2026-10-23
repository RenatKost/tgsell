"""AI audit guard: never analyse (or show a cached analysis of) channels without real stats.

A channel is "ready" when it has a real subscriber count (> 0) AND at least one
dated stats snapshot (channel_stats row with subscribers); for closed channels a
seller-stated / invite-preview count is enough. The cache stores a
fingerprint of the stats it was generated from; any change invalidates it.
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import ChannelStats

FP_KEY = "_stats_fp"
PREPARING_MESSAGE = "Аналіз готується — збираємо статистику каналів. Зазирніть трохи пізніше."


def preparing_result() -> dict:
    """200-payload shown by the UI as «Аналіз готується». Never cached."""
    return {"status": "preparing", "message": PREPARING_MESSAGE}


async def last_snapshot_dates(db: AsyncSession, channel_ids: Iterable[int]) -> dict:
    ids = list(channel_ids)
    if not ids:
        return {}
    rows = (await db.execute(
        select(ChannelStats.channel_id, func.max(ChannelStats.date))
        .where(ChannelStats.channel_id.in_(ids), ChannelStats.subscribers.isnot(None),
               ChannelStats.subscribers > 0)
        .group_by(ChannelStats.channel_id)
    )).all()
    return {cid: d for cid, d in rows}


def channel_ready(channel, snapshot_dates: dict) -> bool:
    if (channel.subscribers_count or 0) <= 0:
        return False
    # Closed channels can't always be auto-read: a seller-stated count (> 0) is accepted.
    return bool(snapshot_dates.get(channel.id) or getattr(channel, "is_closed", False))


async def channels_ready(db: AsyncSession, channels: list) -> bool:
    if not channels:
        return False
    dates = await last_snapshot_dates(db, [c.id for c in channels])
    return all(channel_ready(c, dates) for c in channels)


def stats_fingerprint(channels: list) -> str:
    parts = sorted(
        (c.id, int(c.subscribers_count or 0), int(c.avg_views or 0), round(float(c.er or 0), 2),
         bool(getattr(c, "is_closed", False)))
        for c in channels
    )
    return hashlib.sha1(json.dumps(parts).encode()).hexdigest()[:16]


def dump_cache(analysis: dict, fp: str) -> str:
    return json.dumps({**analysis, FP_KEY: fp}, ensure_ascii=False)


def load_cache(raw: str | None, fp: str) -> dict | None:
    """Cached analysis only if it was generated from exactly these stats."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.pop(FP_KEY, None) != fp:
        return None
    return data
