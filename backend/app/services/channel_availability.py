"""Inactive channels (task 15 item 1).

The stats collector records the outcome of every availability check on the lot:
* ok      → last_check_ok_at = now, error + inactive_since cleared;
* failed with a *resolution* error (username not found / channel gone / bot lost access)
          → check_error(+_at) stored, inactive_since set (first failure);
* failed for a transient reason (Telethon down, flood wait, network) → error stored only,
  the lot is NOT marked inactive.
Closed (invite-link) channels and 0-USDT lots inside bundles are never inactive.
Admin "Зняти з біржі" = status removed (soft delete) + audit log; refused while the lot has
an active deal or an auction with bids.
"""
from __future__ import annotations

from sqlalchemy import exists, select

from app.models.auction import Auction
from app.models.bundle import BundleChannel
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealStatus
from app.utils.timeutil import utcnow_naive

RESOLUTION_MARKERS = (
    "chat not found", "no user has", "cannot find any entity", "username not occupied",
    "usernamenotoccupied", "username_not_occupied", "username_invalid", "usernameinvalid",
    "channel_invalid", "channelinvalid", "channel_private", "channelprivate",
    "bot was kicked", "not a member", "member list is inaccessible", "have no rights",
    "not enough rights", "chat_admin_required", "chatadminrequired",
)
LISTED_STATUSES = (ChannelStatus.approved, ChannelStatus.pending)
FINAL_DEAL_STATUSES = (DealStatus.completed, DealStatus.cancelled)
ACTIVE_AUCTION_STATUSES = ("scheduled", "active")


def is_resolution_error(reason: str | None) -> bool:
    r = (reason or "").lower()
    return any(m in r for m in RESOLUTION_MARKERS)


async def is_zero_price_bundle_lot(db, channel: Channel) -> bool:
    if (channel.price or 0) > 0:
        return False
    return bool((await db.execute(select(exists().where(BundleChannel.channel_id == channel.id)))).scalar())


async def record_check(db, channel: Channel, check: dict | None, now=None) -> None:
    """Persist the outcome of one availability check (caller commits)."""
    now = now or utcnow_naive()
    if not check:
        return
    if check.get("ok"):
        channel.last_check_ok_at = now
        channel.check_error = None
        channel.check_error_at = None
        channel.inactive_since = None
        return
    reason = (check.get("reason") or "Канал недоступний")[:300]
    channel.check_error = reason
    channel.check_error_at = now
    if channel.is_closed or not is_resolution_error(reason) or await is_zero_price_bundle_lot(db, channel):
        return
    if channel.inactive_since is None:
        channel.inactive_since = now


async def removal_blockers(db, channel_id: int) -> list[str]:
    out = []
    deal_ids = list((await db.execute(select(Deal.id).where(
        Deal.channel_id == channel_id, Deal.status.notin_(FINAL_DEAL_STATUSES)))).scalars())
    if deal_ids:
        out.append("Активна угода " + ", ".join(f"#{d}" for d in deal_ids) + " — спершу завершіть або скасуйте її")
    auc = (await db.execute(select(Auction.id, Auction.bid_count).where(
        Auction.channel_id == channel_id, Auction.status.in_(ACTIVE_AUCTION_STATUSES),
        Auction.bid_count > 0))).all()
    if auc:
        out.append("Аукціон " + ", ".join(f"#{a} ({b} ставок)" for a, b in auc) + " має ставки — спершу скасуйте аукціон")
    return out


async def list_inactive(db) -> list[dict]:
    rows = (await db.execute(select(Channel).where(
        Channel.status.in_(LISTED_STATUSES), Channel.inactive_since.isnot(None), Channel.is_closed.is_(False),
    ).order_by(Channel.inactive_since))).scalars().all()
    out = []
    for c in rows:
        if await is_zero_price_bundle_lot(db, c):
            continue
        out.append({
            "id": c.id, "channel_name": c.channel_name, "telegram_link": c.telegram_link,
            "status": c.status.value, "price": c.price, "subscribers_count": c.subscribers_count,
            "reason": c.check_error, "check_error_at": _iso(c.check_error_at),
            "inactive_since": _iso(c.inactive_since), "last_check_ok_at": _iso(c.last_check_ok_at),
            "blockers": await removal_blockers(db, c.id),
        })
    return out


def _iso(d):
    return d.isoformat() + "Z" if d else None
