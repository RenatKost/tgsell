"""Moderator «Запитати уточнення» / seller reply on the same lot."""
from __future__ import annotations

import html
import importlib
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select


@pytest_asyncio.fixture
async def env(pg_orm, monkeypatch):
    from app.models.user import User, UserRole

    from unittest.mock import AsyncMock
    admin_r = importlib.import_module("app.routers.admin")
    ch_r = importlib.import_module("app.routers.channels")
    notify_seller = AsyncMock()
    notify_admin = AsyncMock()
    import bot.main as bot_main
    monkeypatch.setattr(bot_main, "notify_channel_clarification_requested", notify_seller)
    monkeypatch.setattr(bot_main, "notify_admin_clarification_reply", notify_admin)

    class FakeBot:
        def __init__(self, token=None, **_kw):
            self.token = token
            self.session = SimpleNamespace(close=AsyncMock())
            self.send_message = AsyncMock()
    monkeypatch.setattr("aiogram.Bot", FakeBot)
    if hasattr(admin_r, "_notify_seller_channel_approved"):
        monkeypatch.setattr(admin_r, "_notify_seller_channel_approved", AsyncMock())
    from app.config import settings
    monkeypatch.setattr(settings, "admin_group_id", 111, raising=False)
    monkeypatch.setattr(settings, "bot_token_alerts", "123:test-token", raising=False)
    if not getattr(settings, "frontend_url", None):
        monkeypatch.setattr(settings, "frontend_url", "https://tgsell.me", raising=False)

    async with pg_orm.session() as db:
        admin = User(first_name="Mod", telegram_id=71001, role=UserRole.admin)
        mod = User(first_name="Moder", telegram_id=71002, role=UserRole.moderator)
        seller = User(first_name="Seller", telegram_id=71003, role=UserRole.user)
        other = User(first_name="Other", telegram_id=71004, role=UserRole.user)
        db.add_all([admin, mod, seller, other])
        await db.commit()
    ids = SimpleNamespace(admin=admin.id, mod=mod.id, seller=seller.id, other=other.id)

    async def channel(**kw):
        from app.models.channel import Channel, ChannelStatus
        async with pg_orm.session() as db:
            c = Channel(
                seller_id=ids.seller,
                telegram_link=kw.pop("telegram_link", "https://t.me/clarify_lot"),
                channel_name=kw.pop("channel_name", "ClarifyLot"),
                category=kw.pop("category", "news"),
                price=kw.pop("price", 100.0),
                status=kw.pop("status", ChannelStatus.pending),
                **kw,
            )
            db.add(c)
            await db.commit()
            return c.id

    async def get(cid):
        from app.models.channel import Channel
        async with pg_orm.session() as db:
            return await db.get(Channel, cid)

    async def as_user(uid):
        from app.models.user import User
        async with pg_orm.session() as db:
            return await db.get(User, uid)

    async def staff_call(fn, *a, staff="admin", **kw):
        from app.models.user import User
        uid = ids.admin if staff == "admin" else ids.mod
        async with pg_orm.session() as db:
            return await fn(*a, admin=await db.get(User, uid), db=db, **kw)

    async def seller_call(fn, *a, uid=None, **kw):
        from app.models.user import User
        async with pg_orm.session() as db:
            return await fn(*a, user=await db.get(User, uid or ids.seller), db=db, **kw)

    return SimpleNamespace(
        orm=pg_orm, admin=admin_r, channels=ch_r, ids=ids, channel=channel, get=get,
        staff_call=staff_call, seller_call=seller_call, as_user=as_user,
        notify_seller=notify_seller, notify_admin=notify_admin,
    )


async def _audit(env, action):
    from app.models.user import AdminAuditLog
    async with env.orm.session() as db:
        return (await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action))).scalars().all()


@pytest.mark.asyncio
async def test_staff_can_ask_moderator_too(env):
    from app.models.channel import ChannelStatus
    cid = await env.channel()
    body = env.admin.ChannelClarifyRequest(question="Додайте скрін статистики за 30 днів")
    r = await env.staff_call(env.admin.clarify_channel, cid, body, staff="mod")
    assert r.status == "needs_clarification"
    assert r.clarifications and r.clarifications[0].question.startswith("Додайте")
    assert (await env.get(cid)).status == ChannelStatus.needs_clarification
    logs = await _audit(env, "channel.clarify")
    assert len(logs) == 1 and logs[0].target_id == cid
    env.notify_seller.assert_awaited()


