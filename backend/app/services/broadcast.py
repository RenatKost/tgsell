"""Admin one-off broadcast through the alerts bot.

Segment «продавці з активним лотом»: distinct sellers with ≥1 published (approved) channel
or bundle not in the exclusion lists, subscribed to the alerts bot (/start seen, not
unreachable), not blocked, never the owners' accounts. Idempotent per campaign_key via
UNIQUE(campaign_key, user_id): a row is claimed (pending → sending) before the send, so a
re-run never messages anyone who already got (or may have got) the campaign.
"""
from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import func, or_, select, update

from app.models.broadcast import BroadcastLog
from app.models.bundle import BundleStatus, ChannelBundle
from app.models.channel import Channel, ChannelStatus
from app.models.user import User
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

ALWAYS_EXCLUDED_USERNAMES = ("renat_kos", "ox010010")
MAX_RECIPIENTS = 500
SEND_INTERVAL_SEC = 0.1  # ≈10 msg/s
TEXT_MAX = 4000
KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{3,64}$")

_tasks: dict[str, asyncio.Task] = {}


class BroadcastError(Exception):
    pass


def validate_key(key: str) -> str:
    key = (key or "").strip()
    if not KEY_RE.match(key):
        raise BroadcastError("campaign_key: 3–64 символи, латиниця, цифри, _ . : -")
    return key


async def segment_active_sellers(db, exclude_channel_ids=(), exclude_bundle_ids=(), include_no_bot: bool = False) -> list[User]:
    """Subscribed sellers by default; include_no_bot=True also returns those without the bot
    (split later with split_no_bot for the dry-run «без бота» list)."""
    ch_q = select(Channel.seller_id).where(Channel.status == ChannelStatus.approved)
    if exclude_channel_ids:
        ch_q = ch_q.where(Channel.id.notin_(list(exclude_channel_ids)))
    b_q = select(ChannelBundle.seller_id).where(ChannelBundle.status == BundleStatus.approved)
    if exclude_bundle_ids:
        b_q = b_q.where(ChannelBundle.id.notin_(list(exclude_bundle_ids)))
    q = (select(User).where(
        or_(User.id.in_(ch_q), User.id.in_(b_q)),
        *(() if include_no_bot else (User.telegram_id.isnot(None),
                                      User.tg_bot_started_at.isnot(None),
                                      User.tg_bot_unreachable_at.is_(None))),
        User.is_blocked.is_(False),
        User.is_active.is_(True),
        or_(User.username.is_(None), func.lower(User.username).notin_(ALWAYS_EXCLUDED_USERNAMES)),
    ).order_by(User.id))
    return list((await db.execute(q)).scalars().all())


# ---- Campaign relist_top7_2026_10_27: sellers of lots that left the catalog ----
RELIST_SEGMENT = "relist_top7"
RELIST_KEY = "relist_top7_2026_10_27"
RELIST_TEXT = ("Вітаємо! До 1 листопада на TgSell діє акція: кожен новий лот, який схвалить модерація, "
               "отримує «Топ» на 7 днів безкоштовно (зазвичай це 10 USDT). Якщо ваш канал ще продається, "
               "виставте його знову: https://tgsell.me/sell. Розміщення безкоштовне, комісія 3% береться лише після угоди.")
RELIST_EXCLUDE_CHANNEL_IDS = (61, 94, 95, 96, 15, 16, 17, 18)
RELIST_EXCLUDE_BUNDLE_IDS = (1,)
LOT_STATUS_LABELS = {"removed": "знятий", "sold": "проданий", "rejected": "знятий з публікації", "inactive": "неактивний"}


def _subscribed(u: User) -> bool:
    return bool(u.telegram_id and u.tg_bot_started_at and not u.tg_bot_unreachable_at)


# ---- no_bot: users who never started the alerts bot or are unreachable ----
NO_BOT_LABELS = {
    "no_telegram": "немає Telegram-акаунта (надіслати неможливо)",
    "not_started": "не запускав бота",
    "unreachable": "бот недоступний (заблокував або видалив чат)",
}


def no_bot_reason(u: User) -> str | None:
    if not u.telegram_id:
        return "no_telegram"
    if u.tg_bot_unreachable_at:
        return "unreachable"
    if not u.tg_bot_started_at:
        return "not_started"
    return None


