"""Unified escrow payouts (audit task 12, PR A) — real Postgres, TRON fully mocked.

Covers: success; FAILED; PENDING → SUCCESS (single payout); broadcast raised but funds
went (no retry); concurrent requests; invalid / master / escrow address; unknown and
insufficient balance; admin refund + release; cancel during payout_in_progress → 409;
collect-fee rules + stats; restart with payout_in_progress handled conservatively.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402
from tronpy.keys import PrivateKey  # noqa: E402

from app.utils.timeutil import utcnow_naive  # noqa: E402


def _addr(seed: int) -> str:
    return PrivateKey(bytes([seed]) * 32).public_key.to_base58check_address()


MASTER = _addr(0x11)
SELLER_W = _addr(0x33)
BUYER_W = _addr(0x44)


class FakeTron:
    """Mocks the escrow layer used by app.services.payouts."""

    def __init__(self):
        self.balances: dict[str, object] = {}
        self.prepared: list[tuple] = []
        self.broadcasts: list[str] = []
        self.receipts: dict[str, list[dict]] = {}
        self.default_receipt = {"status": "SUCCESS", "reason": None}
        self.broadcast_raises = False
        self.prepare_raises = None
        self.prepare_delay = 0.0
        self.sweeps: list[str] = []
        self._lock = threading.Lock()

    def fetch_units(self, address):
        from app.services.escrow import BalanceUnavailable

        v = self.balances.get(address, 0)
        if isinstance(v, Exception):
            raise BalanceUnavailable(str(v))
        return int(v)

    def prepare(self, enc, to, units, allow_master=False):
        if self.prepare_delay:
            time.sleep(self.prepare_delay)
        if self.prepare_raises is not None:
            raise self.prepare_raises
        with self._lock:
            self.prepared.append((enc, to, units, allow_master))
            txid = f"txid{len(self.prepared)}"
        return {"txid": txid, "txn": None, "gas_tx": None, "fee_limit_sun": 30_000_000, "estimate": {}}

    def broadcast(self, prepared):
        self.broadcasts.append(prepared["txid"])
        if self.broadcast_raises:
            raise ConnectionError("read timeout after send")
        return prepared["txid"]

    def receipt(self, txid, timeout=0):
        script = self.receipts.get(txid)
        if script:
            return script.pop(0) if len(script) > 1 else script[0]
        return dict(self.default_receipt)

    def sweep(self, enc):
        self.sweeps.append(enc)
        return "sweep"


@pytest_asyncio.fixture
async def env(pg_orm, monkeypatch):
    from app.config import settings

    payouts = importlib.import_module("app.services.payouts")
    escrow = payouts.escrow_svc
    alerts = importlib.import_module("app.services.alerts")
    admin_router = importlib.import_module("app.routers.admin")
    deals_router = importlib.import_module("app.routers.deals")
    pc = importlib.import_module("app.tasks.payment_checker")

    tron = FakeTron()
    monkeypatch.setattr(escrow, "fetch_usdt_balance_units", tron.fetch_units)
    monkeypatch.setattr(escrow, "prepare_usdt_transfer", tron.prepare)
    monkeypatch.setattr(escrow, "broadcast_prepared", tron.broadcast)
    monkeypatch.setattr(escrow, "get_receipt", tron.receipt)
    monkeypatch.setattr(escrow, "sweep_trx_to_master", tron.sweep)
    monkeypatch.setattr(escrow, "get_usdt_balance", lambda a: tron.fetch_units(a) / 1e6)
    alert = AsyncMock()
    monkeypatch.setattr(alerts, "send_admin_alert", alert)
    monkeypatch.setattr(settings, "tron_master_wallet_address", MASTER)
    payouts._stuck_alerted.clear()

    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus, Transaction, TransactionStatus, TransactionType
    from app.models.user import User

    async with pg_orm.session() as db:
        buyer = User(first_name="Buyer", telegram_id=9101, usdt_wallet=BUYER_W)
        seller = User(first_name="Seller", telegram_id=9102, usdt_wallet=SELLER_W)
        db.add_all([buyer, seller])
        await db.flush()
        channel = Channel(
            seller_id=seller.id, telegram_link="https://t.me/x", channel_name="X",
            category="news", price=100.0, status=ChannelStatus.approved,
        )
        db.add(channel)
        await db.commit()
        ids = SimpleNamespace(buyer=buyer.id, seller=seller.id, channel=channel.id)

    seeds = iter(range(0x50, 0xF0))

    async def make_deal(status, *, amount=100.0, fee=3.0, funded=True, **kw):
        escrow_addr = _addr(next(seeds))
        deal = Deal(
            channel_id=ids.channel, buyer_id=ids.buyer, seller_id=ids.seller, status=status,
            escrow_wallet_address=escrow_addr, escrow_private_key_encrypted=f"enc-{escrow_addr}",
            amount_usdt=amount, service_fee=fee, **kw,
        )
        async with pg_orm.session() as db:
            db.add(deal)
            await db.commit()
        if funded:
            tron.balances[escrow_addr] = payouts.to_units(amount)
        return deal.id, escrow_addr

    async def get(deal_id):
        async with pg_orm.session() as db:
            return await db.get(Deal, deal_id)

    async def txs(deal_id):
        async with pg_orm.session() as db:
            return list((await db.execute(
                select(Transaction).where(Transaction.deal_id == deal_id).order_by(Transaction.id)
            )).scalars())

    async def seller_wallet(deal_id, wallet=SELLER_W):
        from app.schemas.deal import SellerWalletRequest

        async with pg_orm.session() as db:
            user = await db.get(User, ids.seller)
            return await deals_router.set_seller_wallet(
                deal_id, SellerWalletRequest(wallet_address=wallet), user=user, db=db
            )

    async def resolve(deal_id, resolution, wallet=None):
        from app.schemas.deal import DealResolveRequest

        async with pg_orm.session() as db:
            return await admin_router.resolve_deal(
                deal_id, DealResolveRequest(resolution=resolution, wallet_address=wallet), admin=None, db=db
            )

    async def call(fn, *a, **kw):
        async with pg_orm.session() as db:
            return await fn(*a, admin=None, db=db, **kw)

    async def reconcile(now=None):
        async with pg_orm.session() as db:
            return await payouts.reconcile_pending_transfers(db, now)

    yield SimpleNamespace(
        orm=pg_orm, tron=tron, alert=alert, payouts=payouts, admin=admin_router, deals=deals_router,
        pc=pc, ids=ids, make_deal=make_deal, get=get, txs=txs, seller_wallet=seller_wallet,
        resolve=resolve, call=call, reconcile=reconcile, S=DealStatus, TS=TransactionStatus,
        TT=TransactionType, Tx=Transaction, Deal=Deal, Channel=Channel, CS=ChannelStatus,
    )


# ── amounts / addresses ──

def test_decimal_round_down_units():
    payouts = importlib.import_module("app.services.payouts")
    assert payouts.to_units(0.1 + 0.2) == 300_000
    assert payouts.to_units("1.9999999") == 1_999_999
    deal = SimpleNamespace(amount_usdt=10.1, service_fee=0.303)
    assert payouts.release_units(deal) == 9_797_000
    deal = SimpleNamespace(amount_usdt=15.0, service_fee=15.0 * 0.03)
    assert payouts.release_units(deal) == 14_550_000


def test_tron_address_validation():
    payouts = importlib.import_module("app.services.payouts")
    assert payouts.is_tron_address(SELLER_W)
    assert not payouts.is_tron_address(SELLER_W[:-1] + ("A" if SELLER_W[-1] != "A" else "B"))
    assert not payouts.is_tron_address("0x" + "1" * 40)
    assert not payouts.is_tron_address("")


# ── seller path ──

@pytest.mark.asyncio
async def test_seller_payout_success(env):
    deal_id, escrow_addr = await env.make_deal(env.S.awaiting_payout)
    resp = await env.seller_wallet(deal_id)
    assert resp.status == "completed" and resp.payout_tx_hash == "txid1"
    assert env.tron.prepared == [(f"enc-{escrow_addr}", SELLER_W, 97_000_000, False)]
    (tx,) = await env.txs(deal_id)
    assert tx.status == env.TS.confirmed and tx.receipt_status == "SUCCESS"
    assert tx.amount_units == 97_000_000 and tx.tx_hash == "txid1" and tx.type == env.TT.release
    assert env.tron.sweeps == [f"enc-{escrow_addr}"]


@pytest.mark.asyncio
async def test_seller_payout_failed_receipt_releases_claim_and_alerts(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    env.tron.default_receipt = {"status": "FAILED", "reason": "OUT_OF_ENERGY"}
    resp = await env.seller_wallet(deal_id)
    assert resp.status == "awaiting_payout" and resp.payout_tx_hash is None
    (tx,) = await env.txs(deal_id)
    assert tx.status == env.TS.failed and tx.receipt_status == "OUT_OF_ENERGY"
    assert any("FAILED" in c.args[0] for c in env.alert.await_args_list)


@pytest.mark.asyncio
async def test_pending_then_success_single_payout(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    env.tron.default_receipt = {"status": "PENDING", "reason": "not found"}
    resp = await env.seller_wallet(deal_id)
    assert resp.status == "payout_in_progress"  # claim kept, NOT back to awaiting_payout
    (tx,) = await env.txs(deal_id)
    assert tx.status == env.TS.pending and tx.tx_hash == "txid1"

    with pytest.raises(HTTPException) as ei:  # retry while pending → 409, nothing sent
        await env.seller_wallet(deal_id)
    assert ei.value.status_code == 409

    await env.reconcile()  # still pending, fresh → untouched
    assert (await env.get(deal_id)).status == env.S.payout_in_progress

    env.tron.default_receipt = {"status": "SUCCESS", "reason": None}
    assert await env.reconcile() == 1
    deal = await env.get(deal_id)
    assert deal.status == env.S.completed and deal.payout_tx_hash == "txid1"
    assert len(env.tron.prepared) == 1 and len(env.tron.broadcasts) == 1


@pytest.mark.asyncio
async def test_broadcast_raised_but_funds_went_no_retry(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    env.tron.broadcast_raises = True
    resp = await env.seller_wallet(deal_id)
    assert resp.status == "completed" and resp.payout_tx_hash == "txid1"
    assert len(env.tron.prepared) == 1 and len(env.tron.broadcasts) == 1


@pytest.mark.asyncio
async def test_broadcast_raised_unknown_keeps_claim_and_no_resend(env):
    deal_id, escrow_addr = await env.make_deal(env.S.awaiting_payout)
    env.tron.broadcast_raises = True
    env.tron.default_receipt = {"status": "PENDING", "reason": "not found"}
    resp = await env.seller_wallet(deal_id)
    assert resp.status == "payout_in_progress"
    # Funds left escrow (tx went through late) → stale reconcile must NOT release the claim.
    env.tron.balances[escrow_addr] = 3_000_000
    later = utcnow_naive() + timedelta(minutes=30)
    await env.reconcile(later)
    assert (await env.get(deal_id)).status == env.S.payout_in_progress
    assert len(env.tron.prepared) == 1


@pytest.mark.asyncio
async def test_concurrent_seller_requests_single_transfer(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    env.tron.prepare_delay = 0.3
    results = await asyncio.gather(env.seller_wallet(deal_id), env.seller_wallet(deal_id), return_exceptions=True)
    assert len(env.tron.prepared) == 1
    errors = [r for r in results if isinstance(r, HTTPException)]
    assert len(errors) == 1 and errors[0].status_code in (400, 409)
    assert (await env.get(deal_id)).status == env.S.completed


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["invalid", "master", "escrow", "own_escrow"])
async def test_bad_destination_rejected_nothing_sent(env, kind):
    deal_id, escrow_addr = await env.make_deal(env.S.awaiting_payout)
    other_id, other_escrow = await env.make_deal(env.S.cancelled)
    wallet = {
        "invalid": "T" + "1" * 33, "master": MASTER, "escrow": other_escrow, "own_escrow": escrow_addr,
    }[kind]
    with pytest.raises(HTTPException) as ei:
        await env.seller_wallet(deal_id, wallet)
    assert ei.value.status_code == 400
    assert env.tron.prepared == [] and await env.txs(deal_id) == []
    assert (await env.get(deal_id)).status == env.S.awaiting_payout


@pytest.mark.asyncio
@pytest.mark.parametrize("balance", [RuntimeError("429"), 50_000_000])
async def test_unknown_or_insufficient_balance_refused(env, balance):
    deal_id, escrow_addr = await env.make_deal(env.S.awaiting_payout)
    env.tron.balances[escrow_addr] = balance
    resp = await env.seller_wallet(deal_id)
    assert resp.status == "awaiting_payout"
    assert env.tron.prepared == [] and await env.txs(deal_id) == []
    assert any("REFUSED" in c.args[0] for c in env.alert.await_args_list)


# ── admin resolve / cancel ──

@pytest.mark.asyncio
async def test_admin_refund_buyer_full_amount_cancelled(env):
    deal_id, _ = await env.make_deal(env.S.disputed)
    resp = await env.resolve(deal_id, "refund_buyer")
    assert resp.status == "cancelled" and resp.payout_tx_hash == "txid1"
    assert env.tron.prepared[0][1:3] == (BUYER_W, 100_000_000)
    (tx,) = await env.txs(deal_id)
    assert tx.type == env.TT.refund and tx.status == env.TS.confirmed


@pytest.mark.asyncio
async def test_admin_release_seller_completed_and_channel_sold(env):
    deal_id, _ = await env.make_deal(env.S.disputed)
    resp = await env.resolve(deal_id, "release_seller")
    assert resp.status == "completed"
    assert env.tron.prepared[0][1:3] == (SELLER_W, 97_000_000)
    async with env.orm.session() as db:
        assert (await db.get(env.Channel, env.ids.channel)).status == env.CS.sold


@pytest.mark.asyncio
async def test_admin_resolve_pending_keeps_claim(env):
    deal_id, _ = await env.make_deal(env.S.disputed)
    env.tron.default_receipt = {"status": "PENDING", "reason": "not found"}
    with pytest.raises(HTTPException) as ei:
        await env.resolve(deal_id, "refund_buyer")
    assert ei.value.status_code == 202
    assert (await env.get(deal_id)).status == env.S.payout_in_progress  # NOT disputed


@pytest.mark.asyncio
async def test_admin_resolve_failed_restores_disputed(env):
    deal_id, _ = await env.make_deal(env.S.disputed)
    env.tron.default_receipt = {"status": "FAILED", "reason": "OUT_OF_ENERGY"}
    with pytest.raises(HTTPException) as ei:
        await env.resolve(deal_id, "release_seller")
    assert ei.value.status_code == 502 and "OUT_OF_ENERGY" in ei.value.detail
    assert (await env.get(deal_id)).status == env.S.disputed


@pytest.mark.asyncio
async def test_admin_resolve_rejects_master_wallet(env):
    deal_id, _ = await env.make_deal(env.S.disputed)
    with pytest.raises(HTTPException) as ei:
        await env.resolve(deal_id, "refund_buyer", wallet=MASTER)
    assert ei.value.status_code == 400 and env.tron.prepared == []


@pytest.mark.asyncio
async def test_cancel_during_payout_in_progress_409(env):
    deal_id, _ = await env.make_deal(env.S.payout_in_progress)
    with pytest.raises(HTTPException) as ei:
        await env.call(env.admin.admin_cancel_deal, deal_id)
    assert ei.value.status_code == 409 and env.tron.prepared == []
    assert (await env.get(deal_id)).status == env.S.payout_in_progress


@pytest.mark.asyncio
async def test_cancel_funded_refunds_then_cancelled(env):
    deal_id, _ = await env.make_deal(env.S.paid)
    resp = await env.call(env.admin.admin_cancel_deal, deal_id)
    assert resp.status == "cancelled" and resp.payout_tx_hash == "txid1"
    assert env.tron.prepared[0][1:3] == (BUYER_W, 100_000_000)


@pytest.mark.asyncio
async def test_cancel_funded_failed_restores_status(env):
    deal_id, _ = await env.make_deal(env.S.paid)
    env.tron.default_receipt = {"status": "FAILED", "reason": "REVERT"}
    with pytest.raises(HTTPException) as ei:
        await env.call(env.admin.admin_cancel_deal, deal_id)
    assert ei.value.status_code == 502
    assert (await env.get(deal_id)).status == env.S.paid


# ── sweep endpoint guards ──

@pytest.mark.asyncio
async def test_sweep_only_cancelled_and_not_to_master(env):
    deal_id, _ = await env.make_deal(env.S.completed, payout_tx_hash="x")
    r = await env.call(env.admin.sweep_escrow_wallet, deal_id, to_address=BUYER_W)
    assert r["ok"] is False and "cancelled" in r["error"]
    c_id, _ = await env.make_deal(env.S.cancelled)
    r = await env.call(env.admin.sweep_escrow_wallet, c_id, to_address=MASTER)
    assert r["ok"] is False and "master" in r["error"]
    assert env.tron.prepared == []
    r = await env.call(env.admin.sweep_escrow_wallet, c_id, to_address=BUYER_W)
    assert r["ok"] is True
    (tx,) = await env.txs(c_id)
    assert tx.type == env.TT.sweep and (await env.get(c_id)).status == env.S.cancelled


# ── collect fee ──

@pytest.mark.asyncio
async def test_collect_fee_after_confirmed_release(env):
    deal_id, escrow_addr = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    env.tron.balances[escrow_addr] = 3_000_000  # fee left on escrow
    r = await env.call(env.admin.collect_fee, deal_id)
    assert r["ok"] is True and r["amount_usdt"] == 3.0
    assert env.tron.prepared[-1][1:] == (MASTER, 3_000_000, True)
    fee_tx = (await env.txs(deal_id))[-1]
    assert fee_tx.type == env.TT.fee_collection and fee_tx.status == env.TS.confirmed
    assert (await env.get(deal_id)).status == env.S.completed

    with pytest.raises(HTTPException) as ei:  # only once
        await env.call(env.admin.collect_fee, deal_id)
    assert ei.value.status_code == 409

    stats = await env.call(env.admin.admin_dashboard_stats)
    assert stats["fee_accrued"] == 3.0 and stats["fee_collected"] == 3.0


@pytest.mark.asyncio
async def test_collect_fee_refused_for_legacy_cancelled_and_open(env):
    # legacy completed: confirmed release without receipt_status → refused
    legacy_id, _ = await env.make_deal(env.S.completed, payout_tx_hash="legacy")
    async with env.orm.session() as db:
        db.add(env.Tx(deal_id=legacy_id, tx_hash="legacy", amount=97.0, type=env.TT.release,
                      status=env.TS.confirmed))
        await db.commit()
    for did in (legacy_id, (await env.make_deal(env.S.cancelled))[0], (await env.make_deal(env.S.disputed))[0]):
        with pytest.raises(HTTPException) as ei:
            await env.call(env.admin.collect_fee, did)
        assert ei.value.status_code == 400
    assert env.tron.prepared == []


@pytest.mark.asyncio
async def test_collect_fee_refused_with_open_tx(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    async with env.orm.session() as db:
        db.add(env.Tx(deal_id=deal_id, tx_hash="other", amount=1.0, type=env.TT.sweep, status=env.TS.pending))
        await db.commit()
    with pytest.raises(HTTPException) as ei:
        await env.call(env.admin.collect_fee, deal_id)
    assert ei.value.status_code == 409


# ── restart recovery ──

@pytest.mark.asyncio
async def test_restart_stale_pending_not_on_chain_releases_claim_no_resend(env):
    deal_id, escrow_addr = await env.make_deal(env.S.payout_in_progress)
    old = utcnow_naive() - timedelta(hours=1)
    async with env.orm.session() as db:
        db.add(env.Tx(deal_id=deal_id, tx_hash="lost", amount=97.0, amount_units=97_000_000,
                      from_address=escrow_addr, to_address=SELLER_W, type=env.TT.release,
                      status=env.TS.pending, restore_status="awaiting_payout", broadcast_at=old))
        await env_commit(db)
    env.tron.default_receipt = {"status": "PENDING", "reason": "not found"}
    await env.reconcile()
    assert (await env.get(deal_id)).status == env.S.awaiting_payout
    (tx,) = await env.txs(deal_id)
    assert tx.status == env.TS.failed and tx.receipt_status == "EXPIRED_NOT_ON_CHAIN"
    assert env.tron.prepared == [] and env.tron.broadcasts == []


@pytest.mark.asyncio
async def test_restart_payout_in_progress_without_tx_alert_only(env):
    deal_id, _ = await env.make_deal(env.S.payout_in_progress)
    await env.reconcile()
    await env.reconcile()
    assert (await env.get(deal_id)).status == env.S.payout_in_progress
    stuck = [c for c in env.alert.await_args_list if "stuck" in c.args[0]]
    assert len(stuck) == 1 and env.tron.prepared == []


@pytest.mark.asyncio
async def test_payment_checker_runs_reconcile(env, monkeypatch):
    called = AsyncMock(return_value=0)
    monkeypatch.setattr(env.payouts, "reconcile_pending_transfers", called)
    monkeypatch.setattr(env.pc, "LATE_PAYMENT_CHECK_EVERY_N_CYCLES", 10**9)
    monkeypatch.setattr(env.pc, "_cycle", 1)
    await env.pc.check_payments_once()
    assert called.await_count == 1


async def env_commit(db):
    await db.commit()
