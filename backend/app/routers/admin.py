import asyncio
import logging
from datetime import datetime, timedelta, timezone
import os

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.utils.avatars import public_channel_avatar_url
from app.models.auction import Auction, AuctionBid
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealStatus, Transaction, TransactionStatus, TransactionType
from app.models.user import User, UserRole
from app.schemas.bundle import BundleBalancesUpdate
from app.schemas.channel import ChannelResponse, ChannelUpdate
from app.schemas.deal import DealResolveRequest, DealResponse
from app.services.moderation import audit
from app.utils.security import get_admin_user, get_superadmin_user
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/setup")
async def initial_admin_setup(
    telegram_id: int,
    secret: str,
    db: AsyncSession = Depends(get_db),
):
    """One-time admin setup. Requires ADMIN_SETUP_SECRET env var."""
    setup_secret = os.getenv("ADMIN_SETUP_SECRET", "")
    if not setup_secret or secret != setup_secret:
        raise HTTPException(status_code=403, detail="Invalid setup secret")

    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Login via Telegram first.")

    prev_role = user.role.value
    user.role = UserRole.admin
    audit(db, None, "admin.setup", "user", user.id, prev_role=prev_role, telegram_id=telegram_id)
    await db.commit()
    await db.refresh(user)

    return {"ok": True, "user_id": user.id, "username": user.username, "role": user.role.value}


def _bundle_member_exists():
    """Correlated EXISTS: the channel is a member of some bundle (moderated via the bundle)."""
    from app.models.bundle import BundleChannel
    return select(BundleChannel.id).where(BundleChannel.channel_id == Channel.id).exists()


async def _channel_bundle_id(db: AsyncSession, channel_id: int):
    from app.models.bundle import BundleChannel
    return (await db.execute(
        select(BundleChannel.bundle_id).where(BundleChannel.channel_id == channel_id).limit(1)
    )).scalar_one_or_none()


BUNDLE_MEMBER_DETAIL = "Канал входить до сітки — модеруйте сітку цілком (вкладка «На модерації»)."


@router.get("/channels/pending", response_model=list[ChannelResponse])
async def get_pending_channels(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all channels awaiting moderation."""
    result = await db.execute(
        select(Channel)
        .where(Channel.status == ChannelStatus.pending, ~_bundle_member_exists())
        .order_by(Channel.created_at.asc())
    )
    channels = result.scalars().all()
    from app.services.pricing import high_views_flag
    out = []
    for c in channels:
        r = ChannelResponse.model_validate(c)
        flag = high_views_flag(category=c.category, subscribers=c.subscribers_count, avg_views=c.avg_views,
                               is_closed=bool(c.is_closed), views_hidden=bool(c.views_hidden),
                               last_post_date=c.last_post_date)
        r.moderation_flags = [flag] if flag else []
        out.append(r)
    return out


@router.post("/channels/{channel_id}/approve", response_model=ChannelResponse)
async def approve_channel(
    channel_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a channel listing."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status != ChannelStatus.pending:
        raise HTTPException(status_code=400, detail="Channel is not pending")
    if await _channel_bundle_id(db, channel_id) is not None:
        raise HTTPException(status_code=400, detail=BUNDLE_MEMBER_DETAIL)

    try:
        channel.status = ChannelStatus.approved
        channel.moderator_id = admin.id
        channel.moderated_at = datetime.utcnow()
        audit(db, admin, "channel.approve", "channel", channel.id)
        await db.commit()
        await db.refresh(channel)

        # Refresh stats from Telegram on approve
        try:
            from app.services.channel_stats import collect_channel_stats
            from app.models.channel import ChannelStats

            stats = await collect_channel_stats(channel.telegram_link)
            if stats.get("subscribers_count"):
                channel.subscribers_count = stats["subscribers_count"]
            if stats.get("avg_views"):
                channel.avg_views = stats["avg_views"]
            if stats.get("er"):
                channel.er = stats["er"]
            if stats.get("avatar_url"):
                channel.avatar_url = stats["avatar_url"]
            if stats.get("channel_name"):
                channel.channel_name = stats["channel_name"]
            if stats.get("adv_reach_12h"):
                channel.adv_reach_12h = stats["adv_reach_12h"]
            if stats.get("adv_reach_24h"):
                channel.adv_reach_24h = stats["adv_reach_24h"]
            if stats.get("adv_reach_48h"):
                channel.adv_reach_48h = stats["adv_reach_48h"]
            if stats.get("channel_age_months"):
                channel.age = f"{stats['channel_age_months']}"

            # Save historical daily stats for graphs (honest series, Task 20)
            from app.services.stats_history import record_stats

            await record_stats(db, channel.id, stats)
            await db.commit()
            await db.refresh(channel)
        except Exception as e:
            logger.warning(f"Stats refresh on approve failed for channel #{channel_id}: {e}")

        # Auto-create auction if listing_type is 'auction' or 'both'
        if channel.listing_type in ("auction", "both") and channel.auction_start_price:
            try:
                from app.models.auction import Auction
                auction = Auction(
                    channel_id=channel.id,
                    seller_id=channel.seller_id,
                    start_price=channel.auction_start_price,
                    bid_step=channel.auction_bid_step or 10.0,
                    current_price=channel.auction_start_price,
                    buyout_price=None,
                    status="active",
                    starts_at=datetime.utcnow(),
                    ends_at=datetime.utcnow() + timedelta(hours=channel.auction_duration_hours or 48),
                )
                db.add(auction)
                await db.commit()
                await db.refresh(channel)
                logger.info(f"Auction auto-created for channel #{channel.id}")
            except Exception as e:
                logger.error(f"Failed to auto-create auction for channel #{channel_id}: {e}")

        # Task 24: queue saved-search matches (sent grouped by the notifier, max 1/h per search)
        try:
            from app.services.saved_searches import enqueue_matches_for_channel
            await enqueue_matches_for_channel(db, channel.id)
        except Exception as e:
            logger.warning(f"Saved-search matching failed for channel #{channel_id}: {type(e).__name__}")
            await db.rollback()
            await db.refresh(channel)

        return ChannelResponse.model_validate(channel)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approve channel #{channel_id} failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Помилка підтвердження: {e}")


@router.post("/channels/{channel_id}/reject", response_model=ChannelResponse)
async def reject_channel(
    channel_id: int,
    reason: str = Body("", embed=True),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a channel listing."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status != ChannelStatus.pending:
        raise HTTPException(status_code=400, detail="Channel is not pending")
    if await _channel_bundle_id(db, channel_id) is not None:
        raise HTTPException(status_code=400, detail=BUNDLE_MEMBER_DETAIL)

    try:
        channel.status = ChannelStatus.rejected
        channel.moderator_id = admin.id
        channel.moderated_at = datetime.utcnow()
        channel.rejection_reason = reason
        audit(db, admin, "channel.reject", "channel", channel.id, reason=reason)
        await db.commit()
        await db.refresh(channel)
        return ChannelResponse.model_validate(channel)
    except Exception as e:
        logger.error(f"Reject channel #{channel_id} failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Помилка відхилення: {e}")


@router.get("/deals", response_model=list[DealResponse])
async def get_all_deals(
    deal_status: str | None = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all deals (admin only). Optional status filter."""
    query = (
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .order_by(Deal.created_at.desc())
    )
    if deal_status:
        query = query.where(Deal.status == deal_status)
    result = await db.execute(query)
    deals = result.scalars().all()

    responses = []
    for d in deals:
        responses.append(DealResponse(
            id=d.id, channel_id=d.channel_id, buyer_id=d.buyer_id, seller_id=d.seller_id,
            channel_name=d.channel.channel_name if d.channel else None,
            buyer_name=d.buyer.first_name if d.buyer else None,
            seller_name=d.seller.first_name if d.seller else None,
            status=d.status.value, escrow_wallet_address=d.escrow_wallet_address,
            amount_usdt=d.amount_usdt, service_fee=d.service_fee,
            deal_group_chat_id=d.deal_group_chat_id, dispute_reason=d.dispute_reason,
            balance_stars=d.balance_stars, balance_ton=d.balance_ton,
            created_at=d.created_at, paid_at=d.paid_at, completed_at=d.completed_at,
        ))
    return responses


async def _load_deal_full(db: AsyncSession, deal_id: int) -> Deal:
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def _admin_deal_response(deal: Deal) -> DealResponse:
    return DealResponse(
        id=deal.id, channel_id=deal.channel_id, buyer_id=deal.buyer_id, seller_id=deal.seller_id,
        channel_name=deal.channel.channel_name if deal.channel else None,
        buyer_name=deal.buyer.first_name if deal.buyer else None,
        seller_name=deal.seller.first_name if deal.seller else None,
        status=deal.status.value, escrow_wallet_address=deal.escrow_wallet_address,
        amount_usdt=deal.amount_usdt, service_fee=deal.service_fee,
        deal_group_chat_id=deal.deal_group_chat_id, dispute_reason=deal.dispute_reason,
        balance_stars=deal.balance_stars, balance_ton=deal.balance_ton,
        created_at=deal.created_at, paid_at=deal.paid_at, completed_at=deal.completed_at,
        seller_payout_address=deal.seller_payout_address,
        payout_tx_hash=deal.payout_tx_hash,
    )


def _resolve_wallet(preferred: str | None, user_wallet: str | None, override: str | None) -> str | None:
    """First non-empty candidate; real validation is payouts.validate_destination."""
    for candidate in (override, preferred, user_wallet):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return None


async def _precheck_gas_or_http(db: AsyncSession, deal: Deal, wallet: str, units: int, **kw) -> None:
    """Master TRX must cover gas BEFORE claim; otherwise rollback (no claim) + 503."""
    from app.services import payouts

    try:
        await payouts.precheck_gas(deal, wallet, units, **kw)
    except payouts.PayoutError as e:
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.message)


