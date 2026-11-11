"""Price offers: rights, anti-spam, 48h expiry, accept/decline, no public leak, deal amount snapshot."""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.utils.timeutil import utcnow_naive


def test_parse_amount_bounds():
    from app.services.price_offers import OfferError, parse_amount

    assert parse_amount(50, 100) == 50.0
    assert parse_amount(99.99, 100) == 99.99
    with pytest.raises(OfferError, match="нижчою за ціну"):
        parse_amount(100, 100)
    with pytest.raises(OfferError, match="50%"):
        parse_amount(49.99, 100)
    with pytest.raises(OfferError, match="50%"):
        parse_amount(30, 100)
    with pytest.raises(OfferError, match="0,01"):
        parse_amount(40.123, 100)


async def _seed(db, *, lots=1, price=100.0):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User

    seller = User(first_name="Seller", telegram_id=51001)
    buyer = User(first_name="Buyer", telegram_id=51002)
    other = User(first_name="Other", telegram_id=51003)
    db.add_all([seller, buyer, other])
    await db.flush()
    channels = []
    for i in range(lots):
        ch = Channel(
            seller_id=seller.id,
            telegram_link=f"https://t.me/poffer{i}-{id(seller)}",
            channel_name=f"Lot {i}",
            category="Новини/ЗМІ",
            price=price,
            subscribers_count=100,
            status=ChannelStatus.approved,
        )
        db.add(ch)
        channels.append(ch)
    await db.commit()
    return SimpleNamespace(
        seller_id=seller.id, buyer_id=buyer.id, other_id=other.id,
        channels=channels, ch_id=channels[0].id,
    )


async def _client(pg_orm, monkeypatch, *extra_modules):
    from fastapi import FastAPI
    from app.config import settings
    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", pg_orm.session)
    monkeypatch.setattr(settings, "bot_token_alerts", "123:TEST-OFFER")
    monkeypatch.setattr(settings, "frontend_url", "https://tgsell.me")
    monkeypatch.setattr(settings, "service_fee_percent", 3.0)

    for name in ("user", "channel", "deal", "price_offer", "bundle", "auction"):
        importlib.import_module(f"app.models.{name}")
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
    deals = importlib.import_module("app.routers.deals")
    monkeypatch.setattr(deals, "generate_escrow_wallet", lambda: ("TOFFERESCROWADDR00000000000000001", "enc"))

    import aiogram
    class FakeBot:
        sent = []
        def __init__(self, token="", **_k):
            self.session = SimpleNamespace(close=AsyncMock())
        async def send_message(self, chat_id, text, **kw):
            FakeBot.sent.append((chat_id, text, kw))
    FakeBot.sent = []
    monkeypatch.setattr(aiogram, "Bot", FakeBot)

    app = FastAPI()
    mods = ["app.routers.price_offers", "app.routers.deals", "app.routers.channels", "app.routers.user_activity", *extra_modules]
    for path in mods:
        mod = importlib.import_module(path)
        app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    return app, AsyncClient(transport=ASGITransport(app=app), base_url="http://t"), FakeBot


def _tok(uid):
    from app.utils.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': str(uid)})}"}


@pytest.mark.asyncio
async def test_guest_owner_and_stranger_permissions(pg_orm, monkeypatch):
    async with pg_orm.session() as db:
        ids = await _seed(db)
    app, cl, bot = await _client(pg_orm, monkeypatch)
    body = {"channel_id": ids.ch_id, "amount_usdt": 70}
    async with cl:
        assert (await cl.post("/api/price-offers", json=body)).status_code in (401, 403)
        assert (await cl.post("/api/price-offers", json=body, headers=_tok(ids.seller_id))).status_code == 400
        r = await cl.post("/api/price-offers", json=body, headers=_tok(ids.buyer_id))
        assert r.status_code == 201, r.text
        offer_id = r.json()["id"]
        # other buyer cannot read or decide
        assert (await cl.get(f"/api/price-offers/{offer_id}", headers=_tok(ids.other_id))).status_code == 403
        assert (await cl.post(f"/api/price-offers/{offer_id}/accept", headers=_tok(ids.other_id))).status_code == 403
        assert (await cl.post(f"/api/price-offers/{offer_id}/accept", headers=_tok(ids.buyer_id))).status_code == 403
        # seller inbox has it; other inbox is empty
        inbox_s = (await cl.get("/api/price-offers/inbox", headers=_tok(ids.seller_id))).json()
        inbox_o = (await cl.get("/api/price-offers/inbox", headers=_tok(ids.other_id))).json()
        assert [x["id"] for x in inbox_s] == [offer_id]
        assert inbox_o == []
        mine_o = (await cl.get("/api/price-offers/my", headers=_tok(ids.other_id))).json()
        assert mine_o == []


