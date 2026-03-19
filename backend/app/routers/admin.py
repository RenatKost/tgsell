import logging
from datetime import datetime, timezone
import os

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealStatus
from app.models.user import User, UserRole
from app.schemas.channel import ChannelResponse
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

            stat_record = ChannelStats(
                channel_id=channel.id,
                date=datetime.utcnow(),
                subscribers=stats.get("subscribers_count", 0),
                avg_views=stats.get("avg_views", 0),
                avg_reach=stats.get("avg_views", 0),
                er=stats.get("er", 0.0),
            )
            db.add(stat_record)
            await db.commit()
            await db.refresh(channel)
        except Exception as e:
            logger.warning(f"Stats refresh on approve failed for channel #{channel_id}: {e}")

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
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all deals (admin only)."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .order_by(Deal.created_at.desc())
    )
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
