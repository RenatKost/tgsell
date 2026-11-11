"""Admin DELETE /channels and /auctions is a soft-delete; public lists hide the rows."""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select


@pytest_asyncio.fixture
async def env(pg_orm):
    from app.models.user import User, UserRole

    admin_r = importlib.import_module("app.routers.admin")

    async with pg_orm.session() as db:
        admin = User(first_name="A", telegram_id=91001, role=UserRole.admin)
        seller = User(first_name="S", telegram_id=91002)
        buyer = User(first_name="B", telegram_id=91003)
        db.add_all([admin, seller, buyer])
        await db.commit()
    ids = SimpleNamespace(admin=admin.id, seller=seller.id, buyer=buyer.id)

    async def channel(**kw):
        from app.models.channel import Channel, ChannelStatus

        async with pg_orm.session() as db:
            c = Channel(
                seller_id=ids.seller, telegram_link=kw.pop("telegram_link", "https://t.me/softdel"),
                channel_name=kw.pop("channel_name", "SoftDel"), category="news",
                price=kw.pop("price", 10.0), status=kw.pop("status", ChannelStatus.approved), **kw,
            )
            db.add(c)
            await db.commit()
            return c.id

    async def get_ch(cid):
        from app.models.channel import Channel
        async with pg_orm.session() as db:
            return await db.get(Channel, cid)

    async def get_auc(aid):
        from app.models.auction import Auction
        async with pg_orm.session() as db:
            return await db.get(Auction, aid)

    async def call(fn, *a, **kw):
        from app.models.user import User
        async with pg_orm.session() as db:
            return await fn(*a, admin=await db.get(User, ids.admin), db=db, **kw)

    return SimpleNamespace(
        orm=pg_orm, admin=admin_r, ids=ids, channel=channel,
        get_ch=get_ch, get_auc=get_auc, call=call,
    )


async def _audit(env, action):
    from app.models.user import AdminAuditLog
    async with env.orm.session() as db:
        return (await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action))).scalars().all()


@pytest.mark.asyncio
async def test_admin_delete_channel_soft_removes_and_audits(env):
    from app.models.channel import Channel, ChannelStatus

    cid = await env.channel()
    r = await env.call(env.admin.admin_delete_channel, cid)
    assert r is None
    c = await env.get_ch(cid)
    assert c is not None
    assert c.status == ChannelStatus.removed
    assert c.removed_by_id == env.ids.admin
    assert c.removed_at is not None
    assert "адміністратором" in (c.removed_reason or "").lower()
    rows = await _audit(env, "channel.delete")
    assert len(rows) == 1 and rows[0].target_id == cid and rows[0].details["prev_status"] == "approved"

    # idempotent: still 204, no second audit
    await env.call(env.admin.admin_delete_channel, cid)
    assert len(await _audit(env, "channel.delete")) == 1


@pytest.mark.asyncio
async def test_admin_deleted_channel_hidden_from_public_catalog(env):
    import httpx
    from fastapi import FastAPI

    from app.routers import channels as ch_router
    from app.utils import security

    cid = await env.channel()
    await env.call(env.admin.admin_delete_channel, cid)

    app = FastAPI()
    app.include_router(ch_router.router, prefix="/api")
    app.dependency_overrides[security.get_optional_user] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get("/api/channels")
        assert r.status_code == 200
        assert all(item["id"] != cid for item in r.json()["items"])
        assert (await client.get(f"/api/channels/{cid}")).status_code == 404


@pytest.mark.asyncio
async def test_admin_delete_channel_blocked_by_active_escrow(env):
    from app.models.channel import ChannelStatus
    from app.models.deal import Deal, DealStatus

    cid = await env.channel()
    async with env.orm.session() as db:
        db.add(Deal(
            channel_id=cid, buyer_id=env.ids.buyer, seller_id=env.ids.seller,
            status=DealStatus.paid, escrow_wallet_address="TX1",
            escrow_private_key_encrypted="e", amount_usdt=10, service_fee=0.3,
        ))
        await db.commit()
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.admin_delete_channel, cid)
    assert e.value.status_code == 409
    assert "активне ескроу" in e.value.detail
    assert (await env.get_ch(cid)).status == ChannelStatus.approved


@pytest.mark.asyncio
async def test_admin_delete_channel_blocked_by_open_deal_without_escrow(env):
    from app.models.channel import ChannelStatus
    from app.models.deal import Deal, DealStatus

    cid = await env.channel()
    async with env.orm.session() as db:
        db.add(Deal(
            channel_id=cid, buyer_id=env.ids.buyer, seller_id=env.ids.seller,
            status=DealStatus.created, escrow_wallet_address="TX2",
            escrow_private_key_encrypted="e", amount_usdt=10, service_fee=0.3,
        ))
        await db.commit()
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.admin_delete_channel, cid)
    assert e.value.status_code == 409
    assert "Активна угода" in e.value.detail
    assert (await env.get_ch(cid)).status == ChannelStatus.approved


