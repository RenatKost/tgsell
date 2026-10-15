"""Task 24: similar channels, saved searches, grouped bot notifications, events."""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


def test_rank_prefers_close_then_quality_and_skips_inflated():
    from app.services.similar import rank
    base = {"id": 1, "subscribers_count": 10000, "price_per_view": 0.1, "quality_score": 50, "price_verdict": "fair"}
    cands = [
        {"id": 2, "subscribers_count": 9000, "price_per_view": 0.11, "quality_score": 40, "price_verdict": "fair"},
        {"id": 3, "subscribers_count": 12000, "price_per_view": 0.09, "quality_score": 80, "price_verdict": "fair"},
        {"id": 4, "subscribers_count": 200000, "price_per_view": 0.1, "quality_score": 99, "price_verdict": "fair"},
        {"id": 5, "subscribers_count": 10000, "price_per_view": 0.1, "quality_score": 95, "price_verdict": "inflated"},
        {"id": 6, "subscribers_count": 11000, "price_per_view": None, "quality_score": None, "price_verdict": "unknown"},
        {"id": 1, "subscribers_count": 10000, "price_per_view": 0.1, "quality_score": 50, "price_verdict": "fair"},
    ]
    assert [c["id"] for c in rank(base, cands)] == [3, 2, 6, 4]
    assert len(rank(base, cands * 5, limit=6)) <= 6


def test_sanitize_filters_and_label():
    from app.services.saved_searches import filters_label, sanitize_filters
    f = sanitize_filters({"category": " Крипта ", "min_price": "100", "no_inflation": 1, "evil": "x",
                          "max_subscribers": "5000", "er_min": "bad", "search": ""})
    assert f == {"category": "Крипта", "min_price": 100.0, "no_inflation": True, "max_subscribers": 5000}
    assert "Крипта" in filters_label(f) and "без накрутки" in filters_label(f)
    assert sanitize_filters(None) == {} and filters_label({}) == "Усі фільтри"


