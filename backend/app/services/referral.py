"""«Приведи продавця»: referral links, binding, and the free 7-day «Топ» reward.

Rules (simple and auditable):
* every user gets a stable ``ref_code``; link = {frontend}/?ref=<code>; the site keeps it
  (localStorage + cookie, 30 days) and sends it with the first lot submission;
* binding: the referred user's FIRST valid referrer wins (``users.referred_by_id``) and the new lot
  records ``channels.referrer_id``; self-referral is refused — same user, same telegram_id, or the
  referrer already has (had) a lot of the same Telegram channel;
* reward: when a referred lot is approved by moderation for the FIRST time, the referrer gets a free
  7-day «Топ» (promo Top: ``top_source="promo"``, outside the paid 3-slot limit, no payment row) on
  their ACTIVE (approved) lot with most subscribers. A longer existing Top is never shortened. If the
  referrer has no active lot → a «credit» row applied to the referrer's next lot on its first approval.
  ONE reward per referred seller (UNIQUE referred_user_id).
* the free «Перевірено TgSell» badge is NOT a referral reward (CEO decision; migration 0056 revoked
  the badges granted earlier and turned unused badge credits into Top credits).
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select

from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)
REFERRAL_TOP_DAYS = 7
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def _new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(8))


async def ensure_code(db, user) -> str:
    from app.models.user import User
    user = await db.get(User, user.id) or user  # same-session instance (request user may be detached)
    if user.ref_code:
        return user.ref_code
    for _ in range(10):
        code = _new_code()
        if (await db.execute(select(User.id).where(User.ref_code == code))).scalar_one_or_none() is None:
            user.ref_code = code
            await db.commit()
            return code
    raise RuntimeError("cannot allocate ref code")


async def _referrer_owns_channel(db, referrer_id: int, telegram_link: str) -> bool:
    from app.models.channel import Channel
    from app.services.promo_top import link_key
    key = link_key(telegram_link)
    links = (await db.execute(select(Channel.telegram_link).where(Channel.seller_id == referrer_id))).scalars().all()
    return bool(key) and any(link_key(x) == key for x in links)


async def is_self_referral(db, referrer, user, telegram_link: str | None) -> bool:
    if referrer.id == user.id:
        return True
    if referrer.telegram_id and user.telegram_id and referrer.telegram_id == user.telegram_id:
        return True
    return bool(telegram_link) and await _referrer_owns_channel(db, referrer.id, telegram_link)


async def bind_on_submit(db, user, channel, ref_code: str | None) -> None:
    """Called on lot creation (before commit). Sets channel.referrer_id (+ user.referred_by_id once)."""
    from app.models.user import User
    user = await db.get(User, user.id) or user
    referrer = None
    if user.referred_by_id:
        referrer = await db.get(User, user.referred_by_id)
    elif ref_code:
        referrer = (await db.execute(select(User).where(User.ref_code == ref_code.strip().lower()))).scalar_one_or_none()
    if referrer is None or referrer.is_blocked or not referrer.is_active:
        return
    if await is_self_referral(db, referrer, user, channel.telegram_link):
        return
    if user.referred_by_id is None:
        user.referred_by_id = referrer.id
    channel.referrer_id = referrer.id


async def _best_active_lot(db, referrer_id: int):
    from app.models.channel import Channel, ChannelStatus
    q = select(Channel).where(Channel.seller_id == referrer_id, Channel.status == ChannelStatus.approved)
    return (await db.execute(q.order_by(Channel.subscribers_count.desc().nulls_last(), Channel.id))).scalars().first()


def grant_top(channel, now: datetime) -> bool:
    """Free promo Top for REFERRAL_TOP_DAYS. Never shortens a longer Top (paid or promo). True if changed."""
    from app.services.promo_top import PROMO_SOURCE
    target = now + timedelta(days=REFERRAL_TOP_DAYS)
    if channel.top_until and channel.top_until >= target:
        return False
    channel.top_until = target
    channel.top_source = PROMO_SOURCE
    return True


async def on_moderation_approve(db, channel, first_approval: bool, now: datetime | None = None) -> dict:
    """Hook for moderation approval (call BEFORE commit). Returns what happened (for tests/logs)."""
    from app.models.referral import ReferralReward
    from app.models.user import User
    now = now or utcnow_naive()
    out = {"reward": None, "credit_applied": False}
    if not first_approval:
        return out
    # 1) the approved lot's seller had an unused credit → free 7-day Top on this lot
    credit = (await db.execute(select(ReferralReward).where(
        ReferralReward.referrer_id == channel.seller_id, ReferralReward.status == "credit")
        .order_by(ReferralReward.id).limit(1))).scalar_one_or_none()
    if credit is not None:
        grant_top(channel, now)
        credit.status, credit.awarded_channel_id, credit.applied_at = "applied", channel.id, now
        out["credit_applied"] = True
    # 2) the lot came by referral → reward the referrer once per referred seller
    if channel.referrer_id:
        exists = (await db.execute(select(ReferralReward.id).where(
            ReferralReward.referred_user_id == channel.seller_id))).scalar_one_or_none()
        referrer = await db.get(User, channel.referrer_id)
        seller = await db.get(User, channel.seller_id)
        if exists is None and referrer is not None and seller is not None \
                and not await is_self_referral(db, referrer, seller, channel.telegram_link):
            lot = await _best_active_lot(db, referrer.id)
            r = ReferralReward(referrer_id=referrer.id, referred_user_id=seller.id, source_channel_id=channel.id,
                               created_at=now, status="credit")
            if lot is not None:
                grant_top(lot, now)
                r.status, r.awarded_channel_id, r.applied_at = "applied", lot.id, now
            db.add(r)
            out["reward"] = r.status
            logger.info(f"[REFERRAL] referrer #{referrer.id} ← seller #{seller.id}: {r.status}")
    return out


async def summary(db, user) -> dict:
    from app.config import settings
    from app.models.referral import ReferralReward
    code = await ensure_code(db, user)
    rows = (await db.execute(select(ReferralReward.status).where(ReferralReward.referrer_id == user.id))).scalars().all()
    return {"code": code, "link": f"{settings.frontend_url.rstrip('/')}/?ref={code}",
            "rewards_applied": sum(1 for s in rows if s == "applied"),
            "credits": sum(1 for s in rows if s == "credit")}
