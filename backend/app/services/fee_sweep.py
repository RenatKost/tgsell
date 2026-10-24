"""Task 19: automatic fee sweep — whole remaining escrow USDT → TREASURY_ADDRESS.

* Destination is ALWAYS settings.treasury_address (validated base58check); no address is
  ever taken from UI/API. The worker additionally refuses any fee_sweep job whose
  to_address differs from the treasury.
* Executed as a normal queued job (TransactionType.fee_sweep) by the single payout worker
  via payouts.process_queued → CatFee energy (Task 18) with the 17A TRX-burn fallback.
* Eligible deals only: completed with a confirmed SUCCESS release == payout_tx_hash, or
  cancelled with a confirmed SUCCESS refund == payout_tx_hash; overpay closed (NULL/done);
  no open outgoing tx; never the legacy deals #3/#29 (рішення за Ренатом) nor #6.
* State (deals.sweep_status): due → queued → done/failed; due → pending_sweep (< min) /
  empty (0). pending_sweep is collected only by the superadmin "Зібрати все" button.
* Idempotent: every transition happens under the deal row lock; a deal with an open
  outgoing tx or a non-matching state is skipped.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.models.deal import Deal, DealStatus, Transaction, TransactionStatus, TransactionType

logger = logging.getLogger(__name__)

# Legacy deals: excluded from ALL automation and from the button; shown in the list only.
RENAT_DECISION_DEAL_IDS = frozenset({29, 3})
# Plus #6 — not touched at all.
EXCLUDED_DEAL_IDS = RENAT_DECISION_DEAL_IDS | {6}
RENAT_DECISION_NOTE = {29: "2.30 USDT, з них 2.00 переплата", 3: "4.00 USDT"}


class FeeSweepError(Exception):
    def __init__(self, message: str, http_status: int = 400):
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def treasury_address() -> str:
    """The only sweep destination; raises FeeSweepError if it is not a valid TRON address."""
    from app.services.payouts import is_tron_address

    addr = (settings.treasury_address or "").strip()
    if not is_tron_address(addr):
        raise FeeSweepError("TREASURY_ADDRESS не є валідною TRON base58-адресою — sweep заборонено", 500)
    master = (settings.tron_master_wallet_address or "").strip()
    if master and addr == master:
        raise FeeSweepError("TREASURY_ADDRESS збігається з master-гаманцем — sweep заборонено", 500)
    return addr


def min_units() -> int:
    from app.services.payouts import to_units

    return to_units(settings.fee_sweep_min_usdt)


def quick_eligible(deal: Deal) -> bool:
    """Sync pre-check used inside finalize (full check happens in :func:`check_eligible`)."""
    return bool(
        deal.id not in EXCLUDED_DEAL_IDS
        and deal.status in (DealStatus.completed, DealStatus.cancelled)
        and deal.payout_tx_hash
        and deal.overpay_status in (None, "done")
    )


def mark_due(deal: Deal) -> bool:
    """Called from payouts._finalize_success (deal row locked). Never overrides a state."""
    if not settings.fee_sweep_enabled or deal.sweep_status is not None or not quick_eligible(deal):
        return False
    deal.sweep_status = "due"
    return True


async def check_eligible(db, deal: Deal) -> str | None:
    """None if the deal may be swept, else the refusal reason (Ukrainian)."""
    from app.services.payouts import open_outgoing_tx

    if deal.id in EXCLUDED_DEAL_IDS:
        return f"Угода #{deal.id} виключена з автоматики (рішення за Ренатом)"
    if deal.status == DealStatus.completed:
        need_type = TransactionType.release
    elif deal.status == DealStatus.cancelled:
        need_type = TransactionType.refund
    else:
        return "Sweep лише з completed/cancelled-угоди"
    if not deal.payout_tx_hash:
        return "Немає підтвердженого payout_tx_hash"
    ok = (await db.execute(
        select(Transaction.id).where(
            Transaction.deal_id == deal.id, Transaction.type == need_type,
            Transaction.tx_hash == deal.payout_tx_hash,
            Transaction.status == TransactionStatus.confirmed, Transaction.receipt_status == "SUCCESS",
        ).limit(1)
    )).scalar_one_or_none()
    if ok is None:
        return "Виплата/повернення не має квитанції SUCCESS — sweep заборонено"
    if deal.overpay_status not in (None, "done"):
        return "Є відкрите повернення переплати — sweep заборонено"
    if await open_outgoing_tx(db, deal.id) is not None:
        return "Є непідтверджена вихідна транзакція по угоді"
    return None


def _ledger(db, actor, deal: Deal, action: str, **details) -> None:
    from app.services.moderation import audit

    audit(db, actor, action, "deal", deal.id, **details)


async def _sweep_trx(deal: Deal) -> None:
    payouts = __import__("importlib").import_module("app.services.payouts")

    await payouts._sweep_trx(deal)


async def sweep_deal(db, deal_id: int, *, force: bool, actor=None, allowed_states=("due",)) -> dict:
    """Decide + enqueue the fee sweep of one deal; commits. Returns {deal_id, result, ...}.

    force=False (worker): balance < FEE_SWEEP_MIN_USDT → pending_sweep (funds stay).
    force=True (button / collect-fee): any positive balance is swept.
    """
    import importlib

    escrow_svc = importlib.import_module("app.services.escrow")
    payouts = importlib.import_module("app.services.payouts")

    treasury = treasury_address()
    deal = await payouts._lock_deal(db, deal_id)
    if deal.sweep_status not in allowed_states:
        await db.commit()
        return {"deal_id": deal_id, "result": "skipped", "reason": f"sweep_status={deal.sweep_status}"}
    reason = await check_eligible(db, deal)
    if reason is not None:
        await db.commit()
        return {"deal_id": deal_id, "result": "ineligible", "reason": reason}
    escrow_addr = deal.escrow_wallet_address
    await db.commit()  # no row lock during the network read

    try:
        balance = await asyncio.to_thread(escrow_svc.fetch_usdt_balance_units, escrow_addr)
    except escrow_svc.BalanceUnavailable as e:
        return {"deal_id": deal_id, "result": "balance_unknown", "reason": str(e)}

    deal = await payouts._lock_deal(db, deal_id)
    if deal.sweep_status not in allowed_states or await check_eligible(db, deal) is not None:
        await db.commit()
        return {"deal_id": deal_id, "result": "skipped", "reason": "state changed"}
    units = int(balance)
    if units <= 0:
        deal.sweep_status = "empty"
        _ledger(db, actor, deal, "fee_sweep.empty", escrow=escrow_addr)
        await db.commit()
        await _sweep_trx(deal)
        return {"deal_id": deal_id, "result": "empty"}
    if not force and units < min_units():
        deal.sweep_status = "pending_sweep"
        _ledger(db, actor, deal, "fee_sweep.pending", escrow=escrow_addr, amount_units=units,
                min_usdt=settings.fee_sweep_min_usdt)
        await db.commit()
        await _sweep_trx(deal)
        logger.info(f"[FEE-SWEEP] deal #{deal_id}: {payouts.units_to_usdt(units)} USDT < min → pending_sweep")
        return {"deal_id": deal_id, "result": "pending_sweep", "amount_usdt": payouts.units_to_usdt(units)}
    job = payouts.enqueue_transfer(
        db, deal, tx_type=TransactionType.fee_sweep, to_address=treasury,
        amount_units=units, restore_status=None,
    )
    deal.sweep_status = "queued"
    _ledger(db, actor, deal, "fee_sweep.queued", escrow=escrow_addr, to_address=treasury, amount_units=units)
    await db.commit()
    logger.info(f"[FEE-SWEEP] deal #{deal_id}: {payouts.units_to_usdt(units)} USDT → treasury queued (tx #{job.id})")
    return {"deal_id": deal_id, "result": "queued", "amount_usdt": payouts.units_to_usdt(units),
            "transaction_id": job.id}


async def schedule_due(session_factory) -> int:
    """Worker step: decide every 'due' deal. Returns jobs queued."""
    if not settings.fee_sweep_enabled:
        return 0
    async with session_factory() as db:
        ids = (await db.execute(
            select(Deal.id).where(Deal.sweep_status == "due").order_by(Deal.id)
        )).scalars().all()
        await db.commit()
    queued = 0
    for deal_id in ids:
        if deal_id in EXCLUDED_DEAL_IDS:
            continue
        async with session_factory() as db:
            try:
                r = await sweep_deal(db, deal_id, force=False)
                queued += r["result"] == "queued"
            except Exception as e:
                logger.error(f"[FEE-SWEEP] deal #{deal_id}: {e}", exc_info=True)
                await db.rollback()
    return queued


async def collect_all(db, actor) -> dict:
    """Superadmin "Зібрати все": enqueue sweeps for every pending_sweep deal (not excluded)."""
    treasury_address()
    ids = (await db.execute(
        select(Deal.id).where(Deal.sweep_status == "pending_sweep", Deal.id.notin_(EXCLUDED_DEAL_IDS))
        .order_by(Deal.id)
    )).scalars().all()
    await db.commit()
    results = []
    for deal_id in ids:
        results.append(await sweep_deal(db, deal_id, force=True, actor=actor, allowed_states=("pending_sweep",)))
    svc_results = await collect_all_services(db, actor)
    queued = [r for r in results + svc_results if r["result"] == "queued"]
    return {
        "ok": True, "treasury": settings.treasury_address, "queued": len(queued),
        "amount_usdt": round(sum(r.get("amount_usdt") or 0 for r in queued), 6), "results": results,
        "service_results": svc_results,
    }


# ═══════════════════════════════════════════════════════════════════════
#   Paid services (paid_service_orders) → the same TREASURY_ADDRESS
# ═══════════════════════════════════════════════════════════════════════
#
# Same destination (treasury_address()), same min (FEE_SWEEP_MIN_USDT), same gas/energy path
# (payouts.prepare_service_sweep: CatFee energy when enabled, TRX top-up / burn fallback,
# persisted gas tx / energy order reused on retry), same single leader (payout worker).
# Orders are not deals, so the job state lives on the order row itself:
#   NULL → queued → processing → broadcast → done | failed;  NULL → pending_sweep (< min) | empty (0)
# Idempotency: every transition happens under the order row lock; txid is persisted BEFORE
# broadcast and a row that has a sweep_tx_hash is never prepared/broadcast again; done/failed
# rows are never re-queued automatically.

SERVICE_PENDING_STALE_AFTER_SEC = 600  # TRON tx expires 60 s after build


def _svc_models():
    from app.models.paid_service import PaidServiceOrder
    from app.services import paid_services as ps

    return PaidServiceOrder, ps


def service_fully_paid(order) -> bool:
    _, ps = _svc_models()
    return bool(
        order.status in ps.PAID_STATUSES
        and order.received_usdt is not None
        and float(order.received_usdt) + 1e-6 >= float(order.price_usdt)
    )


async def _lock_order(db, order_id: int):
    PaidServiceOrder, _ = _svc_models()
    return (await db.execute(
        select(PaidServiceOrder).where(PaidServiceOrder.id == order_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one()


def _svc_ledger(db, actor, order, action: str, **details) -> None:
    from app.services.moderation import audit

    audit(db, actor, action, "paid_service_order", order.id, **details)


async def _svc_alert(text: str, key: str) -> None:
    payouts = __import__("importlib").import_module("app.services.payouts")
    await payouts._alert(text, key)


async def _svc_sweep_trx(order) -> None:
    import importlib

    escrow_svc = importlib.import_module("app.services.escrow")
    try:
        await asyncio.to_thread(escrow_svc.sweep_trx_to_master, order.escrow_private_key_encrypted)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[FEE-SWEEP] service order #{order.id}: TRX sweep-back failed: {e}")


async def decide_service_sweep(db, order_id: int, *, force: bool, actor=None, allowed_states=(None,)) -> dict:
    """Decide one order: queued / pending_sweep / empty. Commits. Never sends anything."""
    import importlib

    escrow_svc = importlib.import_module("app.services.escrow")
    payouts = importlib.import_module("app.services.payouts")
    treasury = treasury_address()
    o = await _lock_order(db, order_id)
    if o.sweep_status not in allowed_states or not service_fully_paid(o) or o.sweep_tx_hash:
        await db.commit()
        return {"order_id": order_id, "result": "skipped"}
    addr = o.escrow_wallet_address
    await db.commit()  # no row lock during the network read
    try:
        units = int(await asyncio.to_thread(escrow_svc.fetch_usdt_balance_units, addr))
    except escrow_svc.BalanceUnavailable as e:
        return {"order_id": order_id, "result": "balance_unknown", "reason": str(e)}
    o = await _lock_order(db, order_id)
    if o.sweep_status not in allowed_states or not service_fully_paid(o) or o.sweep_tx_hash:
        await db.commit()
        return {"order_id": order_id, "result": "skipped", "reason": "state changed"}
    now = __import__("app.utils.timeutil", fromlist=["utcnow_naive"]).utcnow_naive()
    if units <= 0:
        o.sweep_status, o.sweep_finalized_at = "empty", now
        _svc_ledger(db, actor, o, "fee_sweep.service.empty", escrow=addr)
        await db.commit()
        return {"order_id": order_id, "result": "empty"}
    if not force and units < min_units():
        o.sweep_status = "pending_sweep"
        _svc_ledger(db, actor, o, "fee_sweep.service.pending", escrow=addr, amount_units=units)
        await db.commit()
        return {"order_id": order_id, "result": "pending_sweep", "amount_usdt": payouts.units_to_usdt(units)}
    o.sweep_status, o.sweep_amount_units, o.sweep_reason = "queued", units, None
    _svc_ledger(db, actor, o, "fee_sweep.service.queued", escrow=addr, to_address=treasury, amount_units=units)
    await db.commit()
    logger.info(f"[FEE-SWEEP] service order #{order_id}: {payouts.units_to_usdt(units)} USDT → treasury queued")
    return {"order_id": order_id, "result": "queued", "amount_usdt": payouts.units_to_usdt(units)}


async def _svc_fail(db, order_id: int, code: str, msg: str, *, sweep_trx: bool) -> dict:
    from app.utils.timeutil import utcnow_naive

    o = await _lock_order(db, order_id)
    o.sweep_status, o.sweep_reason, o.sweep_finalized_at = "failed", f"{code}: {msg}"[:1000], utcnow_naive()
    _svc_ledger(db, None, o, "fee_sweep.service.failed", reason=code, tx_hash=o.sweep_tx_hash)
    await db.commit()
    await _svc_alert(f"🔴 <b>Service fee sweep FAILED</b> — заявка #{order_id}\n{code}: {msg}",
                     f"svc_sweep_failed_{order_id}")
    if sweep_trx:
        await _svc_sweep_trx(o)
    return {"order_id": order_id, "result": "failed", "reason": code}


async def _svc_finalize_receipt(db, order_id: int, receipt: dict) -> dict:
    from app.utils.timeutil import utcnow_naive

    o = await _lock_order(db, order_id)
    if o.sweep_status != "broadcast":
        await db.commit()
        return {"order_id": order_id, "result": o.sweep_status}
    if receipt.get("status") == "SUCCESS":
        o.sweep_status, o.sweep_finalized_at = "done", utcnow_naive()
        _svc_ledger(db, None, o, "fee_sweep.service.done", tx_hash=o.sweep_tx_hash,
                    to_address=settings.treasury_address, amount_units=o.sweep_amount_units)
        await db.commit()
        await _svc_sweep_trx(o)
        logger.info(f"[FEE-SWEEP] service order #{order_id}: SUCCESS tx={o.sweep_tx_hash}")
        return {"order_id": order_id, "result": "done"}
    if receipt.get("status") == "FAILED":
        await db.commit()
        return await _svc_fail(db, order_id, receipt.get("reason") or "FAILED", f"TX {o.sweep_tx_hash}", sweep_trx=True)
    await db.commit()
    return {"order_id": order_id, "result": "pending"}


async def process_service_sweep(db, order_id: int, *, receipt_timeout: float | None = None) -> dict:
    """Execute one queued order sweep. Never resends (txid persisted before broadcast)."""
    import importlib

    from app.utils.timeutil import utcnow_naive

    escrow_svc = importlib.import_module("app.services.escrow")
    payouts = importlib.import_module("app.services.payouts")

    o = await _lock_order(db, order_id)
    if o.sweep_status != "queued" or o.sweep_tx_hash:
        await db.commit()
        return {"order_id": order_id, "result": "skipped"}
    try:
        treasury = treasury_address()
    except FeeSweepError as e:
        await db.commit()
        return await _svc_fail(db, order_id, "BAD_TREASURY", e.message, sweep_trx=False)
    units = int(o.sweep_amount_units or 0)
    enc, addr = o.escrow_private_key_encrypted, o.escrow_wallet_address
    prior_gas, prior_energy = o.sweep_gas_tx_hash, o.sweep_energy_order_id
    o.sweep_status = "processing"
    await db.commit()  # release the row lock during network calls

    if units <= 0:
        return await _svc_fail(db, order_id, "BAD_AMOUNT", "Некоректна сума", sweep_trx=False)
    try:
        balance = await asyncio.to_thread(escrow_svc.fetch_usdt_balance_units, addr)
    except escrow_svc.BalanceUnavailable as e:
        o = await _lock_order(db, order_id)
        o.sweep_status, o.sweep_reason = "queued", f"BALANCE_UNKNOWN: {e}"[:1000]
        await db.commit()
        return {"order_id": order_id, "result": "deferred", "reason": "BALANCE_UNKNOWN"}
    if balance < units:
        return await _svc_fail(db, order_id, "INSUFFICIENT_ESCROW",
                               f"{payouts.units_to_usdt(balance)} < {payouts.units_to_usdt(units)} USDT", sweep_trx=False)

    try:
        prepared = await asyncio.to_thread(
            payouts.prepare_service_sweep, enc, treasury, units, order_id=order_id,
            prior_gas_tx=prior_gas, prior_energy_order=prior_energy,
        )
    except Exception as e:
        o = await _lock_order(db, order_id)
        order_id_energy = getattr(e, "energy_order_id", None)
        if order_id_energy:
            o.sweep_energy_order_id = order_id_energy  # never ordered twice
        if getattr(e, "gas_tx", None):
            o.sweep_gas_tx_hash = e.gas_tx
        if getattr(e, "retryable", False):
            o.sweep_attempts = int(o.sweep_attempts or 0) + 1
            if o.sweep_attempts < payouts.MAX_GAS_ATTEMPTS:
                o.sweep_status = "queued"
                o.sweep_reason = (getattr(e, "message", None) or str(e))[:1000]
                await db.commit()
                return {"order_id": order_id, "result": "deferred", "reason": getattr(e, "reason", "GAS_RETRY")}
            await db.commit()
            return await _svc_fail(db, order_id, getattr(e, "reason", "GAS_RETRY"),
                                   "газ не підтвердився після всіх спроб", sweep_trx=False)
        await db.commit()
        return await _svc_fail(db, order_id, getattr(e, "reason", "PREPARE_ERROR"),
                               getattr(e, "message", None) or str(e), sweep_trx=True)

    o = await _lock_order(db, order_id)
    o.sweep_tx_hash = prepared["txid"]
    if prepared.get("gas_tx"):
        o.sweep_gas_tx_hash = prepared["gas_tx"]
    en = prepared.get("energy") or {}
    if en.get("order_id"):
        o.sweep_energy_order_id = en["order_id"]
    o.sweep_status, o.sweep_broadcast_at = "broadcast", utcnow_naive()
    await db.commit()  # txid persisted BEFORE broadcast
    try:
        await asyncio.to_thread(payouts.broadcast_service_sweep, prepared)
    except Exception as e:
        logger.error(f"[FEE-SWEEP] service order #{order_id}: broadcast raised: {e} — checking receipt")
    timeout = escrow_svc.RECEIPT_TIMEOUT_SEC if receipt_timeout is None else receipt_timeout
    receipt = await asyncio.to_thread(escrow_svc.get_receipt, prepared["txid"], timeout)
    return await _svc_finalize_receipt(db, order_id, receipt)


async def reconcile_service_sweeps(db, now=None) -> int:
    """Finalize broadcast service sweeps by receipt; fail crashed 'processing' rows. Never resends."""
    import importlib

    from app.utils.timeutil import utcnow_naive

    escrow_svc = importlib.import_module("app.services.escrow")
    PaidServiceOrder, _ = _svc_models()
    now = now or utcnow_naive()
    rows = (await db.execute(select(PaidServiceOrder.id, PaidServiceOrder.sweep_status).where(
        PaidServiceOrder.sweep_status.in_(("broadcast", "processing"))).order_by(PaidServiceOrder.id))).all()
    await db.commit()
    done = 0
    for oid, st in rows:
        try:
            o = await _lock_order(db, oid)
            ref = o.sweep_broadcast_at or o.updated_at or now
            stale = (now - ref).total_seconds() >= SERVICE_PENDING_STALE_AFTER_SEC
            if o.sweep_status == "processing":
                await db.commit()
                if o.sweep_tx_hash is None and stale:
                    # txid is persisted before broadcast → nothing was sent; admin decides on retry.
                    await _svc_fail(db, oid, "NEVER_BROADCAST", "обробку перервано до відправлення", sweep_trx=False)
                    done += 1
                continue
            txh = o.sweep_tx_hash
            await db.commit()
            receipt = await asyncio.to_thread(escrow_svc.get_receipt, txh, 0)
            if receipt.get("status") in ("SUCCESS", "FAILED"):
                await _svc_finalize_receipt(db, oid, receipt)
                done += 1
            elif stale:
                await _svc_alert(f"🟠 <b>Service fee sweep unresolved</b> — заявка #{oid}\nTX: <code>{txh}</code>\n"
                                 f"Немає квитанції понад 10 хв. Повтор НЕ виконується — перевірте вручну.",
                                 f"svc_sweep_unresolved_{oid}")
        except Exception as e:
            logger.error(f"[FEE-SWEEP] reconcile service order #{oid}: {e}", exc_info=True)
            await db.rollback()
    return done


async def service_sweep_cycle(session_factory, *, receipt_timeout: float | None = None) -> dict:
    """Worker step (payout-worker leader only): decide new, run queued, reconcile broadcast."""
    if not settings.fee_sweep_enabled:
        return {"enabled": False}
    PaidServiceOrder, ps = _svc_models()
    out = {"decided": 0, "processed": 0, "reconciled": 0}
    async with session_factory() as db:
        new_ids = (await db.execute(select(PaidServiceOrder.id).where(
            PaidServiceOrder.sweep_status.is_(None), PaidServiceOrder.status.in_(ps.PAID_STATUSES),
            PaidServiceOrder.received_usdt.isnot(None),
        ).order_by(PaidServiceOrder.id))).scalars().all()
        await db.commit()
    for oid in new_ids:
        async with session_factory() as db:
            try:
                r = await decide_service_sweep(db, oid, force=False)
                out["decided"] += r["result"] in ("queued", "pending_sweep", "empty")
            except Exception as e:
                logger.error(f"[FEE-SWEEP] decide service order #{oid}: {e}", exc_info=True)
                await db.rollback()
    async with session_factory() as db:
        queued = (await db.execute(select(PaidServiceOrder.id).where(
            PaidServiceOrder.sweep_status == "queued").order_by(PaidServiceOrder.id))).scalars().all()
        await db.commit()
    for oid in queued:
        async with session_factory() as db:
            try:
                await process_service_sweep(db, oid, receipt_timeout=receipt_timeout)
                out["processed"] += 1
            except Exception as e:
                logger.error(f"[FEE-SWEEP] process service order #{oid}: {e}", exc_info=True)
                await db.rollback()
    async with session_factory() as db:
        out["reconciled"] = await reconcile_service_sweeps(db)
    return out


async def collect_all_services(db, actor) -> list[dict]:
    """"Зібрати все" for services: queue every pending_sweep order (force, any positive balance)."""
    PaidServiceOrder, _ = _svc_models()
    ids = (await db.execute(select(PaidServiceOrder.id).where(
        PaidServiceOrder.sweep_status == "pending_sweep").order_by(PaidServiceOrder.id))).scalars().all()
    await db.commit()
    return [await decide_service_sweep(db, oid, force=True, actor=actor, allowed_states=("pending_sweep",))
            for oid in ids]
