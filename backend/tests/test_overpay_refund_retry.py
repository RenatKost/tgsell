"""Task 15 item 4: admin-manual retry of a FAILED overpay refund + ledger visibility."""
from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from tests.test_overpay_refund import _addr, _overpaid
from tests.test_unified_payouts import BUYER_W, env  # noqa: F401


def _am():
    return importlib.import_module("app.routers.admin_money")


async def _failed(env):
    deal_id, addr = await _overpaid(env)
    await _addr(env, deal_id, BUYER_W)
    await env.seller_wallet(deal_id)
    env.tron.default_receipt = {"status": "FAILED", "reason": "OUT_OF_ENERGY"}
    await env.work()
    assert (await env.get(deal_id)).overpay_status == "failed"
    env.tron.default_receipt = {"status": "SUCCESS", "reason": None}
    return deal_id, addr


def _refs(txs, env):
    return [t for t in txs if t.type == env.TT.overpay_refund]


@pytest.mark.asyncio
async def test_retry_requeues_once_and_succeeds(env):
    from app.models.user import AdminAuditLog

    deal_id, _ = await _failed(env)
    r = await env.call(_am().retry_overpay_refund, deal_id, run_worker=False)
    assert r["status"] == "queued" and r["http"] == 202 and r["amount_usdt"] == 2.0
    # second click while queued → refused, no second job
    with pytest.raises(HTTPException) as e:
        await env.call(_am().retry_overpay_refund, deal_id, run_worker=False)
    assert e.value.status_code == 409
    assert len(_refs(await env.txs(deal_id), env)) == 2  # failed + one new
    await env.work()
    refs = _refs(await env.txs(deal_id), env)
    assert [t.status for t in refs] == [env.TS.failed, env.TS.confirmed]
    assert refs[1].to_address == BUYER_W and refs[1].amount_units == 2_000_000
    assert (await env.get(deal_id)).overpay_status == "done"
    # after success → refused, still exactly one confirmed
    with pytest.raises(HTTPException) as e:
        await env.call(_am().retry_overpay_refund, deal_id, run_worker=False)
    assert e.value.status_code == 409
    for _ in range(2):
        await env.work()
    assert len(_refs(await env.txs(deal_id), env)) == 2
    async with env.orm.session() as db:
        logs = (await db.execute(select(AdminAuditLog).where(
            AdminAuditLog.action == "deal.overpay_refund_retry"))).scalars().all()
    assert len(logs) == 1 and logs[0].target_id == deal_id


@pytest.mark.asyncio
async def test_retry_refused_unless_failed(env):
    deal_id, _ = await _overpaid(env)  # awaiting_address
    with pytest.raises(HTTPException) as e:
        await env.call(_am().retry_overpay_refund, deal_id, run_worker=False)
    assert e.value.status_code == 409
    # legacy/no-overpay deal (#29/#3-like)
    plain, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(plain)
    with pytest.raises(HTTPException) as e:
        await env.call(_am().retry_overpay_refund, plain, run_worker=False)
    assert e.value.status_code == 400
    assert not _refs(await env.txs(plain), env)
    assert not _refs(await env.txs(deal_id), env)


@pytest.mark.asyncio
async def test_no_automatic_retry_and_listing(env):
    deal_id, _ = await _failed(env)
    for _ in range(3):
        await env.work()
    assert len(_refs(await env.txs(deal_id), env)) == 1
    async with env.orm.session() as db:
        lst = await _am().list_overpay_refunds(admin=None, db=db)
    (item,) = [i for i in lst["items"] if i["deal_id"] == deal_id]
    assert item["overpay_status"] == "failed" and item["retry_allowed"] is True
    assert item["transactions"][0]["type"] == "overpay_refund"
