"""Task 23: activity events, heartbeat sessions, admin users list + funnel."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient


def test_hash_id_is_stable_and_not_raw():
    from app.utils.activity_ids import hash_id
    assert hash_id("abc-123") == hash_id("abc-123") and "abc" not in hash_id("abc-123")
    assert len(hash_id("abc-123")) == 32 and hash_id("") is None and hash_id("x" * 200) is None


def test_rate_limiter():
    from app.utils.activity_ids import _RateLimiter
    rl = _RateLimiter()
    assert rl.min_interval("k", 25, now=100) and not rl.min_interval("k", 25, now=110)
    assert rl.min_interval("k", 25, now=126)
    assert all(rl.per_minute("e", 3, now=t) for t in (0, 1, 2)) and not rl.per_minute("e", 3, now=3)
    assert rl.per_minute("e", 3, now=61)


async def _client(pg_orm, monkeypatch):
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
async def test_tracking_dedupe_heartbeat_users_and_funnel(pg_orm, monkeypatch):
    from sqlalchemy import func, select

    from app.models.activity import UserEvent, UserSession
    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus
    from app.models.user import User, UserRole
    from app.services import user_activity as ua
    from app.utils.security import create_access_token

    async with pg_orm.session() as db:
        seller = User(first_name="S", telegram_id=1)
        buyer = User(first_name="B", telegram_id=2, username="buyer_x")
        lurker = User(first_name="L", telegram_id=3)
        admin = User(first_name="A", telegram_id=4, role=UserRole.admin)
        mod = User(first_name="M", telegram_id=5, role=UserRole.moderator)
        db.add_all([seller, buyer, lurker, admin, mod])
        await db.commit()
        ch = Channel(seller_id=seller.id, telegram_link="https://t.me/c1", channel_name="Канал 1",
                     category="Новини/ЗМІ", price=100, subscribers_count=1000, status=ChannelStatus.approved)
        db.add(ch)
        await db.commit()
        ids = dict(buyer=buyer.id, lurker=lurker.id, admin=admin.id, mod=mod.id, ch=ch.id, seller=seller.id)

    app, cl = await _client(pg_orm, monkeypatch)
    tok = lambda uid: {"Authorization": f"Bearer {create_access_token({'sub': str(uid)})}"}
    async with cl:
        # anonymous visit + view; then same browser logs in (anon linked via heartbeat)
        assert (await cl.post("/api/track/event", json={"type": "visit", "anon": "anon-1", "page": "home"})).status_code == 204
        await cl.post("/api/track/event", json={"type": "channel_view", "anon": "anon-1", "channel_id": ids["ch"]})
        await cl.post("/api/track/event", json={"type": "channel_view", "anon": "anon-1", "channel_id": ids["ch"]})  # dup
        await cl.post("/api/track/event", json={"type": "search", "anon": "anon-1"})
        assert (await cl.post("/api/track/event", json={"type": "payment", "anon": "anon-1"})).status_code == 400
        r = await cl.post("/api/track/heartbeat", json={"sid": "session-aaa", "anon": "anon-1"}, headers=tok(ids["buyer"]))
        assert r.status_code == 200 and r.json()["credited"] == 0
        assert (await cl.post("/api/track/heartbeat", json={"sid": "session-aaa"})).status_code == 429
        # other anonymous visitor (visit only)
        await cl.post("/api/track/event", json={"type": "visit", "anon": "anon-2"})
        await cl.post("/api/track/event", json={"type": "visit", "anon": "anon-3", "page": "catalog"})
        await cl.post("/api/track/event", json={"type": "channel_view", "anon": "anon-3", "channel_id": ids["ch"]})
        # logged-in lurker views
        await cl.post("/api/track/event", json={"type": "channel_view", "channel_id": ids["ch"]}, headers=tok(ids["lurker"]))

        # per-minute limit
        ua.limiter.reset()
        codes = [(await cl.post("/api/track/event", json={"type": "search", "anon": "spam"})).status_code for _ in range(32)]
        assert codes.count(429) == 2

        # admin-only endpoints
        assert (await cl.get("/api/admin/activity/users")).status_code in (401, 403)
        assert (await cl.get("/api/admin/activity/users", headers=tok(ids["mod"]))).status_code == 403

    async with pg_orm.session() as db:
        n_views = (await db.execute(select(func.count()).select_from(UserEvent).where(
            UserEvent.event_type == "channel_view"))).scalar()
        assert n_views == 3  # duplicate dropped
        # no raw ids stored
        assert not (await db.execute(select(UserEvent).where(UserEvent.anon_id == "anon-1"))).first()
        s = (await db.execute(select(UserSession))).scalar_one()
        assert s.user_id == ids["buyer"]
        # heartbeat crediting: 45s -> 45, then gap 10 min -> 0 (hidden tab), cap 60
        t0 = s.last_seen_at
        assert await ua.heartbeat(db, s.session_key, user_id=None, anon_id=None, now=t0 + timedelta(seconds=45)) == 45
        assert await ua.heartbeat(db, s.session_key, user_id=None, anon_id=None, now=t0 + timedelta(seconds=145)) == 60
        assert await ua.heartbeat(db, s.session_key, user_id=None, anon_id=None, now=t0 + timedelta(minutes=15)) == 0
        now = datetime.utcnow()
        db.add(Deal(channel_id=ids["ch"], buyer_id=ids["buyer"], seller_id=ids["seller"], status=DealStatus.paid,
                    escrow_wallet_address="T" * 34, escrow_private_key_encrypted="x", amount_usdt=100, service_fee=3, paid_at=now))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
        r = await cl.get("/api/admin/activity/users", headers=tok(ids["admin"]))
        assert r.status_code == 200
        items = r.json()["items"]
        assert items[0]["user_id"] == ids["buyer"]
        b = items[0]
        assert b["sessions_7d"] == 1 and b["seconds_30d"] == 105 and b["views_30d"] == 1
        assert b["searches_30d"] == 1 and b["deals_30d"] == 1 and b["paid_30d"] == 1
        assert b["viewed"] == [{"channel_id": ids["ch"], "name": "Канал 1"}]
        assert {i["user_id"] for i in items} == {ids["buyer"], ids["lurker"]}

        f = (await cl.get("/api/admin/activity/funnel", headers=tok(ids["admin"]))).json()["funnels"]
        assert [x["days"] for x in f] == [7, 30]
        users = {s["step"]: s["users"] for s in f[0]["steps"]}
        # visitors: buyer (anon-1 linked), anon-2, anon-3, lurker, spam
        assert users == {"visit": 5, "channel_view": 3, "deal_start": 1, "payment": 1}
        assert f[0]["steps"][3]["from_prev_pct"] == 100.0
