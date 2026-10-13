"""Task 15 item 1: inactive channels list + 'Зняти з біржі'."""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

NOT_FOUND = {"ok": False, "reason": "Bot API: Bad Request: chat not found; Telethon: No user has \"x\" as username"}
TRANSIENT = {"ok": False, "reason": "Telethon: database is locked"}
OK = {"ok": True, "reason": None}


@pytest_asyncio.fixture
async def env(pg_orm, monkeypatch):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole

    sc = importlib.import_module("app.tasks.stats_collector")
    admin_r = importlib.import_module("app.routers.admin")
    monkeypatch.setattr(sc, "async_session", pg_orm.session)
    monkeypatch.setattr(sc, "reset_telethon_retries", lambda: None)
    monkeypatch.setattr(sc.asyncio, "sleep", AsyncMock())
    alerts = importlib.import_module("app.services.alerts")
    monkeypatch.setattr(alerts, "alert_stats_summary", AsyncMock())
    checks: dict[str, dict] = {}
    calls: list[str] = []

    async def fake_collect(link, message_limit=5000):
        calls.append(link)
        return {"check": checks.get(link, OK), "subscribers_count": 0, "daily_stats": []}

    monkeypatch.setattr(sc, "collect_channel_stats", fake_collect)

    async with pg_orm.session() as db:
        admin = User(first_name="A", telegram_id=1, role=UserRole.admin)
        seller = User(first_name="S", telegram_id=2)
        buyer = User(first_name="B", telegram_id=3)
        db.add_all([admin, seller, buyer])
        await db.commit()
    ids = SimpleNamespace(admin=admin.id, seller=seller.id, buyer=buyer.id)

    async def channel(link, **kw):
        async with pg_orm.session() as db:
            c = Channel(seller_id=ids.seller, telegram_link=link, channel_name=link, category="news",
                        price=kw.pop("price", 10.0), status=kw.pop("status", ChannelStatus.approved), **kw)
            db.add(c)
            await db.commit()
            return c.id

    async def get(cid):
        async with pg_orm.session() as db:
            return await db.get(Channel, cid)

    async def call(fn, *a, **kw):
        async with pg_orm.session() as db:
            return await fn(*a, admin=await db.get(User, ids.admin), db=db, **kw)

    return SimpleNamespace(orm=pg_orm, sc=sc, admin=admin_r, checks=checks, calls=calls, channel=channel,
                           get=get, call=call, ids=ids, CS=ChannelStatus)


@pytest.mark.asyncio
async def test_collector_records_checks_and_lists_inactive(env):
    gone = await env.channel("https://t.me/homwar3333")
    flaky = await env.channel("https://t.me/flaky")
    fine = await env.channel("https://t.me/fine")
    closed = await env.channel("https://t.me/+abc", is_closed=True, subscribers_count=0)
    env.checks["https://t.me/homwar3333"] = NOT_FOUND
    env.checks["https://t.me/flaky"] = TRANSIENT
    await env.sc.collect_stats_once()
    g, f, ok = await env.get(gone), await env.get(flaky), await env.get(fine)
    assert g.inactive_since and "chat not found" in g.check_error and g.last_check_ok_at is None
    assert f.inactive_since is None and f.check_error  # transient: not inactive
    assert ok.last_check_ok_at and ok.inactive_since is None
    items = (await env.call(env.admin.list_inactive_channels))["items"]
    assert [i["id"] for i in items] == [gone]
    assert items[0]["reason"].startswith("Bot API") and items[0]["blockers"] == []
    assert closed not in [i["id"] for i in items]
    # recovers → leaves the list, last ok date stored
    env.checks["https://t.me/homwar3333"] = OK
    await env.sc.collect_stats_once()
    g = await env.get(gone)
    assert g.inactive_since is None and g.last_check_ok_at is not None


