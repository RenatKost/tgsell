"""Seller promo: free «Топ» 7 days on first moderation approval before the configured deadline."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.asyncio

from tests.test_paid_services import _setup


def _cfg(monkeypatch, until="2026-11-01T23:59:00"):
    from app.config import settings
    monkeypatch.setattr(settings, "promo_top_until", until)
    monkeypatch.setattr(settings, "promo_top_tz", "Europe/Chisinau")
    monkeypatch.setattr(settings, "promo_top_days", 7)


async def _seed_pending(orm, **kw):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    async with orm.session() as db:
        seller = User(first_name="S", username="s", telegram_id=11)
        adm = User(first_name="A", username="a", telegram_id=12, role=UserRole.admin)
        db.add_all([seller, adm])
        await db.flush()
        ch = Channel(seller_id=seller.id, telegram_link="https://t.me/promo1", channel_name="P", category="Спорт",
                     subscribers_count=1000, price=100, status=ChannelStatus.pending, **kw)
        db.add(ch)
        await db.commit()
        return adm, ch.id


async def _approve(orm, monkeypatch, client, cur, adm, cid):
    cur.user = adm
    r = await client.post(f"/api/admin/channels/{cid}/approve")
    assert r.status_code == 200, r.text
    from app.models.channel import Channel
    async with orm.session() as db:
        return await db.get(Channel, cid)


@pytest.fixture
def frozen(monkeypatch):
    """Pin 'now' used by the approve endpoint + promo service."""
    holder = {"now": datetime(2026, 10, 27, 10, 0)}
    admin = importlib.import_module("app.routers.admin")
    promo = importlib.import_module("app.services.promo_top")

    class _DT(datetime):
        @classmethod
        def utcnow(cls):
            return holder["now"]
    monkeypatch.setattr(admin, "datetime", _DT)
    monkeypatch.setattr(promo, "utcnow_naive", lambda: holder["now"])

    async def no_stats(link):
        raise RuntimeError("offline")
    monkeypatch.setattr(importlib.import_module("app.services.channel_stats"), "collect_channel_stats", no_stats)
    return holder


async def test_approval_before_deadline_gives_7d_top(orm, monkeypatch, frozen):
    _cfg(monkeypatch)
    client, cur = await _setup(orm, monkeypatch)
    adm, cid = await _seed_pending(orm)
    ch = await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert ch.top_until == frozen["now"] + timedelta(days=7)
    assert ch.top_source == "promo"
    assert ch.first_approved_at == frozen["now"]
    from app.models.paid_service import PaidServiceOrder
    from sqlalchemy import select, func
    async with orm.session() as db:
        assert (await db.execute(select(func.count(PaidServiceOrder.id)))).scalar() == 0  # no payment record


@pytest.mark.filterwarnings("ignore")
async def test_deadline_is_local_chisinau_time(monkeypatch):
    _cfg(monkeypatch)
    from app.services import promo_top
    # 2026-11-01 23:59 Europe/Chisinau (EET, UTC+2) == 21:59 UTC
    assert promo_top.promo_deadline_utc() == datetime(2026, 11, 1, 21, 59)
    assert promo_top.promo_active(datetime(2026, 11, 1, 21, 59))
    assert not promo_top.promo_active(datetime(2026, 11, 1, 22, 0))


async def test_approval_after_deadline_gives_nothing(orm, monkeypatch, frozen):
    _cfg(monkeypatch)
    frozen["now"] = datetime(2026, 11, 1, 22, 0)  # 00:00 Nov 2 Chisinau
    client, cur = await _setup(orm, monkeypatch)
    adm, cid = await _seed_pending(orm)
    ch = await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert ch.top_until is None and ch.top_source is None
    assert ch.first_approved_at is not None


async def test_reapproval_does_not_duplicate(orm, monkeypatch, frozen):
    _cfg(monkeypatch)
    client, cur = await _setup(orm, monkeypatch)
    adm, cid = await _seed_pending(orm)
    first = await _approve(orm, monkeypatch, client, cur, adm, cid)
    from app.models.channel import Channel, ChannelStatus
    async with orm.session() as db:  # seller edits → back to moderation
        c = await db.get(Channel, cid)
        c.status = ChannelStatus.pending
        await db.commit()
    frozen["now"] = frozen["now"] + timedelta(days=3)
    again = await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert again.top_until == first.top_until
    assert again.first_approved_at == first.first_approved_at


async def test_previously_approved_lot_not_retroactive(orm, monkeypatch, frozen):
    _cfg(monkeypatch)
    client, cur = await _setup(orm, monkeypatch)
    adm, cid = await _seed_pending(orm, first_approved_at=datetime(2026, 9, 1))  # backfilled by migration
    ch = await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert ch.top_until is None


async def test_longer_existing_top_not_shortened(orm, monkeypatch, frozen):
    _cfg(monkeypatch)
    client, cur = await _setup(orm, monkeypatch)
    longer = frozen["now"] + timedelta(days=20)
    adm, cid = await _seed_pending(orm, top_until=longer, top_source="paid")
    ch = await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert ch.top_until == longer and ch.top_source == "paid"


async def test_shorter_existing_top_extended(orm, monkeypatch, frozen):
    _cfg(monkeypatch)
    client, cur = await _setup(orm, monkeypatch)
    adm, cid = await _seed_pending(orm, top_until=frozen["now"] + timedelta(days=2), top_source="paid")
    ch = await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert ch.top_until == frozen["now"] + timedelta(days=7)


async def test_public_promo_endpoint(orm, monkeypatch):
    _cfg(monkeypatch)
    client, cur = await _setup(orm, monkeypatch)
    promo = importlib.import_module("app.services.promo_top")
    monkeypatch.setattr(promo, "utcnow_naive", lambda: datetime(2026, 10, 30))
    r = await client.get("/api/services/promo")
    assert r.status_code == 200
    j = r.json()
    assert j["active"] is True and j["days"] == 7 and j["ends_at_local"].startswith("2026-11-01T23:59:00")
    monkeypatch.setattr(promo, "utcnow_naive", lambda: datetime(2026, 11, 2))
    assert (await client.get("/api/services/promo")).json()["active"] is False
