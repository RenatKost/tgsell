"""Honest TgSell lot-view counts for the owner and staff (from user_events).

Counts existing ``channel_view`` events (already 10-minute deduped on insert).
Seller and staff views are excluded when ``user_id`` is known. Anonymous
views are counted. One aggregate query for a batch of lots — no N+1.
Numbers are raw counts; never multiplied.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import UserEvent
from app.models.channel import Channel
from app.models.user import User, UserRole
from app.schemas.channel import ChannelResponse
from app.services.listing_visibility import can_view_unpublished
from app.utils.timeutil import utcnow_naive

SITE_VIEWS_WINDOW = timedelta(days=7)
CHANNEL_VIEW = "channel_view"


async def _staff_ids(db: AsyncSession) -> list[int]:
    rows = (await db.execute(
        select(User.id).where(User.role.in_((UserRole.admin, UserRole.moderator)))
    )).scalars().all()
    return [int(i) for i in rows]


async def counts_for(
    db: AsyncSession,
    channel_ids: list[int],
    *,
    now: datetime | None = None,
) -> dict[int, tuple[int, int]]:
    """Return ``{channel_id: (views_7d, views_total)}`` for the given lots.

    A missing id means zero views. Seller's own and staff views are dropped
    when ``user_id`` is set; ``user_id IS NULL`` events still count.
    """
    ids = [int(i) for i in channel_ids if i is not None]
    if not ids:
        return {}
    now = now or utcnow_naive()
    since = now - SITE_VIEWS_WINDOW
    staff = await _staff_ids(db)

    viewer_ok = or_(
        UserEvent.user_id.is_(None),
        and_(
            UserEvent.user_id != Channel.seller_id,
            *([UserEvent.user_id.notin_(staff)] if staff else []),
        ),
    )
    rows = (await db.execute(
        select(
            UserEvent.object_id,
            func.coalesce(
                func.sum(case((UserEvent.created_at >= since, 1), else_=0)),
                0,
            ).label("views_7d"),
            func.count().label("views_total"),
        )
        .select_from(UserEvent)
        .join(Channel, Channel.id == UserEvent.object_id)
        .where(
            UserEvent.event_type == CHANNEL_VIEW,
            UserEvent.object_id.in_(ids),
            viewer_ok,
        )
        .group_by(UserEvent.object_id)
    )).all()
    out: dict[int, tuple[int, int]] = {}
    for object_id, views_7d, views_total in rows:
        out[int(object_id)] = (int(views_7d or 0), int(views_total or 0))
    return out


def attach_takedown(responses: list[ChannelResponse], allowed: list[Channel]) -> None:
    """Owner/staff only: reason + time a lot was rejected / removed (cabinet shows it)."""
    by_id = {c.id: c for c in allowed}
    for resp in responses:
        c = by_id.get(resp.id)
        if c is None:
            continue
        status = getattr(c.status, "value", c.status)
        if status == "rejected":
            resp.takedown_reason = c.rejection_reason or None
            resp.takedown_at = c.moderated_at
        elif status == "removed":
            resp.takedown_reason = c.removed_reason or None
            resp.takedown_at = c.removed_at


async def attach(
    db: AsyncSession,
    responses: list[ChannelResponse],
    channels: list[Channel],
    viewer,
    *,
    now: datetime | None = None,
) -> list[ChannelResponse]:
    """Fill owner/staff-only data (site-view counts, takedown reason) on responses the viewer may see."""
    allowed = [c for c in channels if can_view_unpublished(viewer, c.seller_id)]
    if not allowed:
        return responses
    attach_takedown(responses, allowed)
    counts = await counts_for(db, [c.id for c in allowed], now=now)
    by_id = {c.id: c for c in allowed}
    for resp in responses:
        if resp.id not in by_id:
            continue
        n7, total = counts.get(resp.id, (0, 0))
        resp.site_views_7d = n7
        resp.site_views_total = total
    return responses


async def attach_one(
    db: AsyncSession,
    response: ChannelResponse,
    channel: Channel,
    viewer,
    *,
    now: datetime | None = None,
) -> ChannelResponse:
    await attach(db, [response], [channel], viewer, now=now)
    return response
