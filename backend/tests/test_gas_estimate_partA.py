"""Task 17 Part A: energy-aware gas top-up, fail-fast before broadcast, receipt cost
logging, and the scoped data fix for deal #29 (migration 0035). TronGrid fully mocked."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest
from sqlalchemy import select, text

from tests.test_escrow_payout import ESCROW, RECEIVER, env  # noqa: F401  (fixture)


# ── estimate ──

def _with_resources(chain, energy_limit=0, energy_used=0):
    orig = chain.make_request

    def mr(method, params=None):
        if method == "wallet/getaccountresource":
            chain.requests.append(method)
            return {"EnergyLimit": energy_limit, "EnergyUsed": energy_used}
        return orig(method, params)
    chain.make_request = mr


def test_low_api_estimate_for_empty_receiver_is_floored_to_new_slot(env):
    env.chain.estimate = 64_000          # estimate ignoring the new storage slot
    env.chain.receiver_usdt = 0
    c = env.chain.client()
    assert env.escrow.estimate_usdt_transfer_energy(ESCROW, RECEIVER, 1, c) == 130_000
    env.chain.receiver_usdt = 7_000_000  # holder → real estimate kept
    assert env.escrow.estimate_usdt_transfer_energy(ESCROW, RECEIVER, 1, c) == 64_000


def test_escrow_own_energy_reduces_required_trx(env):
    _with_resources(env.chain, energy_limit=200_000)
    est = env.escrow.estimate_usdt_transfer_cost_sun(ESCROW, RECEIVER, 1, env.chain.client())
    assert est["energy_available"] == 200_000
    assert est["required_sun"] == int(1_000_000 * 1.2)  # only bandwidth reserve
    assert est["fee_limit_sun"] == 30_000_000


def test_resource_lookup_failure_means_zero_energy(env):
    est = env.escrow.estimate_usdt_transfer_cost_sun(ESCROW, RECEIVER, 1, env.chain.client())
    assert est["energy_available"] == 0
    assert est["required_sun"] == int(130_285 * 1.2) * 100 + int(1_000_000 * 1.2)


def test_fee_limit_capped_and_absurd_estimate_refused_nothing_sent(env):
    env.chain.energy_fee = 2_000  # ~312 TRX estimate
    with pytest.raises(env.escrow.EscrowTransferRefused) as ei:
        env.escrow.prepare_usdt_transfer("enc", RECEIVER, 4_000_000)
    assert ei.value.reason == "GAS_ESTIMATE_TOO_HIGH" and not ei.value.retryable
    assert env.chain.broadcasts == []


def test_short_escrow_after_topup_does_not_broadcast(env, monkeypatch):
    """Top-up 'confirmed' by receipt but escrow balance still short → no USDT tx built."""
    calls = {"n": 0}
    real = env.escrow._trx_sun_or_none

    def bal(client, addr):
        calls["n"] += 1
        return 0 if addr == ESCROW else real(client, addr)
    monkeypatch.setattr(env.escrow, "_trx_sun_or_none", bal)
    monkeypatch.setattr(env.escrow, "wait_gas_topup",
                        lambda *a, **k: {"status": "SUCCESS", "reason": None, "balance_sun": None})
    with pytest.raises(env.escrow.EscrowTransferRefused) as ei:
        env.escrow.prepare_usdt_transfer("enc", RECEIVER, 4_000_000)
    assert ei.value.reason == "ESCROW_GAS_SHORT" and ei.value.retryable
    assert ei.value.gas_tx  # reused on retry, no second top-up
    assert not [b for b in env.chain.broadcasts if b[0] == "usdt"]


def test_happy_path_topup_covers_estimate_and_fee_limit(env):
    p = env.escrow.prepare_usdt_transfer("enc", RECEIVER, 4_000_000)
    assert env.chain.balances[ESCROW] >= p["estimate"]["required_sun"]
    assert p["fee_limit_sun"] >= p["estimate"]["required_sun"]


# ── receipt cost logging ──

def test_receipt_costs_logged(env, caplog):
    info = {"id": "t1", "fee": 13_045_000,
            "receipt": {"result": "SUCCESS", "energy_usage_total": 130_285, "energy_fee": 13_028_500,
                        "net_fee": 345_000}}
    with caplog.at_level(logging.INFO):
        c = env.escrow.log_payout_receipt("t1", {"status": "SUCCESS", "info": info},
                                          estimate={"energy": 130_285, "required_sun": 16_834_200,
                                                    "fee_limit_sun": 30_000_000}, label="deal #1 release")
    assert c == {"energy_used": 130_285, "energy_from_stake": 0, "energy_fee_sun": 13_028_500,
                 "net_fee_sun": 345_000, "fee_sun": 13_045_000}
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "energy_used=130285" in msg and "total_fee=13.045000 TRX" in msg


def test_receipt_costs_tolerate_missing_fields(env):
    assert env.escrow.receipt_costs({})["energy_used"] == 0
    assert env.escrow.receipt_costs(None)["fee_sun"] == 0


# ── migration 0035: deal #29 stale record ──

def _close_sql():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0035_close_deal29_stale_release.py"
    spec = importlib.util.spec_from_file_location("m0035", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CLOSE_SQL


@pytest.mark.asyncio
async def test_migration_0035_closes_only_deal29_stale_record(pg_orm):
    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus, Transaction, TransactionStatus as TS, TransactionType as TT
    from app.models.user import User

    async with pg_orm.session() as db:
        b, s = User(first_name="B", telegram_id=1), User(first_name="S", telegram_id=2)
        db.add_all([b, s]); await db.flush()
        ch = Channel(seller_id=s.id, telegram_link="https://t.me/x", channel_name="X", category="news",
                     price=1.0, status=ChannelStatus.sold)
        db.add(ch); await db.flush()
        for did, st, ph in ((29, DealStatus.completed, "bbb3b463" + "0" * 56),
                            (3, DealStatus.paid, None), (6, DealStatus.completed, None)):
            db.add(Deal(id=did, channel_id=ch.id, buyer_id=b.id, seller_id=s.id, status=st, amount_usdt=4.0,
                        service_fee=0.1, escrow_wallet_address=f"T{did}", escrow_private_key_encrypted="e",
                        payout_tx_hash=ph))
        await db.flush()
        reason = "Газ-поповнення escrow не підтвердилось: x (tx g1)"
        rows = [
            Transaction(deal_id=29, type=TT.release, status=TS.failed, amount=4.0,
                        receipt_status="GAS_TOPUP_UNCONFIRMED", receipt_reason=reason),          # target
            Transaction(deal_id=29, type=TT.release, status=TS.confirmed, amount=4.0,
                        tx_hash="bbb3b463" + "0" * 56, receipt_status="SUCCESS"),               # the real payout
            Transaction(deal_id=29, type=TT.overpay_refund, status=TS.failed, amount=2.3,
                        receipt_status="GAS_TOPUP_UNCONFIRMED", receipt_reason=reason),          # other type
            Transaction(deal_id=3, type=TT.release, status=TS.failed, amount=4.0,
                        receipt_status="GAS_TOPUP_UNCONFIRMED", receipt_reason=reason),          # other deal
            Transaction(deal_id=6, type=TT.release, status=TS.failed, amount=4.0,
                        receipt_status="GAS_TOPUP_UNCONFIRMED", receipt_reason=reason),
        ]
        db.add_all(rows); await db.commit()
        ids = [r.id for r in rows]

    sql = _close_sql()
    for _ in range(2):  # idempotent
        async with pg_orm.engine.begin() as conn:
            await conn.execute(text(sql))

    async with pg_orm.session() as db:
        got = {t.id: t for t in (await db.execute(select(Transaction))).scalars()}
        deals = {d.id: d for d in (await db.execute(select(Deal))).scalars()}
    t = got[ids[0]]
    assert t.receipt_status == "SUPERSEDED" and t.status == TS.failed and t.finalized_at is not None
    assert "bbb3b463" in t.receipt_reason and t.receipt_reason.count("Закрито") == 1
    assert got[ids[1]].receipt_status == "SUCCESS" and got[ids[1]].status == TS.confirmed
    for i in ids[2:]:
        assert got[i].receipt_status == "GAS_TOPUP_UNCONFIRMED"
    assert deals[3].status == DealStatus.paid and deals[6].status == DealStatus.completed
    assert deals[29].status == DealStatus.completed


@pytest.mark.asyncio
async def test_migration_0035_noop_without_proof_of_success(pg_orm):
    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus, Transaction, TransactionStatus as TS, TransactionType as TT
    from app.models.user import User

    async with pg_orm.session() as db:
        b, s = User(first_name="B", telegram_id=11), User(first_name="S", telegram_id=12)
        db.add_all([b, s]); await db.flush()
        ch = Channel(seller_id=s.id, telegram_link="https://t.me/y", channel_name="Y", category="news",
                     price=1.0, status=ChannelStatus.sold)
        db.add(ch); await db.flush()
        db.add(Deal(id=29, channel_id=ch.id, buyer_id=b.id, seller_id=s.id, status=DealStatus.awaiting_payout,
                    amount_usdt=4.0, service_fee=0.1, escrow_wallet_address="T29", escrow_private_key_encrypted="e"))
        await db.flush()
        tx = Transaction(deal_id=29, type=TT.release, status=TS.failed, amount=4.0,
                         receipt_status="GAS_TOPUP_UNCONFIRMED", receipt_reason="x")
        db.add(tx); await db.commit()
        tid = tx.id
    async with pg_orm.engine.begin() as conn:
        await conn.execute(text(_close_sql()))
    async with pg_orm.session() as db:
        assert (await db.get(Transaction, tid)).receipt_status == "GAS_TOPUP_UNCONFIRMED"
