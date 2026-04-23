"""Channel bundle router — create, list, detail, stats."""
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
from app.models.channel import Channel, ChannelStatus
from app.schemas.bundle import (
    BundleCreate,
    BundleListResponse,
    BundleResponse,
    BundleStatsResponse,
    BundleUpdate,
    BundleChannelInfo,
)
from app.utils.security import get_current_user
from app.models.user import User
from app.services.ai_analysis import analyze_bundle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bundles", tags=["bundles"])


def _channel_to_info(channel: Channel) -> BundleChannelInfo:
    return BundleChannelInfo(
        id=channel.id,
        channel_name=channel.channel_name,
        telegram_link=channel.telegram_link,
        avatar_url=channel.avatar_url,
        subscribers_count=channel.subscribers_count or 0,
        avg_views=channel.avg_views,
        er=channel.er,
        category=channel.category or "",
    )


def _bundle_to_response(bundle: ChannelBundle) -> BundleResponse:
    channels = [
        _channel_to_info(bc.channel)
        for bc in (bundle.bundle_channels or [])
        if bc.channel is not None
    ]
    return BundleResponse(
        id=bundle.id,
        seller_id=bundle.seller_id,
        name=bundle.name,
        description=bundle.description,
        category=bundle.category,
        price=bundle.price,
        monthly_income=bundle.monthly_income,
        resources=bundle.resources,
        status=bundle.status.value,
        rejection_reason=bundle.rejection_reason,
        created_at=bundle.created_at,
        moderated_at=bundle.moderated_at,
        channels=channels,
        channel_count=len(channels),
    )


@router.get("", response_model=BundleListResponse)
async def list_bundles(
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    search: str | None = None,
    seller_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List approved bundles (public) or all bundles for a specific seller."""
    query = (
        select(ChannelBundle)
        .options(
            selectinload(ChannelBundle.bundle_channels).selectinload(BundleChannel.channel)
        )
        .order_by(ChannelBundle.created_at.desc())
    )

    if seller_id is not None:
        query = query.where(ChannelBundle.seller_id == seller_id)
    else:
        query = query.where(ChannelBundle.status == BundleStatus.approved)

    if category:
        query = query.where(ChannelBundle.category == category)
    if min_price is not None:
        query = query.where(ChannelBundle.price >= min_price)
    if max_price is not None:
        query = query.where(ChannelBundle.price <= max_price)
    if search:
        query = query.where(ChannelBundle.name.ilike(f"%{search}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    bundles = (
        await db.execute(query.offset((page - 1) * limit).limit(limit))
    ).scalars().all()

    import math
    return BundleListResponse(
        items=[_bundle_to_response(b) for b in bundles],
        total=total,
        total_pages=math.ceil(total / limit) if total > 0 else 1,
        page=page,
    )


@router.get("/{bundle_id}", response_model=BundleResponse)
async def get_bundle(
    bundle_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get bundle by ID (public if approved)."""
    result = await db.execute(
        select(ChannelBundle)
        .options(
            selectinload(ChannelBundle.bundle_channels).selectinload(BundleChannel.channel)
        )
        .where(ChannelBundle.id == bundle_id)
    )
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle.status not in (BundleStatus.approved, BundleStatus.sold):
        raise HTTPException(status_code=404, detail="Bundle not found")
    return _bundle_to_response(bundle)


@router.get("/{bundle_id}/stats", response_model=BundleStatsResponse)
async def get_bundle_stats(
    bundle_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats for a bundle."""
    result = await db.execute(
        select(ChannelBundle)
        .options(
            selectinload(ChannelBundle.bundle_channels).selectinload(BundleChannel.channel)
        )
        .where(ChannelBundle.id == bundle_id)
    )
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    channels = [bc.channel for bc in bundle.bundle_channels if bc.channel is not None]

    total_subs = sum(c.subscribers_count or 0 for c in channels)
    total_income = sum(c.monthly_income or 0 for c in channels)
    er_vals = [c.er for c in channels if c.er is not None]
    avg_er = round(sum(er_vals) / len(er_vals), 2) if er_vals else 0.0
    views_vals = [c.avg_views for c in channels if c.avg_views is not None]
    avg_views = int(sum(views_vals) / len(views_vals)) if views_vals else 0

    return BundleStatsResponse(
        bundle_id=bundle_id,
        total_subscribers=total_subs,
        total_monthly_income=total_income,
        avg_er=avg_er,
        avg_views=avg_views,
        channel_count=len(channels),
        channels=[_channel_to_info(c) for c in channels],
    )


@router.post("", response_model=BundleResponse, status_code=status.HTTP_201_CREATED)
async def create_bundle(
    body: BundleCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new bundle listing."""
    bundle = ChannelBundle(
        seller_id=user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        price=body.price,
        monthly_income=body.monthly_income,
        resources=body.resources,
        status=BundleStatus.pending,
    )
    db.add(bundle)
    await db.flush()  # get bundle.id

    for idx, link in enumerate(body.channel_links):
        # Normalize link
        username = link.strip()
        for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
            if username.startswith(prefix):
                username = username[len(prefix):]
                break
        username = username.lstrip("@")

        # Find or create channel
        res = await db.execute(
            select(Channel).where(Channel.telegram_link.ilike(username))
        )
        channel = res.scalar_one_or_none()

        if channel is not None:
            if channel.seller_id != user.id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Channel @{username} belongs to another seller",
                )
            # Check not already in another bundle
            bc_res = await db.execute(
                select(BundleChannel).where(BundleChannel.channel_id == channel.id)
            )
            existing_bc = bc_res.scalar_one_or_none()
            if existing_bc and existing_bc.bundle_id != bundle.id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Channel @{username} is already part of another bundle",
                )
        else:
            # Create minimal channel record awaiting moderation with bundle
            channel = Channel(
                seller_id=user.id,
                telegram_link=username,
                channel_name=username,
                category=body.category or "Інше",
                price=0.0,
                status=ChannelStatus.pending,
            )
            db.add(channel)
            await db.flush()

        bc = BundleChannel(bundle_id=bundle.id, channel_id=channel.id, display_order=idx)
        db.add(bc)

    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(ChannelBundle)
        .options(
            selectinload(ChannelBundle.bundle_channels).selectinload(BundleChannel.channel)
        )
        .where(ChannelBundle.id == bundle.id)
    )
    bundle = result.scalar_one()
    return _bundle_to_response(bundle)


