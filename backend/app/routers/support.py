"""Support queue API for the Support TgSell agent."""
from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.support import SupportMessage
from app.services.support_logic import MAX_SUPPORT_TEXT_LEN
from app.utils.log_redact import redact
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])


def require_support_secret(
    x_support_secret: str | None = Header(default=None, alias="x-support-secret"),
) -> None:
    expected = settings.support_queue_secret or ""
    if not expected:
        raise HTTPException(status_code=503, detail="Support queue not configured")
    provided = x_support_secret or ""
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


class SupportReplyBody(BaseModel):
    telegram_user_id: int
    text: str = Field(..., min_length=1, max_length=MAX_SUPPORT_TEXT_LEN)
    reply_to_id: int | None = None


class SupportHandledBody(BaseModel):
    ids: list[int] = Field(..., min_length=1)


def _serialize(row: SupportMessage) -> dict:
    return {
        "id": row.id,
        "telegram_user_id": row.telegram_user_id,
        "username": row.username,
        "first_name": row.first_name,
        "chat_id": row.chat_id,
        "direction": row.direction,
        "text": row.text,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "is_urgent": row.is_urgent,
        "handled": row.handled,
        "handled_at": row.handled_at.isoformat() if row.handled_at else None,
        "reply_to_id": row.reply_to_id,
    }


@router.get("/queue")
async def support_queue(
    only_unhandled: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    since_id: int | None = Query(default=None),
    _: None = Depends(require_support_secret),
    db: AsyncSession = Depends(get_db),
):
    q = select(SupportMessage).order_by(SupportMessage.id.asc())
    if only_unhandled:
        q = q.where(SupportMessage.handled.is_(False))
    if since_id is not None:
        q = q.where(SupportMessage.id > since_id)
    q = q.limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return {"messages": [_serialize(r) for r in rows]}


@router.post("/reply")
async def support_reply(
    body: SupportReplyBody,
    _: None = Depends(require_support_secret),
    db: AsyncSession = Depends(get_db),
):
    if not settings.bot_token_support:
        raise HTTPException(status_code=503, detail="Support bot not configured")

    text = body.text.strip()
    if not text or len(text) > MAX_SUPPORT_TEXT_LEN:
        raise HTTPException(status_code=400, detail="Invalid text")

    # Resolve chat_id from last inbound (or any) message for this user
    result = await db.execute(
        select(SupportMessage)
        .where(SupportMessage.telegram_user_id == body.telegram_user_id)
        .order_by(SupportMessage.id.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if not last:
        raise HTTPException(status_code=404, detail="No prior messages from this user")
    chat_id = last.chat_id

    if body.reply_to_id is not None:
        target = (
            await db.execute(
                select(SupportMessage).where(SupportMessage.id == body.reply_to_id)
            )
        ).scalar_one_or_none()
        if not target or target.telegram_user_id != body.telegram_user_id:
            raise HTTPException(status_code=404, detail="reply_to_id not found for user")

    try:
        from aiogram import Bot

        bot = Bot(token=settings.bot_token_support)
        try:
            await bot.send_message(chat_id, text)
        finally:
            await bot.session.close()
    except Exception as e:
        logger.error("Support reply send failed: %s", redact(e))
        raise HTTPException(status_code=502, detail="Failed to send Telegram message") from e

    now = utcnow_naive()  # handled_at is naive TIMESTAMP (UTC)
    out = SupportMessage(
        telegram_user_id=body.telegram_user_id,
        username=last.username,
        first_name=last.first_name,
        chat_id=chat_id,
        direction="out",
        text=text,
        is_urgent=False,
        handled=True,
        handled_at=now,
        reply_to_id=body.reply_to_id,
    )
    db.add(out)

    # Mark related incoming as handled (specific id or all unhandled from user)
    if body.reply_to_id is not None:
        await db.execute(
            update(SupportMessage)
            .where(
                SupportMessage.id == body.reply_to_id,
                SupportMessage.direction == "in",
            )
            .values(handled=True, handled_at=now)
        )
    await db.execute(
        update(SupportMessage)
        .where(
            SupportMessage.telegram_user_id == body.telegram_user_id,
            SupportMessage.direction == "in",
            SupportMessage.handled.is_(False),
        )
        .values(handled=True, handled_at=now)
    )
    await db.commit()
    await db.refresh(out)
    return {"ok": True, "message": _serialize(out)}


@router.post("/handled")
async def support_mark_handled(
    body: SupportHandledBody,
    _: None = Depends(require_support_secret),
    db: AsyncSession = Depends(get_db),
):
    now = utcnow_naive()  # handled_at is naive TIMESTAMP (UTC)
    result = await db.execute(
        update(SupportMessage)
        .where(SupportMessage.id.in_(body.ids))
        .values(handled=True, handled_at=now)
    )
    await db.commit()
    return {"ok": True, "updated": result.rowcount or 0}
