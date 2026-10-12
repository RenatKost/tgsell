"""Deal chat ⇄ Telegram bridge (task 13 stage B).

* Forward: every new user message (text/file) of chat v2 is sent by the alerts bot to
  each OTHER participant with a bound Telegram account, with an inline
  "Відкрити чат на сайті" button and a "✓ Прочитано" button. Runs inside the payout
  worker cycle (PostgreSQL advisory lock ⇒ exactly one sender across instances).
  A link row is committed BEFORE sending (at-most-once: a crash never double-sends).
* Reply: a Telegram reply to a forwarded message is written into the same site chat as
  that user (idempotent via client_id ``tg:<chat>:<msg>``), and marks the chat read.
* Read sync: tapping "✓ Прочитано" marks read on the site; reading on the site removes the
  button in Telegram (message edited to "✓ Прочитано").
* Participants = buyer, seller and staff (admin/moderator) who have written in this chat.
  The Telegram account must be bound to that site user; everyone else is rejected.
"""
from __future__ import annotations

import html
import logging
from types import SimpleNamespace

from sqlalchemy import select, update

from app.config import settings
from app.models.chat import DealChatRead, DealChatTgLink
from app.models.deal import Deal, DealMessage
from app.models.user import User
import app.services.chat as chat_svc
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)


def _h(v) -> str:  # user content: escape everything (no tags allowed)
    return html.escape("" if v is None else str(v), quote=False)

BATCH = 50
READ_SYNC_BATCH = 50
ROLE_UA = {"buyer": "Покупець", "seller": "Продавець", "guarantor": "Гарант"}
READ_CB = "chatread:"


def chat_url(deal_id: int) -> str:
    return f"{settings.frontend_url.rstrip('/')}/deal/{deal_id}#chat"


