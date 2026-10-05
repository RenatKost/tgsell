"""Telegram channel statistics collector using Telethon (MTProto) and Bot API."""
import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy imports — Telethon is optional
_telethon_client = None
_telethon_was_ok = False  # Track state for recovery alerts
_telethon_retries = 0
_MAX_RETRIES = 3

# Startup delay gate: do not open MTProto until the previous container is gone.
# Railway healthcheckTimeout is 120s; default delay is 150s (configurable).
_startup_connect_allowed = False
_authkey_duplicated = False  # Permanent fail — never reconnect until re-auth / restart
# waiting | connecting | connected | unauthorized | failed | authkey_duplicated
_telethon_status = "waiting"
_telethon_status_detail: str | None = None
_intentional_disconnect = False  # True during process shutdown — suppress mid-session alerts
_disconnect_watch_task: asyncio.Task | None = None


def get_telethon_health() -> dict:
    """Snapshot for /api/health and admin UI. ok is True only when connected+authorized."""
    ok = (
        _telethon_status == "connected"
        and _telethon_client is not None
        and _telethon_client.is_connected()
    )
    return {
        "status": _telethon_status,
        "ok": bool(ok),
        "detail": _telethon_status_detail,
        "startup_delay_sec": settings.telethon_startup_delay_sec,
        "startup_connect_allowed": _startup_connect_allowed,
        "authkey_duplicated": _authkey_duplicated,
    }


def allow_telethon_connect_now():
    """Bypass remaining startup delay (e.g. right after a successful re-auth)."""
    global _startup_connect_allowed, _authkey_duplicated, _telethon_retries
    _startup_connect_allowed = True
    _authkey_duplicated = False
    _telethon_retries = 0


def _should_suppress_telethon_alerts() -> bool:
    """No admin spam during TELETHON_STARTUP_DELAY / waiting / connecting."""
    if not _startup_connect_allowed:
        return True
    if _telethon_status in ("waiting", "connecting"):
        return True
    return False


async def _notify_telethon_down(reason: str, detail: str = "") -> None:
    """Fire immediate Telethon-down alert unless still in startup/waiting/connecting."""
    if _should_suppress_telethon_alerts():
        logger.info(
            "Telethon down suppressed (status=%s, startup_allowed=%s, reason=%s)",
            _telethon_status,
            _startup_connect_allowed,
            reason,
        )
        return
    from app.services.alerts import alert_telethon_session_down
    await alert_telethon_session_down(reason, detail)


async def _notify_telethon_recovered() -> None:
    """Fire recovery alert only if a prior down was latched."""
    from app.services.alerts import alert_telethon_session_recovered
    await alert_telethon_session_recovered()


def _cancel_disconnect_watcher() -> None:
    """Cancel mid-session disconnect watcher (reconnect / shutdown / reset)."""
    global _disconnect_watch_task
    if _disconnect_watch_task is not None and not _disconnect_watch_task.done():
        _disconnect_watch_task.cancel()
    _disconnect_watch_task = None


def _attach_disconnect_watcher(client) -> None:
    """Watch Telethon client.disconnected for mid-session drops (event-driven)."""
    global _disconnect_watch_task
    _cancel_disconnect_watcher()

    async def _watch():
        global _telethon_client, _telethon_status, _telethon_status_detail, _telethon_was_ok
        try:
            # Resolves when the connection is fully gone (reconnects exhausted / logout / disconnect)
            await client.disconnected
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Telethon disconnected with error: {e}")

        if _intentional_disconnect:
            return
        if _telethon_client is not client:
            return  # replaced or already cleared
        _telethon_client = None
        if _telethon_status == "connected":
            _telethon_status = "failed"
            _telethon_status_detail = "Disconnected mid-session"
            _telethon_was_ok = False
            logger.error("Telethon: mid-session disconnect detected")
            await _notify_telethon_down(
                "disconnect",
                "З'єднання обірвано під час роботи",
            )

    _disconnect_watch_task = asyncio.create_task(_watch())


async def _safe_disconnect(client) -> None:
    """Disconnect a client and cancel lingering reconnect tasks; never raise."""
    if client is None:
        return
    try:
        await client.disconnect()
    except Exception as e:
        logger.warning(f"Telethon disconnect failed: {e}")


