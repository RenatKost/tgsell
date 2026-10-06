"""Minimal TgSell support bot (@tgsell_support_bot) — private DMs inbox."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramConflictError
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.support import DELIVERY_SENT, SupportMessage
from app.services.support_logic import (
    AUTO_REPLY_TEXT,
    WELCOME_TEXT,
    build_urgent_alert_html,
    is_urgent_text,
    message_text_from_update,
    should_send_auto_reply,
    should_send_urgent_alert,
)
from app.utils.log_redact import redact
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

support_router = Router(name="support")

# In-process urgent-alert dedup (also throttled via send_admin_alert alert_key).
_last_urgent_alert: dict[int, datetime] = {}
# In-process auto-reply cooldown guard (naive UTC), complements the DB lookup.
_last_auto_reply_mem: dict[int, datetime] = {}


def _content_type(message: Message) -> str | None:
    if message.photo:
        return "photo"
    if message.document:
        return "document"
    if message.video:
        return "video"
    if message.voice:
        return "voice"
    if message.audio:
        return "audio"
    if message.sticker:
        return "sticker"
    if message.animation:
        return "animation"
    if message.video_note:
        return "video_note"
    if message.contact:
        return "contact"
    if message.location:
        return "location"
    return None


async def _last_auto_reply_at(db, telegram_user_id: int) -> datetime | None:
    result = await db.execute(
        select(SupportMessage.created_at)
        .where(
            SupportMessage.telegram_user_id == telegram_user_id,
            SupportMessage.direction == "out",
            SupportMessage.text == AUTO_REPLY_TEXT,
        )
        .order_by(SupportMessage.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _save_message(
    *,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    chat_id: int,
    direction: str,
    text: str | None,
    is_urgent: bool = False,
    handled: bool = False,
    reply_to_id: int | None = None,
    telegram_message_id: int | None = None,
) -> SupportMessage:
    now = utcnow_naive()  # naive TIMESTAMP (UTC)
    async with async_session() as db:
        row = SupportMessage(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            chat_id=chat_id,
            direction=direction,
            text=text,
            is_urgent=is_urgent,
            handled=handled,
            handled_at=now if handled else None,
            reply_to_id=reply_to_id,
            # Bot-originated 'out' rows are saved right after Telegram accepted them.
            delivery_status=DELIVERY_SENT if direction == "out" else None,
            sent_at=now if direction == "out" else None,
            telegram_message_id=telegram_message_id if isinstance(telegram_message_id, int) else None,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


@support_router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def support_start(message: Message):
    user = message.from_user
    if not user:
        return
    text = message_text_from_update(message.text, message.caption, _content_type(message))
    await _save_message(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        chat_id=message.chat.id,
        direction="in",
        text=text,
        is_urgent=False,
    )
    sent = await message.answer(WELCOME_TEXT)
    await _save_message(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        chat_id=message.chat.id,
        direction="out",
        text=WELCOME_TEXT,
        handled=True,
        telegram_message_id=getattr(sent, "message_id", None),
    )


@support_router.message(F.chat.type == ChatType.PRIVATE)
async def support_private_message(message: Message):
    """Store inbound DM; auto-reply (30 min dedup); urgent → admin alert."""
    user = message.from_user
    if not user:
        return
    # /start handled above; ignore other commands' empty bodies if any
    text = message_text_from_update(message.text, message.caption, _content_type(message))
    urgent = is_urgent_text(text)

    row = await _save_message(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        chat_id=message.chat.id,
        direction="in",
        text=text,
        is_urgent=urgent,
    )

    # Auto-reply cooldown
    async with async_session() as db:
        last_ar = await _last_auto_reply_at(db, user.id)
    # In-process guard: aiogram handles updates concurrently, so two quick messages
    # could both read "no auto-reply yet" from the DB. Check + set has no await between.
    mem_ar = _last_auto_reply_mem.get(user.id)
    if mem_ar is not None and (last_ar is None or mem_ar > last_ar):
        last_ar = mem_ar
    if should_send_auto_reply(last_ar):
        _last_auto_reply_mem[user.id] = utcnow_naive()
        sent, delivered = None, False
        try:
            sent = await message.answer(AUTO_REPLY_TEXT)
            delivered = True
        except Exception as e:
            _last_auto_reply_mem.pop(user.id, None)  # not delivered → allow next attempt
            logger.error("Support auto-reply failed: %s", redact(e))
        if delivered:
            try:
                await _save_message(
                    telegram_user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    chat_id=message.chat.id,
                    direction="out",
                    text=AUTO_REPLY_TEXT,
                    handled=True,
                    telegram_message_id=getattr(sent, "message_id", None),
                )
            except Exception as e:
                logger.error("Support auto-reply save failed: %s", redact(e))

    if urgent and should_send_urgent_alert(_last_urgent_alert.get(user.id)):
        _last_urgent_alert[user.id] = datetime.now(timezone.utc)
        try:
            from app.services.alerts import send_admin_alert

            await send_admin_alert(
                build_urgent_alert_html(
                    telegram_user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    text=text,
                    message_id=row.id,
                ),
                alert_key=f"support_urgent_{user.id}",
                throttle_minutes=30,
            )
        except Exception as e:
            logger.error("Support urgent alert failed: %s", redact(e))


async def run_support_bot_background():
    """Long-poll support bot; no-op if BOT_TOKEN_SUPPORT empty.

    Overlapping Railway containers briefly cause TelegramConflictError on
    getUpdates — log quietly and retry instead of crashing the app.
    """
    if not settings.bot_token_support:
        logger.warning("BOT_TOKEN_SUPPORT not set — support bot disabled")
        return

    logger.info("Support bot enabled (token set)")
    while True:
        bot: Bot | None = None
        try:
            bot = Bot(token=settings.bot_token_support)
            dp = Dispatcher(storage=MemoryStorage())
            dp.include_router(support_router)
            logger.info("Support bot starting polling…")
            await dp.start_polling(bot)
        except asyncio.CancelledError:
            logger.info("Support bot stopped.")
            raise
        except TelegramConflictError:
            logger.warning(
                "Support bot getUpdates conflict (overlapping deploy) — retry in 5s"
            )
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("Support bot error: %s — retry in 10s", redact(e))
            await asyncio.sleep(10)
        finally:
            if bot is not None:
                try:
                    await bot.session.close()
                except Exception:
                    pass
