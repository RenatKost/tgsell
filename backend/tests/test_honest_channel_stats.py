"""Task 20: honest channel-stats time series."""
from __future__ import annotations

import importlib
import importlib.util
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text

from app.utils.timeutil import utcnow_naive

BACKEND = __import__("pathlib").Path(__file__).resolve().parents[1]


def _today():
    n = utcnow_naive()
    return datetime(n.year, n.month, n.day)


def _d(days_ago: int) -> str:
    return (_today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _stats(subs=1000, avg_views=300, er=30.0, days=(0, 1, 2, 5, 10), views=100):
    return {
        "subscribers_count": subs,
        "avg_views": avg_views,
        "er": er,
        "daily_stats": [
            {"date": _d(i), "avg_views": views + i, "subscribers": None, "er": None, "post_count": 2,
             "avg_forwards": 1, "avg_reactions": 3}
            for i in days
        ],
    }


async def _mk_channel(db, name="c1"):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User

    u = User(first_name="S", telegram_id=hash(name) % 10**9)
    db.add(u)
    await db.commit()
    c = Channel(seller_id=u.id, telegram_link=f"https://t.me/{name}", channel_name=name,
                category="news", price=10.0, status=ChannelStatus.approved)
    db.add(c)
    await db.commit()
    return c.id


async def _rows(db, cid):
    from app.models.channel import ChannelStats

    res = await db.execute(select(ChannelStats).where(ChannelStats.channel_id == cid).order_by(ChannelStats.date))
    return res.scalars().all()


@pytest.mark.asyncio
async def test_retro_points_have_no_subscribers_and_today_is_real(pg_orm):
    from app.services.stats_history import save_stats_history

    async with pg_orm.session() as db:
        cid = await _mk_channel(db)
        await save_stats_history(db, cid, _stats())
        await db.commit()
        rows = await _rows(db, cid)
    assert len(rows) == 5
    past = [r for r in rows if r.date < _today()]
    assert all(r.subscribers is None and r.er is None for r in past)
    assert all(r.date.hour == 0 and r.date.minute == 0 for r in rows)
    today = rows[-1]
    assert today.date == _today() and today.subscribers == 1000 and today.avg_views == 300 and today.er == 30.0
    assert today.post_count == 2


@pytest.mark.asyncio
async def test_rerun_upserts_today_and_refreshes_only_last_3_days(pg_orm):
    from app.services.stats_history import save_stats_history

    async with pg_orm.session() as db:
        cid = await _mk_channel(db)
        await save_stats_history(db, cid, _stats(views=100))
        await db.commit()
        await save_stats_history(db, cid, _stats(subs=1100, avg_views=350, er=31.0, views=500))
        await db.commit()
        rows = {r.date: r for r in await _rows(db, cid)}
    assert len(rows) == 5  # no duplicates
    t = _today()
    assert rows[t].subscribers == 1100 and rows[t].avg_views == 350
    assert rows[t - timedelta(days=1)].avg_views == 501  # refreshed
    assert rows[t - timedelta(days=2)].avg_views == 502  # refreshed
    assert rows[t - timedelta(days=5)].avg_views == 105  # old: untouched
    assert rows[t - timedelta(days=10)].avg_views == 110


@pytest.mark.asyncio
async def test_retro_point_never_wipes_a_real_snapshot(pg_orm):
    from app.models.channel import ChannelStats
    from app.services.stats_history import save_stats_history

    async with pg_orm.session() as db:
        cid = await _mk_channel(db)
        db.add(ChannelStats(channel_id=cid, date=_today() - timedelta(days=1), subscribers=990,
                            avg_views=10, avg_reach=10, er=1.0))
        await db.commit()
        await save_stats_history(db, cid, _stats())
        await db.commit()
        rows = {r.date: r for r in await _rows(db, cid)}
    y = rows[_today() - timedelta(days=1)]
    assert y.subscribers == 990 and y.er == 1.0 and y.avg_views == 101


@pytest.mark.asyncio
async def test_failed_subscribers_read_keeps_known_value(pg_orm):
    from app.services.stats_history import save_stats_history

    async with pg_orm.session() as db:
        cid = await _mk_channel(db)
        await save_stats_history(db, cid, _stats(subs=1000))
        await db.commit()
        await save_stats_history(db, cid, _stats(subs=0, er=0.0))
        await db.commit()
        rows = await _rows(db, cid)
    assert rows[-1].subscribers == 1000


@pytest.mark.asyncio
async def test_growth_is_null_without_enough_data(pg_orm):
    from app.models.channel import ChannelStats
    from app.services.stats_history import compute_growth

    async with pg_orm.session() as db:
        cid = await _mk_channel(db)
        assert await compute_growth(db, cid) == {"daily_growth": None, "growth_7d": None, "growth_30d": None}
        t = _today()
        db.add(ChannelStats(channel_id=cid, date=t, subscribers=1000, avg_views=0, avg_reach=0))
        db.add(ChannelStats(channel_id=cid, date=t - timedelta(days=1), subscribers=990, avg_views=0, avg_reach=0))
        # retro point with NULL subs must be ignored
        db.add(ChannelStats(channel_id=cid, date=t - timedelta(days=7), subscribers=None, avg_views=5, avg_reach=5))
        await db.commit()
        g = await compute_growth(db, cid)
        assert g == {"daily_growth": 10, "growth_7d": None, "growth_30d": None}

        db.add(ChannelStats(channel_id=cid, date=t - timedelta(days=8), subscribers=900, avg_views=0, avg_reach=0))
        db.add(ChannelStats(channel_id=cid, date=t - timedelta(days=31), subscribers=1010, avg_views=0, avg_reach=0))
        await db.commit()
        g = await compute_growth(db, cid)
        assert g == {"daily_growth": 10, "growth_7d": 100, "growth_30d": -10}


@pytest.mark.asyncio
async def test_collector_writes_snapshot_and_growth_without_greenlet(pg_orm, monkeypatch, caplog):
    from app.models.channel import Channel, ChannelStats

    sc = importlib.import_module("app.tasks.stats_collector")
    monkeypatch.setattr(sc, "async_session", pg_orm.session)
    monkeypatch.setattr(sc.asyncio, "sleep", AsyncMock())
    import app.services.alerts as alerts
    monkeypatch.setattr(alerts, "alert_stats_summary", AsyncMock())

    async with pg_orm.session() as db:
        cid = await _mk_channel(db, "good")
        bad = await _mk_channel(db, "bad")
        db.add(ChannelStats(channel_id=cid, date=_today() - timedelta(days=1), subscribers=950,
                            avg_views=1, avg_reach=1, er=1.0))
        await db.commit()

    async def fake_collect(link):
        if link.endswith("bad"):
            raise RuntimeError("boom")
        return _stats(subs=1000)

    monkeypatch.setattr(sc, "collect_channel_stats", fake_collect)
    caplog.set_level("ERROR")
    await sc.collect_stats_once()
    await sc.collect_stats_once()  # second run: upsert, no duplicates
    assert "greenlet" not in caplog.text

    async with pg_orm.session() as db:
        rows = await _rows(db, cid)
        ch = await db.get(Channel, cid)
        assert not await _rows(db, bad)
    assert len(rows) == 5
    assert rows[-1].subscribers == 1000
    assert ch.subscribers_count == 1000
    assert ch.daily_growth == 50 and ch.growth_7d is None and ch.growth_30d is None


@pytest.mark.asyncio
async def test_migration_dedupes_normalizes_and_clears_fake_subscribers(pg_orm):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    async with pg_orm.session() as db:
        cid = await _mk_channel(db)
        cid2 = await _mk_channel(db, "c2")

    t = _today()
    async with pg_orm.engine.begin() as conn:
        await conn.execute(text("ALTER TABLE channel_stats DROP CONSTRAINT uq_channel_stats_channel_date"))
        await conn.execute(text("ALTER TABLE channels DROP COLUMN growth_7d, DROP COLUMN growth_30d"))
        rows = [
            # channel 1: fake retro subs (current value written into past)
            (cid, t - timedelta(days=3), 500), (cid, t - timedelta(days=2), 500),
            (cid, t - timedelta(days=1, hours=-5), 500),  # dup of day-1 (older recorded)
            (cid, t - timedelta(days=1), 500),
            (cid, t + timedelta(hours=7), 500),  # latest real, non-midnight
            (cid2, t - timedelta(days=4), 0),
        ]
        for i, (c, d, s) in enumerate(rows):
            await conn.execute(text(
                "INSERT INTO channel_stats (channel_id, date, subscribers, avg_views, avg_reach, er, recorded_at)"
                " VALUES (:c, :d, :s, 1, 1, 5.0, :r)"), {"c": c, "d": d, "s": s, "r": t + timedelta(minutes=i)})

        spec = importlib.util.spec_from_file_location(
            "mig0038", BACKEND / "alembic" / "versions" / "0038_honest_channel_stats.py")
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)

        def run(sync_conn):
            with Operations.context(MigrationContext.configure(sync_conn)):
                mig.upgrade()

        await conn.run_sync(run)

    async with pg_orm.session() as db:
        r1 = await _rows(db, cid)
        r2 = await _rows(db, cid2)
    assert [r.date for r in r1] == [t - timedelta(days=3), t - timedelta(days=2), t - timedelta(days=1), t]
    assert [r.subscribers for r in r1] == [None, None, None, 500]
    assert [r.er for r in r1] == [None, None, None, 5.0]
    assert r2[0].subscribers is None
