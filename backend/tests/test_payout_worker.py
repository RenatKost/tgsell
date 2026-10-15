"""PR B: background payout worker, advisory-lock leadership, restart recovery,
pre-claim master TRX check, None TRX balance, master balance endpoint, 202 + polling.

Real Postgres, TRON mocked (fixture `env` from test_unified_payouts).
"""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.utils.timeutil import utcnow_naive
from tests.test_unified_payouts import BUYER_W, MASTER, SELLER_W, env  # noqa: F401


# ── claim + enqueue (HTTP) ──

@pytest.mark.asyncio
async def test_seller_returns_202_with_claim_and_job_in_one_commit(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    resp = await env.seller_wallet(deal_id, run_worker=False)
    assert resp.http == 202 and resp.status == "payout_in_progress"
    (job,) = await env.txs(deal_id)
    assert job.status == env.TS.pending and job.tx_hash is None and job.amount_units == 97_000_000
    assert env.tron.prepared == []  # HTTP did not touch the chain

    async with env.orm.session() as db:  # polling endpoint
        deal = await db.get(env.Deal, deal_id)
        st = await env.payouts.payout_status(db, deal)
    assert st["in_progress"] and st["last_transfer"]["state"] == "queued"

    await env.work()
    async with env.orm.session() as db:
        deal = await db.get(env.Deal, deal_id)
        st = await env.payouts.payout_status(db, deal)
    assert st["deal_status"] == "completed" and st["last_transfer"]["state"] == "confirmed"
    assert not st["in_progress"]


@pytest.mark.asyncio
async def test_seller_payout_status_endpoint_forbidden_for_others(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    async with env.orm.session() as db:
        with pytest.raises(HTTPException) as ei:
            await env.deals.get_payout_status(deal_id, user=SimpleNamespace(id=999_999), db=db)
    assert ei.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["MASTER_INSUFFICIENT_TRX", "TRX_BALANCE_UNKNOWN"])
async def test_insufficient_or_unknown_master_trx_no_claim(env, reason):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    env.tron.gas_result = {"ok": False, "reason": reason, "message": "Master: 8.64 TRX, потрібно ≈18.9"}
    with pytest.raises(HTTPException) as ei:
        await env.seller_wallet(deal_id)
    assert ei.value.status_code == 503 and "TRX" in ei.value.detail
    assert (await env.get(deal_id)).status == env.S.awaiting_payout
    assert await env.txs(deal_id) == [] and env.tron.prepared == []
    keys = [c.kwargs.get("alert_key") for c in env.alert.await_args_list]
    assert f"master_trx_{reason}" in keys  # throttled by key


@pytest.mark.asyncio
async def test_admin_resolve_insufficient_master_trx_stays_disputed(env):
    deal_id, _ = await env.make_deal(env.S.disputed)
    env.tron.gas_result = {"ok": False, "reason": "MASTER_INSUFFICIENT_TRX", "message": "low"}
    with pytest.raises(HTTPException) as ei:
        await env.resolve(deal_id, "refund_buyer")
    assert ei.value.status_code == 503
    assert (await env.get(deal_id)).status == env.S.disputed and await env.txs(deal_id) == []


# ── worker leadership (deploy overlap) ──

@pytest.mark.asyncio
async def test_two_workers_only_one_leader(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id, run_worker=False)
    w1, w2 = env.new_worker(), env.new_worker()
    assert await w1.acquire() is True
    assert await w2.acquire() is False
    assert (await w2.run_once()) == {"leader": False}
    assert env.tron.prepared == []
    await w1.run_once()
    assert len(env.tron.prepared) == 1
    await w1.release()
    assert await w2.acquire() is True
    await w2.run_once()  # nothing left, no resend
    assert len(env.tron.prepared) == 1
    assert (await env.get(deal_id)).status == env.S.completed


@pytest.mark.asyncio
async def test_leader_keeps_lock_across_cycles(env):
    w = env.new_worker()
    assert await w.acquire() and await w.acquire()  # re-check keeps leadership


# ── restart recovery ──

@pytest.mark.asyncio
async def test_restart_recovers_queued_job_never_broadcast(env):
    """Crash right after claim+enqueue: new worker processes the job exactly once."""
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id, run_worker=False)  # "crash" before worker ran
    await env.work()  # fresh worker after restart
    await env.work()
    assert len(env.tron.prepared) == 1 and len(env.tron.broadcasts) == 1
    assert (await env.get(deal_id)).status == env.S.completed


