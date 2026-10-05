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

# Telethon session alert state — one «down» until recovered (no 30‑min wait on first signal)
_telethon_down_alerted: bool = False

# ModerCabinet UI: section title is «Telethon сесія»
_TELETHON_ACTION = "Адмінка → Telethon сесія → повторна авторизація (re-auth)"

_TELETHON_REASON_UA: dict[str, str] = {
    "authkey_duplicated": (
        "AuthKeyDuplicatedError — сесію анульовано (використано з двох IP одночасно). "
        "Повторне підключення не допоможе — потрібен новий логін."
    ),
    "unauthorized": "Сесія не авторизована (протухла або відсутня).",
    "disconnect": "З'єднання обірвано під час роботи (mid-session disconnect).",
    "connect_failed": "Не вдалося підключитися після кількох спроб.",
    "health_check": "Перевірка здоров'я: клієнт відключений або сесія протухла.",
}


async def send_admin_alert(text: str, alert_key: str | None = None, throttle_minutes: int = _THROTTLE_MINUTES):
    """Send alert message to admin Telegram group.

    Args:
        text: HTML-formatted alert message
        alert_key: Unique key for throttling (e.g. 'telethon_down'). If None, always sends.
        throttle_minutes: Min interval between same alert_key messages.
    """
    if not settings.bot_token_alerts or not settings.admin_group_id:
        logger.warning(f"[ALERT] Cannot send — bot_token_alerts or admin_group_id not configured")
        return False

    # Throttle check
    if alert_key:
        now = datetime.now(timezone.utc)
        last = _last_alerts.get(alert_key)
        if last and (now - last).total_seconds() < throttle_minutes * 60:
            return False  # Suppress duplicate
        _last_alerts[alert_key] = now

    try:
        bot = Bot(token=settings.bot_token_alerts)
        await bot.send_message(
            settings.admin_group_id,
            text,
            parse_mode=ParseMode.HTML,
        )
        await bot.session.close()
        return True
    except Exception as e:
        logger.error(f"[ALERT] Failed to send admin alert: {e}")
        return False


async def alert_service_down(service_name: str, error: str):
    """Alert that a critical service is down."""
    import html
    safe_error = html.escape(str(error)[:500])
    await send_admin_alert(
        f"🔴 <b>{service_name} — НЕ ПРАЦЮЄ</b>\n\n"
        f"<code>{safe_error}</code>\n\n"
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


def telethon_down_alerted() -> bool:
    """Whether a Telethon «down» alert is currently outstanding (awaiting recovery)."""
    return _telethon_down_alerted


def reset_telethon_alert_state() -> None:
    """Reset Telethon alert latch (tests / process restart semantics)."""
    global _telethon_down_alerted
    _telethon_down_alerted = False


async def alert_telethon_session_down(reason: str, detail: str = "") -> bool:
    """Event-driven Telethon session death alert (UA). One «down» until recovered.

    First signal sends immediately (no 30‑min throttle). Subsequent downs are
    suppressed until ``alert_telethon_session_recovered`` clears the latch.
    Caller must skip waiting/connecting / startup-delay states.
    """
    global _telethon_down_alerted
    if _telethon_down_alerted:
        return False

    import html

    reason_ua = _TELETHON_REASON_UA.get(reason, reason)
    safe_detail = html.escape(str(detail)[:400]) if detail else ""
    lines = [
        "🔴 <b>Telethon сесія — НЕ ПРАЦЮЄ</b>",
        "",
        f"<b>Причина ({html.escape(reason)}):</b> {html.escape(reason_ua)}",
    ]
    if safe_detail:
        lines.append(f"<code>{safe_detail}</code>")
    lines.extend([
        "",
        f"<b>Дія:</b> {_TELETHON_ACTION}",
    ])
    # No time throttle — state latch is the dedup. alert_key=None → always attempt send.
    sent = await send_admin_alert("\n".join(lines), alert_key=None)
    # Latch even if send failed/unconfigured so we don't spam retries every second
    _telethon_down_alerted = True
    return bool(sent)


async def alert_telethon_session_recovered() -> bool:
    """Send one «🟢 відновлено» after a prior down alert. No-op if never down."""
    global _telethon_down_alerted
    if not _telethon_down_alerted:
        return False

    sent = await send_admin_alert(
        "🟢 <b>Telethon сесія — відновлено</b>\n\n"
        "Клієнт знову підключений і авторизований.",
        alert_key=None,
    )
    _telethon_down_alerted = False
    return bool(sent)


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
