"""Task 24: saved catalog searches and match notifications via tgsell_alert_bot.

When a listing is approved, matching saved searches get a match row. A
background flusher groups unprocessed matches per search (at most one
Telegram message per search per hour) and marks undelivered when the user
never pressed Start or send fails.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel, ChannelStatus
from app.models.saved_search import SavedSearch, SavedSearchMatch
from app.models.user import User
from app.services.catalog_filters import CATALOG_FILTER_KEYS, apply_catalog_filters
from app.services.moderation import not_blocked_seller
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

MAX_PER_USER = 10
NOTIFY_COOLDOWN = timedelta(hours=1)
NAME_MAX = 100
FILTER_BOOL = {"verified_data", "ai_recommended", "no_inflation", "with_balance"}
FILTER_FLOAT = {"min_price", "max_price", "er_min", "pps_min", "pps_max"}
FILTER_INT = {"roi_max", "min_subscribers", "max_subscribers"}
FILTER_STR = {"search", "category"}


def sanitize_filters(raw: dict | None) -> dict:
    """Keep only known catalog keys with typed values; drop empties."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k in CATALOG_FILTER_KEYS:
        if k not in raw or raw[k] is None or raw[k] == "":
            continue
        v = raw[k]
        try:
            if k in FILTER_BOOL:
                out[k] = bool(v)
            elif k in FILTER_FLOAT:
                out[k] = float(v)
            elif k in FILTER_INT:
                out[k] = int(v)
            elif k in FILTER_STR:
                s = str(v).strip()[:100]
                if s:
                    out[k] = s
        except (TypeError, ValueError):
            continue
    return out


def filters_label(f: dict) -> str:
    parts = []
    if f.get("category"):
        parts.append(str(f["category"]))
    if f.get("min_price") is not None or f.get("max_price") is not None:
        lo = f.get("min_price")
        hi = f.get("max_price")
        parts.append(f"{lo or 0}–{hi if hi is not None else '∞'} USDT")
    if f.get("min_subscribers") is not None or f.get("max_subscribers") is not None:
        lo = f.get("min_subscribers")
        hi = f.get("max_subscribers")
        parts.append(f"{lo or 0}–{hi if hi is not None else '∞'} підп.")
    if f.get("no_inflation"):
        parts.append("без накрутки")
    if f.get("with_balance"):
        parts.append("з балансом")
    if f.get("verified_data"):
        parts.append("перевірені дані")
    if f.get("ai_recommended"):
        parts.append("AI рекомендує")
    if f.get("er_min") is not None:
        parts.append(f"ER ≥ {f['er_min']}%")
    if f.get("roi_max") is not None:
        parts.append(f"ROI ≤ {f['roi_max']} міс.")
    if f.get("pps_min") is not None or f.get("pps_max") is not None:
        lo = f.get("pps_min")
        hi = f.get("pps_max")
        parts.append(f"$/підп. {lo if lo is not None else '…'}–{hi if hi is not None else '…'}")
    if f.get("search"):
        parts.append("пошук")
    return ", ".join(parts) or "Усі фільтри"


def listing_url(channel_id: int, search_id: int) -> str:
    from app.config import settings
    base = settings.frontend_url.rstrip("/")
    return f"{base}/channel/{channel_id}?ref=saved_search&sid={search_id}"


async def count_for_user(db: AsyncSession, user_id: int) -> int:
    return (await db.execute(
        select(func.count()).select_from(SavedSearch).where(SavedSearch.user_id == user_id)
    )).scalar() or 0


async def list_for_user(db: AsyncSession, user_id: int) -> list[SavedSearch]:
    return list((await db.execute(
        select(SavedSearch).where(SavedSearch.user_id == user_id).order_by(SavedSearch.created_at.desc())
    )).scalars().all())


async def create_for_user(db: AsyncSession, user: User, *, name: str | None, filters: dict) -> SavedSearch:
    clean = sanitize_filters(filters)
    n = (name or "").strip()[:NAME_MAX] or filters_label(clean)[:NAME_MAX]
    if await count_for_user(db, user.id) >= MAX_PER_USER:
        raise ValueError("limit")
    row = SavedSearch(user_id=user.id, name=n, filters=clean)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    from app.services.user_activity import record_event_detached
    await record_event_detached("saved_search_create", user_id=user.id, object_type="saved_search", object_id=row.id)
    return row


async def delete_for_user(db: AsyncSession, user_id: int, search_id: int) -> bool:
    row = (await db.execute(
        select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.user_id == user_id)
    )).scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def channel_matches_filters(db: AsyncSession, channel_id: int, filters: dict) -> bool:
    """True if the (approved) channel would appear under these catalog filters."""
    from app.models.bundle import BundleChannel
    bundled = select(BundleChannel.channel_id).scalar_subquery()
    q = select(Channel.id).where(
        Channel.id == channel_id,
        Channel.status == ChannelStatus.approved,
        ~Channel.id.in_(bundled),
        not_blocked_seller(Channel.seller_id),
    )
    q = apply_catalog_filters(q, filters or {})
    return (await db.execute(q.limit(1))).first() is not None