@pytest.mark.asyncio
async def test_antispam_one_pending_and_five_per_day(pg_orm, monkeypatch):
    async with pg_orm.session() as db:
        ids = await _seed(db, lots=6)
    app, cl, bot = await _client(pg_orm, monkeypatch)
    async with cl:
        h = _tok(ids.buyer_id)
        first = await cl.post("/api/price-offers", json={"channel_id": ids.channels[0].id, "amount_usdt": 70}, headers=h)
        assert first.status_code == 201, first.text
        dup = await cl.post("/api/price-offers", json={"channel_id": ids.channels[0].id, "amount_usdt": 60}, headers=h)
        assert dup.status_code == 400 and "активна пропозиція" in dup.json()["detail"]
        # four more on other lots (5 total), sixth rejected
        for ch in ids.channels[1:5]:
            r = await cl.post("/api/price-offers", json={"channel_id": ch.id, "amount_usdt": 70}, headers=h)
            assert r.status_code == 201, r.text
        sixth = await cl.post("/api/price-offers", json={"channel_id": ids.channels[5].id, "amount_usdt": 70}, headers=h)
        assert sixth.status_code == 400 and "5 пропозицій" in sixth.json()["detail"]


@pytest.mark.asyncio
async def test_expiry_blocks_accept_and_marks_expired(pg_orm, monkeypatch):
    from app.models.price_offer import PriceOffer, PriceOfferStatus

    async with pg_orm.session() as db:
        ids = await _seed(db)
    app, cl, bot = await _client(pg_orm, monkeypatch)
    async with cl:
        r = await cl.post("/api/price-offers", json={"channel_id": ids.ch_id, "amount_usdt": 70, "comment": "ok"},
                          headers=_tok(ids.buyer_id))
        assert r.status_code == 201
        offer_id = r.json()["id"]
        # 48h window is stored on the row
        assert r.json()["status"] == "pending"
        async with pg_orm.session() as db:
            offer = await db.get(PriceOffer, offer_id)
            offer.expires_at = utcnow_naive() - timedelta(minutes=1)
            await db.commit()
        acc = await cl.post(f"/api/price-offers/{offer_id}/accept", headers=_tok(ids.seller_id))
        assert acc.status_code == 400 and "Термін" in acc.json()["detail"]
    async with pg_orm.session() as db:
        offer = await db.get(PriceOffer, offer_id)
        assert offer.status == PriceOfferStatus.expired


