import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.channel import Channel, ChannelPost, ChannelStats, ChannelStatus
from app.models.user import User
from app.schemas.channel import (
    ChannelCreate,
    ChannelListResponse,
    ChannelPostResponse,
    ChannelPostsListResponse,
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


@router.get("/{channel_id}/posts", response_model=ChannelPostsListResponse)
async def get_channel_posts(
    channel_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get individual posts for a channel with detailed stats."""
    # Verify channel exists
    ch = await db.execute(select(Channel.id).where(Channel.id == channel_id))
    if not ch.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Channel not found")

    # Count total
    total_result = await db.execute(
        select(func.count()).select_from(ChannelPost).where(
            ChannelPost.channel_id == channel_id
        )
    )
    total = total_result.scalar() or 0

    # Get posts sorted by date desc (newest first)
    result = await db.execute(
        select(ChannelPost)
        .where(ChannelPost.channel_id == channel_id)
        .order_by(ChannelPost.date.desc())
        .offset(offset)
        .limit(limit)
    )
    posts = result.scalars().all()

    return ChannelPostsListResponse(
        items=[ChannelPostResponse.model_validate(p) for p in posts],
        total=total,
    )


@router.get("/{channel_id}/health")
async def get_channel_health(channel_id: int, db: AsyncSession = Depends(get_db)):
    """Analyze channel health: bot detection, engagement quality, view patterns."""
    from app.schemas.channel import ChannelHealthResponse

    # Get channel
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    subs = channel.subscribers_count or 0
    avg_views = channel.avg_views or 0
    er = channel.er or 0.0
    views_hidden = channel.views_hidden

    # Get posts with view dynamics
    result = await db.execute(
        select(ChannelPost)
        .where(ChannelPost.channel_id == channel_id)
        .order_by(ChannelPost.date.desc())
        .limit(100)
    )
    posts = result.scalars().all()

    flags = []
    score = 50  # start neutral
    posts_analyzed = len(posts)
    suspicious_posts = 0

    # ── 1. View velocity analysis (bot detection) ──
    # If 90%+ views come in the first hour → likely bot views
    velocity_ratios = []
    if not views_hidden:
        for p in posts:
            if p.views_1h and p.views and p.views > 0:
                ratio = p.views_1h / p.views
                velocity_ratios.append(ratio)
                if ratio > 0.9:
                    suspicious_posts += 1

    avg_velocity = sum(velocity_ratios) / len(velocity_ratios) if velocity_ratios else None

    if avg_velocity is not None:
        if avg_velocity > 0.85:
            view_velocity_label = "Накрутка"
            score -= 30
            flags.append("⚠️ 90%+ переглядів за першу годину — ознака ботів")
        elif avg_velocity > 0.7:
            view_velocity_label = "Підозріло"
            score -= 15
            flags.append("⚡ Висока швидкість набору переглядів")
        else:
            view_velocity_label = "Нормально"
            score += 10
    else:
        view_velocity_label = "Приховані" if views_hidden else "Немає даних"

    # ── 2. Subscriber-to-views ratio ──
    if views_hidden:
        views_to_subs = None
        activity_label = "Перегляди приховані"
        flags.append("ℹ️ Лічильник переглядів вимкнено адміном каналу")
    elif subs > 0 and avg_views > 0:
        views_to_subs = avg_views / subs * 100
        if views_to_subs < 1:
            activity_label = "Мертвий канал"
            score -= 30
            flags.append(f"💀 Лише {views_to_subs:.1f}% підписників бачать пости")
        elif views_to_subs < 5:
            activity_label = "Низька активність"
            score -= 15
            flags.append(f"📉 Низький охват: {views_to_subs:.1f}% підписників")
        elif views_to_subs < 20:
            activity_label = "Нормальна активність"
            score += 10
        else:
            activity_label = "Високий охват"
            score += 15
    else:
        views_to_subs = None
        activity_label = "Немає даних"

    # ── 3. ER analysis ──
    if er > 0:
        if er < 1:
            er_label = "Дуже низький"
            score -= 10
        elif er < 5:
            er_label = "Низький"
        elif er < 15:
            er_label = "Нормальний"
            score += 10
        elif er < 30:
            er_label = "Високий"
            score += 15
        else:
            er_label = "Підозріло високий"
            score -= 5
            flags.append("🤔 Надзвичайно високий ER — можлива накрутка реакцій")
    else:
        er_label = "Немає даних"

    # ── 4. Posts with zero/very low views ──
    if posts_analyzed > 0 and not views_hidden:
        dead_posts = sum(1 for p in posts if p.views < 10)
        dead_ratio = dead_posts / posts_analyzed
        if dead_ratio > 0.5:
            score -= 15
            flags.append(f"👻 {int(dead_ratio*100)}% постів з менше 10 переглядами")

    # ── 5. View consistency check ──
    if posts_analyzed >= 5 and not views_hidden:
        view_list = [p.views for p in posts if p.views > 0]
        if view_list:
            avg_v = sum(view_list) / len(view_list)
            max_v = max(view_list)
            min_v = min(view_list)
            if avg_v > 0 and max_v > avg_v * 10:
                flags.append("📊 Великий розкид переглядів — можливо рекламні пости")
            if avg_v > 0 and min_v < avg_v * 0.05:
                flags.append("📉 Деякі пости з мізерними переглядами")

    # Clamp score
    score = max(0, min(100, score))

    # Overall health label
    if score >= 70:
        health_label = "Здоровий"
    elif score >= 40:
        health_label = "Підозрілий"
    else:
        health_label = "Мертвий канал"

    if not flags:
        flags.append("✅ Підозрілих ознак не виявлено")

    return ChannelHealthResponse(
        health_score=score,
        health_label=health_label,
        views_1h_ratio=round(avg_velocity * 100, 1) if avg_velocity is not None else None,
        view_velocity_label=view_velocity_label,
        views_to_subs_ratio=round(views_to_subs, 1) if views_to_subs is not None else None,
        activity_label=activity_label,
        er=er if er else None,
        er_label=er_label,
        avg_views=avg_views if avg_views else None,
        subscribers=subs if subs else None,
        posts_analyzed=posts_analyzed,
        suspicious_posts=suspicious_posts,
        flags=flags,
    )


@router.get("/{channel_id}/ai-analysis")
async def get_ai_analysis(channel_id: int, db: AsyncSession = Depends(get_db)):
    """Get AI-powered deep analysis of a channel using Google Gemini."""
    from app.services.ai_analysis import analyze_channel

    # Get channel
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Prepare channel data dict
    channel_data = {
        "channel_name": channel.channel_name,
        "category": channel.category,
        "subscribers_count": channel.subscribers_count,
        "avg_views": channel.avg_views,
        "er": channel.er,
        "price": channel.price,
        "monthly_income": channel.monthly_income,
        "age": channel.age,
        "total_posts": channel.total_posts,
        "post_frequency": channel.post_frequency,
        "avg_forwards": channel.avg_forwards,
        "avg_reactions": channel.avg_reactions,
        "telegram_link": channel.telegram_link,
        "description": channel.description,
        "views_hidden": channel.views_hidden,
    }

    # Get last 20 posts for AI analysis
    posts_result = await db.execute(
        select(ChannelPost)
        .where(ChannelPost.channel_id == channel_id)
        .order_by(ChannelPost.date.desc())
        .limit(20)
    )
    posts = posts_result.scalars().all()
    posts_data = [
        {
            "text": p.text,
            "views": p.views,
            "reactions": p.reactions,
            "forwards": p.forwards,
            "media_type": p.media_type,
        }
        for p in posts
    ]

    # Get stats history
    stats_result = await db.execute(
        select(ChannelStats)
        .where(ChannelStats.channel_id == channel_id)
        .order_by(ChannelStats.date.asc())
    )
    stats = stats_result.scalars().all()
    stats_data = [
        {
            "date": s.date.isoformat() if s.date else None,
            "subscribers": s.subscribers,
            "avg_views": s.avg_views,
            "er": s.er,
        }
        for s in stats
    ]

    analysis = await analyze_channel(channel_data, posts_data, stats_data)
    if analysis is None:
        raise HTTPException(status_code=503, detail="AI analysis unavailable")
    if "error" in analysis:
        raise HTTPException(status_code=503, detail=analysis.get("detail", "AI analysis error"))

    return analysis


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
            listing_type=body.listing_type or "sale",
            auction_start_price=body.auction_start_price,
            auction_bid_step=body.auction_bid_step,
            auction_duration_hours=body.auction_duration_hours,
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
                channel.last_post_date = dt2.fromisoformat(stats["last_post_date"]).replace(tzinfo=None)
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
                    subscribers=ds.get("subscribers") or 0,
                    avg_views=ds.get("avg_views") or 0,
                    avg_reach=ds.get("avg_views") or 0,
                    er=ds.get("er") or 0.0,
                    post_count=ds.get("post_count") or 0,
                )
                db.add(stat_record)
        else:
            # Fallback: save single current record
            stat_record = ChannelStats(
                channel_id=channel.id,
                date=dt.utcnow(),
                subscribers=stats.get("subscribers_count") or 0,
                avg_views=stats.get("avg_views") or 0,
                avg_reach=stats.get("avg_views") or 0,
                er=stats.get("er") or 0.0,
                post_count=0,
            )
            db.add(stat_record)
        await db.commit()

        # Save individual posts
        posts_data = stats.get("posts", [])
        if posts_data:
            for p in posts_data:
                post_date = dt.fromisoformat(p["date"]) if isinstance(p["date"], str) else p["date"]
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
            await db.commit()

        await db.refresh(channel)
    except Exception as e:
        logger.warning(f"Stats fetching failed for channel #{channel.id}: {e}")
        # Re-fetch channel to ensure it's attached to session
        result = await db.execute(select(Channel).where(Channel.id == channel.id))
        channel = result.scalar_one_or_none()

    # Notify admin about new channel for moderation
    try:
        from aiogram import Bot
        from aiogram.enums import ParseMode
        from app.config import settings as cfg
        if cfg.admin_group_id and cfg.bot_token_alerts:
            bot = Bot(token=cfg.bot_token_alerts)
            listing_label = {"sale": "Каталог", "auction": "Аукціон", "both": "Каталог + Аукціон"}.get(channel.listing_type, "Каталог")
            admin_text = (
                f"📺 <b>Новий канал на модерацію!</b>\n\n"
                f"Канал: {channel.channel_name or channel.telegram_link}\n"
                f"Продавець: {user.first_name} (id={user.id})\n"
                f"Тип: {listing_label}\n"
                f"Ціна: {channel.price} USDT"
            )
            await bot.send_message(cfg.admin_group_id, admin_text, parse_mode=ParseMode.HTML)
            await bot.session.close()
            logger.info(f"[CHANNEL] Admin notified about new channel #{channel.id}")
    except Exception as e:
        logger.error(f"[CHANNEL] Failed to notify admin about channel #{channel.id}: {e}")

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
