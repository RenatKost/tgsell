"""«Гарант для зовнішніх угод» (/escrow): creation, privacy, token+username access, minimum, fee."""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


class FakeBot:
    def __init__(self, token, **_kw):
        self.session = SimpleNamespace(close=AsyncMock())

    async def send_message(self, *a, **k):
        return None


async def _setup(orm, monkeypatch):
    from fastapi import FastAPI, HTTPException
    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", orm.session)
    from app.config import settings
    monkeypatch.setattr(settings, "bot_token_alerts", "test-token")
    monkeypatch.setattr(settings, "frontend_url", "https://tgsell.test/")
    monkeypatch.setattr(settings, "service_fee_percent", 3.0)
    monkeypatch.setattr(importlib.import_module("aiogram"), "Bot", FakeBot)
    esc = importlib.import_module("app.routers.external_escrow")
    monkeypatch.setattr(esc, "generate_escrow_wallet", lambda: ("TTestEscrowAddr0000000000000000000", "enc"))
    sec = importlib.import_module("app.utils.security")
    deals = importlib.import_module("app.routers.deals")
    activity = importlib.import_module("app.routers.activity")
    seo = importlib.import_module("app.routers.seo")
    app = FastAPI()
    app.include_router(esc.router, prefix="/api")
    app.include_router(deals.router, prefix="/api")
    app.include_router(activity.router, prefix="/api")
    app.include_router(seo.router)
    app.dependency_overrides[db_mod.get_db] = orm.get_db
    cur = SimpleNamespace(user=None)

    async def current():
        if cur.user is None:
            raise HTTPException(status_code=401, detail="no")
        return cur.user

    app.dependency_overrides[sec.get_current_user] = current
    app.dependency_overrides[sec.get_current_user_or_blocked] = current
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t"), cur


async def _users(orm):
    from app.models.user import User
    async with orm.session() as db:
        seller = User(first_name="Seller", username="seller_one", telegram_id=901)
        buyer = User(first_name="Buyer", username="Buyer_Ivan", telegram_id=902)
        other = User(first_name="Other", username="someone_else", telegram_id=903)
        google = User(first_name="G", google_id="g1", email="g@x.y")
        db.add_all([seller, buyer, other, google])
        await db.commit()
        return seller, buyer, other, google


BODY = {"channel_link": "https://t.me/my_channel", "price_usdt": 100, "buyer_username": "@buyer_ivan"}


@pytest.mark.asyncio
async def test_create_minimum_fee_and_auth(orm, monkeypatch):
    client, cur = await _setup(orm, monkeypatch)
    seller, buyer, other, google = await _users(orm)
    async with client:
        assert (await client.post("/api/escrow/offers", json=BODY)).status_code == 401
        cur.user = google  # not logged in via Telegram bot
        assert (await client.post("/api/escrow/offers", json=BODY)).status_code == 403
        cur.user = seller
        r = await client.post("/api/escrow/offers", json={**BODY, "price_usdt": 4.99})
        assert r.status_code == 422 and "5" in r.json()["detail"]
        assert (await client.post("/api/escrow/offers", json={**BODY, "channel_link": "https://evil.com/x"})).status_code == 422
        assert (await client.post("/api/escrow/offers", json={**BODY, "buyer_username": "a b"})).status_code == 422
        assert (await client.post("/api/escrow/offers", json={**BODY, "buyer_username": "@Seller_One"})).status_code == 400
        r = await client.post("/api/escrow/offers", json={**BODY, "price_usdt": 5})
        assert r.status_code == 201
        r = await client.post("/api/escrow/offers", json=BODY)
        o = r.json()
        assert o["fee_percent"] == 3.0 and o["service_fee"] == 3.0 and o["seller_receives"] == 97.0
        assert o["buyer_username"] == "buyer_ivan" and o["status"] == "open"
        token = o["buyer_url"].rsplit("/", 1)[1]
        assert o["buyer_url"].startswith("https://tgsell.test/escrow/") and len(token) >= 32
        # fee follows settings
        from app.config import settings
        monkeypatch.setattr(settings, "service_fee_percent", 5.0)
        o2 = (await client.post("/api/escrow/offers", json=BODY)).json()
        assert o2["service_fee"] == 5.0 and o2["fee_percent"] == 5.0
        assert o2["buyer_url"] != o["buyer_url"]  # unpredictable unique tokens
        mine = (await client.get("/api/escrow/offers/my")).json()
        assert len(mine) == 3


