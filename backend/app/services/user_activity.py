"""Task 23: first-party activity tracking + admin aggregates.

Privacy: no IP, user agent, search text or usernames are stored or logged.
Anonymous visitors are identified only by sha256(random client id)[:32].
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import UserEvent, UserSession
from app.models.channel import Channel
from app.models.deal import Deal
from app.models.user import User
from app.utils.timeutil import utcnow_naive
from app.utils.activity_ids import _RateLimiter, hash_id, limiter  # noqa: F401

logger = logging.getLogger(__name__)

CLIENT_EVENTS = {"visit", "channel_view", "search", "saved_search_click"}
SERVER_EVENTS = {"login", "favorite_add", "deal_start", "payment", "saved_search_create"}
PAGES = {"home", "catalog", "channel", "auction", "cabinet", "sell", "deal", "bundle", "faq", "other"}

CHANNEL_VIEW_DEDUPE = timedelta(minutes=10)
SEARCH_DEDUPE = timedelta(seconds=60)
VISIT_DEDUPE = timedelta(minutes=30)

HEARTBEAT_MIN_INTERVAL = 20  # seconds; frontend sends every 45 s and never more often than every 30 s
HEARTBEAT_MAX_PER_MINUTE = 12  # hard flood cap per session (normal: ~1.3/min, even with 4 tabs on one sid ~5/min)
HEARTBEAT_MAX_CREDIT = 60  # seconds credited per heartbeat
HEARTBEAT_MAX_GAP = 120  # longer gap = tab hidden / idle, credit nothing
EVENTS_PER_MINUTE = 30


async def record_event(
    db: AsyncSession,
    event_type: str,
    *,
    user_id: int | None = None,
    anon_id: str | None = None,
    object_type: str | None = None,
    object_id: int | None = None,
    page: str | None = None,
    attribution: dict | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> bool:
    """Insert an event unless it's a near-duplicate. Never raises."""
    if user_id is None and anon_id is None:
        return False
    now = now or utcnow_naive()
    try:
        window = {"channel_view": CHANNEL_VIEW_DEDUPE, "search": SEARCH_DEDUPE, "visit": VISIT_DEDUPE}.get(event_type)
        if window is not None:
            actor = UserEvent.user_id == user_id if user_id is not None else UserEvent.anon_id == anon_id
            q = select(UserEvent.id).where(
                actor, UserEvent.event_type == event_type, UserEvent.created_at >= now - window
            )
            if event_type == "channel_view":
                q = q.where(UserEvent.object_id == object_id)
            if (await db.execute(q.limit(1))).first():
                return False
        db.add(UserEvent(user_id=user_id, anon_id=anon_id, event_type=event_type,
                         object_type=object_type, object_id=object_id, page=page, created_at=now,
                         **(attribution or {})))
        if commit:
            await db.commit()
        return True
    except Exception as e:  # tracking must never break the request
        logger.warning("activity event %s not recorded: %s", event_type, type(e).__name__)
        try:
            await db.rollback()
        except Exception:
            pass
        return False


async def record_event_detached(event_type: str, **kw) -> bool:
    """Server-side events in their own session so a failure can't touch the caller's."""
    try:
        from app.database import async_session
        async with async_session() as db:
            return await record_event(db, event_type, **kw)
    except Exception as e:
        logger.warning("activity event %s not recorded: %s", event_type, type(e).__name__)
        return False


async def heartbeat(
    db: AsyncSession, session_key: str, *, user_id: int | None, anon_id: str | None, now: datetime | None = None
) -> int:
    """Credit visible time to a session. Returns credited seconds."""
    now = now or utcnow_naive()
    s = (await db.execute(select(UserSession).where(UserSession.session_key == session_key))).scalar_one_or_none()
    credited = 0
    if s is None:
        s = UserSession(session_key=session_key, user_id=user_id, anon_id=anon_id, started_at=now,
                        last_seen_at=now, active_seconds=0, heartbeats=1)
        db.add(s)
    else:
        gap = (now - s.last_seen_at).total_seconds()
        if 0 < gap <= HEARTBEAT_MAX_GAP:
            credited = int(min(gap, HEARTBEAT_MAX_CREDIT))
        s.active_seconds = (s.active_seconds or 0) + credited
        s.heartbeats = (s.heartbeats or 0) + 1
        s.last_seen_at = now
        if user_id is not None and s.user_id is None:
            s.user_id = user_id
        if anon_id and not s.anon_id:
            s.anon_id = anon_id
    await db.commit()
    return credited


