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


def link_key(telegram_link: str | None) -> str:
    try:
        from app.services.channel_stats import parse_telegram_link
        ident, _ = parse_telegram_link(telegram_link or "")
    except Exception:
        ident = ""
    return (ident or telegram_link or "").strip().lower()


async def promo_live_for_same_channel(db, channel, now: datetime | None = None) -> bool:
    """Anti-farm: True if the SAME Telegram channel (by link) already has a promo Top that is still
    running — on another lot row, or granted within the last promo_top_days to a lot that was since
    deleted (audit ``promo.top_granted``). A genuine relist after the previous promo ran out is fine."""
    from sqlalchemy import select
    from app.models.channel import Channel
    from app.models.user import AdminAuditLog
    now = now or utcnow_naive()
    key = link_key(channel.telegram_link)
    if not key:
        return False
    rows = (await db.execute(select(Channel.id, Channel.telegram_link).where(
        Channel.id != channel.id, Channel.top_source == PROMO_SOURCE, Channel.top_until > now))).all()
    if any(link_key(link) == key for _, link in rows):
        return True
    since = now - timedelta(days=int(settings.promo_top_days))
    logs = (await db.execute(select(AdminAuditLog.target_id, AdminAuditLog.details).where(
        AdminAuditLog.action == "promo.top_granted", AdminAuditLog.created_at > since))).all()
    return any(tid != channel.id and (d or {}).get("link") == key for tid, d in logs)


async def approve_with_promo(db, channel, admin, now: datetime) -> bool:
    """Moderation approval hook: first approval of THIS lot row + anti-farm check. Returns granted."""
    from app.models.user import AdminAuditLog
    blocked = channel.first_approved_at is None and promo_active(now) and await promo_live_for_same_channel(db, channel, now)
    granted = on_first_approval(channel, now, blocked=blocked)
    if granted:
        db.add(AdminAuditLog(actor_id=getattr(admin, "id", None), action="promo.top_granted", target_type="channel",
                             target_id=channel.id, created_at=now,
                             details={"link": link_key(channel.telegram_link), "until": channel.top_until.isoformat()}))
    return granted


def on_first_approval(channel, now: datetime | None = None, blocked: bool = False) -> bool:
    """Call when moderation approves ``channel``. Marks first approval; grants the promo Top
    once. Returns True if a promo Top was granted. Never shortens an existing Top."""
    now = now or utcnow_naive()
    if channel.first_approved_at is not None:
        return False
    channel.first_approved_at = now
    if blocked or not promo_active(now):
        return False
    target = now + timedelta(days=int(settings.promo_top_days))
    if channel.top_until and channel.top_until >= target:
        return False  # already has a longer Top: keep it untouched
    channel.top_until = target
    channel.top_source = PROMO_SOURCE
    logger.info(f"[PROMO] free Top for channel #{channel.id} until {target}")
    return True