async def _app(pg_orm, monkeypatch, *routers):
    from fastapi import FastAPI
    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", pg_orm.session)
    importlib.import_module("app.services.user_activity").limiter.reset()
    app = FastAPI()
    for name in routers:
        app.include_router(importlib.import_module(name).router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_similar_endpoint_filters_and_ranks(pg_orm, monkeypatch):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User
    from app.utils.timeutil import utcnow_naive

    now = utcnow_naive()
    async with pg_orm.session() as db:
        s = User(first_name="S", telegram_id=11)
        db.add(s)
        await db.commit()
        mk = lambda name, **kw: Channel(seller_id=s.id, telegram_link=f"https://t.me/{name}", channel_name=name,
                                        category=kw.pop("category", "Крипта"), price=kw.pop("price", 500),
                                        subscribers_count=kw.pop("subs", 10000), avg_views=kw.pop("views", 2000),
                                        last_post_date=now - timedelta(days=1),
                                        status=kw.pop("status", ChannelStatus.approved), **kw)
        base = mk("base", quality_score=50)
        good = mk("good", quality_score=90, subs=12000)
        ok = mk("ok", quality_score=30, subs=9000)
        far = mk("far", quality_score=99, subs=900000, views=200000, price=40000)
        inflated = mk("inflated", quality_score=95, views=10)  # views/subs < 2% -> inflated
        other_cat = mk("other", category="Новини/ЗМІ", quality_score=99)
        pending = mk("pending", status=ChannelStatus.pending, quality_score=99)
        removed = mk("removed", status=ChannelStatus.removed, quality_score=99)
        db.add_all([base, good, ok, far, inflated, other_cat, pending, removed])
        await db.commit()
        ids = {c.channel_name: c.id for c in [base, good, ok, far, inflated, other_cat, pending, removed]}

    async with await _app(pg_orm, monkeypatch, "app.routers.channels") as cl:
        r = await cl.get(f"/api/channels/{ids['base']}/similar")
        assert r.status_code == 200
        got = [i["id"] for i in r.json()["items"]]
        assert got == [ids["good"], ids["ok"], ids["far"]]
        assert all("seller_telegram" not in i and "telegram_link" not in i for i in r.json()["items"])
        assert (await cl.get("/api/channels/999999/similar")).status_code == 404


@pytest.mark.asyncio
async def test_saved_search_crud_limit_match_notify(pg_orm, monkeypatch):
    from sqlalchemy import select

    from app.config import settings
    from app.models.activity import UserEvent
    from app.models.channel import Channel, ChannelStatus
    from app.models.saved_search import SavedSearch, SavedSearchMatch
    from app.models.user import User
    ss = importlib.import_module("app.services.saved_searches")
    from app.utils.security import create_access_token
    from app.utils.timeutil import utcnow_naive

    now = utcnow_naive()
    async with pg_orm.session() as db:
        seller = User(first_name="S", telegram_id=101)
        started = User(first_name="B", telegram_id=102, tg_bot_started_at=now)
        silent = User(first_name="C", telegram_id=103)  # never pressed Start
        db.add_all([seller, started, silent])
        await db.commit()
        ids = dict(seller=seller.id, started=started.id, silent=silent.id)

    tok = lambda uid: {"Authorization": f"Bearer {create_access_token({'sub': str(uid)})}"}
    async with await _app(pg_orm, monkeypatch, "app.routers.saved_searches", "app.routers.user_activity") as cl:
        assert (await cl.get("/api/saved-searches")).status_code in (401, 403)
        f = {"category": "Крипта", "max_price": 1000, "no_inflation": True, "junk": 1}
        r = await cl.post("/api/saved-searches", json={"filters": f}, headers=tok(ids["started"]))
        assert r.status_code == 201 and r.json()["filters"] == {"category": "Крипта", "max_price": 1000.0,
                                                               "no_inflation": True}
        sid = r.json()["id"]
        assert "Крипта" in r.json()["name"]
        r = await cl.post("/api/saved-searches", json={"name": "Мій", "filters": {"category": "Крипта"}},
                          headers=tok(ids["silent"]))
        silent_sid = r.json()["id"]
        for i in range(9):
            assert (await cl.post("/api/saved-searches", json={"filters": {"min_price": i}},
                                  headers=tok(ids["started"]))).status_code == 201
        r = await cl.post("/api/saved-searches", json={"filters": {}}, headers=tok(ids["started"]))
        assert r.status_code == 400 and "10" in r.json()["detail"]
        lst = (await cl.get("/api/saved-searches", headers=tok(ids["started"]))).json()
        assert len(lst["items"]) == 10 and lst["max"] == 10
        # other user's search can't be deleted
        assert (await cl.delete(f"/api/saved-searches/{silent_sid}", headers=tok(ids["started"]))).status_code == 404
        extra = [i["id"] for i in lst["items"] if i["id"] != sid]
        for e in extra:
            assert (await cl.delete(f"/api/saved-searches/{e}", headers=tok(ids["started"]))).status_code == 200
        # click-through from the notification is a client event
        r = await cl.post("/api/track/event", json={"type": "saved_search_click", "anon": "a-1", "channel_id": 5},
                          headers=tok(ids["started"]))
        assert r.status_code == 204

    async with pg_orm.session() as db:
        evs = (await db.execute(select(UserEvent.event_type, UserEvent.user_id, UserEvent.object_id))).all()
        assert sum(1 for e in evs if e[0] == "saved_search_create") == 11
        assert ("saved_search_click", ids["started"], 5) in evs
        # approve flow: matching (clean, cheap, crypto) vs not matching
        mk = lambda name, **kw: Channel(seller_id=ids["seller"], telegram_link=f"https://t.me/{name}",
                                        channel_name=name, category="Крипта", subscribers_count=5000,
                                        status=ChannelStatus.approved, **kw)
        a = mk("A <b>", price=500, quality_health="clean")
        b = mk("B", price=700, quality_health="clean")
        expensive = mk("X", price=5000, quality_health="clean")
        dirty = mk("D", price=100, quality_health="suspicious")
        db.add_all([a, b, expensive, dirty])
        await db.commit()
        for c in (a, b, expensive, dirty):
            await ss.enqueue_matches_for_channel(db, c.id)
        await ss.enqueue_matches_for_channel(db, a.id)  # idempotent
        rows = (await db.execute(select(SavedSearchMatch.search_id, SavedSearchMatch.channel_id))).all()
        assert sorted(r[1] for r in rows if r[0] == sid) == sorted([a.id, b.id])
        assert sorted(r[1] for r in rows if r[0] == silent_sid) == sorted([a.id, b.id, expensive.id, dirty.id])
        ch = dict(a=a.id, b=b.id)

    sent = []

    class FakeBot:
        def __init__(self, token, **_kw):
            self.session = SimpleNamespace(close=AsyncMock())

        async def send_message(self, chat_id, text, **_kw):
            sent.append((chat_id, text))

    monkeypatch.setattr(importlib.import_module("aiogram"), "Bot", FakeBot)
    monkeypatch.setattr(settings, "bot_token_alerts", "test-token")
    monkeypatch.setattr(settings, "frontend_url", "https://tgsell.test/")

    await ss.flush_pending(now=now)
    assert len(sent) == 1 and sent[0][0] == 102  # grouped: one message for two listings
    text = sent[0][1]
    assert "Нові канали" in text and "A &lt;b&gt;" in text
    assert f"/channel/{ch['a']}?ref=saved_search&amp;sid={sid}" in text and f"/channel/{ch['b']}?" in text

    async with pg_orm.session() as db:
        s1, s2 = await db.get(SavedSearch, sid), await db.get(SavedSearch, silent_sid)
        assert s1.last_delivery_status == "sent" and s2.last_delivery_status == "not_started"
        undelivered = (await db.execute(select(SavedSearchMatch).where(SavedSearchMatch.search_id == silent_sid))).scalars().all()
        assert all(m.processed_at is not None and m.delivered is False for m in undelivered)
        # a new match within the hour waits; after an hour it goes out
        c = Channel(seller_id=ids["seller"], telegram_link="https://t.me/c", channel_name="C", category="Крипта",
                    subscribers_count=10, price=10, quality_health="clean", status=ChannelStatus.approved)
        db.add(c)
        await db.commit()
        await ss.enqueue_matches_for_channel(db, c.id)
    await ss.flush_pending(now=now + timedelta(minutes=30))
    assert len(sent) == 1
    await ss.flush_pending(now=now + timedelta(minutes=61))
    assert len(sent) == 2

    # send failure -> undelivered, no crash
    class BoomBot(FakeBot):
        async def send_message(self, chat_id, text, **_kw):
            raise RuntimeError("network down")

    monkeypatch.setattr(importlib.import_module("aiogram"), "Bot", BoomBot)
    async with pg_orm.session() as db:
        c = Channel(seller_id=ids["seller"], telegram_link="https://t.me/e", channel_name="E", category="Крипта",
                    subscribers_count=10, price=10, quality_health="clean", status=ChannelStatus.approved)
        db.add(c)
        await db.commit()
        await ss.enqueue_matches_for_channel(db, c.id)
    await ss.flush_pending(now=now + timedelta(minutes=130))
    async with pg_orm.session() as db:
        assert (await db.get(SavedSearch, sid)).last_delivery_status == "failed"
