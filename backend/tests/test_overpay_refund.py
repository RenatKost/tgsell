"""Task 14 PR A: overpay refund to buyer-entered address after seller payout."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.test_unified_payouts import BUYER_W, SELLER_W, env  # noqa: F401


async def _set(env, deal_id, **values):
    async with env.orm.session() as db:
        d = await db.get(env.Deal, deal_id)
        for k, v in values.items():
            setattr(d, k, v)
        await db.commit()


async def _addr(env, deal_id, wallet, user=None):
    from app.schemas.deal import OverpayRefundAddressRequest

    return await env.call(env.deals.set_overpay_refund_address, deal_id,
                          OverpayRefundAddressRequest(wallet_address=wallet),
                          user=user or env.ids.buyer, run_worker=False)


async def _overpaid(env, over_units=2_000_000):
    deal_id, addr = await env.make_deal(env.S.awaiting_payout)
    env.tron.balances[addr] += over_units
    await _set(env, deal_id, overpay_units=over_units, overpay_status="awaiting_address")
    return deal_id, addr


@pytest.mark.asyncio
async def test_refund_after_payout_to_buyer_address(env):
    deal_id, addr = await _overpaid(env)
    r = await _addr(env, deal_id, BUYER_W)
    assert r["overpay_status"] == "awaiting_address"  # payout not done yet → waits
    resp = await env.seller_wallet(deal_id)  # release + worker (refund queued inside success)
    assert resp.status == "completed"
    await env.work()  # worker runs the queued overpay refund
    txs = await env.txs(deal_id)
    rel = [t for t in txs if t.type == env.TT.release]
    ref = [t for t in txs if t.type == env.TT.overpay_refund]
    assert rel[0].amount_units == 97_000_000  # 3% fee from price only
    assert len(ref) == 1 and ref[0].to_address == BUYER_W and ref[0].amount_units == 2_000_000
    assert ref[0].status == env.TS.confirmed
    d = await env.get(deal_id)
    assert d.overpay_status == "done"
    # sweep only once, after the refund (TRX kept for it after the release)
    assert env.tron.sweeps == [f"enc-{addr}"]
    for _ in range(3):
        await env.work()
    assert len([t for t in await env.txs(deal_id) if t.type == env.TT.overpay_refund]) == 1
    with pytest.raises(HTTPException):
        await _addr(env, deal_id, BUYER_W)


@pytest.mark.asyncio
async def test_refund_waits_without_address_then_fires_on_entry(env):
    deal_id, _ = await _overpaid(env)
    await env.seller_wallet(deal_id)
    await env.work()
    assert not [t for t in await env.txs(deal_id) if t.type == env.TT.overpay_refund]
    assert (await env.get(deal_id)).overpay_status == "awaiting_address"
    r = await _addr(env, deal_id, BUYER_W)
    assert r["overpay_status"] == "queued"
    await env.work()
    (ref,) = [t for t in await env.txs(deal_id) if t.type == env.TT.overpay_refund]
    assert ref.status == env.TS.confirmed and ref.to_address == BUYER_W


@pytest.mark.asyncio
async def test_address_validation_and_only_buyer(env):
    deal_id, addr = await _overpaid(env)
    for bad in ("Txxx", BUYER_W[:-1] + ("A" if BUYER_W[-1] != "A" else "B"), addr):
        with pytest.raises(HTTPException) as e:
            await _addr(env, deal_id, bad)
        assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        await _addr(env, deal_id, BUYER_W, user=env.ids.seller)
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_legacy_completed_deal_never_refunds(env):
    """#29-like: completed deal with stray USDT but no recorded overpay (pre-migration)."""
    deal_id, addr = await env.make_deal(env.S.awaiting_payout)
    env.tron.balances[addr] += 2_300_000
    await env.seller_wallet(deal_id)
    for _ in range(3):
        await env.work()
    assert not [t for t in await env.txs(deal_id) if t.type == env.TT.overpay_refund]
    with pytest.raises(HTTPException):
        await _addr(env, deal_id, BUYER_W)
    d = await env.get(deal_id)
    assert d.overpay_units is None and d.overpay_status is None


@pytest.mark.asyncio
async def test_failed_refund_not_retried(env):
    deal_id, _ = await _overpaid(env)
    await _addr(env, deal_id, BUYER_W)
    await env.seller_wallet(deal_id)
    env.tron.default_receipt = {"status": "FAILED", "reason": "OUT_OF_ENERGY"}
    await env.work()
    for _ in range(2):
        await env.work()
    refs = [t for t in await env.txs(deal_id) if t.type == env.TT.overpay_refund]
    assert len(refs) == 1 and refs[0].status == env.TS.failed
    d = await env.get(deal_id)
    assert d.overpay_status == "failed" and d.status == env.S.completed