# ── Aggregates ─────────────────────────────────────────────────────────

async def _anon_to_user(db: AsyncSession) -> dict[str, int]:
    rows = await db.execute(
        select(UserEvent.anon_id, func.min(UserEvent.user_id))
        .where(UserEvent.anon_id.is_not(None), UserEvent.user_id.is_not(None))
        .group_by(UserEvent.anon_id)
    )
    m = {a: u for a, u in rows.all()}
    rows = await db.execute(
        select(UserSession.anon_id, func.min(UserSession.user_id))
        .where(UserSession.anon_id.is_not(None), UserSession.user_id.is_not(None))
        .group_by(UserSession.anon_id)
    )
    for a, u in rows.all():
        m.setdefault(a, u)
    return m


def _actor(user_id, anon_id, amap) -> str | None:
    if user_id is not None:
        return f"u{user_id}"
    if anon_id:
        u = amap.get(anon_id)
        return f"u{u}" if u is not None else f"a{anon_id}"
    return None


async def funnel(db: AsyncSession, days: int, now: datetime | None = None) -> dict:
    now = now or utcnow_naive()
    since = now - timedelta(days=days)
    amap = await _anon_to_user(db)
    visit: set[str] = set()
    view: set[str] = set()
    for uid, aid in (await db.execute(
        select(UserSession.user_id, UserSession.anon_id).where(UserSession.last_seen_at >= since)
    )).all():
        a = _actor(uid, aid, amap)
        if a:
            visit.add(a)
    for uid, aid, et in (await db.execute(
        select(UserEvent.user_id, UserEvent.anon_id, UserEvent.event_type).where(UserEvent.created_at >= since)
    )).all():
        a = _actor(uid, aid, amap)
        if not a:
            continue
        visit.add(a)
        if et == "channel_view":
            view.add(a)
    # Deal start / payment come from the deals table itself (source of truth, read-only).
    start = {f"u{b}" for (b,) in (await db.execute(select(Deal.buyer_id).where(Deal.created_at >= since))).all()}
    paid = {f"u{b}" for (b,) in (await db.execute(
        select(Deal.buyer_id).where(Deal.paid_at.is_not(None), Deal.paid_at >= since))).all()}
    steps = [
        ("visit", "Візит", visit),
        ("channel_view", "Перегляд каналу", view),
        ("deal_start", "Початок угоди", start),
        ("payment", "Оплата", paid),
    ]
    out, prev, top = [], None, len(visit) or 0
    for key, label, s in steps:
        n = len(s)
        out.append({
            "step": key,
            "label": label,
            "users": n,
            "from_prev_pct": round(n * 100 / prev, 1) if prev else None,
            "from_visit_pct": round(n * 100 / top, 1) if top else None,
        })
        prev = n
    return {"days": days, "steps": out}