def no_bot_item(u: User, **extra) -> dict:
    reason = no_bot_reason(u)
    return {"user_id": u.id, "username": u.username, "reason": reason,
            "reason_label": NO_BOT_LABELS.get(reason, ""), "can_try": bool(u.telegram_id), **extra}


def split_no_bot(users: list[User]) -> tuple[list[User], list[User]]:
    """→ (subscribed, no_bot). Order preserved."""
    sub = [u for u in users if _subscribed(u)]
    return sub, [u for u in users if not _subscribed(u)]


def with_try_no_bot(subscribed: list[User], no_bot: list[User], try_no_bot: bool) -> list[User]:
    """Audience to send to. no_bot users are added only when the admin ticked «спробувати надіслати»
    (off by default), and only those with a Telegram account."""
    if not try_no_bot:
        return list(subscribed)
    return list(subscribed) + [u for u in no_bot if u.telegram_id]


# ---- Targeted (адресна) розсилка: explicit list of users / lots ----
TARGETED_SEGMENT = "targeted"
TARGETS_MAX_TOKENS = 1000
_TOKEN_SPLIT = re.compile(r"[\s,;]+")
_USERNAME_RE = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{3,31})$")


def parse_targets(raw: str) -> dict:
    """«12, @seller, #45, lot:45, user:12» → user ids / usernames / lot (channel) ids / invalid tokens.
    Bare digits = user ID on TgSell; #N or lot:N = lot (its seller); @name = Telegram username."""
    out = {"user_ids": [], "usernames": [], "lot_ids": [], "invalid": []}
    tokens = [t for t in _TOKEN_SPLIT.split(raw or "") if t][:TARGETS_MAX_TOKENS]
    for t in tokens:
        low = t.lower()
        m_lot = re.fullmatch(r"(?:#|lot:)(\d{1,9})", low)
        m_user = re.fullmatch(r"(?:user:|id:)?(\d{1,9})", low)
        m_name = _USERNAME_RE.match(t)
        if m_lot:
            out["lot_ids"].append(int(m_lot.group(1)))
        elif m_user:
            out["user_ids"].append(int(m_user.group(1)))
        elif m_name and (t.startswith("@") or not t.isdigit()):
            out["usernames"].append(m_name.group(1).lower())
        else:
            out["invalid"].append(t[:64])
    for k in ("user_ids", "usernames", "lot_ids"):
        out[k] = list(dict.fromkeys(out[k]))
    return out


async def segment_targeted(db, raw: str) -> dict:
    """Resolve an explicit target list → {"users": [User…] (all, bot status not filtered),
    "not_found": [tokens], "invalid": [tokens], "excluded": [user ids blocked/inactive/owners]}."""
    t = parse_targets(raw)
    found: dict[int, User] = {}
    not_found: list[str] = []
    if t["user_ids"]:
        rows = (await db.execute(select(User).where(User.id.in_(t["user_ids"])))).scalars().all()
        for u in rows:
            found[u.id] = u
        have = {u.id for u in rows}
        not_found += [str(i) for i in t["user_ids"] if i not in have]
    if t["usernames"]:
        rows = (await db.execute(select(User).where(func.lower(User.username).in_(t["usernames"])))).scalars().all()
        for u in rows:
            found[u.id] = u
        have = {(u.username or "").lower() for u in rows}
        not_found += [f"@{n}" for n in t["usernames"] if n not in have]
    if t["lot_ids"]:
        rows = (await db.execute(select(Channel.id, Channel.seller_id).where(Channel.id.in_(t["lot_ids"])))).all()
        sellers = {sid for _, sid in rows}
        have = {cid for cid, _ in rows}
        not_found += [f"#{i}" for i in t["lot_ids"] if i not in have]
        missing = sellers - set(found)
        if missing:
            for u in (await db.execute(select(User).where(User.id.in_(list(missing))))).scalars().all():
                found[u.id] = u
    users, excluded = [], []
    for u in sorted(found.values(), key=lambda x: x.id):
        if u.is_blocked or not u.is_active or (u.username or "").lower() in ALWAYS_EXCLUDED_USERNAMES:
            excluded.append(u.id)
            continue
        users.append(u)
    return {"users": users, "not_found": not_found, "invalid": t["invalid"], "excluded": excluded}