@pytest.mark.asyncio
async def test_accept_decline_and_deal_uses_offer_amount_not_lot_price(pg_orm, monkeypatch):
    from app.models.channel import Channel
    from app.models.deal import Deal
    from app.models.price_offer import PriceOffer, PriceOfferStatus

    async with pg_orm.session() as db:
        ids = await _seed(db, price=200)
    app, cl, bot = await _client(pg_orm, monkeypatch)
    async with cl:
        created = await cl.post(
            "/api/price-offers",
            json={"channel_id": ids.ch_id, "amount_usdt": 120, "comment": "можу 120"},
            headers=_tok(ids.buyer_id),
        )
        assert created.status_code == 201, created.text
        offer_id = created.json()["id"]
        # seller notified after commit
        assert any("/cabinet?offers=1" in t for _, t, _ in bot.sent)

        dec = await cl.post(f"/api/price-offers/{offer_id}/decline", headers=_tok(ids.seller_id))
        assert dec.status_code == 200 and dec.json()["status"] == "declined"
        # cannot decline twice
        assert (await cl.post(f"/api/price-offers/{offer_id}/decline", headers=_tok(ids.seller_id))).status_code == 400

        # new offer after decline, then accept
        created2 = await cl.post(
            "/api/price-offers",
            json={"channel_id": ids.ch_id, "amount_usdt": 150},
            headers=_tok(ids.buyer_id),
        )
        assert created2.status_code == 201, created2.text
        offer2 = created2.json()["id"]
        acc = await cl.post(f"/api/price-offers/{offer2}/accept", headers=_tok(ids.seller_id))
        assert acc.status_code == 200 and acc.json()["status"] == "accepted"
        assert any(f"/channel/{ids.ch_id}?offer={offer2}" in t for _, t, _ in bot.sent)

        # lot public price unchanged
        pub = await cl.get(f"/api/channels/{ids.ch_id}")
        assert pub.status_code == 200
        assert pub.json()["price"] == 200
        assert "offers" not in pub.json()
        assert "150" not in str(pub.json())  # agreed amount must not leak on the public lot

        # stranger still cannot read the accepted offer
        assert (await cl.get(f"/api/price-offers/{offer2}", headers=_tok(ids.other_id))).status_code == 403

        # deal is created only after the buyer posts /api/deals with offer_id
        deal = await cl.post(
            "/api/deals",
            json={"channel_id": ids.ch_id, "offer_id": offer2},
            headers=_tok(ids.buyer_id),
        )
        assert deal.status_code == 201, deal.text
        body = deal.json()
        assert body["amount_usdt"] == 150
        assert abs(body["service_fee"] - 4.5) < 1e-6  # 3% of 150, same formula
        # second create from the same offer is rejected
        again = await cl.post(
            "/api/deals",
            json={"channel_id": ids.ch_id, "offer_id": offer2},
            headers=_tok(ids.buyer_id),
        )
        assert again.status_code == 400

    async with pg_orm.session() as db:
        ch = await db.get(Channel, ids.ch_id)
        assert ch.price == 200
        offer = await db.get(PriceOffer, offer2)
        assert offer.status == PriceOfferStatus.accepted and offer.deal_id == body["id"]
        d = await db.get(Deal, body["id"])
        assert d.amount_usdt == 150 and abs(d.service_fee - 4.5) < 1e-6


@pytest.mark.asyncio
async def test_public_api_does_not_leak_foreign_offers(pg_orm, monkeypatch):
    async with pg_orm.session() as db:
        ids = await _seed(db)
    app, cl, bot = await _client(pg_orm, monkeypatch)
    async with cl:
        r = await cl.post("/api/price-offers", json={"channel_id": ids.ch_id, "amount_usdt": 70, "comment": "secret-note"},
                          headers=_tok(ids.buyer_id))
        assert r.status_code == 201
        public = (await cl.get(f"/api/channels/{ids.ch_id}")).json()
        dumped = str(public)
        assert "secret-note" not in dumped
        assert "price_offers" not in dumped
        assert public.get("price") == 100
        # catalog list
        listing = (await cl.get("/api/channels")).json()
        assert "secret-note" not in str(listing)


@pytest.mark.asyncio
async def test_notify_failure_does_not_break_create_or_accept(pg_orm, monkeypatch):
    import bot.main as bot_main

    async def boom(*_a, **_k):
        raise RuntimeError("telegram down")

    async with pg_orm.session() as db:
        ids = await _seed(db)
    app, cl, bot = await _client(pg_orm, monkeypatch)
    monkeypatch.setattr(bot_main, "notify_price_offer_received", boom)
    monkeypatch.setattr(bot_main, "notify_price_offer_accepted", boom)
    async with cl:
        r = await cl.post("/api/price-offers", json={"channel_id": ids.ch_id, "amount_usdt": 70},
                          headers=_tok(ids.buyer_id))
        assert r.status_code == 201
        acc = await cl.post(f"/api/price-offers/{r.json()['id']}/accept", headers=_tok(ids.seller_id))
        assert acc.status_code == 200 and acc.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_offer_events_and_funnel_counter_excludes_staff(pg_orm, monkeypatch):
    from app.models.user import User, UserRole
    from app.services import user_activity as ua
    from app.utils.security import create_access_token

    async with pg_orm.session() as db:
        ids = await _seed(db)
        admin = User(first_name="Adm", telegram_id=51999, role=UserRole.admin)
        db.add(admin)
        await db.commit()
        admin_id = admin.id

    app, cl, bot = await _client(pg_orm, monkeypatch)
    tok = lambda uid: {"Authorization": f"Bearer {create_access_token({'sub': str(uid)})}"}
    async with cl:
        assert (await cl.post("/api/track/event", json={"type": "offer_open"}, headers=tok(ids.buyer_id))).status_code == 400
        r1 = await cl.post("/api/track/event", json={"type": "offer_open", "channel_id": ids.ch_id}, headers=tok(ids.buyer_id))
        r2 = await cl.post("/api/track/event", json={"type": "offer_open", "channel_id": ids.ch_id}, headers=tok(ids.buyer_id))
        assert r1.status_code == 204 and r2.status_code == 204
        s1 = await cl.post("/api/track/event", json={"type": "offer_sent", "channel_id": ids.ch_id}, headers=tok(ids.buyer_id))
        s2 = await cl.post("/api/track/event", json={"type": "offer_sent", "channel_id": ids.ch_id}, headers=tok(ids.buyer_id))
        assert s1.status_code == 204 and s2.status_code == 204
        await cl.post("/api/track/event", json={"type": "offer_sent", "channel_id": ids.ch_id}, headers=tok(admin_id))

    async with pg_orm.session() as db:
        f = await ua.funnel(db, 7)
    assert f["offer_sent"] == 1  # unique non-staff
    assert f["offer_sent_total"] == 2  # two buyer events, staff dropped
    assert [s["step"] for s in f["steps"]] == ["visit", "channel_view", "buy_click", "deal_start", "payment"]


