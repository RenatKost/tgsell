"""Task 19: automatic fee sweep to TREASURY_ADDRESS (TRON fully mocked, no mainnet)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.test_unified_payouts import BUYER_W, MASTER, env  # noqa: F401

TREASURY = "TXoRpYu5FDgZvrqNQb239bLjcc5oHzavCG"


@pytest.fixture
def on(env, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "fee_sweep_enabled", True)
    orig = env.tron.broadcast

    def broadcast(prepared):  # model the chain: funds leave the escrow on broadcast
        enc, to, units, _ = next(p for p in env.tron.prepared if f"txid{env.tron.prepared.index(p) + 1}" == prepared["txid"])
        addr = enc.removeprefix("enc-")
        env.tron.balances[addr] = env.tron.balances.get(addr, 0) - units
        return orig(prepared)

    env.tron.broadcast = broadcast
    import importlib
    monkeypatch.setattr(importlib.import_module("app.services.escrow"), "broadcast_prepared", broadcast)
    return env


def _sweeps(txs, env):
    return [t for t in txs if t.type == env.TT.fee_sweep]


@pytest.mark.asyncio
async def test_treasury_default_is_valid_tron_address(env):  # env: isolated module imports
    from app.config import settings
    from app.services import fee_sweep, payouts

    assert settings.treasury_address == TREASURY
    assert payouts.is_tron_address(TREASURY)
    assert fee_sweep.treasury_address() == TREASURY
    assert settings.fee_sweep_min_usdt == 5.0


@pytest.mark.asyncio
async def test_invalid_treasury_refused(env, monkeypatch):
    from app.config import settings
    from app.services import fee_sweep

    monkeypatch.setattr(settings, "treasury_address", "TXoRpYu5FDgZvrqNQb239bLjcc5oHzavCX")
    with pytest.raises(fee_sweep.FeeSweepError):
        fee_sweep.treasury_address()


@pytest.mark.asyncio
async def test_auto_sweep_after_payout_above_min(on):
    env = on
    deal_id, addr = await env.make_deal(env.S.awaiting_payout, amount=200.0, fee=6.0)
    await env.seller_wallet(deal_id)  # release + schedule (6 USDT left ≥ 5) → queued
    await env.work()  # sweep executed
    d = await env.get(deal_id)
    assert d.status == env.S.completed and d.sweep_status == "done"
    sw = _sweeps(await env.txs(deal_id), env)
    assert len(sw) == 1 and sw[0].to_address == TREASURY and sw[0].amount_units == 6_000_000
    assert sw[0].status == env.TS.confirmed and sw[0].from_address == addr
    assert env.tron.balances[addr] == 0
    for _ in range(3):  # idempotent
        await env.work()
    assert len(_sweeps(await env.txs(deal_id), env)) == 1
    # TRX swept back only after the fee sweep (not after the release)
    assert env.tron.sweeps == [f"enc-{addr}"]


@pytest.mark.asyncio
async def test_below_min_stays_pending_then_collect_all(on):
    env = on
    deal_id, addr = await env.make_deal(env.S.awaiting_payout)  # fee 3 < 5
    await env.seller_wallet(deal_id)
    await env.work()
    d = await env.get(deal_id)
    assert d.sweep_status == "pending_sweep" and env.tron.balances[addr] == 3_000_000
    assert _sweeps(await env.txs(deal_id), env) == []
    r = await env.call(env.admin.fee_sweep_collect_all, run_worker=False)
    assert r["http"] == 202 and r["queued"] == 1 and r["treasury"] == TREASURY
    await env.work()
    sw = _sweeps(await env.txs(deal_id), env)
    assert len(sw) == 1 and sw[0].to_address == TREASURY and sw[0].status == env.TS.confirmed
    assert (await env.get(deal_id)).sweep_status == "done"
    r = await env.call(env.admin.fee_sweep_collect_all)
    assert r["queued"] == 0


@pytest.mark.asyncio
async def test_sweep_after_overpay_refund_only(on):
    env = on
    deal_id, addr = await env.make_deal(env.S.awaiting_payout, amount=200.0, fee=6.0)
    env.tron.balances[addr] += 2_000_000
    async with env.orm.session() as db:
        d = await db.get(env.Deal, deal_id)
        d.overpay_units, d.overpay_status, d.overpay_refund_address = 2_000_000, "awaiting_address", BUYER_W
        await db.commit()
    await env.seller_wallet(deal_id)
    assert (await env.get(deal_id)).sweep_status is None  # overpay refund still open
    await env.work()  # overpay refund
    await env.work()  # schedule
    await env.work()  # sweep
    txs = await env.txs(deal_id)
    types = [t.type for t in txs]
    assert types.index(env.TT.overpay_refund) < types.index(env.TT.fee_sweep)
    assert _sweeps(txs, env)[0].amount_units == 6_000_000


@pytest.mark.asyncio
async def test_legacy_deals_excluded(on):
    from app.services import fee_sweep

    env = on
    assert {3, 29} <= fee_sweep.EXCLUDED_DEAL_IDS and 6 in fee_sweep.EXCLUDED_DEAL_IDS
    async with env.orm.session() as db:
        d = await db.get(env.Deal, (await env.make_deal(env.S.completed, payout_tx_hash="h"))[0])
        assert fee_sweep.quick_eligible(d) is True
        d.id = 29
        assert fee_sweep.quick_eligible(d) is False
        assert fee_sweep.mark_due(d) is False
        assert "Ренатом" in (await fee_sweep.check_eligible(db, d))
        await db.rollback()


@pytest.mark.asyncio
async def test_worker_refuses_non_treasury_fee_sweep(on):
    env = on
    deal_id, _ = await env.make_deal(env.S.completed, payout_tx_hash="x")
    async with env.orm.session() as db:
        db.add(env.Tx(deal_id=deal_id, amount=3.0, amount_units=3_000_000, type=env.TT.fee_sweep,
                      status=env.TS.pending, receipt_status="QUEUED", to_address=MASTER))
        await db.commit()
    await env.work()
    sw = _sweeps(await env.txs(deal_id), env)
    assert sw[0].status == env.TS.failed and sw[0].receipt_status == "SWEEP_FORBIDDEN"
    assert env.tron.prepared == []


@pytest.mark.asyncio
async def test_no_sweep_from_open_or_unconfirmed(on):
    env = on
    for st in (env.S.disputed, env.S.cancelled, env.S.awaiting_payout):
        did, _ = await env.make_deal(st)
        with pytest.raises(HTTPException) as ei:
            await env.call(env.admin.collect_fee, did)
        assert ei.value.status_code == 400
    assert env.tron.prepared == []


@pytest.mark.asyncio
async def test_failed_sweep_marked_failed_no_retry(on):
    env = on
    deal_id, addr = await env.make_deal(env.S.awaiting_payout, amount=200.0, fee=6.0)
    await env.seller_wallet(deal_id)
    env.tron.default_receipt = {"status": "FAILED", "reason": "OUT_OF_ENERGY"}
    await env.work()
    assert (await env.get(deal_id)).sweep_status == "failed"
    for _ in range(2):
        await env.work()
    assert len(_sweeps(await env.txs(deal_id), env)) == 1


@pytest.mark.asyncio
async def test_overview_money_block(on):
    env = on
    deal_id, _ = await env.make_deal(env.S.awaiting_payout, amount=200.0, fee=6.0)
    await env.seller_wallet(deal_id)
    await env.work()
    import importlib
    am = importlib.import_module("app.routers.admin_money")

    async def fake_balances(**kw):
        return {"wallets_with_funds": [], "unknown": [], "checked_count": 1}

    import app.routers.admin as adm
    orig = adm.check_escrow_balances
    adm.check_escrow_balances = fake_balances
    try:
        r = await env.call(am.escrow_overview, refresh=False, run_worker=False)
    finally:
        adm.check_escrow_balances = orig
    assert r["treasury_address"] == TREASURY
    assert r["totals"]["treasury_sent"] == 6.0 and r["totals"]["earned"] == 6.0
    assert r["treasury_txs"][0]["tronscan_url"]
