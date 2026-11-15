"""PR2: admin «Видалені» filter, auction restore, lot/auction history."""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select


@pytest_asyncio.fixture
async def env(pg_orm):
    from app.models.user import User, UserRole

    admin_r = importlib.import_module("app.routers.admin")

    async with pg_orm.session() as db:
        admin = User(first_name="Admin", telegram_id=92001, role=UserRole.admin, username="adm")
        mod = User(first_name="Mod", telegram_id=92002, role=UserRole.moderator, username="mod")
        seller = User(first_name="Seller", telegram_id=92003)
        buyer = User(first_name="Buyer", telegram_id=92004)
        db.add_all([admin, mod, seller, buyer])
        await db.commit()
    ids = SimpleNamespace(admin=admin.id, mod=mod.id, seller=seller.id, buyer=buyer.id)

    async def channel(**kw):
        from app.models.channel import Channel, ChannelStatus

        async with pg_orm.session() as db:
            c = Channel(
                seller_id=ids.seller,
                telegram_link=kw.pop("telegram_link", "https://t.me/pr2lot"),
                channel_name=kw.pop("channel_name", "PR2Lot"),
                category="news",
                price=kw.pop("price", 10.0),
                status=kw.pop("status", ChannelStatus.approved),
                **kw,
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

    async def call(fn, *a, as_mod=False, **kw):
        from app.models.user import User
        uid = ids.mod if as_mod else ids.admin
        async with pg_orm.session() as db:
            return await fn(*a, admin=await db.get(User, uid), db=db, **kw)

    return SimpleNamespace(
        orm=pg_orm, admin=admin_r, ids=ids, channel=channel,
        get_ch=get_ch, get_auc=get_auc, call=call,
    )


async def _audit(env, action, target_id=None):
    from app.models.user import AdminAuditLog
    async with env.orm.session() as db:
        q = select(AdminAuditLog).where(AdminAuditLog.action == action)
        if target_id is not None:
            q = q.where(AdminAuditLog.target_id == target_id)
        return (await db.execute(q.order_by(AdminAuditLog.id))).scalars().all()


async def _make_auction(env, cid, *, status="active", hours=2, bid_count=0, starts_offset_hours=0):
    from app.models.auction import Auction
    from app.utils.timeutil import utcnow_naive

    async with env.orm.session() as db:
        now = utcnow_naive()
        a = Auction(
            channel_id=cid, seller_id=env.ids.seller, start_price=5, current_price=5,
            status=status, starts_at=now + timedelta(hours=starts_offset_hours),
            ends_at=now + timedelta(hours=hours), bid_count=bid_count,
        )
        db.add(a)
        await db.commit()
        return a.id


@pytest.mark.asyncio
async def test_channel_list_removed_includes_who_when_why(env):
    cid = await env.channel()
    await env.call(env.admin.admin_delete_channel, cid)
    items = await env.call(env.admin.list_all_channels, status="removed")
    match = [c for c in items if c.id == cid]
    assert len(match) == 1
    row = match[0]
    assert row.status == "removed"
    assert row.removed_at is not None
    assert row.removed_by_id == env.ids.admin
    assert row.removed_by == "adm"
    assert "адміністратором" in (row.removed_reason or "").lower()
    payload = row.model_dump()
    assert payload["removed_by"] == "adm"
    live = await env.call(env.admin.list_all_channels, status="approved")
    assert all(c.id != cid for c in live)


@pytest.mark.asyncio
async def test_channel_history_visible_to_moderator_and_scoped(env):
    from app.models.user import User, UserRole
    from app.utils import security

    cid = await env.channel()
    other = await env.channel(telegram_link="https://t.me/pr2other")
    await env.call(env.admin.admin_delete_channel, cid)
    await env.call(env.admin.admin_delete_channel, other)

    data = await env.call(env.admin.channel_history, cid, as_mod=True)
    assert data["total"] >= 1
    assert all(item["target_type"] == "channel" and item["target_id"] == cid for item in data["items"])
    assert any(item["action"] == "channel.delete" for item in data["items"])
    assert all(item["target_id"] != other for item in data["items"])

    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.channel_history, 999999, as_mod=True)
    assert e.value.status_code == 404

    app = FastAPI()
    app.include_router(env.admin.router, prefix="/api")

    async def as_user():
        async with env.orm.session() as db:
            u = User(first_name="U", telegram_id=92999, role=UserRole.user)
            db.add(u)
            await db.commit()
            return await db.get(User, u.id)

    app.dependency_overrides[security.get_current_user] = as_user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get(f"/api/admin/channels/{cid}/history")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_auctions_hidden_unless_deleted_true(env):
    cid = await env.channel()
    aid = await _make_auction(env, cid)
    await env.call(env.admin.admin_delete_auction, aid)

    hidden = await env.call(env.admin.admin_list_auctions)
    assert all(i["id"] != aid for i in hidden["items"])

    shown = await env.call(env.admin.admin_list_auctions, deleted=True)
    match = [i for i in shown["items"] if i["id"] == aid]
    assert len(match) == 1
    row = match[0]
    assert row["deleted_at"] is not None
    assert row["deleted_by_id"] == env.ids.admin
    assert row["deleted_by"] == "adm"


