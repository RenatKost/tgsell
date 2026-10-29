"""Bot deep-link login (@tgsell_auth_bot): user find-or-create + UTM attribution.

The site visitor's anon id + first-touch utm_* are bound to the one-time token when it is created
(POST /auth/bot-token), so attribution survives the Telegram roundtrip even when the visitor never
returns to the same in-app browser (Instagram WebView → Telegram app → …): the user is created as
soon as they confirm in the bot, with the campaign of the visit that produced the token.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

logger = logging.getLogger("app.utm")


async def ensure_bot_user(db, user_data: dict, utm_src) -> tuple:
    """Find or create the Telegram user; UTM first-touch only for a NEW user. Returns (user, created)."""
    from app.models.user import User
    from app.services.utm import apply
    user = (await db.execute(select(User).where(User.telegram_id == user_data["id"]))).scalar_one_or_none()
    created = user is None
    if created:
        user = User(telegram_id=user_data["id"], username=user_data.get("username"),
                    first_name=user_data.get("first_name") or "User", avatar_url=None)
        try:
            apply(user, utm_src or {})
        except Exception:  # attribution must never block a login
            pass
        db.add(user)
    else:
        user.username = user_data.get("username") or user.username
        user.first_name = user_data.get("first_name") or user.first_name
    await db.commit()
    await db.refresh(user)
    return user, created


async def finalize_bot_auth(token: str, user_data: dict) -> bool:
    """Called from the bot on «Увійти в TgSell»: complete the token and register the user right away."""
    from app.utils.auth_tokens import complete_auth_token, get_meta
    meta = get_meta(token)
    if not complete_auth_token(token, user_data):
        return False
    try:
        from app.database import async_session
        async with async_session() as db:
            user, created = await ensure_bot_user(db, user_data, meta)
        logger.info(f"[auth] bot confirm user_id={user.id} new={created} campaign={meta.get('utm_campaign') or '-'}")
    except Exception as e:  # the site poll (bot-check) still creates the user
        logger.warning("bot confirm: user not created early: %s", type(e).__name__)
    return True
