"""Task 15 item 2: view tracker must not hit greenlet_spawn after one channel fails."""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.utils.timeutil import utcnow_naive


@pytest.mark.asyncio
async def test_view_tracker_survives_failing_channel(pg_orm, monkeypatch, caplog):
    from app.models.channel import Channel, ChannelPost, ChannelStatus
    from app.models.user import User

    sc = importlib.import_module("app.tasks.stats_collector")
    cs = importlib.import_module("app.services.channel_stats")
    monkeypatch.setattr(sc, "async_session", pg_orm.session)
    monkeypatch.setattr(sc.asyncio, "sleep", AsyncMock())

    async with pg_orm.session() as db:
        seller = User(first_name="S", telegram_id=42)
        db.add(seller)
        await db.commit()
        chans = []
        for name in ("bad", "good1", "good2"):
            c = Channel(seller_id=seller.id, telegram_link=f"https://t.me/{name}", channel_name=name,
                        category="news", price=10.0, status=ChannelStatus.approved)
            db.add(c)
            chans.append(c)
        await db.commit()
        for c in chans:
            db.add(ChannelPost(channel_id=c.id, telegram_msg_id=100, date=utcnow_naive() - timedelta(hours=30),
                               views=1, forwards=0, reactions=0, comments=0))
        await db.commit()
        ids = [c.id for c in chans]

    class Client:
        async def get_entity(self, username):
            if username == "bad":
                raise ValueError("No user has \"bad\" as username")
            return username

        async def get_messages(self, entity, ids):
            return [SimpleNamespace(id=i, views=500, forwards=3, reactions=None) for i in ids]

    monkeypatch.setattr(cs, "_get_telethon_client", AsyncMock(return_value=Client()))

    caplog.set_level("ERROR")
    await sc.update_post_views_once()

    assert "greenlet" not in caplog.text
    from sqlalchemy import select
    async with pg_orm.session() as db:
        posts = {p.channel_id: p for p in (await db.execute(select(ChannelPost))).scalars().all()}
    assert posts[ids[0]].views == 1
    for cid in ids[1:]:
        assert posts[cid].views == 500 and posts[cid].views_24h == 500 and posts[cid].views_1h == 500
