"""Background task: monitor system health and send admin alerts."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.config import settings
from app.database import async_session
from app.models.channel import Channel, ChannelStats, ChannelStatus
from app.services.alerts import send_admin_alert, alert_service_down, alert_service_recovered

logger = logging.getLogger(__name__)

_prev_telethon_ok: bool | None = None
_prev_bot_api_ok: bool | None = None


async def _check_telethon():
    """Check if Telethon is alive and authorized."""
    global _prev_telethon_ok
    try:
        from app.services.channel_stats import _get_telethon_client
        client = await _get_telethon_client()
        ok = client is not None and client.is_connected()
        if ok:
            ok = await client.is_user_authorized()
    except Exception:
        ok = False

    if _prev_telethon_ok is not None and ok != _prev_telethon_ok:
        if ok:
            await alert_service_recovered("Telethon (аналітика каналів)")
        else:
            await alert_service_down(
                "Telethon (аналітика каналів)",
                "Клієнт відключений або сесія протухла"
            )
    _prev_telethon_ok = ok
    return ok


async def _check_bot_api():
    """Check if Bot API stats token works."""
    global _prev_bot_api_ok
    if not settings.bot_token_stats:
        return False

    ok = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(
                f"https://api.telegram.org/bot{settings.bot_token_stats}/getMe"
            )
            ok = resp.status_code == 200
    except Exception:
        ok = False

    if _prev_bot_api_ok is not None and ok != _prev_bot_api_ok:
        if ok:
            await alert_service_recovered("Bot API Stats")
        else:
            await alert_service_down("Bot API Stats", "getMe повернув помилку або таймаут")
    _prev_bot_api_ok = ok
    return ok


async def _check_stale_stats():
    """Check if any approved channels have no stats at all or very old stats."""
    async with async_session() as db:
        # Count approved channels with zero stats records
        subq = (
            select(ChannelStats.channel_id)
            .group_by(ChannelStats.channel_id)
        ).subquery()

        result = await db.execute(
            select(func.count()).select_from(Channel).where(
                Channel.status == ChannelStatus.approved,
                Channel.id.notin_(select(subq.c.channel_id)),
            )
        )
        no_stats = result.scalar() or 0

        # Total approved
        total_result = await db.execute(
            select(func.count()).select_from(Channel).where(
                Channel.status == ChannelStatus.approved
            )
        )
        total = total_result.scalar() or 0

        return total, no_stats


async def _check_db():
    """Quick DB connectivity check."""
    try:
        async with async_session() as db:
            await db.execute(select(func.count()).select_from(Channel))
        return True
    except Exception:
        return False


async def health_check_once():
    """Run all health checks and send summary if problems found."""
    telethon_ok = await _check_telethon()
    bot_api_ok = await _check_bot_api()
    db_ok = await _check_db()

    problems = []
    if not telethon_ok:
        problems.append("❌ Telethon не працює — немає аналітики")
    if not bot_api_ok:
        problems.append("⚠️ Bot API Stats — токен невалідний")
    if not db_ok:
        problems.append("🔴 БД недоступна!")

    if db_ok:
        total, no_stats = await _check_stale_stats()
        if no_stats > 0:
            problems.append(f"📊 {no_stats}/{total} каналів без статистики")

    if problems:
        await send_admin_alert(
            "🔍 <b>Перевірка здоров'я системи</b>\n\n" + "\n".join(problems),
            alert_key="health_check",
            throttle_minutes=360,  # Max once per 6 hours
        )

    logger.info(
        f"[HEALTH] telethon={'✓' if telethon_ok else '✗'} "
        f"bot_api={'✓' if bot_api_ok else '✗'} "
        f"db={'✓' if db_ok else '✗'}"
    )


async def run_health_monitor(interval_minutes: int = 30):
    """Run health monitor loop."""
    logger.info(f"Health monitor started (interval: {interval_minutes}min)")
    # Initial delay — let services start up
    await asyncio.sleep(60)
    while True:
        try:
            await health_check_once()
        except Exception as e:
            logger.error(f"Health check error: {e}")
        await asyncio.sleep(interval_minutes * 60)
