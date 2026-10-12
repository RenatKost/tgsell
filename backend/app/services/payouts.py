"""Unified outgoing escrow transfers (USDT TRC-20) — the ONLY way money leaves escrow.

Rules (audit task 12, PR A):
* Every outgoing transfer (seller release, buyer refund, admin cancel-refund, stray-funds
  sweep, manual fee collection) goes through :func:`execute_transfer`.
* Before sending: destination is a real TRON base58check address and is neither the
  master wallet (except fee collection) nor ANY escrow address; there is no unresolved
  outgoing transfer for the deal; the on-chain escrow USDT balance is known and covers
  the amount (otherwise refuse + admin alert, nothing sent).
* Amounts are Decimal, rounded DOWN to 6 decimals, passed to the contract as integers.
* A Transaction row is committed as ``pending`` BEFORE broadcast and its tx_hash (known
  from the signed tx) is committed BEFORE broadcast too, so a crash/timeout after
  broadcast never leads to a blind resend.
* Receipt SUCCESS → finalize (deal completed / cancelled-with-refund). FAILED → release the
  claim to the status stored on the row + admin alert. No receipt within the wait window
  → PENDING: claim kept, row stays pending, :func:`reconcile_pending_transfers`
  (payment_checker loop) finalizes later.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select

from app.config import settings
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealStatus, Transaction, TransactionStatus, TransactionType
from app.services import escrow as escrow_svc
from app.services.deal_lifecycle import (
    PayoutClaimError,
    claim_deal_for_transfer,
    mark_deal_completed,
    release_payout_claim,
)
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

OUTGOING_TYPES = (
    TransactionType.release,
    TransactionType.refund,
    TransactionType.fee_collection,
    TransactionType.sweep,
)
UNITS = Decimal("0.000001")
# TRON txs expire 60s after build; a tx not on chain after this is dead for good.
PENDING_STALE_AFTER = timedelta(minutes=10)

# Dedup for "stuck payout_in_progress without a tracked tx" alerts (per process).
_stuck_alerted: set[int] = set()


class PayoutError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass
class TransferOutcome:
    status: str  # "success" | "failed" | "pending" | "refused"
    tx_hash: str | None = None
    error: str | None = None
    reason: str | None = None
    transaction_id: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success"


# ── amounts / addresses ─────────────────────────────────────────────────

def to_units(amount) -> int:
    """USDT amount → integer contract units (6 decimals, rounded DOWN)."""
    d = Decimal(str(amount)).quantize(UNITS, rounding=ROUND_DOWN)
    return int(d * 1_000_000)


def release_units(deal: Deal) -> int:
    """Seller payout = amount − service fee (Decimal, round down)."""
    return to_units(Decimal(str(deal.amount_usdt)) - Decimal(str(deal.service_fee or 0)))


def refund_units(deal: Deal) -> int:
    return to_units(deal.amount_usdt)


def units_to_usdt(units: int) -> float:
    return float(Decimal(int(units)) / Decimal(1_000_000))


def is_tron_address(address: str) -> bool:
    from tronpy.keys import is_base58check_address

    try:
        return bool(address) and len(address) == 34 and is_base58check_address(address)
    except Exception:
        return False


async def validate_destination(db, address: str | None, *, allow_master: bool = False) -> str:
    """Real base58check TRON address, not master (unless allowed), not ANY escrow address."""
    addr = (address or "").strip()
    if not is_tron_address(addr):
        raise PayoutError("invalid_address", "Некоректна TRON-адреса (base58check, починається з T, 34 символи)")
    master = (settings.tron_master_wallet_address or "").strip()
    if master and addr == master and not allow_master:
        raise PayoutError("master_address", "Адреса = master-гаманець платформи — виплата туди заборонена")
    hit = (await db.execute(
        select(Deal.id).where(Deal.escrow_wallet_address == addr).limit(1)
    )).scalar_one_or_none()
    if hit is not None:
        raise PayoutError("escrow_address", f"Адреса є escrow-гаманцем угоди #{hit} — заборонено")
    return addr


async def open_outgoing_tx(db, deal_id: int) -> Transaction | None:
    return (await db.execute(
        select(Transaction)
        .where(
            Transaction.deal_id == deal_id,
            Transaction.status == TransactionStatus.pending,
            Transaction.type.in_(OUTGOING_TYPES),
        )
        .order_by(Transaction.id.desc())
        .limit(1)
    )).scalar_one_or_none()


async def claim_for_payout(db, deal: Deal, *, expected_status: DealStatus) -> None:
    """claim_deal_for_transfer + refuse when an unresolved outgoing tx exists (409).

    Caller holds SELECT … FOR UPDATE on the deal and commits right after.
    """
    if await open_outgoing_tx(db, deal.id) is not None:
        raise PayoutClaimError(
            "unresolved_tx", "Є непідтверджена вихідна транзакція по угоді — повтор заборонено", http_status=409
        )
    claim_deal_for_transfer(deal, expected_status=expected_status)


async def _alert(text: str, key: str) -> None:
    try:
        from app.services.alerts import send_admin_alert

        await send_admin_alert(text, alert_key=key, throttle_minutes=5)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[PAYOUT] admin alert failed: {e}")


async def _lock_deal(db, deal_id: int) -> Deal:
    return (await db.execute(
        select(Deal).where(Deal.id == deal_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()


# ── finalize ────────────────────────────────────────────────────────────

async def _finalize_success(db, deal: Deal, tx: Transaction) -> None:
    tx.status = TransactionStatus.confirmed
    tx.receipt_status = "SUCCESS"
    tx.finalized_at = utcnow_naive()
    channel = await db.get(Channel, deal.channel_id) if deal.channel_id else None
    if tx.type == TransactionType.release:
        deal.seller_payout_address = tx.to_address
        mark_deal_completed(deal, tx.tx_hash)
        if channel is not None:
            channel.status = ChannelStatus.sold
    elif tx.type == TransactionType.refund:
        deal.payout_tx_hash = tx.tx_hash  # idempotency marker for refunds
        deal.status = DealStatus.cancelled
        if channel is not None:
            channel.status = ChannelStatus.approved
    logger.info(f"[PAYOUT] Deal #{deal.id}: {tx.type.value} SUCCESS tx={tx.tx_hash}")


async def _finalize_failure(db, deal: Deal, tx: Transaction, reason: str) -> None:
    tx.status = TransactionStatus.failed
    tx.receipt_status = (reason or "FAILED")[:50]
    tx.receipt_reason = reason
    tx.finalized_at = utcnow_naive()
    if (tx.type in (TransactionType.release, TransactionType.refund)
            and deal.status == DealStatus.payout_in_progress and tx.restore_status):
        release_payout_claim(deal, restore_status=DealStatus(tx.restore_status))
    logger.error(f"[PAYOUT] Deal #{deal.id}: {tx.type.value} FAILED tx={tx.tx_hash}: {reason}")


async def _sweep_trx(deal: Deal) -> None:
    try:
        await asyncio.to_thread(escrow_svc.sweep_trx_to_master, deal.escrow_private_key_encrypted)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[PAYOUT] Deal #{deal.id}: TRX sweep-back failed: {e}")


async def _apply_receipt(db, deal_id: int, tx_id: int, receipt: dict) -> TransferOutcome:
    """Finalize under the deal row lock; idempotent (no-op if row no longer pending)."""
    deal = await _lock_deal(db, deal_id)
    tx = await db.get(Transaction, tx_id, populate_existing=True)
    if tx.status != TransactionStatus.pending:
        await db.commit()
        st = "success" if tx.status == TransactionStatus.confirmed else "failed"
        return TransferOutcome(st, tx.tx_hash, None if st == "success" else tx.receipt_reason, tx.receipt_status, tx.id)
    if receipt["status"] == "SUCCESS":
        await _finalize_success(db, deal, tx)
        await db.commit()
        await _sweep_trx(deal)
        return TransferOutcome("success", tx.tx_hash, transaction_id=tx.id)
    if receipt["status"] == "FAILED":
        reason = receipt.get("reason") or "FAILED"
        await _finalize_failure(db, deal, tx, reason)
        await db.commit()
        await _alert(
            f"🔴 <b>Escrow {tx.type.value} FAILED</b> — deal #{deal.id}\n"
            f"Reason: <code>{reason}</code>\nTX: <code>{tx.tx_hash}</code>\n"
            f"Статус: {deal.status.value}",
            f"payout_failed_{tx.id}",
        )
        await _sweep_trx(deal)
        return TransferOutcome("failed", tx.tx_hash, f"Транзакція не виконана: {reason}. TX: {tx.tx_hash}", reason, tx.id)
    await db.commit()
    return TransferOutcome("pending", tx.tx_hash, None, "PENDING", tx.id)


# ── execute ─────────────────────────────────────────────────────────────

async def execute_transfer(
    db,
    deal: Deal,
    *,
    tx_type: TransactionType,
    to_address: str,
    amount_units: int,
    restore_status: DealStatus | None,
    allow_master: bool = False,
    receipt_timeout: float | None = None,
) -> TransferOutcome:
    """Send amount_units USDT from deal escrow to to_address (see module docstring).

    For release/refund the deal must already be claimed (payout_in_progress) and that claim
    committed; on refusal/failure the claim is released to restore_status. For
    fee_collection/sweep the caller holds the deal row lock; the committed pending row is
    the lock for concurrent requests.
    """
    deal_id = deal.id
    escrow_addr = deal.escrow_wallet_address
    enc_key = deal.escrow_private_key_encrypted
    amount_units = int(amount_units)

    async def refuse(code: str, msg: str) -> TransferOutcome:
        d = await _lock_deal(db, deal_id)
        if restore_status is not None and d.status == DealStatus.payout_in_progress:
            release_payout_claim(d, restore_status=restore_status)
        await db.commit()
        await _alert(
            f"⚠️ <b>Escrow {tx_type.value} REFUSED</b> — deal #{deal_id}\n{msg}\nНічого не відправлено.",
            f"payout_refused_{deal_id}_{code}",
        )
        return TransferOutcome("refused", None, msg, code)

    if amount_units <= 0:
        return await refuse("BAD_AMOUNT", "Некоректна сума переказу")

    # 1) On-chain balance (unknown or insufficient → refuse, nothing sent).
    try:
        balance = await asyncio.to_thread(escrow_svc.fetch_usdt_balance_units, escrow_addr)
    except escrow_svc.BalanceUnavailable as e:
        return await refuse("BALANCE_UNKNOWN", f"Баланс escrow {escrow_addr} невідомий ({e}). Спробуйте пізніше.")
    if balance < amount_units:
        return await refuse(
            "INSUFFICIENT_ESCROW",
            f"На escrow {escrow_addr} {units_to_usdt(balance)} USDT < потрібно {units_to_usdt(amount_units)} USDT",
        )

    # 2) Record the attempt BEFORE anything is broadcast.
    tx = Transaction(
        deal_id=deal_id, tx_hash=None, from_address=escrow_addr, to_address=to_address,
        amount=units_to_usdt(amount_units), amount_units=amount_units, type=tx_type,
        status=TransactionStatus.pending,
        restore_status=restore_status.value if restore_status is not None else None,
    )
    db.add(tx)
    await db.commit()
    tx_id = tx.id

    # 3) Gas + build/sign (no USDT broadcast yet).
    try:
        prepared = await asyncio.to_thread(
            escrow_svc.prepare_usdt_transfer, enc_key, to_address, amount_units, allow_master=allow_master
        )
    except Exception as e:
        reason = getattr(e, "reason", "PREPARE_ERROR")
        msg = getattr(e, "message", None) or f"Підготовка переказу не вдалася: {e}"
        d = await _lock_deal(db, deal_id)
        t = await db.get(Transaction, tx_id, populate_existing=True)
        await _finalize_failure(db, d, t, reason)
        t.receipt_reason = msg
        await db.commit()
        await _alert(f"⚠️ <b>Escrow {tx_type.value} NOT SENT</b> — deal #{deal_id}\n{msg}", f"payout_prep_{deal_id}_{reason}")
        await _sweep_trx(deal)
        return TransferOutcome("refused", None, msg, reason, tx_id)

    # 4) txid is known before broadcast → persist it first.
    t = await db.get(Transaction, tx_id, populate_existing=True)
    t.tx_hash = prepared["txid"]
    t.fee_limit_sun = prepared.get("fee_limit_sun")
    t.broadcast_at = utcnow_naive()
    await db.commit()
    tx_hash = prepared["txid"]

    # 5) Broadcast. An exception does NOT mean it was not sent — rely on the receipt.
    try:
        await asyncio.to_thread(escrow_svc.broadcast_prepared, prepared)
    except Exception as e:
        logger.error(f"[PAYOUT] Deal #{deal_id}: broadcast raised for {tx_hash}: {e} — checking receipt")

    # 6) Receipt (bounded wait). No receipt → PENDING (claim kept, reconciled later).
    timeout = escrow_svc.RECEIPT_TIMEOUT_SEC if receipt_timeout is None else receipt_timeout
    receipt = await asyncio.to_thread(escrow_svc.get_receipt, tx_hash, timeout)
    outcome = await _apply_receipt(db, deal_id, tx_id, receipt)
    if outcome.status == "pending":
        await _alert(
            f"⏳ <b>Escrow {tx_type.value} PENDING</b> — deal #{deal_id}\nTX: <code>{tx_hash}</code>\n"
            f"Немає квитанції за {int(timeout)}s; claim збережено, фінализує payment_checker.",
            f"payout_pending_{tx_id}",
        )
        outcome.error = f"Транзакція відправлена, очікує підтвердження. TX: {tx_hash}"
    return outcome


# ── reconciliation (payment_checker loop) ───────────────────────────────

async def reconcile_pending_transfers(db, now=None) -> int:
    """Finalize pending outgoing txs by receipt; never resends. Returns rows finalized."""
    now = now or utcnow_naive()
    rows = (await db.execute(
        select(Transaction.id, Transaction.deal_id).where(
            Transaction.status == TransactionStatus.pending,
            Transaction.type.in_(OUTGOING_TYPES),
        ).order_by(Transaction.id)
    )).all()
    done = 0
    for tx_id, deal_id in rows:
        try:
            tx = await db.get(Transaction, tx_id, populate_existing=True)
            age_from = tx.broadcast_at or tx.created_at or now
            stale = now - age_from >= PENDING_STALE_AFTER
            if tx.tx_hash:
                receipt = await asyncio.to_thread(escrow_svc.get_receipt, tx.tx_hash, 0)
            else:
                receipt = {"status": "PENDING", "reason": "no txid recorded"}
            if receipt["status"] == "PENDING":
                if not stale:
                    await db.commit()
                    continue
                # Never on chain after expiry window (or never broadcast). Only release
                # the claim if escrow still holds the funds; otherwise keep + alert.
                try:
                    bal = await asyncio.to_thread(escrow_svc.fetch_usdt_balance_units, tx.from_address)
                except escrow_svc.BalanceUnavailable:
                    bal = None
                need = tx.amount_units or to_units(tx.amount)
                if bal is None or bal < need:
                    await db.commit()
                    await _alert(
                        f"🟠 <b>Escrow tx unresolved</b> — deal #{deal_id}\nTX: <code>{tx.tx_hash}</code>\n"
                        f"Немає квитанції > {PENDING_STALE_AFTER}, баланс escrow={bal}. Claim НЕ знято — перевірте вручну.",
                        f"payout_unresolved_{tx_id}",
                    )
                    continue
                receipt = {"status": "FAILED", "reason": "EXPIRED_NOT_ON_CHAIN"}
            outcome = await _apply_receipt(db, deal_id, tx_id, receipt)
            if outcome.status in ("success", "failed"):
                done += 1
        except Exception as e:
            logger.error(f"[PAYOUT] reconcile tx #{tx_id}: {e}", exc_info=True)
            await db.rollback()

    # payout_in_progress with no tracked pending tx (legacy / crash before row insert):
    # conservative — never resend, alert once per process.
    stuck = (await db.execute(
        select(Deal.id).where(Deal.status == DealStatus.payout_in_progress)
    )).scalars().all()
    for deal_id in stuck:
        if deal_id in _stuck_alerted:
            continue
        if await open_outgoing_tx(db, deal_id) is None:
            _stuck_alerted.add(deal_id)
            await _alert(
                f"🟠 <b>Deal #{deal_id} stuck in payout_in_progress</b> без відстежуваної транзакції.\n"
                f"Автоматичний повтор НЕ виконується — перевірте escrow вручну.",
                f"payout_stuck_{deal_id}",
            )
    await db.commit()
    return done