@router.post("/deals/{deal_id}/resolve", response_model=DealResponse)
async def resolve_deal(
    deal_id: int,
    body: DealResolveRequest,
    response: Response,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a disputed deal: on-chain refund to buyer or release to seller.

    Money-safety: FOR UPDATE claim → payout_in_progress + commit BEFORE broadcast;
    the job row is enqueued in the same commit; the payout worker executes it (202).
    """
    from app.services import payouts
    from app.services.deal_lifecycle import PayoutClaimError, has_payout_tx

    if body.resolution not in ("refund_buyer", "release_seller"):
        raise HTTPException(status_code=400, detail="Invalid resolution")

    # 1) Lock row
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
        .with_for_update()
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # 2) Idempotency: already resolved with an on-chain tx — do not send again.
    if has_payout_tx(deal) or deal.status in (DealStatus.completed, DealStatus.cancelled):
        await db.commit()
        return _admin_deal_response(deal)

    # 3) Validate wallet / amount BEFORE claim (still under row lock).
    if body.resolution == "refund_buyer":
        wallet = _resolve_wallet(None, deal.buyer.usdt_wallet if deal.buyer else None, body.wallet_address)
        if not wallet:
            await db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Немає адреси гаманця покупця для refund. Вкажіть wallet_address або збережіть usdt_wallet у профілі покупця.",
            )
        units = payouts.refund_units(deal)
        tx_type = TransactionType.refund
    else:  # release_seller
        wallet = _resolve_wallet(
            deal.seller_payout_address, deal.seller.usdt_wallet if deal.seller else None, body.wallet_address
        )
        if not wallet:
            await db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Немає адреси гаманця продавця для release. Вкажіть wallet_address, seller_payout_address або usdt_wallet продавця.",
            )
        units = payouts.release_units(deal)
        tx_type = TransactionType.release
    if units <= 0:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Некоректна сума виплати")
    try:
        wallet = await payouts.validate_destination(db, wallet)
    except payouts.PayoutError as e:
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.message)

    await _precheck_gas_or_http(db, deal, wallet, units)

    # 4) Claim (disputed → payout_in_progress) + enqueue job in ONE commit.
    try:
        await payouts.claim_for_payout(db, deal, expected_status=DealStatus.disputed)
    except PayoutClaimError as e:
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.message)
    payouts.enqueue_transfer(
        db, deal, tx_type=tx_type, to_address=wallet, amount_units=units,
        restore_status=DealStatus.disputed,
    )
    audit(db, admin, "deal.resolve", "deal", deal.id, resolution=body.resolution,
          to_address=wallet, amount_units=units)
    await db.commit()  # claim + job visible — second double-click gets 409
    logger.info(f"[ADMIN] Deal #{deal.id}: CLAIMED + queued {body.resolution}")
    response.status_code = 202
    return _admin_deal_response(await _load_deal_full(db, deal_id))


# Statuses where USDT is (or may be) sitting in escrow after payment
_FUNDED_DEAL_STATUSES = (
    DealStatus.paid,
    DealStatus.channel_transferring,
    DealStatus.awaiting_payout,
    DealStatus.payout_in_progress,
    DealStatus.disputed,
)


@router.post("/deals/{deal_id}/cancel", response_model=DealResponse)
async def admin_cancel_deal(
    deal_id: int,
    response: Response,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin cancel a deal. Paid/escrowed deals require on-chain refund (or refuse).

    Locked + claimed like resolve: payout_in_progress / unresolved tx → 409.
    """
    from app.services import payouts
    from app.services.deal_lifecycle import PayoutClaimError, has_payout_tx

    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
        .with_for_update()
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.status in (DealStatus.completed, DealStatus.cancelled):
        await db.rollback()
        raise HTTPException(status_code=400, detail="Deal is already completed or cancelled")
    if deal.status == DealStatus.payout_in_progress:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Виплата в процесі — скасування заборонено")
    if has_payout_tx(deal) or await payouts.open_outgoing_tx(db, deal.id) is not None:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Є вихідна транзакція по угоді — скасування заборонено")

    if deal.status in _FUNDED_DEAL_STATUSES:
        # Never silently cancel funded deals — refund on-chain if possible, else refuse.
        wallet = _resolve_wallet(None, deal.buyer.usdt_wallet if deal.buyer else None, None)
        if not wallet:
            await db.rollback()
            raise HTTPException(
                status_code=400,
                detail=(
                    "Кошти в escrow. Скасування без refund заборонено. "
                    "Використайте POST /admin/deals/{id}/resolve з resolution=refund_buyer "
                    "(і wallet_address покупця) або release_seller."
                ),
            )
        try:
            wallet = await payouts.validate_destination(db, wallet)
        except payouts.PayoutError as e:
            await db.rollback()
            raise HTTPException(status_code=e.http_status, detail=e.message)
        prev_status = deal.status
        units = payouts.refund_units(deal)
        await _precheck_gas_or_http(db, deal, wallet, units)
        try:
            await payouts.claim_for_payout(db, deal, expected_status=prev_status)
        except PayoutClaimError as e:
            await db.rollback()
            raise HTTPException(status_code=e.http_status, detail=e.message)
        payouts.enqueue_transfer(
            db, deal, tx_type=TransactionType.refund, to_address=wallet,
            amount_units=units, restore_status=prev_status,
        )
        audit(db, admin, "deal.cancel_refund", "deal", deal.id, to_address=wallet,
              amount_units=units, prev_status=prev_status.value)
        await db.commit()
        logger.info(f"[ADMIN] Deal #{deal.id}: cancel-with-refund queued")
        response.status_code = 202
        return _admin_deal_response(await _load_deal_full(db, deal_id))

    prev = deal.status.value
    deal.status = DealStatus.cancelled
    if deal.channel:
        deal.channel.status = ChannelStatus.approved
    audit(db, admin, "deal.cancel", "deal", deal.id, prev_status=prev)
    import app.services.chat as chat_svc

    chat_svc.system(db, deal, "cancelled", "Угоду скасовано гарантом.")
    await db.commit()
    return _admin_deal_response(await _load_deal_full(db, deal_id))


@router.post("/deals/{deal_id}/collect-fee")
async def collect_fee(
    deal_id: int,
    response: Response,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin-manual fee collection of ONE deal (Task 19: replaced by the fee sweep).

    Sweeps the whole remaining escrow USDT to TREASURY_ADDRESS (never a UI/API address)
    through the payout worker (CatFee energy / burn fallback). Same eligibility as the
    automatic sweep; legacy #3/#29 (and #6) are refused; at most one sweep per deal.
    """
    import importlib

    fee_sweep = importlib.import_module("app.services.fee_sweep")
    payouts = importlib.import_module("app.services.payouts")

    deal = (await db.execute(select(Deal).where(Deal.id == deal_id).with_for_update())).scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    try:
        fee_sweep.treasury_address()
    except fee_sweep.FeeSweepError as e:
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.message)
    if await payouts.open_outgoing_tx(db, deal.id) is not None:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Є непідтверджена вихідна транзакція по угоді")
    if deal.sweep_status in ("queued", "done"):
        await db.rollback()
        raise HTTPException(status_code=409, detail="Комісію з цієї угоди вже зібрано / в черзі")
    reason = await fee_sweep.check_eligible(db, deal)
    if reason is not None:
        await db.rollback()
        raise HTTPException(status_code=400, detail=reason)
    prev = deal.sweep_status
    if deal.sweep_status is None:
        deal.sweep_status = "pending_sweep"
    await db.commit()
    r = await fee_sweep.sweep_deal(db, deal_id, force=True, actor=admin,
                                   allowed_states=("pending_sweep", "due", "failed", "empty"))
    if r["result"] != "queued":
        if prev is None and r["result"] != "empty":
            d = await payouts._lock_deal(db, deal_id)
            d.sweep_status = prev if d.sweep_status == "pending_sweep" else d.sweep_status
            await db.commit()
        raise HTTPException(status_code=400, detail=f"Sweep не поставлено: {r.get('reason') or r['result']}")
    response.status_code = 202
    return {"ok": True, "status": "queued", "deal_id": deal_id, "amount_usdt": r["amount_usdt"],
            "to_address": fee_sweep.treasury_address(), "transaction_id": r["transaction_id"]}


@router.post("/fee-sweep/collect-all")
async def fee_sweep_collect_all(
    response: Response,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Superadmin "Зібрати все": queue sweeps of every pending_sweep escrow → TREASURY_ADDRESS.

    No address parameter by design. Legacy #3/#29 (рішення за Ренатом) and #6 are excluded.
    """
    fee_sweep = __import__("importlib").import_module("app.services.fee_sweep")

    try:
        res = await fee_sweep.collect_all(db, admin)
    except fee_sweep.FeeSweepError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)
    audit(db, admin, "fee_sweep.collect_all", "deal", None, queued=res["queued"], amount_usdt=res["amount_usdt"])
    await db.commit()
    response.status_code = 202
    return res


def settings_master_wallet() -> str:
    from app.config import settings

    return settings.tron_master_wallet_address


@router.post("/users/{user_id}/role")
async def set_user_role(
    user_id: int,
    role: str,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Set user role (admin only). Only admins can assign roles."""
    if admin.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Тільки адміністратор може змінювати ролі")

    if role not in ("user", "moderator", "admin"):
        raise HTTPException(status_code=400, detail="Невідома роль")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    prev_role = target.role.value
    target.role = UserRole(role)
    audit(db, admin, "user.role", "user", target.id, prev_role=prev_role, role=role)
    await db.commit()
    await db.refresh(target)

    return {"id": target.id, "username": target.username, "role": target.role.value}


def _user_row(u: User) -> dict:
    return {
        "id": u.id,
        "telegram_id": u.telegram_id,
        "username": u.username,
        "first_name": u.first_name,
        "email": u.email,
        "role": u.role.value,
        "is_active": u.is_active,
        "is_blocked": bool(u.is_blocked),
        "blocked_reason": u.blocked_reason,
        "blocked_at": u.blocked_at.isoformat() if u.blocked_at else None,
        "blocked_by_id": u.blocked_by_id,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/users")
async def list_users(
    q: str = Query("", max_length=100),
    blocked: bool | None = None,
    role: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Search users (admin only)."""
    from sqlalchemy import cast, or_, String as SAString

    query = select(User)
    q = q.strip().lstrip("@")
    if q:
        like = f"%{q}%"
        conds = [User.username.ilike(like), User.first_name.ilike(like), User.email.ilike(like),
                 cast(User.telegram_id, SAString).ilike(like)]
        if q.isdigit():
            conds.append(User.id == int(q))
        query = query.where(or_(*conds))
    if blocked is not None:
        query = query.where(User.is_blocked.is_(blocked))
    if role:
        if role not in ("user", "moderator", "admin"):
            raise HTTPException(status_code=400, detail="Невідома роль")
        query = query.where(User.role == UserRole(role))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (await db.execute(
        query.order_by(User.created_at.desc(), User.id.desc()).offset((page - 1) * limit).limit(limit)
    )).scalars().all()
    return {"items": [_user_row(u) for u in rows], "total": total, "page": page, "limit": limit}


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: int,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import moderation

    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    deals = await moderation.active_deals_of(db, target.id)
    return {**_user_row(target), "active_deals": [moderation.deal_brief(d, target.id) for d in deals]}


class BlockRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)


@router.post("/users/{user_id}/block")
async def block_user(
    user_id: int,
    body: BlockRequest,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Block a user. Never modifies deals: funded deals continue under admin control."""
    from app.services import moderation

    reason = body.reason.strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Вкажіть причину блокування")
    target = (await db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Не можна заблокувати себе")
    if target.role == UserRole.admin:
        raise HTTPException(status_code=400, detail="Не можна заблокувати адміністратора — спершу змініть роль")
    deals = await moderation.active_deals_of(db, target.id)
    if not target.is_blocked:
        target.is_blocked = True
        target.blocked_reason = reason
        target.blocked_at = utcnow_naive()
        target.blocked_by_id = admin.id
        audit(db, admin, "user.block", "user", target.id, reason=reason,
              active_deals=[d.id for d in deals])
        await db.commit()
        await db.refresh(target)
    briefs = [moderation.deal_brief(d, target.id) for d in deals]
    pending = [b for b in briefs if b["needs_admin_decision"]]
    if pending:
        try:
            from app.services.alerts import send_admin_alert, telegram_html_safe as _h

            lines = "\n".join(f"• угода #{b['deal_id']} ({b['status']}, {b['amount_usdt']} USDT)" for b in pending)
            await send_admin_alert(
                f"⛔ <b>Користувача #{target.id} заблоковано</b> ({_h(target.username or target.first_name)})\n"
                f"Оплачені угоди потребують рішення (allow / dispute):\n{lines}",
                alert_key=f"user_blocked_{target.id}", throttle_minutes=1,
            )
        except Exception as e:  # pragma: no cover
            logger.warning(f"[ADMIN] block alert failed: {e}")
    return {
        **_user_row(target),
        "active_deals": briefs,
        "escrow_total_usdt": round(sum(b["amount_usdt"] or 0 for b in briefs if b["funded"]), 6),
    }


@router.post("/users/{user_id}/unblock")
async def unblock_user(
    user_id: int,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    target = (await db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    if target.is_blocked:
        prev_reason = target.blocked_reason
        target.is_blocked = False
        target.blocked_reason = None
        target.blocked_at = None
        target.blocked_by_id = None
        audit(db, admin, "user.unblock", "user", target.id, prev_reason=prev_reason)
        await db.commit()
        await db.refresh(target)
    return _user_row(target)


class BlockedPartyRequest(BaseModel):
    action: str = Field(..., pattern="^(allow|disallow|dispute)$")
    note: str | None = Field(None, max_length=1000)


@router.post("/deals/{deal_id}/blocked-party")
async def deal_blocked_party(
    deal_id: int,
    body: BlockedPartyRequest,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Decide what happens to a deal with a blocked party.

    allow/disallow toggles the blocked party's ability to act on THIS deal.
    dispute moves a funded deal into admin resolution (paid/channel_transferring/awaiting_payout
    only). payout_in_progress or any open outgoing tx → 409 (never interrupted).
    """
    from app.services import payouts

    deal = (await db.execute(select(Deal).where(Deal.id == deal_id).with_for_update())).scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if body.action in ("allow", "disallow"):
        deal.blocked_party_allowed = body.action == "allow"
    else:
        if deal.status == DealStatus.payout_in_progress:
            raise HTTPException(status_code=409, detail="Виплата в процесі — не можна переводити у спір")
        if await payouts.open_outgoing_tx(db, deal.id) is not None:
            raise HTTPException(status_code=409, detail="Є відкрита вихідна транзакція — не можна переводити у спір")
        allowed = (DealStatus.paid, DealStatus.channel_transferring, DealStatus.awaiting_payout)
        if deal.status not in allowed:
            raise HTTPException(status_code=409, detail=f"Спір можливий лише з {', '.join(s.value for s in allowed)}")
        prev = deal.status.value
        deal.status = DealStatus.disputed
        deal.dispute_reason = (body.note or "Адмін: заблокований учасник угоди")[:1000]
    audit(db, admin, f"deal.blocked_party.{body.action}", "deal", deal.id,
          status=deal.status.value, note=body.note)
    await db.commit()
    return {"deal_id": deal.id, "status": deal.status.value,
            "blocked_party_allowed": bool(deal.blocked_party_allowed)}


@router.get("/audit-log")
async def get_audit_log(
    action: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    actor_id: int | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import AdminAuditLog

    query = select(AdminAuditLog)
    if action:
        query = query.where(AdminAuditLog.action.ilike(f"{action}%"))
    if target_type:
        query = query.where(AdminAuditLog.target_type == target_type)
    if target_id is not None:
        query = query.where(AdminAuditLog.target_id == target_id)
    if actor_id is not None:
        query = query.where(AdminAuditLog.actor_id == actor_id)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (await db.execute(
        query.order_by(AdminAuditLog.id.desc()).offset((page - 1) * limit).limit(limit)
    )).scalars().all()
    actor_ids = {r.actor_id for r in rows if r.actor_id}
    names = {}
    if actor_ids:
        for u in (await db.execute(select(User).where(User.id.in_(actor_ids)))).scalars():
            names[u.id] = u.username or u.first_name
    return {
        "items": [{
            "id": r.id, "actor_id": r.actor_id, "actor": names.get(r.actor_id),
            "action": r.action, "target_type": r.target_type, "target_id": r.target_id,
            "details": r.details, "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
        "total": total, "page": page, "limit": limit,
    }


@router.get("/channels", response_model=list[ChannelResponse])
async def list_all_channels(
    status: str | None = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all channels for admin (any status). Includes seller_telegram."""
    query = select(Channel).order_by(Channel.created_at.desc())
    if status:
        query = query.where(Channel.status == status)
    result = await db.execute(query)
    channels = result.scalars().all()
    return [ChannelResponse.model_validate(c) for c in channels]


@router.put("/channels/{channel_id}", response_model=ChannelResponse)
async def admin_update_channel(
    channel_id: int,
    body: ChannelUpdate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: update any channel."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(channel, field, value)

    await db.commit()
    await db.refresh(channel)
    return ChannelResponse.model_validate(channel)


@router.delete("/channels/{channel_id}", status_code=204)
async def admin_delete_channel(
    channel_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: delete any channel."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    await db.delete(channel)
    await db.commit()


@router.post("/channels/{channel_id}/recollect")
async def recollect_channel_stats(
    channel_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Force re-collect stats for a single channel from Telegram."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    from app.services.channel_stats import collect_channel_stats
    from app.models.channel import ChannelStats

    stats = await collect_channel_stats(channel.telegram_link)

    if stats.get("subscribers_count"):
        channel.subscribers_count = stats["subscribers_count"]
    if stats.get("avg_views"):
        channel.avg_views = stats["avg_views"]
    if stats.get("er"):
        channel.er = stats["er"]
    if stats.get("avatar_url"):
        channel.avatar_url = stats["avatar_url"]
    if stats.get("channel_name"):
        channel.channel_name = stats["channel_name"]
    if stats.get("adv_reach_12h"):
        channel.adv_reach_12h = stats["adv_reach_12h"]
    if stats.get("adv_reach_24h"):
        channel.adv_reach_24h = stats["adv_reach_24h"]
    if stats.get("adv_reach_48h"):
        channel.adv_reach_48h = stats["adv_reach_48h"]

    from app.services.stats_history import record_stats

    daily_stats = stats.get("daily_stats", [])
    new_records = await record_stats(db, channel.id, stats)
    await db.commit()

    return {
        "ok": True,
        "channel_id": channel.id,
        "channel_name": channel.channel_name,
        "daily_stats_total": len(daily_stats),
        "new_records_added": new_records,
    }


@router.post("/channels/recollect-all")
async def recollect_all_channels_stats(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Force re-collect stats for ALL active channels."""
    import asyncio
    from app.services.channel_stats import collect_channel_stats
    from app.models.channel import ChannelStats

    result = await db.execute(
        select(Channel).where(
            Channel.status.in_([ChannelStatus.approved, ChannelStatus.pending])
        )
    )
    channels = result.scalars().all()

    results = []
    for channel in channels:
        try:
            stats = await collect_channel_stats(channel.telegram_link)

            if stats.get("subscribers_count"):
                channel.subscribers_count = stats["subscribers_count"]
            if stats.get("avg_views"):
                channel.avg_views = stats["avg_views"]
            if stats.get("er"):
                channel.er = stats["er"]

            from app.services.stats_history import record_stats

            daily_stats = stats.get("daily_stats", [])
            new_records = await record_stats(db, channel.id, stats)
            await db.commit()
            results.append({
                "channel_id": channel.id,
                "name": channel.channel_name,
                "daily_stats": len(daily_stats),
                "new_records": new_records,
            })

            await asyncio.sleep(3)
        except Exception as e:
            results.append({
                "channel_id": channel.id,
                "name": channel.channel_name,
                "error": str(e),
            })

    return {"ok": True, "channels_processed": len(results), "details": results}


@router.post("/escrow/sweep/{deal_id}")
async def sweep_escrow_wallet(
    deal_id: int,
    response: Response,
    to_address: str = Body(..., embed=True),
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin-manual: sweep stray USDT from a CANCELLED deal's escrow to a validated address.

    Row lock + guards: only cancelled deals, no unresolved outgoing tx, destination is a
    real TRON address that is neither master nor any escrow. Fee collection from completed
    deals is POST /admin/deals/{id}/collect-fee. Queued for the payout worker (202).
    """
    import asyncio
    from app.services import payouts
    from app.services.escrow import get_usdt_balance

    result = await db.execute(select(Deal).where(Deal.id == deal_id).with_for_update())
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    escrow_addr = deal.escrow_wallet_address

    async def fail(msg: str) -> dict:
        await db.rollback()
        return {"ok": False, "error": msg}

    if deal.status != DealStatus.cancelled:
        return await fail(
            f"Sweep дозволено лише для cancelled-угод (зараз {deal.status.value}). "
            "Для виплат — resolve/cancel, для комісії — collect-fee."
        )
    if await payouts.open_outgoing_tx(db, deal.id) is not None:
        return await fail("Є непідтверджена вихідна транзакція по угоді — повтор заборонено")
    try:
        to_address = await payouts.validate_destination(db, to_address)
    except payouts.PayoutError as e:
        return await fail(e.message)

    # Balance (None = unknown, e.g. TronGrid 429 — never treat as 0)
    balance = await asyncio.to_thread(get_usdt_balance, escrow_addr)
    if balance is None:
        return await fail(f"Не вдалося отримати баланс {escrow_addr} (TronGrid). Спробуйте пізніше.")
    units = payouts.to_units(balance)
    if units <= 0:
        return await fail(f"Escrow {escrow_addr} has 0 USDT")

    try:
        await payouts.precheck_gas(deal, to_address, units)
    except payouts.PayoutError as e:
        return await fail(e.message)
    job = payouts.enqueue_transfer(
        db, deal, tx_type=TransactionType.sweep, to_address=to_address,
        amount_units=units, restore_status=None,
    )
    audit(db, admin, "escrow.sweep", "deal", deal.id, to_address=to_address, amount_units=units)
    await db.commit()
    response.status_code = 202
    return {
        "ok": True,
        "status": "queued",
        "deal_id": deal_id,
        "escrow": escrow_addr,
        "to": to_address,
        "amount_usdt": payouts.units_to_usdt(units),
        "transaction_id": job.id,
    }


@router.get("/deals/{deal_id}/payout-status")
async def admin_payout_status(
    deal_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import payouts

    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return await payouts.payout_status(db, deal)


@router.get("/escrow/master-balance")
async def master_wallet_balance(admin: User = Depends(get_admin_user)):
    """Master TRX balance (gas source). trx=None → unknown. Low → throttled admin alert."""
    from app.tasks.payout_worker import check_master_trx

    return await check_master_trx()


ESCROW_BALANCES_CACHE_TTL_SEC = 300
ESCROW_BALANCES_MIN_REFRESH_SEC = 10
_escrow_balances_cache: dict = {"at": 0.0, "payload": None}
_escrow_balances_lock = asyncio.Lock()


from app.services.escrow_balances import collect_escrow_balances as _collect_escrow_balances  # noqa: E402


@router.get("/escrow/balances")
async def check_escrow_balances(
    refresh: bool = Query(False),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """USDT balances of all escrow wallets.

    Cached for 5 min (``refresh=true`` bypasses it, at most once per 10s). TronGrid reads
    are throttled; wallets whose balance could not be read are listed in ``unknown``
    (shown as "помилка/невідомо" in the UI) — they are NOT counted as 0.
    """
    import time as _time

    async with _escrow_balances_lock:
        cached = _escrow_balances_cache["payload"]
        age = _time.monotonic() - _escrow_balances_cache["at"]
        use_cache = cached is not None and (
            age < ESCROW_BALANCES_MIN_REFRESH_SEC or (not refresh and age < ESCROW_BALANCES_CACHE_TTL_SEC)
        )
        if use_cache:
            return {**cached, "cached": True, "cache_age_sec": round(age, 1)}

        result = await db.execute(
            select(Deal.id, Deal.escrow_wallet_address, Deal.status).order_by(Deal.id.desc())
        )
        rows = [(d_id, addr, st.value if hasattr(st, "value") else str(st)) for d_id, addr, st in result.all()]
        payload = await asyncio.to_thread(_collect_escrow_balances, rows, cached)
        payload["checked_at"] = utcnow_naive().isoformat() + "Z"
        _escrow_balances_cache["payload"] = payload
        _escrow_balances_cache["at"] = _time.monotonic()
        return {**payload, "cached": False, "cache_age_sec": 0.0}


# ═══════════════════════════════════════════════════════════════
#   AUCTION MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@router.get("/auctions")
async def admin_list_auctions(
    status_filter: str = Query("", alias="status"),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all auctions for admin panel."""
    query = (
        select(Auction)
        .options(selectinload(Auction.channel), selectinload(Auction.seller), selectinload(Auction.winner))
        .order_by(Auction.created_at.desc())
    )
    if status_filter:
        query = query.where(Auction.status == status_filter)

    result = await db.execute(query)
    auctions = result.scalars().all()

    items = []
    for a in auctions:
        bid_count_real = (await db.execute(
            select(func.count()).select_from(AuctionBid).where(AuctionBid.auction_id == a.id)
        )).scalar() or 0

        items.append({
            "id": a.id,
            "channel_id": a.channel_id,
            "channel_name": a.channel.channel_name if a.channel else None,
            "channel_avatar": public_channel_avatar_url(a.channel.id, a.channel.avatar_url) if a.channel else None,
            "seller_name": a.seller.first_name if a.seller else None,
            "seller_id": a.seller_id,
            "start_price": a.start_price,
            "current_price": a.current_price,
            "buyout_price": a.buyout_price,
            "bid_step": a.bid_step,
            "bid_count": bid_count_real,
            "status": a.status,
            "starts_at": a.starts_at.isoformat() if a.starts_at else None,
            "ends_at": a.ends_at.isoformat() if a.ends_at else None,
            "winner_id": a.winner_id,
            "winner_name": a.winner.first_name if a.winner else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    return {"items": items, "total": len(items)}


@router.post("/auctions/{auction_id}/cancel")
async def admin_cancel_auction(
    auction_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin cancel an auction."""
    result = await db.execute(select(Auction).where(Auction.id == auction_id))
    auction = result.scalar_one_or_none()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    if auction.status in ("ended", "cancelled"):
        raise HTTPException(status_code=400, detail="Auction already finished")

    auction.status = "cancelled"
    await db.commit()
    return {"ok": True, "auction_id": auction_id, "status": "cancelled"}


@router.post("/auctions/{auction_id}/extend")
async def admin_extend_auction(
    auction_id: int,
    hours: int = Body(..., embed=True),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin extend auction end time by N hours."""
    result = await db.execute(select(Auction).where(Auction.id == auction_id))
    auction = result.scalar_one_or_none()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    if auction.status not in ("active", "scheduled"):
        raise HTTPException(status_code=400, detail="Can only extend active/scheduled auctions")

    auction.ends_at = auction.ends_at + timedelta(hours=hours)
    await db.commit()
    return {"ok": True, "auction_id": auction_id, "new_ends_at": auction.ends_at.isoformat()}


@router.put("/auctions/{auction_id}")
async def admin_update_auction(
    auction_id: int,
    bid_step: float | None = Body(None),
    buyout_price: float | None = Body(None),
    start_price: float | None = Body(None),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin edit auction parameters."""
    result = await db.execute(select(Auction).where(Auction.id == auction_id))
    auction = result.scalar_one_or_none()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")

    if bid_step is not None:
        auction.bid_step = bid_step
    if buyout_price is not None:
        auction.buyout_price = buyout_price
    if start_price is not None and auction.bid_count == 0:
        auction.start_price = start_price
        auction.current_price = start_price

    await db.commit()
    return {"ok": True, "auction_id": auction_id}


@router.delete("/auctions/{auction_id}", status_code=204)
async def admin_delete_auction(
    auction_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin delete auction and its bids."""
    result = await db.execute(select(Auction).where(Auction.id == auction_id))
    auction = result.scalar_one_or_none()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    await db.delete(auction)
    await db.commit()


# ── Channel Stats Management ──


@router.post("/channels/{channel_id}/refresh-stats")
async def admin_refresh_channel_stats(
    channel_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually re-collect stats for a channel from Telegram."""
    import traceback
    from app.services.channel_stats import collect_channel_stats
    from app.models.channel import ChannelStats, ChannelPost

    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    try:
        stats = await collect_channel_stats(channel.telegram_link, message_limit=500)
    except Exception as e:
        logger.error(f"refresh-stats collect error for #{channel_id}: {traceback.format_exc()}")
        raise HTTPException(status_code=502, detail=f"Telegram API error: {e}")

    try:
        # Update channel snapshot
        if stats.get("subscribers_count"):
            channel.subscribers_count = stats["subscribers_count"]
        if stats.get("avg_views"):
            channel.avg_views = stats["avg_views"]
        if stats.get("er"):
            channel.er = stats["er"]
        if stats.get("avatar_url"):
            channel.avatar_url = stats["avatar_url"]
        if stats.get("channel_name"):
            channel.channel_name = stats["channel_name"]
        if stats.get("adv_reach_12h"):
            channel.adv_reach_12h = stats["adv_reach_12h"]
        if stats.get("adv_reach_24h"):
            channel.adv_reach_24h = stats["adv_reach_24h"]
        if stats.get("adv_reach_48h"):
            channel.adv_reach_48h = stats["adv_reach_48h"]
        if stats.get("total_posts"):
            channel.total_posts = stats["total_posts"]
        if stats.get("post_frequency") is not None:
            channel.post_frequency = stats["post_frequency"]
        if stats.get("last_post_date"):
            try:
                channel.last_post_date = datetime.fromisoformat(stats["last_post_date"]).replace(tzinfo=None)
            except (ValueError, TypeError):
                pass
        if stats.get("avg_forwards"):
            channel.avg_forwards = stats["avg_forwards"]
        if stats.get("avg_reactions"):
            channel.avg_reactions = stats["avg_reactions"]
        if stats.get("channel_age_months"):
            channel.age = f"{stats['channel_age_months']}"

        # Save daily stats (honest series, Task 20)
        from app.services.stats_history import record_stats

        daily_stats = stats.get("daily_stats", [])
        new_stats_count = await record_stats(db, channel.id, stats)

        # Save posts with dedup
        posts_data = stats.get("posts", [])
        new_posts_count = 0
        if posts_data:
            msg_ids = [p["telegram_msg_id"] for p in posts_data]
            existing_posts = await db.execute(
                select(ChannelPost.telegram_msg_id).where(
                    ChannelPost.channel_id == channel.id,
                    ChannelPost.telegram_msg_id.in_(msg_ids),
                )
            )
            existing_msg_ids = set(existing_posts.scalars().all())
            for p in posts_data:
                if p["telegram_msg_id"] not in existing_msg_ids:
                    post_date = datetime.fromisoformat(p["date"]) if isinstance(p["date"], str) else p["date"]
                    if hasattr(post_date, 'tzinfo') and post_date.tzinfo is not None:
                        post_date = post_date.replace(tzinfo=None)
                    db.add(ChannelPost(
                        channel_id=channel.id,
                        telegram_msg_id=p["telegram_msg_id"],
                        date=post_date,
                        text=p.get("text"),
                        media_type=p.get("media_type"),
                        link=p.get("link"),
                        views=p["views"],
                        forwards=p["forwards"],
                        reactions=p["reactions"],
                        comments=p.get("comments", 0),
                    ))
                    new_posts_count += 1

        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"refresh-stats save error for #{channel_id}: {traceback.format_exc()}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Save error: {e}")

    return {
        "ok": True,
        "channel_id": channel_id,
        "channel_name": channel.channel_name,
        "subscribers_count": channel.subscribers_count,
        "avg_views": channel.avg_views,
        "er": channel.er,
        "new_stats_records": new_stats_count,
        "total_daily_stats": len(daily_stats),
        "new_posts": new_posts_count,
        "total_posts_fetched": len(posts_data),
        "telethon_data": len(daily_stats) > 0,
    }


@router.get("/diagnostics/telegram")
async def admin_telegram_diagnostics(
    admin: User = Depends(get_admin_user),
):
    """Check Telegram API configuration status."""
    from app.config import settings as cfg

    diagnostics = {
        "bot_token_stats": bool(cfg.bot_token_stats),
        "telegram_api_id": cfg.telegram_api_id > 0,
        "telegram_api_hash": bool(cfg.telegram_api_hash),
        "telethon_session_string": bool(cfg.telethon_session_string),
    }

    # Test Bot API
    bot_api_ok = False
    bot_api_error = None
    if cfg.bot_token_stats:
        try:
            import httpx
            async with httpx.AsyncClient() as http:
                resp = await http.get(
                    f"https://api.telegram.org/bot{cfg.bot_token_stats}/getMe",
                    timeout=10.0,
                )
                bot_api_ok = resp.status_code == 200
                if not bot_api_ok:
                    bot_api_error = f"HTTP {resp.status_code}"
        except Exception as e:
            from app.utils.log_redact import redact
            bot_api_error = redact(e)
    else:
        bot_api_error = "BOT_TOKEN_STATS not configured"

    diagnostics["bot_api_ok"] = bot_api_ok
    diagnostics["bot_api_error"] = bot_api_error

    # Test Telethon — session can come from env var OR from DB (DB-first storage)
    telethon_ok = False
    telethon_error = None
    telethon_status = None
    if cfg.telegram_api_id and cfg.telegram_api_hash:
        from app.services.channel_stats import _load_session_from_db, get_telethon_health
        health = get_telethon_health()
        telethon_status = health.get("status")
        db_session = await _load_session_from_db()
        has_session = bool(cfg.telethon_session_string or db_session)
        if health.get("authkey_duplicated") or telethon_status == "authkey_duplicated":
            telethon_error = health.get("detail") or "AuthKeyDuplicatedError — re-auth required"
        elif telethon_status in ("waiting", "connecting"):
            telethon_error = health.get("detail") or f"Telethon {telethon_status} (startup delay)"
        elif has_session:
            try:
                from app.services.channel_stats import _get_telethon_client
                client = await _get_telethon_client()
                telethon_ok = client is not None and client.is_connected()
                if telethon_ok:
                    try:
                        telethon_ok = await client.is_user_authorized()
                    except Exception as e:
                        telethon_ok = False
                        telethon_error = str(e)
                if not telethon_ok and not telethon_error:
                    telethon_error = health.get("detail") or "Client not connected or not authorized"
            except Exception as e:
                telethon_error = str(e)
        else:
            telethon_error = "No session — use the Telethon сесія panel to authorize"
    else:
        missing = []
        if not cfg.telegram_api_id:
            missing.append("TELEGRAM_API_ID")
        if not cfg.telegram_api_hash:
            missing.append("TELEGRAM_API_HASH")
        telethon_error = f"Missing env vars: {', '.join(missing)}"

    diagnostics["telethon_ok"] = telethon_ok
    diagnostics["telethon_error"] = telethon_error
    diagnostics["telethon_status"] = telethon_status

    # Overall status
    diagnostics["analytics_available"] = bot_api_ok and telethon_ok
    diagnostics["basic_stats_only"] = bot_api_ok and not telethon_ok

    return diagnostics


# ═══════════════════════════════════════════════════════════════
#   ACTIVITY / FAKE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

# In-memory config — survives until restart, configurable from admin UI
_activity_config = {
    "online_investors_min": 80,
    "online_investors_max": 150,
    "deals_week_min": 8,
    "deals_week_max": 20,
    "bids_today_min": 15,
    "bids_today_max": 40,
    "active_auctions_min": 3,
    "active_auctions_max": 8,
    "channels_min": 40,
    "channels_max": 80,
    "feed_generated_count": 15,
    "enabled": True,
}


def get_activity_config():
    return _activity_config


@router.get("/activity-config")
async def get_activity_config_endpoint(
    admin: User = Depends(get_admin_user),
):
    """Get current activity boost config."""
    return _activity_config


@router.put("/activity-config")
async def update_activity_config(
    config: dict = Body(...),
    admin: User = Depends(get_admin_user),
):
    """Update activity boost config."""
    allowed_keys = set(_activity_config.keys())
    for key, value in config.items():
        if key in allowed_keys:
            if key == "enabled":
                _activity_config[key] = bool(value)
            else:
                _activity_config[key] = int(value)
    return _activity_config


@router.get("/dashboard-stats")
async def admin_dashboard_stats(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats for admin dashboard overview."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    total_channels = (await db.execute(
        select(func.count()).select_from(Channel)
    )).scalar() or 0

    pending_channels = (await db.execute(
        select(func.count()).select_from(Channel).where(
            Channel.status == "pending", ~_bundle_member_exists())
    )).scalar() or 0

    approved_channels = (await db.execute(
        select(func.count()).select_from(Channel).where(Channel.status == "approved")
    )).scalar() or 0

    total_deals = (await db.execute(
        select(func.count()).select_from(Deal)
    )).scalar() or 0

    active_deals = (await db.execute(
        select(func.count()).select_from(Deal).where(
            Deal.status.in_(["created", "payment_pending", "paid", "channel_transferring"])
        )
    )).scalar() or 0

    disputed_deals = (await db.execute(
        select(func.count()).select_from(Deal).where(Deal.status == "disputed")
    )).scalar() or 0

    active_auctions = (await db.execute(
        select(func.count()).select_from(Auction).where(Auction.status == "active")
    )).scalar() or 0

    total_users = (await db.execute(
        select(func.count()).select_from(User)
    )).scalar() or 0

    deals_this_week = (await db.execute(
        select(func.count()).select_from(Deal).where(Deal.created_at >= week_ago)
    )).scalar() or 0

    total_revenue = (await db.execute(
        select(func.sum(Deal.service_fee)).where(Deal.status == "completed")
    )).scalar() or 0
    # Fee actually moved to master (admin collect-fee, receipt SUCCESS only).
    fee_collected = (await db.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.type.in_((TransactionType.fee_collection, TransactionType.fee_sweep)),
            Transaction.status == TransactionStatus.confirmed,
        )
    )).scalar() or 0

    return {
        "total_channels": total_channels,
        "pending_channels": pending_channels,
        "approved_channels": approved_channels,
        "total_deals": total_deals,
        "active_deals": active_deals,
        "disputed_deals": disputed_deals,
        "active_auctions": active_auctions,
        "total_users": total_users,
        "deals_this_week": deals_this_week,
        "total_revenue": round(float(total_revenue), 2),
        "fee_accrued": round(float(total_revenue), 2),
        "fee_collected": round(float(fee_collected), 2),
    }


# ═══════════════════════════════════════════════════════════════
#   TELETHON RE-AUTH  (web-based, no bot / SSH needed)
# ═══════════════════════════════════════════════════════════════

# Temporary in-process state for the re-auth wizard.
# Keyed by admin user id so concurrent admins don't collide.
_reauth_sessions: dict[int, dict] = {}


def _sent_code_delivery_type(sent) -> str:
    """Map Telethon sent_code.type to a short label: app / sms / call / etc."""
    t = getattr(sent, "type", None)
    if t is None:
        return "unknown"
    name = type(t).__name__  # e.g. SentCodeTypeApp
    if name.startswith("SentCodeType"):
        raw = name[len("SentCodeType"):]
    else:
        raw = name
    # CamelCase → snake_case then simplify common ones
    import re
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", raw).lower()
    aliases = {
        "app": "app",
        "sms": "sms",
        "call": "call",
        "flash_call": "flash_call",
        "missed_call": "missed_call",
        "email_code": "email",
        "firebase_sms": "firebase_sms",
        "fragment_sms": "fragment_sms",
        "sms_word": "sms_word",
        "sms_phrase": "sms_phrase",
        "set_up_email_required": "email_setup",
    }
    return aliases.get(snake, snake or "unknown")


@router.post("/reauth/start")
async def reauth_start(
    admin: User = Depends(get_admin_user),
):
    """Step 1 — request OTP from Telegram.

    Connects a fresh Telethon client and calls send_code_request().
    Returns immediately; the OTP arrives on the registered phone / app.
    Includes code_type (app / sms / call / …) so the admin UI can show where to look.
    """
    from app.config import settings as cfg

    phone = cfg.telegram_phone
    if not phone:
        raise HTTPException(status_code=400, detail="TELEGRAM_PHONE not set in env")
    if not cfg.telegram_api_id or not cfg.telegram_api_hash:
        raise HTTPException(status_code=400, detail="TELEGRAM_API_ID / TELEGRAM_API_HASH not set")

    client = None
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(
            StringSession(),
            cfg.telegram_api_id,
            cfg.telegram_api_hash,
        )
        await client.connect()
        sent = await client.send_code_request(phone)
        code_type = _sent_code_delivery_type(sent)
        _reauth_sessions[admin.id] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": sent.phone_code_hash,
            "code_type": code_type,
        }
        return {
            "ok": True,
            "phone": phone,
            "code_type": code_type,
            "message": f"Code sent via {code_type}. Call /reauth/confirm with the code.",
        }
    except Exception as e:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reauth/confirm")
async def reauth_confirm(
    body: dict = Body(...),
    admin: User = Depends(get_admin_user),
):
    """Step 2 — submit the OTP (and optional 2FA password).

    Body: {"code": "12345"}  or  {"code": "12345", "password": "..."}
    On success, the new session string is persisted to DB and the in-memory
    Telethon client is reset so the next stats cycle uses the fresh session.
    """
    data = _reauth_sessions.get(admin.id)
    if not data:
        raise HTTPException(status_code=400, detail="No active re-auth session. Call /reauth/start first.")

    code = body.get("code", "").strip()
    password = body.get("password", "").strip()

    if not code:
        raise HTTPException(status_code=422, detail="'code' is required")

    client = data["client"]
    try:
        await client.sign_in(data["phone"], code, phone_code_hash=data["phone_code_hash"])
    except Exception as e:
        from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError

        if isinstance(e, SessionPasswordNeededError):
            if not password:
                return {"ok": False, "need_2fa": True, "message": "2FA password required. Resend with 'password' field."}
            try:
                await client.sign_in(password=password)
            except Exception as e2:
                _reauth_sessions.pop(admin.id, None)
                await client.disconnect()
                raise HTTPException(status_code=400, detail=f"2FA failed: {e2}")
        elif isinstance(e, (PhoneCodeInvalidError, PhoneCodeExpiredError)):
            raise HTTPException(status_code=400, detail="Wrong or expired code. Try again.")
        else:
            _reauth_sessions.pop(admin.id, None)
            await client.disconnect()
            raise HTTPException(status_code=400, detail=f"Auth error: {e}")

    # Save fresh session to DB
    session_string = client.session.save()
    from app.services.channel_stats import _save_session_to_db, reset_telethon_client
    await _save_session_to_db(session_string)
    reset_telethon_client()

    _reauth_sessions.pop(admin.id, None)
    await client.disconnect()

    return {"ok": True, "message": "Telethon session updated. Analytics will resume on the next stats cycle."}


@router.get("/reauth/status")
async def reauth_status(
    admin: User = Depends(get_admin_user),
):
    """Check current Telethon session status (DB + live client)."""
    from app.services.channel_stats import _load_session_from_db, _telethon_client, get_telethon_health

    db_session = await _load_session_from_db()
    health = get_telethon_health()
    live_ok = False
    live_error = health.get("detail")
    if _telethon_client is not None:
        try:
            live_ok = _telethon_client.is_connected() and await _telethon_client.is_user_authorized()
            if live_ok:
                live_error = None
        except Exception as e:
            live_error = str(e)
    elif health.get("status") in ("waiting", "connecting"):
        live_error = health.get("detail") or f"Telethon status: {health.get('status')}"

    return {
        "db_session_exists": bool(db_session),
        "live_client_ok": live_ok,
        "live_client_error": live_error,
        "telethon_status": health.get("status"),
        "authkey_duplicated": health.get("authkey_duplicated", False),
        "pending_reauth": admin.id in _reauth_sessions,
    }


@router.post("/run-stats-now")
async def run_stats_now(
    admin: User = Depends(get_admin_user),
):
    """Immediately trigger one stats-collection cycle for all channels (runs in background).

    Refuses with an error if Telethon is not connected+authorized (so the admin UI
    does not show a false green OK).
    """
    import asyncio
    from app.services.channel_stats import (
        _get_telethon_client,
        get_telethon_health,
    )
    from app.tasks.stats_collector import collect_stats_once

    health = get_telethon_health()
    status = health.get("status")

    if health.get("authkey_duplicated") or status == "authkey_duplicated":
        raise HTTPException(
            status_code=503,
            detail=(
                "AuthKeyDuplicatedError: сесію інвалідовано (два IP одночасно). "
                "Потрібна повторна авторизація (Telethon сесія → Запросити код)."
            ),
        )
    if status in ("waiting", "connecting"):
        delay = health.get("startup_delay_sec", 150)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Telethon ще не готовий (status={status}). "
                f"Після деплою перше підключення відкладається на ~{delay}s — зачекайте і спробуйте знову."
            ),
        )

    client = await _get_telethon_client()
    if client is None or not client.is_connected():
        reason = health.get("detail") or f"Telethon не підключений (status={status})"
        raise HTTPException(status_code=503, detail=reason)
    try:
        authorized = await client.is_user_authorized()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Telethon auth check failed: {e}")
    if not authorized:
        raise HTTPException(
            status_code=503,
            detail="Telethon сесія не авторизована — потрібна повторна авторизація.",
        )

    asyncio.create_task(collect_stats_once())
    return {"ok": True, "message": "Stats collection started in background. Check channel pages in ~1-2 minutes."}


# ─── Bundle moderation ──────────────────────────────────────────────────────


@router.get("/bundles/pending")
async def get_pending_bundles(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all bundles awaiting moderation."""
    from app.models.bundle import ChannelBundle, BundleStatus, BundleChannel
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(ChannelBundle)
        .options(selectinload(ChannelBundle.seller), selectinload(ChannelBundle.bundle_channels))
        .where(ChannelBundle.status == BundleStatus.pending)
        .order_by(ChannelBundle.created_at.asc())
    )
    bundles = result.scalars().all()

    items = []
    for b in bundles:
        # Gather channel links for display
        channel_ids = [bc.channel_id for bc in b.bundle_channels]
        order = {bc.channel_id: bc.display_order for bc in b.bundle_channels}
        channel_links: list[str] = []
        channels_detail: list[dict] = []
        if channel_ids:
            ch_rows = (await db.execute(
                select(Channel).where(Channel.id.in_(channel_ids))
            )).scalars().all()
            ch_rows = sorted(ch_rows, key=lambda c: order.get(c.id, 0))
            # Task 31: show the seller-stated balance to the moderator
            from app.services.deal_checklist import format_balance
            for c in ch_rows:
                bal = format_balance(c.stars_balance, c.ton_balance)
                channel_links.append(
                    f"{c.channel_name} ({c.telegram_link})" + (f" · {bal} (зі слів продавця)" if bal else "")
                )
                link = c.telegram_link or ""
                url = link if link.startswith("http") else f"https://t.me/{link.lstrip('@')}"
                channels_detail.append({
                    "id": c.id,
                    "channel_name": c.channel_name,
                    "telegram_link": c.telegram_link,
                    "url": url,
                    "status": getattr(c.status, "value", c.status),
                    "is_closed": bool(c.is_closed),
                    "subscribers_count": c.subscribers_count,
                    "balance": bal or None,
                })

        items.append({
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "category": b.category,
            "price": b.price,
            "monthly_income": b.monthly_income,
            "resources": b.resources,
            "seller_id": b.seller_id,
            "seller_name": b.seller.first_name if b.seller else None,
            "channel_count": len(b.bundle_channels),
            "channels": channel_links,
            "channels_detail": channels_detail,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })
    return {"items": items, "total": len(items)}


async def _pending_bundle_channels(db: AsyncSession, bundle_id: int) -> list:
    """Pending member channels of a bundle; already-moderated ones are left untouched."""
    from app.models.bundle import BundleChannel
    return list((await db.execute(
        select(Channel)
        .join(BundleChannel, BundleChannel.channel_id == Channel.id)
        .where(BundleChannel.bundle_id == bundle_id, Channel.status == ChannelStatus.pending)
    )).scalars().all())


@router.post("/bundles/{bundle_id}/approve")
async def approve_bundle(
    bundle_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a bundle listing."""
    from app.models.bundle import ChannelBundle, BundleStatus, BundleChannel
    from datetime import datetime

    result = await db.execute(select(ChannelBundle).where(ChannelBundle.id == bundle_id))
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle.status != BundleStatus.pending:
        raise HTTPException(status_code=400, detail="Bundle is not pending")

    bundle.status = BundleStatus.approved
    bundle.moderator_id = admin.id
    bundle.moderated_at = datetime.utcnow()
    audit(db, admin, "bundle.approve", "bundle", bundle.id)
    for ch in await _pending_bundle_channels(db, bundle.id):
        ch.status = ChannelStatus.approved
        ch.moderator_id = admin.id
        ch.moderated_at = bundle.moderated_at
        audit(db, admin, "channel.approve", "channel", ch.id, via_bundle=bundle.id)
    await db.commit()
    await db.refresh(bundle)

    # Notify seller
    try:
        from bot.main import notify_bundle_approved
        from aiogram import Bot
        from app.config import settings
        seller_result = await db.execute(select(User).where(User.id == bundle.seller_id))
        seller = seller_result.scalar_one_or_none()
        bot = Bot(token=settings.bot_token_alerts)
        await notify_bundle_approved(bot, bundle, seller)
        await bot.session.close()
    except Exception as e:
        logger.warning(f"[ADMIN] Bundle #{bundle_id} approved but notification failed: {e}")

    return {"ok": True, "bundle_id": bundle_id, "status": "approved"}


@router.post("/bundles/{bundle_id}/reject")
async def reject_bundle(
    bundle_id: int,
    reason: str = Query(..., max_length=500),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a bundle listing with a reason."""
    from app.models.bundle import ChannelBundle, BundleStatus
    from datetime import datetime

    result = await db.execute(select(ChannelBundle).where(ChannelBundle.id == bundle_id))
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle.status != BundleStatus.pending:
        raise HTTPException(status_code=400, detail="Bundle is not pending")

    bundle.status = BundleStatus.rejected
    bundle.moderator_id = admin.id
    bundle.moderated_at = datetime.utcnow()
    bundle.rejection_reason = reason
    audit(db, admin, "bundle.reject", "bundle", bundle.id, reason=reason)
    for ch in await _pending_bundle_channels(db, bundle.id):
        ch.status = ChannelStatus.rejected
        ch.moderator_id = admin.id
        ch.moderated_at = bundle.moderated_at
        ch.rejection_reason = reason
        audit(db, admin, "channel.reject", "channel", ch.id, via_bundle=bundle.id, reason=reason)
    await db.commit()

    # Notify seller
    try:
        from bot.main import notify_bundle_rejected
        from aiogram import Bot
        from app.config import settings
        seller_result = await db.execute(select(User).where(User.id == bundle.seller_id))
        seller = seller_result.scalar_one_or_none()
        bot = Bot(token=settings.bot_token_alerts)
        await notify_bundle_rejected(bot, bundle, seller)
        await bot.session.close()
    except Exception as e:
        logger.warning(f"[ADMIN] Bundle #{bundle_id} rejected but notification failed: {e}")

    return {"ok": True, "bundle_id": bundle_id, "status": "rejected", "reason": reason}



# ── Task 32: bundle per-channel balances (staff can always edit) ───────

def _admin_bundle_item(b, active: bool) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "status": getattr(b.status, "value", b.status),
        "seller_id": b.seller_id,
        "price": b.price,
        "has_active_deal": active,
        "channels": [
            {
                "id": bc.channel.id,
                "channel_name": bc.channel.channel_name,
                "telegram_link": bc.channel.telegram_link,
                "stars_balance": bc.channel.stars_balance,
                "ton_balance": bc.channel.ton_balance,
            }
            for bc in (b.bundle_channels or []) if bc.channel is not None
        ],
    }


@router.get("/bundles")
async def admin_list_bundles(
    search: str | None = Query(None, max_length=200),
    limit: int = Query(30, ge=1, le=100),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Staff: any bundle (any status) with per-channel stated balances."""
    from app.models.bundle import BundleChannel, ChannelBundle
    from app.services import bundle_balances as bb

    q = (
        select(ChannelBundle)
        .options(selectinload(ChannelBundle.bundle_channels).selectinload(BundleChannel.channel))
        .order_by(ChannelBundle.id.desc())
        .limit(limit)
    )
    if search:
        s = search.strip().lstrip("#")
        if s.isdigit():
            q = q.where(ChannelBundle.id == int(s))
        else:
            q = q.where(ChannelBundle.name.ilike(f"%{s}%"))
    bundles = (await db.execute(q)).scalars().all()
    items = [_admin_bundle_item(b, await bb.has_active_deal(db, b)) for b in bundles]
    return {"items": items, "total": len(items)}




@router.put("/bundles/{bundle_id}/balances")
async def admin_update_bundle_balances(
    bundle_id: int,
    body: BundleBalancesUpdate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Staff (admin/moderator): edit per-channel balances at any time, audited.
    Never touches deals.balance_* — existing deals keep their snapshot."""
    from app.services import bundle_balances as bb

    bundle = await bb.load_bundle_for_update(db, bundle_id)
    changes = bb.apply_balances(bundle, body.channel_balances)
    if changes:
        audit(db, admin, "bundle.balances_edit", "bundle", bundle.id, changes=changes)
    await db.commit()
    db.expire_all()
    bundle = await bb.load_bundle(db, bundle_id)
    return _admin_bundle_item(bundle, await bb.has_active_deal(db, bundle))


# ── Inactive channels (task 15 item 1) ─────────────────────────────────

class ChannelRemoveRequest(BaseModel):
    confirm: bool = False
    reason: str | None = Field(default=None, max_length=500)


@router.get("/channels/inactive")
async def list_inactive_channels(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Lots whose username no longer resolves / channel gone / bot lost access."""
    from app.services.channel_availability import list_inactive

    return {"items": await list_inactive(db)}


@router.post("/channels/{channel_id}/remove")
async def remove_channel_from_market(
    channel_id: int,
    body: ChannelRemoveRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """'Зняти з біржі': soft delete (status removed) + audit. Refused with an explanation
    while the lot has an active deal or an auction with bids."""
    from app.services.channel_availability import LISTED_STATUSES, removal_blockers

    if not body.confirm:
        raise HTTPException(status_code=400, detail="Підтвердіть зняття лота з біржі")
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id).with_for_update())).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status == ChannelStatus.removed:
        return {"id": channel.id, "status": channel.status.value}
    if channel.status not in LISTED_STATUSES:
        raise HTTPException(status_code=400, detail=f"Лот у статусі {channel.status.value} — знімати нічого")
    blockers = await removal_blockers(db, channel.id)
    if blockers:
        raise HTTPException(status_code=409, detail="Неможливо зняти з біржі: " + "; ".join(blockers))
    prev = channel.status.value
    channel.status = ChannelStatus.removed
    channel.removed_at = utcnow_naive()
    channel.removed_by_id = admin.id
    channel.removed_reason = (body.reason or channel.check_error or "Канал неактивний")[:500]
    audit(db, admin, "channel.remove", "channel", channel.id, prev_status=prev,
          reason=channel.removed_reason, check_error=channel.check_error)
    await db.commit()
    logger.info(f"[ADMIN] Channel #{channel.id} removed from market by admin #{admin.id}: {channel.removed_reason}")
    return {"id": channel.id, "status": channel.status.value}


# ── Weekly stats (read-only, superadmin) ──────────────────────────────

@router.get("/stats/weekly")
async def admin_weekly_stats(
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Same numbers as the Monday report to the admin group (last 7 days)."""
    from app.services.weekly_stats import collect_weekly_stats

    return await collect_weekly_stats(db)
