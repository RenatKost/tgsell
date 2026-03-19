"""Telegram channel statistics collector using Telethon (MTProto) and Bot API."""
import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy imports — Telethon is optional
_telethon_client = None


async def _get_telethon_client():
    """Get or create a Telethon client (singleton)."""
    global _telethon_client
    if _telethon_client is not None and _telethon_client.is_connected():
        return _telethon_client

    try:
        from telethon import TelegramClient

        client = TelegramClient(
            "tgsell_stats_session",
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.start(phone=settings.telegram_phone)
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

    base_url = f"https://api.telegram.org/bot{settings.bot_token}"

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
                            photo_url = f"https://api.telegram.org/file/bot{settings.bot_token}/{file_path}"

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


async def get_channel_stats_telethon(channel_username: str, message_limit: int = 50) -> dict | None:
    """Get detailed channel stats using Telethon (MTProto).

    Returns: {avg_views, er, avg_reach, adv_reach_12h, adv_reach_24h, adv_reach_48h}
    """
    client = await _get_telethon_client()
    if not client:
        logger.warning("Telethon client not available, skipping deep stats")
        return None

    try:
        from telethon.tl.functions.channels import GetFullChannelRequest

        entity = await client.get_entity(channel_username)
        full_channel = await client(GetFullChannelRequest(entity))

        subscribers = full_channel.full_chat.participants_count

        # Get recent messages with views
        messages = await client.get_messages(entity, limit=message_limit)

        views_list = []
        now = datetime.now(timezone.utc)

        reach_12h = []
        reach_24h = []
        reach_48h = []

        for msg in messages:
            if msg.views is not None:
                views_list.append(msg.views)

                age_hours = (now - msg.date.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                if age_hours <= 12:
                    reach_12h.append(msg.views)
                elif age_hours <= 24:
                    reach_24h.append(msg.views)
                elif age_hours <= 48:
                    reach_48h.append(msg.views)

        avg_views = sum(views_list) // len(views_list) if views_list else 0
        er = round((avg_views / subscribers * 100), 2) if subscribers > 0 else 0.0
        avg_reach = avg_views  # Simplified: avg_reach ≈ avg_views

        # Add delay to avoid rate-limiting
        await asyncio.sleep(2)

        return {
            "subscribers": subscribers,
            "avg_views": avg_views,
            "er": er,
            "avg_reach": avg_reach,
            "adv_reach_12h": sum(reach_12h) // len(reach_12h) if reach_12h else 0,
            "adv_reach_24h": sum(reach_24h) // len(reach_24h) if reach_24h else 0,
            "adv_reach_48h": sum(reach_48h) // len(reach_48h) if reach_48h else 0,
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

    return result