@pytest.mark.asyncio
async def test_restart_after_txid_persisted_uses_receipt_no_resend(env):
    """Crash after txid was saved (maybe broadcast): recovery by receipt, never resend."""
    deal_id, escrow_addr = await env.make_deal(env.S.payout_in_progress)
    async with env.orm.session() as db:
        db.add(env.Tx(deal_id=deal_id, tx_hash="saved", amount=97.0, amount_units=97_000_000,
                      from_address=escrow_addr, to_address=SELLER_W, type=env.TT.release,
                      status=env.TS.pending, restore_status="awaiting_payout",
                      broadcast_at=utcnow_naive()))
        await db.commit()
    env.tron.receipts["saved"] = [{"status": "SUCCESS", "reason": None}]
    await env.work()
    deal = await env.get(deal_id)
    assert deal.status == env.S.completed and deal.payout_tx_hash == "saved"
    assert env.tron.prepared == [] and env.tron.broadcasts == []


@pytest.mark.asyncio
async def test_restart_txid_persisted_failed_receipt_releases_claim(env):
    deal_id, escrow_addr = await env.make_deal(env.S.payout_in_progress)
    async with env.orm.session() as db:
        db.add(env.Tx(deal_id=deal_id, tx_hash="bad", amount=97.0, amount_units=97_000_000,
                      from_address=escrow_addr, to_address=SELLER_W, type=env.TT.release,
                      status=env.TS.pending, restore_status="awaiting_payout",
                      broadcast_at=utcnow_naive()))
        await db.commit()
    env.tron.receipts["bad"] = [{"status": "FAILED", "reason": "OUT_OF_ENERGY"}]
    await env.work()
    assert (await env.get(deal_id)).status == env.S.awaiting_payout
    assert env.tron.prepared == []


@pytest.mark.asyncio
async def test_restart_legacy_payout_in_progress_without_job_alert_only(env):
    deal_id, _ = await env.make_deal(env.S.payout_in_progress)
    await env.work()
    await env.work()
    assert (await env.get(deal_id)).status == env.S.payout_in_progress
    assert env.tron.prepared == []
    assert len([c for c in env.alert.await_args_list if "stuck" in c.args[0]]) == 1


@pytest.mark.asyncio
async def test_queued_job_not_stale_failed_by_reconcile(env):
    """Reconcile must leave never-broadcast jobs to the worker (no stale-fail)."""
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id, run_worker=False)
    await env.reconcile(utcnow_naive() + timedelta(hours=2))
    (job,) = await env.txs(deal_id)
    assert job.status == env.TS.pending
    await env.work()
    assert (await env.get(deal_id)).status == env.S.completed


@pytest.mark.asyncio
async def test_sweep_and_collect_fee_are_queued(env):
    deal_id, escrow_addr = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    env.tron.balances[escrow_addr] = 3_000_000
    r = await env.call(env.admin.collect_fee, deal_id, run_worker=False)
    assert r["http"] == 202 and r["status"] == "queued" and env.tron.prepared[-1][1] == SELLER_W
    await env.work()
    from app.config import settings
    assert env.tron.prepared[-1][1:] == (settings.treasury_address, 3_000_000, False)


# ── TRX balances ──

def test_get_trx_balance_none_on_error(monkeypatch):
    escrow = importlib.import_module("app.services.escrow")

    def boom():
        raise RuntimeError("429")

    monkeypatch.setattr(escrow, "_get_tron_client", boom)
    assert escrow.get_trx_balance(MASTER) is None
    assert escrow.get_trx_balance("") is None


def test_check_gas_funding_unknown_on_error(monkeypatch):
    escrow = importlib.import_module("app.services.escrow")

    def boom(*a, **k):
        raise RuntimeError("TronGrid down")

    monkeypatch.setattr(escrow, "_get_tron_client", lambda: SimpleNamespace())
    monkeypatch.setattr(escrow, "estimate_usdt_transfer_cost_sun", boom)
    r = escrow.check_gas_funding(SELLER_W, BUYER_W, 1)
    assert r["ok"] is False and r["reason"] == "TRX_BALANCE_UNKNOWN"


