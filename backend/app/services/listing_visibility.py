"""Task 33: who may see a listing (channel / bundle).

Published lots (approved, sold) are public. Unpublished ones (pending, rejected,
removed) exist only for their owner and staff (admin/moderator); everyone else
gets a plain 404 so neither the lot nor the seller's contacts leak.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel, ChannelStatus

PUBLIC_CHANNEL_STATUSES = (ChannelStatus.approved, ChannelStatus.sold)
PUBLIC_BUNDLE_STATUSES = ("approved", "sold")


def _val(x):
    return getattr(x, "value", x)


def _viewer(user):
    """Only a user-like object counts (direct calls may pass FastAPI's Depends placeholder)."""
    return user if (hasattr(user, "id") and hasattr(user, "role")) else None


def is_staff(user) -> bool:
    user = _viewer(user)
    return user is not None and _val(user.role) in ("admin", "moderator")


def can_view_unpublished(user, seller_id) -> bool:
    user = _viewer(user)
    return is_staff(user) or (user is not None and seller_id is not None and user.id == seller_id)


def channel_is_public(channel) -> bool:
    return _val(channel.status) in {s.value for s in PUBLIC_CHANNEL_STATUSES}


def bundle_is_public(bundle) -> bool:
    return _val(bundle.status) in PUBLIC_BUNDLE_STATUSES


async def visible_channel_or_404(db: AsyncSession, channel_id: int, viewer) -> Channel:
    from app.services.moderation import not_blocked_seller
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if can_view_unpublished(viewer, channel.seller_id):
        return channel
    if not channel_is_public(channel):
        raise HTTPException(status_code=404, detail="Channel not found")
    ok = (await db.execute(
        select(Channel.id).where(Channel.id == channel_id).where(not_blocked_seller(Channel.seller_id))
    )).scalar_one_or_none()
    if ok is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


def ensure_bundle_visible(bundle, viewer) -> None:
    if bundle is None:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle_is_public(bundle) or can_view_unpublished(viewer, bundle.seller_id):
        return
    raise HTTPException(status_code=404, detail="Bundle not found")
