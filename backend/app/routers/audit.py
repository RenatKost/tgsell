"""Read-only audit summary for the daily audit routine (x-audit-key).

Returns ids, statuses, counts, ages and amount aggregates only: no usernames, names,
contacts, wallet addresses, keys, tx hashes, channel titles or links.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
from app.models.channel import Channel, ChannelClarification, ChannelStatus, MODERATION_STATUSES
from app.models.deal import ACTIVE_DEAL_STATUSES, Deal, DealMessage, DealStatus, Transaction
from app.models.paid_service import PaidServiceOrder
from app.models.price_offer import PriceOffer, PriceOfferStatus
from app.models.seller_notification import SellerNotification
from app.utils.error_buffer import PROCESS_STARTED_AT, get_error_buffer, redact_sample
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])

RATE_LIMIT = 30
RATE_WINDOW_SEC = 60.0
MODERATION_ITEMS_LIMIT = 20
ACTIVE_DEALS_LIMIT = 50
STUCK_HOURS = 24

ESCROW_STATUSES = (
    DealStatus.paid,
    DealStatus.channel_transferring,
    DealStatus.awaiting_payout,
    DealStatus.payout_in_progress,
)


class SlidingWindowLimiter:
    """Global in-process sliding window (every request counts, authorized or not)."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            while self._hits and now - self._hits[0] >= self.window:
                self._hits.popleft()
            if len(self._hits) >= self.limit:
                return False
            self._hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter(RATE_LIMIT, RATE_WINDOW_SEC)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else "?"


def key_matches(provided: str | None) -> bool:
    expected = (settings.audit_key_sha256 or "").strip().lower()
    if not provided or not expected:
        return False
    digest = hashlib.sha256(provided.strip().encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, expected)


def require_audit_key(
    request: Request,
    x_audit_key: str | None = Header(default=None, alias="x-audit-key"),
) -> None:
    ip = _client_ip(request)
    if not limiter.allow():
        logger.warning("[AUDIT] summary rate-limited ip=%s", ip)
        raise HTTPException(status_code=429, detail="Too many requests")
    if not key_matches(x_audit_key):
        logger.warning("[AUDIT] summary denied ip=%s key_present=%s", ip, bool(x_audit_key))
        raise HTTPException(status_code=403, detail="Forbidden")
    logger.info("[AUDIT] summary ok ip=%s", ip)


def _hours(now: datetime, since: datetime | None) -> float | None:
    if since is None:
        return None
    return round(max((now - since).total_seconds(), 0) / 3600, 1)


def _utc_iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def _status_value(s) -> str:
    return s.value if hasattr(s, "value") else str(s)


async def _moderation(db: AsyncSession, now: datetime) -> dict:
    bundle_member = select(BundleChannel.id).where(BundleChannel.channel_id == Channel.id).exists()
    rows = (await db.execute(
        select(Channel.id, Channel.status, Channel.created_at)
        .where(Channel.status.in_(MODERATION_STATUSES), ~bundle_member)
    )).all()
    ids = [r.id for r in rows]
    asked: dict[int, datetime] = {}
    answered: dict[int, datetime] = {}
    if ids:
        for cid, last_asked, last_answered in (await db.execute(
            select(ChannelClarification.channel_id,
                   func.max(ChannelClarification.asked_at),
                   func.max(ChannelClarification.answered_at))
            .where(ChannelClarification.channel_id.in_(ids))
            .group_by(ChannelClarification.channel_id)
        )).all():
            if last_asked:
                asked[cid] = last_asked
            if last_answered:
                answered[cid] = last_answered

    items = []
    counts = {s.value: 0 for s in MODERATION_STATUSES}
    for r in rows:
        status = _status_value(r.status)
        counts[status] = counts.get(status, 0) + 1
        if r.status == ChannelStatus.needs_clarification:
            since = asked.get(r.id) or r.created_at
        else:
            # back in the queue after the seller answered → count from the latest answer
            since = max((d for d in (r.created_at, answered.get(r.id)) if d is not None), default=None)
        items.append({"kind": "channel", "id": r.id, "status": status, "waiting_hours": _hours(now, since)})

    bundles = (await db.execute(
        select(ChannelBundle.id, ChannelBundle.created_at).where(ChannelBundle.status == BundleStatus.pending)
    )).all()
    for b in bundles:
        items.append({"kind": "bundle", "id": b.id, "status": "pending", "waiting_hours": _hours(now, b.created_at)})

    items.sort(key=lambda it: it["waiting_hours"] or 0, reverse=True)
    return {
        "channels": counts,
        "bundles_pending": len(bundles),
        "total": len(items),
        "oldest_waiting_hours": items[0]["waiting_hours"] if items else None,
        "oldest": items[:MODERATION_ITEMS_LIMIT],
    }


