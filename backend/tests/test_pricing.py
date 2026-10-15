"""Task 21 v2: price estimate vs. market baseline (market_prices.json)."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.pricing import Sample, build_market, estimate, load_baseline

NOW = datetime(2026, 10, 15, 12, 0)
FRESH = NOW - timedelta(days=1)


def _est(m, **kw):
    base = dict(category="Новини/ЗМІ", price=1000.0, subscribers=10000, avg_views=1500, is_closed=False,
                last_post_date=FRESH, now=NOW)
    base.update(kw)
    return estimate(m, **base)


def test_baseline_file_and_fallback():
    b = load_baseline()
    assert b["overall"] == {"pps": 0.096, "ppv": 0.62, "n": 152}
    assert b["segments"]["news"]["pps"] == 0.105 and b["segments"]["jobs"]["ppv"] == 2.0
    m = build_market()
    ref, scope = m.ref_for("Новини/ЗМІ")
    assert scope == "category" and ref.pps == 0.105
    ref, scope = m.ref_for("Криптовалюта")
    assert scope == "overall" and ref.pps == 0.096


def test_median_of_two_estimates_and_verdicts():
    m = build_market()
    # news: 10000*0.105=1050, 1500*0.66=990 -> median 1020
    r = _est(m, price=1000)
    assert r["price_verdict"] == "fair" and r["fair_price_range"] == [765.0, 1275.0]
    assert _est(m, price=700)["price_verdict"] == "cheaper"
    assert _est(m, price=1500)["price_verdict"] == "expensive"


def test_case_85_far_below_market_is_unknown_without_numbers():
    # prod #85: «Інше», price 100, 8244 subs, 1974 views (was fair 21878–36464)
    m = build_market()
    r = _est(m, category="Інше", price=100, subscribers=8244, avg_views=1974)
    assert r["price_verdict"] == "unknown" and r["fair_price_range"] is None


def test_case_84_news_far_below_market_is_unknown():
    m = build_market()
    r = _est(m, price=150, subscribers=14475, avg_views=2682)
    assert r["price_verdict"] == "unknown" and r["fair_price_range"] is None


def test_case_81_inflated_subscribers():
    # prod #81: 10464 subs, 32 views -> 0.3% views/subs, was flagged "cheaper"
    m = build_market()
    r = _est(m, category="Криптовалюта", price=100, subscribers=10464, avg_views=32)
    assert r["price_verdict"] == "inflated" and r["fair_price_range"] is None


def test_views_above_subs_is_inflated():
    m = build_market()
    assert _est(m, subscribers=500, avg_views=1200, price=100)["price_verdict"] == "inflated"


def test_stale_views_ignored():
    m = build_market()
    r = _est(m, price=1000, avg_views=32, last_post_date=NOW - timedelta(days=90))
    assert r["price_per_view"] is None and r["price_verdict"] == "fair"  # subs-only 1050
    r = _est(m, price=1000, avg_views=32, views_hidden=True)
    assert r["price_verdict"] == "fair"


def test_unmapped_category_badge_only():
    m = build_market()
    # overall: 10000*0.096=960, 1500*0.62=930 -> 945
    r = _est(m, category="Криптовалюта", price=945)
    assert r["price_verdict"] == "fair" and r["fair_price_range"] is None
    assert r["price_reference_scope"] == "overall"


def test_unknown_cases():
    m = build_market()
    for kw in (dict(is_closed=True), dict(subscribers=0), dict(price=0), dict(subscribers=None)):
        r = _est(m, **kw)
        assert r["price_verdict"] == "unknown" and r["fair_price_range"] is None


def test_deals_hook_weighted():
    deals = [Sample("Новини/ЗМІ", 2000, 10000, 1500)] * 2
    assert build_market(deals=deals).ref_for("Новини/ЗМІ")[0].pps == 0.105  # below MIN_DEALS
    deals = [Sample("Новини/ЗМІ", 2000, 10000, 1500)] * 8  # 8*5=40 weight vs n=37
    ref = build_market(deals=deals).ref_for("Новини/ЗМІ")[0]
    assert ref.pps == pytest.approx(0.2) and ref.samples == 45


@pytest.mark.asyncio
async def test_api_fields_sort_filter_and_deals(pg_orm):
    from fastapi import FastAPI

    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus
    from app.models.user import User

    router_mod = importlib.import_module("app.routers.channels")
    db_mod = importlib.import_module("app.database")
    async with pg_orm.session() as db:
        u = User(first_name="S", telegram_id=77)
        db.add(u)
        await db.commit()

        def ch(name, price, subs, views, **kw):
            return Channel(seller_id=u.id, telegram_link=f"https://t.me/{name}", channel_name=name,
                           category="Новини/ЗМІ", price=price, subscribers_count=subs, avg_views=views,
                           last_post_date=datetime.utcnow() - timedelta(days=1),
                           status=kw.pop("status", ChannelStatus.approved), **kw)

        chans = [ch("a", 700, 10000, 1500), ch("b", 1000, 10000, 1500), ch("c", 2000, 10000, 1500),
                 ch("closed", 50, 0, 0, is_closed=True), ch("zero", 0, 1000, 100),
                 ch("sold", 300, 10000, 1500, status=ChannelStatus.sold)]
        db.add_all(chans)
        await db.commit()
        db.add(Deal(channel_id=chans[-1].id, buyer_id=u.id, seller_id=u.id, status=DealStatus.completed,
                    escrow_wallet_address="T", escrow_private_key_encrypted="x", amount_usdt=300))
        await db.commit()
        ids = {c.channel_name: c.id for c in chans}

    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
        r = (await cl.get("/channels", params={"limit": 50})).json()
        by = {i["channel_name"]: i for i in r["items"]}
        # baseline news: median(1050, 990) = 1020 -> 765..1275
        assert by["b"]["price_verdict"] == "fair" and by["c"]["price_verdict"] == "expensive"
        assert by["closed"]["price_verdict"] == "unknown" and by["zero"]["price_verdict"] == "unknown"
        assert by["b"]["price_per_sub"] == pytest.approx(0.1)
        assert by["b"]["fair_price_range"] is not None

        r = (await cl.get("/channels", params={"sort": "pps_asc"})).json()
        names = [i["channel_name"] for i in r["items"]]
        assert names[:3] == ["a", "b", "c"] and set(names[3:]) == {"closed", "zero"}

        r = (await cl.get("/channels", params={"sort": "pps_desc"})).json()
        assert [i["channel_name"] for i in r["items"]][:3] == ["c", "b", "a"]

        r = (await cl.get("/channels", params={"pps_min": 0.08, "pps_max": 0.15})).json()
        assert [i["channel_name"] for i in r["items"]] == ["b"]

        d = (await cl.get(f"/channels/{ids['a']}")).json()
        assert d["price_verdict"] == "cheaper" and d["price_reference_scope"] == "category"
