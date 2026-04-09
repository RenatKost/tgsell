"""Utility for sending admin alerts to the Telegram admin group."""
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.enums import ParseMode

from app.config import settings

logger = logging.getLogger(__name__)

# Throttle: don't spam the same alert type more than once per interval
_last_alerts: dict[str, datetime] = {}
_THROTTLE_MINUTES = 30


async def send_admin_alert(text: str, alert_key: str | None = None, throttle_minutes: int = _THROTTLE_MINUTES):
    """Send alert message to admin Telegram group.

    Args:
        text: HTML-formatted alert message
        alert_key: Unique key for throttling (e.g. 'telethon_down'). If None, always sends.
        throttle_minutes: Min interval between same alert_key messages.
    """
    if not settings.bot_token_alerts or not settings.admin_group_id:
        logger.warning(f"[ALERT] Cannot send — bot_token_alerts or admin_group_id not configured")
        return

    # Throttle check
    if alert_key:
        now = datetime.now(timezone.utc)
        last = _last_alerts.get(alert_key)
        if last and (now - last).total_seconds() < throttle_minutes * 60:
            return  # Suppress duplicate
        _last_alerts[alert_key] = now

    try:
        bot = Bot(token=settings.bot_token_alerts)
        await bot.send_message(
            settings.admin_group_id,
            text,
            parse_mode=ParseMode.HTML,
        )
        await bot.session.close()
    except Exception as e:
        logger.error(f"[ALERT] Failed to send admin alert: {e}")


async def alert_service_down(service_name: str, error: str):
    """Alert that a critical service is down."""
    await send_admin_alert(
        f"🔴 <b>{service_name} — НЕ ПРАЦЮЄ</b>\n\n"
        f"<code>{error[:500]}</code>\n\n"
        f"Потрібна увага адміна.",
        alert_key=f"down_{service_name}",
    )


async def alert_service_recovered(service_name: str):
    """Alert that a service has recovered."""
    await send_admin_alert(
        f"🟢 <b>{service_name} — відновлено</b>\n\n"
        f"Сервіс знову працює нормально.",
        alert_key=f"up_{service_name}",
        throttle_minutes=5,
    )


async def alert_stats_summary(total: int, success: int, failed: int, telethon_ok: bool):
    """Post summary after stats collection cycle."""
    if failed == 0 and telethon_ok:
        return  # All good, don't spam

    status = "🟡" if failed > 0 else "🔴"
    if failed == 0:
        status = "🟢"

    lines = [
        f"{status} <b>Збір статистики завершено</b>",
        f"",
        f"Каналів: {total}",
        f"✅ Успішно: {success}",
    ]
    if failed > 0:
        lines.append(f"❌ Помилки: {failed}")
    if not telethon_ok:
        lines.append(f"⚠️ Telethon не працює — немає глибокої аналітики")

    await send_admin_alert(
        "\n".join(lines),
        alert_key="stats_summary",
        throttle_minutes=180,  # Max once per 3 hours
    )
