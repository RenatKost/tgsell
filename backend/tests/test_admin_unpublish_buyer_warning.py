"""Admin «Зняти з публікації / відхилити з причиною», republish, buyer_warning."""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select


@pytest_asyncio.fixture
async def env(pg_orm, monkeypatch):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole

    admin_r = importlib.import_module("app.routers.admin")
    notify = AsyncMock()
    monkeypatch.setattr(admin_r, "_notify_seller_channel", notify)

    async with pg_orm.session() as db:
        admin = User(first_name="A", telegram_id=11, role=UserRole.admin)
        seller = User(first_name="S", telegram_id=12)
        db.add_all([admin, seller])
        await db.commit()
    ids = SimpleNamespace(admin=admin.id, seller=seller.id)

    async def channel(**kw):
        async with pg_orm.session() as db:
            c = Channel(seller_id=ids.seller, telegram_link="https://t.me/x", channel_name="X", category="news",
                        price=10.0, status=kw.pop("status", ChannelStatus.approved), **kw)
            db.add(c)
            await db.commit()
            return c.id

    async def get(cid):
        async with pg_orm.session() as db:
            return await db.get(Channel, cid)

    async def call(fn, *a, **kw):
        async with pg_orm.session() as db:
            return await fn(*a, admin=await db.get(User, ids.admin), db=db, **kw)

    return SimpleNamespace(orm=pg_orm, admin=admin_r, notify=notify, channel=channel, get=get, call=call, CS=ChannelStatus)


async def _audit(env, action):
    from app.models.user import AdminAuditLog
    async with env.orm.session() as db:
        return (await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action))).scalars().all()


@pytest.mark.asyncio
async def test_unpublish_with_reason_then_republish(env):
    cid = await env.channel()
    R = env.admin.ChannelUnpublishRequest
    r = await env.call(env.admin.unpublish_channel, cid, R(reason="  Менше 100 підписників  "))
    assert r["status"] == "rejected" and r["prev_status"] == "approved"
    c = await env.get(cid)
    assert c.status == env.CS.rejected and c.rejection_reason == "Менше 100 підписників"
    rows = await _audit(env, "channel.unpublish")
    assert len(rows) == 1 and rows[0].details["reason"] == "Менше 100 підписників"
    env.notify.assert_awaited()
    assert env.notify.await_args.args[2] == "unpublish"
    assert env.notify.await_args.args[3] == "Менше 100 підписників"

    # second unpublish refused (not published anymore)
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.unpublish_channel, cid, R(reason="ще раз"))
    assert e.value.status_code == 400

    r = await env.call(env.admin.republish_channel, cid)
    assert r["status"] == "approved"
    c = await env.get(cid)
    assert c.status == env.CS.approved and c.rejection_reason is None
    rows = await _audit(env, "channel.republish")
    assert rows and rows[0].details["prev_reason"] == "Менше 100 підписників"


@pytest.mark.asyncio
async def test_unpublish_requires_reason_and_republish_restores_removed(env):
    cid = await env.channel()
    with pytest.raises(Exception):
        env.admin.ChannelUnpublishRequest(reason="")
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.unpublish_channel, cid, env.admin.ChannelUnpublishRequest(reason="     "))
    assert e.value.status_code == 400
    removed = await env.channel(status=env.CS.removed, removed_reason="gone")
    await env.call(env.admin.republish_channel, removed)
    c = await env.get(removed)
    assert c.status == env.CS.approved and c.removed_reason is None
    sold = await env.channel(status=env.CS.sold)
    with pytest.raises(HTTPException):
        await env.call(env.admin.republish_channel, sold)
    with pytest.raises(HTTPException):
        await env.call(env.admin.unpublish_channel, sold, env.admin.ChannelUnpublishRequest(reason="причина"))


@pytest.mark.asyncio
async def test_buyer_warning_set_clear_and_in_response(env):
    from app.schemas.channel import ChannelResponse
    cid = await env.channel()
    W = env.admin.BuyerWarningRequest
    r = await env.call(env.admin.set_buyer_warning, cid, W(buyer_warning=" Частина аудиторії — боти "))
    assert r["buyer_warning"] == "Частина аудиторії — боти"
    assert ChannelResponse.model_validate(await env.get(cid)).buyer_warning == "Частина аудиторії — боти"
    await env.call(env.admin.set_buyer_warning, cid, W(buyer_warning="  "))
    assert (await env.get(cid)).buyer_warning is None
    assert len(await _audit(env, "channel.buyer_warning")) == 2


def test_seller_update_schema_cannot_set_buyer_warning():
    from app.schemas.channel import ChannelUpdate
    assert "buyer_warning" not in ChannelUpdate.model_fields


@pytest.mark.asyncio
async def test_notify_helper_formats_reason(monkeypatch):
    bm = importlib.import_module("bot.main")
    bot = SimpleNamespace(send_message=AsyncMock())
    ch = SimpleNamespace(id=62, channel_name="<b>Kanal</b>")
    seller = SimpleNamespace(telegram_id=5)
    await bm.notify_channel_unpublished(bot, ch, seller, "18+ & <спам>")
    text = bot.send_message.await_args.args[1]
    assert "&lt;спам&gt;" in text and "#62" in text and "&lt;b&gt;Kanal" in text
