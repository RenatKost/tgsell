"""Lightweight tab counters for the user cabinet (/cabinet). COUNT queries only."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.auction import Auction
from app.models.bundle import ChannelBundle
from app.models.channel import Channel, ChannelStatus, Favorite
from app.models.deal import Deal
from app.models.saved_search import SavedSearch
from app.models.user import User
from app.utils.security import get_current_user

router = APIRouter(prefix="/me", tags=["me"])


async def _count(db: AsyncSession, stmt) -> int:
    return int((await db.execute(stmt)).scalar() or 0)


@router.get("/counts")
async def my_counts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Counters for cabinet tabs; semantics match the lists each tab shows."""
    uid = user.id
    return {
        # «Мої оголошення»: owner sees own channels in every status
        "listings": await _count(db, select(func.count(Channel.id)).where(Channel.seller_id == uid)),
        "bundles": await _count(db, select(func.count(ChannelBundle.id)).where(ChannelBundle.seller_id == uid)),
        "auctions": await _count(db, select(func.count(Auction.id)).where(Auction.seller_id == uid)),
        "deals": await _count(db, select(func.count(Deal.id)).where(
            or_(Deal.buyer_id == uid, Deal.seller_id == uid))),
        # «Обране» lists only approved channels
        "favorites": await _count(db, select(func.count(Favorite.id)).join(
            Channel, Channel.id == Favorite.channel_id).where(
            Favorite.user_id == uid, Channel.status == ChannelStatus.approved)),
        "saved_searches": await _count(db, select(func.count(SavedSearch.id)).where(SavedSearch.user_id == uid)),
    }


@router.get("/referral")
async def my_referral(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """«Приведи продавця»: own referral link + reward counters."""
    from app.services.referral import summary
    return await summary(db, user)
