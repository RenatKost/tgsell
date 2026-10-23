"""Bundle moderation on «На модерації»: a pending bundle is ONE card; its member
channels are never listed / moderated on their own; approve/reject cascade."""
from __future__ import annotations

import importlib
import sys
from types import ModuleType

import pytest
from fastapi import HTTPException
from sqlalchemy import select


@pytest.fixture
def no_bot(monkeypatch):
    stub = ModuleType("bot.main")

    async def _noop(*a, **kw):
        return None

    stub.notify_bundle_approved = _noop
    stub.notify_bundle_rejected = _noop
    monkeypatch.setitem(sys.modules, "bot.main", stub)


async def _seed(orm):
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole

    async with orm.session() as db:
        admin = User(first_name="Admin", telegram_id=835001, role=UserRole.admin)
        seller = User(first_name="avrora", telegram_id=835002, role=UserRole.user)
        db.add_all([admin, seller])
        await db.flush()
        links = ["BDSN_novyny", "+TNWUA62W9pQ3YzYy", "ukr_informue"]
        members = [Channel(seller_id=seller.id, telegram_link=l, channel_name=f"ch{i}", category="Новини",
                           price=0.0, status=ChannelStatus.pending, is_closed=(i == 1))
                   for i, l in enumerate(links)]
        solo = Channel(seller_id=seller.id, telegram_link="https://t.me/solo", channel_name="solo",
                       category="Новини", price=500.0, status=ChannelStatus.pending)
        db.add_all(members + [solo])
        b = ChannelBundle(seller_id=seller.id, name="БДСН + Інформує Україна (3 канали)", category="Новини",
                          price=33000, status=BundleStatus.pending)
        db.add(b)
        await db.flush()
        db.add_all([BundleChannel(bundle_id=b.id, channel_id=c.id, display_order=i) for i, c in enumerate(members)])
        await db.commit()
        return admin, b.id, [c.id for c in members], solo.id


def _admin_mod():
    return importlib.import_module("app.routers.admin")


@pytest.mark.asyncio
async def test_pending_lists_bundle_once_and_hides_members(orm):
    admin, bid, member_ids, solo_id = await _seed(orm)
    adm = _admin_mod()
    async with orm.session() as db:
        chans = await adm.get_pending_channels(admin=admin, db=db)
        bundles = await adm.get_pending_bundles(admin=admin, db=db)
    assert [c.id for c in chans] == [solo_id]
    assert bundles["total"] == 1
    b = bundles["items"][0]
    assert b["id"] == bid and b["price"] == 33000 and b["channel_count"] == 3
    assert [c["id"] for c in b["channels_detail"]] == member_ids
    assert b["channels_detail"][0]["url"] == "https://t.me/BDSN_novyny"
    assert b["channels_detail"][1]["is_closed"] is True


@pytest.mark.asyncio
async def test_approve_bundle_cascades(orm, no_bot):
    from app.models.bundle import BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus

    admin, bid, member_ids, solo_id = await _seed(orm)
    adm = _admin_mod()
    async with orm.session() as db:
        await adm.approve_bundle(bundle_id=bid, admin=admin, db=db)
    async with orm.session() as db:
        b = (await db.execute(select(ChannelBundle).where(ChannelBundle.id == bid))).scalar_one()
        cs = {c.id: c for c in (await db.execute(select(Channel))).scalars()}
    assert b.status == BundleStatus.approved
    assert all(cs[i].status == ChannelStatus.approved and cs[i].moderator_id == admin.id for i in member_ids)
    assert cs[solo_id].status == ChannelStatus.pending


@pytest.mark.asyncio
async def test_reject_bundle_cascades_with_reason(orm, no_bot):
    from app.models.bundle import BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus

    admin, bid, member_ids, solo_id = await _seed(orm)
    adm = _admin_mod()
    async with orm.session() as db:
        await adm.reject_bundle(bundle_id=bid, reason="Ціна завищена", admin=admin, db=db)
    async with orm.session() as db:
        b = (await db.execute(select(ChannelBundle).where(ChannelBundle.id == bid))).scalar_one()
        cs = {c.id: c for c in (await db.execute(select(Channel))).scalars()}
    assert b.status == BundleStatus.rejected and b.rejection_reason == "Ціна завищена"
    for i in member_ids:
        assert cs[i].status == ChannelStatus.rejected and cs[i].rejection_reason == "Ціна завищена"
    assert cs[solo_id].status == ChannelStatus.pending


@pytest.mark.asyncio
async def test_member_channel_cannot_be_moderated_alone(orm):
    from app.models.channel import Channel, ChannelStatus

    admin, bid, member_ids, solo_id = await _seed(orm)
    adm = _admin_mod()
    async with orm.session() as db:
        with pytest.raises(HTTPException) as e1:
            await adm.approve_channel(channel_id=member_ids[0], admin=admin, db=db)
        with pytest.raises(HTTPException) as e2:
            await adm.reject_channel(channel_id=member_ids[1], reason="x", admin=admin, db=db)
    assert e1.value.status_code == 400 and "сітки" in e1.value.detail
    assert e2.value.status_code == 400
    async with orm.session() as db:
        cs = {c.id: c for c in (await db.execute(select(Channel))).scalars()}
    assert all(cs[i].status == ChannelStatus.pending for i in member_ids)


@pytest.mark.asyncio
async def test_approved_bundle_leftover_pending_members_hidden(orm):
    """Legacy: bundle approved before the cascade, members still pending —
    they must not reappear as 0-USDT lots (handled in code, no data migration)."""
    from app.models.bundle import BundleStatus, ChannelBundle

    admin, bid, member_ids, solo_id = await _seed(orm)
    async with orm.session() as db:
        b = (await db.execute(select(ChannelBundle).where(ChannelBundle.id == bid))).scalar_one()
        b.status = BundleStatus.approved
        await db.commit()
    adm = _admin_mod()
    async with orm.session() as db:
        chans = await adm.get_pending_channels(admin=admin, db=db)
    assert [c.id for c in chans] == [solo_id]
