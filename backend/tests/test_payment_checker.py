"""Payment checker: BALANCE FIRST, then timeout (audit task 11) — real Postgres.

TronGrid and Telegram are always faked. Covers: payment at the timeout edge,
unknown balance (429), zero balance after timeout (+ notifications), partial
payment (admin alert, deduped), stuck 'created' deals (legacy vs new), concurrent
status change, late payment after auto-cancel, deadlines on create/confirm-ready,
escrow throttle/retry/cache, admin balances "unknown" + 60s cache, sweep on unknown.
"""
from __future__ import annotations

import importlib
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select  # noqa: E402

from app.utils.timeutil import utcnow_naive  # noqa: E402

ADMIN_GROUP = -100777
BUYER_TG = 7001
SELLER_TG = 7002


class FakeBot:
    sent: list[tuple[int, str]] = []

    def __init__(self, token: str = "", **_kw):
        self.session = SimpleNamespace(close=AsyncMock())

    async def send_message(self, chat_id, text, **_kw):
        FakeBot.sent.append((chat_id, text))
        return SimpleNamespace(message_id=len(FakeBot.sent))


class Chain:
    """Fake TronGrid: address → balance (float) or an Exception instance to raise."""

    def __init__(self):
        self.balances: dict[str, object] = {}
        self.calls: list[str] = []
        self.on_call = None

    def fetch(self, address: str) -> float:
        BalanceUnavailable = importlib.import_module("app.services.escrow").BalanceUnavailable

        self.calls.append(address)
        if self.on_call is not None:
            self.on_call(address)
        value = self.balances.get(address, 0.0)
        if isinstance(value, Exception):
            raise BalanceUnavailable(str(value))
        return float(value)


@pytest_asyncio.fixture
async def env(pg_orm, monkeypatch):
    from app.config import settings

    # sys.modules entry (package attribute can be stale after other tests' module juggling)
    escrow = importlib.import_module("app.services.escrow")
    pc = importlib.import_module("app.tasks.payment_checker")
    monkeypatch.setattr(settings, "bot_token_alerts", "123:TEST")
    monkeypatch.setattr(settings, "admin_group_id", ADMIN_GROUP)
    monkeypatch.setattr(settings, "payment_timeout_hours", 2)
    monkeypatch.setattr(settings, "created_deal_timeout_hours", 24)
    monkeypatch.setattr(pc, "Bot", FakeBot)
    chain = Chain()
    monkeypatch.setattr(escrow, "fetch_usdt_balance", chain.fetch)
    if pc.escrow_svc is not escrow:
        monkeypatch.setattr(pc.escrow_svc, "fetch_usdt_balance", chain.fetch)
    FakeBot.sent = []
    pc._partial_alerted.clear()
    pc._late_alerted.clear()
    monkeypatch.setattr(pc, "_cycle", 0)
    monkeypatch.setattr(pc, "LATE_PAYMENT_CHECK_EVERY_N_CYCLES", 1)

    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealChecklistItem, DealMessage, DealStatus, Transaction
    from app.models.user import User

    async with pg_orm.session() as db:
        buyer = User(first_name="Buyer", telegram_id=BUYER_TG)
        seller = User(first_name="Seller", telegram_id=SELLER_TG)
        db.add_all([buyer, seller])
        await db.flush()
        channel = Channel(
            seller_id=seller.id, telegram_link="https://t.me/x", channel_name="X",
            category="news", price=15.0, status=ChannelStatus.approved,
        )
        db.add(channel)
        await db.commit()
        ids = SimpleNamespace(buyer=buyer.id, seller=seller.id, channel=channel.id)

    counter = iter(range(1, 1000))

    async def make_deal(status, *, age_hours: float, amount=15.0, deadline_in_hours=None, **kw):
        now = utcnow_naive()
        n = next(counter)
        deal = Deal(
            channel_id=ids.channel, buyer_id=ids.buyer, seller_id=ids.seller, status=status,
            escrow_wallet_address=f"TESCROW{n:026d}", escrow_private_key_encrypted="enc",
            amount_usdt=amount, service_fee=amount * 0.03,
            created_at=now - timedelta(hours=age_hours),
            payment_deadline_at=(now + timedelta(hours=deadline_in_hours)) if deadline_in_hours is not None else None,
            **kw,
        )
        async with pg_orm.session() as db:
            db.add(deal)
            await db.commit()
            return deal.id, deal.escrow_wallet_address

    async def get(deal_id):
        async with pg_orm.session() as db:
            return await db.get(Deal, deal_id)

    async def count(model, **where):
        async with pg_orm.session() as db:
            q = select(func.count()).select_from(model)
            for k, v in where.items():
                q = q.where(getattr(model, k) == v)
            return (await db.execute(q)).scalar_one()

    yield SimpleNamespace(
        orm=pg_orm, pc=pc, chain=chain, ids=ids, make_deal=make_deal, get=get, count=count,
        S=DealStatus, Deal=Deal, Tx=Transaction, Msg=DealMessage, Item=DealChecklistItem,
    )


