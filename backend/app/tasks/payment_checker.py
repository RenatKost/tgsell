"""Background task: monitor USDT deposits for unpaid deals.

Rules (audit 2026-10-06, task 11):
* Deals in ``created`` AND ``payment_pending`` are checked (the buyer receives the
  escrow address right at creation, so money can arrive before both sides are ready).
* BALANCE FIRST, then timeout:
    - balance unknown (TronGrid error / 429)  → do nothing, retry next cycle;
    - balance >= amount                       → paid (even if the deadline passed);
    - 0 < balance < amount (partial)          → never cancel, alert admin (deduped);
    - balance == 0 (confirmed) and deadline passed → re-check once, then cancel +
      notify buyer, seller and admin group.
* Deadline: ``deal.payment_deadline_at`` (migration 0025). Legacy deals have NULL:
    - legacy ``payment_pending`` → created_at + PAYMENT_TIMEOUT_HOURS (old rule);
    - legacy ``created``         → NO auto-cancel (no mass cancel on deploy).
* Status changes use a conditional UPDATE (WHERE status = <seen status>) so a
  concurrent transition is never overwritten.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session
from app.models.deal import Deal, DealMessage, DealStatus, Transaction, TransactionStatus, TransactionType
from app.services import escrow as escrow_svc
from app.services.payment_deadlines import effective_payment_deadline
from app.utils.timeutil import utcnow_naive
from bot.main import (
    notify_deal_cancelled_timeout,
    notify_late_payment_admin,
    notify_partial_payment_admin,
    notify_payment_received,
)

logger = logging.getLogger(__name__)

CHECKED_STATUSES = (DealStatus.created, DealStatus.payment_pending)
CANCEL_REASON_PAYMENT_TIMEOUT = "payment_timeout"
BALANCE_EPSILON = 1e-6

# Funds arriving on a deal we auto-cancelled (race / late payer) → admin alert.
LATE_PAYMENT_WATCH_HOURS = 72
LATE_PAYMENT_CHECK_EVERY_N_CYCLES = 10  # × 30s ≈ every 5 min

# In-process alert dedup: deal_id → balance we last alerted about.
_partial_alerted: dict[int, float] = {}
_late_alerted: dict[int, float] = {}
_cycle = 0


async def _fetch_balance(address: str) -> float | None:
    """Balance or None if unknown. Runs the blocking TronGrid call in a thread."""
    try:
        return await asyncio.to_thread(escrow_svc.fetch_usdt_balance, address)
    except escrow_svc.BalanceUnavailable:
        return None


def _new_bot() -> Bot:
    return Bot(token=settings.bot_token_alerts)


async def _close_bot(bot) -> None:
    try:
        await bot.session.close()
    except Exception:
        pass


async def check_payments_once(now: datetime | None = None) -> None:
    """One checker cycle over all unpaid deals (+ periodic late-payment watch)."""
    global _cycle
    _cycle += 1
    async with async_session() as db:
        result = await db.execute(
            select(Deal.id).where(Deal.status.in_(CHECKED_STATUSES)).order_by(Deal.id)
        )
        deal_ids = list(result.scalars().all())
        for deal_id in deal_ids:
            try:
                # Fresh row each time (a rollback for a previous deal expires instances).
                deal = await db.get(Deal, deal_id, populate_existing=True)
                if deal is None or deal.status not in CHECKED_STATUSES:
                    continue
                await _process_deal(db, deal, now or utcnow_naive())
            except Exception as e:
                logger.error(f"[PAYMENT] Deal #{deal_id}: ERROR checking payment: {e}", exc_info=True)
                await db.rollback()

    if (_cycle - 1) % max(1, LATE_PAYMENT_CHECK_EVERY_N_CYCLES) == 0:
        try:
            await check_late_payments_once(now or utcnow_naive())
        except Exception as e:
            logger.error(f"[PAYMENT] late-payment watch failed: {e}", exc_info=True)


async def _process_deal(db, deal: Deal, now: datetime) -> None:
    balance = await _fetch_balance(deal.escrow_wallet_address)
    if balance is None:
        logger.warning(
            f"[PAYMENT] Deal #{deal.id} ({deal.status.value}): balance UNKNOWN for "
            f"{deal.escrow_wallet_address} — no action, retry next cycle"
        )
        return

    logger.info(
        f"[PAYMENT] Deal #{deal.id} ({deal.status.value}): checking escrow {deal.escrow_wallet_address}, "
        f"balance={balance} USDT, required={deal.amount_usdt} USDT"
    )

    if balance + BALANCE_EPSILON >= deal.amount_usdt:
        await _mark_paid(db, deal, balance, now)
        return

    if balance > 0:
        await _alert_partial(deal, balance)
        return  # partial payment: never auto-cancel

    deadline = effective_payment_deadline(deal)
    if deadline is None or now <= deadline:
        return

    # Confirmed 0 and past the deadline: re-check right before cancelling.
    balance2 = await _fetch_balance(deal.escrow_wallet_address)
    if balance2 is None or balance2 > 0:
        logger.warning(
            f"[PAYMENT] Deal #{deal.id}: re-check before cancel gave {balance2!r} — not cancelling"
        )
        return
    await _cancel_for_timeout(db, deal, now)


async def _mark_paid(db, deal: Deal, balance: float, now: datetime) -> None:
    prev_status = deal.status
    res = await db.execute(
        update(Deal)
        .where(Deal.id == deal.id, Deal.status == prev_status)
        .values(status=DealStatus.paid, paid_at=now)
    )
    if res.rowcount != 1:
        await db.rollback()
        logger.warning(f"[PAYMENT] Deal #{deal.id}: status changed concurrently — not marking paid")
        return
    db.add(Transaction(
        deal_id=deal.id,
        to_address=deal.escrow_wallet_address,
        amount=balance,
        type=TransactionType.deposit,
        status=TransactionStatus.confirmed,
    ))
    await db.commit()
    await db.refresh(deal)
    _partial_alerted.pop(deal.id, None)
    logger.info(
        f"[PAYMENT] Deal #{deal.id} PAID ({prev_status.value} → paid): {balance} USDT received at "
        f"{deal.escrow_wallet_address}; deposit transaction recorded"
    )

    # Transfer checklist starts now (idempotent; GET /checklist also creates lazily)
    # Separate session: a failure here must not expire/roll back the paid deal.
    paid_deal_id = deal.id
    try:
        from app.services.deal_checklist import ensure_checklist
        async with async_session() as cdb:
            cdeal = await cdb.get(Deal, paid_deal_id)
            if cdeal is not None:
                await ensure_checklist(cdb, cdeal)
                await cdb.commit()
    except Exception as e:
        logger.error(f"[CHECKLIST] deal #{paid_deal_id}: checklist init failed: {e}")

    db.add(DealMessage(
        deal_id=deal.id,
        sender_id=deal.buyer_id,
        text=(
            f"Оплата {balance} USDT отримана!\n"
            f"Продавець, передайте канал покупцю через Telegram і відмічайте "
            f"пункти чек-листа передачі нижче.\n"
            f"Покупець, після отримання перевірте канал, відмітьте свої пункти "
            f"чек-листа та натисніть «Підтвердити отримання»."
        ),
        is_system=True,
    ))
    await db.commit()

    try:
        from app.models.user import User
        buyer = await db.get(User, deal.buyer_id)
        seller = await db.get(User, deal.seller_id)
        if buyer and seller:
            bot = _new_bot()
            try:
                await notify_payment_received(bot, deal, buyer, seller)
            finally:
                await _close_bot(bot)
            logger.info(f"[PAYMENT] Deal #{deal.id}: Telegram notification sent to buyer={buyer.telegram_id}, seller={seller.telegram_id}")
    except Exception as e:
        logger.error(f"[PAYMENT] Deal #{deal.id}: Telegram notification FAILED: {e}", exc_info=True)


async def _alert_partial(deal: Deal, balance: float) -> None:
    logger.warning(f"[PAYMENT] Deal #{deal.id}: PARTIAL payment {balance}/{deal.amount_usdt} USDT — not cancelling")
    if _partial_alerted.get(deal.id) == balance:
        return
    _partial_alerted[deal.id] = balance
    bot = _new_bot()
    try:
        await notify_partial_payment_admin(bot, deal, balance)
    except Exception as e:
        logger.error(f"[PAYMENT] Deal #{deal.id}: partial-payment admin alert failed: {e}")
    finally:
        await _close_bot(bot)


async def _cancel_for_timeout(db, deal: Deal, now: datetime) -> None:
    prev_status = deal.status
    res = await db.execute(
        update(Deal)
        .where(Deal.id == deal.id, Deal.status == prev_status)
        .values(
            status=DealStatus.cancelled,
            cancelled_at=now,
            cancel_reason=CANCEL_REASON_PAYMENT_TIMEOUT,
        )
    )
    if res.rowcount != 1:
        await db.rollback()
        logger.warning(f"[PAYMENT] Deal #{deal.id}: status changed concurrently — not cancelling")
        return
    db.add(DealMessage(
        deal_id=deal.id,
        sender_id=deal.buyer_id,
        text=(
            "Угоду автоматично скасовано: оплату не отримано вчасно "
            "(баланс ескроу — 0 USDT). Якщо ви все ж надіслали кошти — напишіть у підтримку."
        ),
        is_system=True,
    ))
    await db.commit()
    await db.refresh(deal)
    logger.info(
        f"[PAYMENT] Deal #{deal.id} CANCELLED ({prev_status.value} → cancelled): payment timeout, "
        f"escrow balance confirmed 0"
    )

    try:
        from app.models.user import User
        buyer = await db.get(User, deal.buyer_id)
        seller = await db.get(User, deal.seller_id)
        bot = _new_bot()
        try:
            await notify_deal_cancelled_timeout(bot, deal, buyer, seller)
        finally:
            await _close_bot(bot)
    except Exception as e:
        logger.error(f"[PAYMENT] Deal #{deal.id}: cancel notification FAILED: {e}", exc_info=True)


async def check_late_payments_once(now: datetime) -> None:
    """Funds that arrive on a deal we auto-cancelled recently → admin alert (deduped)."""
    since = now - timedelta(hours=LATE_PAYMENT_WATCH_HOURS)
    async with async_session() as db:
        result = await db.execute(
            select(Deal).where(
                Deal.status == DealStatus.cancelled,
                Deal.cancel_reason == CANCEL_REASON_PAYMENT_TIMEOUT,
                Deal.cancelled_at >= since,
            ).order_by(Deal.id)
        )
        deals = result.scalars().all()
    for deal in deals:
        balance = await _fetch_balance(deal.escrow_wallet_address)
        if balance is None or balance <= 0 or _late_alerted.get(deal.id) == balance:
            continue
        _late_alerted[deal.id] = balance
        logger.warning(f"[PAYMENT] Deal #{deal.id}: {balance} USDT arrived AFTER auto-cancel")
        bot = _new_bot()
        try:
            await notify_late_payment_admin(bot, deal, balance)
        except Exception as e:
            logger.error(f"[PAYMENT] Deal #{deal.id}: late-payment admin alert failed: {e}")
        finally:
            await _close_bot(bot)


async def run_payment_checker(interval_seconds: int = 30):
    """Run payment checker loop."""
    logger.info(f"Payment checker started (interval: {interval_seconds}s)")
    while True:
        try:
            await check_payments_once()
        except Exception as e:
            logger.error(f"Payment checker error: {e}")
            from app.services.alerts import alert_service_down
            await alert_service_down("Payment Checker", str(e))
        await asyncio.sleep(interval_seconds)
