"""Best-effort Telethon auto-verification for the deal transfer checklist.

Read-only observations (subscriber count, admin list, creator) are stored as
auto_verified / auto_note on checklist items. This module NEVER ticks items,
NEVER changes deal status and NEVER moves money.

Safety: it only uses the Telethon client when get_telethon_health()["ok"] is
already True, so it never triggers a fresh connect (e.g. during the deploy
startup delay — AuthKeyDuplicated risk with overlapping containers).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from app.models.deal import Deal
from app.services import deal_checklist as checklist_svc

logger = logging.getLogger(__name__)

_COOLDOWN_SEC = 60
_TIMEOUT_SEC = 25
_last_run: dict[int, float] = {}

TELETHON_DOWN_MSG = (
    "Telethon тимчасово недоступний — автоперевірка неможлива. "
    "Відмітьте пункти вручну після перевірки в Telegram."
)


async def _deal_channels(db, deal: Deal) -> list:
    from sqlalchemy import select
    from app.models.channel import Channel

    if deal.channel_id:
        ch = await db.get(Channel, deal.channel_id)
        return [ch] if ch else []
    if deal.bundle_id:
        from app.models.bundle import BundleChannel

        rows = (await db.execute(
            select(BundleChannel).where(BundleChannel.bundle_id == deal.bundle_id)
        )).scalars().all()
        out = []
        for bc in rows:
            ch = await db.get(Channel, bc.channel_id)
            if ch:
                out.append(ch)
        return out
    return []


async def _observe_channel(client, channel) -> dict:
    """Collect read-only facts about one channel via Telethon."""
    res = {
        "name": channel.channel_name,
        "expected_subs": channel.subscribers_count or 0,
        "actual_subs": None,
        "admins": None,
        "error": None,
    }
    username = checklist_svc.parse_channel_username(channel.telegram_link)
    if not username:
        res["error"] = "приватне посилання — автоперевірка неможлива"
        return res
    try:
        from telethon.tl.functions.channels import GetFullChannelRequest

        entity = await client.get_entity(username)
        full = await client(GetFullChannelRequest(entity))
        res["actual_subs"] = getattr(full.full_chat, "participants_count", None)
    except Exception as e:
        logger.warning(f"[CHECKLIST] auto-verify: channel @{username} lookup failed: {type(e).__name__}")
        res["error"] = "канал не знайдено або недоступний для перевірки"
        return res

    try:
        from telethon.tl.types import ChannelParticipantCreator, ChannelParticipantsAdmins

        admins = []
        async for u in client.iter_participants(entity, filter=ChannelParticipantsAdmins):
            admins.append({
                "id": u.id,
                "is_bot": bool(getattr(u, "bot", False)),
                "is_creator": isinstance(getattr(u, "participant", None), ChannelParticipantCreator),
            })
        res["admins"] = admins
    except Exception as e:
        # Typically ChatAdminRequiredError — service account is not a channel admin.
        logger.info(f"[CHECKLIST] auto-verify: admins of @{username} not visible: {type(e).__name__}")
        res["admins"] = None
    return res


async def run_auto_verify(db, deal: Deal, items: list) -> str:
    """Run checks and store auto_verified/auto_note. Returns a Ukrainian summary. No commit."""
    from app.services.channel_stats import get_telethon_health

    now_mono = time.monotonic()
    last = _last_run.get(deal.id)
    if last and now_mono - last < _COOLDOWN_SEC:
        wait = int(_COOLDOWN_SEC - (now_mono - last))
        return f"Автоперевірку щойно виконано — повторити можна через {wait} с."

    try:
        health = get_telethon_health()
    except Exception:
        health = {"ok": False}
    if not health.get("ok"):
        logger.info(f"[CHECKLIST] deal #{deal.id} auto-verify skipped: Telethon unavailable")
        return TELETHON_DOWN_MSG

    _last_run[deal.id] = now_mono
    try:
        from app.services.channel_stats import _get_telethon_client

        client = await _get_telethon_client()
        if client is None:
            return TELETHON_DOWN_MSG
        channels = await _deal_channels(db, deal)
        if not channels:
            return "Немає каналів для перевірки."

        async def _all():
            return [await _observe_channel(client, ch) for ch in channels]

        results = await asyncio.wait_for(_all(), timeout=_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        return "Автоперевірка не встигла за відведений час — спробуйте пізніше."
    except Exception as e:
        logger.warning(f"[CHECKLIST] deal #{deal.id} auto-verify failed: {type(e).__name__}")
        return TELETHON_DOWN_MSG

    buyer_tg = deal.buyer.telegram_id if deal.buyer else None
    seller_tg = deal.seller.telegram_id if deal.seller else None
    verdicts = checklist_svc.evaluate_auto_verify(results, buyer_tg=buyer_tg, seller_tg=seller_tg)

    now = datetime.utcnow()
    by_key = {i.key: i for i in items}
    for key, (verified, note) in verdicts.items():
        row = by_key.get(key)
        if row is None:
            continue
        row.auto_verified = verified
        row.auto_note = (note or "")[:1000] or None
        row.auto_checked_at = now

    summary = ", ".join(
        f"{k}={'✓' if v is True else '✗' if v is False else '?'}"
        for k, (v, _) in verdicts.items()
    )
    logger.info(f"[CHECKLIST] deal #{deal.id} auto-verify: {summary}")
    return "Автоперевірку виконано. Результати — біля відповідних пунктів (лише підказка, не замінює ручну перевірку)."
