"""Background task: weekly admin report (Mondays 09:00 Europe/Chisinau → admin group).

Idempotent across restarts and overlapping containers: the ISO-week key is claimed in
``scheduled_report_runs`` (primary key) and committed BEFORE sending, so the report
goes out at most once per week. A failed send is retried on later ticks (up to
weekly_stats.MAX_ATTEMPTS) within the same Monday catch-up window.
"""
import asyncio
import logging
from datetime import datetime

from app.database import async_session
from app.services.weekly_stats import (
    build_weekly_report_text,
    claim_weekly_report,
    collect_weekly_stats,
    finish_weekly_report,
    week_due,
)
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)


async def send_weekly_report_once(now: datetime | None = None) -> bool:
    """One tick. Returns True if a report was sent in this call."""
    from app.services.alerts import send_admin_alert

    now = now or utcnow_naive()
    due = week_due(now)
    if due is None:
        return False
    key, _ = due
    async with async_session() as db:
        if not await claim_weekly_report(db, key):
            return False
    async with async_session() as db:
        stats = await collect_weekly_stats(db, now)
    ok = bool(await send_admin_alert(build_weekly_report_text(stats), alert_key=None))
    async with async_session() as db:
        await finish_weekly_report(db, key, ok)
    logger.info(f"[WEEKLY] report {key} {'sent' if ok else 'send failed'}")
    return ok


async def run_weekly_report(interval_seconds: int = 300, initial_delay_sec: int = 300):
    """Periodic loop; initial delay keeps fresh deploys quiet while old container drains."""
    logger.info(f"Weekly report scheduler started (tick: {interval_seconds}s, first in {initial_delay_sec}s)")
    try:
        await asyncio.sleep(initial_delay_sec)
    except asyncio.CancelledError:
        return
    while True:
        try:
            await send_weekly_report_once()
        except Exception as e:
            logger.error(f"[WEEKLY] report loop error: {e}", exc_info=True)
        await asyncio.sleep(interval_seconds)