def _sent_to(chat_id):
    return [t for c, t in FakeBot.sent if c == chat_id]


# ── balance first, then timeout ────────────────────────────────────────

@pytest.mark.asyncio
async def test_payment_at_timeout_edge_is_confirmed_not_cancelled(env):
    # legacy payment_pending (NULL deadline) 2h + 1min old: old code cancelled BEFORE balance check
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=2 + 1 / 60)
    env.chain.balances[addr] = 15.0

    await env.pc.check_payments_once()

    deal = await env.get(deal_id)
    assert deal.status == env.S.paid and deal.paid_at is not None
    assert deal.cancelled_at is None
    assert await env.count(env.Tx, deal_id=deal_id) == 1
    assert await env.count(env.Item, deal_id=deal_id) > 0  # transfer checklist started
    assert any("оплата 15.0 USDT отримана" in t for t in _sent_to(BUYER_TG))
    assert not any("скасовано" in t.lower() for _, t in FakeBot.sent)


@pytest.mark.asyncio
async def test_unknown_balance_never_cancels(env):
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=5)
    env.chain.balances[addr] = RuntimeError("429 Client Error: Too Many Requests")

    for _ in range(3):
        await env.pc.check_payments_once()

    deal = await env.get(deal_id)
    assert deal.status == env.S.payment_pending
    assert FakeBot.sent == []


@pytest.mark.asyncio
async def test_zero_balance_after_timeout_cancels_and_notifies(env):
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=0.5, deadline_in_hours=-0.01)
    env.chain.balances[addr] = 0.0

    await env.pc.check_payments_once()

    deal = await env.get(deal_id)
    assert deal.status == env.S.cancelled
    assert deal.cancel_reason == "payment_timeout" and deal.cancelled_at is not None
    assert deal.cancelled_at.tzinfo is None
    assert env.chain.calls.count(addr) >= 2  # re-checked right before cancelling
    assert any("скасовано" in t for t in _sent_to(BUYER_TG))
    assert any("скасовано" in t for t in _sent_to(SELLER_TG))
    assert any("автоматично скасовано" in t for t in _sent_to(ADMIN_GROUP))
    assert await env.count(env.Msg, deal_id=deal_id, is_system=True) == 1


@pytest.mark.asyncio
async def test_zero_balance_before_deadline_is_left_alone(env):
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=0.5, deadline_in_hours=1.5)
    await env.pc.check_payments_once()
    assert (await env.get(deal_id)).status == env.S.payment_pending
    assert FakeBot.sent == []


@pytest.mark.asyncio
async def test_recheck_before_cancel_unknown_does_not_cancel(env):
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=3)
    seen = {"n": 0}

    def flaky(address):
        seen["n"] += 1
        if seen["n"] >= 2:  # first read 0, re-check fails
            env.chain.balances[address] = RuntimeError("timeout")

    env.chain.on_call = flaky
    await env.pc.check_payments_once()
    assert (await env.get(deal_id)).status == env.S.payment_pending