def test_check_gas_funding_insufficient_and_ok(monkeypatch):
    escrow = importlib.import_module("app.services.escrow")
    bal = {SELLER_W: 0, MASTER: 8_640_000}
    monkeypatch.setattr(escrow.settings, "tron_master_wallet_address", MASTER)
    monkeypatch.setattr(escrow, "_get_tron_client", lambda: SimpleNamespace())
    monkeypatch.setattr(escrow, "estimate_usdt_transfer_cost_sun",
                        lambda *a, **k: {"required_sun": 17_400_000, "fee_limit_sun": 30_000_000})
    monkeypatch.setattr(escrow, "_account_balance_sun", lambda c, a: bal[a])
    r = escrow.check_gas_funding(SELLER_W, BUYER_W, 1)
    assert r["ok"] is False and r["reason"] == "MASTER_INSUFFICIENT_TRX"
    assert r["need_sun"] == 17_400_000 + escrow.MASTER_TRANSFER_RESERVE_SUN
    bal[MASTER] = 50_000_000
    assert escrow.check_gas_funding(SELLER_W, BUYER_W, 1)["ok"] is True
    bal[SELLER_W] = 20_000_000  # escrow already funded → master not needed
    bal[MASTER] = 0
    assert escrow.check_gas_funding(SELLER_W, BUYER_W, 1)["ok"] is True


@pytest.mark.asyncio
async def test_master_balance_endpoint_low_alert_and_unknown(env, monkeypatch):
    escrow = env.payouts.escrow_svc
    monkeypatch.setattr(escrow, "get_trx_balance", lambda a: 8.64)
    r = await env.admin.master_wallet_balance(admin=None)
    assert r["trx"] == 8.64 and r["low"] is True and r["threshold"] == 30.0
    assert any(c.kwargs.get("alert_key") == "master_trx_low" for c in env.alert.await_args_list)
    env.alert.reset_mock()
    monkeypatch.setattr(escrow, "get_trx_balance", lambda a: None)
    r = await env.admin.master_wallet_balance(admin=None)
    assert r["trx"] is None and r["unknown"] is True and r["low"] is False
    assert env.alert.await_count == 0


@pytest.mark.asyncio
async def test_overlap_old_release_inflight_row_not_picked_by_worker(env):
    """A pending row without txid and without the QUEUED marker belongs to an in-flight
    synchronous attempt of the previous release (deploy overlap): the worker never takes
    it; only when stale (never broadcast) it is failed and the claim released."""
    deal_id, escrow_addr = await env.make_deal(env.S.payout_in_progress)
    async with env.orm.session() as db:
        db.add(env.Tx(deal_id=deal_id, tx_hash=None, amount=97.0, amount_units=97_000_000,
                      from_address=escrow_addr, to_address=SELLER_W, type=env.TT.release,
                      status=env.TS.pending, restore_status="awaiting_payout"))
        await db.commit()
    await env.work()
    assert env.tron.prepared == []
    assert (await env.get(deal_id)).status == env.S.payout_in_progress
    await env.reconcile(utcnow_naive() + timedelta(minutes=30))
    (tx,) = await env.txs(deal_id)
    assert tx.status == env.TS.failed and tx.receipt_status == "NEVER_BROADCAST"
    assert (await env.get(deal_id)).status == env.S.awaiting_payout and env.tron.prepared == []


@pytest.mark.asyncio
async def test_worker_crash_mid_prepare_recovered_without_resend(env, monkeypatch):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id, run_worker=False)
    env.tron.prepare_raises = SystemError("worker killed")  # crash inside prepare
    await env.work()
    env.tron.prepare_raises = None
    (tx,) = await env.txs(deal_id)
    # prepare raised → handled as refused (nothing broadcast), claim released
    assert tx.status == env.TS.failed and env.tron.broadcasts == []
    assert (await env.get(deal_id)).status == env.S.awaiting_payout