async def enqueue_matches_for_channel(db: AsyncSession, channel_id: int) -> int:
    """After approve: enqueue a match for every saved search that fits. Idempotent."""
    searches = (await db.execute(select(SavedSearch))).scalars().all()
    n = 0
    for s in searches:
        try:
            if not await channel_matches_filters(db, channel_id, s.filters or {}):
                continue
            exists = (await db.execute(
                select(SavedSearchMatch.id).where(
                    SavedSearchMatch.search_id == s.id, SavedSearchMatch.channel_id == channel_id
                ).limit(1)
            )).first()
            if exists:
                continue
            db.add(SavedSearchMatch(search_id=s.id, channel_id=channel_id))
            n += 1
        except Exception as e:
            logger.warning("[SAVED] match check failed search=%s channel=%s: %s", s.id, channel_id, type(e).__name__)
    if n:
        await db.commit()
    return n


async def _send_grouped(bot, user: User, search: SavedSearch, channels: list[Channel]) -> str:
    """Returns 'sent' | 'not_started' | 'failed'."""
    if not user.telegram_id or not user.tg_bot_started_at or user.tg_bot_unreachable_at:
        return "not_started"
    from html import escape
    from aiogram.enums import ParseMode
    lines = [
        f"🔔 <b>Нові канали за збереженим пошуком</b>",
        f"«{escape(search.name)}»",
        "",
    ]
    for c in channels[:6]:
        url = escape(listing_url(c.id, search.id), quote=True)
        name = escape(c.channel_name or f"#{c.id}")
        price = f"{c.price:g}" if c.price is not None else "—"
        subs = f"{c.subscribers_count:,}".replace(",", " ") if c.subscribers_count else "—"
        lines.append(f"• <a href=\"{url}\">{name}</a> — {subs} підп., {price} USDT")
    if len(channels) > 6:
        lines.append(f"…ще {len(channels) - 6}")
    text = "\n".join(lines)
    try:
        await bot.send_message(user.telegram_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        return "sent"
    except Exception as e:
        from app.services.chat_bridge import is_unreachable_error
        logger.warning("[SAVED] notify user=%s search=%s failed: %s", user.id, search.id, type(e).__name__)
        if is_unreachable_error(e):
            return "not_started"
        return "failed"


async def flush_pending(now=None) -> int:
    """Send at most one grouped message per search per hour. Never raises out."""
    from app.config import settings
    from app.database import async_session
    from aiogram import Bot

    now = now or utcnow_naive()
    if not settings.bot_token_alerts:
        return 0
    sent_n = 0
    async with async_session() as db:
        pending = (await db.execute(
            select(SavedSearchMatch.search_id).where(SavedSearchMatch.processed_at.is_(None)).distinct()
        )).scalars().all()
    for sid in pending:
        try:
            async with async_session() as db:
                # Claim the hourly slot atomically BEFORE sending, so overlapping
                # containers during a deploy cannot double-send.
                claimed = (await db.execute(
                    update(SavedSearch).where(
                        SavedSearch.id == sid,
                        or_(SavedSearch.last_notified_at.is_(None),
                            SavedSearch.last_notified_at <= now - NOTIFY_COOLDOWN),
                    ).values(last_notified_at=now).returning(SavedSearch.id)
                )).first()
                await db.commit()
                if not claimed:
                    continue
                search = await db.get(SavedSearch, sid)
                if not search:
                    continue
                matches = list((await db.execute(
                    select(SavedSearchMatch).where(
                        SavedSearchMatch.search_id == sid, SavedSearchMatch.processed_at.is_(None)
                    ).order_by(SavedSearchMatch.created_at.asc())
                )).scalars().all())
                if not matches:
                    continue
                ch_ids = [m.channel_id for m in matches]
                channels = list((await db.execute(
                    select(Channel).where(Channel.id.in_(ch_ids), Channel.status == ChannelStatus.approved)
                )).scalars().all())
                by_id = {c.id: c for c in channels}
                ordered = [by_id[i] for i in ch_ids if i in by_id]
                user = await db.get(User, search.user_id)
                if not ordered or not user:
                    for m in matches:
                        m.processed_at = now
                        m.delivered = False
                    search.last_notified_at = now
                    search.last_delivery_status = "failed"
                    await db.commit()
                    continue
                bot = Bot(token=settings.bot_token_alerts)
                try:
                    status = await _send_grouped(bot, user, search, ordered)
                finally:
                    await bot.session.close()
                delivered = status == "sent"
                for m in matches:
                    m.processed_at = now
                    m.delivered = delivered
                search.last_notified_at = now
                search.last_delivery_status = status
                await db.commit()
                if delivered:
                    sent_n += 1
        except Exception as e:
            logger.error("[SAVED] flush search=%s: %s", sid, e)
    return sent_n


async def run_saved_search_notifier(startup_delay_sec: int = 90, interval_seconds: int = 60):
    await asyncio.sleep(startup_delay_sec)
    while True:
        try:
            n = await flush_pending()
            if n:
                logger.info("[SAVED] sent %s notification(s)", n)
        except Exception as e:
            logger.error("[SAVED] notifier error: %s", e)
        await asyncio.sleep(interval_seconds)
