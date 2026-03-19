from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealStatus
from app.models.user import User
from app.schemas.deal import DealCreate, DealDisputeRequest, DealResponse
from app.services.escrow import generate_escrow_wallet
from app.utils.security import get_current_user

router = APIRouter(prefix="/deals", tags=["deals"])


def _deal_to_response(deal: Deal, channel: Channel | None = None, buyer: User | None = None, seller: User | None = None) -> DealResponse:
    return DealResponse(
        id=deal.id,
        channel_id=deal.channel_id,
        buyer_id=deal.buyer_id,
        seller_id=deal.seller_id,
        channel_name=channel.channel_name if channel else None,
        buyer_name=buyer.first_name if buyer else None,
        seller_name=seller.first_name if seller else None,
        status=deal.status.value,
        escrow_wallet_address=deal.escrow_wallet_address,
        amount_usdt=deal.amount_usdt,
        service_fee=deal.service_fee,
        deal_group_chat_id=deal.deal_group_chat_id,
        dispute_reason=deal.dispute_reason,
        created_at=deal.created_at,
        paid_at=deal.paid_at,
        completed_at=deal.completed_at,
    )


@router.post("", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    body: DealCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiate a purchase — create a deal with escrow wallet."""
    # Get channel
    result = await db.execute(select(Channel).where(Channel.id == body.channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status != ChannelStatus.approved:
        raise HTTPException(status_code=400, detail="Channel is not available for purchase")
    if channel.seller_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own channel")

    # Check no active deal for this channel
    existing = await db.execute(
        select(Deal).where(
            Deal.channel_id == body.channel_id,
            Deal.status.in_([
                DealStatus.created, DealStatus.payment_pending,
                DealStatus.paid, DealStatus.channel_transferring,
            ]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Channel already has an active deal")

    # Generate escrow wallet
    wallet_address, encrypted_private_key = generate_escrow_wallet()

    # Calculate fee
    fee = channel.price * (settings.service_fee_percent / 100)

    deal = Deal(
        channel_id=channel.id,
        buyer_id=user.id,
        seller_id=channel.seller_id,
        status=DealStatus.created,
        escrow_wallet_address=wallet_address,
        escrow_private_key_encrypted=encrypted_private_key,
        amount_usdt=channel.price,
        service_fee=fee,
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)

    # TODO: trigger Telegram bot to create deal group

    # Get seller for response
    seller_result = await db.execute(select(User).where(User.id == channel.seller_id))
    seller = seller_result.scalar_one_or_none()

    return _deal_to_response(deal, channel, user, seller)


@router.get("/my", response_model=list[DealResponse])
async def get_my_deals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all deals where user is buyer or seller."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(or_(Deal.buyer_id == user.id, Deal.seller_id == user.id))
        .order_by(Deal.created_at.desc())
    )
    deals = result.scalars().all()
    return [_deal_to_response(d, d.channel, d.buyer, d.seller) for d in deals]


@router.get("/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get deal details (only buyer/seller/admin can see)."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id and user.role not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Access denied")

    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


@router.post("/{deal_id}/confirm-transfer", response_model=DealResponse)
async def confirm_transfer(
    deal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Buyer confirms they received the channel. Triggers payout to seller."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id:
        raise HTTPException(status_code=403, detail="Only buyer can confirm transfer")
    if deal.status != DealStatus.paid:
        raise HTTPException(status_code=400, detail="Deal is not in paid status")

    deal.status = DealStatus.completed
    deal.completed_at = datetime.now(timezone.utc)

    # Mark channel as sold
    deal.channel.status = ChannelStatus.sold

    await db.commit()
    await db.refresh(deal)

    # TODO: trigger USDT payout to seller in background task

    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


@router.post("/{deal_id}/dispute", response_model=DealResponse)
async def open_dispute(
    deal_id: int,
    body: DealDisputeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a dispute on a deal."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Only deal participants can dispute")
    if deal.status not in (DealStatus.paid, DealStatus.channel_transferring):
        raise HTTPException(status_code=400, detail="Cannot dispute this deal")

    deal.status = DealStatus.disputed
    deal.dispute_reason = body.reason
    await db.commit()
    await db.refresh(deal)

    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)
