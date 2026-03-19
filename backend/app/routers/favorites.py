from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.channel import Channel, ChannelStatus, Favorite
from app.models.user import User
from app.schemas.channel import ChannelResponse
from app.utils.security import get_current_user

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=list[ChannelResponse])
async def get_favorites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all favorite channels for current user."""
    result = await db.execute(
        select(Channel)
        .join(Favorite, Favorite.channel_id == Channel.id)
        .where(Favorite.user_id == user.id, Channel.status == ChannelStatus.approved)
        .order_by(Favorite.created_at.desc())
    )
    return [ChannelResponse.model_validate(c) for c in result.scalars().all()]


@router.get("/ids", response_model=list[int])
async def get_favorite_ids(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of favorite channel IDs for current user."""
    result = await db.execute(
        select(Favorite.channel_id).where(Favorite.user_id == user.id)
    )
    return list(result.scalars().all())


@router.post("/{channel_id}", status_code=status.HTTP_201_CREATED)
async def add_favorite(
    channel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add channel to favorites."""
    # Check channel exists
    ch = await db.get(Channel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Check if already favorited
    existing = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id, Favorite.channel_id == channel_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already in favorites")

    db.add(Favorite(user_id=user.id, channel_id=channel_id))
    await db.commit()
    return {"ok": True}


@router.delete("/{channel_id}")
async def remove_favorite(
    channel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove channel from favorites."""
    result = await db.execute(
        delete(Favorite).where(
            Favorite.user_id == user.id, Favorite.channel_id == channel_id
        )
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not in favorites")
    return {"ok": True}
