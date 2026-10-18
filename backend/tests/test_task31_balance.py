"""Task 31: seller-stated Telegram Stars / TON balance on channels.

Covers: migration 0043, catalog/saved-search filter «з балансом», API fields &
badges, deal snapshot, checklist payout gate and «баланс не відповідає» dispute.
"""
from __future__ import annotations

import importlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

from app.models.deal import DealStatus  # noqa: E402
from app.services import deal_checklist as cl  # noqa: E402

SELLER_ID, BUYER_ID = 1, 2
BASE_REQUIRED = [d.key for d in cl.CHECKLIST_ITEMS if d.required]


# ── Migration ──────────────────────────────────────────────────────────

def test_migration_0043_shape():
    mig = (BACKEND_ROOT / "alembic/versions/0043_channel_balance.py").read_text(encoding="utf-8")
    assert 'revision = "0043"' in mig and 'down_revision = "0042"' in mig
    for col in ('"stars_balance", sa.Integer()', '"ton_balance", sa.Numeric(20, 9)',
                '"balance_stars", sa.Integer()', '"balance_ton", sa.Numeric(20, 9)'):
        assert col in mig
    assert mig.count("nullable=True") == 4  # existing rows stay NULL (deals #3, #6, #29 …)
    assert "stars_balance >= 0" in mig and "ton_balance >= 0" in mig
    assert "def downgrade" in mig and mig.count("op.drop_column") == 4
    # linear history: only 0044 (weekly report log) builds on 0043
    heads = [p.name for p in (BACKEND_ROOT / "alembic/versions").glob("*.py")
             if 'down_revision = "0043"' in p.read_text(encoding="utf-8")]
    assert heads == ["0044_scheduled_report_runs.py"]


