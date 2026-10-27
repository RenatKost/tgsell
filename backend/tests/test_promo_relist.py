"""Relisting a channel = a NEW channels row (POST /channels) → its own promo Top; anti-farm guards."""
from __future__ import annotations

from datetime import timedelta

import pytest

from tests.test_paid_services import _setup
from tests.test_promo_top import _approve, _cfg, frozen  # noqa: F401
from tests.test_promo_top_paid import _mock_bot

pytestmark = pytest.mark.asyncio


async def _users(orm):
    from app.models.user import User, UserRole
    async with orm.session() as db:
        s = User(first_name="S", username="s", telegram_id=31)
        a = User(first_name="A", username="a", telegram_id=32, role=UserRole.admin)
        db.add_all([s, a])
        await db.commit()
        return s, a


async def _lot(orm, seller, status, link="https://t.me/relist_me", **kw):
    from app.models.channel import Channel, ChannelStatus
    async with orm.session() as db:
        c = Channel(seller_id=seller.id, telegram_link=link, channel_name="R", category="Спорт",
                    subscribers_count=1000, price=100, status=ChannelStatus(status), **kw)
        db.add(c)
        await db.commit()
        return c.id


async def _submit(client, cur, seller, link="https://t.me/relist_me"):
    cur.user = seller
    r = await client.post("/api/channels", json={"telegram_link": link, "channel_name": "R", "category": "Спорт", "price": 100})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.parametrize("old_status", ["removed", "rejected", "sold"])
async def test_relist_after_removal_is_new_lot_with_promo(orm, monkeypatch, frozen, old_status):  # noqa: F811
    _cfg(monkeypatch)
    _mock_bot(monkeypatch)
    client, cur = await _setup(orm, monkeypatch)
    seller, adm = await _users(orm)
    old = await _lot(orm, seller, old_status, first_approved_at=frozen["now"] - timedelta(days=30),
                     top_until=frozen["now"] - timedelta(days=20), top_source="promo")
    new = await _submit(client, cur, seller)
    assert new != old  # relist creates a separate channels row; first_approved_at starts NULL
    ch = await _approve(orm, monkeypatch, client, cur, adm, new)
    assert ch.top_source == "promo" and ch.top_until == frozen["now"] + timedelta(days=7)


async def test_relist_after_deadline_no_promo(orm, monkeypatch, frozen):  # noqa: F811
    _cfg(monkeypatch)
    _mock_bot(monkeypatch)
    frozen["now"] = frozen["now"].replace(month=11, day=2)
    client, cur = await _setup(orm, monkeypatch)
    seller, adm = await _users(orm)
    await _lot(orm, seller, "removed", first_approved_at=frozen["now"] - timedelta(days=30))
    ch = await _approve(orm, monkeypatch, client, cur, adm, await _submit(client, cur, seller))
    assert ch.top_until is None


async def test_active_lot_cannot_be_duplicated(orm, monkeypatch):
    client, cur = await _setup(orm, monkeypatch)
    seller, _ = await _users(orm)
    await _lot(orm, seller, "approved")
    cur.user = seller
    r = await client.post("/api/channels", json={"telegram_link": "https://t.me/relist_me", "channel_name": "R",
                                                 "category": "Спорт", "price": 100})
    assert r.status_code == 409


async def test_reapproving_active_lot_no_second_promo(orm, monkeypatch, frozen):  # noqa: F811
    _cfg(monkeypatch)
    _mock_bot(monkeypatch)
    frozen["now"] = frozen["now"].replace(day=20)
    client, cur = await _setup(orm, monkeypatch)
    seller, adm = await _users(orm)
    cid = await _submit(client, cur, seller)
    first = await _approve(orm, monkeypatch, client, cur, adm, cid)
    from app.models.channel import Channel, ChannelStatus
    async with orm.session() as db:
        c = await db.get(Channel, cid)
        c.status = ChannelStatus.pending
        await db.commit()
    frozen["now"] += timedelta(days=5)
    again = await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert again.top_until == first.top_until


async def test_delete_and_resubmit_while_promo_running_is_not_farmable(orm, monkeypatch, frozen):  # noqa: F811
    _cfg(monkeypatch)
    _mock_bot(monkeypatch)
    frozen["now"] = frozen["now"].replace(day=20)
    client, cur = await _setup(orm, monkeypatch)
    seller, adm = await _users(orm)
    cid = await _submit(client, cur, seller)
    first = await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert first.top_source == "promo"
    cur.user = seller
    assert (await client.delete(f"/api/channels/{cid}")).status_code == 204
    frozen["now"] += timedelta(days=3)
    ch = await _approve(orm, monkeypatch, client, cur, adm, await _submit(client, cur, seller))
    assert ch.top_until is None  # promo of the deleted lot still running → no new one
    frozen["now"] += timedelta(days=5)  # first promo expired → genuine relist gets promo again
    cur.user = seller
    assert (await client.delete(f"/api/channels/{ch.id}")).status_code == 204
    ch2 = await _approve(orm, monkeypatch, client, cur, adm, await _submit(client, cur, seller))
    assert ch2.top_source == "promo"