async def _deals_and_escrow(db: AsyncSession, now: datetime) -> tuple[dict, dict]:
    by_status = {s.value: 0 for s in DealStatus}
    for status, cnt in (await db.execute(select(Deal.status, func.count(Deal.id)).group_by(Deal.status))).all():
        by_status[_status_value(status)] = cnt

    rows = (await db.execute(
        select(Deal.id, Deal.status, Deal.amount_usdt, Deal.created_at, Deal.paid_at,
               Deal.payment_deadline_at, Deal.checklist_started_at, Deal.last_checklist_activity_at)
        .where(Deal.status.in_(ACTIVE_DEAL_STATUSES))
    )).all()
    ids = [r.id for r in rows]
    last_tx: dict[int, datetime] = {}
    dispute_opened: dict[int, datetime] = {}
    if ids:
        for did, ts in (await db.execute(
            select(Transaction.deal_id, func.max(Transaction.created_at))
            .where(Transaction.deal_id.in_(ids)).group_by(Transaction.deal_id)
        )).all():
            if ts:
                last_tx[did] = ts
        disputed_ids = [r.id for r in rows if r.status == DealStatus.disputed]
        if disputed_ids:
            for did, ts in (await db.execute(
                select(DealMessage.deal_id, func.max(DealMessage.created_at))
                .where(DealMessage.deal_id.in_(disputed_ids), DealMessage.event == "dispute_opened")
                .group_by(DealMessage.deal_id)
            )).all():
                if ts:
                    dispute_opened[did] = ts

    active, disputes = [], []
    escrow_count, escrow_amount, escrow_stuck = 0, 0.0, 0
    escrow_by_status = {s.value: {"count": 0, "amount_usdt": 0.0} for s in ESCROW_STATUSES}
    disputed_amount = 0.0
    for r in rows:
        stamps = [r.created_at, r.paid_at, r.checklist_started_at, r.last_checklist_activity_at,
                  last_tx.get(r.id), dispute_opened.get(r.id)]
        since = max((d for d in stamps if d is not None), default=None)
        hours = _hours(now, since)
        overdue = bool(
            r.status in (DealStatus.created, DealStatus.payment_pending)
            and r.payment_deadline_at is not None and r.payment_deadline_at < now
        )
        status = _status_value(r.status)
        active.append({
            "id": r.id, "status": status, "hours_since_last_change": hours,
            "payment_deadline_overdue": overdue,
        })
        if r.status in ESCROW_STATUSES:
            amount = float(r.amount_usdt or 0)
            escrow_count += 1
            escrow_amount += amount
            escrow_by_status[status]["count"] += 1
            escrow_by_status[status]["amount_usdt"] += amount
            if hours is not None and hours > STUCK_HOURS:
                escrow_stuck += 1
        if r.status == DealStatus.disputed:
            disputed_amount += float(r.amount_usdt or 0)
            opened = dispute_opened.get(r.id)
            disputes.append({
                "deal_id": r.id,
                "age_hours": _hours(now, opened or r.paid_at or r.created_at),
                "age_source": "dispute_opened" if opened else ("paid_at" if r.paid_at else "created_at"),
            })

    active.sort(key=lambda d: d["hours_since_last_change"] or 0, reverse=True)
    disputes.sort(key=lambda d: d["age_hours"] or 0, reverse=True)
    for v in escrow_by_status.values():
        v["amount_usdt"] = round(v["amount_usdt"], 2)
    deals = {
        "by_status": by_status,
        "active_total": len(active),
        "payment_deadline_overdue": sum(1 for d in active if d["payment_deadline_overdue"]),
        "active": active[:ACTIVE_DEALS_LIMIT],
        "open_disputes": disputes,
    }
    escrow = {
        "statuses": [s.value for s in ESCROW_STATUSES],
        "deals": escrow_count,
        "amount_usdt": round(escrow_amount, 2),
        "by_status": escrow_by_status,
        "stuck_over_24h": escrow_stuck,
        "disputed_deals": len(disputes),
        "disputed_amount_usdt": round(disputed_amount, 2),
    }
    return deals, escrow


