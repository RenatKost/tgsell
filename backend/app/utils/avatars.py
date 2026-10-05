"""Channel avatar helpers — keep Telegram bot tokens out of DB and API responses.

Internal storage format (channels.avatar_url):
  "tg:<file_id>"  — Telegram Bot API file_id only (no token, no file path)

Public API always exposes a same-origin proxy path:
  "/api/media/channel-avatar/{channel_id}"

The media endpoint calls getFile server-side and streams bytes; the token
never appears in responses, redirects, or (thanks to log hygiene) logs.
"""
from __future__ import annotations

LEAK_MARKER = "api.telegram.org/file/bot"
TG_PREFIX = "tg:"
PUBLIC_PREFIX = "/api/media/channel-avatar/"


def store_avatar_ref(file_id: str | None) -> str | None:
    """Build the token-free DB value from a Telegram file_id."""
    if not file_id:
        return None
    fid = str(file_id).strip()
    if not fid or LEAK_MARKER in fid or "api.telegram.org" in fid:
        return None
    if fid.startswith(TG_PREFIX):
        return fid
    return f"{TG_PREFIX}{fid}"


def parse_stored_file_id(stored: str | None) -> str | None:
    """Extract file_id from a stored avatar_url value, or None."""
    if not stored:
        return None
    if LEAK_MARKER in stored or (
        "api.telegram.org" in stored and not stored.startswith(TG_PREFIX)
    ):
        return None
    if stored.startswith(TG_PREFIX):
        fid = stored[len(TG_PREFIX) :].strip()
        return fid or None
    return None


def public_channel_avatar_url(channel_id: int | None, stored: str | None) -> str | None:
    """Map a stored avatar ref to the public proxy URL (or None).

    Defensively drops any value that still contains a Bot API file URL with token.
    """
    if channel_id is None or not stored:
        return None
    if LEAK_MARKER in stored or "api.telegram.org" in stored:
        return None
    if stored.startswith(TG_PREFIX) or stored.startswith(PUBLIC_PREFIX):
        return f"{PUBLIC_PREFIX}{channel_id}"
    # Unknown non-Telegram value — do not invent a proxy URL
    return None


def scrub_leaked_avatar_url(value: str | None) -> str | None:
    """Drop avatar URLs that embed a bot token (any entity)."""
    if not value:
        return None
    if LEAK_MARKER in value or (
        "api.telegram.org" in value and "/file/bot" in value
    ):
        return None
    return value
