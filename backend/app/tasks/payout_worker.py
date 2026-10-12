"""Background payout worker — the ONLY place that executes outgoing escrow transfers.

* HTTP handlers claim the deal and enqueue a job row (pending Transaction, tx_hash NULL)
  in the same commit, then return 202.
* Exactly one worker runs at a time across instances: a session-level PostgreSQL
  advisory lock held on a dedicated connection. During a deploy overlap the new
  instance waits until the old one exits (lock released with its connection).
* Each cycle: (1) process queued jobs, (2) reconcile broadcast-but-pending txs by receipt
  (never resends), (3) alert on payout_in_progress deals without a tracked job, and
  (4) every ~5 min: master gas coverage alerts, 15-min snapshots, 09:00 daily summary
  (app.services.gas_monitor).
  The first cycle after start is the restart recovery.
* All blocking tronpy calls run in ``asyncio.to_thread`` (inside app.services.payouts).
"""
from __future__ import annotations

import asyncio
import html
import logging

from sqlalchemy import select, text

from app.config import settings
from app.database import async_session, engine
from app.models.deal import Transaction, TransactionStatus
from app.services import payouts
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

ADVISORY_LOCK_KEY = 7_316_400_112  # "tgsell payout worker" (arbitrary, stable)
MASTER_CHECK_EVERY_N_CYCLES = 60  # × 5s ≈ every 5 min


class PayoutWorker:
    def __init__(self, *, engine_=None, session_factory=None, receipt_timeout: float | None = None):
        self.engine = engine_ or engine
        self.session_factory = session_factory or async_session
        self.receipt_timeout = receipt_timeout
        self._conn = None
        self.cycles = 0

    @property
    def is_leader(self) -> bool:
        return self._conn is not None

    async def acquire(self) -> bool:
        """Try to become the single worker (non-blocking)."""
        if self._conn is not None:
            try:
                await self._conn.execute(text("SELECT 1"))
                await self._conn.commit()
                return True
            except Exception as e:
                logger.warning(f"[PAYOUT-WORKER] lock connection lost: {e}")
                await self._drop_conn()
        conn = await self.engine.connect()
        try:
            got = (await conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}
            )).scalar()
            await conn.commit()
        except Exception:
            await conn.close()
            raise
        if not got:
            await conn.close()
            return False
        self._conn = conn
        logger.info("[PAYOUT-WORKER] advisory lock acquired — this instance runs payouts")
        return True

    async def _drop_conn(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass

    async def release(self) -> None:
        if self._conn is not None:
            try:
                await self._conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
                await self._conn.commit()
            except Exception:
                pass
            await self._drop_conn()

    async def run_once(self) -> dict:
        """One cycle; caller must hold the lock (acquire() == True)."""
        if not self.is_leader:
            return {"leader": False}
        self.cycles += 1
        processed = 0
        async with self.session_factory() as db:
            queued = (await db.execute(
                select(Transaction.id).where(
                    Transaction.status == TransactionStatus.pending,
                    Transaction.tx_hash.is_(None),
                    Transaction.receipt_status == payouts.QUEUED,
                    Transaction.type.in_(payouts.OUTGOING_TYPES),
                ).order_by(Transaction.id)
            )).scalars().all()
            await db.commit()
        for tx_id in queued:
            async with self.session_factory() as db:
                try:
                    await payouts.process_queued(db, tx_id, receipt_timeout=self.receipt_timeout)
                    processed += 1
                except Exception as e:
                    logger.error(f"[PAYOUT-WORKER] job tx#{tx_id} failed: {e}", exc_info=True)
                    await db.rollback()
        async with self.session_factory() as db:
            reconciled = await payouts.reconcile_pending_transfers(db, utcnow_naive())
        if (self.cycles - 1) % MASTER_CHECK_EVERY_N_CYCLES == 0:
            await self.gas_cycle()
        try:  # deal chat → Telegram bridge (same single-instance lock)
            import importlib

            await importlib.import_module("app.services.chat_bridge").bridge_cycle(self.session_factory)
        except Exception as e:
            logger.error(f"[PAYOUT-WORKER] chat bridge failed: {e}", exc_info=True)
        return {"leader": True, "processed": processed, "reconciled": reconciled}


async def _gas_cycle(worker: "PayoutWorker", now=None) -> None:
    """Gas alerts + 15-min snapshot + 09:00 daily summary — all under the worker lock."""
    from app.services import gas_monitor

    try:
        st = await gas_monitor.check_and_alert()
        async with worker.session_factory() as db:
            await gas_monitor.maybe_snapshot(db, st, now)
    except Exception as e:
        logger.error(f"[PAYOUT-WORKER] gas check failed: {e}", exc_info=True)
    try:
        await gas_monitor.maybe_send_daily_summary(worker.session_factory, now)
    except Exception as e:
        logger.error(f"[PAYOUT-WORKER] daily summary failed: {e}", exc_info=True)


PayoutWorker.gas_cycle = lambda self, now=None: _gas_cycle(self, now)


async def master_trx_status() -> dict:
    master = settings.tron_master_wallet_address
    from app.services import escrow as escrow_svc

    trx = await asyncio.to_thread(escrow_svc.get_trx_balance, master)
    threshold = float(settings.master_trx_low_threshold)
    return {
        "address": master,
        "trx": trx,
        "unknown": trx is None,
        "threshold": threshold,
        "low": trx is not None and trx < threshold,
    }


async def check_master_trx() -> dict:
    """Throttled admin alert when master TRX is below threshold (unknown → no alert)."""
    st = await master_trx_status()
    if st["low"]:
        try:
            from app.services.alerts import send_admin_alert

            await send_admin_alert(
                f"⛽ <b>Master TRX низький</b>: {st['trx']:.2f} TRX &lt; {st['threshold']:.0f} TRX\n"
                f"<code>{html.escape(str(st['address']))}</code>\nПоповніть для газу виплат.",
                alert_key="master_trx_low",
                throttle_minutes=360,
            )
        except Exception as e:  # pragma: no cover
            logger.warning(f"[PAYOUT-WORKER] master TRX alert failed: {e}")
    return st


async def run_payout_worker(interval_seconds: float = 5.0) -> None:
    worker = PayoutWorker()
    logger.info(f"Payout worker started (interval {interval_seconds}s)")
    while True:
        try:
            if await worker.acquire():
                await worker.run_once()
        except asyncio.CancelledError:
            await worker.release()
            raise
        except Exception as e:
            logger.error(f"[PAYOUT-WORKER] cycle error: {e}", exc_info=True)
        await asyncio.sleep(interval_seconds)
