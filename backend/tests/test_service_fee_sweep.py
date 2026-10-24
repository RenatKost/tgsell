"""Paid services → treasury fee sweep (TRON fully mocked) + one-shot partial-payment alert."""
from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
import pytest_asyncio

TREASURY = "TXoRpYu5FDgZvrqNQb239bLjcc5oHzavCG"


class Tron:
    def __init__(self):
        self.balances, self.prepared, self.broadcasts, self.trx_sweeps = {}, [], [], []
        self.receipt_status = "SUCCESS"
        self.prepare_error = None

    def units(self, addr):
        return self.balances.get(addr, 0)

    def prepare(self, enc, to, units, **kw):
        if self.prepare_error is not None:
            err, self.prepare_error = self.prepare_error, None
            raise err
        self.prepared.append((enc, to, units, kw))
        return {"txid": f"svctx{len(self.prepared)}", "gas_tx": "gas1", "energy": {"source": "burn"}}

    def broadcast(self, prepared):
        enc, to, units, _ = self.prepared[int(prepared["txid"].removeprefix("svctx")) - 1]
        self.broadcasts.append(prepared["txid"])
        addr = enc.removeprefix("enc-")
        self.balances[addr] -= units

    def receipt(self, txid, timeout=0):
        return {"status": self.receipt_status}

    def sweep(self, enc):
        self.trx_sweeps.append(enc)


@pytest_asyncio.fixture
async def env(orm, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "fee_sweep_enabled", True)
    monkeypatch.setattr(settings, "treasury_address", TREASURY)
    monkeypatch.setattr(settings, "tron_master_wallet_address", "")
    tron = Tron()
    escrow = importlib.import_module("app.services.escrow")
    for name, fn in (("fetch_usdt_balance_units", tron.units), ("prepare_usdt_transfer", tron.prepare),
                     ("broadcast_prepared", tron.broadcast), ("get_receipt", tron.receipt),
                     ("sweep_trx_to_master", tron.sweep)):
        monkeypatch.setattr(escrow, name, fn)
    monkeypatch.setattr(importlib.import_module("app.services.catfee"), "enabled", lambda: True)
    alerts = []

    async def alert(text, key):
        alerts.append(key)
    monkeypatch.setattr(importlib.import_module("app.services.payouts"), "_alert", alert)
    tron.alerts = alerts
    tron.orm = orm
    return tron


async def _order(orm, tron, *, status="active", price=10.0, received=10.0, balance_units=None, kind="top"):
    from app.models.channel import Channel, ChannelStatus
    from app.models.paid_service import PaidServiceOrder
    from app.models.user import User
    async with orm.session() as db:
        u = User(first_name="S", telegram_id=7000 + len(tron.balances))
        db.add(u)
        await db.flush()
        ch = Channel(seller_id=u.id, telegram_link="https://t.me/x", channel_name="X", category="Спорт",
                     subscribers_count=1, price=10, status=ChannelStatus.approved)
        db.add(ch)
        await db.flush()
        addr = f"TSvcAddr{len(tron.balances):026d}"
        o = PaidServiceOrder(kind=kind, channel_id=ch.id, seller_id=u.id, price_usdt=price, status=status,
                             escrow_wallet_address=addr, escrow_private_key_encrypted=f"enc-{addr}",
                             received_usdt=received)
        db.add(o)
        await db.commit()
        tron.balances[addr] = int((received or 0) * 1_000_000) if balance_units is None else balance_units
        return o.id, addr


async def _get(orm, oid):
    from app.models.paid_service import PaidServiceOrder
    async with orm.session() as db:
        return await db.get(PaidServiceOrder, oid)


async def _cycle(orm):
    fs = importlib.import_module("app.services.fee_sweep")
    return await fs.service_sweep_cycle(orm.session, receipt_timeout=0)


