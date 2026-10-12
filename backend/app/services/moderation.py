"""User blocking + admin audit log.

Blocking never touches money: deals of a blocked user are not modified automatically.
* Default: every authenticated action is refused (``get_current_user`` → 403).
* Read-only own-deal endpoints use ``get_current_user_or_blocked``.
* Deal actions (handover checklist, confirmations, seller wallet) are allowed for a
  blocked party only when the admin set ``deal.blocked_party_allowed`` on that deal.
* payout_in_progress is never interrupted (the worker finishes it regardless).
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import exists, select

from app.models.deal import Deal, DealStatus
from app.models.user import AdminAuditLog, User
from app.utils.security import blocked_detail

logger = logging.getLogger(__name__)

ACTIVE_DEAL_STATUSES = (
    DealStatus.created,
    DealStatus.payment_pending,
    DealStatus.paid,
    DealStatus.channel_transferring,
    DealStatus.awaiting_payout,
    DealStatus.payout_in_progress,
    DealStatus.disputed,
)
FUNDED_STATUSES = (
    DealStatus.paid,
    DealStatus.channel_transferring,
    DealStatus.awaiting_payout,
    DealStatus.payout_in_progress,
    DealStatus.disputed,
)


def audit(db, actor, action: str, target_type: str, target_id: int | None, **details) -> None:
    """Add an audit row to the current transaction (committed with the action)."""
    db.add(AdminAuditLog(
        actor_id=getattr(actor, "id", None), action=action, target_type=target_type,
        target_id=target_id, details=details or None,
    ))


def blocked_sellers_subquery():
    return select(User.id).where(User.is_blocked.is_(True))


def not_blocked_seller(column):
    """SQL filter: listing owner is not blocked."""
    return column.notin_(blocked_sellers_subquery())


def ensure_deal_action_allowed(user: User, deal: Deal) -> None:
    """Blocked party may act on a deal only when the admin allowed it for that deal."""
    if getattr(user, "is_blocked", False) and not getattr(deal, "blocked_party_allowed", False):
        raise HTTPException(status_code=403, detail=blocked_detail(user) + " — дії по угоді вимкнено адміністратором")


async def may_login(db, user: User) -> bool:
    """Blocked users may still log in when an active deal of theirs is admin-allowed."""
    if not user.is_blocked:
        return True
    q = select(exists().where(
        Deal.blocked_party_allowed.is_(True),
        Deal.status.in_(ACTIVE_DEAL_STATUSES),
        (Deal.buyer_id == user.id) | (Deal.seller_id == user.id),
    ))
    return bool((await db.execute(q)).scalar())


async def ensure_login_allowed(db, user: User) -> None:
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Акаунт деактивовано")
    if not await may_login(db, user):
        raise HTTPException(status_code=403, detail=blocked_detail(user))


async def active_deals_of(db, user_id: int) -> list[Deal]:
    return list((await db.execute(
        select(Deal).where(
            Deal.status.in_(ACTIVE_DEAL_STATUSES),
            (Deal.buyer_id == user_id) | (Deal.seller_id == user_id),
        ).order_by(Deal.id)
    )).scalars())


def deal_brief(deal: Deal, user_id: int) -> dict:
    return {
        "deal_id": deal.id,
        "role": "buyer" if deal.buyer_id == user_id else "seller",
        "status": deal.status.value,
        "amount_usdt": deal.amount_usdt,
        "escrow": deal.escrow_wallet_address,
        "funded": deal.status in FUNDED_STATUSES,
        "blocked_party_allowed": bool(deal.blocked_party_allowed),
        "needs_admin_decision": deal.status in FUNDED_STATUSES and deal.status != DealStatus.payout_in_progress,
    }