@pytest.mark.asyncio
async def test_partial_payment_alerts_admin_once_and_never_cancels(env):
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=10)
    env.chain.balances[addr] = 5.0

    await env.pc.check_payments_once()
    await env.pc.check_payments_once()
    deal = await env.get(deal_id)
    assert deal.status == env.S.payment_pending
    alerts = [t for t in _sent_to(ADMIN_GROUP) if "Часткова оплата" in t]
    assert len(alerts) == 1 and "5.0 з 15.0" in alerts[0]

    env.chain.balances[addr] = 7.0  # amount changed → new alert
    await env.pc.check_payments_once()
    assert len([t for t in _sent_to(ADMIN_GROUP) if "Часткова оплата" in t]) == 2
    assert (await env.get(deal_id)).status == env.S.payment_pending
    assert not any("скасовано" in t.lower() for _, t in FakeBot.sent)


# ── 'created' stage ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_legacy_created_deal_like_26_is_never_auto_cancelled(env):
    # #26: created 2026-10-04, buyer ready, seller not, no payment_deadline_at, balance 0
    deal_id, addr = await env.make_deal(env.S.created, age_hours=50, buyer_ready=True)
    env.chain.balances[addr] = 0.0

    await env.pc.check_payments_once()

    deal = await env.get(deal_id)
    assert deal.status == env.S.created and deal.cancelled_at is None
    assert addr in env.chain.calls  # balance IS checked (payment would be detected)
    assert FakeBot.sent == []


@pytest.mark.asyncio
async def test_new_created_deal_past_24h_with_zero_balance_is_cancelled(env):
    deal_id, addr = await env.make_deal(env.S.created, age_hours=25, deadline_in_hours=-1)
    await env.pc.check_payments_once()
    deal = await env.get(deal_id)
    assert deal.status == env.S.cancelled and deal.cancel_reason == "payment_timeout"
    assert any("скасовано" in t for t in _sent_to(BUYER_TG))


@pytest.mark.asyncio
async def test_new_created_deal_within_24h_is_left_alone(env):
    deal_id, addr = await env.make_deal(env.S.created, age_hours=3, deadline_in_hours=21)
    await env.pc.check_payments_once()
    assert (await env.get(deal_id)).status == env.S.created


@pytest.mark.asyncio
async def test_created_deal_with_full_payment_becomes_paid(env):
    deal_id, addr = await env.make_deal(env.S.created, age_hours=50, buyer_ready=True)
    env.chain.balances[addr] = 15.0
    await env.pc.check_payments_once()
    deal = await env.get(deal_id)
    assert deal.status == env.S.paid
    assert await env.count(env.Tx, deal_id=deal_id) == 1


@pytest.mark.asyncio
async def test_created_deal_partial_alerts_not_cancelled(env):
    deal_id, addr = await env.make_deal(env.S.created, age_hours=30, deadline_in_hours=-6)
    env.chain.balances[addr] = 1.0
    await env.pc.check_payments_once()
    assert (await env.get(deal_id)).status == env.S.created
    assert any("Часткова оплата" in t for t in _sent_to(ADMIN_GROUP))


@pytest.mark.asyncio
async def test_concurrent_status_change_is_not_overwritten(env):
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=3)

    def admin_acts(address):
        # Between our balance read and the cancel, someone else moves the deal.
        import asyncio

        async def _move():
            from sqlalchemy import update

            async with env.orm.session() as db:
                await db.execute(update(env.Deal).where(env.Deal.id == deal_id).values(status=env.S.disputed))
                await db.commit()

        if env.chain.calls.count(address) == 2:
            asyncio.run(_move())  # runs in the to_thread worker → its own event loop

    env.chain.on_call = admin_acts
    await env.pc.check_payments_once()
    deal = await env.get(deal_id)
    assert deal.status == env.S.disputed and deal.cancelled_at is None
    assert not any("скасовано" in t.lower() for _, t in FakeBot.sent)


