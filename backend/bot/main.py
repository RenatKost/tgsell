"""TgSell Telegram Bot — deal rooms, notifications, inline controls."""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session
from app.models.deal import Deal, DealStatus
from app.models.user import User

logger = logging.getLogger(__name__)

router = Router()

DEAL_STATUS_LABELS = {
    DealStatus.created: "⏳ Створено — очікування оплати",
    DealStatus.payment_pending: "💸 Часткова оплата",
    DealStatus.paid: "✅ Оплачено — передайте канал",
    DealStatus.channel_transferring: "🔄 Передача каналу",
    DealStatus.completed: "🎉 Завершено",
    DealStatus.disputed: "⚠️ Спір відкрито",
    DealStatus.cancelled: "❌ Скасовано",
}


def deal_keyboard(deal_id: int, user_role: str) -> InlineKeyboardMarkup:
    """Generate inline keyboard based on deal context."""
    buttons = [
        [InlineKeyboardButton(text="📊 Статус угоди", callback_data=f"deal_status:{deal_id}")],
    ]
    if user_role == "buyer":
        buttons.append([
            InlineKeyboardButton(text="✅ Підтвердити отримання", callback_data=f"deal_confirm:{deal_id}"),
            InlineKeyboardButton(text="⚠️ Відкрити спір", callback_data=f"deal_dispute:{deal_id}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Commands ──────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Вітаю! Я бот TgSell — маркетплейс Telegram-каналів.\n\n"
        "Я допоможу вам із угодами:\n"
        "• Повідомляю про нові угоди\n"
        "• Відслідковую оплату USDT\n"
        "• Контролюю передачу каналів\n\n"
        "Використовуйте /help для списку команд.",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📌 <b>Команди:</b>\n\n"
        "/start — Привітання\n"
        "/my_deals — Мої активні угоди\n"
        "/deal &lt;id&gt; — Статус угоди\n"
        "/help — Ця довідка",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("my_deals"))
async def cmd_my_deals(message: Message):
    tg_id = message.from_user.id
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if not user:
            await message.answer("Ви не зареєстровані на платформі. Авторизуйтесь через сайт.")
            return

        result = await db.execute(
            select(Deal)
            .options(selectinload(Deal.channel))
            .where(
                ((Deal.buyer_id == user.id) | (Deal.seller_id == user.id))
                & Deal.status.notin_([DealStatus.completed, DealStatus.cancelled])
            )
        )
        deals = result.scalars().all()

    if not deals:
        await message.answer("У вас немає активних угод.")
        return

    lines = ["<b>📋 Ваші активні угоди:</b>\n"]
    for d in deals:
        role = "покупець" if d.buyer_id == user.id else "продавець"
        channel_name = d.channel.channel_name if d.channel else "—"
        status_label = DEAL_STATUS_LABELS.get(d.status, d.status.value)
        lines.append(f"• <b>#{d.id}</b> {channel_name} ({role})\n  {status_label}")

    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("deal"))
async def cmd_deal_status(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Використання: /deal <id>")
        return

    deal_id = int(parts[1])
    tg_id = message.from_user.id

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if not user:
            await message.answer("Ви не зареєстровані на платформі.")
            return

        deal = (
            await db.execute(
                select(Deal).options(selectinload(Deal.channel)).where(Deal.id == deal_id)
            )
        ).scalar_one_or_none()

        if not deal or (deal.buyer_id != user.id and deal.seller_id != user.id):
            await message.answer("Угоду не знайдено або у вас немає доступу.")
            return

    role = "buyer" if deal.buyer_id == user.id else "seller"
    channel_name = deal.channel.channel_name if deal.channel else "—"
    status_label = DEAL_STATUS_LABELS.get(deal.status, deal.status.value)

    text = (
        f"<b>Угода #{deal.id}</b>\n\n"
        f"📺 Канал: {channel_name}\n"
        f"💰 Сума: {deal.amount_usdt} USDT\n"
        f"📊 Статус: {status_label}\n"
    )

    if role == "buyer" and deal.status in (DealStatus.created, DealStatus.payment_pending):
        text += f"\n💳 Адреса для оплати:\n<code>{deal.escrow_wallet_address}</code>\n"
        text += f"Мережа: TRON (TRC-20 USDT)\n"

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=deal_keyboard(deal.id, role))


# ── Callbacks ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("deal_status:"))
async def cb_deal_status(callback: CallbackQuery):
    deal_id = int(callback.data.split(":")[1])
    tg_id = callback.from_user.id

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if not user:
            await callback.answer("Ви не зареєстровані.", show_alert=True)
            return

        deal = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
        if not deal or (deal.buyer_id != user.id and deal.seller_id != user.id):
            await callback.answer("Немає доступу.", show_alert=True)
            return

    status_label = DEAL_STATUS_LABELS.get(deal.status, deal.status.value)
    await callback.answer(status_label, show_alert=True)


@router.callback_query(F.data.startswith("deal_confirm:"))
async def cb_deal_confirm(callback: CallbackQuery):
    deal_id = int(callback.data.split(":")[1])
    tg_id = callback.from_user.id

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if not user:
            await callback.answer("Ви не зареєстровані.", show_alert=True)
            return

        deal = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
        if not deal or deal.buyer_id != user.id:
            await callback.answer("Тільки покупець може підтвердити.", show_alert=True)
            return

        if deal.status != DealStatus.paid:
            await callback.answer("Угоду неможливо підтвердити в поточному статусі.", show_alert=True)
            return

        deal.status = DealStatus.completed
        from datetime import datetime, timezone
        deal.completed_at = datetime.now(timezone.utc)
        await db.commit()

    await callback.message.answer(f"🎉 Угода #{deal_id} завершена! Кошти будуть переведені продавцю.")
    await callback.answer()
    # TODO: Trigger USDT release to seller via escrow service


@router.callback_query(F.data.startswith("deal_dispute:"))
async def cb_deal_dispute(callback: CallbackQuery):
    deal_id = int(callback.data.split(":")[1])
    tg_id = callback.from_user.id

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if not user:
            await callback.answer("Ви не зареєстровані.", show_alert=True)
            return

        deal = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
        if not deal or deal.buyer_id != user.id:
            await callback.answer("Тільки покупець може відкрити спір.", show_alert=True)
            return

        if deal.status not in (DealStatus.paid, DealStatus.channel_transferring):
            await callback.answer("Спір неможливо відкрити в поточному статусі.", show_alert=True)
            return

        deal.status = DealStatus.disputed
        await db.commit()

    await callback.message.answer(
        f"⚠️ Спір по угоді #{deal_id} відкрито. Модератор розгляне ситуацію."
    )
    await callback.answer()


# ── Notification helpers (called from backend services) ───────────────

async def notify_new_deal(bot: Bot, deal: Deal, buyer: User, seller: User):
    """Notify buyer and seller about a new deal."""
    text = (
        f"🆕 <b>Нова угода #{deal.id}</b>\n\n"
        f"💰 Сума: {deal.amount_usdt} USDT\n"
        f"💳 Адреса для оплати:\n<code>{deal.escrow_wallet_address}</code>\n"
        f"Мережа: TRON (TRC-20 USDT)\n\n"
        f"⏱ Час на оплату: {settings.payment_timeout_hours} год."
    )
    if buyer.telegram_id:
        try:
            await bot.send_message(buyer.telegram_id, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to notify buyer {buyer.telegram_id}: {e}")

    seller_text = (
        f"🆕 <b>Нова угода #{deal.id}</b>\n\n"
        f"Покупець бажає придбати ваш канал.\n"
        f"💰 Сума: {deal.amount_usdt} USDT\n"
        f"Очікуємо оплату від покупця…"
    )
    if seller.telegram_id:
        try:
            await bot.send_message(seller.telegram_id, seller_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to notify seller {seller.telegram_id}: {e}")


async def notify_payment_received(bot: Bot, deal: Deal, buyer: User, seller: User):
    """Notify that USDT payment arrived."""
    text = f"✅ <b>Угода #{deal.id}</b>: оплата {deal.amount_usdt} USDT отримана!\n\n"
    buyer_text = text + "Очікуйте передачу каналу від продавця."
    seller_text = text + "Будь ласка, передайте канал покупцю та очікуйте підтвердження."

    for user, msg in [(buyer, buyer_text), (seller, seller_text)]:
        if user.telegram_id:
            try:
                await bot.send_message(user.telegram_id, msg, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Failed to notify user {user.telegram_id}: {e}")


async def notify_deal_completed(bot: Bot, deal: Deal, buyer: User, seller: User):
    """Notify that deal is completed."""
    text = f"🎉 <b>Угода #{deal.id} завершена!</b>\n\nДякуємо за використання TgSell!"
    for user in [buyer, seller]:
        if user.telegram_id:
            try:
                await bot.send_message(user.telegram_id, text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Failed to notify user {user.telegram_id}: {e}")


# ── Auth bot router (separate bot for login) ─────────────────────────

auth_router = Router()


@auth_router.message(CommandStart())
async def auth_cmd_start(message: Message):
    """Handle /start with auth tokens on the auth bot."""
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("auth_"):
        token = args[1][5:]  # strip "auth_" prefix
        from app.utils.auth_tokens import complete_auth_token

        user_data = {
            "id": message.from_user.id,
            "first_name": message.from_user.first_name or "User",
            "username": message.from_user.username,
        }
        if complete_auth_token(token, user_data):
            await message.answer(
                "✅ Авторизація успішна! Поверніться на сайт — вхід виконається автоматично.",
            )
        else:
            await message.answer(
                "❌ Посилання для входу недійсне або вже використане.\n"
                "Спробуйте ще раз на сайті.",
            )
        return

    await message.answer(
        "👋 Вітаю! Я бот авторизації TgSell.\n"
        "Використовуйте кнопку на сайті для входу.",
    )


# ── Bot runner ────────────────────────────────────────────────────────

async def run_bots_background():
    """Start both Telegram bots as a background task (called from FastAPI lifespan)."""
    try:
        alerts_bot = Bot(token=settings.bot_token_alerts)
        alerts_dp = Dispatcher()
        alerts_dp.include_router(router)

        auth_bot = Bot(token=settings.bot_token_auth)
        auth_dp = Dispatcher()
        auth_dp.include_router(auth_router)

        logger.info("Telegram bots starting (alerts + auth)…")
        await asyncio.gather(
            alerts_dp.start_polling(alerts_bot),
            auth_dp.start_polling(auth_bot),
        )
    except asyncio.CancelledError:
        logger.info("Telegram bots stopped.")
    except Exception as e:
        logger.error(f"Telegram bots error: {e}")


async def start_bot():
    """Start both Telegram bots (standalone entry point)."""
    # Alerts bot (deals, notifications)
    alerts_bot = Bot(token=settings.bot_token_alerts)
    alerts_dp = Dispatcher()
    alerts_dp.include_router(router)

    # Auth bot (login via deep link)
    auth_bot = Bot(token=settings.bot_token_auth)
    auth_dp = Dispatcher()
    auth_dp.include_router(auth_router)

    logger.info("Telegram bots starting (alerts + auth)…")
    await asyncio.gather(
        alerts_dp.start_polling(alerts_bot),
        auth_dp.start_polling(auth_bot),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_bot())
