"""Task 32: editing a bundle's per-channel seller-stated balances after creation.

Rules (enforced here, server-side):
- seller (owner) may edit only while the bundle has NO active deal (and is not sold);
- admins / moderators may always edit (admin panel), every edit is audited;
- edits only touch channels.stars_balance / channels.ton_balance — never
  deals.balance_* (those are creation-time snapshots of existing deals).
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import selectinload

from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
from app.models.deal import Deal
from app.services.moderation import ACTIVE_DEAL_STATUSES

STAFF_ROLES = ("admin", "moderator")


def _role(user) -> str:
    r = getattr(user, "role", None)
    return getattr(r, "value", r) or ""


def is_staff(user) -> bool:
    return _role(user) in STAFF_ROLES


async def load_bundle(db, bundle_id: int, *, for_update: bool = False) -> ChannelBundle:
    q = (
        select(ChannelBundle)
        .options(selectinload(ChannelBundle.bundle_channels).selectinload(BundleChannel.channel))
        .where(ChannelBundle.id == bundle_id)
    )
    if for_update:
        q = q.with_for_update(of=ChannelBundle)
    bundle = (await db.execute(q)).scalar_one_or_none()
    if bundle is None:
        raise HTTPException(status_code=404, detail="Сітку не знайдено")
    return bundle


async def has_active_deal(db, bundle: ChannelBundle) -> bool:
    """Active deal on the bundle itself or on any of its channels sold separately."""
    channel_ids = [bc.channel_id for bc in (bundle.bundle_channels or [])]
    cond = Deal.bundle_id == bundle.id
    if channel_ids:
        cond = or_(cond, Deal.channel_id.in_(channel_ids))
    q = select(exists().where(cond, Deal.status.in_(ACTIVE_DEAL_STATUSES)))
    return bool((await db.execute(q)).scalar())


async def ensure_seller_may_edit(db, bundle: ChannelBundle, user) -> None:
    if bundle.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Це не ваша сітка")
    if bundle.status == BundleStatus.sold:
        raise HTTPException(status_code=400, detail="Сітку продано — баланс змінити неможливо")
    if await has_active_deal(db, bundle):
        raise HTTPException(
            status_code=409,
            detail="По сітці є активна угода — змінити баланс неможливо. Зверніться до модератора.",
        )


def apply_balances(bundle: ChannelBundle, balances) -> list[dict]:
    """Validate ownership of every channel first, then write. Returns change log."""
    by_id = {bc.channel_id: bc.channel for bc in (bundle.bundle_channels or []) if bc.channel is not None}
    for bal in balances:
        if bal.channel_id not in by_id:
            raise HTTPException(status_code=400, detail="Канал не належить до цієї сітки")
    changes = []
    for bal in balances:
        ch = by_id[bal.channel_id]
        before = (ch.stars_balance, ch.ton_balance)
        ch.stars_balance = bal.stars_balance
        ch.ton_balance = bal.ton_balance
        after = (ch.stars_balance, ch.ton_balance)
        if before != after:
            changes.append({"channel_id": ch.id, "before": list(before), "after": list(after)})
    return changes


async def load_bundle_for_update(db, bundle_id: int) -> ChannelBundle:
    return await load_bundle(db, bundle_id, for_update=True)