@router.put("/{bundle_id}", response_model=BundleResponse)
async def update_bundle(
    bundle_id: int,
    body: BundleUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a pending bundle (seller only)."""
    result = await db.execute(
        select(ChannelBundle)
        .options(
            selectinload(ChannelBundle.bundle_channels).selectinload(BundleChannel.channel)
        )
        .where(ChannelBundle.id == bundle_id)
    )
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Not your bundle")
    if bundle.status != BundleStatus.pending:
        raise HTTPException(status_code=400, detail="Can only edit pending bundles")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(bundle, field, value)
    await db.commit()
    await db.refresh(bundle)
    return _bundle_to_response(bundle)


@router.delete("/{bundle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bundle(
    bundle_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a pending bundle (seller only)."""
    result = await db.execute(select(ChannelBundle).where(ChannelBundle.id == bundle_id))
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Not your bundle")
    if bundle.status != BundleStatus.pending:
        raise HTTPException(status_code=400, detail="Can only delete pending bundles")

    await db.delete(bundle)
    await db.commit()


@router.get("/{bundle_id}/ai-analysis")
async def get_bundle_ai_analysis(
    bundle_id: int,
    db: AsyncSession = Depends(get_db),
):
    """AI-powered investment analysis for a bundle. Cached for 7 days."""
    result = await db.execute(
        select(ChannelBundle)
        .options(
            selectinload(ChannelBundle.bundle_channels).selectinload(BundleChannel.channel)
        )
        .where(ChannelBundle.id == bundle_id)
    )
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    # Return cached result if fresher than 7 days
    if bundle.ai_cache and bundle.ai_cache_updated_at:
        age = datetime.now(timezone.utc) - bundle.ai_cache_updated_at.replace(tzinfo=timezone.utc)
        if age < timedelta(days=7):
            return json.loads(bundle.ai_cache)

    channels = [bc.channel for bc in bundle.bundle_channels if bc.channel is not None]
    total_subs = sum(c.subscribers_count or 0 for c in channels)
    er_vals = [c.er for c in channels if c.er is not None]
    avg_er = round(sum(er_vals) / len(er_vals), 2) if er_vals else 0.0

    bundle_data = {
        "name": bundle.name,
        "channel_count": len(channels),
        "price": bundle.price,
        "category": bundle.category,
        "monthly_income": bundle.monthly_income,
        "total_subscribers": total_subs,
        "avg_er": avg_er,
        "description": bundle.description,
    }
    channels_data = [
        {
            "channel_name": c.channel_name,
            "subscribers_count": c.subscribers_count or 0,
            "er": c.er,
            "avg_views": c.avg_views,
        }
        for c in channels
    ]

    analysis = await analyze_bundle(bundle_data, channels_data)
    if analysis is None:
        raise HTTPException(status_code=503, detail="AI сервіс недоступний")
    if isinstance(analysis, dict) and analysis.get("error"):
        raise HTTPException(status_code=503, detail=analysis.get("detail", "Помилка AI аналізу"))

    # Save to cache (non-blocking — don't fail the request if cache write fails)
    try:
        bundle.ai_cache = json.dumps(analysis, ensure_ascii=False)
        bundle.ai_cache_updated_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as cache_err:
        logger.warning(f"Failed to save AI cache for bundle {bundle_id}: {cache_err}")
        await db.rollback()

    return analysis
