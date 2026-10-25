"""GET /api/me/counts (cabinet tab counters) + GET /api/admin/counts (sidebar badges)."""
from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient


async def _client(pg_orm, monkeypatch, *routers):
    from fastapi import FastAPI
    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", pg_orm.session)
    app = FastAPI()
    for name in routers:
        app.include_router(importlib.import_module(name).router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _tok(uid):
    from app.utils.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': str(uid)})}"}


async def _seed(pg_orm):
    from app.models.auction import Auction
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus, Favorite
    from app.models.deal import Deal, DealStatus
    from app.models.saved_search import SavedSearch
    from app.models.user import User
    from app.utils.timeutil import utcnow_naive

    now = utcnow_naive()
    async with pg_orm.session() as db:
        me = User(first_name="Me", telegram_id=9001)
        other = User(first_name="Other", telegram_id=9002)
        empty = User(first_name="Empty", telegram_id=9003)
        mod = User(first_name="Mod", telegram_id=9004, role="moderator")
        db.add_all([me, other, empty, mod])
        await db.commit()

        def ch(owner, name, st):
            return Channel(seller_id=owner.id, telegram_link=f"https://t.me/{name}", channel_name=name,
                           category="Крипта", price=100, subscribers_count=1000, status=st)
        mine = [ch(me, "m1", ChannelStatus.approved), ch(me, "m2", ChannelStatus.pending),
                ch(me, "m3", ChannelStatus.rejected)]
        theirs = [ch(other, "o1", ChannelStatus.approved), ch(other, "o2", ChannelStatus.pending),
                  ch(other, "o3", ChannelStatus.approved), ch(other, "o4", ChannelStatus.pending)]
        db.add_all(mine + theirs)
        await db.commit()

        b_me = ChannelBundle(seller_id=me.id, name="B1", price=500, status=BundleStatus.pending)
        b_other = ChannelBundle(seller_id=other.id, name="B2", price=500, status=BundleStatus.approved)
        db.add_all([b_me, b_other])
        await db.commit()
        # o4 is a bundle member → excluded from admin pending channels
        db.add(BundleChannel(bundle_id=b_other.id, channel_id=theirs[3].id))

        db.add_all([
            Auction(channel_id=mine[0].id, seller_id=me.id, start_price=10, current_price=10,
                    status="active", starts_at=now, ends_at=now + timedelta(days=1)),
            Auction(channel_id=theirs[0].id, seller_id=other.id, start_price=10, current_price=10,
                    status="active", starts_at=now, ends_at=now + timedelta(days=1)),
        ])

        def deal(buyer, seller, st, chan):
            return Deal(channel_id=chan.id, buyer_id=buyer.id, seller_id=seller.id, status=st,
                        escrow_wallet_address="T" + "x" * 33, escrow_private_key_encrypted="enc", amount_usdt=100)
        db.add_all([deal(me, other, DealStatus.completed, theirs[0]),     # me buyer
                    deal(other, me, DealStatus.disputed, mine[0]),        # me seller
                    deal(other, empty, DealStatus.cancelled, theirs[0])])  # not mine

        db.add_all([Favorite(user_id=me.id, channel_id=theirs[0].id),
                    Favorite(user_id=me.id, channel_id=theirs[2].id),
                    Favorite(user_id=me.id, channel_id=theirs[1].id),     # pending → not shown/counted
                    Favorite(user_id=other.id, channel_id=mine[0].id)])
        db.add_all([SavedSearch(user_id=me.id, name="s1", filters={}),
                    SavedSearch(user_id=other.id, name="s2", filters={})])
        await db.commit()
        return dict(me=me.id, other=other.id, empty=empty.id, mod=mod.id)


@pytest.mark.asyncio
async def test_me_counts_requires_auth(pg_orm, monkeypatch):
    async with await _client(pg_orm, monkeypatch, "app.routers.me") as cl:
        assert (await cl.get("/api/me/counts")).status_code in (401, 403)
        assert (await cl.get("/api/me/counts", headers={"Authorization": "Bearer junk"})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_counts_scoped_to_current_user(pg_orm, monkeypatch):
    ids = await _seed(pg_orm)
    async with await _client(pg_orm, monkeypatch, "app.routers.me") as cl:
        r = await cl.get("/api/me/counts", headers=_tok(ids["me"]))
        assert r.status_code == 200
        assert r.json() == {"listings": 3, "bundles": 1, "auctions": 1, "deals": 2,
                            "favorites": 2, "saved_searches": 1}
        r = await cl.get("/api/me/counts", headers=_tok(ids["other"]))
        assert r.json() == {"listings": 4, "bundles": 1, "auctions": 1, "deals": 3,
                            "favorites": 1, "saved_searches": 1}
        r = await cl.get("/api/me/counts", headers=_tok(ids["empty"]))
        assert r.json() == {"listings": 0, "bundles": 0, "auctions": 0, "deals": 1,
                            "favorites": 0, "saved_searches": 0}


@pytest.mark.asyncio
async def test_me_counts_matches_favorites_and_saved_lists(pg_orm, monkeypatch):
    ids = await _seed(pg_orm)
    async with await _client(pg_orm, monkeypatch, "app.routers.me", "app.routers.favorites",
                             "app.routers.saved_searches") as cl:
        h = _tok(ids["me"])
        c = (await cl.get("/api/me/counts", headers=h)).json()
        assert c["favorites"] == len((await cl.get("/api/favorites", headers=h)).json())
        assert c["saved_searches"] == len((await cl.get("/api/saved-searches", headers=h)).json()["items"])
        # counter follows actions
        assert (await cl.post("/api/saved-searches", json={"filters": {}}, headers=h)).status_code == 201
        assert (await cl.get("/api/me/counts", headers=h)).json()["saved_searches"] == c["saved_searches"] + 1


@pytest.mark.asyncio
async def test_admin_counts(pg_orm, monkeypatch):
    ids = await _seed(pg_orm)
    async with await _client(pg_orm, monkeypatch, "app.routers.admin") as cl:
        assert (await cl.get("/api/admin/counts")).status_code in (401, 403)
        assert (await cl.get("/api/admin/counts", headers=_tok(ids["me"]))).status_code == 403
        r = await cl.get("/api/admin/counts", headers=_tok(ids["mod"]))
        assert r.status_code == 200
        # pending channels: m2, o2 (o4 is a bundle member); pending bundles: B1; disputes: 1
        assert r.json() == {"pending_channels": 2, "pending_bundles": 1, "pending": 3, "disputes": 1}
