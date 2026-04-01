import logging
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=ChannelListResponse)
async def list_channels(
    search: str = Query("", max_length=100),
    category: str = Query("", max_length=100),
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=100),
    seller_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    """List channels with filters, search, sorting and pagination."""
    query = select(Channel)

    if seller_id:
        # Show all channels for a specific seller (any status)
        query = query.where(Channel.seller_id == seller_id)
        if status_filter:
            query = query.where(Channel.status == status_filter)
    else:
        # Public listing — only approved
        query = query.where(Channel.status == ChannelStatus.approved)

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
    # Normalize link and check for duplicates
    import re
    clean_link = re.sub(r'^(https?://)?(t\.me/|@)', '', body.telegram_link.strip()).strip('/')
    logger.info(f"[CHANNEL] Create request from user={user.id}: link='{body.telegram_link}', clean='{clean_link}'")
    if clean_link:
        existing = await db.execute(
            select(Channel).where(
                Channel.telegram_link.ilike(f"%{clean_link}%"),
                Channel.status.in_([ChannelStatus.pending, ChannelStatus.approved]),
            )
        )
        if existing.scalar_one_or_none():
            logger.warning(f"[CHANNEL] Duplicate channel rejected: '{clean_link}' from user={user.id}")
            raise HTTPException(status_code=409, detail="Цей канал вже розміщений на біржі")

    try:
        channel = Channel(
            seller_id=user.id,
            telegram_link=body.telegram_link,
            channel_name=body.channel_name or body.telegram_link,
            seller_telegram=body.seller_telegram,
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
    except Exception as e:
        logger.error(f"Channel creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Помилка збереження: {e}")

    # Fetch channel stats from Telegram
    try:
        from app.services.channel_stats import collect_channel_stats
        from datetime import datetime as dt

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
        if stats.get("total_posts"):
            channel.total_posts = stats["total_posts"]
        if stats.get("post_frequency") is not None:
            channel.post_frequency = stats["post_frequency"]
        if stats.get("last_post_date"):
            from datetime import datetime as dt2
            try:
                channel.last_post_date = dt2.fromisoformat(stats["last_post_date"])
            except (ValueError, TypeError):
                pass
        if stats.get("avg_forwards"):
            channel.avg_forwards = stats["avg_forwards"]
        if stats.get("avg_reactions"):
            channel.avg_reactions = stats["avg_reactions"]

        # Save historical daily stats for graphs
        daily_stats = stats.get("daily_stats", [])
        if daily_stats:
            for ds in daily_stats:
                stat_record = ChannelStats(
                    channel_id=channel.id,
                    date=dt.strptime(ds["date"], "%Y-%m-%d"),
                    subscribers=ds.get("subscribers", 0),
                    avg_views=ds.get("avg_views", 0),
                    avg_reach=ds.get("avg_views", 0),
                    er=ds.get("er", 0.0),
                    post_count=ds.get("post_count", 0),
                )
                db.add(stat_record)
        else:
            # Fallback: save single current record
            stat_record = ChannelStats(
                channel_id=channel.id,
                date=dt.utcnow(),
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
        logger.warning(f"Stats fetching failed for channel #{channel.id}: {e}")
        # Re-fetch channel to ensure it's attached to session
        result = await db.execute(select(Channel).where(Channel.id == channel.id))
        channel = result.scalar_one_or_none()

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
