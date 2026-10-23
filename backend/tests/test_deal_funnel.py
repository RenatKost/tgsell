"""Deal funnel: active-status reservation, bundle/channel cross-checks, FOR UPDATE,
refund restoration for bundles, configurable fee percent in messages."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.deal import ACTIVE_DEAL_STATUSES, DealStatus


def test_active_statuses_cover_all_non_terminal():
    terminal = {DealStatus.completed, DealStatus.cancelled}
    assert set(ACTIVE_DEAL_STATUSES) == set(DealStatus) - terminal


def test_create_deal_uses_row_locks():
    from app.routers import deals
    src = inspect.getsource(deals.create_deal)
    assert src.count("with_for_update") >= 3


def test_fee_percent_in_payout_message(monkeypatch):
    from app.config import settings
    from app.services import deal_checklist as cl
    monkeypatch.setattr(settings, "service_fee_percent", 5.0)
    msg = cl.payout_request_message(SimpleNamespace(amount_usdt=100, service_fee=5))
    assert "(5%)" in msg and "3%" not in msg


async def _seed(db, *, bundle=True):
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    s = User(first_name="S", telegram_id=990001, role=UserRole.user)
    b = User(first_name="B", telegram_id=990002, role=UserRole.user)
    db.add_all([s, b]); await db.flush()
    chs = [Channel(seller_id=s.id, telegram_link=f"https://t.me/fn{i}", channel_name=f"fn{i}",
                   category="x", price=10, status=ChannelStatus.approved) for i in range(2)]
    db.add_all(chs); await db.flush()
    bun = None
    if bundle:
        bun = ChannelBundle(seller_id=s.id, name="N", price=20, status=BundleStatus.approved)
        db.add(bun); await db.flush()
        db.add_all([BundleChannel(bundle_id=bun.id, channel_id=c.id, display_order=i) for i, c in enumerate(chs)])
    await db.commit()
    return s, b, chs, bun


def _deal(**kw):
    from app.models.deal import Deal
    base = dict(escrow_wallet_address="T" + "x" * 33, escrow_private_key_encrypted="enc",
                amount_usdt=10, service_fee=0.3)
    base.update(kw)
    return Deal(**base)


async def _create(db, user, **body):
    from app.routers.deals import create_deal
    from app.schemas.deal import DealCreate
    return await create_deal(DealCreate(**body), user=user, db=db)


@pytest.mark.asyncio
@pytest.mark.parametrize("st", [DealStatus.disputed, DealStatus.awaiting_payout, DealStatus.payout_in_progress])
async def test_channel_rejected_when_active_deal_in_late_status(pg_orm, st):
    async with pg_orm.session() as db:
        s, b, chs, _ = await _seed(db, bundle=False)
        db.add(_deal(channel_id=chs[0].id, buyer_id=b.id, seller_id=s.id, status=st)); await db.commit()
        with pytest.raises(HTTPException) as e:
            await _create(db, b, channel_id=chs[0].id)
        assert e.value.status_code == 400 and "active deal" in e.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("st", [DealStatus.disputed, DealStatus.payout_in_progress])
async def test_bundle_rejected_when_bundle_deal_in_late_status(pg_orm, st):
    async with pg_orm.session() as db:
        s, b, chs, bun = await _seed(db)
        db.add(_deal(bundle_id=bun.id, buyer_id=b.id, seller_id=s.id, status=st)); await db.commit()
        with pytest.raises(HTTPException) as e:
            await _create(db, b, bundle_id=bun.id)
        assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_bundle_rejected_when_channel_has_active_deal(pg_orm):
    async with pg_orm.session() as db:
        s, b, chs, bun = await _seed(db)
        db.add(_deal(channel_id=chs[1].id, buyer_id=b.id, seller_id=s.id, status=DealStatus.paid)); await db.commit()
        with pytest.raises(HTTPException) as e:
            await _create(db, b, bundle_id=bun.id)
        assert "channel of this bundle" in e.value.detail


@pytest.mark.asyncio
async def test_bundle_rejected_when_channel_not_approved(pg_orm):
    from app.models.channel import ChannelStatus
    async with pg_orm.session() as db:
        s, b, chs, bun = await _seed(db)
        chs[0].status = ChannelStatus.sold; await db.commit()
        with pytest.raises(HTTPException) as e:
            await _create(db, b, bundle_id=bun.id)
        assert e.value.detail == "Bundle is not available for purchase"


@pytest.mark.asyncio
async def test_channel_rejected_when_bundle_has_active_deal(pg_orm):
    async with pg_orm.session() as db:
        s, b, chs, bun = await _seed(db)
        db.add(_deal(bundle_id=bun.id, buyer_id=b.id, seller_id=s.id, status=DealStatus.created)); await db.commit()
        with pytest.raises(HTTPException) as e:
            await _create(db, b, channel_id=chs[0].id)
        assert "bundle with an active deal" in e.value.detail


@pytest.mark.asyncio
async def test_channel_ok_after_bundle_deal_cancelled_and_fee_msg(pg_orm, monkeypatch):
    from app.config import settings
    from app.models.deal import DealMessage
    from app.routers import deals
    monkeypatch.setattr(deals, "generate_escrow_wallet", lambda: ("T" + "y" * 33, "enc"))
    monkeypatch.setattr(settings, "service_fee_percent", 7.5)
    async with pg_orm.session() as db:
        s, b, chs, bun = await _seed(db)
        db.add(_deal(bundle_id=bun.id, buyer_id=b.id, seller_id=s.id, status=DealStatus.cancelled)); await db.commit()
        resp = await _create(db, b, channel_id=chs[0].id)
        msgs = (await db.execute(select(DealMessage.text).where(DealMessage.deal_id == resp.id))).scalars().all()
        joined = "\n".join(msgs)
        assert "7.5%" in joined and "3%" not in joined


@pytest.mark.asyncio
async def test_bundle_refund_restores_bundle_and_channels(pg_orm):
    from app.models.bundle import BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import TransactionType
    from app.services import payouts
    async with pg_orm.session() as db:
        s, b, chs, bun = await _seed(db)
        bun.status = BundleStatus.sold
        for c in chs:
            c.status = ChannelStatus.sold
        d = _deal(bundle_id=bun.id, buyer_id=b.id, seller_id=s.id, status=DealStatus.payout_in_progress)
        db.add(d); await db.commit()
        tx = SimpleNamespace(type=TransactionType.refund, status=None, receipt_status=None, finalized_at=None,
                             tx_hash="h" * 64, amount=20, to_address="T" + "z" * 33, amount_units=0)
        await payouts._finalize_success(db, d, tx)
        await db.commit()
        assert d.status == DealStatus.cancelled
        assert (await db.get(ChannelBundle, bun.id)).status == BundleStatus.approved
        for c in chs:
            assert (await db.get(Channel, c.id)).status == ChannelStatus.approved


def _mig47():
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0047_active_deal_unique.py"
    spec = importlib.util.spec_from_file_location("m0047", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m, p.read_text(encoding="utf-8")


def test_migration_0047_shape():
    m, src = _mig47()
    assert m.revision == "0047" and m.down_revision == "0046"
    assert set(m.ACTIVE) == {s.value for s in ACTIVE_DEAL_STATUSES}
    assert "DELETE" not in src.upper() and "UPDATE DEALS" not in src.upper()


@pytest.mark.asyncio
async def test_migration_0047_enforces_unique_on_postgres(pg_orm):
    from sqlalchemy.exc import IntegrityError
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    m, _ = _mig47()
    async with pg_orm.session() as db:
        s, b, chs, bun = await _seed(db)

    def run(conn, fn):
        with Operations.context(MigrationContext.configure(conn)):
            fn()
    async with pg_orm.engine.begin() as conn:
        await conn.run_sync(run, m.upgrade)
    try:
        async with pg_orm.session() as db:
            db.add(_deal(channel_id=chs[0].id, buyer_id=b.id, seller_id=s.id, status=DealStatus.disputed))
            db.add(_deal(channel_id=chs[0].id, buyer_id=b.id, seller_id=s.id, status=DealStatus.cancelled))
            await db.commit()
            db.add(_deal(channel_id=chs[0].id, buyer_id=b.id, seller_id=s.id, status=DealStatus.created,
                         escrow_wallet_address="T" + "q" * 33))
            with pytest.raises(IntegrityError):
                await db.commit()
    finally:
        async with pg_orm.engine.begin() as conn:
            await conn.run_sync(run, m.downgrade)
