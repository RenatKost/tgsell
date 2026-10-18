"""Weekly admin report: read-only counts + Ukrainian Telegram text.

Read-only: only SELECTs against business tables. The only write in this module is the
idempotency row in ``scheduled_report_runs`` (see ``claim_weekly_report``), which is a
separate log table and never touches users/channels/deals.

All DB datetimes are naive UTC (see app.utils.timeutil).
"""
from __future__ import annotations

import html
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import UserEvent, UserSession
from app.models.auction import Auction
from app.models.bundle import BundleStatus, ChannelBundle
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealStatus
from app.models.report import ScheduledReportRun
from app.models.saved_search import SavedSearch
from app.models.user import User
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

PERIOD_DAYS = 7
TOP_SOURCES = 10
NO_SOURCE = "(direct)"
UNKNOWN_SOURCE = "(невідомо)"

REPORT_TZ = ZoneInfo("Europe/Chisinau")
REPORT_WEEKDAY = 0  # Monday
REPORT_HOUR = 9
# If the container was down at 09:00, still send later the same day — never on Tue+.
CATCH_UP_HOURS = 12
MAX_ATTEMPTS = 3

DEAL_STATUS_UA = {
    DealStatus.created: "створено",
    DealStatus.payment_pending: "очікує оплату",
    DealStatus.paid: "оплачено",
    DealStatus.channel_transferring: "передача каналу",
    DealStatus.awaiting_payout: "очікує виплату",
    DealStatus.payout_in_progress: "виплата в процесі",
    DealStatus.completed: "завершено",
    DealStatus.disputed: "спір",
    DealStatus.cancelled: "скасовано",
}


async def _count(db: AsyncSession, stmt) -> int:
    return int((await db.execute(stmt)).scalar() or 0)


def _status_key(v) -> str:
    return getattr(v, "value", v)


async def _new_users_by_source(db: AsyncSession, since: datetime) -> tuple[Counter, Counter]:
    """First-touch attribution of users registered since ``since``: the earliest
    'visit' event of the user (by user_id or by an anon_id later linked to them)."""
    new_ids = set((await db.execute(select(User.id).where(User.created_at >= since))).scalars().all())
    by_utm: Counter = Counter()
    by_ref: Counter = Counter()
    if not new_ids:
        return by_utm, by_ref

    anon_owner: dict[str, int] = {}
    for model in (UserEvent, UserSession):
        rows = await db.execute(
            select(model.anon_id, func.min(model.user_id))
            .where(model.user_id.in_(new_ids), model.anon_id.is_not(None))
            .group_by(model.anon_id)
        )
        for aid, uid in rows.all():
            anon_owner.setdefault(aid, uid)

    conds = [UserEvent.user_id.in_(new_ids)]
    if anon_owner:
        conds.append(UserEvent.anon_id.in_(list(anon_owner)))
    rows = await db.execute(
        select(UserEvent.user_id, UserEvent.anon_id, UserEvent.utm_source, UserEvent.ref_domain,
               UserEvent.created_at, UserEvent.id)
        .where(UserEvent.event_type == "visit", or_(*conds))
        .order_by(UserEvent.created_at, UserEvent.id)
    )
    first: dict[int, tuple[str | None, str | None]] = {}
    for uid, aid, utm, ref, _c, _i in rows.all():
        owner = uid if uid in new_ids else anon_owner.get(aid)
        if owner is None or owner in first:
            continue
        first[owner] = (utm, ref)

    for uid in new_ids:
        if uid in first:
            utm, ref = first[uid]
            by_utm[utm or NO_SOURCE] += 1
            by_ref[ref or NO_SOURCE] += 1
        else:
            by_utm[UNKNOWN_SOURCE] += 1
            by_ref[UNKNOWN_SOURCE] += 1
    return by_utm, by_ref


