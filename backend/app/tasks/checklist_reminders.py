"""Background task: transfer-checklist reminders (6h / 24h to sides, 48h admin alert).

Dedup: reminder_6h_sent_at / reminder_24h_sent_at / admin_alert_48h_sent_at on
deals. Markers are claimed (row lock SKIP LOCKED + commit) BEFORE sending, so
overlapping containers during a deploy cannot double-send. Any checklist
activity (tick / confirm) resets the markers → at most one of each per idle period.
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.deal import Deal
from app.models.user import User
from app.services import deal_checklist as checklist_svc

logger = logging.getLogger(__name__)


async def _send_side_reminder(bot, user: User | None, deal_id: int, side: str, stage: str,
                              plan: checklist_svc.ReminderPlan) -> None:
    from bot.main import notify_checklist_reminder

    label = "reminder 6h" if stage == checklist_svc.STAGE_6H else "reminder 24h"
    if not user or not user.telegram_id:
        logger.info(f"[CHECKLIST] deal #{deal_id} {label} → {side} skipped (no telegram_id)")
        return
    text = checklist_svc.build_reminder_text(
        deal_id, side, stage,
        plan.open_labels.get(side, []),
        plan.needs_confirm.get(side, False),
        settings.frontend_url,
    )
    ok = await notify_checklist_reminder(bot, user.telegram_id, text)
    logger.info(f"[CHECKLIST] deal #{deal_id} {label} → {side}{'' if ok else ' (send failed)'}")


async def check_checklist_reminders_once(now: datetime | None = None) -> int:
    """One pass. Returns number of deals for which reminders were claimed."""
    now = now or datetime.utcnow()
    async with async_session() as db:
        ids = (await db.execute(
            select(Deal.id).where(Deal.status.in_(checklist_svc.TRANSFER_STATUSES))
        )).scalars().all()

    handled = 0
    for deal_id in ids:
        try:
            async with async_session() as db:
                deal = (await db.execute(
                    select(Deal).where(Deal.id == deal_id)
                    .with_for_update(skip_locked=True)
                )).scalar_one_or_none()
                if deal is None or deal.status not in checklist_svc.TRANSFER_STATUSES:
                    await db.rollback()
                    continue
                # Legacy deals (paid before the checklist existed) start their idle
                # timer here, so they are not alerted immediately after deploy.
                items = await checklist_svc.ensure_checklist(db, deal, now)
                plan = checklist_svc.plan_deal_reminders(deal, items, now)
                if plan is None:
                    await db.commit()
                    continue
                checklist_svc.apply_reminder_plan(deal, plan.stages, now)
                buyer = await db.get(User, deal.buyer_id)
                seller = await db.get(User, deal.seller_id)
                await db.commit()  # claim markers BEFORE sending
            handled += 1
            await _deliver(plan, buyer, seller)
        except Exception as e:
            logger.error(f"[CHECKLIST] deal #{deal_id} reminder error: {e}", exc_info=True)
    return handled


async def _deliver(plan: checklist_svc.ReminderPlan, buyer: User | None, seller: User | None) -> None:
    side_stages = [s for s in plan.stages if s in (checklist_svc.STAGE_6H, checklist_svc.STAGE_24H)]
    if side_stages and settings.bot_token_alerts:
        from aiogram import Bot

        bot = Bot(token=settings.bot_token_alerts)
        try:
            for stage in side_stages:
                for side in plan.sides:
                    user = seller if side == checklist_svc.SIDE_SELLER else buyer
                    await _send_side_reminder(bot, user, plan.deal_id, side, stage, plan)
        finally:
            await bot.session.close()
    elif side_stages:
        logger.warning(f"[CHECKLIST] deal #{plan.deal_id} reminders skipped: bot token not configured")

    if checklist_svc.STAGE_ADMIN_48H in plan.stages:
        from app.services.alerts import send_admin_alert

        await send_admin_alert(
            checklist_svc.build_admin_alert_text(plan, settings.frontend_url),
            alert_key=f"checklist_48h_{plan.deal_id}",
            throttle_minutes=60,
        )
        logger.info(
            f"[CHECKLIST] deal #{plan.deal_id} admin alert 48h → admin group "
            f"(waiting: {','.join(plan.sides)})"
        )


async def run_checklist_reminders(interval_minutes: int = 30, initial_delay_sec: int = 600):
    """Periodic loop. Initial delay keeps fresh deploys quiet while old container drains."""
    logger.info(
        f"Checklist reminders started (interval: {interval_minutes}min, first run in {initial_delay_sec}s)"
    )
    try:
        await asyncio.sleep(initial_delay_sec)
    except asyncio.CancelledError:
        return
    while True:
        try:
            n = await check_checklist_reminders_once()
            if n:
                logger.info(f"[CHECKLIST] reminder pass: {n} deal(s) notified")
        except Exception as e:
            logger.error(f"[CHECKLIST] reminder loop error: {e}", exc_info=True)
        await asyncio.sleep(interval_minutes * 60)
