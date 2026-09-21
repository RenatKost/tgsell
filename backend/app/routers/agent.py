"""Inbound endpoint for autonomous agent run reports.

An agent's cloud routine (see automation/agents/*.md) never holds the
Telegram bot token itself — it calls this endpoint with a shared secret,
and the backend relays the summary into the admin Telegram group via the
existing bot/main.py notification plumbing. Also writes an AdminAction
audit row so agent activity shows up in the same trail as human admin
actions.
"""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.audit import log_admin_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/report")
async def agent_report(
    secret: str = Body(...),
    role: str = Body(...),
    summary: str = Body(...),
    links: list[str] = Body(default=[]),
    db: AsyncSession = Depends(get_db),
):
    """Relay an autonomous agent's run summary to the admin Telegram group.

    Requires AGENT_REPORT_SECRET to be set — with no secret configured this
    endpoint stays disabled (403) rather than silently accepting anything.
    """
    if not settings.agent_report_secret or secret != settings.agent_report_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid agent secret")

    await log_admin_action(db, f"agent:{role}", "agent.report", payload={"summary": summary[:2000], "links": links})

    try:
        from bot.main import notify_agent_report
        from aiogram import Bot

        bot = Bot(token=settings.bot_token_alerts)
        await notify_agent_report(bot, role, summary, links)
        await bot.session.close()
    except Exception as e:
        logger.error(f"[AGENT] Failed to relay report for role={role}: {e}")
        raise HTTPException(status_code=502, detail="Report logged but Telegram delivery failed")

    return {"ok": True}