@pytest.mark.asyncio
async def test_deal_from_offer_rejected_when_accept_older_than_48h(pg_orm, monkeypatch):
    from app.models.deal import Deal
    from app.models.price_offer import PriceOffer
    from sqlalchemy import func, select

    async with pg_orm.session() as db:
        ids = await _seed(db)
    app, cl, bot = await _client(pg_orm, monkeypatch)
    async with cl:
        created = await cl.post(
            "/api/price-offers",
            json={"channel_id": ids.ch_id, "amount_usdt": 70},
            headers=_tok(ids.buyer_id),
        )
        assert created.status_code == 201, created.text
        offer_id = created.json()["id"]
        acc = await cl.post(f"/api/price-offers/{offer_id}/accept", headers=_tok(ids.seller_id))
        assert acc.status_code == 200
        assert acc.json()["accepted_at"] is not None
        async with pg_orm.session() as db:
            offer = await db.get(PriceOffer, offer_id)
            offer.accepted_at = utcnow_naive() - timedelta(hours=48, minutes=1)
            await db.commit()
        # buyer can see the offer, but can no longer confirm the deal
        got = (await cl.get(f"/api/price-offers/{offer_id}", headers=_tok(ids.buyer_id))).json()
        assert got["can_create_deal"] is False
        deal = await cl.post(
            "/api/deals",
            json={"channel_id": ids.ch_id, "offer_id": offer_id},
            headers=_tok(ids.buyer_id),
        )
        assert deal.status_code == 400
        assert "48 годин" in deal.json()["detail"]
        pub = (await cl.get(f"/api/channels/{ids.ch_id}")).json()
        assert pub["price"] == 100
    async with pg_orm.session() as db:
        n = (await db.execute(select(func.count()).select_from(Deal))).scalar()
        assert n == 0


@pytest.mark.asyncio
async def test_any_deal_closes_other_pending_and_accepted_offers(pg_orm, monkeypatch):
    """A deal at the listed price closes everyone else's pending/accepted offers on that lot."""
    from app.models.price_offer import PriceOffer, PriceOfferStatus
    from app.models.user import User
    from app.services.price_offers import CLOSE_REASON_LOT_IN_DEAL

    async with pg_orm.session() as db:
        ids = await _seed(db)
        extra = User(first_name="Buyer2", telegram_id=51004)
        db.add(extra)
        await db.commit()
        extra_id = extra.id

    app, cl, bot = await _client(pg_orm, monkeypatch)
    async with cl:
        pending = await cl.post(
            "/api/price-offers",
            json={"channel_id": ids.ch_id, "amount_usdt": 70, "comment": "pending-one"},
            headers=_tok(ids.buyer_id),
        )
        accepted = await cl.post(
            "/api/price-offers",
            json={"channel_id": ids.ch_id, "amount_usdt": 80},
            headers=_tok(extra_id),
        )
        assert pending.status_code == 201 and accepted.status_code == 201, (pending.text, accepted.text)
        pending_id, accepted_id = pending.json()["id"], accepted.json()["id"]
        acc = await cl.post(f"/api/price-offers/{accepted_id}/accept", headers=_tok(ids.seller_id))
        assert acc.status_code == 200

        # third party buys at the listed price
        deal = await cl.post("/api/deals", json={"channel_id": ids.ch_id}, headers=_tok(ids.other_id))
        assert deal.status_code == 201, deal.text
        assert deal.json()["amount_usdt"] == 100

        p = (await cl.get(f"/api/price-offers/{pending_id}", headers=_tok(ids.buyer_id))).json()
        a = (await cl.get(f"/api/price-offers/{accepted_id}", headers=_tok(extra_id))).json()
        assert p["status"] == "closed" and p["close_reason"] == CLOSE_REASON_LOT_IN_DEAL
        assert a["status"] == "closed" and a["close_reason"] == CLOSE_REASON_LOT_IN_DEAL
        assert a["deal_id"] is None and p["deal_id"] is None

        closed_texts = [text for _chat, text, _kw in bot.sent if "пропозиція закрита" in text.lower() or "пропозицію закрито" in text.lower()]
        # the required honest sentence must reach both displaced buyers
        assert len(closed_texts) == 2
        assert all("Лот уже в угоді з іншим покупцем, ваша пропозиція закрита" in text or
                   "уже в угоді з іншим покупцем, ваша пропозиція закрита" in text
                   for text in closed_texts)
        chats = {chat for chat, text, _ in bot.sent if "пропозиція закрита" in text.lower() or "пропозицію закрито" in text.lower()}
        assert chats == {51002, 51004}  # the two offer buyers, not the deal buyer / seller


