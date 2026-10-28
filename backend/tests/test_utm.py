"""UTM campaign tracking: sanitising, visit beacon (+log, rate limit, no PII), attribution on
registration / single lot / bundle, admin «Кампанії» report with date filter."""
from __future__ import annotations

import importlib
import logging
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from tests.test_paid_services import _setup
from tests.test_promo_top_paid import _mock_bot

IG_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
         "Mobile/15E148 Instagram 345.0.0.0 (iPhone14,5; iOS 17_5; uk_UA)")
UTM = {"utm_source": "instagram", "utm_campaign": "promo_top7", "utm_content": "reel1"}


def test_clean_and_ua_class():
    from app.services import utm
    assert utm.clean("  Insta<script>Gram ") == "instascriptgram"
    assert utm.clean("x" * 100) == "x" * 64 and utm.clean("") is None
    assert utm.clean_path("/sell?utm_source=a&tg=1") == "/sell" and utm.clean_path("javascript:x") is None
    assert utm.ua_class(IG_UA) == "ig_inapp"
    assert utm.ua_class("Mozilla/5.0 (iPhone) FBAN/FBIOS") == "fb_inapp"
    assert utm.ua_class("Mozilla/5.0 (Linux; Android 14) Mobile Safari") == "mobile"
    assert utm.ua_class("Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120") == "bot"
    assert utm.ua_class("Mozilla/5.0 (Windows NT 10.0)") == "desktop"


def test_apply_first_touch_only():
    from types import SimpleNamespace

    from app.services import utm
    o = SimpleNamespace(utm_source=None, utm_campaign=None, utm_content=None)
    assert not utm.apply(o, {"utm_content": "only-content"})  # needs source or campaign
    assert utm.apply(o, UTM) and o.utm_campaign == "promo_top7"
    assert not utm.apply(o, {"utm_source": "tiktok"}) and o.utm_source == "instagram"


async def _app(orm, monkeypatch):
    client, cur = await _setup(orm, monkeypatch)
    app = client._transport.app
    for name in ("app.routers.utm", "app.routers.bundles", "app.routers.auth"):
        app.include_router(importlib.import_module(name).router, prefix="/api")
    importlib.import_module("app.utils.activity_ids").limiter.reset()
    monkeypatch.setattr(importlib.import_module("app.tasks.stats_collector"), "schedule_stats_refresh", lambda ids: None)
    return client, cur


@pytest.mark.asyncio
async def test_visit_beacon_logs_and_rate_limits(orm, monkeypatch, caplog):
    from sqlalchemy import select

    from app.models.utm import UtmVisit
    client, _ = await _app(orm, monkeypatch)
    caplog.set_level(logging.INFO, logger="app.utm")
    r = await client.post("/api/track/utm", json={"anon": "anon-1", "path": "/catalog?x=1", **UTM},
                          headers={"user-agent": IG_UA})
    assert r.status_code == 204
    assert "[utm] visit source=instagram campaign=promo_top7 content=reel1 path=/catalog ua=ig_inapp" in caplog.text
    r = await client.post("/api/track/utm", json={"anon": "anon-1", "path": "/"})  # no utm → ignored
    assert r.status_code == 204
    async with orm.session() as db:
        rows = (await db.execute(select(UtmVisit))).scalars().all()
    assert len(rows) == 1 and rows[0].anon_hash != "anon-1" and len(rows[0].anon_hash) == 32
    assert rows[0].ua_class == "ig_inapp" and rows[0].path == "/catalog"
    codes = [(await client.post("/api/track/utm", json={"anon": "anon-1", "path": "/", **UTM})).status_code
             for _ in range(12)]
    assert codes.count(429) >= 2


@pytest.mark.asyncio
async def test_attribution_and_campaign_report(orm, monkeypatch):
    from app.models.bundle import BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    from app.utils import auth_tokens
    _mock_bot(monkeypatch)
    from app.config import settings
    monkeypatch.setattr(settings, "promo_top_until", "2000-01-01T00:00:00")
    client, cur = await _app(orm, monkeypatch)

    for i in range(3):
        await client.post("/api/track/utm", json={"anon": f"v{i}", "path": "/sell", **UTM})
    await client.post("/api/track/utm", json={"anon": "v9", "path": "/", "utm_source": "tiktok"})

    # registration through the bot deep-link login carries the stored UTM
    tok = auth_tokens.create_auth_token()
    auth_tokens.complete_auth_token(tok, {"id": 7001, "username": "newbie", "first_name": "N"})
    r = await client.get("/api/auth/bot-check", params={"token": tok, **UTM})
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    async with orm.session() as db:
        from sqlalchemy import select
        seller = (await db.execute(select(User).where(User.telegram_id == 7001))).scalar_one()
        assert seller.utm_campaign == "promo_top7"
        adm = User(first_name="A", telegram_id=7999, role=UserRole.admin)
        db.add(adm)
        await db.commit()

    cur.user = seller
    r = await client.post("/api/channels", json={"telegram_link": "https://t.me/utm_one", "channel_name": "x",
                                                 "category": "Спорт", "price": 50, **UTM})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = await client.post("/api/bundles", json={"name": "Сітка", "price": 100, "category": "Спорт",
                                                "channel_links": ["https://t.me/utm_b1", "https://t.me/utm_b2"], **UTM})
    assert r.status_code in (200, 201), r.text
    bid = r.json()["id"]
    async with orm.session() as db:
        assert (await db.get(Channel, cid)).utm_source == "instagram"
        assert (await db.get(ChannelBundle, bid)).utm_content == "reel1"
    cur.user = adm
    assert (await client.post(f"/api/admin/channels/{cid}/approve")).status_code == 200

    r = await client.get("/api/admin/utm/campaigns")
    assert r.status_code == 200, r.text
    rows = {(i["utm_source"], i["utm_campaign"], i["utm_content"]): i for i in r.json()["items"]}
    p = rows[("instagram", "promo_top7", "reel1")]
    assert (p["visits"], p["visitors"], p["registrations"], p["lots_submitted"], p["lots_approved"]) == (3, 3, 1, 2, 1)
    assert rows[("tiktok", "", "")]["visits"] == 1
    future = (date.today() + timedelta(days=5)).isoformat()
    r = await client.get("/api/admin/utm/campaigns", params={"date_from": future})
    assert r.json()["items"] == [] and r.json()["totals"]["visits"] == 0
    assert (await client.get("/api/admin/utm/campaigns", params={"date_from": future, "date_to": "2020-01-01"})).status_code == 400
    async with orm.session() as db:
        b = await db.get(ChannelBundle, bid)
        b.status = BundleStatus.approved
        await db.commit()
    r = await client.get("/api/admin/utm/campaigns")
    assert r.json()["totals"]["lots_approved"] == 2
    _ = ChannelStatus


@pytest.mark.asyncio
async def test_campaign_report_is_admin_only(orm, monkeypatch):
    from app.models.user import User
    client, cur = await _app(orm, monkeypatch)
    assert (await client.get("/api/admin/utm/campaigns")).status_code == 401
    async with orm.session() as db:
        u = User(first_name="U", telegram_id=7100)
        db.add(u)
        await db.commit()
    cur.user = u
    assert (await client.get("/api/admin/utm/campaigns")).status_code == 403


def test_telegram_hash_ignores_utm_fields():
    from app.schemas.auth import TelegramAuthData
    d = TelegramAuthData(id=1, first_name="a", auth_date=1, hash="h", **UTM)
    dumped = d.model_dump(exclude={"utm_source", "utm_campaign", "utm_content"})
    assert "utm_source" not in dumped and d.utm_campaign == "promo_top7"
