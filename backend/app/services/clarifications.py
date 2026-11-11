"""Moderator «Запитати уточнення» / seller reply on the same lot."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.channel import (
    Channel,
    ChannelClarification,
    ChannelStatus,
    MODERATION_STATUSES,
)
from app.models.user import User
from app.schemas.channel import ChannelResponse, ClarificationItem
from app.services.listing_visibility import can_view_unpublished
from app.services.moderation import audit
from app.utils.timeutil import utcnow_naive

QUESTION_MIN = 5
QUESTION_MAX = 2000
ANSWER_MAX = 2000


def _clean_question(text: str) -> str:
    q = (text or "").strip()
    if len(q) < QUESTION_MIN:
        raise HTTPException(status_code=400, detail="Вкажіть питання для продавця (мінімум 5 символів)")
    if len(q) > QUESTION_MAX:
        raise HTTPException(status_code=400, detail=f"Питання занадто довге (макс. {QUESTION_MAX} символів)")
    return q


def _clean_answer(text: str | None) -> str | None:
    if text is None:
        return None
    a = text.strip()
    if len(a) > ANSWER_MAX:
        raise HTTPException(status_code=400, detail=f"Відповідь занадто довга (макс. {ANSWER_MAX} символів)")
    return a or None


def to_item(row: ChannelClarification) -> ClarificationItem:
    asked_name = None
    if row.asked_by is not None:
        asked_name = row.asked_by.first_name or row.asked_by.username
    return ClarificationItem(
        id=row.id,
        question=row.question,
        asked_at=row.asked_at,
        asked_by_id=row.asked_by_id,
        asked_by_name=asked_name,
        answer=row.answer,
        answered_at=row.answered_at,
        answered_by_id=row.answered_by_id,
    )


async def list_for(db: AsyncSession, channel_ids: list[int]) -> dict[int, list[ClarificationItem]]:
    if not channel_ids:
        return {}
    rows = (await db.execute(
        select(ChannelClarification)
        .options(selectinload(ChannelClarification.asked_by))
        .where(ChannelClarification.channel_id.in_(channel_ids))
        .order_by(ChannelClarification.id.asc())
    )).scalars().all()
    out: dict[int, list[ClarificationItem]] = {cid: [] for cid in channel_ids}
    for row in rows:
        out.setdefault(row.channel_id, []).append(to_item(row))
    return out


async def attach(db: AsyncSession, responses: list[ChannelResponse], channels: list[Channel], viewer) -> list[ChannelResponse]:
    """Fill clarifications on responses the viewer is allowed to see (owner or staff)."""
    allowed = [c.id for c in channels if can_view_unpublished(viewer, c.seller_id)]
    if not allowed:
        return responses
    by_id = await list_for(db, allowed)
    ch_by_id = {c.id: c for c in channels}
    for r in responses:
        ch = ch_by_id.get(r.id)
        if ch is not None and can_view_unpublished(viewer, ch.seller_id):
            r.clarifications = by_id.get(r.id, [])
    return responses


async def attach_one(db: AsyncSession, response: ChannelResponse, channel: Channel, viewer) -> ChannelResponse:
    await attach(db, [response], [channel], viewer)
    return response


async def ask(db: AsyncSession, channel: Channel, staff: User, question: str) -> ChannelClarification:
    if channel.status not in MODERATION_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Лот у статусі {channel.status.value} — уточнення можна запитати лише під час модерації",
        )
    q = _clean_question(question)
    now = utcnow_naive()
    row = ChannelClarification(
        channel_id=channel.id, question=q, asked_by_id=staff.id, asked_at=now,
    )
    db.add(row)
    prev = channel.status.value
    channel.status = ChannelStatus.needs_clarification
    channel.moderator_id = staff.id
    channel.moderated_at = now
    audit(db, staff, "channel.clarify", "channel", channel.id, prev_status=prev, question=q)
    return row


async def reply(db: AsyncSession, channel: Channel, seller: User, answer: str | None) -> None:
    if channel.seller_id != seller.id:
        raise HTTPException(status_code=403, detail="Це не ваш лот")
    if channel.status != ChannelStatus.needs_clarification:
        raise HTTPException(status_code=400, detail="Зараз модератор не чекає уточнення по цьому лоту")
    text = _clean_answer(answer)
    now = utcnow_naive()
    open_rows = list((await db.execute(
        select(ChannelClarification)
        .where(ChannelClarification.channel_id == channel.id, ChannelClarification.answered_at.is_(None))
        .order_by(ChannelClarification.id.asc())
        .with_for_update()
    )).scalars())
    if open_rows:
        # Comment is stored on the latest unanswered question; all open ones are closed.
        open_rows[-1].answer = text
        for row in open_rows:
            row.answered_at = now
            row.answered_by_id = seller.id
    channel.status = ChannelStatus.pending
    audit(db, seller, "channel.clarify_reply", "channel", channel.id, answer=text)