@pytest.mark.asyncio
async def test_fully_paid_swept_once_to_treasury_with_same_gas_path(env):
    oid, addr = await _order(env.orm, env, price=15.0, received=15.0, status="published", kind="post")
    await _cycle(env.orm)
    o = await _get(env.orm, oid)
    assert o.sweep_status == "done" and o.sweep_tx_hash == "svctx1" and o.sweep_amount_units == 15_000_000
    enc, to, units, kw = env.prepared[0]
    assert to == TREASURY and units == 15_000_000 and kw["allow_master"] is False
    assert kw["energy_key"] == f"tgsell-svc{oid}"  # CatFee energy, same as deal jobs
    assert env.balances[addr] == 0 and env.trx_sweeps == [f"enc-{addr}"]
    for _ in range(3):  # idempotent: never swept twice
        await _cycle(env.orm)
    assert len(env.prepared) == 1 and len(env.broadcasts) == 1


@pytest.mark.asyncio
async def test_only_fully_paid_orders(env):
    awaiting, _ = await _order(env.orm, env, status="awaiting_payment", received=3.0)
    cancelled, _ = await _order(env.orm, env, status="cancelled", received=None, balance_units=0)
    partial, _ = await _order(env.orm, env, status="paid", price=20.0, received=19.0)
    rejected_audit, _ = await _order(env.orm, env, status="rejected", price=20.0, received=20.0, kind="verified")
    await _cycle(env.orm)
    for oid in (awaiting, cancelled, partial):
        assert (await _get(env.orm, oid)).sweep_status is None
    assert (await _get(env.orm, rejected_audit)).sweep_status == "done"  # audit fee, no refund
    assert len(env.prepared) == 1


@pytest.mark.asyncio
async def test_below_min_pending_then_collect_all(env):
    from app.config import settings
    oid, _ = await _order(env.orm, env, price=10.0, received=10.0)
    settings_min = settings.fee_sweep_min_usdt
    try:
        settings.fee_sweep_min_usdt = 50.0
        await _cycle(env.orm)
        assert (await _get(env.orm, oid)).sweep_status == "pending_sweep" and env.prepared == []
        fs = importlib.import_module("app.services.fee_sweep")
        async with env.orm.session() as db:
            r = await fs.collect_all(db, None)
        assert r["queued"] == 1 and r["service_results"][0]["result"] == "queued"
        await _cycle(env.orm)
        assert (await _get(env.orm, oid)).sweep_status == "done" and len(env.prepared) == 1
    finally:
        settings.fee_sweep_min_usdt = settings_min


@pytest.mark.asyncio
async def test_disabled_does_nothing(env):
    from app.config import settings
    settings.fee_sweep_enabled = False
    oid, _ = await _order(env.orm, env)
    assert (await _cycle(env.orm)) == {"enabled": False}
    assert (await _get(env.orm, oid)).sweep_status is None and env.prepared == []


@pytest.mark.asyncio
async def test_retryable_gas_defers_and_reuses_gas_tx(env):
    class GasRetry(Exception):
        retryable, reason, message, gas_tx = True, "GAS_PENDING", "gas pending", "gasA"
    oid, _ = await _order(env.orm, env)
    env.prepare_error = GasRetry()
    await _cycle(env.orm)
    o = await _get(env.orm, oid)
    assert o.sweep_status == "queued" and o.sweep_attempts == 1 and o.sweep_gas_tx_hash == "gasA"
    assert env.broadcasts == []
    await _cycle(env.orm)
    assert env.prepared[0][3]["prior_gas_tx"] == "gasA"
    assert (await _get(env.orm, oid)).sweep_status == "done"


@pytest.mark.asyncio
async def test_failed_receipt_and_pending_never_resent(env):
    oid, _ = await _order(env.orm, env)
    env.receipt_status = "PENDING"
    await _cycle(env.orm)
    assert (await _get(env.orm, oid)).sweep_status == "broadcast"
    await _cycle(env.orm)
    await _cycle(env.orm)
    assert len(env.prepared) == 1 and len(env.broadcasts) == 1  # never re-prepared / re-broadcast
    env.receipt_status = "FAILED"
    await _cycle(env.orm)
    o = await _get(env.orm, oid)
    assert o.sweep_status == "failed" and f"svc_sweep_failed_{oid}" in env.alerts
    await _cycle(env.orm)
    assert len(env.prepared) == 1  # failed is not auto-retried


