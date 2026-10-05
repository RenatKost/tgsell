"""Public media proxy — serves channel avatars without exposing bot tokens."""
from __future__ import annotations

import logging
import mimetypes
import time
from collections import OrderedDict

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.channel import Channel
from app.utils.avatars import parse_stored_file_id
from app.utils.log_redact import redact

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

# Simple in-memory LRU: channel_id -> {bytes, content_type, expires}
_CACHE_MAX = 256
_CACHE_TTL = 86400  # 1 day, matches Cache-Control
_avatar_cache: OrderedDict[int, dict] = OrderedDict()


def _cache_get(channel_id: int) -> dict | None:
    entry = _avatar_cache.get(channel_id)
    if not entry:
        return None
    if entry["expires"] < time.time():
        _avatar_cache.pop(channel_id, None)
        return None
    _avatar_cache.move_to_end(channel_id)
    return entry


def _cache_put(channel_id: int, data: bytes, content_type: str) -> None:
    _avatar_cache[channel_id] = {
        "bytes": data,
        "content_type": content_type,
        "expires": time.time() + _CACHE_TTL,
    }
    _avatar_cache.move_to_end(channel_id)
    while len(_avatar_cache) > _CACHE_MAX:
        _avatar_cache.popitem(last=False)


@router.get("/channel-avatar/{channel_id}")
async def get_channel_avatar(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Stream a channel avatar via Bot API getFile. Token never leaves the server."""
    cached = _cache_get(channel_id)
    if cached:
        return Response(
            content=cached["bytes"],
            media_type=cached["content_type"],
            headers={"Cache-Control": "public, max-age=86400"},
        )

    channel = await db.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Not found")

    file_id = parse_stored_file_id(channel.avatar_url)
    if not file_id:
        raise HTTPException(status_code=404, detail="No avatar")

    if not settings.bot_token_stats:
        logger.warning("BOT_TOKEN_STATS not configured — cannot serve avatar")
        raise HTTPException(status_code=404, detail="No avatar")

    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            # getFile — do not log URL (contains token); httpx silenced to WARNING
            meta = await http.get(
                f"https://api.telegram.org/bot{settings.bot_token_stats}/getFile",
                params={"file_id": file_id},
            )
            if meta.status_code != 200:
                raise HTTPException(status_code=404, detail="No avatar")
            body = meta.json()
            if not body.get("ok"):
                raise HTTPException(status_code=404, detail="No avatar")
            file_path = (body.get("result") or {}).get("file_path")
            if not file_path:
                raise HTTPException(status_code=404, detail="No avatar")

            file_resp = await http.get(
                f"https://api.telegram.org/file/bot{settings.bot_token_stats}/{file_path}"
            )
            if file_resp.status_code != 200 or not file_resp.content:
                raise HTTPException(status_code=404, detail="No avatar")

            content_type = file_resp.headers.get("content-type")
            if not content_type or content_type == "application/octet-stream":
                guessed, _ = mimetypes.guess_type(file_path)
                content_type = guessed or "image/jpeg"

            data = file_resp.content
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Avatar fetch failed for channel %s: %s", channel_id, redact(e))
        raise HTTPException(status_code=404, detail="No avatar") from None

    _cache_put(channel_id, data, content_type)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
