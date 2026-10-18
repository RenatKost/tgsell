from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealStatus
from app.models.user import User
from app.schemas.auth import OwnerUserProfile, PublicUserProfile
from app.utils.security import get_optional_user, is_admin

router = APIRouter(prefix="/users", tags=["users"])


async def _count(db: AsyncSession, stmt) -> int:
    return int((await db.execute(stmt)).scalar() or 0)


@router.get("/{user_id}/profile", response_model=OwnerUserProfile | PublicUserProfile)
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    """Public profile. Private fields (telegram_id, google_id, email, usdt_wallet, role)
    are returned only to the profile owner or an admin."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    counters = {
        "channels_listed": await _count(db, select(func.count(Channel.id)).where(
            Channel.seller_id == user.id, Channel.status.in_([ChannelStatus.approved, ChannelStatus.sold]))),
        "deals_completed_as_seller": await _count(db, select(func.count(Deal.id)).where(
            Deal.seller_id == user.id, Deal.status == DealStatus.completed)),
        "deals_completed_as_buyer": await _count(db, select(func.count(Deal.id)).where(
            Deal.buyer_id == user.id, Deal.status == DealStatus.completed)),
    }
    base = {
        "id": user.id, "username": user.username, "first_name": user.first_name,
        "avatar_url": user.avatar_url, "created_at": user.created_at,
        "is_blocked": bool(user.is_blocked), **counters,
    }
    if viewer is not None and (viewer.id == user.id or is_admin(viewer)):
        return OwnerUserProfile(
            **base, telegram_id=user.telegram_id, google_id=user.google_id, email=user.email,
            usdt_wallet=user.usdt_wallet, role=getattr(user.role, "value", user.role),
        )
    return PublicUserProfile(**base)