def keyboard(deal_id: int, link_id: int | None, *, read: bool = False):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [[InlineKeyboardButton(text="Відкрити чат на сайті", url=chat_url(deal_id))]]
    if not read and link_id is not None:
        rows.append([InlineKeyboardButton(text="✓ Прочитано", callback_data=f"{READ_CB}{link_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_forward(deal: Deal, msg: DealMessage, sender: User | None, attachment_name: str | None) -> str:
    role = ROLE_UA.get(chat_svc.role_of(deal, sender, msg.sender_id) or "", "")
    who = _h(sender.first_name if sender else "Користувач") + (f" ({role})" if role else "")
    body = msg.text or ""
    if attachment_name:
        cap = "" if body == f"📎 {attachment_name}" else f"\n{_h(body)}"
        content = f"📎 Файл: <b>{_h(attachment_name)}</b> (відкрийте на сайті){cap}"
    else:
        content = _h(body)
    return (f"💬 <b>Угода #{deal.id}</b> · {who}:\n{content}\n\n"
            f"<i>Відповідайте (Reply) на це повідомлення, щоб написати в чат угоди.</i>")


async def recipients(db, deal: Deal, sender_id: int | None) -> list[User]:
    staff_ids = set((await db.execute(
        select(DealMessage.sender_id).join(User, User.id == DealMessage.sender_id).where(
            DealMessage.deal_id == deal.id, User.role.in_(chat_svc.STAFF_ROLES)).distinct()
    )).scalars())
    ids = ({deal.buyer_id, deal.seller_id} | staff_ids) - {sender_id, None}
    if not ids:
        return []
    users = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return [u for u in users if u.telegram_id and u.is_active and chat_svc.can_view(u, deal)]


async def forward_pending(session_factory, bot) -> int:
    """Forward pending messages. Returns number of Telegram messages sent."""
    from app.models.chat import DealAttachment

    sent = 0
    async with session_factory() as db:
        ids = list((await db.execute(select(DealMessage.id).where(
            DealMessage.tg_forward_status == "pending").order_by(DealMessage.id).limit(BATCH))).scalars())
    for mid in ids:
        async with session_factory() as db:
            msg = (await db.execute(select(DealMessage).where(
                DealMessage.id == mid, DealMessage.tg_forward_status == "pending").with_for_update(skip_locked=True)
            )).scalar_one_or_none()
            if msg is None:
                await db.commit()
                continue
            deal = await db.get(Deal, msg.deal_id)
            sender = await db.get(User, msg.sender_id) if msg.sender_id else None
            att = None
            if msg.kind == "file":
                att = (await db.execute(select(DealAttachment.filename).where(
                    DealAttachment.message_id == msg.id))).scalar()
            text = format_forward(deal, msg, sender, att)
            targets = await recipients(db, deal, msg.sender_id)
            existing = set((await db.execute(select(DealChatTgLink.recipient_user_id).where(
                DealChatTgLink.message_id == msg.id))).scalars())
            plan = []
            for u in targets:
                if u.id in existing:
                    continue
                link = DealChatTgLink(deal_id=deal.id, message_id=msg.id, recipient_user_id=u.id,
                                      tg_chat_id=u.telegram_id)
                db.add(link)
                plan.append(link)
            msg.tg_forward_status = "done"
            await db.flush()
            jobs = [(l.id, l.tg_chat_id, l.recipient_user_id) for l in plan]
            deal_id, msg_id = deal.id, msg.id
            await db.commit()  # links + status persisted BEFORE sending (no double send)
            for link_id, chat_id, uid in jobs:
                try:
                    res = await bot.send_message(chat_id, text, parse_mode="HTML",
                                                 reply_markup=keyboard(deal_id, link_id),
                                                 disable_web_page_preview=True)
                    await db.execute(update(DealChatTgLink).where(DealChatTgLink.id == link_id)
                                     .values(tg_message_id=res.message_id))
                    await db.commit()
                    sent += 1
                except Exception as e:
                    await db.rollback()
                    logger.warning(f"[CHAT-TG] deal #{deal_id} msg #{msg_id} → user #{uid}: {e}")
    return sent


async def sync_reads_to_telegram(session_factory, bot) -> int:
    """Message read on the site → edit Telegram copy (drop the "Прочитано" button)."""
    done = 0
    async with session_factory() as db:
        rows = (await db.execute(
            select(DealChatTgLink).join(DealChatRead, (DealChatRead.deal_id == DealChatTgLink.deal_id)
                                        & (DealChatRead.user_id == DealChatTgLink.recipient_user_id))
            .where(DealChatTgLink.read_synced_at.is_(None), DealChatTgLink.tg_message_id.isnot(None),
                   DealChatRead.last_read_message_id >= DealChatTgLink.message_id)
            .order_by(DealChatTgLink.id).limit(READ_SYNC_BATCH)
        )).scalars().all()
        jobs = [SimpleNamespace(id=l.id, deal_id=l.deal_id, tg_chat_id=l.tg_chat_id, tg_message_id=l.tg_message_id)
                for l in rows]
        for link in rows:
            link.read_synced_at = utcnow_naive()
        await db.commit()
        for link in jobs:
            try:
                await bot.edit_message_reply_markup(chat_id=link.tg_chat_id, message_id=link.tg_message_id,
                                                    reply_markup=keyboard(link.deal_id, link.id, read=True))
                done += 1
            except Exception as e:  # message too old / unchanged / blocked bot
                logger.info(f"[CHAT-TG] read-sync link #{link.id}: {e}")
    return done


# ── Telegram → site ─────────────────────────────────────────────────────

class BridgeReject(Exception):
    def __init__(self, text: str):
        super().__init__(text)
        self.text = text


async def _link_and_user(db, tg_user_id: int, tg_chat_id: int, tg_message_id: int):
    link = (await db.execute(select(DealChatTgLink).where(
        DealChatTgLink.tg_chat_id == tg_chat_id, DealChatTgLink.tg_message_id == tg_message_id))).scalar_one_or_none()
    if link is None:
        return None, None, None
    user = (await db.execute(select(User).where(User.telegram_id == tg_user_id))).scalar_one_or_none()
    if user is None:
        raise BridgeReject("Ваш Telegram не привʼязаний до акаунта TgSell. Увійдіть на сайті через Telegram.")
    if user.id != link.recipient_user_id or not user.is_active:
        raise BridgeReject("Це повідомлення адресоване іншому користувачу.")
    deal = await db.get(Deal, link.deal_id)
    if deal is None or not chat_svc.can_view(user, deal):
        raise BridgeReject("Немає доступу до чату цієї угоди.")
    return link, user, deal


async def handle_reply(db, *, tg_user_id: int, tg_chat_id: int, reply_to_message_id: int,
                       tg_message_id: int, text: str | None) -> DealMessage | None:
    """Write a Telegram reply into the site chat. Returns the message, None if not a bridge reply."""
    link, user, deal = await _link_and_user(db, tg_user_id, tg_chat_id, reply_to_message_id)
    if link is None:
        return None
    try:
        chat_svc.ensure_can_post(user, deal)
    except Exception as e:
        raise BridgeReject(f"Надсилання недоступне: {getattr(e, 'detail', e)}")
    text = (text or "").strip()
    if not text:
        raise BridgeReject("Через бот можна надсилати лише текст. Файли — на сайті.")
    if len(text) > chat_svc.MAX_TEXT:
        raise BridgeReject(f"Повідомлення задовге (макс. {chat_svc.MAX_TEXT} символів).")
    client_id = f"tg:{tg_chat_id}:{tg_message_id}"
    prior = (await db.execute(select(DealMessage).where(
        DealMessage.deal_id == deal.id, DealMessage.client_id == client_id))).scalar_one_or_none()
    if prior is not None:
        return prior
    msg = DealMessage(deal_id=deal.id, sender_id=user.id, text=text, kind="text", client_id=client_id,
                      tg_forward_status="pending", meta={"via": "telegram"})
    db.add(msg)
    await db.flush()
    await chat_svc.mark_read(db, deal.id, user.id, msg.id)
    await db.execute(update(DealChatTgLink).where(
        DealChatTgLink.deal_id == deal.id, DealChatTgLink.recipient_user_id == user.id,
        DealChatTgLink.message_id <= msg.id, DealChatTgLink.read_synced_at.is_(None),
    ).values(read_synced_at=utcnow_naive()))
    await db.commit()
    return msg


async def handle_read_tap(db, *, tg_user_id: int, link_id: int) -> DealChatTgLink:
    link = await db.get(DealChatTgLink, link_id)
    if link is None or link.tg_message_id is None:
        raise BridgeReject("Повідомлення не знайдено.")
    link, user, deal = await _link_and_user(db, tg_user_id, link.tg_chat_id, link.tg_message_id)
    await chat_svc.mark_read(db, deal.id, user.id, link.message_id)
    await chat_svc.touch_presence(db, deal.id, user.id)
    link.read_synced_at = utcnow_naive()
    out = SimpleNamespace(id=link.id, deal_id=link.deal_id, tg_chat_id=link.tg_chat_id, tg_message_id=link.tg_message_id)
    await db.commit()
    return out


_bot = None


def get_bot():
    global _bot
    if _bot is None and settings.bot_token_alerts:
        from aiogram import Bot

        _bot = Bot(token=settings.bot_token_alerts)
    return _bot


async def bridge_cycle(session_factory) -> dict:
    bot = get_bot()
    if bot is None:
        return {"sent": 0, "read_synced": 0}
    return {"sent": await forward_pending(session_factory, bot),
            "read_synced": await sync_reads_to_telegram(session_factory, bot)}
