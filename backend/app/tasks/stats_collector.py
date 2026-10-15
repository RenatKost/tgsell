"""Background task: Periodically collect channel stats for all approved channels."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.channel import Channel, ChannelPost, ChannelStats, ChannelStatus
from app.services.channel_stats import collect_channel_stats, parse_telegram_link, reset_telethon_retries
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)


async def collect_stats_once():
    """Collect fresh stats for all active channels (pending + approved)."""
    reset_telethon_retries()  # Allow fresh reconnect attempts each cycle

    async with async_session() as db:
        result = await db.execute(
            select(Channel.id).where(
                Channel.status.in_([ChannelStatus.approved, ChannelStatus.pending]),
                Channel.is_closed.is_(False),
            )
        )
        channel_ids = result.scalars().all()

    total = len(channel_ids)
    success = 0
    failed = 0
    telethon_ok = True

    # Each channel gets its own session/transaction. The full sweep can take a
    # long time (rate-limited + Telethon flood waits), so a channel may get
    # deleted mid-run; isolating sessions keeps that from poisoning the rest
    # of the batch with a broken transaction.
    for channel_id in channel_ids:
        try:
            async with async_session() as db:
                channel = await db.get(Channel, channel_id)
                if channel is None:
                    logger.info(f"Channel #{channel_id} was deleted before stats collection, skipping")
                    continue

                stats = await collect_channel_stats(channel.telegram_link)
                if not stats.get("daily_stats"):
                    telethon_ok = False
                check = stats.get("check")
                if check is not None:
                    from app.services.channel_availability import record_check

                    was_inactive = channel.inactive_since is not None
                    await record_check(db, channel, check)
                    if not check.get("ok"):
                        if channel.inactive_since is not None and not was_inactive:
                            logger.warning(f"[STATS] Channel #{channel.id} ({channel.telegram_link}) INACTIVE: {channel.check_error}")
                        await db.commit()
                        failed += 1
                        continue  # nothing to store from a failed check (no zero snapshots)

                # Update channel with latest data
                if stats.get("subscribers_count"):
                    channel.subscribers_count = stats["subscribers_count"]
                if stats.get("avg_views"):
                    channel.avg_views = stats["avg_views"]
                if stats.get("views_hidden") is not None:
                    channel.views_hidden = stats["views_hidden"]
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
                        channel.last_post_date = datetime.fromisoformat(stats["last_post_date"]).replace(tzinfo=None)
                    except (ValueError, TypeError):
                        pass
                if stats.get("avg_forwards"):
                    channel.avg_forwards = stats["avg_forwards"]
                if stats.get("avg_reactions"):
                    channel.avg_reactions = stats["avg_reactions"]
                if stats.get("channel_age_months"):
                    channel.age = f"{stats['channel_age_months']}"

                # Honest time series (Task 20): retro points carry post metrics
                # only; today's row is a real snapshot; last 3 days are refreshed.
                from app.services.stats_history import record_stats

                await record_stats(db, channel_id, stats)

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
            logger.error(f"Stats collection failed for channel #{channel_id}: {e}")

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
                date=post_date.replace(tzinfo=None),
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
    # Wait past Telethon startup delay so the first cycle can use MTProto
    from app.config import settings as cfg
    delay = max(0, int(cfg.telethon_startup_delay_sec)) + 5
    logger.info(f"Stats collector: waiting {delay}s for Telethon startup delay…")
    await asyncio.sleep(delay)
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

    # Load plain column tuples only (no ORM instances shared across channels).
    # Previously ORM ChannelPost objects were loaded once and reused across
    # channels; a db.rollback() after one channel failed expired *all* of them,
    # so touching e.g. post.telegram_msg_id for the next channel triggered a
    # lazy refresh outside the async greenlet -> "greenlet_spawn has not been
    # called" errors. Now each channel gets its own session and fresh rows.
    from collections import defaultdict

    cutoff = utcnow_naive().replace(hour=0, minute=0) - timedelta(hours=50)
    async with async_session() as db:
        rows = (await db.execute(
            select(ChannelPost.channel_id, ChannelPost.id, Channel.telegram_link)
            .join(Channel, Channel.id == ChannelPost.channel_id)
            .where(
                ChannelPost.date >= cutoff,
                Channel.status.in_([ChannelStatus.approved, ChannelStatus.pending]),
                Channel.is_closed.is_(False),
            )
        )).all()

    if not rows:
        return

    by_channel: dict[int, list[int]] = defaultdict(list)
    links: dict[int, str] = {}
    for channel_id, post_id, link in rows:
        by_channel[channel_id].append(post_id)
        links[channel_id] = link

    now = datetime.now(timezone.utc)

    for channel_id, post_ids in by_channel.items():
        try:
            link = links.get(channel_id)
            if not link:
                continue
            username, link_kind = parse_telegram_link(link)
            if link_kind == "invite":
                continue

            async with async_session() as db:
                channel_posts = (await db.execute(
                    select(ChannelPost).where(ChannelPost.id.in_(post_ids))
                )).scalars().all()
                if not channel_posts:
                    continue

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
            logger.info(f"View tracking updated for channel #{channel_id} ({len(post_ids)} posts)")
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