def confirm_token(key: str, segment: str, text: str, try_no_bot: bool, user_ids: list[int]) -> str:
    """Token returned by the dry-run; a real send must echo it. Changes whenever the audience, the
    text or the checkbox changes, so nothing goes out that the admin didn't see in the dry-run."""
    import hashlib
    raw = "|".join([key, segment, (text or "").strip(), "1" if try_no_bot else "0",
                    ",".join(str(i) for i in sorted(user_ids))])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


async def segment_relist(db, exclude_channel_ids=(), exclude_bundle_ids=()) -> dict:
    """Lots that are now removed / sold / unpublished-after-publication (rejected with first_approved_at)
    / inactive (approved but unreachable). Grouped per seller → {"recipients": [...], "no_bot": [...]}.
    Lots whose channel is already listed again (another pending/approved row, same link) are skipped."""
    from app.models.bundle import BundleChannel
    from app.services.promo_top import link_key
    ex_ch = set(RELIST_EXCLUDE_CHANNEL_IDS) | set(exclude_channel_ids or ())
    ex_b = list(set(RELIST_EXCLUDE_BUNDLE_IDS) | set(exclude_bundle_ids or ()))
    ex_ch |= set((await db.execute(select(BundleChannel.channel_id).where(BundleChannel.bundle_id.in_(ex_b)))).scalars())
    gone = or_(
        Channel.status.in_([ChannelStatus.removed, ChannelStatus.sold]),
        (Channel.status == ChannelStatus.rejected) & Channel.first_approved_at.isnot(None),
        (Channel.status == ChannelStatus.approved) & Channel.inactive_since.isnot(None),
    )
    lots = (await db.execute(select(Channel).where(gone).order_by(Channel.id))).scalars().all()
    live = (await db.execute(select(Channel.telegram_link).where(
        Channel.status.in_([ChannelStatus.pending, ChannelStatus.approved]), Channel.inactive_since.is_(None)))).scalars().all()
    live_keys = {link_key(x) for x in live}
    per: dict[int, list[Channel]] = {}
    for c in lots:
        if c.id in ex_ch or link_key(c.telegram_link) in live_keys:
            continue
        per.setdefault(c.seller_id, []).append(c)
    users = (await db.execute(select(User).where(User.id.in_(list(per))).order_by(User.id))).scalars().all() if per else []
    rec, no_bot = [], []
    for u in users:
        if u.is_blocked or not u.is_active or (u.username or "").lower() in ALWAYS_EXCLUDED_USERNAMES:
            continue
        item = {"user_id": u.id, "username": u.username, "lots": [
            {"id": c.id, "channel": c.channel_name, "link": c.telegram_link,
             "status": "inactive" if c.status == ChannelStatus.approved else c.status.value,
             "status_label": LOT_STATUS_LABELS["inactive" if c.status == ChannelStatus.approved else c.status.value]}
            for c in per[u.id]]}
        if not _subscribed(u):
            item |= {"reason": no_bot_reason(u), "reason_label": NO_BOT_LABELS.get(no_bot_reason(u), ""),
                     "can_try": bool(u.telegram_id)}
        (rec if _subscribed(u) else no_bot).append((u, item))
    return {"recipients": rec, "no_bot": no_bot}


FAIL_REASON_LABELS = {
    "unreachable": "бот заблоковано або чат не запущено",
    "rate_limit": "ліміт Telegram (429)",
    "other": "інша помилка",
}


def fail_reason(error: str | None) -> str:
    t = (error or "").lower()
    if any(x in t for x in ("forbidden", "blocked", "chat not found", "deactivated", "bot can't initiate")):
        return "unreachable"
    if "retryafter" in t or "too many requests" in t or "flood" in t:
        return "rate_limit"
    return "other"


async def errors(db, key: str) -> list[dict]:
    rows = (await db.execute(select(BroadcastLog.user_id, User.username, BroadcastLog.error)
                             .join(User, User.id == BroadcastLog.user_id)
                             .where(BroadcastLog.campaign_key == key, BroadcastLog.status == "failed")
                             .order_by(BroadcastLog.id))).all()
    return [{"user_id": uid, "username": un, "error": err, "reason": fail_reason(err),
             "reason_label": FAIL_REASON_LABELS[fail_reason(err)]} for uid, un, err in rows]


