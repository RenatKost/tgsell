"""Background task: Periodically collect channel stats for all approved channels."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.channel import Channel, ChannelPost, ChannelStats, ChannelStatus
from app.services.channel_stats import collect_channel_stats, reset_telethon_retries

logger = logging.getLogger(__name__)


async def collect_stats_once():
    """Collect fresh stats for all active channels (pending + approved)."""
    reset_telethon_retries()  # Allow fresh reconnect attempts each cycle

    async with async_session() as db:
        result = await db.execute(
            select(Channel).where(
                Channel.status.in_([ChannelStatus.approved, ChannelStatus.pending])
            )
        )
        channels = result.scalars().all()

        total = len(channels)
        success = 0
        failed = 0
        telethon_ok = True

        for channel in channels:
            try:
                stats = await collect_channel_stats(channel.telegram_link)
                if not stats.get("daily_stats"):
                    telethon_ok = False

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
                if stats.get("adv_reach_12h"):
                    channel.adv_reach_12h = stats["adv_reach_12h"]
                if stats.get("adv_reach_24h"):
                    channel.adv_reach_24h = stats["adv_reach_24h"]
                if stats.get("adv_reach_48h"):
                    channel.adv_reach_48h = stats["adv_reach_48h"]

                # Extended stats
                if stats.get("total_posts"):
                    channel.total_posts = stats["total_posts"]
                if stats.get("post_frequency") is not None:
                    channel.post_frequency = stats["post_frequency"]
                if stats.get("last_post_date"):
                    try:
                        channel.last_post_date = datetime.fromisoformat(stats["last_post_date"])
                    except (ValueError, TypeError):
                        pass
                if stats.get("avg_forwards"):
                    channel.avg_forwards = stats["avg_forwards"]
                if stats.get("avg_reactions"):
                    channel.avg_reactions = stats["avg_reactions"]

                # Save daily_stats history with deduplication
                daily_stats = stats.get("daily_stats", [])
                if daily_stats:
                    # Get existing dates for this channel to avoid duplicates
                    existing = await db.execute(
                        select(ChannelStats.date).where(
                            ChannelStats.channel_id == channel.id
                        )
                    )
                    existing_dates = {
                        d.strftime("%Y-%m-%d") for d in existing.scalars().all()
                    }

                    for ds in daily_stats:
                        if ds["date"] not in existing_dates:
                            db.add(ChannelStats(
                                channel_id=channel.id,
                                date=datetime.strptime(ds["date"], "%Y-%m-%d"),
                                subscribers=ds.get("subscribers") or 0,
                                avg_views=ds.get("avg_views") or 0,
                                avg_reach=ds.get("avg_views") or 0,
                                er=ds.get("er") or 0.0,
                                post_count=ds.get("post_count") or 0,
                                avg_forwards=ds.get("avg_forwards") or 0,
                                avg_reactions=ds.get("avg_reactions") or 0,
                            ))
                else:
                    # Fallback: save today's snapshot
                    today_str = datetime.utcnow().strftime("%Y-%m-%d")
                    existing = await db.execute(
                        select(ChannelStats.id).where(
                            ChannelStats.channel_id == channel.id,
                            ChannelStats.date >= datetime.strptime(today_str, "%Y-%m-%d"),
                        )
                    )
                    if not existing.scalar_one_or_none():
                        db.add(ChannelStats(
                            channel_id=channel.id,
                            date=datetime.utcnow(),
                            subscribers=stats.get("subscribers_count") or 0,
                            avg_views=stats.get("avg_views") or 0,
                            avg_reach=stats.get("avg_views") or 0,
                            er=stats.get("er") or 0.0,
                            post_count=0,
                        ))

                # Save individual posts with deduplication + view tracking
                posts_data = stats.get("posts", [])
                if posts_data:
                    await _upsert_channel_posts(db, channel.id, posts_data)

                await db.commit()

                logger.info(f"Stats collected for channel #{channel.id} ({channel.channel_name})")
                success += 1

                # Rate limit: wait between channels
                await asyncio.sleep(3)

            except Exception as e:
                failed += 1
                logger.error(f"Stats collection failed for channel #{channel.id}: {e}")

        # Send summary alert if there were problems
        if total > 0:
            from app.services.alerts import alert_stats_summary
            await alert_stats_summary(total, success, failed, telethon_ok)


async def _upsert_channel_posts(db: AsyncSession, channel_id: int, posts_data: list):
    """Insert new posts or update existing ones with latest view counts.

    Also fills views_1h, views_12h, views_24h, views_48h based on post age.
    """
    if not posts_data:
        return

    # Get existing posts for this channel
    msg_ids = [p["telegram_msg_id"] for p in posts_data]
    existing_result = await db.execute(
        select(ChannelPost).where(
            ChannelPost.channel_id == channel_id,
            ChannelPost.telegram_msg_id.in_(msg_ids),
        )
    )
    existing_posts = {p.telegram_msg_id: p for p in existing_result.scalars().all()}

    now = datetime.now(timezone.utc)

    for post in posts_data:
        msg_id = post["telegram_msg_id"]
        post_date = datetime.fromisoformat(post["date"])
        if post_date.tzinfo is None:
            post_date = post_date.replace(tzinfo=timezone.utc)
        age_hours = (now - post_date).total_seconds() / 3600

        if msg_id in existing_posts:
            # Update existing post with latest views
            existing = existing_posts[msg_id]
            existing.views = post["views"]
            existing.forwards = post["forwards"]
            existing.reactions = post["reactions"]
            existing.comments = post["comments"]

            # Track view snapshots by post age
            if age_hours <= 2 and existing.views_1h is None:
                existing.views_1h = post["views"]
            if 10 <= age_hours <= 14 and existing.views_12h is None:
                existing.views_12h = post["views"]
            if 22 <= age_hours <= 26 and existing.views_24h is None:
                existing.views_24h = post["views"]
            if 46 <= age_hours <= 50 and existing.views_48h is None:
                existing.views_48h = post["views"]
        else:
            # New post
            new_post = ChannelPost(
                channel_id=channel_id,
                telegram_msg_id=msg_id,
                date=post_date,
                text=post.get("text"),
                media_type=post.get("media_type"),
                link=post.get("link"),
                views=post["views"],
                forwards=post["forwards"],
                reactions=post["reactions"],
                comments=post["comments"],
            )
            # Set initial view snapshot if post is young
            if age_hours <= 2:
                new_post.views_1h = post["views"]
            if 10 <= age_hours <= 14:
                new_post.views_12h = post["views"]
            if 22 <= age_hours <= 26:
                new_post.views_24h = post["views"]
            if 46 <= age_hours <= 50:
                new_post.views_48h = post["views"]

            db.add(new_post)


async def run_stats_collector(interval_hours: int = 24):
    """Run stats collector loop."""
    interval_seconds = interval_hours * 3600
    logger.info(f"Stats collector started (interval: {interval_hours}h)")
    while True:
        try:
            await collect_stats_once()
        except Exception as e:
            logger.error(f"Stats collector error: {e}")
            from app.services.alerts import alert_service_down
            await alert_service_down("Stats Collector", str(e))
        await asyncio.sleep(interval_seconds)


async def update_post_views_once():
    """Update view counts for recent posts (last 48h) to track view dynamics."""
    from app.services.channel_stats import _get_telethon_client

    client = await _get_telethon_client()
    if not client:
        return

    async with async_session() as db:
        # Get all posts from last 48 hours that still need view snapshots
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0) - __import__('datetime').timedelta(hours=50)
        result = await db.execute(
            select(ChannelPost).join(Channel).where(
                ChannelPost.date >= cutoff,
                Channel.status.in_([ChannelStatus.approved, ChannelStatus.pending]),
            )
        )
        posts = result.scalars().all()

        if not posts:
            return

        # Group posts by channel
        from collections import defaultdict
        by_channel = defaultdict(list)
        for post in posts:
            by_channel[post.channel_id].append(post)

        now = datetime.now(timezone.utc)

        for channel_id, channel_posts in by_channel.items():
            try:
                # Get channel entity
                ch_result = await db.execute(
                    select(Channel.telegram_link).where(Channel.id == channel_id)
                )
                link = ch_result.scalar_one_or_none()
                if not link:
                    continue

                username = link.strip()
                for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
                    if username.startswith(prefix):
                        username = username[len(prefix):]
                        break

                entity = await client.get_entity(username)

                # Fetch latest messages to get updated views
                msg_ids = [p.telegram_msg_id for p in channel_posts]
                messages = await client.get_messages(entity, ids=msg_ids)

                msg_map = {}
                for msg in messages:
                    if msg is not None:
                        msg_map[msg.id] = msg

                for post in channel_posts:
                    msg = msg_map.get(post.telegram_msg_id)
                    if not msg:
                        continue

                    post.views = msg.views or post.views
                    if msg.forwards is not None:
                        post.forwards = msg.forwards
                    if hasattr(msg, 'reactions') and msg.reactions and hasattr(msg.reactions, 'results'):
                        post.reactions = sum(r.count for r in msg.reactions.results)

                    # Track view snapshots based on post age
                    post_date = post.date
                    if post_date.tzinfo is None:
                        post_date = post_date.replace(tzinfo=timezone.utc)
                    age_hours = (now - post_date).total_seconds() / 3600

                    if age_hours >= 1 and post.views_1h is None:
                        post.views_1h = post.views
                    if age_hours >= 12 and post.views_12h is None:
                        post.views_12h = post.views
                    if age_hours >= 24 and post.views_24h is None:
                        post.views_24h = post.views
                    if age_hours >= 48 and post.views_48h is None:
                        post.views_48h = post.views

                await db.commit()
                logger.info(f"View tracking updated for channel #{channel_id} ({len(channel_posts)} posts)")
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"View tracking failed for channel #{channel_id}: {e}")


async def run_view_tracker(interval_hours: int = 6):
    """Run view tracker loop — updates post views more frequently than full stats."""
    interval_seconds = interval_hours * 3600
    logger.info(f"View tracker started (interval: {interval_hours}h)")
    # Initial delay — wait 30min after startup to let first stats collection finish
    await asyncio.sleep(1800)
    while True:
        try:
            await update_post_views_once()
        except Exception as e:
            logger.error(f"View tracker error: {e}")
        await asyncio.sleep(interval_seconds)