@pytest.mark.asyncio
async def test_other_statuses_are_not_touched(env):
    ids = []
    for st in (env.S.paid, env.S.channel_transferring, env.S.awaiting_payout, env.S.payout_in_progress,
               env.S.completed, env.S.disputed):
        ids.append((await env.make_deal(st, age_hours=100))[0])
    await env.pc.check_payments_once()
    assert env.chain.calls == []
    for deal_id, st in zip(ids, (env.S.paid, env.S.channel_transferring, env.S.awaiting_payout,
                                 env.S.payout_in_progress, env.S.completed, env.S.disputed)):
        assert (await env.get(deal_id)).status == st


@pytest.mark.asyncio
async def test_late_payment_after_auto_cancel_alerts_admin_once(env):
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=3)
    await env.pc.check_payments_once()
    assert (await env.get(deal_id)).status == env.S.cancelled

    env.chain.balances[addr] = 15.0
    await env.pc.check_payments_once()
    await env.pc.check_payments_once()
    late = [t for t in _sent_to(ADMIN_GROUP) if "скасованій угоді" in t]
    assert len(late) == 1
    assert (await env.get(deal_id)).status == env.S.cancelled  # never auto-revived


# ── deadlines set by the API ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_deal_sets_created_stage_deadline(env, monkeypatch):
    import aiogram

    from app.models.user import User
    from app.schemas.deal import DealCreate

    deals_router = importlib.import_module("app.routers.deals")
    monkeypatch.setattr(aiogram, "Bot", FakeBot)
    monkeypatch.setattr(deals_router, "generate_escrow_wallet", lambda: ("TNEWESCROW", "enc"))

    async with env.orm.session() as db:
        buyer = await db.get(User, env.ids.buyer)
        resp = await deals_router.create_deal(DealCreate(channel_id=env.ids.channel), user=buyer, db=db)
    deal = await env.get(resp.id)
    assert deal.status == env.S.created
    expected = utcnow_naive() + timedelta(hours=24)
    assert abs((deal.payment_deadline_at - expected).total_seconds()) < 60


@pytest.mark.asyncio
async def test_confirm_ready_starts_2h_payment_window(env):
    from app.models.user import User

    deals_router = importlib.import_module("app.routers.deals")
    # legacy 'created' deal (NULL deadline), 50h old — like #26 if the seller clicks "ready" now
    deal_id, addr = await env.make_deal(env.S.created, age_hours=50, buyer_ready=True)
    async with env.orm.session() as db:
        seller = await db.get(User, env.ids.seller)
        await deals_router.confirm_ready(deal_id, user=seller, db=db)
    deal = await env.get(deal_id)
    assert deal.status == env.S.payment_pending
    expected = utcnow_naive() + timedelta(hours=2)
    assert abs((deal.payment_deadline_at - expected).total_seconds()) < 60

    # and the checker does NOT cancel it right away (old rule would: created_at + 2h passed)
    await env.pc.check_payments_once()
    assert (await env.get(deal_id)).status == env.S.payment_pending


# ── admin escrow balances / sweep ───────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_balances_show_unknown_not_zero_and_cache(env):
    admin_router = importlib.import_module("app.routers.admin")
    d_funded, a_funded = await env.make_deal(env.S.paid, age_hours=1)
    d_unknown, a_unknown = await env.make_deal(env.S.created, age_hours=1)
    d_empty, a_empty = await env.make_deal(env.S.cancelled, age_hours=1)
    env.chain.balances.update({a_funded: 15.0, a_unknown: RuntimeError("429"), a_empty: 0.0})

    async with env.orm.session() as db:
        r1 = await admin_router.check_escrow_balances(refresh=False, admin=None, db=db)
    assert [w["deal_id"] for w in r1["wallets_with_funds"]] == [d_funded]
    assert r1["total"] == 15.0
    assert r1["unknown_count"] == 1
    assert r1["unknown"][0]["deal_id"] == d_unknown
    assert r1["unknown"][0]["balance_usdt"] is None and r1["unknown"][0]["error"] == "unknown"
    assert r1["cached"] is False
    calls_after_first = len(env.chain.calls)
    assert calls_after_first == 3

    async with env.orm.session() as db:
        r2 = await admin_router.check_escrow_balances(refresh=False, admin=None, db=db)
        r3 = await admin_router.check_escrow_balances(refresh=True, admin=None, db=db)  # <10s: still cached
    assert r2["cached"] is True and r3["cached"] is True
    assert len(env.chain.calls) == calls_after_first

    admin_router._escrow_balances_cache["at"] -= 61  # expire
    async with env.orm.session() as db:
        r4 = await admin_router.check_escrow_balances(refresh=False, admin=None, db=db)
    assert r4["cached"] is False and len(env.chain.calls) == calls_after_first + 3