async def stats(db, key: str) -> dict:
    rows = dict((await db.execute(select(BroadcastLog.status, func.count(BroadcastLog.id))
                                  .where(BroadcastLog.campaign_key == key).group_by(BroadcastLog.status))).all())
    sent, failed = rows.get("sent", 0), rows.get("failed", 0)
    pending = rows.get("pending", 0) + rows.get("sending", 0)
    task = _tasks.get(key)
    errs = await errors(db, key)
    reasons: dict[str, int] = {}
    for e in errs:
        reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
    return {"campaign_key": key, "total": sent + failed + pending, "sent": sent, "failed": failed,
            "pending": pending, "running": bool(task and not task.done()), "errors": errs,
            "fail_reasons": reasons}


async def prepare(db, key: str, users: list[User]) -> dict:
    """Insert pending rows for users without a row in this campaign (UNIQUE guards races)."""
    existing = set((await db.execute(select(BroadcastLog.user_id).where(BroadcastLog.campaign_key == key))).scalars())
    new = [u.id for u in users if u.id not in existing]
    for uid in new:
        db.add(BroadcastLog(campaign_key=key, user_id=uid, status="pending"))
    await db.commit()
    return {"already_in_campaign": len(users) - len(new), "added": len(new)}


def _is_unreachable(e: Exception) -> bool:
    from app.services.chat_bridge import is_unreachable_error
    text = f"{type(e).__name__} {e}".lower()
    return is_unreachable_error(e) or "forbidden" in text or "blocked" in text


RETRY_AFTER_MAX_SEC = 60


def _retry_after(e: Exception) -> float | None:
    """Seconds to wait for a Telegram 429 (aiogram TelegramRetryAfter.retry_after), else None."""
    ra = getattr(e, "retry_after", None)
    if ra is None and type(e).__name__ != "TelegramRetryAfter":
        return None
    try:
        return float(min(max(float(ra or 1), 0.0), RETRY_AFTER_MAX_SEC))
    except (TypeError, ValueError):
        return 1.0


async def run_campaign(session_factory, key: str, text: str, bot=None, interval: float = SEND_INTERVAL_SEC) -> dict:
    if bot is None:
        from app.services.chat_bridge import get_bot
        bot = get_bot()
    if bot is None:
        raise BroadcastError("Alert-бот не налаштований")
    sent = failed = 0
    async with session_factory() as db:
        ids = (await db.execute(select(BroadcastLog.id).where(
            BroadcastLog.campaign_key == key, BroadcastLog.status == "pending").order_by(BroadcastLog.id))).scalars().all()
        await db.commit()
    for log_id in ids:
        async with session_factory() as db:
            claimed = await db.execute(update(BroadcastLog).where(
                BroadcastLog.id == log_id, BroadcastLog.status == "pending").values(status="sending"))
            await db.commit()
            if claimed.rowcount != 1:
                continue  # another run took it
            row = await db.get(BroadcastLog, log_id)
            user = await db.get(User, row.user_id)
            try:
                try:
                    await bot.send_message(user.telegram_id, text, parse_mode="HTML", disable_web_page_preview=True)
                except Exception as e:
                    wait = _retry_after(e)
                    if wait is None:
                        raise
                    # Telegram 429: respect retry_after once, then try again
                    logger.warning(f"[BROADCAST] {key}: rate limited, sleeping {wait}s")
                    await asyncio.sleep(wait)
                    await bot.send_message(user.telegram_id, text, parse_mode="HTML", disable_web_page_preview=True)
                row.status, row.sent_at, row.error = "sent", utcnow_naive(), None
                if user.tg_bot_unreachable_at:  # delivered → reachable again («спробувати надіслати»)
                    user.tg_bot_unreachable_at = None
                sent += 1
            except Exception as e:
                row.status, row.error = "failed", f"{type(e).__name__}: {e}"[:1000]
                if _is_unreachable(e):
                    user.tg_bot_unreachable_at = utcnow_naive()
                failed += 1
                logger.warning(f"[BROADCAST] {key} → user #{row.user_id}: {type(e).__name__}")
            await db.commit()
        await asyncio.sleep(interval)
    logger.info(f"[BROADCAST] {key}: sent={sent} failed={failed}")
    return {"sent": sent, "failed": failed}


def start_background(session_factory, key: str, text: str) -> bool:
    task = _tasks.get(key)
    if task and not task.done():
        return False
    _tasks[key] = asyncio.get_running_loop().create_task(run_campaign(session_factory, key, text))
    return True
