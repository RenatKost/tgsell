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
* HTTP handlers only claim + enqueue (job row in the SAME commit as the claim) and
  return 202; the single payout worker (app.tasks.payout_worker, PG advisory lock)
  runs :func:`process_queued` and :func:`reconcile_pending_transfers`.
* Receipt SUCCESS → finalize (deal completed / cancelled-with-refund). FAILED → release the
  claim to the status stored on the row + admin alert. No receipt within the wait window
  → PENDING: claim kept, row stays pending, :func:`reconcile_pending_transfers`
  (payment_checker loop) finalizes later.
"""
from __future__ import annotations

import asyncio
import html
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
# receipt_status marker of a job enqueued for the worker. Rows without it and without a
# tx_hash belong to an in-flight synchronous attempt of the previous release (deploy
# overlap) and are never picked up by the worker.
QUEUED = "QUEUED"

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


def _e(value) -> str:
    """HTML-escape an interpolated value for Telegram HTML alerts."""
    return html.escape("" if value is None else str(value), quote=False)


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
    if tx.type == TransactionType.release:
        _add_deal_message(db, deal, f"Виплата {tx.amount} USDT підтверджена мережею ✅\nTX: {tx.tx_hash}")
    elif tx.type == TransactionType.refund:
        _add_deal_message(db, deal, f"Повернення {tx.amount} USDT покупцю підтверджено ✅\nTX: {tx.tx_hash}")
    logger.info(f"[PAYOUT] Deal #{deal.id}: {tx.type.value} SUCCESS tx={tx.tx_hash}")


async def _finalize_failure(db, deal: Deal, tx: Transaction, reason: str) -> None:
    tx.status = TransactionStatus.failed
    tx.receipt_status = (reason or "FAILED")[:50]
    tx.receipt_reason = reason
    tx.finalized_at = utcnow_naive()
    if (tx.type in (TransactionType.release, TransactionType.refund)
            and deal.status == DealStatus.payout_in_progress and tx.restore_status):
        release_payout_claim(deal, restore_status=DealStatus(tx.restore_status))
    if tx.type in (TransactionType.release, TransactionType.refund):
        _add_deal_message(db, deal, "Виплату не виконано (кошти лишаються в escrow). Адміністратора повідомлено.")
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
            f"Reason: <code>{_e(reason)}</code>\nTX: <code>{_e(tx.tx_hash)}</code>\n"
            f"Статус: {deal.status.value}",
            f"payout_failed_{tx.id}",
        )
        await _sweep_trx(deal)
        return TransferOutcome("failed", tx.tx_hash, f"Транзакція не виконана: {reason}. TX: {tx.tx_hash}", reason, tx.id)
    await db.commit()
    return TransferOutcome("pending", tx.tx_hash, None, "PENDING", tx.id)


# ── pre-claim gas funding check ─────────────────────────────────────────

# Refused prechecks (timestamps, this process) — shown in gas alerts/summary.
_precheck_refusals: list = []


def record_precheck_refusal(reason: str, now=None) -> None:
    now = now or utcnow_naive()
    _precheck_refusals.append((now, reason))
    cutoff = now - timedelta(hours=24)
    while _precheck_refusals and _precheck_refusals[0][0] < cutoff:
        _precheck_refusals.pop(0)


def refused_prechecks_24h(now=None) -> int:
    cutoff = (now or utcnow_naive()) - timedelta(hours=24)
    return sum(1 for t, _ in _precheck_refusals if t >= cutoff)

async def precheck_gas(deal: Deal, to_address: str, amount_units: int, *, allow_master: bool = False) -> dict:
    """Master/escrow TRX must cover the estimated gas BEFORE any claim.

    Unknown balances → refuse (never assume funded). Raises PayoutError(http 503) with a
    clear text; sends a throttled admin alert when master TRX is insufficient/unknown.
    """
    res = await asyncio.to_thread(
        escrow_svc.check_gas_funding, deal.escrow_wallet_address, to_address, int(amount_units)
    )
    if res.get("ok"):
        return res
    reason = res.get("reason") or "GAS_UNKNOWN"
    record_precheck_refusal(reason)
    await _alert(
        f"⛽ <b>Master TRX: виплату не розпочато</b> — deal #{deal.id}\n{_e(res.get('message'))}",
        f"master_trx_{reason}",
    )
    raise PayoutError(
        "master_trx",
        "Виплата тимчасово недоступна: на платформному гаманці недостатньо TRX для комісії мережі "
        "(або баланс не вдалося перевірити). Адміністратора повідомлено, статус угоди не змінено — "
        "спробуйте пізніше.",
        http_status=503,
    )


# ── enqueue (HTTP) + process (worker) ───────────────────────────────────

def enqueue_transfer(
    db,
    deal: Deal,
    *,
    tx_type: TransactionType,
    to_address: str,
    amount_units: int,
    restore_status: DealStatus | None,
) -> Transaction:
    """Add the job row (pending, tx_hash NULL) to the CURRENT db transaction.

    The caller commits it together with the claim, so there is no window where a deal is
    payout_in_progress without a tracked job (crash-safe: tx_hash NULL ⇒ never broadcast,
    the worker can process it after a restart).
    """
    tx = Transaction(
        deal_id=deal.id, tx_hash=None, from_address=deal.escrow_wallet_address, to_address=to_address,
        amount=units_to_usdt(int(amount_units)), amount_units=int(amount_units), type=tx_type,
        status=TransactionStatus.pending, receipt_status=QUEUED,
        restore_status=restore_status.value if restore_status is not None else None,
    )
    db.add(tx)
    return tx


def _add_deal_message(db, deal: Deal, text: str) -> None:
    from app.models.deal import DealMessage

    db.add(DealMessage(deal_id=deal.id, sender_id=deal.seller_id, text=text, is_system=True))


async def process_queued(db, tx_id: int, *, receipt_timeout: float | None = None) -> TransferOutcome:
    """Worker: execute one queued job (pending row with tx_hash NULL). Never resends.

    balance check → gas top-up + build/sign → persist txid → broadcast → receipt.
    """
    tx = await db.get(Transaction, tx_id, populate_existing=True)
    if tx is None or tx.status != TransactionStatus.pending or tx.tx_hash or tx.receipt_status != QUEUED:
        await db.commit()
        return TransferOutcome("pending" if tx is not None and tx.status == TransactionStatus.pending else "skipped")
    deal = await _lock_deal(db, tx.deal_id)
    tx = await db.get(Transaction, tx_id, populate_existing=True)
    if tx.status != TransactionStatus.pending or tx.tx_hash or tx.receipt_status != QUEUED:
        await db.commit()
        return TransferOutcome("skipped")
    tx.receipt_status = "PROCESSING"
    deal_id = deal.id
    tx_type = tx.type
    to_address = tx.to_address
    amount_units = int(tx.amount_units or to_units(tx.amount))
    allow_master = tx_type == TransactionType.fee_collection
    await db.commit()  # release row lock during network calls

    async def refuse(code: str, msg: str, *, sweep: bool = False) -> TransferOutcome:
        d = await _lock_deal(db, deal_id)
        t = await db.get(Transaction, tx_id, populate_existing=True)
        await _finalize_failure(db, d, t, code)
        t.receipt_reason = msg
        await db.commit()
        await _alert(
            f"⚠️ <b>Escrow {tx_type.value} NOT SENT</b> — deal #{deal_id}\n{_e(msg)}\nНічого не відправлено.",
            f"payout_refused_{deal_id}_{code}",
        )
        if sweep:
            await _sweep_trx(d)
        return TransferOutcome("refused", None, msg, code, tx_id)

    if amount_units <= 0:
        return await refuse("BAD_AMOUNT", "Некоректна сума переказу")
    try:
        balance = await asyncio.to_thread(escrow_svc.fetch_usdt_balance_units, deal.escrow_wallet_address)
    except escrow_svc.BalanceUnavailable as e:
        return await refuse("BALANCE_UNKNOWN", f"Баланс escrow {deal.escrow_wallet_address} невідомий ({e}).")
    if balance < amount_units:
        return await refuse(
            "INSUFFICIENT_ESCROW",
            f"На escrow {deal.escrow_wallet_address} {units_to_usdt(balance)} USDT < "
            f"потрібно {units_to_usdt(amount_units)} USDT",
        )

    try:
        prepared = await asyncio.to_thread(
            escrow_svc.prepare_usdt_transfer, deal.escrow_private_key_encrypted, to_address,
            amount_units, allow_master=allow_master,
        )
    except Exception as e:
        reason = getattr(e, "reason", "PREPARE_ERROR")
        msg = getattr(e, "message", None) or f"Підготовка переказу не вдалася: {e}"
        return await refuse(reason, msg, sweep=True)

    # txid is known before broadcast → persist it first.
    t = await db.get(Transaction, tx_id, populate_existing=True)
    t.tx_hash = prepared["txid"]
    t.fee_limit_sun = prepared.get("fee_limit_sun")
    t.broadcast_at = utcnow_naive()
    await db.commit()
    tx_hash = prepared["txid"]

    try:
        await asyncio.to_thread(escrow_svc.broadcast_prepared, prepared)
    except Exception as e:
        logger.error(f"[PAYOUT] Deal #{deal_id}: broadcast raised for {tx_hash}: {e} — checking receipt")

    timeout = escrow_svc.RECEIPT_TIMEOUT_SEC if receipt_timeout is None else receipt_timeout
    receipt = await asyncio.to_thread(escrow_svc.get_receipt, tx_hash, timeout)
    outcome = await _apply_receipt(db, deal_id, tx_id, receipt)
    if outcome.status == "pending":
        await _alert(
            f"⏳ <b>Escrow {tx_type.value} PENDING</b> — deal #{deal_id}\nTX: <code>{_e(tx_hash)}</code>\n"
            f"Немає квитанції за {int(timeout)}s; claim збережено, worker фіналізує за квитанцією.",
            f"payout_pending_{tx_id}",
        )
        outcome.error = f"Транзакція відправлена, очікує підтвердження. TX: {tx_hash}"
    return outcome


async def payout_status(db, deal: Deal) -> dict:
    """Status of the latest outgoing transfer of a deal (for UI polling)."""
    tx = (await db.execute(
        select(Transaction).where(
            Transaction.deal_id == deal.id, Transaction.type.in_(OUTGOING_TYPES)
        ).order_by(Transaction.id.desc()).limit(1)
    )).scalar_one_or_none()
    last = None
    if tx is not None:
        if tx.status == TransactionStatus.pending:
            state = "queued" if not tx.tx_hash else "broadcast"
        else:
            state = "confirmed" if tx.status == TransactionStatus.confirmed else "failed"
        last = {
            "id": tx.id, "type": tx.type.value, "state": state, "tx_hash": tx.tx_hash,
            "amount_usdt": tx.amount, "receipt_status": tx.receipt_status, "reason": tx.receipt_reason,
        }
    return {
        "deal_id": deal.id,
        "deal_status": deal.status.value,
        "payout_tx_hash": deal.payout_tx_hash,
        "in_progress": deal.status == DealStatus.payout_in_progress
        or (last is not None and last["state"] in ("queued", "broadcast")),
        "last_transfer": last,
    }


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
            stale = now - (tx.broadcast_at or tx.created_at or now) >= PENDING_STALE_AFTER
            if not tx.tx_hash:
                if tx.receipt_status == QUEUED or not stale:
                    # Queued job — processed by the payout worker (or fresh in-flight attempt).
                    await db.commit()
                    continue
                # Stale row without txid: txid is persisted BEFORE broadcast, so this was
                # never broadcast (crash during gas/prepare) → safe to fail + release claim.
                await _apply_receipt(db, deal_id, tx_id, {"status": "FAILED", "reason": "NEVER_BROADCAST"})
                done += 1
                continue
            age_from = tx.broadcast_at or tx.created_at or now
            stale = now - age_from >= PENDING_STALE_AFTER
            receipt = await asyncio.to_thread(escrow_svc.get_receipt, tx.tx_hash, 0)
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
                        f"🟠 <b>Escrow tx unresolved</b> — deal #{deal_id}\nTX: <code>{_e(tx.tx_hash)}</code>\n"
                        f"Немає квитанції &gt; {PENDING_STALE_AFTER}, баланс escrow={bal}. Claim НЕ знято — перевірте вручну.",
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