async def users_activity(db: AsyncSession, now: datetime | None = None, limit: int = 200) -> list[dict]:
    now = now or utcnow_naive()
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    amap = await _anon_to_user(db)
    stats: dict[int, dict] = {}

    def row(uid: int) -> dict:
        return stats.setdefault(uid, {
            "user_id": uid, "last_seen_at": None,
            "sessions_7d": 0, "sessions_30d": 0, "seconds_7d": 0, "seconds_30d": 0,
            "views_30d": 0, "searches_30d": 0, "favorites_30d": 0, "logins_30d": 0,
            "viewed": [], "deals_total": 0, "deals_30d": 0, "paid_30d": 0,
        })

    def bump_last(r, t):
        if t and (r["last_seen_at"] is None or t > r["last_seen_at"]):
            r["last_seen_at"] = t

    for uid, aid, last, secs in (await db.execute(
        select(UserSession.user_id, UserSession.anon_id, UserSession.last_seen_at, UserSession.active_seconds)
        .where(UserSession.last_seen_at >= d30)
    )).all():
        uid = uid if uid is not None else amap.get(aid)
        if uid is None:
            continue
        r = row(uid)
        bump_last(r, last)
        r["sessions_30d"] += 1
        r["seconds_30d"] += secs or 0
        if last >= d7:
            r["sessions_7d"] += 1
            r["seconds_7d"] += secs or 0

    viewed: dict[int, list[tuple[datetime, int]]] = defaultdict(list)
    for uid, aid, et, oid, t in (await db.execute(
        select(UserEvent.user_id, UserEvent.anon_id, UserEvent.event_type, UserEvent.object_id, UserEvent.created_at)
        .where(UserEvent.created_at >= d30)
    )).all():
        uid = uid if uid is not None else amap.get(aid)
        if uid is None:
            continue
        r = row(uid)
        bump_last(r, t)
        if et == "channel_view":
            r["views_30d"] += 1
            if oid:
                viewed[uid].append((t, oid))
        elif et == "search":
            r["searches_30d"] += 1
        elif et == "favorite_add":
            r["favorites_30d"] += 1
        elif et == "login":
            r["logins_30d"] += 1

    for b, created, paid_at in (await db.execute(select(Deal.buyer_id, Deal.created_at, Deal.paid_at))).all():
        if b in stats or (created and created >= d30):
            r = row(b)
            r["deals_total"] += 1
            if created and created >= d30:
                r["deals_30d"] += 1
            if paid_at and paid_at >= d30:
                r["paid_30d"] += 1

    ch_ids = {oid for lst in viewed.values() for _, oid in lst}
    names = {}
    if ch_ids:
        names = dict((await db.execute(select(Channel.id, Channel.channel_name).where(Channel.id.in_(ch_ids)))).all())
    for uid, lst in viewed.items():
        seen, out = set(), []
        for _, oid in sorted(lst, reverse=True):
            if oid in seen:
                continue
            seen.add(oid)
            out.append({"channel_id": oid, "name": names.get(oid)})
            if len(out) >= 5:
                break
        stats[uid]["viewed"] = out

    if stats:
        for u in (await db.execute(
            select(User.id, User.username, User.first_name, User.role).where(User.id.in_(list(stats)))
        )).all():
            stats[u.id].update(username=u.username, first_name=u.first_name,
                               role=getattr(u.role, "value", u.role))
    rows = [r for r in stats.values() if "first_name" in r]
    for r in rows:
        r["activity_score"] = (r["seconds_30d"] // 60) + r["sessions_30d"] * 2 + r["views_30d"] \
            + r["searches_30d"] + r["favorites_30d"] * 2 + r["deals_30d"] * 5 + r["paid_30d"] * 10
    rows.sort(key=lambda r: (r["activity_score"], r["last_seen_at"] or datetime.min), reverse=True)
    return rows[:limit]


# ── Attribution (no PII) ───────────────────────────────────────────────
ATTR_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
_UTM_RE = re.compile(r"[^\w.\-+ ]", re.UNICODE)
_DOMAIN_RE = re.compile(r"^[a-z0-9.-]{1,64}$")


def clean_attribution(raw: dict) -> dict:
    """Keep only short sanitized utm_* values and a bare referer hostname."""
    out: dict = {}
    for f in ATTR_FIELDS:
        v = raw.get(f)
        if isinstance(v, str):
            v = _UTM_RE.sub("", v).strip()[:64]
            if v:
                out[f] = v
    ref = raw.get("ref_domain")
    if isinstance(ref, str):
        ref = ref.strip().lower()
        if "//" in ref:
            ref = ref.split("//", 1)[1]
        ref = ref.split("/", 1)[0].split("?", 1)[0].split("@")[-1].split(":", 1)[0]
        if ref.startswith("www."):
            ref = ref[4:]
        if ref and _DOMAIN_RE.match(ref):
            out["ref_domain"] = ref
    return out
