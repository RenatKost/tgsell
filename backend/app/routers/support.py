"""Support queue API for the Support TgSell agent."""
from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.support import (
    DELIVERY_FAILED,
    DELIVERY_SENDING,
    DELIVERY_SENT,
    SupportMessage,
)
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


IDEMPOTENCY_KEY_MAX_LEN = 128


class SupportReplyBody(BaseModel):
    telegram_user_id: int
    text: str = Field(..., min_length=1, max_length=MAX_SUPPORT_TEXT_LEN)
    reply_to_id: int | None = None
    # Optional, recommended: makes retries safe (same key → Telegram send at most once
    # per successful delivery). Can also be passed as the `Idempotency-Key` header.
    idempotency_key: str | None = Field(default=None, max_length=IDEMPOTENCY_KEY_MAX_LEN)


class SupportHandledBody(BaseModel):
    ids: list[int] = Field(..., min_length=1)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _serialize(row: SupportMessage) -> dict:
    return {
        "id": row.id,
        "telegram_user_id": row.telegram_user_id,
        "username": row.username,
        "first_name": row.first_name,
        "chat_id": row.chat_id,
        "direction": row.direction,
        "text": row.text,
        "created_at": _iso(row.created_at),
        "is_urgent": row.is_urgent,
        "handled": row.handled,
        "handled_at": _iso(row.handled_at),
        "reply_to_id": row.reply_to_id,
        "delivery_status": row.delivery_status,
        "idempotency_key": row.idempotency_key,
        "sent_at": _iso(row.sent_at),
        "telegram_message_id": row.telegram_message_id,
        "send_attempts": row.send_attempts,
        "last_error": row.last_error,
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


def _resolve_idempotency_key(body_key: str | None, header_key: str | None) -> str | None:
    body_key = (body_key or "").strip() or None
    header_key = (header_key or "").strip() or None
    if body_key and header_key and body_key != header_key:
        raise HTTPException(
            status_code=400, detail="idempotency_key in body and Idempotency-Key header differ"
        )
    key = body_key or header_key
    if key is not None and len(key) > IDEMPOTENCY_KEY_MAX_LEN:
        raise HTTPException(status_code=400, detail="Idempotency key too long")
    return key


async def _get_by_key(db: AsyncSession, key: str) -> SupportMessage | None:
    return (
        await db.execute(select(SupportMessage).where(SupportMessage.idempotency_key == key))
    ).scalar_one_or_none()


def _error(status_code: int, detail: str, error: str, row: SupportMessage | None = None) -> JSONResponse:
    content = {"ok": False, "detail": detail, "error": error}
    if row is not None:
        content["status"] = row.delivery_status
        content["message"] = _serialize(row)
    return JSONResponse(status_code=status_code, content=content)


def _ok(row: SupportMessage, *, duplicate: bool) -> dict:
    return {"ok": True, "duplicate": duplicate, "status": row.delivery_status, "message": _serialize(row)}


async def _deliver(db: AsyncSession, row: SupportMessage):
    """Row is already committed as 'sending'. Send once, then mark 'sent' / 'failed'."""
    try:
        from aiogram import Bot

        bot = Bot(token=settings.bot_token_support)
        try:
            sent = await bot.send_message(row.chat_id, row.text)
        finally:
            await bot.session.close()
    except Exception as e:
        err = redact(e)
        logger.error("Support reply send failed (message #%s): %s", row.id, err)
        await db.execute(
            update(SupportMessage)
            .where(SupportMessage.id == row.id)
            .values(delivery_status=DELIVERY_FAILED, last_error=(err or "")[:1000])
        )
        await db.commit()
        await db.refresh(row)
        # `detail` string kept identical to the pre-idempotency API.
        return _error(502, "Failed to send Telegram message", "telegram_send_failed", row)

    now = utcnow_naive()
    await db.execute(
        update(SupportMessage)
        .where(SupportMessage.id == row.id)
        .values(
            delivery_status=DELIVERY_SENT,
            sent_at=now,
            telegram_message_id=getattr(sent, "message_id", None),
            last_error=None,
            handled=True,
            handled_at=now,
        )
    )
    # Mark related incoming as handled (specific id or all unhandled from user)
    if row.reply_to_id is not None:
        await db.execute(
            update(SupportMessage)
            .where(SupportMessage.id == row.reply_to_id, SupportMessage.direction == "in")
            .values(handled=True, handled_at=now)
        )
    await db.execute(
        update(SupportMessage)
        .where(
            SupportMessage.telegram_user_id == row.telegram_user_id,
            SupportMessage.direction == "in",
            SupportMessage.handled.is_(False),
        )
        .values(handled=True, handled_at=now)
    )
    await db.commit()
    await db.refresh(row)
    return _ok(row, duplicate=False)


async def _handle_existing(db: AsyncSession, row: SupportMessage, body: SupportReplyBody, text: str):
    """A reply with this idempotency key already exists — never send blindly twice."""
    if (
        row.telegram_user_id != body.telegram_user_id
        or (row.text or "") != text
        or row.reply_to_id != body.reply_to_id
    ):
        return _error(
            422,
            "Idempotency key was already used for a different reply",
            "idempotency_key_reused",
            row,
        )

    if row.delivery_status == DELIVERY_SENT:
        return _ok(row, duplicate=True)

    if row.delivery_status == DELIVERY_FAILED:
        # Explicit retry after a failed send: atomically claim failed → sending, so
        # concurrent retries cannot both resend.
        claimed = await db.execute(
            update(SupportMessage)
            .where(SupportMessage.id == row.id, SupportMessage.delivery_status == DELIVERY_FAILED)
            .values(
                delivery_status=DELIVERY_SENDING,
                send_attempts=SupportMessage.send_attempts + 1,
                last_error=None,
            )
        )
        await db.commit()
        await db.refresh(row)
        if claimed.rowcount == 1:
            return await _deliver(db, row)
        if row.delivery_status == DELIVERY_SENT:
            return _ok(row, duplicate=True)

    # 'sending': another request is delivering it right now, or the process died between
    # the Telegram call and the 'sent' commit. We cannot know whether the user got it,
    # so we do NOT resend automatically.
    return _error(
        409,
        "Reply with this idempotency key is already being sent (or its delivery state is "
        "unknown); not resending to avoid a duplicate",
        "reply_in_progress",
        row,
    )


@router.post("/reply")
async def support_reply(
    body: SupportReplyBody,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    _: None = Depends(require_support_secret),
    db: AsyncSession = Depends(get_db),
):
    """Send a support reply to the user in Telegram.

    Order: persist the outgoing row as 'sending' (commit) → send to Telegram →
    mark 'sent' (commit) or 'failed' (commit).

    Idempotency (``idempotency_key`` body field or ``Idempotency-Key`` header):
      * 200 ``{"ok": true, "duplicate": false, "status": "sent", "message": {...}}`` — sent now;
      * 200 ``{"ok": true, "duplicate": true, ...}`` — already sent earlier, nothing resent;
      * 409 ``error=reply_in_progress`` — same key is 'sending' (in flight or crashed
        mid-send); not resent. Check the chat manually; use a NEW key to send again;
      * 422 ``error=idempotency_key_reused`` — key used for a different user/text/reply_to_id;
      * 502 ``error=telegram_send_failed``, ``status=failed`` — Telegram send failed; retrying
        with the SAME key resends once.
    Without a key the call works as before (row still persisted before sending), but a
    client retry cannot be de-duplicated.
    """
    if not settings.bot_token_support:
        raise HTTPException(status_code=503, detail="Support bot not configured")

    text = body.text.strip()
    if not text or len(text) > MAX_SUPPORT_TEXT_LEN:
        raise HTTPException(status_code=400, detail="Invalid text")

    key = _resolve_idempotency_key(body.idempotency_key, idempotency_key_header)

    if key is not None:
        existing = await _get_by_key(db, key)
        if existing is not None:
            return await _handle_existing(db, existing, body, text)

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

    if body.reply_to_id is not None:
        target = (
            await db.execute(
                select(SupportMessage).where(SupportMessage.id == body.reply_to_id)
            )
        ).scalar_one_or_none()
        if not target or target.telegram_user_id != body.telegram_user_id:
            raise HTTPException(status_code=404, detail="reply_to_id not found for user")

    row = SupportMessage(
        telegram_user_id=body.telegram_user_id,
        username=last.username,
        first_name=last.first_name,
        chat_id=last.chat_id,
        direction="out",
        text=text,
        is_urgent=False,
        handled=True,
        handled_at=utcnow_naive(),
        reply_to_id=body.reply_to_id,
        delivery_status=DELIVERY_SENDING,
        idempotency_key=key,
        send_attempts=1,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent request with the same idempotency key won the insert.
        await db.rollback()
        existing = await _get_by_key(db, key) if key is not None else None
        if existing is None:
            raise
        return await _handle_existing(db, existing, body, text)
    await db.refresh(row)
    return await _deliver(db, row)


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
