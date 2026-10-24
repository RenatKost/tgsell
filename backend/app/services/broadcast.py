"""Admin one-off broadcast through the alerts bot.

Segment «продавці з активним лотом»: distinct sellers with ≥1 published (approved) channel
or bundle not in the exclusion lists, subscribed to the alerts bot (/start seen, not
unreachable), not blocked, never the owners' accounts. Idempotent per campaign_key via
UNIQUE(campaign_key, user_id): a row is claimed (pending → sending) before the send, so a
re-run never messages anyone who already got (or may have got) the campaign.
"""
from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import func, or_, select, update

from app.models.broadcast import BroadcastLog
from app.models.bundle import BundleStatus, ChannelBundle
from app.models.channel import Channel, ChannelStatus
from app.models.user import User
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

ALWAYS_EXCLUDED_USERNAMES = ("renat_kos", "ox010010")
MAX_RECIPIENTS = 500
SEND_INTERVAL_SEC = 0.1  # ≈10 msg/s
TEXT_MAX = 4000
KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{3,64}$")

_tasks: dict[str, asyncio.Task] = {}


class BroadcastError(Exception):
    pass


def validate_key(key: str) -> str:
    key = (key or "").strip()
    if not KEY_RE.match(key):
        raise BroadcastError("campaign_key: 3–64 символи, латиниця, цифри, _ . : -")
    return key


async def segment_active_sellers(db, exclude_channel_ids=(), exclude_bundle_ids=()) -> list[User]:
    ch_q = select(Channel.seller_id).where(Channel.status == ChannelStatus.approved)
    if exclude_channel_ids:
        ch_q = ch_q.where(Channel.id.notin_(list(exclude_channel_ids)))
    b_q = select(ChannelBundle.seller_id).where(ChannelBundle.status == BundleStatus.approved)
    if exclude_bundle_ids:
        b_q = b_q.where(ChannelBundle.id.notin_(list(exclude_bundle_ids)))
    q = (select(User).where(
        or_(User.id.in_(ch_q), User.id.in_(b_q)),
        User.telegram_id.isnot(None),
        User.tg_bot_started_at.isnot(None),
        User.tg_bot_unreachable_at.is_(None),
        User.is_blocked.is_(False),
        User.is_active.is_(True),
        or_(User.username.is_(None), func.lower(User.username).notin_(ALWAYS_EXCLUDED_USERNAMES)),
    ).order_by(User.id))
    return list((await db.execute(q)).scalars().all())


async def stats(db, key: str) -> dict:
    rows = dict((await db.execute(select(BroadcastLog.status, func.count(BroadcastLog.id))
                                  .where(BroadcastLog.campaign_key == key).group_by(BroadcastLog.status))).all())
    sent, failed = rows.get("sent", 0), rows.get("failed", 0)
    pending = rows.get("pending", 0) + rows.get("sending", 0)
    task = _tasks.get(key)
    return {"campaign_key": key, "total": sent + failed + pending, "sent": sent, "failed": failed,
            "pending": pending, "running": bool(task and not task.done())}


async def prepare(db, key: str, users: list[User]) -> dict:
    """Insert pending rows for users without a row in this campaign (UNIQUE guards races)."""
    existing = set((await db.execute(select(BroadcastLog.user_id).where(BroadcastLog.campaign_key == key))).scalars())
    new = [u.id for u in users if u.id not in existing]
    for uid in new:
        db.add(BroadcastLog(campaign_key=key, user_id=uid, status="pending"))
    await db.commit()
    return {"already_in_campaign": len(users) - len(new), "added": len(new)}


def _is_unreachable(e: Exception) -> bool:
    from app.services.chat_bridge import is_unreachable_error
    text = f"{type(e).__name__} {e}".lower()
    return is_unreachable_error(e) or "forbidden" in text or "blocked" in text


async def run_campaign(session_factory, key: str, text: str, bot=None, interval: float = SEND_INTERVAL_SEC) -> dict:
    if bot is None:
        from app.services.chat_bridge import get_bot
        bot = get_bot()
    if bot is None:
        raise BroadcastError("Alert-бот не налаштований")
    sent = failed = 0
    async with session_factory() as db:
        ids = (await db.execute(select(BroadcastLog.id).where(
            BroadcastLog.campaign_key == key, BroadcastLog.status == "pending").order_by(BroadcastLog.id))).scalars().all()
        await db.commit()
    for log_id in ids:
        async with session_factory() as db:
            claimed = await db.execute(update(BroadcastLog).where(
                BroadcastLog.id == log_id, BroadcastLog.status == "pending").values(status="sending"))
            await db.commit()
            if claimed.rowcount != 1:
                continue  # another run took it
            row = await db.get(BroadcastLog, log_id)
            user = await db.get(User, row.user_id)
            try:
                await bot.send_message(user.telegram_id, text, parse_mode="HTML", disable_web_page_preview=True)
                row.status, row.sent_at, row.error = "sent", utcnow_naive(), None
                sent += 1
            except Exception as e:
                row.status, row.error = "failed", f"{type(e).__name__}: {e}"[:1000]
                if _is_unreachable(e):
                    user.tg_bot_unreachable_at = utcnow_naive()
                failed += 1
                logger.warning(f"[BROADCAST] {key} → user #{row.user_id}: {type(e).__name__}")
            await db.commit()
        await asyncio.sleep(interval)
    logger.info(f"[BROADCAST] {key}: sent={sent} failed={failed}")
    return {"sent": sent, "failed": failed}


def start_background(session_factory, key: str, text: str) -> bool:
    task = _tasks.get(key)
    if task and not task.done():
        return False
    _tasks[key] = asyncio.get_running_loop().create_task(run_campaign(session_factory, key, text))
    return True