@pytest.mark.asyncio
async def test_alembic_upgrade_downgrade_on_postgres(db_url):
    """Run 0043 upgrade/downgrade via alembic Operations on real Postgres (isolated schema)."""
    url, kind = db_url
    if kind != "postgres":
        pytest.skip("needs Postgres")
    import importlib.util
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.ext.asyncio import create_async_engine

    spec = importlib.util.spec_from_file_location("m0043", BACKEND_ROOT / "alembic/versions/0043_channel_balance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def run(conn):
        conn.execute(sa.text("DROP SCHEMA IF EXISTS m43 CASCADE"))
        conn.execute(sa.text("CREATE SCHEMA m43"))
        conn.execute(sa.text("SET search_path TO m43"))
        conn.execute(sa.text("CREATE TABLE channels (id serial primary key, price float)"))
        conn.execute(sa.text("CREATE TABLE deals (id serial primary key)"))
        conn.execute(sa.text("INSERT INTO channels (price) VALUES (10)"))
        conn.execute(sa.text("INSERT INTO deals DEFAULT VALUES"))
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
        assert conn.execute(sa.text("SELECT stars_balance, ton_balance FROM channels")).one() == (None, None)
        assert conn.execute(sa.text("SELECT balance_stars, balance_ton FROM deals")).one() == (None, None)
        conn.execute(sa.text("UPDATE channels SET stars_balance=5, ton_balance=1.5"))
        for bad in ("stars_balance=-1", "ton_balance=-0.5"):
            with pytest.raises(Exception):
                with conn.begin_nested():
                    conn.execute(sa.text(f"UPDATE channels SET {bad}"))
        with Operations.context(ctx):
            mod.downgrade()
        cols = {r[0] for r in conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='m43' AND table_name IN ('channels','deals')"))}
        assert not cols & {"stars_balance", "ton_balance", "balance_stars", "balance_ton"}
        conn.execute(sa.text("DROP SCHEMA m43 CASCADE"))

    eng = create_async_engine(url)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(run)
    finally:
        await eng.dispose()


# ── Schemas ────────────────────────────────────────────────────────────

def test_schema_validation_non_negative_and_stars_integer():
    from pydantic import ValidationError
    from app.schemas.channel import ChannelCreate, ChannelUpdate
    from app.schemas.bundle import BundleCreate, ChannelBalanceUpdate

    base = dict(telegram_link="https://t.me/x", category="Крипта", price=100)
    ok = ChannelCreate(**base, stars_balance=1500, ton_balance=12.5)
    assert ok.stars_balance == 1500 and ok.ton_balance == 12.5
    assert ChannelCreate(**base).stars_balance is None
    for bad in ({"stars_balance": -1}, {"ton_balance": -0.1}, {"stars_balance": 1.5}):
        with pytest.raises(ValidationError):
            ChannelCreate(**base, **bad)
    with pytest.raises(ValidationError):
        ChannelUpdate(ton_balance=-5)
    b = BundleCreate(name="N", price=10, channel_links=["a", "b"],
                     channel_balances=[{"stars_balance": 3}, None])
    assert b.channel_balances[0].stars_balance == 3 and b.channel_balances[1] is None
    with pytest.raises(ValidationError):
        ChannelBalanceUpdate(channel_id=1, stars_balance=-3)


# ── Filter / saved searches ───────────────────────────────────────────

def test_saved_search_sanitize_and_label_with_balance():
    from app.services.catalog_filters import CATALOG_FILTER_KEYS
    from app.services.saved_searches import filters_label, sanitize_filters
    assert "with_balance" in CATALOG_FILTER_KEYS
    f = sanitize_filters({"with_balance": 1, "category": "Крипта"})
    assert f == {"with_balance": True, "category": "Крипта"}
    assert "з балансом" in filters_label(f)


def test_balance_never_used_by_pricing_quality_or_ai():
    for rel in ("app/services/pricing.py", "app/services/quality.py", "app/services/ai_analysis.py",
                "app/services/channel_stats.py"):
        p = BACKEND_ROOT / rel
        if p.exists():
            src = p.read_text(encoding="utf-8")
            assert "stars_balance" not in src and "ton_balance" not in src, rel


def _mk_channel(seller_id, name, **kw):
    from app.models.channel import Channel, ChannelStatus
    return Channel(seller_id=seller_id, telegram_link=f"https://t.me/{name}", channel_name=name,
                   category=kw.pop("category", "Крипта"), price=kw.pop("price", 500),
                   subscribers_count=10000, status=kw.pop("status", ChannelStatus.approved), **kw)


async def _client(pg_orm, monkeypatch, *routers):
    from fastapi import FastAPI
    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", pg_orm.session)
    app = FastAPI()
    for name in routers:
        app.include_router(importlib.import_module(name).router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_catalog_filter_with_balance_and_api_fields(pg_orm, monkeypatch):
    from sqlalchemy import select
    from app.models.channel import Channel
    from app.models.user import User
    from app.services.catalog_filters import apply_catalog_filters

    async with pg_orm.session() as db:
        s = User(first_name="S", telegram_id=3101)
        db.add(s)
        await db.commit()
        chans = [
            _mk_channel(s.id, "stars", stars_balance=1500),
            _mk_channel(s.id, "ton", ton_balance=12.5),
            _mk_channel(s.id, "both", stars_balance=10, ton_balance=0.000000001),
            _mk_channel(s.id, "zero", stars_balance=0, ton_balance=0),
            _mk_channel(s.id, "none"),
        ]
        db.add_all(chans)
        await db.commit()
        ids = {c.channel_name: c.id for c in chans}

        got = (await db.execute(apply_catalog_filters(select(Channel.channel_name), {"with_balance": True}))).scalars().all()
        assert sorted(got) == ["both", "stars", "ton"]

    async with await _client(pg_orm, monkeypatch, "app.routers.channels") as c:
        r = await c.get("/api/channels", params={"with_balance": "true", "limit": 50})
        assert r.status_code == 200, r.text
        names = sorted(i["channel_name"] for i in r.json()["items"])
        assert names == ["both", "stars", "ton"]
        r_all = await c.get("/api/channels", params={"limit": 50})
        assert len(r_all.json()["items"]) == 5

        one = (await c.get(f"/api/channels/{ids['stars']}")).json()
        assert one["stars_balance"] == 1500 and one["ton_balance"] is None
        ton = (await c.get(f"/api/channels/{ids['ton']}")).json()
        assert ton["ton_balance"] == 12.5 and ton["stars_balance"] is None
        none = (await c.get(f"/api/channels/{ids['none']}")).json()
        assert "stars_balance" in none and none["stars_balance"] is None and none["ton_balance"] is None
        # Balance does not change price / fair price / quality (same inputs as 'none')
        for k in ("price", "fair_price_range", "price_verdict", "quality_score", "price_per_sub"):
            assert one[k] == none[k], k


@pytest.mark.asyncio
async def test_saved_search_matching_respects_with_balance(pg_orm):
    from sqlalchemy import select
    from app.models.channel import Channel
    from app.models.user import User
    from app.services.catalog_filters import apply_catalog_filters
    from app.services.saved_searches import sanitize_filters

    async with pg_orm.session() as db:
        s = User(first_name="S", telegram_id=3102)
        db.add(s)
        await db.commit()
        a, b = _mk_channel(s.id, "a", ton_balance=2), _mk_channel(s.id, "b")
        db.add_all([a, b])
        await db.commit()
        f = sanitize_filters({"with_balance": True})
        q = apply_catalog_filters(select(Channel.id).where(Channel.id.in_([a.id, b.id])), f)
        assert (await db.execute(q)).scalars().all() == [a.id]


def test_frontend_badges_filter_and_checklist_wiring():
    badges = (REPO_ROOT / "src/components/Balance/BalanceBadges.jsx").read_text(encoding="utf-8")
    assert "⭐" in badges and "Stars" in badges and "💎" in badges and "TON" in badges
    assert "зі слів продавця" in badges and "USDT" not in badges
    card = (REPO_ROOT / "src/components/Cards/CatalogCard.jsx").read_text(encoding="utf-8")
    assert "BalanceBadges" in card
    page = (REPO_ROOT / "src/layouts/ChannelDetailsPage.jsx").read_text(encoding="utf-8")
    assert "BalanceBadges" in page
    catalog = (REPO_ROOT / "src/layouts/CatalogPage.jsx").read_text(encoding="utf-8")
    assert "with_balance" in catalog and "з балансом" in catalog
    # one shared chip block feeds both the desktop bar and the mobile sheet
    assert catalog.count("{otherFilters}") >= 2
    sell = (REPO_ROOT / "src/components/SellForm.jsx").read_text(encoding="utf-8")
    assert "stars_balance" in sell and "ton_balance" in sell
    bundle = (REPO_ROOT / "src/layouts/BundleSellPage.jsx").read_text(encoding="utf-8")
    assert "channel_balances" in bundle
    moder = (REPO_ROOT / "src/layouts/ModerCabinet.jsx").read_text(encoding="utf-8")
    assert "stars_balance" in moder and "BalanceBadges" in moder
    tc = (REPO_ROOT / "src/components/Deal/TransferChecklist.jsx").read_text(encoding="utf-8")
    assert "Баланс не відповідає" in tc and "reportBalanceMismatch" in tc


# ── Checklist (pure) ───────────────────────────────────────────────────

def _deal(**kw):
    base = dict(id=31, status=DealStatus.channel_transferring, buyer_id=BUYER_ID, seller_id=SELLER_ID,
                buyer_confirmed_transfer=True, seller_confirmed_transfer=True,
                balance_stars=None, balance_ton=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _items(done=(), with_balance_row=False):
    defs = list(cl.CHECKLIST_ITEMS) + ([cl.BALANCE_ITEM] if with_balance_row else [])
    return [SimpleNamespace(key=d.key, side=d.side, required=d.required, done=d.key in set(done)) for d in defs]


def test_no_balance_deal_unchanged_like_existing_deals():
    d = _deal()  # deals #3, #6, #29 …: balance NULL
    assert not cl.deal_has_balance(d)
    assert [x.key for x in cl.defs_for_side(cl.SIDE_BUYER, d)] == [x.key for x in cl.defs_for_side(cl.SIDE_BUYER)]
    assert cl.can_advance_to_awaiting_payout(d, _items(BASE_REQUIRED))
    with pytest.raises(cl.ChecklistError) as e:
        cl.check_toggle_allowed(d, BUYER_ID, cl.BALANCE_ITEM_KEY)
    assert e.value.http_status == 404


@pytest.mark.parametrize("snap", [{"balance_stars": 100}, {"balance_ton": 0.5},
                                  {"balance_stars": 7, "balance_ton": 2.0}])
def test_balance_item_blocks_payout_until_buyer_confirms(snap):
    d = _deal(**snap)
    assert cl.deal_has_balance(d)
    buyer_keys = [x.key for x in cl.defs_for_side(cl.SIDE_BUYER, d)]
    assert buyer_keys[-1] == "balance_ok"
    assert cl.ITEMS_BY_KEY["balance_ok"].label == "Баланс Stars/TON на місці"
    # rows missing → fail-closed
    assert not cl.can_advance_to_awaiting_payout(d, _items(BASE_REQUIRED))
    # row present but open
    assert not cl.can_advance_to_awaiting_payout(d, _items(BASE_REQUIRED, with_balance_row=True))
    assert [x.key for x in cl.open_required_defs(_items(BASE_REQUIRED, True), cl.SIDE_BUYER, d)] == ["balance_ok"]
    assert cl.pending_sides(d, _items(BASE_REQUIRED, True)) == [cl.SIDE_BUYER]
    # buyer cannot confirm receipt while it is open; seller still can
    with pytest.raises(cl.ChecklistError) as e:
        cl.check_confirm_allowed(d, BUYER_ID, _items(BASE_REQUIRED, True))
    assert "Баланс Stars/TON на місці" in e.value.message
    assert cl.check_confirm_allowed(d, SELLER_ID, _items(BASE_REQUIRED, True)) == cl.SIDE_SELLER
    # only buyer may tick it
    with pytest.raises(cl.ChecklistError):
        cl.check_toggle_allowed(d, SELLER_ID, "balance_ok")
    assert cl.check_toggle_allowed(d, BUYER_ID, "balance_ok")[1] == cl.SIDE_BUYER
    # done → payout allowed as before
    assert cl.can_advance_to_awaiting_payout(d, _items(BASE_REQUIRED + ["balance_ok"], True))


def test_existing_balance_row_is_fail_closed_even_without_deal_arg():
    items = _items(BASE_REQUIRED, with_balance_row=True)
    assert not cl.all_required_done(items)


def test_snapshot_helpers():
    ch = SimpleNamespace(stars_balance=1500, ton_balance=12.5)
    assert cl.balance_snapshot(ch) == {"balance_stars": 1500, "balance_ton": 12.5}
    assert cl.balance_snapshot(SimpleNamespace(stars_balance=0, ton_balance=None)) == {
        "balance_stars": None, "balance_ton": None}
    chs = [SimpleNamespace(stars_balance=5, ton_balance=None), SimpleNamespace(stars_balance=None, ton_balance=1.25), None]
    assert cl.bundle_balance_snapshot(chs) == {"balance_stars": 5, "balance_ton": 1.25}
    assert cl.bundle_balance_snapshot([SimpleNamespace(stars_balance=None, ton_balance=None)]) == {
        "balance_stars": None, "balance_ton": None}
    assert cl.format_balance(1500, 12.5) == "⭐ 1500 Stars, 💎 12.5 TON"


# ── End-to-end with DB: snapshot, gate, dispute ─────────────────────────

class _FakeBot:
    def __init__(self, *a, **kw):
        self.session = SimpleNamespace(close=AsyncMock())

    async def send_message(self, *a, **kw):
        return SimpleNamespace(message_id=1)


async def _seed_users(db):
    from app.models.user import User
    s = User(first_name="Seller", telegram_id=3111)
    b = User(first_name="Buyer", telegram_id=3112)
    db.add_all([s, b])
    await db.commit()
    return s, b


@pytest.mark.asyncio
async def test_deal_snapshot_gate_and_mismatch_dispute(pg_orm, monkeypatch):
    from app.models.deal import DealStatus
    cl = importlib.import_module("app.services.deal_checklist")
    import aiogram
    from fastapi import HTTPException
    from app.models.channel import Channel
    from app.models.deal import Deal
    from app.models.user import User
    from app.schemas.deal import DealCreate

    deals_router = importlib.import_module("app.routers.deals")
    monkeypatch.setattr(aiogram, "Bot", _FakeBot)
    monkeypatch.setattr(deals_router, "generate_escrow_wallet", lambda: ("TESCROW31", "enc"))
    import app.services.channel_stats as cs
    monkeypatch.setattr(cs, "get_telethon_health", lambda: {"ok": False})

    async with pg_orm.session() as db:
        s, b = await _seed_users(db)
        ch = _mk_channel(s.id, "bal31", stars_balance=1500, ton_balance=12.5)
        plain = _mk_channel(s.id, "plain31")
        db.add_all([ch, plain])
        await db.commit()
        sid, bid, chid, plain_id = s.id, b.id, ch.id, plain.id

    async with pg_orm.session() as db:
        buyer = await db.get(User, bid)
        resp = await deals_router.create_deal(DealCreate(channel_id=chid), user=buyer, db=db)
        assert resp.balance_stars == 1500 and resp.balance_ton == 12.5
        deal_id = resp.id
        resp2 = await deals_router.create_deal(DealCreate(channel_id=plain_id), user=buyer, db=db)
        plain_deal_id = resp2.id
        assert resp2.balance_stars is None and resp2.balance_ton is None

    # later lot edit does not change the snapshot
    async with pg_orm.session() as db:
        c = await db.get(Channel, chid)
        c.stars_balance, c.ton_balance = 1, None
        for did in (deal_id, plain_deal_id):
            d = await db.get(Deal, did)
            d.status = DealStatus.paid
            d.paid_at = datetime(2026, 10, 17, 12, 0)
        await db.commit()

    async with pg_orm.session() as db:
        d = await db.get(Deal, deal_id)
        assert d.balance_stars == 1500 and d.balance_ton == 12.5
        buyer = await db.get(User, bid)
        seller = await db.get(User, sid)
        chk = await deals_router.get_deal_checklist(deal_id, user=buyer, db=db)
        assert [i.key for i in chk.buyer.items][-1] == "balance_ok"
        assert chk.balance_stars == 1500 and chk.balance_ton == 12.5
        plain_chk = await deals_router.get_deal_checklist(plain_deal_id, user=buyer, db=db)
        assert "balance_ok" not in [i.key for i in plain_chk.buyer.items]

    # tick everything except balance_ok; both sides attempt to confirm → stays transferring
    async with pg_orm.session() as db:
        buyer = await db.get(User, bid)
        seller = await db.get(User, sid)
        for d_ in cl.CHECKLIST_ITEMS:
            if not d_.required:
                continue
            who = seller if d_.side == cl.SIDE_SELLER else buyer
            await deals_router.toggle_deal_checklist_item(deal_id, d_.key, body=None, user=who, db=db)
        await deals_router._confirm_transfer_impl(deal_id, seller, db)
        with pytest.raises(HTTPException) as e:
            await deals_router._confirm_transfer_impl(deal_id, buyer, db)
        assert e.value.status_code == 400 and "Баланс Stars/TON на місці" in e.value.detail
    async with pg_orm.session() as db:
        d = await db.get(Deal, deal_id)
        assert d.status == DealStatus.channel_transferring  # payout blocked
        assert not d.buyer_confirmed_transfer

    # seller can't report mismatch; buyer can → dispute via existing flow
    async with pg_orm.session() as db:
        seller = await db.get(User, sid)
        with pytest.raises(HTTPException) as e:
            await deals_router.report_balance_mismatch(deal_id, user=seller, db=db)
        assert e.value.status_code == 403
        buyer = await db.get(User, bid)
        with pytest.raises(HTTPException) as e:
            await deals_router.report_balance_mismatch(plain_deal_id, user=buyer, db=db)
        assert e.value.status_code == 400
        out = await deals_router.report_balance_mismatch(deal_id, user=buyer, db=db)
        assert out.status == "disputed"
    async with pg_orm.session() as db:
        d = await db.get(Deal, deal_id)
        assert d.status == DealStatus.disputed
        assert "Баланс не відповідає" in d.dispute_reason and "1500" in d.dispute_reason


@pytest.mark.asyncio
async def test_balance_ok_tick_unblocks_payout(pg_orm, monkeypatch):
    from app.models.deal import DealStatus
    cl = importlib.import_module("app.services.deal_checklist")
    import aiogram
    from app.models.deal import Deal
    from app.models.user import User
    from app.schemas.deal import DealCreate

    deals_router = importlib.import_module("app.routers.deals")
    monkeypatch.setattr(aiogram, "Bot", _FakeBot)
    monkeypatch.setattr(deals_router, "generate_escrow_wallet", lambda: ("TESCROW32", "enc"))
    import app.services.channel_stats as cs
    monkeypatch.setattr(cs, "get_telethon_health", lambda: {"ok": False})

    async with pg_orm.session() as db:
        s, b = await _seed_users(db)
        ch = _mk_channel(s.id, "tonly31", ton_balance=3)
        db.add(ch)
        await db.commit()
        sid, bid, chid = s.id, b.id, ch.id
    async with pg_orm.session() as db:
        resp = await deals_router.create_deal(DealCreate(channel_id=chid), user=await db.get(User, bid), db=db)
        deal_id = resp.id
        d = await db.get(Deal, deal_id)
        d.status = DealStatus.paid
        await db.commit()
    async with pg_orm.session() as db:
        buyer, seller = await db.get(User, bid), await db.get(User, sid)
        for d_ in (*cl.CHECKLIST_ITEMS, cl.BALANCE_ITEM):
            if d_.required:
                who = seller if d_.side == cl.SIDE_SELLER else buyer
                await deals_router.toggle_deal_checklist_item(deal_id, d_.key, body=None, user=who, db=db)
        await deals_router._confirm_transfer_impl(deal_id, seller, db)
        await deals_router._confirm_transfer_impl(deal_id, buyer, db)
    async with pg_orm.session() as db:
        assert (await db.get(Deal, deal_id)).status == DealStatus.awaiting_payout


@pytest.mark.asyncio
async def test_bundle_per_channel_balance_create_and_update(pg_orm):
    from fastapi import HTTPException
    from app.models.user import User
    from app.schemas.bundle import BundleCreate, BundleUpdate

    bundles_router = importlib.import_module("app.routers.bundles")
    async with pg_orm.session() as db:
        u = User(first_name="S", telegram_id=3121)
        db.add(u)
        await db.commit()
        uid = u.id
    async with pg_orm.session() as db:
        user = await db.get(User, uid)
        resp = await bundles_router.create_bundle(BundleCreate(
            name="Сітка", price=100, channel_links=["@b31a", "@b31b"],
            channel_balances=[{"stars_balance": 250}, {"ton_balance": 1.5}],
        ), user=user, db=db)
        by_link = {c.telegram_link: c for c in resp.channels}
        assert by_link["b31a"].stars_balance == 250 and by_link["b31a"].ton_balance is None
        assert by_link["b31b"].ton_balance == 1.5
        bid, cid_a = resp.id, by_link["b31a"].id
    async with pg_orm.session() as db:
        user = await db.get(User, uid)
        out = await bundles_router.update_bundle(bid, BundleUpdate(
            channel_balances=[{"channel_id": cid_a, "stars_balance": None, "ton_balance": 3}],
        ), user=user, db=db)
        a = next(c for c in out.channels if c.id == cid_a)
        assert a.stars_balance is None and a.ton_balance == 3
    async with pg_orm.session() as db:
        user = await db.get(User, uid)
        with pytest.raises(HTTPException) as e:
            await bundles_router.update_bundle(bid, BundleUpdate(
                channel_balances=[{"channel_id": 999999, "stars_balance": 1}]), user=user, db=db)
        assert e.value.status_code == 400
