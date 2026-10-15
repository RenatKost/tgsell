"""Task 21: market price estimate (price_per_sub / price_per_view / verdict)."""
from __future__ import annotations

import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.pricing import Sample, build_market, estimate


def _est(m, **kw):
    base = dict(category="news", price=100.0, subscribers=1000, avg_views=500, is_closed=False)
    base.update(kw)
    return estimate(m, **base)


NEWS = [Sample("news", 100, 1000, 500), Sample("news", 200, 1000, 1000), Sample("news", 300, 1000, 1500)]


def test_metrics_and_category_median():
    m = build_market(NEWS)
    ref, scope = m.ref_for("news")
    assert scope == "category" and ref.pps == pytest.approx(0.2) and ref.ppv == pytest.approx(0.2)
    r = _est(m, price=200, avg_views=1000)
    assert r["price_per_sub"] == pytest.approx(0.2) and r["price_per_view"] == pytest.approx(0.2)
    assert r["fair_price_range"] == [150.0, 250.0] and r["price_verdict"] == "fair"
    assert r["price_reference_scope"] == "category"


def test_verdicts_cheaper_and_expensive():
    m = build_market(NEWS)
    assert _est(m, price=100, avg_views=1000)["price_verdict"] == "cheaper"
    assert _est(m, price=400, avg_views=1000)["price_verdict"] == "expensive"


def test_small_category_falls_back_to_catalog():
    m = build_market(NEWS + [Sample("crypto", 10_000, 1000, 500)])
    r = _est(m, category="crypto", price=200, avg_views=1000)
    assert r["price_reference_scope"] == "catalog"
    assert r["price_verdict"] in {"cheaper", "fair", "expensive"}


def test_unknown_cases():
    m = build_market(NEWS)
    for kw in (dict(is_closed=True), dict(subscribers=0), dict(price=0), dict(subscribers=None)):
        r = _est(m, **kw)
        assert r["price_verdict"] == "unknown" and r["fair_price_range"] is None
    assert _est(build_market([]))["price_verdict"] == "unknown"


def test_no_views_uses_subs_only():
    m = build_market(NEWS)
    r = _est(m, price=200, avg_views=0)
    assert r["price_per_view"] is None and r["fair_price_range"] == [150.0, 250.0]


def test_closed_zero_subs_and_zero_price_excluded_from_medians():
    junk = [Sample("news", 0, 1000, 500), Sample("news", 50, 0, 0),
            Sample("news", 1, 1000, 500, is_closed=True), Sample("news", 0.0, None, None)]
    m = build_market(NEWS + junk)
    ref, scope = m.ref_for("news")
    assert scope == "category" and ref.samples == 3 and ref.pps == pytest.approx(0.2)
    assert _est(m, price=0)["price_verdict"] == "unknown"  # not flagged "cheaper"


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
                           category="news", price=price, subscribers_count=subs, avg_views=views,
                           status=kw.pop("status", ChannelStatus.approved), **kw)

        chans = [ch("a", 100, 1000, 500), ch("b", 200, 1000, 1000), ch("c", 1000, 1000, 1000),
                 ch("closed", 50, 0, 0, is_closed=True), ch("zero", 0, 1000, 100),
                 ch("sold", 300, 1000, 1500, status=ChannelStatus.sold)]
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
        # medians over a,b,c + completed deal (0.1,0.2,1.0,0.3 → pps 0.25)
        assert by["b"]["price_verdict"] == "fair" and by["c"]["price_verdict"] == "expensive"
        assert by["closed"]["price_verdict"] == "unknown" and by["zero"]["price_verdict"] == "unknown"
        assert by["b"]["price_per_sub"] == pytest.approx(0.2)
        assert by["b"]["fair_price_range"] is not None

        r = (await cl.get("/channels", params={"sort": "pps_asc"})).json()
        names = [i["channel_name"] for i in r["items"]]
        assert names[:3] == ["a", "b", "c"] and set(names[3:]) == {"closed", "zero"}

        r = (await cl.get("/channels", params={"sort": "pps_desc"})).json()
        assert [i["channel_name"] for i in r["items"]][:3] == ["c", "b", "a"]

        r = (await cl.get("/channels", params={"pps_min": 0.15, "pps_max": 0.5})).json()
        assert [i["channel_name"] for i in r["items"]] == ["b"]

        d = (await cl.get(f"/channels/{ids['a']}")).json()
        assert d["price_verdict"] == "cheaper" and d["price_reference_scope"] == "category"