@pytest.mark.asyncio
async def test_restore_auction_returns_prev_status_and_audits(env):
    cid = await env.channel()
    aid = await _make_auction(env, cid, status="active", hours=3)
    await env.call(env.admin.admin_delete_auction, aid)
    assert (await env.get_auc(aid)).deleted_at is not None

    r = await env.call(env.admin.admin_restore_auction, aid)
    assert r["ok"] is True and r["status"] == "active" and r["prev_status"] == "active"
    a = await env.get_auc(aid)
    assert a.deleted_at is None and a.status == "active"
    rows = await _audit(env, "auction.restore", aid)
    assert len(rows) == 1 and rows[0].details["restored_status"] == "active"

    # idempotent
    r2 = await env.call(env.admin.admin_restore_auction, aid)
    assert r2["status"] == "active"
    assert len(await _audit(env, "auction.restore", aid)) == 1

    listed = await env.call(env.admin.admin_list_auctions)
    assert any(i["id"] == aid and i["deleted_at"] is None for i in listed["items"])


@pytest.mark.asyncio
async def test_restore_expired_auction_becomes_ended(env):
    cid = await env.channel()
    aid = await _make_auction(env, cid, status="active", hours=-1)
    await env.call(env.admin.admin_delete_auction, aid)
    r = await env.call(env.admin.admin_restore_auction, aid)
    assert r["status"] == "ended"
    assert (await env.get_auc(aid)).status == "ended"
    assert (await env.get_auc(aid)).deleted_at is None


@pytest.mark.asyncio
async def test_restore_auction_refused_if_lot_still_removed(env):
    cid = await env.channel()
    aid = await _make_auction(env, cid)
    await env.call(env.admin.admin_delete_channel, cid)
    a = await env.get_auc(aid)
    assert a.deleted_at is not None
    # cascade writes auction.delete so restore knows prev_status was live
    assert await _audit(env, "auction.delete", aid)
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.admin_restore_auction, aid)
    assert e.value.status_code == 409
    assert "відновіть лот" in e.value.detail.lower()
    assert (await env.get_auc(aid)).deleted_at is not None

    await env.call(env.admin.republish_channel, cid)
    r = await env.call(env.admin.admin_restore_auction, aid)
    assert r["status"] in ("active", "ended")
    assert (await env.get_auc(aid)).deleted_at is None


@pytest.mark.asyncio
async def test_restore_auction_conflict_when_another_is_live(env):
    cid = await env.channel()
    aid = await _make_auction(env, cid, status="active", hours=3)
    await env.call(env.admin.admin_delete_auction, aid)
    other = await _make_auction(env, cid, status="active", hours=4)
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.admin_restore_auction, aid)
    assert e.value.status_code == 409
    assert f"#{other}" in e.value.detail
    assert (await env.get_auc(aid)).deleted_at is not None


@pytest.mark.asyncio
async def test_auction_history_and_missing_404(env):
    cid = await env.channel()
    aid = await _make_auction(env, cid)
    await env.call(env.admin.admin_delete_auction, aid)
    data = await env.call(env.admin.auction_history, aid, as_mod=True)
    assert any(item["action"] == "auction.delete" for item in data["items"])
    assert all(item["target_type"] == "auction" and item["target_id"] == aid for item in data["items"])
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.auction_history, 999999)
    assert e.value.status_code == 404
