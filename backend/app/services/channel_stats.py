"""Telegram channel statistics collector using Telethon (MTProto) and Bot API."""
import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy imports — Telethon is optional
_telethon_client = None


async def _get_telethon_client():
    """Get or create a Telethon client (singleton) using StringSession."""
    global _telethon_client
    if _telethon_client is not None and _telethon_client.is_connected():
        return _telethon_client

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        session = StringSession(settings.telethon_session_string) if settings.telethon_session_string else StringSession()
        client = TelegramClient(
            session,
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.connect()
        if not await client.is_user_authorized():
            logger.warning("Telethon session not authorized. Set TELETHON_SESSION_STRING env var.")
            return None
        _telethon_client = client
        return client
    except Exception as e:
        logger.error(f"Failed to init Telethon client: {e}")
        return None


async def get_channel_info_bot_api(channel_username: str) -> dict | None:
    """Get basic channel info using Bot API (safe, no user account needed).

    Returns: {name, description, subscribers_count, photo_url}
    """
    import httpx

    base_url = f"https://api.telegram.org/bot{settings.bot_token_stats}"

    try:
        async with httpx.AsyncClient() as http:
            # getChat
            resp = await http.get(f"{base_url}/getChat", params={"chat_id": f"@{channel_username}"})
            if resp.status_code != 200:
                return None
            chat_data = resp.json().get("result", {})

            # getChatMemberCount
            count_resp = await http.get(
                f"{base_url}/getChatMemberCount",
                params={"chat_id": f"@{channel_username}"},
            )
            members = count_resp.json().get("result", 0) if count_resp.status_code == 200 else 0

            # Get photo URL (if available)
            photo_url = None
            if chat_data.get("photo"):
                file_id = chat_data["photo"].get("big_file_id")
                if file_id:
                    file_resp = await http.get(f"{base_url}/getFile", params={"file_id": file_id})
                    if file_resp.status_code == 200:
                        file_path = file_resp.json().get("result", {}).get("file_path")
                        if file_path:
                            photo_url = f"https://api.telegram.org/file/bot{settings.bot_token_stats}/{file_path}"

            return {
                "name": chat_data.get("title", ""),
                "description": chat_data.get("description", ""),
                "subscribers_count": members,
                "photo_url": photo_url,
                "username": chat_data.get("username", channel_username),
            }
    except Exception as e:
        logger.error(f"Bot API channel info failed for @{channel_username}: {e}")
        return None


async def get_channel_stats_telethon(channel_username: str, message_limit: int = 1000) -> dict | None:
    """Get detailed channel stats using Telethon (MTProto).

    Collects historical daily stats from messages for graphs (~30 days).
    Returns: {avg_views, er, avg_reach, adv_reach_12h, adv_reach_24h, adv_reach_48h,
              channel_age_months, daily_stats: [{date, views, subscribers}]}
    """
    client = await _get_telethon_client()
    if not client:
        logger.warning("Telethon client not available, skipping deep stats")
        return None

    try:
        from telethon.tl.functions.channels import GetFullChannelRequest
        from collections import defaultdict

        entity = await client.get_entity(channel_username)
        full_channel = await client(GetFullChannelRequest(entity))

        subscribers = full_channel.full_chat.participants_count

        # Calculate channel age
        channel_age_months = None
        if hasattr(entity, 'date') and entity.date:
            created = entity.date.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = now - created
            channel_age_months = max(1, int(diff.days / 30))

        # Get total posts count
        total_posts = None
        try:
            all_msgs = await client.get_messages(entity, limit=0)
            total_posts = all_msgs.total
        except Exception:
            pass

        # Get messages for historical stats (more messages = more history)
        messages = await client.get_messages(entity, limit=message_limit)

        views_list = []
        forwards_list = []
        reactions_list = []
        now = datetime.now(timezone.utc)

        reach_12h = []
        reach_24h = []
        reach_48h = []

        last_post_date = None
        posts_last_30d = 0

        # Group views by date for daily stats
        daily_views = defaultdict(list)

        for msg in messages:
            msg_date = msg.date.replace(tzinfo=timezone.utc)

            # Track last post date
            if last_post_date is None or msg_date > last_post_date:
                last_post_date = msg_date

            # Count posts in last 30 days
            if (now - msg_date).days <= 30:
                posts_last_30d += 1

            if msg.views is not None:
                views_list.append(msg.views)

                age_hours = (now - msg_date).total_seconds() / 3600
                if age_hours <= 12:
                    reach_12h.append(msg.views)
                elif age_hours <= 24:
                    reach_24h.append(msg.views)
                elif age_hours <= 48:
                    reach_48h.append(msg.views)

                # Store daily stats
                day_key = msg_date.strftime("%Y-%m-%d")
                daily_views[day_key].append(msg.views)

            # Forwards
            if msg.forwards is not None:
                forwards_list.append(msg.forwards)

            # Reactions
            if hasattr(msg, 'reactions') and msg.reactions:
                total_react = sum(
                    r.count for r in msg.reactions.results
                ) if hasattr(msg.reactions, 'results') else 0
                if total_react > 0:
                    reactions_list.append(total_react)

        avg_views = sum(views_list) // len(views_list) if views_list else 0
        er = round((avg_views / subscribers * 100), 2) if subscribers > 0 else 0.0
        avg_forwards = sum(forwards_list) // len(forwards_list) if forwards_list else 0
        avg_reactions = sum(reactions_list) // len(reactions_list) if reactions_list else 0
        post_frequency = round(posts_last_30d / 30, 1) if posts_last_30d > 0 else 0.0

        # Build daily stats for graphs (sorted by date)
        daily_stats = []
        for date_str in sorted(daily_views.keys()):
            day_views = daily_views[date_str]
            daily_stats.append({
                "date": date_str,
                "avg_views": sum(day_views) // len(day_views),
                "subscribers": subscribers,  # current value for all days
                "er": er,
            })

        # Add delay to avoid rate-limiting
        await asyncio.sleep(2)

        return {
            "subscribers": subscribers,
            "avg_views": avg_views,
            "er": er,
            "avg_reach": avg_views,
            "adv_reach_12h": sum(reach_12h) // len(reach_12h) if reach_12h else 0,
            "adv_reach_24h": sum(reach_24h) // len(reach_24h) if reach_24h else 0,
            "adv_reach_48h": sum(reach_48h) // len(reach_48h) if reach_48h else 0,
            "channel_age_months": channel_age_months,
            "daily_stats": daily_stats,
            "total_posts": total_posts,
            "post_frequency": post_frequency,
            "last_post_date": last_post_date.isoformat() if last_post_date else None,
            "avg_forwards": avg_forwards,
            "avg_reactions": avg_reactions,
        }
    except Exception as e:
        logger.error(f"Telethon stats failed for @{channel_username}: {e}")
        return None


async def collect_channel_stats(telegram_link: str) -> dict:
    """Collect stats using hybrid approach: Bot API + Telethon.

    Returns combined info dict.
    """
    # Extract username from link
    username = telegram_link.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
        if username.startswith(prefix):
            username = username[len(prefix):]
            break

    result = {
        "channel_name": username,
        "subscribers_count": 0,
        "avg_views": None,
        "er": None,
        "avatar_url": None,
        "adv_reach_12h": None,
        "adv_reach_24h": None,
        "adv_reach_48h": None,
        "channel_age_months": None,
        "daily_stats": [],
        "total_posts": None,
        "post_frequency": None,
        "last_post_date": None,
        "avg_forwards": None,
        "avg_reactions": None,
    }

    # Step 1: Bot API (safe, always works)
    bot_info = await get_channel_info_bot_api(username)
    if bot_info:
        result["channel_name"] = bot_info["name"] or username
        result["subscribers_count"] = bot_info["subscribers_count"]
        result["avatar_url"] = bot_info["photo_url"]

    # Step 2: Telethon (deeper stats, may fail)
    telethon_stats = await get_channel_stats_telethon(username)
    if telethon_stats:
        result["subscribers_count"] = telethon_stats["subscribers"]
        result["avg_views"] = telethon_stats["avg_views"]
        result["er"] = telethon_stats["er"]
        result["adv_reach_12h"] = telethon_stats.get("adv_reach_12h")
        result["adv_reach_24h"] = telethon_stats.get("adv_reach_24h")
        result["adv_reach_48h"] = telethon_stats.get("adv_reach_48h")
        result["channel_age_months"] = telethon_stats.get("channel_age_months")
        result["daily_stats"] = telethon_stats.get("daily_stats", [])
        result["total_posts"] = telethon_stats.get("total_posts")
        result["post_frequency"] = telethon_stats.get("post_frequency")
        result["last_post_date"] = telethon_stats.get("last_post_date")
        result["avg_forwards"] = telethon_stats.get("avg_forwards")
        result["avg_reactions"] = telethon_stats.get("avg_reactions")

    return result
