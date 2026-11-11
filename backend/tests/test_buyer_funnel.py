"""Buyer funnel (task A+B): staff/seller exclusion, new events + dedupe, payment-requested notify once."""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.utils.timeutil import utcnow_naive


async def _activity_client(pg_orm, monkeypatch):
    from fastapi import FastAPI
    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", pg_orm.session)
    mod = importlib.import_module("app.routers.user_activity")
    importlib.import_module("app.services.user_activity").limiter.reset()
    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    return app, AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_funnel_excludes_staff_and_seller_own_lot(pg_orm, monkeypatch):
    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus
    from app.models.user import User, UserRole
    from app.services import user_activity as ua
    from app.utils.security import create_access_token

    async with pg_orm.session() as db:
        seller = User(first_name="S", telegram_id=101)
        buyer = User(first_name="B", telegram_id=102)
        admin = User(first_name="A", telegram_id=103, role=UserRole.admin)
        mod = User(first_name="M", telegram_id=104, role=UserRole.moderator)
        db.add_all([seller, buyer, admin, mod])
        await db.commit()
        ch = Channel(seller_id=seller.id, telegram_link="https://t.me/funnel-lot",
                     channel_name="Lot", category="Новини/ЗМІ", price=50,
                     subscribers_count=100, status=ChannelStatus.approved)
        db.add(ch)
        await db.commit()
        ids = dict(seller=seller.id, buyer=buyer.id, admin=admin.id, mod=mod.id, ch=ch.id)

    app, cl = await _activity_client(pg_orm, monkeypatch)
    tok = lambda uid: {"Authorization": f"Bearer {create_access_token({'sub': str(uid)})}"}
    async with cl:
        await cl.post("/api/track/event", json={"type": "visit", "page": "home"}, headers=tok(ids["buyer"]))
        await cl.post("/api/track/event", json={"type": "channel_view", "channel_id": ids["ch"]}, headers=tok(ids["buyer"]))
        await cl.post("/api/track/event", json={"type": "buy_click", "channel_id": ids["ch"]}, headers=tok(ids["buyer"]))
        # staff noise — must not enter any step
        for uid in (ids["admin"], ids["mod"]):
            await cl.post("/api/track/event", json={"type": "visit", "page": "catalog"}, headers=tok(uid))
            await cl.post("/api/track/event", json={"type": "channel_view", "channel_id": ids["ch"]}, headers=tok(uid))
            await cl.post("/api/track/event", json={"type": "buy_click", "channel_id": ids["ch"]}, headers=tok(uid))
        # seller looking at / clicking Buy on their own lot — dropped from those steps
        await cl.post("/api/track/event", json={"type": "visit", "page": "channel"}, headers=tok(ids["seller"]))
        await cl.post("/api/track/event", json={"type": "channel_view", "channel_id": ids["ch"]}, headers=tok(ids["seller"]))
        await cl.post("/api/track/event", json={"type": "buy_click", "channel_id": ids["ch"]}, headers=tok(ids["seller"]))

    async with pg_orm.session() as db:
        now = utcnow_naive()
        db.add(Deal(
            channel_id=ids["ch"], buyer_id=ids["buyer"], seller_id=ids["seller"],
            status=DealStatus.paid, escrow_wallet_address="T" * 34,
            escrow_private_key_encrypted="x", amount_usdt=50, service_fee=1.5, paid_at=now,
        ))
        # staff as a buyer must not inflate deal_start / payment
        db.add(Deal(
            channel_id=ids["ch"], buyer_id=ids["admin"], seller_id=ids["seller"],
            status=DealStatus.paid, escrow_wallet_address="A" * 34,
            escrow_private_key_encrypted="x", amount_usdt=50, service_fee=1.5, paid_at=now,
        ))
        await db.commit()
        f = await ua.funnel(db, 7, now=now)

    users = {s["step"]: s["users"] for s in f["steps"]}
    assert [s["step"] for s in f["steps"]] == [
        "visit", "channel_view", "buy_click", "deal_start", "payment",
    ]
    assert f["steps"][2]["label"] == "Натиснув Купити"
    # visit: buyer + seller (seller visit is kept; own-lot filter is view/buy only)
    assert users["visit"] == 2
    assert users["channel_view"] == 1
    assert users["buy_click"] == 1
    assert users["deal_start"] == 1
    assert users["payment"] == 1


