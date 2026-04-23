"""TgSell Telegram Bot — deal rooms, notifications, inline controls."""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
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
    logger.info(f"[BOT] /start from user {message.from_user.id} (@{message.from_user.username})")
    await message.answer(
        "👋 Вітаю! Я бот TgSell — маркетплейс Telegram-каналів.\n\n"
        "Я допоможу вам із угодами:\n"
        "• Повідомляю про нові угоди\n"
        "• Відслідковую оплату USDT\n"
        "• Контролюю передачу каналів\n\n"
        "🔔 Тепер ви будете отримувати сповіщення про угоди!\n\n"
        "Використовуйте /help для списку команд.",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📌 <b>Команди:</b>\n\n"
        "/start — Привітання\n"
        "/my_deals — Мої активні угоди\n"
        "/deal &lt;id&gt; — Статус угоди\n"
        "/reauth — Оновити Telethon сесію (тільки адмін)\n"
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
    """Notify buyer, seller and admin about a new deal."""
    logger.info(f"[NOTIFY] notify_new_deal called: deal={deal.id}, buyer={buyer.id}(tg={buyer.telegram_id}), seller={seller.id}(tg={seller.telegram_id})")

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
            logger.info(f"[NOTIFY] Buyer {buyer.telegram_id} notified about deal #{deal.id}")
        except Exception as e:
            logger.error(f"[NOTIFY] Failed to notify buyer {buyer.telegram_id}: {e}", exc_info=True)
    else:
        logger.warning(f"[NOTIFY] Buyer {buyer.id} has no telegram_id, skipping notification")

    frontend_url = settings.frontend_url.rstrip("/")

    seller_text = (
        f"🆕 <b>Нова угода!</b>\n\n"
        f"Покупець бажає придбати ваш канал.\n"
        f"💰 Сума: {deal.amount_usdt} USDT\n"
        f"Очікуємо оплату від покупця…\n\n"
        f"<a href='{frontend_url}/deal/{deal.id}'>Перейти до чату угоди →</a>"
    )
    if seller.telegram_id:
        try:
            await bot.send_message(seller.telegram_id, seller_text, parse_mode=ParseMode.HTML)
            logger.info(f"[NOTIFY] Seller {seller.telegram_id} notified about deal #{deal.id}")
        except Exception as e:
            logger.error(f"[NOTIFY] Failed to notify seller {seller.telegram_id}: {e}", exc_info=True)
    else:
        logger.warning(f"[NOTIFY] Seller {seller.id} has no telegram_id, skipping notification")

    # Notify admin group
    if settings.admin_group_id:
        admin_text = (
            f"🆕 <b>Нова угода #{deal.id}</b>\n\n"
            f"Покупець: {buyer.first_name} (id={buyer.id})\n"
            f"Продавець: {seller.first_name} (id={seller.id})\n"
            f"💰 Сума: {deal.amount_usdt} USDT"
        )
        try:
            await bot.send_message(settings.admin_group_id, admin_text, parse_mode=ParseMode.HTML)
            logger.info(f"[NOTIFY] Admin group {settings.admin_group_id} notified about deal #{deal.id}")
        except Exception as e:
            logger.error(f"[NOTIFY] Failed to notify admin: {e}", exc_info=True)


async def notify_payment_received(bot: Bot, deal: Deal, buyer: User, seller: User):
    """Notify that USDT payment arrived."""
    logger.info(f"[NOTIFY] notify_payment_received called: deal={deal.id}")
    text = f"✅ <b>Угода #{deal.id}</b>: оплата {deal.amount_usdt} USDT отримана!\n\n"
    buyer_text = text + "Очікуйте передачу каналу від продавця."
    seller_text = text + "Будь ласка, передайте канал покупцю та очікуйте підтвердження."

    for user, msg in [(buyer, buyer_text), (seller, seller_text)]:
        if user.telegram_id:
            try:
                await bot.send_message(user.telegram_id, msg, parse_mode=ParseMode.HTML)
                logger.info(f"[NOTIFY] User {user.telegram_id} notified about payment for deal #{deal.id}")
            except Exception as e:
                logger.error(f"[NOTIFY] Failed to notify user {user.telegram_id}: {e}", exc_info=True)

    # Notify admin group
    if settings.admin_group_id:
        try:
            admin_text = f"💸 <b>Оплата отримана!</b> Угода #{deal.id} — {deal.amount_usdt} USDT"
            await bot.send_message(settings.admin_group_id, admin_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"[NOTIFY] Failed to notify admin group about payment: {e}")


async def notify_deal_completed(bot: Bot, deal: Deal, buyer: User, seller: User):
    """Notify that deal is completed."""
    logger.info(f"[NOTIFY] notify_deal_completed called: deal={deal.id}")
    text = f"🎉 <b>Угода #{deal.id} завершена!</b>\n\nДякуємо за використання TgSell!"
    for user in [buyer, seller]:
        if user.telegram_id:
            try:
                await bot.send_message(user.telegram_id, text, parse_mode=ParseMode.HTML)
                logger.info(f"[NOTIFY] User {user.telegram_id} notified about deal #{deal.id} completion")
            except Exception as e:
                logger.error(f"[NOTIFY] Failed to notify user {user.telegram_id}: {e}", exc_info=True)

    # Notify admin group
    if settings.admin_group_id:
        try:
            admin_text = f"🎉 <b>Угода #{deal.id} завершена!</b> Сума: {deal.amount_usdt} USDT"
            await bot.send_message(settings.admin_group_id, admin_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"[NOTIFY] Failed to notify admin group about completion: {e}")


async def notify_admin_called(bot: Bot, deal_id: int, channel_name: str, caller_name: str):
    """Notify admin group that they have been called to a deal chat."""
    if not settings.admin_group_id:
        logger.warning(f"[NOTIFY] admin_group_id not set, skipping admin call for deal #{deal_id}")
        return
    frontend_url = settings.frontend_url.rstrip("/")
    text = (
        f"🛡️ <b>Виклик адміністратора!</b>\n\n"
        f"Угода #{deal_id} — {channel_name}\n"
        f"Викликав: {caller_name}\n\n"
        f"<a href='{frontend_url}/deal/{deal_id}'>Перейти до чату угоди →</a>"
    )
    await bot.send_message(settings.admin_group_id, text, parse_mode=ParseMode.HTML)


async def notify_bundle_approved(bot: Bot, bundle, seller: User):
    """Notify seller that their bundle was approved."""
    if not seller or not seller.telegram_id:
        return
    frontend_url = settings.frontend_url.rstrip("/")
    text = (
        f"✅ <b>Вашу сітку схвалено!</b>\n\n"
        f"📡 «{bundle.name}» тепер доступна в каталозі.\n"
        f"💰 Ціна: <b>{bundle.price} USDT</b>\n\n"
        f"<a href='{frontend_url}/bundle/{bundle.id}'>Переглянути сітку →</a>"
    )
    try:
        await bot.send_message(seller.telegram_id, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"[NOTIFY] Cannot notify seller {seller.telegram_id} about bundle approval: {e}")


async def notify_bundle_rejected(bot: Bot, bundle, seller: User):
    """Notify seller that their bundle was rejected."""
    if not seller or not seller.telegram_id:
        return
    reason = bundle.rejection_reason or "Не вказано"
    text = (
        f"❌ <b>Вашу сітку відхилено</b>\n\n"
        f"📡 «{bundle.name}»\n"
        f"Причина: {reason}\n\n"
        f"Виправте помилки та подайте заявку знову."
    )
    try:
        await bot.send_message(seller.telegram_id, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"[NOTIFY] Cannot notify seller {seller.telegram_id} about bundle rejection: {e}")


async def notify_new_bundle_deal(bot: Bot, deal, bundle, buyer: User, seller: User):
    """Notify seller about a new bundle deal."""
    frontend_url = settings.frontend_url.rstrip("/")
    if seller and seller.telegram_id:
        text = (
            f"🎉 <b>Нова угода на вашу сітку!</b>\n\n"
            f"📡 «{bundle.name}»\n"
            f"💰 Сума: <b>{deal.amount_usdt} USDT</b>\n"
            f"👤 Покупець: {buyer.first_name or 'Анонім'}\n\n"
            f"<a href='{frontend_url}/deal/{deal.id}'>Перейти до угоди →</a>"
        )
        try:
            await bot.send_message(seller.telegram_id, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"[NOTIFY] Cannot notify seller about bundle deal: {e}")

    if settings.admin_group_id:
        admin_text = (
            f"📡 <b>Нова угода на сітку</b>\n\n"
            f"Сітка: «{bundle.name}» #{bundle.id}\n"
            f"Угода: #{deal.id}\n"
            f"Покупець: {buyer.first_name or 'Анонім'} (id={buyer.id})\n"
            f"Сума: {deal.amount_usdt} USDT"
        )
        try:
            await bot.send_message(settings.admin_group_id, admin_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"[NOTIFY] Cannot send bundle deal to admin group: {e}")


# ── Telethon re-auth flow (admin only) ───────────────────────────────

class ReauthStates(StatesGroup):
    waiting_code = State()
    waiting_2fa = State()


# In-process store for the temporary Telethon client during re-auth.
# Not serialised — a single admin session is all we need.
_reauth_clients: dict[int, dict] = {}


def _is_admin(user_id: int) -> bool:
    aid = settings.admin_telegram_id
    return bool(aid) and user_id == aid


@router.message(Command("reauth"))
async def cmd_reauth(message: Message, state: FSMContext):
    """Start Telethon re-auth from Telegram — no server access needed.

    Usage (admin only): /reauth
    The bot sends an OTP to the registered phone number; admin replies with
    the code.  If 2FA is enabled the bot asks for the password next.
    After successful sign-in the new session string is saved to DB and the
    in-memory client is reset so the next stats cycle picks it up.
    """
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Тільки адміністратор платформи може виконати цю команду.")
        return

    phone = settings.telegram_phone
    if not phone:
        await message.answer(
            "❌ TELEGRAM_PHONE не задано в .env.\n"
            "Додайте номер телефону облікового запису Telethon (напр.: +380XXXXXXXXX)."
        )
        return

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        await message.answer("❌ TELEGRAM_API_ID або TELEGRAM_API_HASH не задані.")
        return

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(
            StringSession(),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.connect()
        sent = await client.send_code_request(phone)
        _reauth_clients[message.from_user.id] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": sent.phone_code_hash,
        }
        await state.set_state(ReauthStates.waiting_code)
        await message.answer(
            f"📱 Код відправлено на <code>{phone}</code>\n\n"
            "Введіть код з SMS/Telegram (без пробілів):",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await message.answer(f"❌ Помилка при запиті коду: {e}")


@router.message(ReauthStates.waiting_code)
async def process_reauth_code(message: Message, state: FSMContext):
    """Handle OTP code sent by admin."""
    user_id = message.from_user.id
    data = _reauth_clients.get(user_id)
    if not data:
        await state.clear()
        return

    code = message.text.strip()
    try:
        from telethon import TelegramClient

        client: TelegramClient = data["client"]
        await client.sign_in(data["phone"], code, phone_code_hash=data["phone_code_hash"])

        session_string = client.session.save()
        from app.services.channel_stats import _save_session_to_db, reset_telethon_client

        await _save_session_to_db(session_string)
        reset_telethon_client()
        _reauth_clients.pop(user_id, None)
        await state.clear()
        await client.disconnect()
        await message.answer("✅ Telethon сесія успішно оновлена! Аналітика каналів відновлена.")
    except Exception as e:
        err = str(e)
        if "SessionPasswordNeeded" in err:
            await state.set_state(ReauthStates.waiting_2fa)
            await message.answer(
                "🔐 Акаунт захищено двофакторною аутентифікацією.\n"
                "Введіть ваш 2FA пароль:"
            )
        elif "PhoneCode" in err:
            await message.answer("❌ Невірний код. Спробуйте ще раз:")
        else:
            _reauth_clients.pop(user_id, None)
            await state.clear()
            await message.answer(f"❌ Помилка авторизації: {e}")


@router.message(ReauthStates.waiting_2fa)
async def process_reauth_2fa(message: Message, state: FSMContext):
    """Handle 2FA password from admin."""
    user_id = message.from_user.id
    data = _reauth_clients.get(user_id)
    if not data:
        await state.clear()
        return

    password = message.text.strip()
    try:
        from telethon import TelegramClient

        client: TelegramClient = data["client"]
        await client.sign_in(password=password)

        session_string = client.session.save()
        from app.services.channel_stats import _save_session_to_db, reset_telethon_client

        await _save_session_to_db(session_string)
        reset_telethon_client()
        _reauth_clients.pop(user_id, None)
        await state.clear()
        await client.disconnect()
        # Delete message to avoid exposing the password in chat history
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer("✅ Авторизація з 2FA успішна! Telethon сесія оновлена.")
    except Exception as e:
        _reauth_clients.pop(user_id, None)
        await state.clear()
        await message.answer(f"❌ Невірний 2FA пароль: {e}")


# ── Auth bot router (separate bot for login) ─────────────────────────

auth_router = Router()

# Store pending auth tokens per user message (token -> message.from_user.id)
_pending_auth: dict[str, dict] = {}


@auth_router.message(CommandStart())
async def auth_cmd_start(message: Message):
    """Handle /start with auth tokens on the auth bot."""
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("auth_"):
        token = args[1][5:]  # strip "auth_" prefix

        # Store user data for this token
        user = message.from_user
        display_name = user.first_name or "User"
        if user.last_name:
            display_name += f" {user.last_name}"

        _pending_auth[token] = {
            "id": user.id,
            "first_name": user.first_name or "User",
            "username": user.username,
        }

        # Show confirmation like Telemetr
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Увійти в TgSell", callback_data=f"auth_confirm:{token}")],
            [InlineKeyboardButton(text="Скасувати", callback_data=f"auth_cancel:{token}")],
        ])

        await message.answer(
            f'Ви авторизуєтесь в сервісі TgSell під обліковим записом "{display_name}".\n\n'
            f"Для продовження авторизації на сайті натисніть кнопку «Увійти в TgSell».\n\n"
            f"<i>Якщо ви не здійснювали цих дій або потрапили сюди в результаті дій третіх осіб, "
            f'натисніть кнопку «Скасувати».</i>',
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        return

    await message.answer(
        "👋 Вітаю! Я бот авторизації TgSell.\n"
        "Використовуйте кнопку на сайті для входу.",
    )


@auth_router.callback_query(F.data.startswith("auth_confirm:"))
async def auth_confirm_callback(callback: CallbackQuery):
    """User confirmed login — complete the auth token."""
    token = callback.data.split(":", 1)[1]
    user_data = _pending_auth.pop(token, None)

    if not user_data:
        await callback.answer("Сесія закінчилась. Спробуйте ще раз на сайті.", show_alert=True)
        await callback.message.edit_text("❌ Сесія авторизації закінчилась.")
        return

    from app.utils.auth_tokens import complete_auth_token

    if complete_auth_token(token, user_data):
        await callback.message.edit_text(
            "✅ Авторизація успішна! Поверніться на сайт — вхід виконається автоматично."
        )
        await callback.answer()
    else:
        await callback.answer("Посилання вже недійсне. Спробуйте ще раз.", show_alert=True)
        await callback.message.edit_text(
            "❌ Посилання для входу недійсне або вже використане.\n"
            "Спробуйте ще раз на сайті."
        )


@auth_router.callback_query(F.data.startswith("auth_cancel:"))
async def auth_cancel_callback(callback: CallbackQuery):
    """User cancelled login."""
    token = callback.data.split(":", 1)[1]
    _pending_auth.pop(token, None)
    await callback.message.edit_text("🚫 Авторизацію скасовано.")
    await callback.answer()


# ── Bot runner ────────────────────────────────────────────────────────

async def run_bots_background():
    """Start both Telegram bots as a background task (called from FastAPI lifespan)."""
    try:
        alerts_bot = Bot(token=settings.bot_token_alerts)
        alerts_dp = Dispatcher(storage=MemoryStorage())
        alerts_dp.include_router(router)

        auth_bot = Bot(token=settings.bot_token_auth)
        auth_dp = Dispatcher(storage=MemoryStorage())
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
    alerts_dp = Dispatcher(storage=MemoryStorage())
    alerts_dp.include_router(router)

    # Auth bot (login via deep link)
    auth_bot = Bot(token=settings.bot_token_auth)
    auth_dp = Dispatcher(storage=MemoryStorage())
    auth_dp.include_router(auth_router)

    logger.info("Telegram bots starting (alerts + auth)…")
    await asyncio.gather(
        alerts_dp.start_polling(alerts_bot),
        auth_dp.start_polling(auth_bot),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_bot())
