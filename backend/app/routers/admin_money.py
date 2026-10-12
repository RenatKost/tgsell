"""Admin money control (PR 2): transactions, payout queue, escrow overview, gas, summary.

All endpoints are admin-only. Queue actions never send anything on-chain:
* recheck   — reads the receipt of ONE broadcast tx and finalizes it (same path as the
              worker's reconcile; idempotent under the deal row lock). Never resends.
* mark-failed — only for a broadcast tx that is stale (> PENDING_STALE_AFTER), still not
              found on chain, AND whose escrow still holds the full amount. Releases the
              claim exactly like the automatic reconcile does. Audited.
"""
from __future__ import annotations

import asyncio
import csv
import io
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.deal import Deal, DealStatus, Transaction, TransactionStatus, TransactionType
from app.models.user import User
from app.services.moderation import audit
from app.utils.security import get_superadmin_user
from app.utils.timeutil import utcnow_naive

router = APIRouter(prefix="/admin", tags=["admin-money"])

TRONSCAN_TX = "https://tronscan.org/#/transaction/{}"
FUNDED_ACTIVE = (DealStatus.paid, DealStatus.channel_transferring, DealStatus.awaiting_payout,
                 DealStatus.payout_in_progress, DealStatus.disputed)


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _tx_row(tx: Transaction, now=None) -> dict:
    from app.services.payouts import OUTGOING_TYPES, PENDING_STALE_AFTER, QUEUED

    now = now or utcnow_naive()
    stage = None
    if tx.status == TransactionStatus.pending and tx.type in OUTGOING_TYPES:
        if not tx.tx_hash:
            stage = "queued" if tx.receipt_status == QUEUED else "in_flight"
        else:
            age_from = tx.broadcast_at or tx.created_at or now
            stage = "stale" if now - age_from >= PENDING_STALE_AFTER else "broadcast"
    return {
        "id": tx.id, "deal_id": tx.deal_id, "type": tx.type.value, "status": tx.status.value,
        "stage": stage, "amount": tx.amount, "amount_units": tx.amount_units,
        "from_address": tx.from_address, "to_address": tx.to_address, "tx_hash": tx.tx_hash,
        "tronscan_url": TRONSCAN_TX.format(tx.tx_hash) if tx.tx_hash else None,
        "receipt_status": tx.receipt_status, "receipt_reason": tx.receipt_reason,
        "created_at": _iso(tx.created_at), "broadcast_at": _iso(tx.broadcast_at),
        "finalized_at": _iso(tx.finalized_at),
    }