@pytest.mark.asyncio
async def test_admin_delete_sold_channel_refused(env):
    from app.models.channel import ChannelStatus

    cid = await env.channel(status=ChannelStatus.sold)
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.admin_delete_channel, cid)
    assert e.value.status_code == 400
    assert "Проданий" in e.value.detail
    assert (await env.get_ch(cid)).status == ChannelStatus.sold


@pytest.mark.asyncio
async def test_admin_delete_channel_cancels_zero_bid_auction(env):
    from app.models.auction import Auction
    from app.models.channel import ChannelStatus
    from app.utils.timeutil import utcnow_naive

    cid = await env.channel()
    async with env.orm.session() as db:
        now = utcnow_naive()
        a = Auction(
            channel_id=cid, seller_id=env.ids.seller, start_price=5, current_price=5,
            status="active", starts_at=now, ends_at=now + timedelta(hours=1), bid_count=0,
        )
        db.add(a)
        await db.commit()
        aid = a.id
    await env.call(env.admin.admin_delete_channel, cid)
    assert (await env.get_ch(cid)).status == ChannelStatus.removed
    a = await env.get_auc(aid)
    assert a is not None and a.deleted_at is not None and a.status == "cancelled"


@pytest.mark.asyncio
async def test_admin_delete_auction_soft_hides_from_public_keeps_bids(env):
    import httpx
    from fastapi import FastAPI

    from app.models.auction import Auction, AuctionBid
    from app.models.channel import ChannelStatus
    from app.routers import auctions as auc_router
    from app.utils.timeutil import utcnow_naive
    from app.utils import security

    cid = await env.channel()
    async with env.orm.session() as db:
        now = utcnow_naive()
        a = Auction(
            channel_id=cid, seller_id=env.ids.seller, start_price=5, current_price=7,
            status="active", starts_at=now, ends_at=now + timedelta(hours=2), bid_count=1,
        )
        db.add(a)
        await db.flush()
        db.add(AuctionBid(auction_id=a.id, bidder_id=env.ids.buyer, amount=7))
        await db.commit()
        aid = a.id

    await env.call(env.admin.admin_delete_auction, aid)
    a = await env.get_auc(aid)
    assert a is not None and a.deleted_at is not None
    assert a.status == "cancelled"
    async with env.orm.session() as db:
        bids = list((await db.execute(select(AuctionBid).where(AuctionBid.auction_id == aid))).scalars())
    assert len(bids) == 1
    rows = await _audit(env, "auction.delete")
    assert len(rows) == 1 and rows[0].target_id == aid

    # idempotent
    await env.call(env.admin.admin_delete_auction, aid)
    assert len(await _audit(env, "auction.delete")) == 1

    app = FastAPI()
    app.include_router(auc_router.router, prefix="/api")
    app.dependency_overrides[security.get_optional_user] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        listed = await client.get("/api/auctions", params={"status": "active"})
        assert listed.status_code == 200
        assert all(item["id"] != aid for item in listed.json()["items"])
        assert (await client.get(f"/api/auctions/{aid}")).status_code == 404


@pytest.mark.asyncio
async def test_admin_delete_auction_blocked_by_active_escrow(env):
    from app.models.auction import Auction
    from app.models.deal import Deal, DealStatus
    from app.utils.timeutil import utcnow_naive

    cid = await env.channel()
    async with env.orm.session() as db:
        now = utcnow_naive()
        a = Auction(
            channel_id=cid, seller_id=env.ids.seller, start_price=5, current_price=5,
            status="ended", starts_at=now, ends_at=now, bid_count=1,
        )
        db.add(a)
        db.add(Deal(
            channel_id=cid, buyer_id=env.ids.buyer, seller_id=env.ids.seller,
            status=DealStatus.awaiting_payout, escrow_wallet_address="TX3",
            escrow_private_key_encrypted="e", amount_usdt=20, service_fee=0.6,
        ))
        await db.commit()
        aid = a.id
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.admin_delete_auction, aid)
    assert e.value.status_code == 409
    assert "активне ескроу" in e.value.detail
    assert (await env.get_auc(aid)).deleted_at is None


@pytest.mark.asyncio
async def test_admin_delete_missing_is_404(env):
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.admin_delete_channel, 999999)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.admin_delete_auction, 999999)
    assert e.value.status_code == 404