@pytest.mark.asyncio
async def test_sweep_with_unknown_balance_moves_nothing(env, monkeypatch):
    escrow = importlib.import_module("app.services.escrow")
    admin_router = importlib.import_module("app.routers.admin")
    deal_id, addr = await env.make_deal(env.S.cancelled, age_hours=1)
    env.chain.balances[addr] = RuntimeError("429")
    gas, transfer = MagicMock(), MagicMock()
    monkeypatch.setattr(escrow, "send_trx_for_gas", gas)
    monkeypatch.setattr(escrow, "transfer_usdt", transfer)

    async with env.orm.session() as db:
        r = await admin_router.sweep_escrow_wallet(deal_id, to_address="TTARGET", admin=None, db=db)
    assert r["ok"] is False and "Не вдалося отримати баланс" in r["error"]
    gas.assert_not_called()
    transfer.assert_not_called()


# ── escrow service: unknown vs 0, retry/backoff, throttle, contract cache ──

class _FakeContract:
    def __init__(self, script):
        self.script = list(script)  # items: int (raw balance) or Exception
        self.calls = 0
        self.functions = SimpleNamespace(balanceOf=self._balance_of)

    def _balance_of(self, address):
        self.calls += 1
        item = self.script.pop(0) if self.script else 0
        if isinstance(item, Exception):
            raise item
        return item


def _http_error(code):
    import requests

    resp = requests.Response()
    resp.status_code = code
    return requests.HTTPError(f"{code} Client Error", response=resp)