def _parse_date(s: str | None, name: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Некоректна дата {name}")


def _tx_query(type_, status_, deal_id, address, date_from, date_to, receipt_status):
    q = select(Transaction)
    if type_:
        try:
            q = q.where(Transaction.type == TransactionType(type_))
        except ValueError:
            raise HTTPException(status_code=400, detail="Невідомий тип")
    if status_:
        try:
            q = q.where(Transaction.status == TransactionStatus(status_))
        except ValueError:
            raise HTTPException(status_code=400, detail="Невідомий статус")
    if deal_id is not None:
        q = q.where(Transaction.deal_id == deal_id)
    if address:
        a = address.strip()
        q = q.where((Transaction.from_address == a) | (Transaction.to_address == a) | (Transaction.tx_hash == a))
    if receipt_status:
        q = q.where(Transaction.receipt_status == receipt_status)
    f, t = _parse_date(date_from, "from"), _parse_date(date_to, "to")
    if f:
        q = q.where(Transaction.created_at >= f)
    if t:
        q = q.where(Transaction.created_at < t)
    return q


@router.get("/transactions")
async def list_transactions(
    type: str | None = None,
    status: str | None = None,
    deal_id: int | None = None,
    address: str | None = Query(None, max_length=100),
    date_from: str | None = None,
    date_to: str | None = None,
    receipt_status: str | None = Query(None, max_length=50),
    format: str = Query("json", pattern="^(json|csv)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    q = _tx_query(type, status, deal_id, address, date_from, date_to, receipt_status)
    now = utcnow_naive()
    if format == "csv":
        rows = (await db.execute(q.order_by(Transaction.id.desc()).limit(20_000))).scalars().all()
        buf = io.StringIO()
        cols = ["id", "deal_id", "type", "status", "stage", "amount", "amount_units", "from_address",
                "to_address", "tx_hash", "tronscan_url", "receipt_status", "receipt_reason",
                "created_at", "broadcast_at", "finalized_at"]
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for tx in rows:
            w.writerow(_tx_row(tx, now))
        return StreamingResponse(
            iter([buf.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="transactions-{now:%Y%m%d-%H%M}.csv"'},
        )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    rows = (await db.execute(q.order_by(Transaction.id.desc()).offset((page - 1) * limit).limit(limit))).scalars().all()
    return {"items": [_tx_row(t, now) for t in rows], "total": total, "page": page, "limit": limit}


@router.get("/payout-queue")
async def payout_queue(
    failed_hours: int = Query(72, ge=1, le=24 * 30),
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.payouts import OUTGOING_TYPES

    now = utcnow_naive()
    pending = (await db.execute(select(Transaction).where(
        Transaction.status == TransactionStatus.pending, Transaction.type.in_(OUTGOING_TYPES),
    ).order_by(Transaction.id))).scalars().all()
    failed = (await db.execute(select(Transaction).where(
        Transaction.status == TransactionStatus.failed, Transaction.type.in_(OUTGOING_TYPES),
        func.coalesce(Transaction.finalized_at, Transaction.created_at) >= now - timedelta(hours=failed_hours),
    ).order_by(Transaction.id.desc()).limit(100))).scalars().all()
    rows = [_tx_row(t, now) for t in pending]
    return {
        "queued": [r for r in rows if r["stage"] in ("queued", "in_flight")],
        "broadcast": [r for r in rows if r["stage"] == "broadcast"],
        "stale": [r for r in rows if r["stage"] == "stale"],
        "recent_failed": [_tx_row(t, now) for t in failed],
        "checked_at": _iso(now),
    }


async def _load_outgoing_pending(db, tx_id: int) -> Transaction:
    from app.services.payouts import OUTGOING_TYPES

    tx = await db.get(Transaction, tx_id)
    if not tx or tx.type not in OUTGOING_TYPES:
        raise HTTPException(status_code=404, detail="Вихідну транзакцію не знайдено")
    if tx.status != TransactionStatus.pending:
        raise HTTPException(status_code=409, detail=f"Транзакція вже {tx.status.value}")
    if not tx.tx_hash:
        raise HTTPException(status_code=409, detail="Транзакція ще в черзі (не відправлена) — її обробить воркер")
    return tx


@router.post("/transactions/{tx_id}/recheck")
async def recheck_transaction(
    tx_id: int,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Read the receipt of one broadcast tx and finalize it if final. Never resends."""
    from app.services import escrow as escrow_svc
    from app.services import payouts

    tx = await _load_outgoing_pending(db, tx_id)
    deal_id, tx_hash = tx.deal_id, tx.tx_hash
    await db.commit()
    receipt = await asyncio.to_thread(escrow_svc.get_receipt, tx_hash, 0)
    outcome = await payouts._apply_receipt(db, deal_id, tx_id, receipt)
    audit(db, admin, "tx.recheck", "transaction", tx_id, deal_id=deal_id, receipt=receipt.get("status"),
          outcome=outcome.status)
    await db.commit()
    deal = await db.get(Deal, deal_id, populate_existing=True)
    return {"tx_id": tx_id, "receipt": receipt.get("status"), "outcome": outcome.status,
            "deal_status": deal.status.value if deal else None}


class MarkFailedRequest(BaseModel):
    note: str = Field(..., min_length=3, max_length=500)


@router.post("/transactions/{tx_id}/mark-failed")
async def mark_transaction_failed(
    tx_id: int,
    body: MarkFailedRequest,
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Release a claim of a tx that never reached the chain. Strict preconditions; no resend."""
    from app.services import escrow as escrow_svc
    from app.services import payouts

    tx = await _load_outgoing_pending(db, tx_id)
    now = utcnow_naive()
    age_from = tx.broadcast_at or tx.created_at or now
    if now - age_from < payouts.PENDING_STALE_AFTER:
        raise HTTPException(status_code=409, detail=f"Транзакція ще не застаріла (< {payouts.PENDING_STALE_AFTER})")
    deal_id, tx_hash, from_addr = tx.deal_id, tx.tx_hash, tx.from_address
    need = tx.amount_units or payouts.to_units(tx.amount)
    await db.commit()
    receipt = await asyncio.to_thread(escrow_svc.get_receipt, tx_hash, 0)
    if receipt["status"] != "PENDING":
        # Found on chain: finalize by the real receipt instead (SUCCESS or FAILED).
        outcome = await payouts._apply_receipt(db, deal_id, tx_id, receipt)
        audit(db, admin, "tx.recheck", "transaction", tx_id, deal_id=deal_id, receipt=receipt["status"],
              outcome=outcome.status, via="mark-failed")
        await db.commit()
        raise HTTPException(status_code=409, detail=f"Транзакцію знайдено в мережі ({receipt['status']}) — фіналізовано за квитанцією")
    try:
        bal = await asyncio.to_thread(escrow_svc.fetch_usdt_balance_units, from_addr)
    except escrow_svc.BalanceUnavailable:
        raise HTTPException(status_code=503, detail="Баланс escrow невідомий — позначати failed заборонено")
    if bal < need:
        raise HTTPException(status_code=409, detail="Баланс escrow менший за суму — кошти могли піти, позначати failed заборонено")
    outcome = await payouts._apply_receipt(db, deal_id, tx_id, {"status": "FAILED", "reason": "ADMIN_MARKED_NOT_ON_CHAIN"})
    audit(db, admin, "tx.mark_failed", "transaction", tx_id, deal_id=deal_id, note=body.note,
          escrow_units=bal, need_units=need, outcome=outcome.status)
    await db.commit()
    deal = await db.get(Deal, deal_id, populate_existing=True)
    return {"tx_id": tx_id, "outcome": outcome.status, "deal_status": deal.status.value if deal else None}


@router.get("/escrow/overview")
async def escrow_overview(
    refresh: bool = Query(False),
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-deal escrow reconciliation. Read-only: nothing is moved from here."""
    from app.routers.admin import check_escrow_balances
    from app.services.payouts import to_units

    balances = await check_escrow_balances(refresh=refresh, admin=admin, db=db)
    live = {w["deal_id"]: w["balance_usdt"] for w in balances.get("wallets_with_funds", [])}
    unknown = {w["deal_id"] for w in balances.get("unknown", [])}
    checked_all = balances.get("checked_count", 0)

    deals = (await db.execute(select(Deal).order_by(Deal.id.desc()))).scalars().all()
    txs = (await db.execute(select(Transaction).where(Transaction.type.in_((
        TransactionType.release, TransactionType.fee_collection, TransactionType.refund, TransactionType.sweep))))).scalars().all()
    by_deal: dict[int, list[Transaction]] = {}
    for t in txs:
        by_deal.setdefault(t.deal_id, []).append(t)

    totals = {"accrued": 0.0, "collected": 0.0, "collectable": 0.0, "not_collectable_legacy": 0.0,
              "held_active": 0.0, "stray_cancelled": 0.0, "unknown_wallets": len(unknown)}
    items = []
    for d in deals:
        ts = by_deal.get(d.id, [])
        fee = float(d.service_fee or 0)
        bal = None if d.id in unknown else live.get(d.id, 0.0 if checked_all else None)
        fee_tx = [t for t in ts if t.type == TransactionType.fee_collection
                  and t.status in (TransactionStatus.pending, TransactionStatus.confirmed)]
        fee_collected = any(t.status == TransactionStatus.confirmed for t in fee_tx)
        release_ok = any(t.type == TransactionType.release and t.tx_hash == d.payout_tx_hash
                         and t.status == TransactionStatus.confirmed and t.receipt_status == "SUCCESS" for t in ts)
        expected, fee_state, stray = None, None, False
        if d.status in FUNDED_ACTIVE:
            expected = float(d.amount_usdt)
            if bal:
                totals["held_active"] += bal
        elif d.status == DealStatus.completed:
            totals["accrued"] += fee
            if fee_collected:
                fee_state, expected = "collected", 0.0
                totals["collected"] += sum(t.amount for t in fee_tx if t.status == TransactionStatus.confirmed)
            elif fee_tx:
                fee_state = "collecting"
            elif release_ok:
                fee_state, expected = "collectable", fee
                totals["collectable"] += fee
            else:
                fee_state = "not_collectable"  # legacy (pre-0026) release without a tracked receipt
                totals["not_collectable_legacy"] += fee
        elif d.status == DealStatus.cancelled:
            expected = 0.0
            if bal:
                stray = True
                totals["stray_cancelled"] += bal
        mismatch = (expected is not None and bal is not None and not stray
                    and abs(to_units(bal) - to_units(expected)) > 0)
        notable = (bool(bal) or mismatch or bal is None or d.status in FUNDED_ACTIVE
                   or fee_state in ("collectable", "collecting", "not_collectable"))
        if not notable:
            continue
        items.append({
            "deal_id": d.id, "status": d.status.value, "escrow": d.escrow_wallet_address,
            "amount_usdt": d.amount_usdt, "service_fee": fee, "live_usdt": bal, "expected_usdt": expected,
            "fee_state": fee_state, "mismatch": mismatch, "stray": stray, "read_only": stray,
        })
    return {"items": items, "totals": {k: round(v, 6) if isinstance(v, float) else v for k, v in totals.items()},
            "balances_checked_at": balances.get("checked_at"), "cached": balances.get("cached")}


@router.get("/gas")
async def gas_status(
    refresh: bool = Query(False),
    days: int = Query(7, ge=1, le=90),
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """Master wallet gas card: address (server config), TRX, energy, bandwidth, coverage, history."""
    from app.services import gas_monitor

    st = await gas_monitor.fetch_status(force=refresh)
    return {**st, "history": await gas_monitor.snapshot_history(db, days),
            "auto_topup": False,
            "note": "Автопоповнення неможливе: платформа заробляє лише USDT; обмін на TRX потребує DEX-угоди "
                    "з ключем master. Поповнюйте вручну на адресу вище (або застейкайте/орендуйте енергію)."}


@router.get("/summary")
async def daily_summary(
    date_: str | None = Query(None, alias="date"),
    admin: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import gas_monitor

    if date_:
        try:
            day = date.fromisoformat(date_)
        except ValueError:
            raise HTTPException(status_code=400, detail="Дата у форматі YYYY-MM-DD")
    else:
        day = gas_monitor.to_local(utcnow_naive()).date() - timedelta(days=1)
    return await gas_monitor.build_summary(db, day, gas_monitor._cache["payload"])
