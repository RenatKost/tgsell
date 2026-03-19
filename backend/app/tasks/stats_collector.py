"""Background task: Periodically collect channel stats for all approved channels."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.channel import Channel, ChannelStats, ChannelStatus
from app.services.channel_stats import collect_channel_stats

logger = logging.getLogger(__name__)


async def collect_stats_once():
    """Collect fresh stats for all approved channels."""
    async with async_session() as db:
        result = await db.execute(
            select(Channel).where(Channel.status == ChannelStatus.approved)
        )
        channels = result.scalars().all()

        for channel in channels:
            try:
                stats = await collect_channel_stats(channel.telegram_link)

                # Update channel with latest data
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

                # Save historical stats
                stat_record = ChannelStats(
                    channel_id=channel.id,
                    date=datetime.now(timezone.utc),
                    subscribers=stats.get("subscribers_count", 0),
                    avg_views=stats.get("avg_views", 0),
                    avg_reach=stats.get("avg_views", 0),
                    er=stats.get("er", 0.0),
                )
                db.add(stat_record)
                await db.commit()

                logger.info(f"Stats collected for channel #{channel.id} ({channel.channel_name})")

                # Rate limit: wait between channels
                await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"Stats collection failed for channel #{channel.id}: {e}")


async def run_stats_collector(interval_hours: int = 6):
    """Run stats collector loop."""
    interval_seconds = interval_hours * 3600
    logger.info(f"Stats collector started (interval: {interval_hours}h)")
    while True:
        try:
            await collect_stats_once()
        except Exception as e:
            logger.error(f"Stats collector error: {e}")
        await asyncio.sleep(interval_seconds)