@pytest.mark.asyncio
async def test_question_is_required_and_length_limited(env):
    from fastapi import HTTPException
    from pydantic import ValidationError
    from app.models.channel import Channel
    from app.models.user import User
    from app.services.clarifications import ask

    with pytest.raises(ValidationError):
        env.admin.ChannelClarifyRequest(question="hey")
    with pytest.raises(ValidationError):
        env.admin.ChannelClarifyRequest(question="x" * 2001)

    cid = await env.channel()
    async with env.orm.session() as db:
        channel = await db.get(Channel, cid)
        admin = await db.get(User, env.ids.admin)
        with pytest.raises(HTTPException) as e:
            await ask(db, channel, admin, "   ab  ")
        assert e.value.status_code == 400
        assert (await db.get(Channel, cid)).status.value == "pending"


@pytest.mark.asyncio
async def test_only_staff_may_ask(env):
    import httpx
    from fastapi import FastAPI
    from app.models.user import User
    from app.utils import security

    cid = await env.channel()

    async def as_seller():
        async with env.orm.session() as db:
            return await db.get(User, env.ids.seller)

    app = FastAPI()
    app.include_router(env.admin.router, prefix="/api")
    app.dependency_overrides[security.get_current_user] = as_seller
    app.dependency_overrides[env.admin.get_db] = env.orm.get_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        r = await client.post(f"/api/admin/channels/{cid}/clarify", json={"question": "Чому така ціна, поясніть"})
    assert r.status_code == 403
    assert (await env.get(cid)).status.value == "pending"


@pytest.mark.asyncio
async def test_seller_replies_same_id_returns_to_pending(env):
    from app.models.channel import ChannelStatus
    cid = await env.channel(description="old")
    body = env.admin.ChannelClarifyRequest(question="Оновіть опис і ціну")
    await env.staff_call(env.admin.clarify_channel, cid, body)
    reply = env.channels.ChannelClarificationReply(
        description="Новий детальний опис", price=150, answer="Опис оновив, ціну підняв",
    )
    r = await env.seller_call(env.channels.reply_to_clarification, cid, reply)
    assert r.id == cid
    assert r.status == "pending"
    assert r.price == 150
    assert r.description == "Новий детальний опис"
    assert r.clarifications[-1].answer == "Опис оновив, ціну підняв"
    assert (await env.get(cid)).status == ChannelStatus.pending
    logs = await _audit(env, "channel.clarify_reply")
    assert logs and logs[0].target_id == cid
    env.notify_admin.assert_awaited()


@pytest.mark.asyncio
async def test_only_owner_can_reply(env):
    cid = await env.channel()
    await env.staff_call(env.admin.clarify_channel, cid, env.admin.ChannelClarifyRequest(question="Чому така ціна?"))
    with pytest.raises(HTTPException) as e:
        await env.seller_call(
            env.channels.reply_to_clarification, cid,
            env.channels.ChannelClarificationReply(answer="не мій лот"),
            uid=env.ids.other,
        )
    assert e.value.status_code == 403
    assert (await env.get(cid)).status.value == "needs_clarification"


@pytest.mark.asyncio
async def test_cannot_reply_when_pending(env):
    cid = await env.channel()
    with pytest.raises(HTTPException) as e:
        await env.seller_call(
            env.channels.reply_to_clarification, cid,
            env.channels.ChannelClarificationReply(answer="ще не питали"),
        )
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_cannot_clarify_approved_or_sold(env):
    from app.models.channel import ChannelStatus
    for st in (ChannelStatus.approved, ChannelStatus.sold, ChannelStatus.rejected, ChannelStatus.removed):
        cid = await env.channel(status=st, telegram_link=f"https://t.me/x{st.value}")
        with pytest.raises(HTTPException) as e:
            await env.staff_call(
                env.admin.clarify_channel, cid,
                env.admin.ChannelClarifyRequest(question="Чому така ціна, поясніть"),
            )
        assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_approve_and_reject_work_from_needs_clarification(env):
    from app.models.channel import ChannelStatus
    cid_a = await env.channel(telegram_link="https://t.me/approve_me")
    cid_r = await env.channel(telegram_link="https://t.me/reject_me")
    q = env.admin.ChannelClarifyRequest(question="Потрібне уточнення по аудиторії")
    await env.staff_call(env.admin.clarify_channel, cid_a, q)
    await env.staff_call(env.admin.clarify_channel, cid_r, q)
    approved = await env.staff_call(env.admin.approve_channel, cid_a)
    assert approved.status == "approved"
    assert (await env.get(cid_a)).status == ChannelStatus.approved
    rejected = await env.staff_call(env.admin.reject_channel, cid_r, reason="не підходить")
    assert rejected.status == "rejected"
    assert (await env.get(cid_r)).status == ChannelStatus.rejected


