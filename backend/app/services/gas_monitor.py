"""Master wallet gas monitoring, snapshots and the daily admin summary.

Gas (TRX) for every escrow payout is topped up from the master wallet; the platform only
earns USDT, so TRX cannot be replenished automatically (that would need a DEX swap signed
with the master key). The flow is: alert → address + QR + suggested amount → manual top-up.

Coverage = (TRX − reserve) / per-payout cost, using the live energy price:
  new receiver  ≈ (135k energy × fee + 1 TRX bandwidth) × 1.2  (≈17.4 TRX at 100 sun)
  existing      ≈ ( 70k energy × fee + 1 TRX) × 1.2            (≈9.6 TRX)
Master energy/bandwidth is shown for information: the escrow wallet pays the transfer.

Periodic checks, snapshots and the daily summary run inside the payout worker, i.e.
under its PostgreSQL advisory lock (exactly one instance).
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.config import settings
from app.services import escrow as escrow_svc
from app.services.alerts import telegram_html_safe as _h
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

RESERVE_TRX = escrow_svc.MASTER_TRANSFER_RESERVE_SUN / escrow_svc.SUN_PER_TRX  # 1.5
WARNING_PAYOUTS = 3
CRITICAL_PAYOUTS = 1
TARGET_PAYOUTS = 10
WARNING_THROTTLE_MIN = 360
CRITICAL_THROTTLE_MIN = 60
UNKNOWN_THROTTLE_MIN = 60
CACHE_TTL_SEC = 60
SNAPSHOT_EVERY = timedelta(minutes=15)
SNAPSHOT_KEEP = timedelta(days=90)
SUMMARY_HOUR_LOCAL = 9
SUMMARY_ACTION = "summary.daily"

_cache: dict = {"at": 0.0, "payload": None}
_cache_lock = asyncio.Lock()
_alert_state: dict = {"level": None}


# ── time zone (Europe/Chisinau) ─────────────────────────────────────────

def _eu_dst_bounds_utc(year: int) -> tuple[datetime, datetime]:
    def last_sunday(month: int) -> date:
        d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    # Moldova: 03:00 local (01:00 UTC) last Sun of March → 04:00 local (01:00 UTC) last Sun of Oct
    start = datetime.combine(last_sunday(3), datetime.min.time()) + timedelta(hours=1)
    end = datetime.combine(last_sunday(10), datetime.min.time()) + timedelta(hours=1)
    return start, end


def to_local(utc_naive: datetime) -> datetime:
    """UTC naive → Europe/Chisinau naive (zoneinfo, with an EET/EEST fallback)."""
    try:
        from zoneinfo import ZoneInfo

        return utc_naive.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/Chisinau")).replace(tzinfo=None)
    except Exception:
        start, end = _eu_dst_bounds_utc(utc_naive.year)
        return utc_naive + timedelta(hours=3 if start <= utc_naive < end else 2)


def local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """UTC naive [start, end) of a Europe/Chisinau calendar day."""
    def to_utc(local: datetime) -> datetime:
        guess = local - timedelta(hours=2)
        for off in (2, 3):
            cand = local - timedelta(hours=off)
            if to_local(cand) == local:
                guess = cand
        return guess
    start_local = datetime.combine(day, datetime.min.time())
    return to_utc(start_local), to_utc(start_local + timedelta(days=1))


# ── gas status ──────────────────────────────────────────────────────────

def payout_costs_trx(energy_fee_sun: int) -> dict:
    def cost(energy: int) -> float:
        sun = (energy * energy_fee_sun + escrow_svc.BANDWIDTH_RESERVE_SUN) * escrow_svc.GAS_MARGIN
        return round(sun / escrow_svc.SUN_PER_TRX, 3)
    return {"new_receiver": cost(escrow_svc.ENERGY_FALLBACK_NEW_HOLDER),
            "existing_holder": cost(escrow_svc.ENERGY_FALLBACK_EXISTING_HOLDER)}


def warning_threshold_trx(energy_fee_sun: int | None = None) -> float:
    """Single source of the «Мало газу» threshold (admin panel, alerts, admin API)."""
    fee = energy_fee_sun or escrow_svc.ENERGY_FEE_FALLBACK_SUN
    return round(RESERVE_TRX + WARNING_PAYOUTS * payout_costs_trx(fee)["new_receiver"], 2)


def cached_energy_fee_sun() -> int | None:
    payload = _cache.get("payload") or {}
    return payload.get("energy_fee_sun")


def evaluate(resources: dict | None, *, address: str, refused_24h: int = 0, now=None) -> dict:
    """Pure: resources (escrow.get_account_resources) → status dict."""
    now = now or utcnow_naive()
    fee = (resources or {}).get("energy_fee_sun") or escrow_svc.ENERGY_FEE_FALLBACK_SUN
    costs = payout_costs_trx(fee)
    base = {
        "address": address, "energy_fee_sun": fee, "cost_trx": costs, "reserve_trx": RESERVE_TRX,
        "warning_below_payouts": WARNING_PAYOUTS, "critical_below_payouts": CRITICAL_PAYOUTS,
        "warning_threshold_trx": warning_threshold_trx(fee),
        "critical_threshold_trx": round(RESERVE_TRX + CRITICAL_PAYOUTS * costs["new_receiver"], 2),
        "target_trx": round(RESERVE_TRX + TARGET_PAYOUTS * costs["new_receiver"], 2),
        "refused_prechecks_24h": refused_24h, "checked_at": now.isoformat() + "Z",
    }
    if resources is None or resources.get("trx_sun") is None:
        return {**base, "trx": None, "energy_available": None, "bandwidth_available": None,
                "payouts_covered_new": None, "payouts_covered_existing": None,
                "level": "unknown", "suggested_topup_trx": None}
    trx = resources["trx_sun"] / escrow_svc.SUN_PER_TRX
    usable = max(0.0, trx - RESERVE_TRX)
    cov_new = math.floor(usable / costs["new_receiver"] + 1e-9)
    cov_old = math.floor(usable / costs["existing_holder"] + 1e-9)
    level = "critical" if cov_new < CRITICAL_PAYOUTS else "warning" if cov_new < WARNING_PAYOUTS else "ok"
    return {
        **base, "trx": round(trx, 6),
        "energy_available": resources.get("energy_available"),
        "bandwidth_available": resources.get("bandwidth_available"),
        "payouts_covered_new": cov_new, "payouts_covered_existing": cov_old, "level": level,
        "suggested_topup_trx": max(0.0, math.ceil(base["target_trx"] - trx)),
    }


async def fetch_status(*, force: bool = False) -> dict:
    """Master gas status, cached for ~60s."""
    from app.services import payouts

    async with _cache_lock:
        age = time.monotonic() - _cache["at"]
        if not force and _cache["payload"] is not None and age < CACHE_TTL_SEC:
            return {**_cache["payload"], "cached": True, "cache_age_sec": round(age, 1)}
        address = settings.tron_master_wallet_address
        res = await asyncio.to_thread(escrow_svc.get_account_resources, address)
        st = evaluate(res, address=address, refused_24h=payouts.refused_prechecks_24h())
        _cache.update(at=time.monotonic(), payload=st)
        return {**st, "cached": False, "cache_age_sec": 0.0}


def _alert_text(st: dict, title: str) -> str:
    lines = [f"⛽ <b>{_h(title)}</b>", f"Адреса: <code>{_h(st['address'])}</code>"]
    if st["trx"] is not None:
        lines.append(f"Баланс: {st['trx']:.2f} TRX — вистачить на ~{st['payouts_covered_new']} виплат "
                     f"новому отримувачу (~{st['payouts_covered_existing']} існуючому)")
        if st["suggested_topup_trx"]:
            lines.append(f"Рекомендовано поповнити: ~{st['suggested_topup_trx']:.0f} TRX "
                         f"(до {st['target_trx']:.0f} TRX ≈ {TARGET_PAYOUTS} виплат)")
    else:
        lines.append("Баланс не вдалося отримати з TronGrid.")
    lines.append(f"Відмов виплат через газ за 24 год: {st['refused_prechecks_24h']}")
    return "\n".join(lines)


async def check_and_alert(*, send=None) -> dict:
    """Fresh check + level-based alerts (warning 6h, critical 1h, unknown 1h, recovered once)."""
    if send is None:
        from app.services.alerts import send_admin_alert as send
    st = await fetch_status(force=True)
    level, prev = st["level"], _alert_state["level"]
    try:
        if level == "critical":
            await send(_alert_text(st, "КРИТИЧНО: газу на master менше ніж на 1 виплату"),
                       alert_key="gas_critical", throttle_minutes=CRITICAL_THROTTLE_MIN)
        elif level == "warning":
            await send(_alert_text(st, f"Мало газу на master (< {WARNING_PAYOUTS} виплат)"),
                       alert_key="gas_warning", throttle_minutes=WARNING_THROTTLE_MIN)
        elif level == "unknown":
            await send(_alert_text(st, "Баланс master TRX невідомий"),
                       alert_key="gas_unknown", throttle_minutes=UNKNOWN_THROTTLE_MIN)
        elif level == "ok" and prev in ("warning", "critical"):
            await send(_alert_text(st, "Газ на master відновлено"), alert_key="gas_recovered", throttle_minutes=1)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[GAS] alert failed: {e}")
    if level != "unknown":
        _alert_state["level"] = level
    return st


# ── CatFee balance (Task 18) ────────────────────────────────────────────

_catfee_cache: dict = {"at": 0.0, "payload": None}
_catfee_alert_state: dict = {"low": False}


async def avg_rent_trx(db) -> float:
    """Average CatFee rental cost of the last 20 payouts (fallback ~2.5 TRX)."""
    from app.models.deal import Transaction

    from app.services import catfee

    try:
        rows = (await db.execute(select(Transaction.energy_rent_sun).where(
            Transaction.energy_source == "catfee", Transaction.energy_rent_sun > 0,
        ).order_by(Transaction.id.desc()).limit(20))).scalars().all()
    except Exception as e:  # pragma: no cover
        logger.warning(f"[CATFEE] avg rent query failed: {e}")
        rows = []
    if not rows:
        return catfee.DEFAULT_RENT_TRX
    return max(0.1, sum(rows) / len(rows) / escrow_svc.SUN_PER_TRX)


def evaluate_catfee(balance_sun: int | None, per_payout_trx: float, *, enabled: bool, error: str | None = None) -> dict:
    from app.services import catfee

    base = {"enabled": enabled, "per_payout_trx": round(per_payout_trx, 3),
            "low_below_payouts": catfee.LOW_BALANCE_PAYOUTS, "base_url": catfee.base_url() if enabled else None,
            "error": error, "checked_at": utcnow_naive().isoformat() + "Z"}
    if not enabled:
        return {**base, "balance_trx": None, "payouts_covered": None, "level": "disabled"}
    if balance_sun is None:
        return {**base, "balance_trx": None, "payouts_covered": None, "level": "unknown"}
    trx = balance_sun / escrow_svc.SUN_PER_TRX
    cov = math.floor(trx / per_payout_trx + 1e-9) if per_payout_trx > 0 else None
    level = "low" if cov is not None and cov < catfee.LOW_BALANCE_PAYOUTS else "ok"
    return {**base, "balance_trx": round(trx, 6), "payouts_covered": cov, "level": level,
            "suggested_topup_trx": max(0, math.ceil(per_payout_trx * 20 - trx)) if level == "low" else 0}


async def fetch_catfee_status(db, *, force: bool = False) -> dict:
    from app.services import catfee

    age = time.monotonic() - _catfee_cache["at"]
    if not force and _catfee_cache["payload"] is not None and age < CACHE_TTL_SEC:
        return _catfee_cache["payload"]
    per = await avg_rent_trx(db)
    if not catfee.enabled():
        st = evaluate_catfee(None, per, enabled=False)
    else:
        try:
            bal = await asyncio.to_thread(catfee.get_balance_sun)
            st = evaluate_catfee(bal, per, enabled=True)
        except Exception as e:
            st = evaluate_catfee(None, per, enabled=True, error=str(e)[:200])
    _catfee_cache.update(at=time.monotonic(), payload=st)
    return st


async def catfee_check_and_alert(db, *, send=None) -> dict:
    """Admin alert when the CatFee balance covers < 5 payouts (6h throttle; recovery once)."""
    st = await fetch_catfee_status(db, force=True)
    if send is None:
        from app.services.alerts import send_admin_alert as send
    try:
        if st["level"] == "low":
            await send(
                f"🐱 <b>Мало коштів на CatFee</b>\nБаланс: {st['balance_trx']:.2f} TRX — вистачить на "
                f"~{st['payouts_covered']} виплат (≈{st['per_payout_trx']:.2f} TRX/виплата).\n"
                f"Рекомендовано поповнити ~{st.get('suggested_topup_trx', 0)} TRX на catfee.io. "
                f"Без балансу виплати спалюватимуть TRX з master (≈7–17 TRX/виплата).",
                alert_key="catfee_low", throttle_minutes=WARNING_THROTTLE_MIN)
            _catfee_alert_state["low"] = True
        elif st["level"] == "ok" and _catfee_alert_state["low"]:
            await send(f"🐱 Баланс CatFee відновлено: {st['balance_trx']:.2f} TRX", alert_key="catfee_ok",
                       throttle_minutes=1)
            _catfee_alert_state["low"] = False
    except Exception as e:  # pragma: no cover
        logger.warning(f"[CATFEE] alert failed: {e}")
    return st


# ── snapshots ───────────────────────────────────────────────────────────

async def maybe_snapshot(db, st: dict, now=None) -> bool:
    """Store one snapshot per 15 min (DB-checked, restart-safe) and prune > 90 days."""
    from app.models.monitoring import MasterWalletSnapshot as S

    now = now or utcnow_naive()
    last = (await db.execute(select(func.max(S.at)))).scalar()
    if last is not None and now - last < SNAPSHOT_EVERY:
        return False
    trx = st.get("trx")
    db.add(S(at=now, trx_sun=None if trx is None else int(round(trx * escrow_svc.SUN_PER_TRX)),
             energy_available=st.get("energy_available"), bandwidth_available=st.get("bandwidth_available")))
    await db.execute(delete(S).where(S.at < now - SNAPSHOT_KEEP))
    await db.commit()
    return True


async def snapshot_history(db, days: int) -> list[dict]:
    from app.models.monitoring import MasterWalletSnapshot as S

    since = utcnow_naive() - timedelta(days=days)
    rows = (await db.execute(select(S).where(S.at >= since).order_by(S.at))).scalars().all()
    return [{"at": r.at.isoformat() + "Z",
             "trx": None if r.trx_sun is None else r.trx_sun / escrow_svc.SUN_PER_TRX,
             "energy_available": r.energy_available, "bandwidth_available": r.bandwidth_available}
            for r in rows]


# ── daily summary ───────────────────────────────────────────────────────

async def build_summary(db, day: date, gas: dict | None = None) -> dict:
    from app.models.deal import Deal, DealStatus, Transaction, TransactionStatus, TransactionType
    from app.models.user import User
    from app.services import payouts

    start, end = local_day_bounds_utc(day)

    async def scalar(q):
        return (await db.execute(q)).scalar() or 0

    created = await scalar(select(func.count(Deal.id)).where(Deal.created_at >= start, Deal.created_at < end))
    paid = await scalar(select(func.count(Deal.id)).where(Deal.paid_at >= start, Deal.paid_at < end))
    completed = await scalar(select(func.count(Deal.id)).where(Deal.completed_at >= start, Deal.completed_at < end))
    cancelled = await scalar(select(func.count(Deal.id)).where(Deal.cancelled_at >= start, Deal.cancelled_at < end))
    fee_accrued = await scalar(select(func.coalesce(func.sum(Deal.service_fee), 0)).where(
        Deal.status == DealStatus.completed, Deal.completed_at >= start, Deal.completed_at < end))
    out = {}
    for t in payouts.OUTGOING_TYPES:
        ok = (await db.execute(select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.type == t, Transaction.status == TransactionStatus.confirmed,
            Transaction.finalized_at >= start, Transaction.finalized_at < end))).one()
        failed = await scalar(select(func.count(Transaction.id)).where(
            Transaction.type == t, Transaction.status == TransactionStatus.failed,
            Transaction.finalized_at >= start, Transaction.finalized_at < end))
        out[t.value] = {"confirmed": int(ok[0]), "amount_usdt": round(float(ok[1]), 6), "failed": int(failed)}
    pending_now = await scalar(select(func.count(Transaction.id)).where(
        Transaction.type.in_(payouts.OUTGOING_TYPES), Transaction.status == TransactionStatus.pending))
    disputes_open = await scalar(select(func.count(Deal.id)).where(Deal.status == DealStatus.disputed))
    in_progress = await scalar(select(func.count(Deal.id)).where(Deal.status == DealStatus.payout_in_progress))
    blocked = await scalar(select(func.count(User.id)).where(User.is_blocked.is_(True)))
    return {
        "date": day.isoformat(), "tz": "Europe/Chisinau",
        "deals": {"created": int(created), "paid": int(paid), "completed": int(completed), "cancelled": int(cancelled)},
        "fee_accrued_usdt": round(float(fee_accrued), 6),
        "fee_collected_usdt": out.get(TransactionType.fee_collection.value, {}).get("amount_usdt", 0.0),
        "outgoing": out, "pending_outgoing_now": int(pending_now),
        "disputes_open_now": int(disputes_open), "payout_in_progress_now": int(in_progress),
        "blocked_users_now": int(blocked), "gas": gas,
    }


def summary_text(s: dict) -> str:
    o = s["outgoing"]
    g = s.get("gas") or {}

    def line(k, label):
        x = o.get(k, {"confirmed": 0, "amount_usdt": 0, "failed": 0})
        return f"{label}: {x['confirmed']} ({x['amount_usdt']:.2f} USDT), невдалих {x['failed']}"
    gas = (f"{g['trx']:.2f} TRX ≈ {g['payouts_covered_new']} виплат ({g['level']})"
           if g.get("trx") is not None else "невідомо")
    return "\n".join([
        f"📊 <b>Звіт за {_h(s['date'])}</b>",
        f"Угоди: створено {s['deals']['created']}, оплачено {s['deals']['paid']}, "
        f"завершено {s['deals']['completed']}, скасовано {s['deals']['cancelled']}",
        f"Комісія нарахована: {s['fee_accrued_usdt']:.2f} USDT, зібрана: {s['fee_collected_usdt']:.2f} USDT",
        line("release", "Виплати продавцям"), line("refund", "Повернення"),
        line("fee_collection", "Збір комісії"), line("sweep", "Sweep"),
        f"Зараз: pending tx {s['pending_outgoing_now']}, payout_in_progress {s['payout_in_progress_now']}, "
        f"спорів {s['disputes_open_now']}, заблокованих {s['blocked_users_now']}",
        f"Газ master: {_h(gas)}; відмов через газ за 24 год: {g.get('refused_prechecks_24h', 0)}",
    ])


async def maybe_send_daily_summary(session_factory, now=None, *, send=None) -> bool:
    """At/after 09:00 Chisinau, once per day (recorded in admin_audit_log BEFORE sending)."""
    from app.models.user import AdminAuditLog

    now = now or utcnow_naive()
    local = to_local(now)
    if local.hour < SUMMARY_HOUR_LOCAL:
        return False
    today_key = int(local.strftime("%Y%m%d"))
    async with session_factory() as db:
        done = (await db.execute(select(AdminAuditLog.id).where(
            AdminAuditLog.action == SUMMARY_ACTION, AdminAuditLog.target_id == today_key).limit(1))).scalar()
        if done is not None:
            return False
        gas = _cache["payload"]
        summary = await build_summary(db, local.date() - timedelta(days=1), gas)
        db.add(AdminAuditLog(actor_id=None, action=SUMMARY_ACTION, target_type="summary",
                             target_id=today_key, details={"date": summary["date"]}))
        await db.commit()
    if send is None:
        from app.services.alerts import send_admin_alert as send
    try:
        await send(summary_text(summary), alert_key=f"daily_summary_{today_key}", throttle_minutes=1)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[SUMMARY] send failed: {e}")
    return True