async def _visits_by(db: AsyncSession, column, since: datetime) -> Counter:
    rows = await db.execute(
        select(column, func.count(UserEvent.id))
        .where(UserEvent.event_type == "visit", UserEvent.created_at >= since)
        .group_by(column)
    )
    out: Counter = Counter()
    for key, n in rows.all():
        out[key or NO_SOURCE] += int(n)
    return out


def _top(counter: Counter, limit: int = TOP_SOURCES) -> list[dict]:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"source": k, "count": v} for k, v in items[:limit]]


async def collect_weekly_stats(db: AsyncSession, now: datetime | None = None) -> dict:
    """Read-only snapshot. ``now`` is naive UTC."""
    now = now or utcnow_naive()
    since = now - timedelta(days=PERIOD_DAYS)

    users_total = await _count(db, select(func.count(User.id)))
    users_new = await _count(db, select(func.count(User.id)).where(User.created_at >= since))

    ch_ok = Channel.status == ChannelStatus.approved
    channels_total = await _count(db, select(func.count(Channel.id)).where(ch_ok))
    channels_new = await _count(db, select(func.count(Channel.id)).where(ch_ok, Channel.created_at >= since))

    b_ok = ChannelBundle.status == BundleStatus.approved
    bundles_total = await _count(db, select(func.count(ChannelBundle.id)).where(b_ok))
    bundles_new = await _count(db, select(func.count(ChannelBundle.id)).where(b_ok, ChannelBundle.created_at >= since))

    a_ok = Auction.status == "active"
    auctions_total = await _count(db, select(func.count(Auction.id)).where(a_ok))
    auctions_new = await _count(db, select(func.count(Auction.id)).where(a_ok, Auction.created_at >= since))

    deals_total = await _count(db, select(func.count(Deal.id)))
    deals_new = await _count(db, select(func.count(Deal.id)).where(Deal.created_at >= since))
    by_status = {s.value: 0 for s in DealStatus}
    for st, n in (await db.execute(select(Deal.status, func.count(Deal.id)).group_by(Deal.status))).all():
        by_status[_status_key(st)] = int(n)

    bot_subscribers = await _count(db, select(func.count(User.id)).where(
        User.telegram_id.is_not(None),
        User.tg_bot_started_at.is_not(None),
        User.tg_bot_unreachable_at.is_(None),
    ))
    saved_searches = await _count(db, select(func.count(SavedSearch.id)))

    nu_utm, nu_ref = await _new_users_by_source(db, since)
    v_utm = await _visits_by(db, UserEvent.utm_source, since)
    v_ref = await _visits_by(db, UserEvent.ref_domain, since)

    return {
        "period_days": PERIOD_DAYS,
        "period_start": since.replace(tzinfo=timezone.utc).isoformat(),
        "period_end": now.replace(tzinfo=timezone.utc).isoformat(),
        "users": {"total": users_total, "new": users_new},
        "channels": {"total": channels_total, "new": channels_new},
        "bundles": {"total": bundles_total, "new": bundles_new},
        "auctions": {"total": auctions_total, "new": auctions_new},
        "deals": {"total": deals_total, "new": deals_new, "by_status": by_status},
        "bot_subscribers": bot_subscribers,
        "saved_searches": saved_searches,
        "new_users_by_utm_source": _top(nu_utm),
        "new_users_by_ref_domain": _top(nu_ref),
        "visits": {
            "total": sum(v_utm.values()),
            "by_utm_source": _top(v_utm),
            "by_ref_domain": _top(v_ref),
        },
    }


def _fmt_dt_local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(REPORT_TZ).strftime("%d.%m.%Y")


def _src_lines(items: list[dict]) -> list[str]:
    if not items:
        return ["  —"]
    return [f"  • {html.escape(str(i['source']))}: {i['count']}" for i in items]