@pytest.mark.asyncio
async def test_crash_in_processing_is_failed_not_resent(env):
    from app.models.paid_service import PaidServiceOrder
    from app.utils.timeutil import utcnow_naive
    oid, _ = await _order(env.orm, env)
    async with env.orm.session() as db:
        o = await db.get(PaidServiceOrder, oid)
        o.sweep_status, o.sweep_amount_units = "processing", 10_000_000
        o.updated_at = utcnow_naive() - timedelta(hours=1)
        await db.commit()
    await _cycle(env.orm)
    assert (await _get(env.orm, oid)).sweep_status == "failed" and env.prepared == []


@pytest.mark.asyncio
async def test_bad_treasury_refused(env):
    from app.config import settings
    settings.treasury_address = "TXoRpYu5FDgZvrqNQb239bLjcc5oHzavCX"  # bad checksum
    oid, _ = await _order(env.orm, env)
    await _cycle(env.orm)
    assert env.prepared == [] and (await _get(env.orm, oid)).sweep_status is None


@pytest.mark.asyncio
async def test_partial_payment_alert_once(orm, monkeypatch):
    from app.models.paid_service import PaidServiceOrder
    from app.services import paid_services as svc
    from app.utils.timeutil import utcnow_naive
    sent = []

    async def fake_alert(text, alert_key=None, **_kw):
        sent.append((alert_key, text))
        return True
    monkeypatch.setattr(importlib.import_module("app.services.alerts"), "send_admin_alert", fake_alert)
    env = Tron()
    oid, _ = await _order(orm, env, status="awaiting_payment", price=15.0, received=None, balance_units=0)
    async with orm.session() as db:
        o = await db.get(PaidServiceOrder, oid)
        o.payment_deadline_at = utcnow_naive() - timedelta(minutes=1)
        await db.commit()

    async def bal(_a):
        return 4.0
    now = utcnow_naive()
    await svc.check_orders_once(orm.session, now=now, fetch_balance=bal)  # before alert window? deadline passed → alert
    for i in range(5):
        await svc.check_orders_once(orm.session, now=now + timedelta(minutes=i + 1), fetch_balance=bal)
    assert len(sent) == 1 and sent[0][0] == f"svc_partial_{oid}" and "4 з 15" in sent[0][1]
    o = await (orm.session().__aenter__())
    row = await o.get(PaidServiceOrder, oid)
    assert row.status == "awaiting_payment" and row.partial_alerted_at is not None and row.received_usdt == 4.0
    await o.close()


@pytest.mark.asyncio
async def test_partial_before_deadline_no_alert(orm, monkeypatch):
    from app.models.paid_service import PaidServiceOrder
    from app.services import paid_services as svc
    from app.utils.timeutil import utcnow_naive
    sent = []

    async def fake_alert(text, alert_key=None, **_kw):
        sent.append(alert_key)
        return True
    monkeypatch.setattr(importlib.import_module("app.services.alerts"), "send_admin_alert", fake_alert)
    env = Tron()
    oid, _ = await _order(orm, env, status="awaiting_payment", price=15.0, received=None, balance_units=0)
    async with orm.session() as db:
        (await db.get(PaidServiceOrder, oid)).payment_deadline_at = utcnow_naive() + timedelta(hours=5)
        await db.commit()

    async def bal(_a):
        return 4.0
    await svc.check_orders_once(orm.session, fetch_balance=bal)
    assert sent == []


def test_migration_chain():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "alembic/versions/0052_escrow_hardening.py").read_text()
    assert 'revision = "0052"' in src and 'down_revision = "0051"' in src
