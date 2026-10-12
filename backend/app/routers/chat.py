"""Deal chat v2 API (website). Polling with an ``after_id`` cursor; see app.services.chat."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chat import DealAttachment
from app.models.deal import Deal, DealMessage
from app.models.user import User
import app.services.chat as chat_svc
from app.utils.security import get_current_user_or_blocked
from app.utils.timeutil import utcnow_naive

router = APIRouter(prefix="/deals", tags=["deal-chat"])


class ChatMessageCreate(BaseModel):
    text: str = Field(..., max_length=4000)
    client_id: str | None = Field(None, max_length=64)


class ReadRequest(BaseModel):
    message_id: int = Field(..., ge=0)


@router.get("/my/unread")
async def my_unread(
    ids: str | None = Query(None, max_length=2000, description="staff: comma-separated deal ids"),
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    if ids and chat_svc.is_staff(user):
        try:
            deal_ids = [int(x) for x in ids.split(",") if x.strip()][:200]
        except ValueError:
            raise HTTPException(status_code=400, detail="ids")
    else:
        deal_ids = list((await db.execute(select(Deal.id).where(
            (Deal.buyer_id == user.id) | (Deal.seller_id == user.id)))).scalars())
    counts = await chat_svc.unread_counts(db, user.id, deal_ids)
    return {"unread": {str(k): v for k, v in counts.items()}, "total": sum(counts.values())}


@router.get("/{deal_id}/chat")
async def poll_chat(
    deal_id: int,
    after_id: int = Query(0, ge=0),
    limit: int = Query(chat_svc.PAGE, ge=1, le=200),
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """New messages after ``after_id`` (0 = latest page) + ticks/presence/header/unread."""
    deal = await chat_svc.load_deal_for(db, deal_id, user)
    q = select(DealMessage).where(DealMessage.deal_id == deal_id)
    if after_id:
        rows = (await db.execute(q.where(DealMessage.id > after_id).order_by(DealMessage.id).limit(limit + 1))).scalars().all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        has_older = None
    else:
        rows = (await db.execute(q.order_by(DealMessage.id.desc()).limit(limit + 1))).scalars().all()
        has_older = len(rows) > limit
        rows = list(reversed(rows[:limit]))
        has_more = False
    msgs = await chat_svc.serialize_many(db, deal, rows)
    now = utcnow_naive()
    latest = rows[-1].id if rows else after_id
    if latest:
        await chat_svc.mark_delivered(db, deal_id, user.id, latest)
    await chat_svc.touch_presence(db, deal_id, user.id, now)
    state = await chat_svc.peer_state(db, deal, user, now)
    my = await db.get(chat_svc.DealChatRead, (deal_id, user.id))
    unread = await chat_svc.unread_count(db, deal_id, user.id)
    header = await chat_svc.deal_header(db, deal)
    await db.commit()
    return {
        "messages": msgs, "has_more": has_more, "has_older": has_older, **state,
        "my_last_read_id": my.last_read_message_id if my else 0, "unread": unread,
        "deal": header, "me": {"id": user.id, "role": chat_svc.role_of(deal, user, user.id)},
        "poll_interval_ms": 3000 if header["polling"] else None,
        "server_time": now.isoformat() + "Z",
    }


@router.get("/{deal_id}/chat/history")
async def chat_history(
    deal_id: int,
    before_id: int = Query(..., ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    deal = await chat_svc.load_deal_for(db, deal_id, user)
    rows = (await db.execute(select(DealMessage).where(
        DealMessage.deal_id == deal_id, DealMessage.id < before_id).order_by(DealMessage.id.desc()).limit(limit + 1))).scalars().all()
    has_older = len(rows) > limit
    rows = list(reversed(rows[:limit]))
    return {"messages": await chat_svc.serialize_many(db, deal, rows), "has_older": has_older}


async def _existing_by_client_id(db, deal: Deal, client_id: str | None):
    if not client_id:
        return None
    m = (await db.execute(select(DealMessage).where(
        DealMessage.deal_id == deal.id, DealMessage.client_id == client_id))).scalar_one_or_none()
    return m


@router.post("/{deal_id}/chat/messages", status_code=201)
async def post_chat_message(
    deal_id: int,
    body: ChatMessageCreate,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    deal = await chat_svc.load_deal_for(db, deal_id, user)
    chat_svc.ensure_can_post(user, deal)
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(text) > chat_svc.MAX_TEXT:
        raise HTTPException(status_code=400, detail="Message too long")
    prior = await _existing_by_client_id(db, deal, body.client_id)
    if prior is not None:
        return (await chat_svc.serialize_many(db, deal, [prior]))[0]
    msg = DealMessage(deal_id=deal_id, sender_id=user.id, text=text, kind="text", client_id=body.client_id,
                      tg_forward_status="pending")
    db.add(msg)
    try:
        await db.flush()
    except IntegrityError:  # concurrent retry with the same client_id
        await db.rollback()
        prior = await _existing_by_client_id(db, deal, body.client_id)
        return (await chat_svc.serialize_many(db, deal, [prior]))[0]
    await chat_svc.mark_read(db, deal_id, user.id, msg.id)
    await db.execute(chat_svc.DealChatPresence.__table__.update().where(
        chat_svc.DealChatPresence.deal_id == deal_id, chat_svc.DealChatPresence.user_id == user.id
    ).values(typing_until=None))
    await db.commit()
    await db.refresh(msg)
    return (await chat_svc.serialize_many(db, deal, [msg]))[0]


@router.post("/{deal_id}/chat/read")
async def mark_chat_read(
    deal_id: int,
    body: ReadRequest,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    await chat_svc.load_deal_for(db, deal_id, user)
    mid = await chat_svc.mark_read(db, deal_id, user.id, body.message_id)
    await db.commit()
    return {"last_read_message_id": mid, "unread": await chat_svc.unread_count(db, deal_id, user.id)}


@router.post("/{deal_id}/chat/typing")
async def chat_typing(
    deal_id: int,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    deal = await chat_svc.load_deal_for(db, deal_id, user)
    chat_svc.ensure_can_post(user, deal)
    ok = await chat_svc.set_typing(db, deal_id, user.id)
    await db.commit()
    return {"ok": ok}


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    buf = bytearray()
    while True:
        chunk = await upload.read(256 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(status_code=413, detail=f"Файл завеликий (макс. {limit // 2**20} МБ)")
    return bytes(buf)


@router.post("/{deal_id}/chat/attachments", status_code=201)
async def upload_attachment(
    deal_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(None, max_length=chat_svc.MAX_TEXT),
    client_id: str | None = Form(None, max_length=64),
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    deal = await chat_svc.load_deal_for(db, deal_id, user)
    chat_svc.ensure_can_post(user, deal)
    prior = await _existing_by_client_id(db, deal, client_id)
    if prior is not None:
        return (await chat_svc.serialize_many(db, deal, [prior]))[0]
    data = await _read_limited(file, chat_svc.MAX_FILE_BYTES)
    if not data:
        raise HTTPException(status_code=400, detail="Порожній файл")
    name = chat_svc.safe_filename(file.filename)
    mime = chat_svc.validate_type(name, data)
    width = height = None
    thumb = None
    if mime in chat_svc.IMAGE_MIMES:
        data, width, height, thumb = chat_svc.process_image(data, mime)
    stored = len(data) + len(thumb or b"")
    await chat_svc.check_quotas(db, deal_id, user.id, stored)
    text = (caption or "").strip() or f"📎 {name}"
    msg = DealMessage(deal_id=deal_id, sender_id=user.id, text=text[: chat_svc.MAX_TEXT], kind="file",
                      client_id=client_id, tg_forward_status="pending")
    db.add(msg)
    await db.flush()
    db.add(DealAttachment(deal_id=deal_id, message_id=msg.id, uploader_id=user.id, filename=name, mime=mime,
                          size=stored, sha256=chat_svc.sha256(data), width=width, height=height,
                          data=data, thumb=thumb))
    await chat_svc.mark_read(db, deal_id, user.id, msg.id)
    await db.commit()
    await db.refresh(msg)
    return (await chat_svc.serialize_many(db, deal, [msg]))[0]


@router.get("/{deal_id}/chat/attachments/{attachment_id}")
async def download_attachment(
    deal_id: int,
    attachment_id: int,
    thumb: bool = Query(False),
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    await chat_svc.load_deal_for(db, deal_id, user)
    col = DealAttachment.thumb if thumb else DealAttachment.data
    row = (await db.execute(select(DealAttachment.filename, DealAttachment.mime, col.label("blob")).where(
        DealAttachment.id == attachment_id, DealAttachment.deal_id == deal_id,
        DealAttachment.deleted_at.is_(None)))).one_or_none()
    if row is None or row.blob is None:
        raise HTTPException(status_code=404, detail="Файл не знайдено")
    mime = "image/jpeg" if thumb else row.mime
    inline = mime in chat_svc.IMAGE_MIMES
    from urllib.parse import quote

    fname = quote(row.filename)
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, max-age=3600",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Content-Disposition": f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{fname}",
    }
    return Response(content=bytes(row.blob), media_type=mime, headers=headers)


@router.get("/{deal_id}/tg-notify")
async def tg_notify_state(
    deal_id: int,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Deal page banner: can the alerts bot write to this user? + deep link to start it."""
    import app.services.chat_bridge as bridge

    await chat_svc.load_deal_for(db, deal_id, user)
    return {
        "telegram_bound": bool(user.telegram_id),
        "bot_started": bool(user.tg_bot_started_at),
        "bot_unreachable": bool(user.tg_bot_unreachable_at),
        "deep_link": bridge.deep_link(deal_id),
    }