def build_weekly_report_text(stats: dict) -> str:
    """Ukrainian Telegram-HTML text (only <b> tags; dynamic values escaped)."""
    d = stats["deals"]
    lines = [
        "📊 <b>Тижневий звіт TgSell</b>",
        f"Період: {_fmt_dt_local(stats['period_start'])} — {_fmt_dt_local(stats['period_end'])} (останні 7 днів)",
        "",
        f"👤 <b>Користувачі:</b> {stats['users']['total']} (нових: +{stats['users']['new']})",
        f"📢 <b>Канали (схвалені):</b> {stats['channels']['total']} (нових: +{stats['channels']['new']})",
        f"📦 <b>Сітки (схвалені):</b> {stats['bundles']['total']} (нових: +{stats['bundles']['new']})",
        f"🔨 <b>Активні аукціони:</b> {stats['auctions']['total']} (нових: +{stats['auctions']['new']})",
        "",
        f"🤝 <b>Угоди:</b> {d['total']} (нових за 7 днів: +{d['new']})",
    ]
    for st in DealStatus:
        n = d["by_status"].get(st.value, 0)
        if n:
            lines.append(f"  • {DEAL_STATUS_UA[st]}: {n}")
    lines += [
        "",
        f"🤖 <b>Підписники бота:</b> {stats['bot_subscribers']}",
        f"🔎 <b>Збережені пошуки:</b> {stats['saved_searches']}",
        "",
        "🆕 <b>Нові користувачі за джерелом (utm_source):</b>",
        *_src_lines(stats["new_users_by_utm_source"]),
        "🆕 <b>Нові користувачі за доменом-реферером:</b>",
        *_src_lines(stats["new_users_by_ref_domain"]),
        "",
        f"👣 <b>Візити за 7 днів:</b> {stats['visits']['total']}",
        "<b>За utm_source:</b>",
        *_src_lines(stats["visits"]["by_utm_source"]),
        "<b>За доменом-реферером:</b>",
        *_src_lines(stats["visits"]["by_ref_domain"]),
    ]
    return "\n".join(lines)


# ── Schedule + idempotency ─────────────────────────────────────────────

def week_due(now_utc: datetime) -> tuple[str, datetime] | None:
    """If a weekly report is due right now, return (report_key, due_at_utc_naive).

    Due window: Monday 09:00 Europe/Chisinau .. +CATCH_UP_HOURS. ``now_utc`` is naive UTC.
    """
    local = now_utc.replace(tzinfo=timezone.utc).astimezone(REPORT_TZ)
    monday = (local - timedelta(days=(local.weekday() - REPORT_WEEKDAY) % 7)).date()
    due_local = datetime(monday.year, monday.month, monday.day, REPORT_HOUR, tzinfo=REPORT_TZ)
    due_utc = due_local.astimezone(timezone.utc).replace(tzinfo=None)
    if not (due_utc <= now_utc < due_utc + timedelta(hours=CATCH_UP_HOURS)):
        return None
    iso = monday.isocalendar()
    return f"weekly_stats:{iso[0]}-W{iso[1]:02d}", due_utc


async def claim_weekly_report(db: AsyncSession, key: str) -> bool:
    """Atomically claim the period (INSERT on PK, or retry a 'failed' row). Commits."""
    db.add(ScheduledReportRun(report_key=key, status="sending", attempts=1))
    try:
        await db.commit()
        return True
    except IntegrityError:
        await db.rollback()
    res = await db.execute(
        update(ScheduledReportRun)
        .where(ScheduledReportRun.report_key == key,
               ScheduledReportRun.status == "failed",
               ScheduledReportRun.attempts < MAX_ATTEMPTS)
        .values(status="sending", attempts=ScheduledReportRun.attempts + 1)
    )
    await db.commit()
    return res.rowcount == 1


async def finish_weekly_report(db: AsyncSession, key: str, ok: bool) -> None:
    await db.execute(
        update(ScheduledReportRun).where(ScheduledReportRun.report_key == key)
        .values(status="sent" if ok else "failed", sent_at=utcnow_naive() if ok else None)
    )
    await db.commit()
