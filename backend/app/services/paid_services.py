"""Paid seller services: «Топ каталогу», «Пост у каналі», «Перевірено TgSell».

Prices/limits live in ``app_settings`` (admin-editable, no deploy); defaults below.
Payment detection is READ-ONLY (``escrow.fetch_usdt_balance``); nothing here sends
transactions or touches payouts / TRON_MASTER_WALLET.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.models.channel import Channel
from app.models.paid_service import AppSetting, PaidServiceOrder
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

KIND_TOP, KIND_POST, KIND_VERIFIED = "top", "post", "verified"
KINDS = (KIND_TOP, KIND_POST, KIND_VERIFIED)
KIND_LABELS = {
    KIND_TOP: "Топ каталогу",
    KIND_POST: "Пост у каналі t.me/tgsell_exchange",
    KIND_VERIFIED: "Перевірено TgSell",
}
KIND_TERMS = {
    KIND_TOP: "Лот показується вгорі каталогу з позначкою «Топ» протягом {top_days} днів з моменту оплати. Одночасно в Топі — не більше {top_max_slots} лотів.",
    KIND_POST: "Після оплати заявка потрапляє до маркетолога TgSell, який публікує пост про ваш лот у каналі t.me/tgsell_exchange.",
    KIND_VERIFIED: ("Після оплати адміністратор вручну перевіряє канал. Якщо перевірку пройдено — на лот ставиться значок «Перевірено TgSell». "
                    "Увага: у разі відмови кошти не повертаються, бо це оплата аудиту, а не значка."),
}

DEFAULTS: dict[str, float] = {
    "service_price_top": 10.0,
    "service_price_post": 15.0,
    "service_price_verified": 20.0,
    "service_top_days": 7,
    "service_top_max_slots": 3,
    "service_payment_hours": 24,
}
PRICE_KEY = {KIND_TOP: "service_price_top", KIND_POST: "service_price_post", KIND_VERIFIED: "service_price_verified"}

ST_AWAITING = "awaiting_payment"
ST_ACTIVE, ST_EXPIRED = "active", "expired"  # top
ST_PAID, ST_IN_REVIEW = "paid", "in_review"  # post / verified queue
ST_PUBLISHED, ST_VERIFIED, ST_REJECTED = "published", "verified", "rejected"
ST_CANCELLED = "cancelled"  # unpaid, deadline passed with zero balance

# Admin-driven transitions (payment-driven ones are done by the checker).
ADMIN_TRANSITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    KIND_POST: {ST_PAID: (ST_IN_REVIEW, ST_PUBLISHED, ST_REJECTED), ST_IN_REVIEW: (ST_PUBLISHED, ST_REJECTED)},
    KIND_VERIFIED: {ST_PAID: (ST_IN_REVIEW, ST_VERIFIED, ST_REJECTED), ST_IN_REVIEW: (ST_VERIFIED, ST_REJECTED)},
    KIND_TOP: {},
}
# Statuses that mean "money received" → counted as revenue (rejected verified = audit paid, no refund).
PAID_STATUSES = (ST_ACTIVE, ST_EXPIRED, ST_PAID, ST_IN_REVIEW, ST_PUBLISHED, ST_VERIFIED, ST_REJECTED)


class ServiceError(Exception):
    pass


async def get_settings(db) -> dict[str, float]:
    out = dict(DEFAULTS)
    for row in (await db.execute(select(AppSetting).where(AppSetting.key.in_(list(DEFAULTS))))).scalars():
        try:
            out[row.key] = float(row.value)
        except (TypeError, ValueError):
            logger.warning(f"[SERVICES] bad setting {row.key}={row.value!r}, using default")
    return out


async def update_settings(db, updates: dict) -> dict[str, float]:
    for k, v in updates.items():
        if k not in DEFAULTS or v is None:
            continue
        v = float(v)
        if v <= 0 or v > 100000:
            raise ServiceError(f"Некоректне значення для {k}")
        row = await db.get(AppSetting, k)
        if row is None:
            db.add(AppSetting(key=k, value=str(v), updated_at=utcnow_naive()))
        else:
            row.value, row.updated_at = str(v), utcnow_naive()
    await db.flush()
    return await get_settings(db)


def public_catalog(cfg: dict) -> list[dict]:
    fmt = {"top_days": int(cfg["service_top_days"]), "top_max_slots": int(cfg["service_top_max_slots"])}
    return [{"kind": k, "title": KIND_LABELS[k], "price_usdt": cfg[PRICE_KEY[k]], "terms": KIND_TERMS[k].format(**fmt),
             "refundable": k != KIND_VERIFIED} for k in KINDS]


async def top_slots_taken(db, now: datetime) -> int:
    """Active Top lots + unexpired awaiting-payment Top orders (slot is reserved at order time)."""
    active = (await db.execute(select(func.count(Channel.id)).where(Channel.top_until > now))).scalar() or 0
    pending = (await db.execute(select(func.count(PaidServiceOrder.id)).where(
        PaidServiceOrder.kind == KIND_TOP, PaidServiceOrder.status == ST_AWAITING,
        (PaidServiceOrder.payment_deadline_at.is_(None)) | (PaidServiceOrder.payment_deadline_at > now),
    ))).scalar() or 0
    return int(active) + int(pending)


async def create_order(db, *, seller_id: int, channel: Channel, kind: str, now: datetime | None = None,
                       wallet_factory=None) -> PaidServiceOrder:
    from app.models.channel import ChannelStatus
    now = now or utcnow_naive()
    if kind not in KINDS:
        raise ServiceError("Невідома послуга")
    if channel.seller_id != seller_id:
        raise ServiceError("Це не ваш лот")
    if channel.status != ChannelStatus.approved:
        raise ServiceError("Послуги доступні лише для опублікованих лотів")
    cfg = await get_settings(db)
    open_same = (await db.execute(select(PaidServiceOrder.id).where(
        PaidServiceOrder.channel_id == channel.id, PaidServiceOrder.kind == kind,
        PaidServiceOrder.status.in_((ST_AWAITING, ST_PAID, ST_IN_REVIEW, ST_ACTIVE)),
    ).limit(1))).scalar_one_or_none()
    if open_same:
        raise ServiceError("Для цього лота вже є активна заявка на цю послугу")
    if kind == KIND_VERIFIED and channel.tgsell_verified:
        raise ServiceError("Лот уже має значок «Перевірено TgSell»")
    if kind == KIND_TOP:
        if channel.is_top:
            raise ServiceError("Лот уже в Топі")
        if await top_slots_taken(db, now) >= int(cfg["service_top_max_slots"]):
            raise ServiceError("Усі місця в Топі зайняті. Спробуйте пізніше")
    if wallet_factory is None:
        from app.services.escrow import generate_escrow_wallet as wallet_factory
    addr, enc = wallet_factory()
    order = PaidServiceOrder(
        kind=kind, channel_id=channel.id, seller_id=seller_id, price_usdt=float(cfg[PRICE_KEY[kind]]),
        status=ST_AWAITING, escrow_wallet_address=addr, escrow_private_key_encrypted=enc,
        payment_deadline_at=now + timedelta(hours=float(cfg["service_payment_hours"])),
        created_at=now, updated_at=now,
    )
    db.add(order)
    await db.flush()
    return order


async def mark_paid(db, order: PaidServiceOrder, received: float, now: datetime) -> None:
    order.received_usdt, order.paid_at, order.updated_at = received, now, now
    if order.kind == KIND_TOP:
        cfg = await get_settings(db)
        ch = await db.get(Channel, order.channel_id)
        start = max(now, ch.top_until) if ch and ch.top_until else now
        order.active_until = start + timedelta(days=float(cfg["service_top_days"]))
        order.status = ST_ACTIVE
        if ch is not None:
            ch.top_until = order.active_until
    else:
        order.status = ST_PAID


async def admin_transition(db, order: PaidServiceOrder, new_status: str, admin_id: int, note: str | None = None) -> None:
    allowed = ADMIN_TRANSITIONS.get(order.kind, {}).get(order.status, ())
    if new_status not in allowed:
        raise ServiceError(f"Перехід {order.status} → {new_status} недоступний")
    order.status, order.handled_by_id, order.updated_at = new_status, admin_id, utcnow_naive()
    if note:
        order.admin_note = note[:1000]
    if order.kind == KIND_VERIFIED and new_status == ST_VERIFIED:
        ch = await db.get(Channel, order.channel_id)
        if ch is not None:
            ch.tgsell_verified = True


async def expire_tops(db, now: datetime) -> int:
    rows = (await db.execute(select(PaidServiceOrder).where(
        PaidServiceOrder.kind == KIND_TOP, PaidServiceOrder.status == ST_ACTIVE,
        PaidServiceOrder.active_until <= now))).scalars().all()
    for o in rows:
        o.status, o.updated_at = ST_EXPIRED, now
    return len(rows)


async def check_orders_once(session_factory, now: datetime | None = None, fetch_balance=None) -> dict:
    """Read-only balance polling for awaiting orders + Top expiry. Returns counters."""
    from app.services import escrow as escrow_svc
    now = now or utcnow_naive()
    if fetch_balance is None:
        async def fetch_balance(addr):
            try:
                return await asyncio.to_thread(escrow_svc.fetch_usdt_balance, addr)
            except escrow_svc.BalanceUnavailable:
                return None
    stats = {"paid": 0, "cancelled": 0, "expired": 0, "partial_alerts": 0}
    partial_alerts: list[tuple[int, str]] = []
    async with session_factory() as db:
        orders = (await db.execute(select(PaidServiceOrder).where(PaidServiceOrder.status == ST_AWAITING))).scalars().all()
        for o in orders:
            bal = await fetch_balance(o.escrow_wallet_address)
            if bal is None:
                continue  # unknown balance → never cancel
            if bal + 1e-6 >= o.price_usdt:
                await mark_paid(db, o, float(bal), now)
                stats["paid"] += 1
            elif o.payment_deadline_at and o.payment_deadline_at <= now:
                if bal <= 0:
                    o.status, o.updated_at = ST_CANCELLED, now
                    stats["cancelled"] += 1
                else:
                    if o.received_usdt != bal:
                        o.received_usdt = float(bal)  # partial payment: stays for admin review, never auto-cancelled
                    if o.partial_alerted_at is None:
                        o.partial_alerted_at = now  # one-shot: marked in the same commit, sent after it
                        partial_alerts.append((o.id, (
                            f"🟡 <b>Часткова оплата послуги</b> — заявка #{o.id} ({KIND_LABELS.get(o.kind, o.kind)})\n"
                            f"Отримано {float(bal):g} з {o.price_usdt:g} USDT, строк оплати минув.\n"
                            f"Адреса: <code>{o.escrow_wallet_address}</code>\nРішення — за адміністратором.")))
        stats["expired"] = await expire_tops(db, now)
        await db.commit()
    if partial_alerts:
        from app.services.alerts import send_admin_alert
        for oid, text in partial_alerts:
            try:
                await send_admin_alert(text, alert_key=f"svc_partial_{oid}")
                stats["partial_alerts"] += 1
            except Exception as e:  # never re-sent: the order is already marked
                logger.error(f"[SERVICES] partial alert #{oid} failed: {e}")
    return stats


async def services_revenue(db) -> float:
    total = (await db.execute(select(func.sum(PaidServiceOrder.price_usdt)).where(
        PaidServiceOrder.status.in_(PAID_STATUSES)))).scalar() or 0
    return round(float(total), 2)


async def run_service_payment_checker(interval_seconds: int = 60):
    from app.database import async_session
    logger.info(f"Paid services checker started (interval: {interval_seconds}s)")
    while True:
        try:
            await check_orders_once(async_session)
        except Exception as e:
            logger.error(f"Paid services checker error: {e}")
        await asyncio.sleep(interval_seconds)