@pytest.mark.asyncio
async def test_access_only_by_token_and_username_then_standard_deal(orm, monkeypatch):
    from app.models.deal import Deal, DealStatus
    client, cur = await _setup(orm, monkeypatch)
    seller, buyer, other, google = await _users(orm)
    async with client:
        cur.user = seller
        o = (await client.post("/api/escrow/offers", json=BODY)).json()
        token = o["buyer_url"].rsplit("/", 1)[1]
        # seller himself, other user, user without username, wrong token → same 404
        for u in (seller, other, google):
            cur.user = u
            assert (await client.get(f"/api/escrow/invite/{token}")).status_code == 404
            assert (await client.post(f"/api/escrow/invite/{token}/accept")).status_code == 404
        cur.user = buyer
        assert (await client.get("/api/escrow/invite/WRONGTOKEN")).status_code == 404
        assert (await client.get(f"/api/escrow/invite/{token[:-1]}")).status_code == 404
        v = (await client.get(f"/api/escrow/invite/{token}")).json()
        assert v["price_usdt"] == 100 and v["service_fee"] == 3.0 and "buyer_url" not in v and "token" not in str(v)
        r = await client.post(f"/api/escrow/invite/{token}/accept")
        deal_id = r.json()["deal_id"]
        # idempotent
        assert (await client.post(f"/api/escrow/invite/{token}/accept")).json()["deal_id"] == deal_id
        async with orm.session() as db:
            d = await db.get(Deal, deal_id)
            assert d.status == DealStatus.created and d.channel_id is None and d.bundle_id is None
            assert d.buyer_id == buyer.id and d.seller_id == seller.id
            assert d.amount_usdt == 100 and d.service_fee == 3.0
            assert d.escrow_wallet_address.startswith("T") and d.payment_deadline_at is not None
            assert d.external_channel_link == "https://t.me/my_channel"
        dr = (await client.get(f"/api/deals/{deal_id}")).json()
        assert dr["is_external"] and dr["channel_link"] == "https://t.me/my_channel"
        # standard flow continues: ready step works on the external deal
        assert (await client.post(f"/api/deals/{deal_id}/confirm-ready")).status_code == 200
        cur.user = seller
        assert (await client.post(f"/api/escrow/offers/{o['id']}/cancel")).status_code == 400


@pytest.mark.asyncio
async def test_cancelled_offer_cannot_be_accepted(orm, monkeypatch):
    client, cur = await _setup(orm, monkeypatch)
    seller, buyer, *_ = await _users(orm)
    async with client:
        cur.user = seller
        o = (await client.post("/api/escrow/offers", json=BODY)).json()
        assert (await client.post(f"/api/escrow/offers/{o['id']}/cancel")).status_code == 200
        cur.user = buyer
        token = o["buyer_url"].rsplit("/", 1)[1]
        assert (await client.post(f"/api/escrow/invite/{token}/accept")).status_code == 400


@pytest.mark.asyncio
async def test_private_not_in_public_surfaces(orm, monkeypatch):
    client, cur = await _setup(orm, monkeypatch)
    seller, buyer, *_ = await _users(orm)
    async with client:
        cur.user = seller
        o = (await client.post("/api/escrow/offers", json=BODY)).json()
        token = o["buyer_url"].rsplit("/", 1)[1]
        cur.user = buyer
        await client.post(f"/api/escrow/invite/{token}/accept")
        cur.user = None
        sm = (await client.get("/sitemap.xml")).text
        assert "/escrow<" in sm and token not in sm and "my_channel" not in sm
        assert "Disallow: /escrow/" in (await client.get("/robots.txt")).text
        feed = (await client.get("/api/activity/feed")).text
        assert "придбав канал за 100" not in feed
    # no Channel row → never in catalog / search
    from sqlalchemy import func, select
    from app.models.channel import Channel
    async with orm.session() as db:
        assert (await db.execute(select(func.count(Channel.id)))).scalar() == 0


def test_spa_meta_invite_noindex_and_no_token_in_canonical():
    from app.utils.spa_meta import inject_meta, ESCROW_INVITE_META
    html = ('<html><head><title>x</title><link rel="canonical" href="https://tgsell.me/"/>'
            '<meta name="robots" content="index"/><meta property="og:url" content="u"/></head>'
            '<body><div id="root"></div></body></html>')
    out = inject_meta(html, "/escrow/SECRETtoken123", dict(ESCROW_INVITE_META))
    assert "SECRETtoken123" not in out and "noindex" in out
    from app.utils.spa_meta import EXTRA_ROUTE_META
    assert "/escrow" in EXTRA_ROUTE_META


def test_helpers():
    from app.services.external_escrow import normalize_channel_link as L, normalize_username as U, calc_fee
    assert L("@my_chan") == "https://t.me/my_chan" and L("t.me/+AbCdEf123456") == "https://t.me/+AbCdEf123456"
    assert L("https://example.com/x") is None and L("") is None
    assert U("@Ivan_B") == "ivan_b" and U("ab") is None and U("t.me/ivan_b") == "ivan_b"
    assert calc_fee(100, 3) == 3.0 and calc_fee(5, 3) == 0.15


def test_migration_chain():
    from pathlib import Path
    v = Path(__file__).resolve().parents[1] / "alembic/versions"
    src = (v / "0050_external_escrow.py").read_text()
    assert 'revision = "0050"' in src and 'down_revision = "0049"' in src