@pytest.fixture
def tron(monkeypatch):
    escrow = importlib.import_module("app.services.escrow")

    sleeps: list[float] = []
    clock = {"t": 1000.0}

    def fake_sleep(sec):
        sleeps.append(sec)
        clock["t"] += sec

    monkeypatch.setattr(escrow.time, "sleep", fake_sleep)
    monkeypatch.setattr(escrow.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(escrow.random, "uniform", lambda a, b: 0.0)
    escrow.reset_tron_read_cache()
    state = SimpleNamespace(contract=None, get_contract_calls=0)

    def fake_client():
        def get_contract(addr):
            state.get_contract_calls += 1
            return state.contract

        return SimpleNamespace(get_contract=get_contract)

    monkeypatch.setattr(escrow, "_get_tron_client", fake_client)
    yield SimpleNamespace(escrow=escrow, sleeps=sleeps, state=state, clock=clock)
    escrow.reset_tron_read_cache()


def test_balance_zero_is_zero_and_contract_is_cached(tron):
    tron.state.contract = _FakeContract([0, 15_000_000])
    assert tron.escrow.fetch_usdt_balance("TA") == 0.0
    assert tron.escrow.get_usdt_balance("TB") == 15.0
    assert tron.state.get_contract_calls == 1  # no getcontract per balance check


def test_429_is_retried_with_backoff_then_succeeds(tron):
    tron.state.contract = _FakeContract([_http_error(429), _http_error(429), 4_000_000])
    assert tron.escrow.fetch_usdt_balance("TA") == 4.0
    backoffs = [s for s in tron.sleeps if s >= 1.0]
    assert backoffs == [1.0, 2.0]


def test_persistent_429_is_unknown_not_zero(tron):
    tron.state.contract = _FakeContract([_http_error(429)] * 10)
    with pytest.raises(tron.escrow.BalanceUnavailable):
        tron.escrow.fetch_usdt_balance("TA")
    assert tron.escrow.get_usdt_balance("TA") is None
    assert tron.state.contract.calls == 4 + 4  # 1 + 3 retries, twice


def test_non_retryable_error_is_unknown_immediately(tron):
    tron.state.contract = _FakeContract([ValueError("bad address")])
    assert tron.escrow.get_usdt_balance("TA") is None
    assert tron.state.contract.calls == 1


def test_requests_are_spaced_by_min_interval(tron):
    tron.state.contract = _FakeContract([1, 2, 3])
    for addr in ("TA", "TB", "TC"):
        tron.escrow.fetch_usdt_balance(addr)
    interval = tron.escrow.TRON_MIN_INTERVAL_SEC
    spacing = [s for s in tron.sleeps if s < 1.0]
    # getcontract + 3 balanceOf back-to-back → 3 waits of the full min interval
    assert len(spacing) == 3 and all(abs(s - interval) < 1e-9 for s in spacing)


# ── Migration 0025 on a database with existing deals ────────────────────

def test_migration_0025_leaves_existing_deals_without_deadline(db_url):
    import asyncio
    import os
    import subprocess
    import uuid
    from urllib.parse import unquote

    import asyncpg
    from sqlalchemy.engine import make_url

    url, kind = db_url
    if kind != "postgres":
        pytest.skip("!!! REAL POSTGRES UNAVAILABLE — migration test skipped !!!")

    def alembic(target: str, *args: str) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", *args], cwd=BACKEND_ROOT,
            env={**os.environ, "DATABASE_URL": target}, capture_output=True, text=True, timeout=180,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    base = make_url(url)
    dbname = f"mig_{uuid.uuid4().hex[:10]}"

    def dsn(db: str) -> str:
        return base.set(drivername="postgresql", database=db).render_as_string(hide_password=False)

    async def run(db: str, fn):
        conn = await asyncpg.connect(dsn(db))
        try:
            return await fn(conn)
        finally:
            await conn.close()

    try:
        asyncio.run(run(base.database or "postgres", lambda c: c.execute(f'CREATE DATABASE "{dbname}"')))
    except Exception as e:
        pytest.skip(f"cannot create scratch database for migration test: {e}")

    target = unquote(base.set(database=dbname).render_as_string(hide_password=False))
    try:
        alembic(target, "upgrade", "0024")

        async def seed(c):
            u1 = await c.fetchval("INSERT INTO users (telegram_id, first_name) VALUES (1, 'b') RETURNING id")
            u2 = await c.fetchval("INSERT INTO users (telegram_id, first_name) VALUES (2, 's') RETURNING id")
            ch = await c.fetchval(
                "INSERT INTO channels (seller_id, telegram_link, channel_name, category, price, status) "
                "VALUES ($1, 'https://t.me/x', 'X', 'news', 15, 'approved') RETURNING id", u2)
            for st in ("created", "payment_pending", "completed"):
                await c.execute(
                    "INSERT INTO deals (channel_id, buyer_id, seller_id, status, escrow_wallet_address, "
                    "escrow_private_key_encrypted, amount_usdt, service_fee) "
                    "VALUES ($1, $2, $3, $4, $5, 'enc', 15, 0.45)", ch, u1, u2, st, f"T{st}")

        asyncio.run(run(dbname, seed))
        alembic(target, "upgrade", "head")

        rows = asyncio.run(run(dbname, lambda c: c.fetch(
            "SELECT status, payment_deadline_at, cancelled_at, cancel_reason FROM deals ORDER BY id")))
        assert [r["status"] for r in rows] == ["created", "payment_pending", "completed"]
        assert all(r["payment_deadline_at"] is None and r["cancelled_at"] is None
                   and r["cancel_reason"] is None for r in rows)

        alembic(target, "downgrade", "0024")
        alembic(target, "upgrade", "head")
    finally:
        asyncio.run(run(base.database or "postgres", lambda c: c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')))
