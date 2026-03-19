import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.channel import Channel, ChannelStats, ChannelStatus
from app.models.user import User
from app.schemas.channel import (
    ChannelCreate,
    ChannelListResponse,
    ChannelResponse,
    ChannelStatsResponse,
    ChannelUpdate,
)
from app.utils.security import get_current_user

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=ChannelListResponse)
async def list_channels(
    search: str = Query("", max_length=100),
    category: str = Query("", max_length=100),
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List approved channels with filters, search, sorting and pagination."""
    query = select(Channel).where(Channel.status == ChannelStatus.approved)

    if search:
        query = query.where(Channel.channel_name.ilike(f"%{search}%"))
    if category:
        query = query.where(Channel.category == category)

    # Sorting
    if sort == "price_asc":
        query = query.order_by(Channel.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Channel.price.desc())
    elif sort == "subscribers_desc":
        query = query.order_by(Channel.subscribers_count.desc())
    else:
        query = query.order_by(Channel.created_at.desc())

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    total_pages = max(1, math.ceil(total / limit))

    # Paginate
    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    channels = result.scalars().all()

    return ChannelListResponse(
        items=[ChannelResponse.model_validate(c) for c in channels],
        total=total,
        total_pages=total_pages,
        page=page,
    )


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    """Get channel details by ID."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ChannelResponse.model_validate(channel)


@router.get("/{channel_id}/stats", response_model=list[ChannelStatsResponse])
async def get_channel_stats(channel_id: int, db: AsyncSession = Depends(get_db)):
    """Get historical stats for a channel."""
    result = await db.execute(
        select(ChannelStats)
        .where(ChannelStats.channel_id == channel_id)
        .order_by(ChannelStats.date.asc())
    )
    stats = result.scalars().all()
    return [ChannelStatsResponse.model_validate(s) for s in stats]


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new channel listing (goes to moderation)."""
    channel = Channel(
        seller_id=user.id,
        telegram_link=body.telegram_link,
        channel_name=body.channel_name,
        category=body.category,
        price=body.price,
        monthly_income=body.monthly_income,
        description=body.description,
        resources=body.resources,
        status=ChannelStatus.pending,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)

    # TODO: trigger background task to fetch channel stats via Telethon/Bot API

    return ChannelResponse.model_validate(channel)


@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    body: ChannelUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a channel listing (owner only)."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.seller_id != user.id and user.role not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Not your channel")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(channel, field, value)

    await db.commit()
    await db.refresh(channel)
    return ChannelResponse.model_validate(channel)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a channel listing (owner only)."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.seller_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your channel")
    if channel.status == ChannelStatus.sold:
        raise HTTPException(status_code=400, detail="Cannot delete sold channel")

    await db.delete(channel)
    await db.commit()
