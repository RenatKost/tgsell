"""UTM campaign tracking: sanitising, UA classification, attribution and the admin «Кампанії» report.

No PII: visits store a hashed anonymous id, utm_* values, the path and a coarse UA class only.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, or_, select

logger = logging.getLogger("app.utm")
_SAFE = re.compile(r"[^0-9A-Za-z_\-.~+%]")
UTM_FIELDS = ("utm_source", "utm_campaign", "utm_content")


def clean(v: str | None, n: int = 64) -> str | None:
    v = _SAFE.sub("", (v or "").strip())[:n]
    return v.lower() or None


def clean_path(p: str | None) -> str | None:
    p = (p or "").split("?")[0].split("#")[0]
    p = re.sub(r"[^0-9A-Za-z_\-/.]", "", p)[:128]
    return p if p.startswith("/") else None


def ua_class(ua: str | None) -> str:
    u = (ua or "").lower()
    if any(k in u for k in ("bot", "crawler", "spider", "headless", "facebookexternalhit")):
        return "bot"
    if "instagram" in u:
        return "ig_inapp"
    if "fban" in u or "fbav" in u or "fb_iab" in u:
        return "fb_inapp"
    if "telegram" in u:
        return "tg_inapp"
    if any(k in u for k in ("iphone", "android", "mobile", "ipad")):
        return "mobile"
    return "desktop"


def fields(src) -> dict:
    """utm_* from a pydantic body / dict, sanitised; {} when no source and no campaign."""
    get = (lambda k: src.get(k)) if isinstance(src, dict) else (lambda k: getattr(src, k, None))
    d = {k: clean(get(k)) for k in UTM_FIELDS}
    return d if (d["utm_source"] or d["utm_campaign"]) else {}


def apply(obj, src) -> bool:
    """First-touch: set utm_* on a user/channel/bundle only when it has none yet."""
    d = fields(src)
    if not d or getattr(obj, "utm_source", None) or getattr(obj, "utm_campaign", None):
        return False
    for k, v in d.items():
        setattr(obj, k, v)
    return True


FUNNEL_EVENTS = ("login_click", "form_start", "form_submit_attempt", "bot_start", "login_success")
CLIENT_EVENTS = ("login_click", "form_start", "form_submit_attempt")


def log_event(event: str, d: dict) -> None:
    logger.info(f"[utm] funnel event={event} source={d.get('utm_source') or '-'} "
                f"campaign={d.get('utm_campaign') or '-'} content={d.get('utm_content') or '-'}")


async def record_event_detached(event: str, anon_hash: str | None, src) -> bool:
    """Server-side funnel step (bot_start / login_success) in its own session; never raises."""
    d = fields(src or {})
    if not d or event not in FUNNEL_EVENTS:
        return False
    try:
        from app.database import async_session
        from app.models.utm import UtmEvent
        from app.utils.timeutil import utcnow_naive
        log_event(event, d)
        async with async_session() as db:
            db.add(UtmEvent(anon_hash=anon_hash, event=event, created_at=utcnow_naive(), **d))
            await db.commit()
        return True
    except Exception as e:  # attribution must never block a login
        logger.warning("utm event %s not recorded: %s", event, type(e).__name__)
        return False


def log_visit(d: dict, path: str | None, ua: str) -> None:
    logger.info(f"[utm] visit source={d.get('utm_source') or '-'} campaign={d.get('utm_campaign') or '-'} "
                f"content={d.get('utm_content') or '-'} path={path or '-'} ua={ua}")


def _range(date_from: date | None, date_to: date | None):
    start = datetime.combine(date_from, datetime.min.time()) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time()) if date_to else None
    return start, end


def _win(col, start, end):
    conds = []
    if start is not None:
        conds.append(col >= start)
    if end is not None:
        conds.append(col < end)
    return and_(*conds) if conds else True


async def report(db, date_from: date | None = None, date_to: date | None = None) -> dict:
    """Per (source, campaign, content): visits, unique visitors, registrations, lots submitted/approved.
    Lots = single channels (not part of a bundle) + bundles; date filter applies to each row's created_at."""
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User
    from app.models.utm import UtmEvent, UtmVisit

    start, end = _range(date_from, date_to)
    rows: dict[tuple, dict] = {}

    def row(k):
        return rows.setdefault(tuple(x or "" for x in k), {
            "visits": 0, "visitors": 0, "registrations": 0, "lots_submitted": 0, "lots_approved": 0,
            **{e: 0 for e in FUNNEL_EVENTS}})

    def key(m):
        return (m.utm_source, m.utm_campaign, m.utm_content)

    q = (select(UtmVisit.utm_source, UtmVisit.utm_campaign, UtmVisit.utm_content,
                func.count(UtmVisit.id), func.count(func.distinct(UtmVisit.anon_hash)))
         .where(_win(UtmVisit.created_at, start, end))
         .where(or_(UtmVisit.ua_class.is_(None), UtmVisit.ua_class != "bot"))
         .group_by(UtmVisit.utm_source, UtmVisit.utm_campaign, UtmVisit.utm_content))
    for s, c, ct, n, u in (await db.execute(q)).all():
        r = row((s, c, ct)); r["visits"] += n; r["visitors"] += u

    # funnel steps: unique visitors per step (events without an anon id count individually)
    uniq = func.count(func.distinct(UtmEvent.anon_hash)) + func.count(UtmEvent.id).filter(UtmEvent.anon_hash.is_(None))
    q = (select(UtmEvent.utm_source, UtmEvent.utm_campaign, UtmEvent.utm_content, UtmEvent.event, uniq)
         .where(_win(UtmEvent.created_at, start, end), UtmEvent.event.in_(FUNNEL_EVENTS))
         .group_by(UtmEvent.utm_source, UtmEvent.utm_campaign, UtmEvent.utm_content, UtmEvent.event))
    for s, c, ct, ev, n in (await db.execute(q)).all():
        row((s, c, ct))[ev] += n

    has_utm = lambda m: or_(m.utm_source.isnot(None), m.utm_campaign.isnot(None))  # noqa: E731
    q = (select(User.utm_source, User.utm_campaign, User.utm_content, func.count(User.id))
         .where(has_utm(User), _win(User.created_at, start, end))
         .group_by(User.utm_source, User.utm_campaign, User.utm_content))
    for s, c, ct, n in (await db.execute(q)).all():
        row((s, c, ct))["registrations"] += n

    in_bundle = select(BundleChannel.channel_id)
    approved_ch = or_(Channel.first_approved_at.isnot(None),
                      Channel.status.in_([ChannelStatus.approved, ChannelStatus.sold]))
    q = (select(Channel.utm_source, Channel.utm_campaign, Channel.utm_content, func.count(Channel.id),
                func.count(Channel.id).filter(approved_ch))
         .where(has_utm(Channel), _win(Channel.created_at, start, end), Channel.id.notin_(in_bundle))
         .group_by(Channel.utm_source, Channel.utm_campaign, Channel.utm_content))
    for s, c, ct, n, a in (await db.execute(q)).all():
        r = row((s, c, ct)); r["lots_submitted"] += n; r["lots_approved"] += a

    q = (select(ChannelBundle.utm_source, ChannelBundle.utm_campaign, ChannelBundle.utm_content,
                func.count(ChannelBundle.id),
                func.count(ChannelBundle.id).filter(ChannelBundle.status.in_([BundleStatus.approved, BundleStatus.sold])))
         .where(has_utm(ChannelBundle), _win(ChannelBundle.created_at, start, end))
         .group_by(ChannelBundle.utm_source, ChannelBundle.utm_campaign, ChannelBundle.utm_content))
    for s, c, ct, n, a in (await db.execute(q)).all():
        r = row((s, c, ct)); r["lots_submitted"] += n; r["lots_approved"] += a

    items = [{"utm_source": k[0], "utm_campaign": k[1], "utm_content": k[2], **v} for k, v in rows.items()]
    items.sort(key=lambda x: (-x["visits"], -x["registrations"], x["utm_campaign"], x["utm_source"]))
    totals = {f: sum(i[f] for i in items) for f in ("visits", "visitors", "registrations", "lots_submitted", "lots_approved", *FUNNEL_EVENTS)}
    return {"items": items, "totals": totals, "funnel_events": list(FUNNEL_EVENTS),
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None}
