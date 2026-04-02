import logging
from datetime import datetime, timedelta, timezone
import os

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.auction import Auction, AuctionBid
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealStatus
from app.models.user import User, UserRole
from app.schemas.channel import ChannelResponse, ChannelUpdate
from app.schemas.deal import DealResolveRequest, DealResponse
from app.utils.security import get_admin_user

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

    user.role = UserRole.admin
    await db.commit()
    await db.refresh(user)

    return {"ok": True, "user_id": user.id, "username": user.username, "role": user.role.value}


@router.get("/channels/pending", response_model=list[ChannelResponse])
async def get_pending_channels(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all channels awaiting moderation."""
    result = await db.execute(
        select(Channel)
        .where(Channel.status == ChannelStatus.pending)
        .order_by(Channel.created_at.asc())
    )
    channels = result.scalars().all()
    return [ChannelResponse.model_validate(c) for c in channels]


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

    try:
        channel.status = ChannelStatus.approved
        channel.moderator_id = admin.id
        channel.moderated_at = datetime.utcnow()
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

            # Save historical daily stats for graphs
            daily_stats = stats.get("daily_stats", [])
            if daily_stats:
                for ds in daily_stats:
                    stat_record = ChannelStats(
                        channel_id=channel.id,
                        date=datetime.strptime(ds["date"], "%Y-%m-%d"),
                        subscribers=ds.get("subscribers", 0),
                        avg_views=ds.get("avg_views", 0),
                        avg_reach=ds.get("avg_views", 0),
                        er=ds.get("er", 0.0),
                        post_count=ds.get("post_count", 0),
                    )
                    db.add(stat_record)
            else:
                stat_record = ChannelStats(
                    channel_id=channel.id,
                    date=datetime.utcnow(),
                    subscribers=stats.get("subscribers_count", 0),
                    avg_views=stats.get("avg_views", 0),
                    avg_reach=stats.get("avg_views", 0),
                    er=stats.get("er", 0.0),
                    post_count=0,
                )
                db.add(stat_record)
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

    try:
        channel.status = ChannelStatus.rejected
        channel.moderator_id = admin.id
        channel.moderated_at = datetime.utcnow()
        channel.rejection_reason = reason
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
            created_at=d.created_at, paid_at=d.paid_at, completed_at=d.completed_at,
        ))
    return responses


@router.post("/deals/{deal_id}/resolve", response_model=DealResponse)
async def resolve_deal(
    deal_id: int,
    body: DealResolveRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a disputed deal: refund buyer or release to seller."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.status != DealStatus.disputed:
        raise HTTPException(status_code=400, detail="Deal is not disputed")

    if body.resolution == "refund_buyer":
        deal.status = DealStatus.cancelled
        # TODO: refund USDT to buyer
        # Restore channel to approved
        deal.channel.status = ChannelStatus.approved
    elif body.resolution == "release_seller":
        deal.status = DealStatus.completed
        deal.completed_at = datetime.utcnow()
        deal.channel.status = ChannelStatus.sold
        # TODO: release USDT to seller
    else:
        raise HTTPException(status_code=400, detail="Invalid resolution")

    await db.commit()
    await db.refresh(deal)

    return DealResponse(
        id=deal.id, channel_id=deal.channel_id, buyer_id=deal.buyer_id, seller_id=deal.seller_id,
        channel_name=deal.channel.channel_name if deal.channel else None,
        buyer_name=deal.buyer.first_name if deal.buyer else None,
        seller_name=deal.seller.first_name if deal.seller else None,
        status=deal.status.value, escrow_wallet_address=deal.escrow_wallet_address,
        amount_usdt=deal.amount_usdt, service_fee=deal.service_fee,
        deal_group_chat_id=deal.deal_group_chat_id, dispute_reason=deal.dispute_reason,
        created_at=deal.created_at, paid_at=deal.paid_at, completed_at=deal.completed_at,
    )


@router.post("/deals/{deal_id}/cancel", response_model=DealResponse)
async def admin_cancel_deal(
    deal_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin force-cancel a deal (any non-completed status)."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.status in (DealStatus.completed, DealStatus.cancelled):
        raise HTTPException(status_code=400, detail="Deal is already completed or cancelled")

    deal.status = DealStatus.cancelled
    # Restore channel availability
    if deal.channel:
        deal.channel.status = ChannelStatus.approved

    await db.commit()
    await db.refresh(deal)

    return DealResponse(
        id=deal.id, channel_id=deal.channel_id, buyer_id=deal.buyer_id, seller_id=deal.seller_id,
        channel_name=deal.channel.channel_name if deal.channel else None,
        buyer_name=deal.buyer.first_name if deal.buyer else None,
        seller_name=deal.seller.first_name if deal.seller else None,
        status=deal.status.value, escrow_wallet_address=deal.escrow_wallet_address,
        amount_usdt=deal.amount_usdt, service_fee=deal.service_fee,
        deal_group_chat_id=deal.deal_group_chat_id, dispute_reason=deal.dispute_reason,
        created_at=deal.created_at, paid_at=deal.paid_at, completed_at=deal.completed_at,
    )


@router.post("/users/{user_id}/role")
async def set_user_role(
    user_id: int,
    role: str,
    admin: User = Depends(get_admin_user),
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

    target.role = UserRole(role)
    await db.commit()
    await db.refresh(target)

    return {"id": target.id, "username": target.username, "role": target.role.value}


@router.get("/users")
async def list_users(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin/moderator only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "first_name": u.first_name,
            "role": u.role.value,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


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

    daily_stats = stats.get("daily_stats", [])
    new_records = 0
    if daily_stats:
        existing = await db.execute(
            select(ChannelStats.date).where(ChannelStats.channel_id == channel.id)
        )
        existing_dates = {d.strftime("%Y-%m-%d") for d in existing.scalars().all()}

        for ds in daily_stats:
            if ds["date"] not in existing_dates:
                db.add(ChannelStats(
                    channel_id=channel.id,
                    date=datetime.strptime(ds["date"], "%Y-%m-%d"),
                    subscribers=ds.get("subscribers", 0),
                    avg_views=ds.get("avg_views", 0),
                    avg_reach=ds.get("avg_views", 0),
                    er=ds.get("er", 0.0),
                    post_count=ds.get("post_count", 0),
                ))
                new_records += 1

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

            daily_stats = stats.get("daily_stats", [])
            new_records = 0
            if daily_stats:
                existing = await db.execute(
                    select(ChannelStats.date).where(ChannelStats.channel_id == channel.id)
                )
                existing_dates = {d.strftime("%Y-%m-%d") for d in existing.scalars().all()}

                for ds in daily_stats:
                    if ds["date"] not in existing_dates:
                        db.add(ChannelStats(
                            channel_id=channel.id,
                            date=datetime.strptime(ds["date"], "%Y-%m-%d"),
                            subscribers=ds.get("subscribers", 0),
                            avg_views=ds.get("avg_views", 0),
                            avg_reach=ds.get("avg_views", 0),
                            er=ds.get("er", 0.0),
                            post_count=ds.get("post_count", 0),
                        ))
                        new_records += 1

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
    to_address: str = Body(..., embed=True),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Sweep USDT from an escrow wallet to a target address.

    Steps: check balance → send TRX for gas → wait → transfer USDT → sweep leftover TRX back.
    """
    import asyncio
    from app.services.escrow import get_usdt_balance, send_trx_for_gas, transfer_usdt, sweep_trx_to_master

    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    escrow_addr = deal.escrow_wallet_address
    encrypted_key = deal.escrow_private_key_encrypted

    # 1. Check USDT balance
    balance = get_usdt_balance(escrow_addr)
    if balance <= 0:
        return {"ok": False, "error": f"Escrow {escrow_addr} has 0 USDT"}

    # 2. Send TRX for gas (from master wallet) — reduced to 7 TRX
    gas_tx = send_trx_for_gas(escrow_addr, amount_trx=7)
    if not gas_tx:
        return {"ok": False, "error": "Failed to send TRX for gas. Is master wallet funded with TRX?"}

    # 3. Wait for TRX to confirm
    await asyncio.sleep(6)

    # 4. Transfer USDT
    tx_hash = transfer_usdt(encrypted_key, to_address, balance)
    if not tx_hash:
        return {"ok": False, "error": "USDT transfer failed. Check logs for details."}

    # 5. Wait for USDT transfer to confirm, then sweep leftover TRX back to master
    await asyncio.sleep(6)
    trx_sweep_tx = sweep_trx_to_master(encrypted_key)

    return {
        "ok": True,
        "deal_id": deal_id,
        "escrow": escrow_addr,
        "to": to_address,
        "amount_usdt": balance,
        "gas_tx": gas_tx,
        "usdt_tx": tx_hash,
        "trx_sweep_tx": trx_sweep_tx,
    }


@router.get("/escrow/balances")
async def check_escrow_balances(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Check USDT balances of all escrow wallets."""
    from app.services.escrow import get_usdt_balance

    result = await db.execute(
        select(Deal).order_by(Deal.id.desc())
    )
    deals = result.scalars().all()

    balances = []
    for deal in deals:
        balance = get_usdt_balance(deal.escrow_wallet_address)
        if balance > 0:
            balances.append({
                "deal_id": deal.id,
                "escrow": deal.escrow_wallet_address,
                "balance_usdt": balance,
                "status": deal.status.value,
            })

    return {"wallets_with_funds": balances, "total": sum(b["balance_usdt"] for b in balances)}


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
            "channel_avatar": a.channel.avatar_url if a.channel else None,
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
        select(func.count()).select_from(Channel).where(Channel.status == "pending")
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
    }
