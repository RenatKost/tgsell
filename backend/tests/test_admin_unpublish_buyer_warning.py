"""Admin «Зняти з публікації / відхилити з причиною», republish, buyer_warning."""
from __future__ import annotations

import importlib
import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select


_seq = itertools.count(1)


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
            c = Channel(seller_id=ids.seller, telegram_link=kw.pop("telegram_link", f"https://t.me/x{next(_seq)}"),
                        channel_name="X", category="news",
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
    # legacy removed lot (no audit entry) that was approved before → approved
    from app.utils.timeutil import utcnow_naive
    removed = await env.channel(status=env.CS.removed, removed_reason="gone", first_approved_at=utcnow_naive())
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


# ── republish restores the status before the takedown (no moderation bypass) ──

async def _republish(env, cid):
    r = await env.call(env.admin.republish_channel, cid)
    rows = [x for x in await _audit(env, "channel.republish") if x.target_id == cid]
    return r, rows[-1].details


@pytest.mark.asyncio
async def test_pending_deleted_republish_returns_to_pending(env):
    cid = await env.channel(status=env.CS.pending)
    await env.call(env.admin.admin_delete_channel, cid)
    assert (await env.get(cid)).status == env.CS.removed
    env.notify.reset_mock()
    r, details = await _republish(env, cid)
    c = await env.get(cid)
    assert r["status"] == "pending" and c.status == env.CS.pending
    assert c.removed_at is None and c.removed_reason is None and c.removed_by_id is None
    assert details["restored_status"] == "pending" and details["restored_from"] == "audit_log"
    assert details["prev_status"] == "removed"
    env.notify.assert_not_awaited()  # no «знову опубліковано» for a lot that goes to moderation


@pytest.mark.asyncio
async def test_approved_removed_republish_returns_to_approved(env):
    cid = await env.channel(status=env.CS.approved)
    await env.call(env.admin.remove_channel_from_market, cid,
                   env.admin.ChannelRemoveRequest(confirm=True, reason="неактивний"))
    assert (await env.get(cid)).status == env.CS.removed
    r, details = await _republish(env, cid)
    assert r["status"] == "approved" and (await env.get(cid)).status == env.CS.approved
    assert details["restored_status"] == "approved" and details["restored_from"] == "audit_log"
    assert env.notify.await_args.args[2] == "republish"


@pytest.mark.asyncio
async def test_unpublished_then_deleted_walks_back_to_approved(env):
    cid = await env.channel(status=env.CS.approved)
    await env.call(env.admin.unpublish_channel, cid, env.admin.ChannelUnpublishRequest(reason="причина"))
    await env.call(env.admin.admin_delete_channel, cid)  # records prev_status=rejected
    r, details = await _republish(env, cid)
    assert r["status"] == "approved"
    assert details["restored_status"] == "approved" and details["restored_from"] == "audit_log"


@pytest.mark.asyncio
async def test_moderation_reject_then_republish_goes_back_to_pending(env):
    cid = await env.channel(status=env.CS.pending)
    await env.call(env.admin.reject_channel, cid, reason="мало підписників")
    r, details = await _republish(env, cid)
    assert r["status"] == "pending"
    assert details["restored_status"] == "pending"


@pytest.mark.asyncio
async def test_legacy_without_prev_status_never_approved_goes_to_pending(env):
    from app.models.user import AdminAuditLog
    cid = await env.channel(status=env.CS.removed, removed_reason="old")
    async with env.orm.session() as db:  # legacy entry without prev_status
        db.add(AdminAuditLog(actor_id=None, action="channel.delete", target_type="channel", target_id=cid,
                             details={"reason": "old"}))
        await db.commit()
    r, details = await _republish(env, cid)
    assert r["status"] == "pending" and (await env.get(cid)).status == env.CS.pending
    assert details["restored_from"] == "never_approved"


@pytest.mark.asyncio
async def test_legacy_rejected_with_approve_log_goes_to_approved(env):
    from app.models.user import AdminAuditLog
    cid = await env.channel(status=env.CS.rejected, rejection_reason="legacy")
    async with env.orm.session() as db:
        db.add(AdminAuditLog(actor_id=None, action="channel.approve", target_type="channel", target_id=cid))
        await db.commit()
    r, details = await _republish(env, cid)
    assert r["status"] == "approved" and details["restored_from"] == "approve_log"


@pytest.mark.asyncio
async def test_republish_refused_when_same_link_is_live(env):
    old = await env.channel(status=env.CS.approved, telegram_link="https://t.me/dupchan")
    await env.call(env.admin.remove_channel_from_market, old,
                   env.admin.ChannelRemoveRequest(confirm=True, reason="x"))
    await env.channel(status=env.CS.pending, telegram_link="https://t.me/DupChan")
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.republish_channel, old)
    assert e.value.status_code == 409
    assert (await env.get(old)).status == env.CS.removed
