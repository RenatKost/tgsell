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
    queued = [r for r in results if r["result"] == "queued"]
    return {
        "ok": True, "treasury": settings.treasury_address, "queued": len(queued),
        "amount_usdt": round(sum(r.get("amount_usdt") or 0 for r in queued), 6), "results": results,
    }