@pytest.mark.asyncio
async def test_pending_queue_includes_clarification_lots_with_history(env):
    cid = await env.channel()
    await env.staff_call(
        env.admin.clarify_channel, cid,
        env.admin.ChannelClarifyRequest(question="Додайте середній охоплення"),
    )
    pending = await env.staff_call(env.admin.get_pending_channels)
    match = [c for c in pending if c.id == cid]
    assert match and match[0].status == "needs_clarification"
    assert match[0].clarifications[0].question.startswith("Додайте")


@pytest.mark.asyncio
async def test_not_in_public_catalog_or_public_page(env):
    import httpx
    from fastapi import FastAPI
    from app.routers import channels as ch_router
    from app.utils import security

    cid = await env.channel()
    await env.staff_call(
        env.admin.clarify_channel, cid,
        env.admin.ChannelClarifyRequest(question="Уточніть джерело трафіку, будь ласка"),
    )

    app = FastAPI()
    app.include_router(ch_router.router, prefix="/api")
    app.dependency_overrides[security.get_optional_user] = lambda: None
    app.dependency_overrides[ch_router.get_db] = env.orm.get_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        listed = await client.get("/api/channels")
        assert listed.status_code == 200
        assert all(item["id"] != cid for item in listed.json()["items"])
        one = await client.get(f"/api/channels/{cid}")
        assert one.status_code == 404
        assert "clarifications" not in (one.json() or {}) or not one.json().get("clarifications")


@pytest.mark.asyncio
async def test_owner_sees_question_on_lot_page(env):
    from app.models.user import User
    cid = await env.channel()
    await env.staff_call(
        env.admin.clarify_channel, cid,
        env.admin.ChannelClarifyRequest(question="Покажіть дохід за останні 3 місяці"),
    )
    from app.models.user import User
    async with env.orm.session() as db:
        seller = await db.get(User, env.ids.seller)
        r = await env.channels.get_channel(cid, db=db, viewer=seller)
    assert r.status == "needs_clarification"
    assert r.clarifications[0].question.startswith("Покажіть")


@pytest.mark.asyncio
async def test_notify_escapes_html_in_moderator_question():
    from bot.main import notify_channel_clarification_requested, notify_admin_clarification_reply
    from unittest.mock import AsyncMock, MagicMock
    from types import SimpleNamespace

    evild = '<script>alert(1)</script> & "q"'
    bot = MagicMock()
    bot.send_message = AsyncMock()
    channel = SimpleNamespace(id=9, channel_name='<b>Evil</b>', telegram_link="@x", listing_type="sale", price=10, seller_id=1)
    seller = SimpleNamespace(telegram_id=123, first_name='A&B <x>')
    import bot.main as bm
    # settings.frontend_url and admin_group_id
    await notify_channel_clarification_requested(bot, channel, seller, evild)
    text = bot.send_message.await_args.args[1]
    assert "<script>" not in text
    assert html.escape(evild) in text
    assert html.escape("<b>Evil</b>") in text

    from app.config import settings
    old = settings.admin_group_id
    settings.admin_group_id = 1
    try:
        bot.send_message.reset_mock()
        await notify_admin_clarification_reply(bot, channel, seller, evild)
        text = bot.send_message.await_args.args[1]
        assert "<script>" not in text
        assert "&amp;" in text or html.escape(evild) in text
    finally:
        settings.admin_group_id = old
