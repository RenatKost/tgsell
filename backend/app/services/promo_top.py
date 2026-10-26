"""Seller promo «Топ у подарунок»: a lot approved by moderation for the first time before the
configured deadline (settings.promo_top_until, Europe/Chisinau) gets a free «Топ» for N days.

Uses the paid-services Top mechanism (``Channel.top_until``) with ``top_source="promo"``;
no PaidServiceOrder / payment row is created. Idempotent via ``Channel.first_approved_at``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

PROMO_SOURCE = "promo"


def promo_deadline_utc() -> datetime | None:
    """Deadline as naive UTC (None if config is unparsable → promo off)."""
    try:
        local = datetime.fromisoformat(settings.promo_top_until)
        if local.tzinfo is None:
            local = local.replace(tzinfo=ZoneInfo(settings.promo_top_tz))
        return local.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception as e:
        logger.warning(f"[PROMO] bad promo_top_until: {e}")
        return None


def promo_active(now: datetime | None = None) -> bool:
    end = promo_deadline_utc()
    return bool(end and (now or utcnow_naive()) <= end)


def promo_info(now: datetime | None = None) -> dict:
    end = promo_deadline_utc()
    active = promo_active(now)
    out = {"active": active, "days": int(settings.promo_top_days), "ends_at": None, "ends_at_local": None}
    if end:
        out["ends_at"] = end.replace(tzinfo=timezone.utc).isoformat()
        out["ends_at_local"] = end.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.promo_top_tz)).isoformat()
    return out


def on_first_approval(channel, now: datetime | None = None) -> bool:
    """Call when moderation approves ``channel``. Marks first approval; grants the promo Top
    once. Returns True if a promo Top was granted. Never shortens an existing Top."""
    now = now or utcnow_naive()
    if channel.first_approved_at is not None:
        return False
    channel.first_approved_at = now
    if not promo_active(now):
        return False
    target = now + timedelta(days=int(settings.promo_top_days))
    if channel.top_until and channel.top_until >= target:
        return False  # already has a longer Top: keep it untouched
    channel.top_until = target
    channel.top_source = PROMO_SOURCE
    logger.info(f"[PROMO] free Top for channel #{channel.id} until {target}")
    return True