@pytest.mark.asyncio
async def test_buy_funnel_events_require_channel_and_dedupe(pg_orm, monkeypatch):
    from app.models.activity import UserEvent
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User
    from app.utils.security import create_access_token

    async with pg_orm.session() as db:
        buyer = User(first_name="B", telegram_id=201)
        seller = User(first_name="S", telegram_id=202)
        db.add_all([seller, buyer])
        await db.commit()
        ch = Channel(seller_id=seller.id, telegram_link="https://t.me/ev",
                     channel_name="E", category="Новини/ЗМІ", price=10,
                     subscribers_count=10, status=ChannelStatus.approved)
        db.add(ch)
        await db.commit()
        ids = dict(buyer=buyer.id, ch=ch.id)

    app, cl = await _activity_client(pg_orm, monkeypatch)
    tok = {"Authorization": f"Bearer {create_access_token({'sub': str(ids['buyer'])})}"}
    async with cl:
        for typ in ("buy_click", "login_prompt_open", "login_success_from_buy"):
            assert (await cl.post("/api/track/event", json={"type": typ}, headers=tok)).status_code == 400
            r1 = await cl.post("/api/track/event", json={"type": typ, "channel_id": ids["ch"]}, headers=tok)
            r2 = await cl.post("/api/track/event", json={"type": typ, "channel_id": ids["ch"]}, headers=tok)
            assert r1.status_code == 204 and r2.status_code == 204

    async with pg_orm.session() as db:
        rows = (await db.execute(select(UserEvent.event_type))).scalars().all()
        # one of each type (second click dropped by 10-min channel-scoped dedupe)
        assert sorted(rows) == ["buy_click", "login_prompt_open", "login_success_from_buy"]


@pytest.mark.asyncio
async def test_confirm_ready_notifies_buyer_once_after_commit(pg_orm, monkeypatch):
    """Notify fires once on created → payment_pending, after commit; a failure does not roll back."""
    from app.config import settings
    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus
    from app.models.user import User

    deals = importlib.import_module("app.routers.deals")
    bot_main = importlib.import_module("bot.main")

    calls = []

    async def _spy(bot, deal, buyer, seller):
        calls.append((deal.id, getattr(buyer, "id", None), deal.status, deal.escrow_wallet_address))
        return True

    monkeypatch.setattr(settings, "bot_token_alerts", "123:TEST-NOTIFY")
    monkeypatch.setattr(bot_main, "notify_payment_requested", _spy)

    class FakeBot:
        def __init__(self, token: str = "", **_k):
            self.token = token
            self.session = SimpleNamespace(close=AsyncMock())

    monkeypatch.setattr(deals, "Bot", FakeBot, raising=False)
    # hook imports Bot from aiogram inside the function — patch the module used after import
    import aiogram
    monkeypatch.setattr(aiogram, "Bot", FakeBot)

    async with pg_orm.session() as db:
        buyer = User(first_name="Buyer", telegram_id=8001)
        seller = User(first_name="Seller", telegram_id=8002)
        db.add_all([buyer, seller])
        await db.flush()
        ch = Channel(seller_id=seller.id, telegram_link="https://t.me/n", channel_name="N",
                     category="news", price=20, status=ChannelStatus.approved)
        db.add(ch)
        await db.flush()
        deal = Deal(
            channel_id=ch.id, buyer_id=buyer.id, seller_id=seller.id,
            status=DealStatus.created, buyer_ready=True, seller_ready=False,
            escrow_wallet_address="TNOTIFYADDRESS000000000000000001",
            escrow_private_key_encrypted="enc", amount_usdt=20, service_fee=0.6,
        )
        db.add(deal)
        await db.commit()
        deal_id, seller_id, buyer_id = deal.id, seller.id, buyer.id

    async with pg_orm.session() as db:
        seller = await db.get(User, seller_id)
        resp = await deals.confirm_ready(deal_id, user=seller, db=db)

    assert resp.status == DealStatus.payment_pending
    assert resp.payment_deadline_at is not None
    assert len(calls) == 1 and calls[0][0] == deal_id and calls[0][1] == buyer_id
    # already payment_pending: second confirm is 400 and must not notify again
    async with pg_orm.session() as db:
        seller = await db.get(User, seller_id)
        with pytest.raises(Exception):
            await deals.confirm_ready(deal_id, user=seller, db=db)
    assert len(calls) == 1

    # notify failure after commit must not revert payment_pending
    calls.clear()

    async def _boom(*_a, **_k):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(bot_main, "notify_payment_requested", _boom)
    async with pg_orm.session() as db:
        buyer = User(first_name="B2", telegram_id=8003)
        seller = User(first_name="S2", telegram_id=8004)
        db.add_all([buyer, seller])
        await db.flush()
        ch = Channel(seller_id=seller.id, telegram_link="https://t.me/n2", channel_name="N2",
                     category="news", price=20, status=ChannelStatus.approved)
        db.add(ch)
        await db.flush()
        deal = Deal(
            channel_id=ch.id, buyer_id=buyer.id, seller_id=seller.id,
            status=DealStatus.created, buyer_ready=True, seller_ready=False,
            escrow_wallet_address="TNOTIFYADDRESS000000000000000002",
            escrow_private_key_encrypted="enc", amount_usdt=20, service_fee=0.6,
        )
        db.add(deal)
        await db.commit()
        deal_id, seller_id = deal.id, seller.id

    async with pg_orm.session() as db:
        seller = await db.get(User, seller_id)
        resp = await deals.confirm_ready(deal_id, user=seller, db=db)
    assert resp.status == DealStatus.payment_pending