@pytest.mark.asyncio
async def test_offer_deal_keeps_winner_and_closes_others(pg_orm, monkeypatch):
    from app.models.user import User
    from app.services.price_offers import CLOSE_REASON_LOT_IN_DEAL

    async with pg_orm.session() as db:
        ids = await _seed(db, price=200)
        extra = User(first_name="Buyer2", telegram_id=51005)
        db.add(extra)
        await db.commit()
        extra_id = extra.id

    app, cl, bot = await _client(pg_orm, monkeypatch)
    async with cl:
        other_offer = await cl.post(
            "/api/price-offers",
            json={"channel_id": ids.ch_id, "amount_usdt": 120},
            headers=_tok(extra_id),
        )
        winner = await cl.post(
            "/api/price-offers",
            json={"channel_id": ids.ch_id, "amount_usdt": 150},
            headers=_tok(ids.buyer_id),
        )
        assert other_offer.status_code == 201 and winner.status_code == 201
        other_id, winner_id = other_offer.json()["id"], winner.json()["id"]
        assert (await cl.post(f"/api/price-offers/{winner_id}/accept", headers=_tok(ids.seller_id))).status_code == 200
        deal = await cl.post(
            "/api/deals",
            json={"channel_id": ids.ch_id, "offer_id": winner_id},
            headers=_tok(ids.buyer_id),
        )
        assert deal.status_code == 201, deal.text
        assert deal.json()["amount_usdt"] == 150
        win = (await cl.get(f"/api/price-offers/{winner_id}", headers=_tok(ids.buyer_id))).json()
        lost = (await cl.get(f"/api/price-offers/{other_id}", headers=_tok(extra_id))).json()
        assert win["status"] == "accepted" and win["deal_id"] == deal.json()["id"]
        assert lost["status"] == "closed" and lost["close_reason"] == CLOSE_REASON_LOT_IN_DEAL
        pub = (await cl.get(f"/api/channels/{ids.ch_id}")).json()
        assert pub["price"] == 200


@pytest.mark.asyncio
async def test_close_notify_failure_does_not_block_deal(pg_orm, monkeypatch):
    import bot.main as bot_main
    from app.models.user import User

    async def boom(*_a, **_k):
        raise RuntimeError("telegram down")

    async with pg_orm.session() as db:
        ids = await _seed(db)
        extra = User(first_name="Buyer2", telegram_id=51006)
        db.add(extra)
        await db.commit()
        extra_id = extra.id
    app, cl, bot = await _client(pg_orm, monkeypatch)
    monkeypatch.setattr(bot_main, "notify_price_offer_closed", boom)
    async with cl:
        r = await cl.post(
            "/api/price-offers",
            json={"channel_id": ids.ch_id, "amount_usdt": 70},
            headers=_tok(extra_id),
        )
        assert r.status_code == 201
        deal = await cl.post("/api/deals", json={"channel_id": ids.ch_id}, headers=_tok(ids.buyer_id))
        assert deal.status_code == 201, deal.text
        lost = (await cl.get(f"/api/price-offers/{r.json()['id']}", headers=_tok(extra_id))).json()
        assert lost["status"] == "closed"
