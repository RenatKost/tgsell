"""Seller alerts about admin actions on a lot (outbox «seller_notifications», migration 0067).

enqueue_*  — called by admin endpoints inside the SAME transaction as the action.
process_due — called by the paid-services loop; delivers via the alerts bot.

Delivery follows the «Топ увімкнено» pattern (#114): permanent failures (no telegram_id,
bot blocked, chat not found, user deactivated) are stamped failed_at and never retried;
temporary failures back off and retry until NOTIFY_RETRY_HOURS after enqueue, then fail.
A row is claimed (attempts+1, next_attempt_at pushed forward, FOR UPDATE SKIP LOCKED)
before the send, so two loops (e.g. old + new container) never send the same row.
Final outcome → admin_audit_log «channel.notify» {kind, result} (ids only).
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.seller_notification import SellerNotification
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

KIND_UNPUBLISH = "unpublish"
KIND_REMOVE = "remove"
KIND_DELETE = "delete"
KIND_BUYER_WARNING = "buyer_warning"
TAKEDOWN_KINDS = (KIND_UNPUBLISH, KIND_REMOVE, KIND_DELETE)
KINDS = TAKEDOWN_KINDS + (KIND_BUYER_WARNING,)

NOTIFY_RETRY_HOURS = 24
BATCH = 20
# minutes to wait after attempt N (1-based); the last value repeats until the 24h cutoff
BACKOFF_MINUTES = (1, 5, 15, 60, 180)
SUPPORT_HANDLE = "@tgsell_support_bot"


# ── enqueue (same transaction as the admin action) ─────────────────────

def enqueue(db, channel, kind: str, **payload) -> SellerNotification:
    if kind not in KINDS:
        raise ValueError(f"unknown seller notification kind: {kind}")
    now = utcnow_naive()
    row = SellerNotification(
        user_id=channel.seller_id, channel_id=channel.id, kind=kind,
        payload=payload or None, attempts=0, created_at=now, next_attempt_at=now,
    )
    db.add(row)
    return row


def enqueue_takedown(db, channel, kind: str, reason: str | None) -> SellerNotification:
    return enqueue(db, channel, kind, reason=(reason or "").strip() or None)


def enqueue_buyer_warning(db, channel, prev: str | None, value: str | None) -> SellerNotification | None:
    """Only when a warning is set or its text changed — never on clear / unchanged."""
    value = (value or "").strip() or None
    prev = (prev or "").strip() or None
    if value is None or value == prev:
        return None
    return enqueue(db, channel, KIND_BUYER_WARNING, warning=value)


# ── texts ──────────────────────────────────────────────────────────────

def _lot_line(channel) -> str:
    return f"📡 «{html.escape(getattr(channel, 'channel_name', None) or '')}» (#{channel.id})"


def render(kind: str, channel, payload: dict | None) -> str:
    payload = payload or {}
    if kind in TAKEDOWN_KINDS:
        reason = payload.get("reason") or "Не вказано"
        return (
            "⛔️ <b>Ваш лот знято з публікації</b>\n"
            f"{_lot_line(channel)}\n"
            f"Причина: {html.escape(reason)}\n\n"
            "Лот не видалено, він є у вашому кабінеті. Щоб повернути його в каталог, усуньте причину "
            f"й напишіть у підтримку {SUPPORT_HANDLE} — модератор перевірить і відновить публікацію."
        )
    if kind == KIND_BUYER_WARNING:
        return (
            "⚠️ <b>На вашому лоті з'явилося попередження для покупців</b>\n"
            f"{_lot_line(channel)}\n"
            f"Текст: {html.escape(payload.get('warning') or '')}\n\n"
            f"Якщо вважаєте це помилкою або усунули причину — напишіть у підтримку {SUPPORT_HANDLE}."
        )
    raise ValueError(kind)


def cabinet_url() -> str:
    from app.config import settings
    return settings.frontend_url.rstrip("/") + "/cabinet"


def keyboard(kind: str):
    if kind not in TAKEDOWN_KINDS:
        return None
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Відкрити кабінет", url=cabinet_url())]])


# ── delivery ───────────────────────────────────────────────────────────

def _obsolete(row: SellerNotification, channel) -> bool:
    """The action was undone (or superseded) before we managed to send it."""
    from app.models.channel import ChannelStatus
    status = getattr(channel.status, "value", channel.status)
    if row.kind == KIND_UNPUBLISH:
        return status != ChannelStatus.rejected.value
    if row.kind in (KIND_REMOVE, KIND_DELETE):
        return status != ChannelStatus.removed.value
    if row.kind == KIND_BUYER_WARNING:
        return (channel.buyer_warning or None) != (row.payload or {}).get("warning")
    return False


def _backoff(attempts: int) -> timedelta:
    idx = min(max(attempts, 1), len(BACKOFF_MINUTES)) - 1
    return timedelta(minutes=BACKOFF_MINUTES[idx])


def _short_error(e: BaseException) -> str:
    from app.utils.log_redact import redact
    return redact(f"{type(e).__name__}: {e}")[:300]


def _audit_outcome(db, row: SellerNotification, result: str) -> None:
    from app.services.moderation import audit
    audit(db, None, "channel.notify", "channel", row.channel_id,
          kind=row.kind, result=result, notification_id=row.id, attempts=row.attempts)


async def _default_send(chat_id: int, text: str, reply_markup) -> None:
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from app.config import settings
    bot = Bot(token=settings.bot_token_alerts)
    try:
        await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup,
                               disable_web_page_preview=True)
    finally:
        await bot.session.close()


async def _claim(session_factory, now: datetime) -> list[int]:
    """Lock due rows (SKIP LOCKED), bump attempts and push next_attempt_at before sending."""
    async with session_factory() as db:
        q = (select(SellerNotification)
             .where(SellerNotification.sent_at.is_(None), SellerNotification.failed_at.is_(None),
                    SellerNotification.next_attempt_at <= now)
             .order_by(SellerNotification.id).limit(BATCH))
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        rows = (await db.execute(q)).scalars().all()
        for r in rows:
            r.attempts = (r.attempts or 0) + 1
            r.next_attempt_at = now + _backoff(r.attempts)
        await db.commit()
        return [r.id for r in rows]


async def process_due(session_factory, now: datetime | None = None, send=None) -> dict:
    """Deliver due notifications once. Returns counters. Never raises per-row errors."""
    from app.config import settings
    from app.models.channel import Channel
    from app.models.user import User
    from app.utils.telegram_errors import is_permanent_telegram_error

    stats = {"sent": 0, "failed": 0, "retry": 0, "obsolete": 0}
    if send is None:
        if not settings.bot_token_alerts:
            return stats  # not configured: leave rows untouched (no attempts burned)
        send = _default_send
    now = now or utcnow_naive()
    ids = await _claim(session_factory, now)
    for nid in ids:
        try:
            async with session_factory() as db:
                row = await db.get(SellerNotification, nid)
                if row is None or row.sent_at is not None or row.failed_at is not None:
                    continue
                channel = await db.get(Channel, row.channel_id)
                seller = await db.get(User, row.user_id)
                expired = now - row.created_at >= timedelta(hours=NOTIFY_RETRY_HOURS)
                if channel is None or _obsolete(row, channel):
                    row.failed_at, row.last_error = now, "obsolete"
                    _audit_outcome(db, row, "obsolete")
                    stats["obsolete"] += 1
                elif seller is None or not seller.telegram_id:
                    row.failed_at, row.last_error = now, "no_telegram"
                    _audit_outcome(db, row, "no_telegram")
                    stats["failed"] += 1
                elif expired:
                    row.failed_at = now
                    row.last_error = (row.last_error or "expired")[:300]
                    _audit_outcome(db, row, "expired")
                    stats["failed"] += 1
                else:
                    try:
                        await send(seller.telegram_id, render(row.kind, channel, row.payload), keyboard(row.kind))
                    except Exception as e:  # noqa: BLE001 — classified below
                        row.last_error = _short_error(e)
                        if is_permanent_telegram_error(e):
                            row.failed_at = now
                            _audit_outcome(db, row, "permanent_error")
                            stats["failed"] += 1
                            logger.info("[SELLER-NOTICE] #%s %s channel #%s: permanent failure (%s)",
                                        row.id, row.kind, row.channel_id, type(e).__name__)
                        elif row.next_attempt_at is None or row.next_attempt_at - row.created_at >= timedelta(hours=NOTIFY_RETRY_HOURS):
                            row.failed_at = now
                            _audit_outcome(db, row, "expired")
                            stats["failed"] += 1
                            logger.warning("[SELLER-NOTICE] #%s %s channel #%s: gave up after %s attempts (%s)",
                                           row.id, row.kind, row.channel_id, row.attempts, type(e).__name__)
                        else:
                            stats["retry"] += 1
                            logger.info("[SELLER-NOTICE] #%s %s channel #%s: attempt %s failed (%s), retry later",
                                        row.id, row.kind, row.channel_id, row.attempts, type(e).__name__)
                    else:
                        row.sent_at, row.last_error = now, None
                        _audit_outcome(db, row, "sent")
                        stats["sent"] += 1
                await db.commit()
        except Exception as e:  # DB hiccup on one row must not stop the rest
            logger.warning("[SELLER-NOTICE] #%s processing error: %s", nid, type(e).__name__)
    if any(stats.values()):
        logger.info("[SELLER-NOTICE] %s", stats)
    return stats
