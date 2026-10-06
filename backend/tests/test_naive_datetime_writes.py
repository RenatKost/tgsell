"""Regression: aware datetimes must never be written into naive DateTime columns.

Most columns are ``DateTime`` (TIMESTAMP WITHOUT TIME ZONE, naive UTC). asyncpg
raises ``DataError: can't subtract offset-naive and offset-aware datetimes`` when
an aware ``datetime`` is bound to such a column — this crashed the support bot
(``support_messages.handled_at``) and the view tracker (``ChannelPost.date`` cutoff).

DB backend / fixtures: see tests/db_harness.py (real Postgres when available).
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select, text as sa_text  # noqa: E402

from app.utils.timeutil import to_naive_utc, utcnow_naive  # noqa: E402
from tests.db_harness import (  # noqa: E402
    SUPPORT_SECRET,
    _FakeBot,
    _assert_naive_recent,
    _fake_message,
    _strict_errors,
)


# ── Helpers (pure) ─────────────────────────────────────────────────────

def test_utcnow_naive_is_naive_utc():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    value = utcnow_naive()
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert value.tzinfo is None
    assert before <= value <= after


def test_to_naive_utc():
    assert to_naive_utc(None) is None
    naive = datetime(2026, 10, 6, 12, 0, 0)
    assert to_naive_utc(naive) is naive
    kyiv = timezone(timedelta(hours=3))
    aware = datetime(2026, 10, 6, 15, 0, 0, tzinfo=kyiv)
    out = to_naive_utc(aware)
    assert out.tzinfo is None
    assert out == datetime(2026, 10, 6, 12, 0, 0)

@pytest.mark.asyncio
async def test_backend_rejects_aware_datetime_in_naive_column(orm):
    """Sanity: the test DB is as strict as production asyncpg (else the cycle test proves nothing)."""
    from app.models.support import SupportMessage

    async with orm.session() as db:
        db.add(SupportMessage(
            telegram_user_id=1, chat_id=1, direction="in", text="x",
            handled=True, handled_at=datetime.now(timezone.utc),
        ))
        with pytest.raises(_strict_errors()):
            await db.commit()

@pytest.mark.asyncio
async def test_support_full_cycle_incoming_reply_handled(orm, monkeypatch):
    import aiogram
    import httpx
    from fastapi import FastAPI

    from app.config import settings
    from app.models.support import SupportMessage

    bot_support = importlib.import_module("bot.support")
    support_router = importlib.import_module("app.routers.support")

    monkeypatch.setattr(settings, "support_queue_secret", SUPPORT_SECRET)
    monkeypatch.setattr(settings, "bot_token_support", "123:TEST")
    monkeypatch.setattr(aiogram, "Bot", _FakeBot)
    _FakeBot.sent = []
    bot_support._last_urgent_alert.clear()

    user_id, chat_id = 777001, 777001

    # 1) Incoming DM → stored as 'in' + auto-reply stored as 'out' (handled=True → handled_at written)
    msg = _fake_message(user_id, chat_id, "як додати канал?")
    await bot_support.support_private_message(msg)
    msg.answer.assert_awaited_once()

    async with orm.session() as db:
        rows = (await db.execute(
            select(SupportMessage).where(SupportMessage.telegram_user_id == user_id)
            .order_by(SupportMessage.id)
        )).scalars().all()
    assert [r.direction for r in rows] == ["in", "out"]
    incoming, auto_reply = rows
    assert incoming.handled is False and incoming.handled_at is None
    assert auto_reply.handled is True
    _assert_naive_recent(auto_reply.handled_at)

    app = FastAPI()
    app.include_router(support_router.router, prefix="/api")
    app.dependency_overrides[support_router.get_db] = orm.get_db
    headers = {"x-support-secret": SUPPORT_SECRET}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # auth is enforced
        r = await client.get("/api/support/queue", headers={"x-support-secret": "wrong"})
        assert r.status_code == 401

        r = await client.get("/api/support/queue", headers=headers)
        assert r.status_code == 200
        assert [m["id"] for m in r.json()["messages"]] == [incoming.id]

        # 2) Admin reply
        r = await client.post(
            "/api/support/reply",
            headers=headers,
            json={"telegram_user_id": user_id, "text": "Відповідь підтримки", "reply_to_id": incoming.id},
        )
        assert r.status_code == 200, r.text
        out = r.json()["message"]
        assert out["direction"] == "out" and out["handled"] is True
        assert out["handled_at"] is not None
        assert _FakeBot.sent == [(chat_id, "Відповідь підтримки")]

        # 3) Another incoming message, then explicit /handled
        await bot_support.support_private_message(_fake_message(user_id, chat_id, "ще питання"))
        async with orm.session() as db:
            second_in = (await db.execute(
                select(SupportMessage).where(
                    SupportMessage.telegram_user_id == user_id,
                    SupportMessage.direction == "in",
                    SupportMessage.handled.is_(False),
                )
            )).scalar_one()

        r = await client.post("/api/support/handled", headers=headers, json={"ids": [second_in.id]})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "updated": 1}

        r = await client.get("/api/support/queue", headers=headers)
        assert r.status_code == 200
        assert r.json()["messages"] == []

    async with orm.session() as db:
        rows = (await db.execute(
            select(SupportMessage).where(SupportMessage.telegram_user_id == user_id)
        )).scalars().all()
    assert rows and all(r.handled for r in rows)
    for r in rows:
        _assert_naive_recent(r.handled_at)

    if orm.kind == "postgres":
        async with orm.engine.connect() as conn:
            col_type = (await conn.execute(sa_text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='support_messages' AND column_name='handled_at'"
            ))).scalar_one()
        assert col_type == "timestamp without time zone"


# ── View tracker: naive cutoff for ChannelPost.date ─────────────────────

@pytest.mark.asyncio
async def test_update_post_views_once_uses_naive_cutoff(orm, monkeypatch):
    from app.models.channel import Channel, ChannelPost, ChannelStatus
    from app.models.user import User
    cs = importlib.import_module("app.services.channel_stats")

    stats_collector = importlib.import_module("app.tasks.stats_collector")

    post_date = utcnow_naive() - timedelta(hours=13)
    async with orm.session() as db:
        user = User(first_name="Seller")
        db.add(user)
        await db.flush()
        channel = Channel(
            seller_id=user.id, telegram_link="https://t.me/test_channel", channel_name="Test",
            category="news", price=10.0, status=ChannelStatus.approved, is_closed=False,
        )
        db.add(channel)
        await db.flush()
        db.add(ChannelPost(channel_id=channel.id, telegram_msg_id=101, date=post_date, views=10))
        await db.commit()
        channel_id = channel.id

    fake_client = SimpleNamespace(
        get_entity=AsyncMock(return_value=SimpleNamespace(id=1)),
        get_messages=AsyncMock(return_value=[
            SimpleNamespace(id=101, views=555, forwards=7, reactions=None),
        ]),
    )
    monkeypatch.setattr(cs, "_get_telethon_client", AsyncMock(return_value=fake_client))
    monkeypatch.setattr(stats_collector.asyncio, "sleep", AsyncMock())

    await stats_collector.update_post_views_once()

    fake_client.get_messages.assert_awaited_once()
    async with orm.session() as db:
        post = (await db.execute(
            select(ChannelPost).where(ChannelPost.channel_id == channel_id)
        )).scalar_one()
    assert post.views == 555
    assert post.forwards == 7
    assert post.views_1h == 555 and post.views_12h == 555
    assert post.views_24h is None


# ── AI analysis cache: ai_cache_updated_at (naive) ─────────────────────

async def _seed_channel(orm, **overrides):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User

    async with orm.session() as db:
        user = User(first_name="Seller")
        db.add(user)
        await db.flush()
        fields = dict(
            seller_id=user.id, telegram_link="https://t.me/test_channel", channel_name="Test",
            category="news", price=10.0, status=ChannelStatus.approved, is_closed=False,
        )
        fields.update(overrides)
        channel = Channel(**fields)
        db.add(channel)
        await db.commit()
        return user.id, channel.id


@pytest.mark.asyncio
async def test_channel_ai_analysis_cache_is_saved_and_reused(orm, monkeypatch):
    from app.models.channel import Channel
    ai_analysis = importlib.import_module("app.services.ai_analysis")

    channels_router = importlib.import_module("app.routers.channels")
    _, channel_id = await _seed_channel(orm)

    analysis = {"score": 7, "summary": "ok"}
    fake_analyze = AsyncMock(return_value=analysis)
    monkeypatch.setattr(ai_analysis, "analyze_channel", fake_analyze)

    async with orm.session() as db:
        assert await channels_router.get_ai_analysis(channel_id, db) == analysis

    async with orm.session() as db:
        channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one()
    # Cache write is wrapped in try/except (warning + rollback), so check it really landed.
    assert channel.ai_cache is not None, "AI cache was not saved (aware datetime rejected?)"
    _assert_naive_recent(channel.ai_cache_updated_at)

    # Second call within TTL → served from cache, no new AI call
    async with orm.session() as db:
        assert await channels_router.get_ai_analysis(channel_id, db) == analysis
    assert fake_analyze.await_count == 1


@pytest.mark.asyncio
async def test_channel_ai_analysis_stale_cache_is_refreshed(orm, monkeypatch):
    from app.models.channel import Channel
    ai_analysis = importlib.import_module("app.services.ai_analysis")

    channels_router = importlib.import_module("app.routers.channels")
    stale_at = utcnow_naive() - timedelta(days=8)
    _, channel_id = await _seed_channel(
        orm, ai_cache=json.dumps({"old": True}), ai_cache_updated_at=stale_at,
    )
    fresh = {"old": False}
    monkeypatch.setattr(ai_analysis, "analyze_channel", AsyncMock(return_value=fresh))

    async with orm.session() as db:
        assert await channels_router.get_ai_analysis(channel_id, db) == fresh

    async with orm.session() as db:
        channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one()
    assert json.loads(channel.ai_cache) == fresh
    _assert_naive_recent(channel.ai_cache_updated_at)


@pytest.mark.asyncio
async def test_bundle_ai_analysis_cache_is_saved_and_reused(orm, monkeypatch):
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle

    bundles_router = importlib.import_module("app.routers.bundles")
    user_id, channel_id = await _seed_channel(orm, subscribers_count=100, er=5.0)

    async with orm.session() as db:
        bundle = ChannelBundle(
            seller_id=user_id, name="Bundle", price=100.0, status=BundleStatus.approved,
        )
        db.add(bundle)
        await db.flush()
        db.add(BundleChannel(bundle_id=bundle.id, channel_id=channel_id, display_order=0))
        await db.commit()
        bundle_id = bundle.id

    analysis = {"score": 8, "summary": "bundle ok"}
    fake_analyze = AsyncMock(return_value=analysis)
    monkeypatch.setattr(bundles_router, "analyze_bundle", fake_analyze)

    async with orm.session() as db:
        assert await bundles_router.get_bundle_ai_analysis(bundle_id, db) == analysis
    fake_analyze.assert_awaited_once()

    async with orm.session() as db:
        bundle = (await db.execute(
            select(ChannelBundle).where(ChannelBundle.id == bundle_id)
        )).scalar_one()
    assert bundle.ai_cache is not None, "AI cache was not saved (aware datetime rejected?)"
    _assert_naive_recent(bundle.ai_cache_updated_at)

    async with orm.session() as db:
        assert await bundles_router.get_bundle_ai_analysis(bundle_id, db) == analysis
    assert fake_analyze.await_count == 1
