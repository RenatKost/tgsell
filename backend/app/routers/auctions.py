"""Auction API — list, detail, bid, stats."""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.auction import Auction, AuctionBid, AuctionStatus
from app.models.channel import Channel
from app.models.deal import Deal
from app.models.user import User
from app.schemas.auction import (
    AuctionBidCreate,
    AuctionBidResponse,
    AuctionDetailResponse,
    AuctionListResponse,
    AuctionResponse,
)
from app.utils.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auctions", tags=["auctions"])


def _auction_to_response(auction: Auction) -> AuctionResponse:
    channel = auction.channel
    return AuctionResponse(
        id=auction.id,
        channel_id=auction.channel_id,
        seller_id=auction.seller_id,
        start_price=auction.start_price,
        bid_step=auction.bid_step,
        current_price=auction.current_price,
        buyout_price=auction.buyout_price,
        status=auction.status,
        starts_at=auction.starts_at,
        ends_at=auction.ends_at,
        winner_id=auction.winner_id,
        bid_count=auction.bid_count,
        created_at=auction.created_at,
        channel_name=channel.channel_name if channel else None,
        channel_avatar=channel.avatar_url if channel else None,
        subscribers_count=channel.subscribers_count if channel else None,
        category=channel.category if channel else None,
    )


@router.get("", response_model=AuctionListResponse)
async def list_auctions(
    category: str = Query("", max_length=100),
    sort: str = Query("ending_soon"),
    status_filter: str = Query("active", alias="status"),
    seller_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List auctions with filters."""
    query = (
        select(Auction)
        .options(selectinload(Auction.channel))
    )

    if seller_id:
        query = query.where(Auction.seller_id == seller_id)
    else:
        query = query.where(Auction.status == status_filter)

    if category:
        query = query.join(Channel).where(Channel.category == category)

    if sort == "ending_soon":
        query = query.order_by(Auction.ends_at.asc())
    elif sort == "price_asc":
        query = query.order_by(Auction.current_price.asc())
    elif sort == "price_desc":
        query = query.order_by(Auction.current_price.desc())
    elif sort == "bids":
        query = query.order_by(Auction.bid_count.desc())
    else:
        query = query.order_by(Auction.created_at.desc())

    result = await db.execute(query)
    auctions = result.scalars().all()

    return AuctionListResponse(
        items=[_auction_to_response(a) for a in auctions],
        total=len(auctions),
    )


@router.get("/stats")
async def auction_stats(db: AsyncSession = Depends(get_db)):
    """Gamification stats for display."""
    active_count = (await db.execute(
        select(func.count()).select_from(Auction).where(Auction.status == "active")
    )).scalar() or 0

    total_bids = (await db.execute(
        select(func.count()).select_from(AuctionBid)
    )).scalar() or 0

    total_deals = (await db.execute(
        select(func.count()).select_from(Deal)
    )).scalar() or 0

    total_channels = (await db.execute(
        select(func.count()).select_from(Channel).where(Channel.status == "approved")
    )).scalar() or 0

    return {
        "active_auctions": active_count,
        "total_bids": total_bids,
        "total_deals": total_deals,
        "total_channels": total_channels,
    }


@router.get("/{auction_id}", response_model=AuctionDetailResponse)
async def get_auction(auction_id: int, db: AsyncSession = Depends(get_db)):
    """Get auction details with bid history."""
    result = await db.execute(
        select(Auction)
        .options(selectinload(Auction.channel), selectinload(Auction.bids))
        .where(Auction.id == auction_id)
    )
    auction = result.scalar_one_or_none()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")

    # Build bid responses with bidder names
    bid_responses = []
    for bid in auction.bids[:50]:  # Last 50 bids
        bidder = await db.get(User, bid.bidder_id)
        bid_responses.append(AuctionBidResponse(
            id=bid.id,
            auction_id=bid.auction_id,
            bidder_id=bid.bidder_id,
            bidder_name=bidder.first_name if bidder else None,
            amount=bid.amount,
            created_at=bid.created_at,
        ))

    resp = _auction_to_response(auction)
    return AuctionDetailResponse(
        **resp.model_dump(),
        bids=bid_responses,
    )


@router.post("/{auction_id}/bid", response_model=AuctionBidResponse)
async def place_bid(
    auction_id: int,
    body: AuctionBidCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Place a bid on an auction."""
    result = await db.execute(
        select(Auction).where(Auction.id == auction_id)
    )
    auction = result.scalar_one_or_none()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")

    if auction.status != "active":
        raise HTTPException(status_code=400, detail="Аукціон не активний")

    if datetime.utcnow() > auction.ends_at:
        raise HTTPException(status_code=400, detail="Аукціон завершено")

    if user.id == auction.seller_id:
        raise HTTPException(status_code=400, detail="Продавець не може робити ставки")

    min_bid = auction.current_price + auction.bid_step
    if body.amount < min_bid:
        raise HTTPException(
            status_code=400,
            detail=f"Мінімальна ставка: {min_bid} USDT"
        )

    # Buyout check
    is_buyout = auction.buyout_price and body.amount >= auction.buyout_price

    # Create bid
    bid = AuctionBid(
        auction_id=auction.id,
        bidder_id=user.id,
        amount=body.amount,
    )
    db.add(bid)

    # Update auction
    auction.current_price = body.amount
    auction.bid_count += 1
    auction.winner_id = user.id

    if is_buyout:
        # Instant buyout — end auction
        auction.status = "ended"
        auction.ends_at = datetime.utcnow()
    else:
        # Anti-sniping: extend by 2 min if bid in last 2 min
        time_left = (auction.ends_at - datetime.utcnow()).total_seconds()
        if time_left < 120:
            auction.ends_at = datetime.utcnow() + timedelta(minutes=2)

    await db.commit()
    await db.refresh(bid)

    return AuctionBidResponse(
        id=bid.id,
        auction_id=bid.auction_id,
        bidder_id=bid.bidder_id,
        bidder_name=user.first_name,
        amount=bid.amount,
        created_at=bid.created_at,
    )
