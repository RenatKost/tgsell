"""Seller DELETE /api/channels/{id} soft-deletes (status=removed); relist redirect still works."""
from __future__ import annotations

import pytest


async def _client(orm, *, with_auth=True):
    import httpx
    from fastapi import FastAPI

    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    from app.routers import channels as ch_router
    from app.utils import security

    async with orm.session() as db:
        seller = User(first_name="Seller", telegram_id=880001, role=UserRole.user)
        other = User(first_name="Other", telegram_id=880002, role=UserRole.user)
        db.add_all([seller, other])
        await db.flush()
        ids = {"seller": seller.id, "other": other.id}
        db.add(Channel(
            id=201, seller_id=seller.id, telegram_link="https://t.me/SoftDel",
            channel_name="SoftDel", category="x", price=100, status=ChannelStatus.approved,
        ))
        await db.commit()

    state = {"user": seller if with_auth else None}

    async def _override_user():
        if state["user"] is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Not authenticated")
        return state["user"]

    app = FastAPI()
    app.include_router(ch_router.router, prefix="/api")
    app.dependency_overrides[security.get_current_user] = _override_user
    app.dependency_overrides[security.get_optional_user] = lambda: state["user"]
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    return client, state, ids, seller, other


@pytest.mark.asyncio
async def test_seller_delete_sets_removed_keeps_row(orm):
    from app.models.channel import Channel, ChannelStatus

    client, state, ids, seller, _other = await _client(orm)
    r = await client.delete("/api/channels/201")
    assert r.status_code == 204

    async with orm.session() as db:
        c = await db.get(Channel, 201)
        assert c is not None
        assert c.status == ChannelStatus.removed
        assert c.removed_by_id == seller.id
        assert c.removed_at is not None
        assert "продавцем" in (c.removed_reason or "").lower()

    # idempotent
    assert (await client.delete("/api/channels/201")).status_code == 204


@pytest.mark.asyncio
async def test_removed_not_in_public_catalog(orm):
    client, _state, _ids, _s, _o = await _client(orm)
    assert (await client.delete("/api/channels/201")).status_code == 204
    r = await client.get("/api/channels")
    assert r.status_code == 200
    assert all(item["id"] != 201 for item in r.json()["items"])


@pytest.mark.asyncio
async def test_seller_delete_then_relist_exposes_replaced_by(orm):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User

    client, state, ids, seller, _other = await _client(orm)
    assert (await client.delete("/api/channels/201")).status_code == 204

    async with orm.session() as db:
        db.add(Channel(
            id=202, seller_id=ids["seller"], telegram_link="@softdel",
            channel_name="SoftDel (new)", category="x", price=150, status=ChannelStatus.approved,
        ))
        await db.commit()

    # anonymous / public viewer
    state["user"] = None
    r = await client.get("/api/channels/201")
    assert r.status_code == 404
    assert r.json().get("replaced_by") == 202
    assert (await client.get("/api/channels/202")).status_code == 200


@pytest.mark.asyncio
async def test_cannot_delete_sold(orm):
    from app.models.channel import Channel, ChannelStatus

    client, state, ids, seller, _other = await _client(orm)
    async with orm.session() as db:
        c = await db.get(Channel, 201)
        c.status = ChannelStatus.sold
        await db.commit()
    r = await client.delete("/api/channels/201")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_seller_delete_blocked_by_active_deal(orm):
    from datetime import timedelta

    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus

    client, state, ids, seller, other = await _client(orm)
    async with orm.session() as db:
        db.add(Deal(
            channel_id=201, buyer_id=ids["other"], seller_id=ids["seller"],
            status=DealStatus.paid, escrow_wallet_address="TX1",
            escrow_private_key_encrypted="e", amount_usdt=10, service_fee=0.3,
        ))
        await db.commit()
    r = await client.delete("/api/channels/201")
    assert r.status_code == 409
    assert "Активна угода" in r.json()["detail"]
    async with orm.session() as db:
        assert (await db.get(Channel, 201)).status == ChannelStatus.approved


@pytest.mark.asyncio
async def test_seller_delete_blocked_by_auction_with_bids(orm):
    from datetime import timedelta

    from app.models.auction import Auction
    from app.models.channel import Channel, ChannelStatus
    from app.utils.timeutil import utcnow_naive

    client, state, ids, seller, other = await _client(orm)
    async with orm.session() as db:
        now = utcnow_naive()
        db.add(Auction(
            channel_id=201, seller_id=ids["seller"], start_price=5, current_price=7,
            status="active", starts_at=now, ends_at=now + timedelta(hours=1), bid_count=2,
        ))
        await db.commit()
    r = await client.delete("/api/channels/201")
    assert r.status_code == 409
    assert "ставок" in r.json()["detail"]
    async with orm.session() as db:
        assert (await db.get(Channel, 201)).status == ChannelStatus.approved


@pytest.mark.asyncio
async def test_seller_delete_ok_when_auction_has_no_bids(orm):
    from datetime import timedelta

    from app.models.auction import Auction
    from app.models.channel import Channel, ChannelStatus
    from app.utils.timeutil import utcnow_naive

    client, state, ids, seller, other = await _client(orm)
    async with orm.session() as db:
        now = utcnow_naive()
        db.add(Auction(
            channel_id=201, seller_id=ids["seller"], start_price=5, current_price=5,
            status="active", starts_at=now, ends_at=now + timedelta(hours=1), bid_count=0,
        ))
        await db.commit()
    r = await client.delete("/api/channels/201")
    assert r.status_code == 204
    async with orm.session() as db:
        assert (await db.get(Channel, 201)).status == ChannelStatus.removed
