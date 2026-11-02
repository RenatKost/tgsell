"""Promo Top always has an end date; backfill migration 0060; Top expires by top_until."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest

import app.models  # noqa: F401  (register all mappers)
from sqlalchemy import text


def test_on_first_approval_sets_top_until(monkeypatch):
    from app.config import settings
    from types import SimpleNamespace
    from app.services.promo_top import on_first_approval
    monkeypatch.setattr(settings, "promo_top_until", "2026-11-01T23:59:00")
    monkeypatch.setattr(settings, "promo_top_days", 7)
    now = datetime(2026, 11, 1, 12, 0)
    ch = SimpleNamespace(id=1, first_approved_at=None, top_until=None, top_source=None)
    assert on_first_approval(ch, now) is True
    assert ch.top_source == "promo" and ch.top_until == now + timedelta(days=7)


def test_is_top_expires():
    from types import SimpleNamespace
    from app.models.channel import Channel
    is_top = Channel.is_top.fget
    assert is_top(SimpleNamespace(top_until=datetime.utcnow() - timedelta(minutes=1))) is False
    assert is_top(SimpleNamespace(top_until=None)) is False
    assert is_top(SimpleNamespace(top_until=datetime.utcnow() + timedelta(days=1))) is True


def test_schema_exposes_top_until():
    from app.schemas.channel import ChannelResponse
    assert "top_until" in ChannelResponse.model_fields


@pytest.mark.asyncio
async def test_backfill_migration_sql(pg_orm):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "m0060", pathlib.Path(__file__).parents[1] / "alembic/versions/0060_backfill_top_until.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    appr = datetime(2026, 11, 1, 14, 31)
    keep = datetime(2026, 12, 1)
    async with pg_orm.session() as db:
        u = User(telegram_id=990101, username="tu", first_name="T")
        db.add(u)
        await db.flush()
        a = Channel(seller_id=u.id, channel_name="a", telegram_link="https://t.me/a1", category="c",
                    subscribers_count=1, price=1, status=ChannelStatus.approved, top_source="promo",
                    first_approved_at=appr)
        b = Channel(seller_id=u.id, channel_name="b", telegram_link="https://t.me/b1", category="c",
                    subscribers_count=1, price=1, status=ChannelStatus.approved, top_source="paid", top_until=keep)
        c = Channel(seller_id=u.id, channel_name="c", telegram_link="https://t.me/c1", category="c",
                    subscribers_count=1, price=1, status=ChannelStatus.approved)
        db.add_all([a, b, c])
        await db.commit()
        ids = (a.id, b.id, c.id)
    for _ in range(2):  # idempotent
        async with pg_orm.session() as db:
            await db.execute(text(mig.SQL))
            await db.commit()
    async with pg_orm.session() as db:
        ra, rb, rc = [await db.get(Channel, i) for i in ids]
        assert ra.top_until == appr + timedelta(days=7)
        assert rb.top_until == keep
        assert rc.top_until is None