@pytest.mark.asyncio
async def test_no_retroactive_payment_notify_for_existing_pending(pg_orm, monkeypatch):
    """A deal already in payment_pending is not notified just because the hook exists."""
    from app.config import settings
    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus
    from app.models.user import User

    deals = importlib.import_module("app.routers.deals")
    bot_main = importlib.import_module("bot.main")
    calls = []

    async def _spy(*_a, **_k):
        calls.append(1)
        return True

    monkeypatch.setattr(settings, "bot_token_alerts", "123:TEST-NOTIFY")
    monkeypatch.setattr(bot_main, "notify_payment_requested", _spy)

    async with pg_orm.session() as db:
        buyer = User(first_name="B", telegram_id=9001)
        seller = User(first_name="S", telegram_id=9002)
        db.add_all([buyer, seller])
        await db.flush()
        ch = Channel(seller_id=seller.id, telegram_link="https://t.me/old", channel_name="Old",
                     category="news", price=20, status=ChannelStatus.approved)
        db.add(ch)
        await db.flush()
        deal = Deal(
            channel_id=ch.id, buyer_id=buyer.id, seller_id=seller.id,
            status=DealStatus.payment_pending, buyer_ready=True, seller_ready=True,
            escrow_wallet_address="TNOTIFYADDRESS000000000000000099",
            escrow_private_key_encrypted="enc", amount_usdt=20, service_fee=0.6,
        )
        db.add(deal)
        await db.commit()
        deal_id, seller_id = deal.id, seller.id

    async with pg_orm.session() as db:
        seller = await db.get(User, seller_id)
        with pytest.raises(Exception):
            await deals.confirm_ready(deal_id, user=seller, db=db)
    assert calls == []


@pytest.mark.asyncio
async def test_notify_payment_requested_text_is_ukrainian_and_has_deal_link(monkeypatch):
    from bot.main import notify_payment_requested
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_url", "https://tgsell.me")
    sent = []

    class FakeBot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text, kw))

    deal = SimpleNamespace(id=42, amount_usdt="15.5", escrow_wallet_address="TABC<script>")
    buyer = SimpleNamespace(id=1, telegram_id=555)
    ok = await notify_payment_requested(FakeBot(), deal, buyer, SimpleNamespace())
    assert ok is True
    chat, text, kw = sent[0]
    assert chat == 555
    assert kw.get("parse_mode")
    assert "Можна оплачувати угоду #42" in text
    assert "15.5 USDT" in text
    assert "TRC-20" in text
    assert "https://tgsell.me/deal/42" in text
    assert "<script>" not in text
    assert "TABC&lt;script&gt;" in text
