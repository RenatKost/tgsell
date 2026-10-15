"""Task 22: channel quality index."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.quality import score_channel

NOW = datetime(2026, 10, 15, 12, 0)


def _posts(n=20, views=3000, every=1):
    return [(NOW - timedelta(days=i * every, hours=1), views) for i in range(n)]


def test_good_channel_scores_high_with_breakdown():
    r = score_channel(subscribers=10000, posts=_posts(), snapshots=[(NOW - timedelta(days=30), 9500), (NOW, 10000)],
                      growth_30d=500, now=NOW)
    assert r["health"] == "clean" and r["score"] >= 80
    comps = r["breakdown"]["components"]
    assert set(comps) == {"er", "regularity", "growth", "integrity"}
    assert comps["er"]["value"] == 30.0 and comps["integrity"]["inflated"] is False


def test_too_little_data_is_null_not_invented():
    r = score_channel(subscribers=10000, posts=_posts(n=2), snapshots=[], now=NOW)
    assert r["score"] is None and r["health"] == "insufficient"
    assert "few_posts_30d" in r["breakdown"]["reasons"]
    assert score_channel(subscribers=0, posts=_posts(), snapshots=[], now=NOW)["score"] is None
    assert score_channel(subscribers=1000, views_hidden=True, posts=_posts(), snapshots=[], now=NOW)["score"] is None
    # old posts (outside 30 days) do not count
    old = [(NOW - timedelta(days=40 + i), 500) for i in range(10)]
    assert score_channel(subscribers=1000, posts=old, snapshots=[], now=NOW)["score"] is None


def test_missing_growth_is_rescaled_not_zeroed():
    r = score_channel(subscribers=10000, posts=_posts(), snapshots=[], now=NOW)
    assert r["score"] is not None and "growth" in r["breakdown"]["missing"]
    assert "integrity" in r["breakdown"]["components"]  # from views ratio


def test_inflated_low_views_capped():
    # prod #81-like: 10464 subs, 32 views
    r = score_channel(subscribers=10464, posts=_posts(views=32), snapshots=[], now=NOW)
    assert r["health"] == "suspicious" and r["score"] <= 25
    assert r["breakdown"]["components"]["integrity"]["inflated"] is True


def test_views_above_150pct_inflated_but_149_not():
    hi = score_channel(subscribers=1000, posts=_posts(views=1510), snapshots=[], now=NOW)
    ok = score_channel(subscribers=1000, posts=_posts(views=1490), snapshots=[], now=NOW)
    assert hi["health"] == "suspicious" and ok["health"] == "clean"


def test_sharp_subscriber_jump_penalised():
    snaps = [(NOW - timedelta(days=2), 5000), (NOW - timedelta(days=1), 9000), (NOW, 9050)]
    r = score_channel(subscribers=9050, posts=_posts(views=2000), snapshots=snaps, now=NOW)
    assert r["health"] == "suspicious" and r["breakdown"]["components"]["integrity"]["jumps"] == 1
    smooth = [(NOW - timedelta(days=2), 9000), (NOW - timedelta(days=1), 9020), (NOW, 9050)]
    assert score_channel(subscribers=9050, posts=_posts(views=2000), snapshots=smooth, now=NOW)["health"] == "clean"


def test_irregular_posting_scores_lower():
    reg = score_channel(subscribers=10000, posts=_posts(n=15, every=2), snapshots=[], now=NOW)
    burst = [(NOW - timedelta(days=d, hours=h), 3000) for d in (0, 25) for h in range(8)]
    irr = score_channel(subscribers=10000, posts=burst, snapshots=[], now=NOW)
    assert irr["breakdown"]["components"]["regularity"]["points"] < reg["breakdown"]["components"]["regularity"]["points"]


@pytest.mark.asyncio
async def test_compute_store_history_and_api(pg_orm, monkeypatch):
    from fastapi import FastAPI
    from sqlalchemy import select

    from app.models.channel import Channel, ChannelPost, ChannelQualityHistory, ChannelStats, ChannelStatus
    from app.models.user import User
    from app.services import quality

    now = datetime.utcnow()
    async with pg_orm.session() as db:
        u = User(first_name="S", telegram_id=4242)
        db.add(u)
        await db.commit()

        def ch(name, price, subs, views):
            return Channel(seller_id=u.id, telegram_link=f"https://t.me/{name}", channel_name=name,
                           category="Новини/ЗМІ", price=price, subscribers_count=subs, avg_views=views,
                           last_post_date=now - timedelta(days=1), status=ChannelStatus.approved)

        good, infl, empty = ch("good", 1000, 10000, 3000), ch("infl", 100, 10000, 30), ch("empty", 500, 10000, 2000)
        db.add_all([good, infl, empty])
        await db.commit()
        for c, v in ((good, 3000), (infl, 30)):
            for i in range(10):
                db.add(ChannelPost(channel_id=c.id, telegram_msg_id=i + 1, date=now - timedelta(days=i, hours=1), views=v))
        db.add(ChannelStats(channel_id=good.id, date=now.replace(hour=0, minute=0, second=0, microsecond=0),
                            subscribers=10000, avg_views=3000, avg_reach=3000))
        await db.commit()
        ids = {"good": good.id, "infl": infl.id, "empty": empty.id}

    monkeypatch.setattr(importlib.import_module("app.database"), "async_session", pg_orm.session)
    assert await quality.recompute_due() == 3
    assert await quality.recompute_due() == 0  # <= every 6 hours
    assert await quality.recompute_due(now=datetime.utcnow() + timedelta(hours=7)) == 3

    async with pg_orm.session() as db:
        hist = (await db.execute(select(ChannelQualityHistory).where(
            ChannelQualityHistory.channel_id == ids["good"]))).scalars().all()
        assert len(hist) == 2 and hist[0].score is not None and hist[0].breakdown["components"]

    router_mod = importlib.import_module("app.routers.channels")
    db_mod = importlib.import_module("app.database")
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
        r = (await cl.get("/channels", params={"sort": "quality_desc"})).json()
        items = r["items"]
        assert [i["channel_name"] for i in items] == ["good", "infl", "empty"]
        assert items[2]["quality_score"] is None and items[2]["quality_health"] == "insufficient"
        r = (await cl.get("/channels", params={"no_inflation": "true"})).json()
        assert [i["channel_name"] for i in r["items"]] == ["good"]
        r = (await cl.get("/channels", params={"sort": "ppv_asc"})).json()
        # ppv: infl 100/30=3.3, good 1000/3000=0.33, empty 500/2000=0.25
        assert [i["channel_name"] for i in r["items"]] == ["empty", "good", "infl"]
        d = (await cl.get(f"/channels/{ids['good']}")).json()
        assert d["quality_score"] >= 70 and d["quality_breakdown"]["components"]["er"]["points"] > 0


def test_pricing_inflated_verdict_is_authoritative():
    # prod #81: posts look fine but the Task 21 verdict (avg_views 32 / 10464) is inflated
    r = score_channel(subscribers=10464, posts=_posts(views=2500), snapshots=[], now=NOW, price_verdict="inflated")
    assert r["health"] == "suspicious" and r["score"] <= 25
    r = score_channel(subscribers=10464, posts=_posts(views=2500), snapshots=[], now=NOW, price_verdict="unknown")
    assert r["health"] == "clean"
    # inflated + too little data -> still null, but flagged
    r = score_channel(subscribers=10464, posts=_posts(n=1), snapshots=[], now=NOW, price_verdict="inflated")
    assert r["score"] is None and r["health"] == "suspicious"