async def _offers_and_services(db: AsyncSession, now: datetime) -> tuple[dict, dict]:
    offers = {PriceOfferStatus.pending: 0, PriceOfferStatus.accepted: 0}
    for status, cnt in (await db.execute(
        select(PriceOffer.status, func.count(PriceOffer.id))
        .where(PriceOffer.status.in_(tuple(offers))).group_by(PriceOffer.status)
    )).all():
        offers[status] = cnt
    offers["pending_past_expiry"] = (await db.execute(
        select(func.count(PriceOffer.id))
        .where(PriceOffer.status == PriceOfferStatus.pending, PriceOffer.expires_at < now)
    )).scalar_one()

    unpaid_by_kind: dict[str, int] = {}
    for kind, cnt in (await db.execute(
        select(PaidServiceOrder.kind, func.count(PaidServiceOrder.id))
        .where(PaidServiceOrder.status == "awaiting_payment").group_by(PaidServiceOrder.kind)
    )).all():
        unpaid_by_kind[kind] = cnt
    overdue_top = (await db.execute(
        select(func.count(PaidServiceOrder.id)).where(
            PaidServiceOrder.kind == "top", PaidServiceOrder.status == "awaiting_payment",
            PaidServiceOrder.payment_deadline_at.is_not(None), PaidServiceOrder.payment_deadline_at < now,
        )
    )).scalar_one()
    services = {
        "unpaid_top_invoices": unpaid_by_kind.get("top", 0),
        "unpaid_top_past_deadline": overdue_top,
        "unpaid_by_kind": unpaid_by_kind,
    }
    return offers, services


async def _seller_notifications(db: AsyncSession, now: datetime) -> dict:
    """Outbox of seller alerts (0067): queue depth and last-24h outcomes (counts only)."""
    since = now - timedelta(hours=24)
    pending = (await db.execute(select(func.count(SellerNotification.id)).where(
        SellerNotification.sent_at.is_(None), SellerNotification.failed_at.is_(None)))).scalar_one()
    sent = (await db.execute(select(func.count(SellerNotification.id)).where(
        SellerNotification.sent_at >= since))).scalar_one()
    failed = (await db.execute(select(func.count(SellerNotification.id)).where(
        SellerNotification.failed_at >= since))).scalar_one()
    oldest = (await db.execute(select(func.min(SellerNotification.created_at)).where(
        SellerNotification.sent_at.is_(None), SellerNotification.failed_at.is_(None)))).scalar_one()
    return {"pending": pending, "sent_24h": sent, "failed_24h": failed,
            "oldest_pending_hours": _hours(now, oldest)}


def _runtime() -> dict:
    try:
        from app.services.channel_stats import get_telethon_health
        tele = dict(get_telethon_health())
        if tele.get("detail"):
            tele["detail"] = redact_sample(tele["detail"])
    except Exception as e:  # never fail the summary on a diagnostics import
        tele = {"status": "unknown", "error": type(e).__name__}
    try:
        from app.tasks.loop_watchdog import loop_lag_snapshot
        loop = loop_lag_snapshot()
    except Exception:
        loop = None
    started = PROCESS_STARTED_AT
    return {
        "telethon": tele,
        "loop": loop,
        "process_started_at": started.isoformat(),
        "uptime_hours": round((datetime.now(timezone.utc) - started).total_seconds() / 3600, 2),
    }


def _errors() -> dict:
    buf = get_error_buffer()
    if buf is None:
        return {"buffer_size": 0, "buffered": 0, "by_level": {}, "groups": [], "installed": False}
    return {**buf.summary(), "installed": True}


@router.get("/summary")
async def audit_summary(
    _: None = Depends(require_audit_key),
    db: AsyncSession = Depends(get_db),
):
    now = utcnow_naive()
    try:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            await db.execute(text("SET TRANSACTION READ ONLY"))
        moderation = await _moderation(db, now)
        deals, escrow = await _deals_and_escrow(db, now)
        offers, services = await _offers_and_services(db, now)
        notices = await _seller_notifications(db, now)
    finally:
        await db.rollback()
    return {
        "generated_at": _utc_iso(now),
        "moderation": moderation,
        "deals": deals,
        "escrow": escrow,
        "price_offers": offers,
        "paid_services": services,
        "seller_notifications": notices,
        "errors": _errors(),
        "runtime": _runtime(),
    }