@pytest.mark.asyncio
async def test_zero_price_bundle_lot_is_not_inactive(env):
    from app.models.bundle import BundleChannel, ChannelBundle

    cid = await env.channel("https://t.me/inbundle", price=0.0)
    async with env.orm.session() as db:
        cols = {c.name for c in ChannelBundle.__table__.columns}
        kw = {k: v for k, v in dict(seller_id=env.ids.seller, name="B", price=10.0, category="news").items() if k in cols}
        b = ChannelBundle(**kw)
        db.add(b)
        await db.flush()
        db.add(BundleChannel(bundle_id=b.id, channel_id=cid))
        await db.commit()
    env.checks["https://t.me/inbundle"] = NOT_FOUND
    await env.sc.collect_stats_once()
    assert (await env.get(cid)).inactive_since is None
    assert (await env.call(env.admin.list_inactive_channels))["items"] == []


@pytest.mark.asyncio
async def test_remove_soft_deletes_audits_and_collector_skips(env):
    from app.models.user import AdminAuditLog

    cid = await env.channel("https://t.me/motivatorsse")
    env.checks["https://t.me/motivatorsse"] = NOT_FOUND
    await env.sc.collect_stats_once()
    R = env.admin.ChannelRemoveRequest
    with pytest.raises(HTTPException) as e:
        await env.call(env.admin.remove_channel_from_market, cid, R(confirm=False))
    assert e.value.status_code == 400
    r = await env.call(env.admin.remove_channel_from_market, cid, R(confirm=True))
    assert r["status"] == "removed"
    c = await env.get(cid)
    assert c.status == env.CS.removed and c.removed_by_id == env.ids.admin and "chat not found" in c.removed_reason
    async with env.orm.session() as db:
        logs = list((await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "channel.remove"))).scalars())
    assert len(logs) == 1 and logs[0].target_id == cid
    env.calls.clear()
    await env.sc.collect_stats_once()
    assert "https://t.me/motivatorsse" not in env.calls  # removed lots are skipped
    assert (await env.call(env.admin.list_inactive_channels))["items"] == []
    again = await env.call(env.admin.remove_channel_from_market, cid, R(confirm=True))
    assert again["status"] == "removed"


@pytest.mark.asyncio
async def test_remove_blocked_by_active_deal_or_auction_with_bids(env):
    from datetime import timedelta

    from app.models.auction import Auction
    from app.models.deal import Deal, DealStatus
    from app.utils.timeutil import utcnow_naive

    d_cid = await env.channel("https://t.me/avtomoto30")
    a_cid = await env.channel("https://t.me/orbita_maska365")
    async with env.orm.session() as db:
        db.add(Deal(channel_id=d_cid, buyer_id=env.ids.buyer, seller_id=env.ids.seller, status=DealStatus.paid,
                    escrow_wallet_address="TX1", escrow_private_key_encrypted="e", amount_usdt=10, service_fee=0.3))
        now = utcnow_naive()
        db.add(Auction(channel_id=a_cid, seller_id=env.ids.seller, start_price=5, current_price=7, status="active",
                       starts_at=now, ends_at=now + timedelta(hours=1), bid_count=2))
        await db.commit()
    R = env.admin.ChannelRemoveRequest
    for cid, word in ((d_cid, "Активна угода"), (a_cid, "ставок")):
        with pytest.raises(HTTPException) as e:
            await env.call(env.admin.remove_channel_from_market, cid, R(confirm=True))
        assert e.value.status_code == 409 and word in e.value.detail
        assert (await env.get(cid)).status == env.CS.approved


def test_resolution_classifier():
    ca = importlib.import_module("app.services.channel_availability")
    assert ca.is_resolution_error('Telethon: No user has "wicherstm" as username')
    assert ca.is_resolution_error("Bot API: Bad Request: chat not found")
    assert not ca.is_resolution_error("Telethon: FloodWaitError 30s")
    assert not ca.is_resolution_error(None)