async def delayed_telethon_startup() -> None:
    """Background: wait TELETHON_STARTUP_DELAY_SEC, then attempt first connect.

    Keeps /api/health and the web app up immediately while avoiding AuthKey
    duplication when Railway overlaps old and new containers during deploy.
    """
    global _startup_connect_allowed, _telethon_status, _telethon_status_detail

    delay = max(0, int(settings.telethon_startup_delay_sec))
    _telethon_status = "waiting"
    _telethon_status_detail = f"Waiting {delay}s before first Telethon connect (deploy overlap safety)"
    logger.info(f"Telethon: delaying first connect by {delay}s (TELETHON_STARTUP_DELAY_SEC)")
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        logger.info("Telethon: startup delay cancelled (shutdown)")
        raise

    _startup_connect_allowed = True
    _telethon_status = "connecting"
    _telethon_status_detail = "Connecting after startup delay…"
    logger.info("Telethon: startup delay done — connecting…")
    await _get_telethon_client()


async def _get_telethon_client():
    """Get or create a Telethon client (singleton) with auto-reconnect."""
    global _telethon_client, _telethon_was_ok, _telethon_retries
    global _telethon_status, _telethon_status_detail, _authkey_duplicated

    # Permanent lockout after AuthKeyDuplicatedError until re-auth / process restart
    if _authkey_duplicated:
        return None

    # Fast path — already connected
    if _telethon_client is not None and _telethon_client.is_connected():
        try:
            if await _telethon_client.is_user_authorized():
                _telethon_status = "connected"
                _telethon_status_detail = None
                return _telethon_client
        except Exception:
            pass
        logger.warning("Telethon: connected but session invalid, reconnecting…")
        _cancel_disconnect_watcher()  # intentional reconnect — not a mid-session death alert
        await _safe_disconnect(_telethon_client)
        _telethon_client = None

    # Hold off until startup delay elapses (or re-auth calls allow_telethon_connect_now)
    if not _startup_connect_allowed:
        _telethon_status = "waiting"
        return None

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.warning("Telethon: TELEGRAM_API_ID or TELEGRAM_API_HASH not set — skipping")
        _telethon_status = "failed"
        _telethon_status_detail = "TELEGRAM_API_ID or TELEGRAM_API_HASH not set"
        return None

    # Retry limit per cycle
    if _telethon_retries >= _MAX_RETRIES:
        return None

    # DB-first session loading: always use the most recent session data.
    # Falls back to env var on first boot (and seeds the DB immediately after auth).
    session_string = await _load_session_from_db()
    if not session_string:
        session_string = settings.telethon_session_string
        if not session_string:
            logger.warning("Telethon: no session in DB and TELETHON_SESSION_STRING not set — skipping")
            _telethon_status = "unauthorized"
            _telethon_status_detail = "No session in DB and TELETHON_SESSION_STRING not set"
            return None

    client = None
    _telethon_status = "connecting"
    try:
        from telethon import TelegramClient
        from telethon.errors import AuthKeyDuplicatedError
        from telethon.sessions import StringSession

        session = StringSession(session_string)
        client = TelegramClient(
            session,
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.connect()
        if not await client.is_user_authorized():
            logger.warning("Telethon session not authorized (expired?). Re-auth required.")
            _telethon_retries += 1
            _telethon_status = "unauthorized"
            _telethon_status_detail = "Session not authorized — re-auth required"
            await _safe_disconnect(client)
            client = None
            _telethon_was_ok = False
            await _notify_telethon_down(
                "unauthorized",
                "Сесія не авторизована — потрібна повторна авторизація",
            )
            return None

        logger.info("Telethon client connected and authorized ✓")
        _telethon_client = client
        _telethon_retries = 0
        _telethon_status = "connected"
        _telethon_status_detail = None

        # Persist updated session data (captures DC migrations and key refreshes)
        await _save_session_to_db(client.session.save())

        # Watch for mid-session drops (do not wait for health_monitor)
        _attach_disconnect_watcher(client)

        # Recovery only if a prior down alert was latched (not on first boot)
        await _notify_telethon_recovered()

        _telethon_was_ok = True
        return client
    except Exception as e:
        # Always tear down the client so no reconnect loops linger
        await _safe_disconnect(client)
        client = None
        _telethon_client = None

        # AuthKeyDuplicatedError: two IPs used the same auth key — session is dead.
        # Stop all retries; require admin re-auth.
        try:
            from telethon.errors import AuthKeyDuplicatedError
        except ImportError:
            AuthKeyDuplicatedError = type(None)  # type: ignore[misc,assignment]

        if isinstance(e, AuthKeyDuplicatedError):
            _authkey_duplicated = True
            _telethon_retries = _MAX_RETRIES
            _telethon_status = "authkey_duplicated"
            _telethon_status_detail = (
                "AuthKeyDuplicatedError: session used from two IPs simultaneously — "
                "re-auth required (admin → Telethon сесія)"
            )
            logger.error(
                "Telethon AuthKeyDuplicatedError — stopping reconnects; admin re-auth required"
            )
            _telethon_was_ok = False
            await _notify_telethon_down(
                "authkey_duplicated",
                "Сесію анульовано — reconnect марний, потрібен новий логін",
            )
            return None

        logger.error(f"Failed to init Telethon client: {e}")
        _telethon_retries += 1
        _telethon_status = "failed"
        _telethon_status_detail = str(e)[:500]
        # Alert immediately if previously OK, or after retries exhausted
        if _telethon_was_ok or _telethon_retries >= _MAX_RETRIES:
            _telethon_was_ok = False
            await _notify_telethon_down("connect_failed", str(e)[:500])
        return None


def reset_telethon_retries():
    """Reset retry counter — called at start of each stats cycle.

    Does nothing after AuthKeyDuplicatedError (permanent lockout until re-auth).
    """
    global _telethon_retries
    if _authkey_duplicated:
        return
    _telethon_retries = 0


def reset_telethon_client():
    """Force the global client to None — call after re-auth to pick up new session."""
    global _telethon_client, _authkey_duplicated, _telethon_retries
    global _telethon_status, _telethon_status_detail
    _cancel_disconnect_watcher()  # do not treat re-auth reset as mid-session death
    _telethon_client = None
    # Fresh session after re-auth — clear lockout and allow immediate connect
    allow_telethon_connect_now()
    _telethon_status = "connecting"
    _telethon_status_detail = "Reset after re-auth — will reconnect on next use"


async def disconnect_telethon_client():
    """Disconnect the live client on process shutdown.

    Telegram invalidates a user session ("used under two different IP
    addresses simultaneously") if the outgoing container keeps holding an
    idle connection open while the incoming container from the next deploy
    connects with the same DB-stored session string. Releasing it here
    shrinks that overlap window instead of leaving it connected until the
    process is killed.
    """
    global _telethon_client, _telethon_status, _intentional_disconnect
    _intentional_disconnect = True  # suppress mid-session disconnect alert on shutdown
    _cancel_disconnect_watcher()
    if _telethon_client is not None:
        await _safe_disconnect(_telethon_client)
        _telethon_client = None
    if _telethon_status == "connected":
        _telethon_status = "failed"


async def _load_session_from_db() -> str | None:
    """Load the latest Telethon session string from the database.

    Returns None if the table is empty or unreachable (caller falls back to env var).
    """
    try:
        from sqlalchemy import select

        from app.database import async_session
        from app.models.settings import TelethonSession

        async with async_session() as db:
            row = (
                await db.execute(
                    select(TelethonSession).where(TelethonSession.id == 1)
                )
            ).scalar_one_or_none()
            if row and row.session_string:
                return row.session_string
    except Exception as e:
        logger.warning(f"Could not load Telethon session from DB: {e}")
    return None


async def _save_session_to_db(session_string: str) -> None:
    """Persist updated session string to DB.

    Called after every successful connect() so that DC migrations and key
    refreshes issued by Telegram are never lost between container restarts.
    """
    try:
        from sqlalchemy import select

        from app.database import async_session
        from app.models.settings import TelethonSession

        async with async_session() as db:
            row = (
                await db.execute(
                    select(TelethonSession).where(TelethonSession.id == 1)
                )
            ).scalar_one_or_none()
            if row:
                row.session_string = session_string
            else:
                db.add(TelethonSession(id=1, session_string=session_string))
            await db.commit()
            logger.info("Telethon session saved to DB.")
    except Exception as e:
        logger.error(f"Failed to save Telethon session to DB: {e}")


async def get_channel_info_bot_api(channel_username: str) -> dict | None:
    """Get basic channel info using Bot API (safe, no user account needed).

    Returns: {name, description, subscribers_count, photo_url} where photo_url is tg:<file_id> or None
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

            # Store token-free file_id ref (public URL built at response time)
            photo_url = None
            if chat_data.get("photo"):
                file_id = chat_data["photo"].get("big_file_id")
                if file_id:
                    from app.utils.avatars import store_avatar_ref
                    photo_url = store_avatar_ref(file_id)

            return {
                "name": chat_data.get("title", ""),
                "description": chat_data.get("description", ""),
                "subscribers_count": members,
                "photo_url": photo_url,
                "username": chat_data.get("username", channel_username),
            }
    except Exception as e:
        from app.utils.log_redact import redact
        logger.error(f"Bot API channel info failed for @{channel_username}: {redact(e)}")
        return None


async def get_channel_stats_telethon(channel_username: str, message_limit: int = 5000) -> dict | None:
    """Get detailed channel stats using Telethon (MTProto).

    Collects historical daily stats from messages for graphs.
    Returns: {avg_views, er, avg_reach, adv_reach_12h, adv_reach_24h, adv_reach_48h,
              channel_age_months, daily_stats: [{date, views, subscribers}],
              posts: [{telegram_msg_id, date, text, media_type, link, views, forwards, reactions, comments}]}
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
        username = getattr(entity, 'username', channel_username)

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
        daily_forwards = defaultdict(list)
        daily_reactions = defaultdict(list)

        # Individual posts data
        posts_data = []

        for msg in messages:
            msg_date = msg.date.replace(tzinfo=timezone.utc)

            # Track last post date
            if last_post_date is None or msg_date > last_post_date:
                last_post_date = msg_date

            # Count posts in last 30 days
            if (now - msg_date).days <= 30:
                posts_last_30d += 1

            # Determine media type
            media_type = None
            if msg.photo:
                media_type = "photo"
            elif msg.video:
                media_type = "video"
            elif msg.document:
                media_type = "document"
            elif msg.audio:
                media_type = "audio"
            elif msg.voice:
                media_type = "voice"

            # Count reactions
            msg_reactions = 0
            if hasattr(msg, 'reactions') and msg.reactions:
                if hasattr(msg.reactions, 'results'):
                    msg_reactions = sum(r.count for r in msg.reactions.results)

            # Count comments
            msg_comments = 0
            if hasattr(msg, 'replies') and msg.replies:
                msg_comments = msg.replies.replies or 0

            # Build post link
            post_link = f"t.me/{username}/{msg.id}" if username else None

            # Store individual post data (last 200 posts for storage)
            if len(posts_data) < 200:
                posts_data.append({
                    "telegram_msg_id": msg.id,
                    "date": msg_date.replace(tzinfo=None).isoformat(),
                    "text": (msg.text or "")[:2000],  # Truncate long texts
                    "media_type": media_type,
                    "link": post_link,
                    "views": msg.views or 0,
                    "forwards": msg.forwards or 0,
                    "reactions": msg_reactions,
                    "comments": msg_comments,
                })

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
                day_key = msg_date.strftime("%Y-%m-%d")
                daily_forwards[day_key].append(msg.forwards)

            # Reactions
            if msg_reactions > 0:
                reactions_list.append(msg_reactions)
                day_key = msg_date.strftime("%Y-%m-%d")
                daily_reactions[day_key].append(msg_reactions)

        avg_views = sum(views_list) // len(views_list) if views_list else 0
        views_hidden = len(views_list) == 0 and len(messages) > 0
        er = round((avg_views / subscribers * 100), 2) if subscribers > 0 else 0.0
        avg_forwards = sum(forwards_list) // len(forwards_list) if forwards_list else 0
        avg_reactions = sum(reactions_list) // len(reactions_list) if reactions_list else 0
        post_frequency = round(posts_last_30d / 30, 1) if posts_last_30d > 0 else 0.0

        # Build daily stats for graphs (sorted by date)
        daily_stats = []
        for date_str in sorted(daily_views.keys()):
            day_views = daily_views[date_str]
            day_avg = sum(day_views) // len(day_views)
            day_er = round((day_avg / subscribers * 100), 2) if subscribers > 0 else 0.0
            day_fwd = daily_forwards.get(date_str, [])
            day_react = daily_reactions.get(date_str, [])
            daily_stats.append({
                "date": date_str,
                "avg_views": day_avg,
                "subscribers": subscribers,
                "er": day_er,
                "post_count": len(day_views),
                "avg_forwards": sum(day_fwd) // len(day_fwd) if day_fwd else 0,
                "avg_reactions": sum(day_react) // len(day_react) if day_react else 0,
            })

        # Add delay to avoid rate-limiting
        await asyncio.sleep(2)

        return {
            "subscribers": subscribers,
            "avg_views": avg_views,
            "views_hidden": views_hidden,
            "er": er,
            "avg_reach": avg_views,
            "adv_reach_12h": sum(reach_12h) // len(reach_12h) if reach_12h else 0,
            "adv_reach_24h": sum(reach_24h) // len(reach_24h) if reach_24h else 0,
            "adv_reach_48h": sum(reach_48h) // len(reach_48h) if reach_48h else 0,
            "channel_age_months": channel_age_months,
            "daily_stats": daily_stats,
            "total_posts": total_posts,
            "post_frequency": post_frequency,
            "last_post_date": last_post_date.replace(tzinfo=None).isoformat() if last_post_date else None,
            "avg_forwards": avg_forwards,
            "avg_reactions": avg_reactions,
            "posts": posts_data,
        }
    except Exception as e:
        logger.error(f"Telethon stats failed for @{channel_username}: {e}")
        return None


def parse_telegram_link(telegram_link: str) -> tuple[str, str]:
    """Parse a Telegram link/handle into (identifier, kind).

    kind is "invite" for private join-request links (t.me/+hash,
    t.me/joinchat/hash) which cannot be resolved via username-based
    lookups (Bot API / Telethon get_entity both fail on these), or
    "username" for anything else (public @handle or t.me/handle).
    """
    raw = telegram_link.strip()
    for prefix in ("https://", "http://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    if raw.startswith("t.me/"):
        raw = raw[len("t.me/"):]
    elif raw.startswith("@"):
        raw = raw[1:]

    if raw.startswith("+") or raw.startswith("joinchat/"):
        identifier = raw[1:] if raw.startswith("+") else raw[len("joinchat/"):]
        return identifier, "invite"

    return raw.strip("/"), "username"


async def collect_channel_stats(telegram_link: str, message_limit: int = 5000) -> dict:
    """Collect stats using hybrid approach: Bot API + Telethon.

    Returns combined info dict.
    """
    username, link_kind = parse_telegram_link(telegram_link)

    result = {
        "channel_name": username,
        "subscribers_count": 0,
        "avg_views": 0,
        "er": 0.0,
        "avatar_url": None,
        "adv_reach_12h": 0,
        "adv_reach_24h": 0,
        "adv_reach_48h": 0,
        "channel_age_months": None,
        "daily_stats": [],
        "total_posts": 0,
        "post_frequency": 0.0,
        "last_post_date": None,
        "avg_forwards": 0,
        "avg_reactions": 0,
        "posts": [],
    }

    if link_kind == "invite":
        # Private join-request invite link — Bot API and Telethon both need a
        # resolvable username, so there's nothing to fetch here. Seller
        # provides stats manually for these (see is_closed handling in the
        # channels router).
        logger.info(f"[STATS] {username} is a private invite-link (closed) channel — skipping auto-collection")
        return result

    # Step 1: Bot API (safe, always works)
    bot_info = await get_channel_info_bot_api(username)
    if bot_info:
        result["channel_name"] = bot_info["name"] or username
        result["subscribers_count"] = bot_info["subscribers_count"]
        result["avatar_url"] = bot_info["photo_url"]
        logger.info(f"[STATS] @{username} Bot API ✓ subs={bot_info['subscribers_count']}")
    else:
        logger.warning(f"[STATS] @{username} Bot API failed — check BOT_TOKEN_STATS")

    # Step 2: Telethon (deeper stats, may fail)
    telethon_stats = await get_channel_stats_telethon(username, message_limit=message_limit)
    if telethon_stats:
        result["subscribers_count"] = telethon_stats["subscribers"]
        result["avg_views"] = telethon_stats["avg_views"]
        result["er"] = telethon_stats["er"]
        result["adv_reach_12h"] = telethon_stats.get("adv_reach_12h") or 0
        result["adv_reach_24h"] = telethon_stats.get("adv_reach_24h") or 0
        result["adv_reach_48h"] = telethon_stats.get("adv_reach_48h") or 0
        result["channel_age_months"] = telethon_stats.get("channel_age_months")
        result["daily_stats"] = telethon_stats.get("daily_stats", [])
        result["total_posts"] = telethon_stats.get("total_posts") or 0
        result["post_frequency"] = telethon_stats.get("post_frequency") or 0.0
        result["last_post_date"] = telethon_stats.get("last_post_date")
        result["avg_forwards"] = telethon_stats.get("avg_forwards") or 0
        result["avg_reactions"] = telethon_stats.get("avg_reactions") or 0
        result["posts"] = telethon_stats.get("posts", [])
        result["views_hidden"] = telethon_stats.get("views_hidden", False)
        logger.info(f"[STATS] @{username} Telethon ✓ views={result['avg_views']} er={result['er']}% days={len(result['daily_stats'])} posts={len(result['posts'])} views_hidden={result['views_hidden']}")
    else:
        logger.warning(f"[STATS] @{username} Telethon failed — no views/ER/posts data")

    return result
