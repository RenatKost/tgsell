"""«Шукаю канал» (/wanted): validation, auto-checks, limits, moderation, privacy,
lot attribution, buyer notification, seller digest, admin stats, sitemap."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.parametrize("text,bad", [
    ("Шукаю канал про криптовалюту", False),
    ("Пишіть @seller_name", True),
    ("t.me/joinchat/abc", True),
    ("дзвоніть +380 67 123 45 67", True),
    ("див. https://example.com", True),
    ("мій сайт example.com", True),
    ("канал 18+ контент", True),
    ("канал про ставки на спорт", True),
    ("Casino traffic", True),
    ("", False),
])
def test_check_text(text, bad):
    from app.services.wanted import check_text
    assert (check_text(text) is not None) is bad


def test_validate_rules():
    from app.services.wanted import validate
    ok = validate({"category": "Криптовалюта", "language": "ua", "subs_min": "1000", "subs_max": 5000,
                   "budget_max": "300", "comment": "  "})
    assert ok["subs_min"] == 1000 and ok["budget_max"] == 300.0 and ok["comment"] is None
    for bad in [
        {"category": "Новини 18+", "language": "ua", "budget_max": 1},
        {"category": "Нема", "language": "ua", "budget_max": 1},
        {"category": "Спорт", "language": "de", "budget_max": 1},
        {"category": "Спорт", "language": "ua", "subs_min": 10, "subs_max": 5, "budget_max": 1},
        {"category": "Спорт", "language": "ua", "budget_min": 10, "budget_max": 5},
        {"category": "Спорт", "language": "ua"},
        {"category": "Спорт", "language": "ua", "budget_max": 1, "comment": "x" * 301},
        {"category": "Спорт", "language": "ua", "budget_max": 1, "comment": "@contact_me"},
    ]:
        with pytest.raises(ValueError):
            validate(bad)


def test_categories_mirror_catalog_without_adult():
    from pathlib import Path
    import re
    from app.services.wanted import CATEGORIES
    js = (Path(__file__).resolve().parents[2] / "src/components/Main/Calculator.jsx").read_text(encoding="utf-8")
    labels = re.findall(r"label: '([^']+)'", js.split("export const options", 1)[1].split("];", 1)[0])
    assert CATEGORIES == [l for l in labels if "18+" not in l]


def test_channel_matches_budget_tolerance():
    from app.services.wanted import channel_matches
    r = SimpleNamespace(category="Спорт", subs_min=1000, subs_max=5000, budget_max=100)
    ch = lambda **kw: SimpleNamespace(**({"category": "Спорт", "subscribers_count": 2000, "price": 100} | kw))
    assert channel_matches(r, ch())
    assert channel_matches(r, ch(price=120))
    assert not channel_matches(r, ch(price=120.01))
    assert not channel_matches(r, ch(subscribers_count=999))
    assert not channel_matches(r, ch(subscribers_count=5001))
    assert not channel_matches(r, ch(category="Гумор"))


class FakeBot:
    sent: list = []

    def __init__(self, token, **_kw):
        self.session = SimpleNamespace(close=AsyncMock())

    async def send_message(self, chat_id, text, **_kw):
        FakeBot.sent.append((chat_id, text))


async def _setup(orm, monkeypatch):
    from fastapi import FastAPI
    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", orm.session)
    from app.config import settings
    monkeypatch.setattr(settings, "bot_token_alerts", "test-token")
    monkeypatch.setattr(settings, "frontend_url", "https://tgsell.test/")
    monkeypatch.setattr(importlib.import_module("aiogram"), "Bot", FakeBot)
    FakeBot.sent = []
    admin_alerts = []

    async def fake_alert(text, alert_key=None, **_kw):
        admin_alerts.append(text)
        return True

    monkeypatch.setattr(importlib.import_module("app.services.alerts"), "send_admin_alert", fake_alert)
    sec = importlib.import_module("app.utils.security")
    wanted = importlib.import_module("app.routers.wanted")
    channels = importlib.import_module("app.routers.channels")
    monkeypatch.setattr(importlib.import_module("app.services.channel_stats"), "collect_channel_stats",
                        AsyncMock(return_value={}))
    app = FastAPI()
    app.include_router(wanted.router, prefix="/api")
    app.include_router(wanted.admin_router, prefix="/api")
    app.include_router(channels.router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = orm.get_db
    cur = SimpleNamespace(user=None)

    async def current():
        if cur.user is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="no")
        return cur.user

    async def admin_dep():
        if cur.user is None or cur.user.role not in ("admin", "moderator"):
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="no")
        return cur.user

    app.dependency_overrides[sec.get_current_user] = current
    app.dependency_overrides[sec.get_admin_user] = admin_dep
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t"), cur, admin_alerts


async def _users(orm):
    from app.models.user import User, UserRole
    from app.utils.timeutil import utcnow_naive
    now = utcnow_naive()
    async with orm.session() as db:
        buyer = User(first_name="Buyer", username="buyer_secret", telegram_id=501, tg_bot_started_at=now)
        seller = User(first_name="Seller", telegram_id=502, tg_bot_started_at=now)
        mute = User(first_name="Mute", telegram_id=503)  # never pressed Start
        admin = User(first_name="Adm", telegram_id=504, role=UserRole.admin)
        db.add_all([buyer, seller, mute, admin])
        await db.commit()
        return buyer, seller, mute, admin


BODY = {"category": "Спорт", "subs_min": 1000, "subs_max": 10000, "budget_min": 50, "budget_max": 200,
        "language": "ua", "comment": "Потрібен живий канал"}


@pytest.mark.asyncio
async def test_full_flow(orm, monkeypatch):
    from sqlalchemy import select
    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal
    from app.models.wanted import WantedMatch, WantedRequest
    from app.services import wanted as svc

    client, cur, admin_alerts = await _setup(orm, monkeypatch)
    buyer, seller, mute, admin = await _users(orm)
    async with client as cl:
        # anonymous: list works, create requires login
        assert (await cl.get("/api/wanted")).json()["items"] == []
        assert (await cl.post("/api/wanted", json=BODY)).status_code == 401

        cur.user = buyer
        r = await cl.post("/api/wanted", json=BODY | {"comment": "пишіть @buyer_secret"})
        assert r.status_code == 400 and "контакт" in r.json()["detail"]
        r = await cl.post("/api/wanted", json=BODY)
        assert r.status_code == 201 and r.json()["status"] == "pending"
        rid = r.json()["id"]
        assert len(admin_alerts) == 1 and f"#{rid}" in admin_alerts[0] and "модерац" in admin_alerts[0]
        # pending is not public
        assert (await cl.get("/api/wanted")).json()["items"] == []
        assert (await cl.get(f"/api/wanted/{rid}")).status_code == 404
        # limit 3 active
        for _ in range(2):
            assert (await cl.post("/api/wanted", json=BODY)).status_code == 201
        r = await cl.post("/api/wanted", json=BODY)
        assert r.status_code == 400 and "3" in r.json()["detail"]
        mine = (await cl.get("/api/wanted/mine")).json()
        assert mine["active"] == 3 and len(mine["items"]) == 3
        # non-admin cannot moderate
        assert (await cl.post(f"/api/admin/wanted/{rid}/approve")).status_code == 403
        # buyer closes one -> slot frees up
        extra = mine["items"][0]["id"]
        assert (await cl.delete(f"/api/wanted/{extra}")).status_code == 200
        assert (await cl.get("/api/wanted/mine")).json()["active"] == 2

        cur.user = admin
        pend = (await cl.get("/api/admin/wanted?status=pending")).json()["items"]
        assert {p["id"] for p in pend} >= {rid}
        assert (await cl.post(f"/api/admin/wanted/{rid}/approve")).status_code == 200
        assert (await cl.post(f"/api/admin/wanted/{rid}/approve")).status_code == 400
        other = [p["id"] for p in pend if p["id"] != rid][0]
        r = await cl.post(f"/api/admin/wanted/{other}/reject", json={"reason": "Дубль"})
        assert r.json()["status"] == "rejected" and r.json()["rejection_reason"] == "Дубль"

        # public list: approved only, no buyer data
        items = (await cl.get("/api/wanted")).json()["items"]
        assert [i["id"] for i in items] == [rid]
        raw = str(items)
        assert "buyer_secret" not in raw and "user_id" not in raw and "501" not in raw
        card = (await cl.get(f"/api/wanted/{rid}")).json()
        assert card["category"] == "Спорт" and card["language_label"] == "Україна"

        # seller lists a lot via the button -> wanted_request_id stored
        cur.user = seller
        r = await cl.post("/api/channels", json={"telegram_link": "https://t.me/sport_fit", "channel_name": "Sport",
                                                 "category": "Спорт", "price": 230, "wanted_request_id": rid})
        assert r.status_code == 201, r.text
        lot_id = r.json()["id"]
        # buyer can't attribute own lot; bogus id ignored
        cur.user = buyer
        r = await cl.post("/api/channels", json={"telegram_link": "https://t.me/own_one", "channel_name": "Own",
                                                 "category": "Спорт", "price": 10, "wanted_request_id": rid})
        own_id = r.json()["id"]

    async with orm.session() as db:
        lot = await db.get(Channel, lot_id)
        assert lot.wanted_request_id == rid
        assert (await db.get(Channel, own_id)).wanted_request_id is None
        lot.subscribers_count = 5000
        lot.status = ChannelStatus.approved
        too_pricey = Channel(seller_id=seller.id, telegram_link="https://t.me/p", channel_name="P", category="Спорт",
                             subscribers_count=5000, price=241, status=ChannelStatus.approved)
        db.add(too_pricey)
        await db.commit()
        FakeBot.sent = []
        assert await svc.notify_buyers_for_channel(db, lot.id) == 1  # 230 <= 200*1.2
        assert await svc.notify_buyers_for_channel(db, lot.id) == 0  # dedup
        assert await svc.notify_buyers_for_channel(db, too_pricey.id) == 0
        assert len(FakeBot.sent) == 1 and FakeBot.sent[0][0] == 501
        assert f"/channel/{lot.id}?src=wanted" in FakeBot.sent[0][1]
        assert len((await db.execute(select(WantedMatch))).scalars().all()) == 1

        db.add(Deal(channel_id=lot.id, buyer_id=buyer.id, seller_id=seller.id, amount_usdt=230, escrow_wallet_address="T0", escrow_private_key_encrypted="x"))
        await db.commit()
        st = await svc.admin_stats(db)
        assert st["lots_from_button"] == 1 and st["deals_from_lots"] == 1
        assert st["approved"] == 1 and st["rejected"] == 1 and st["closed"] == 1 and st["pending"] == 0

        # expiry: 30 days later the request is gone from public list and frees the slot
        r = await db.get(WantedRequest, rid)
        assert r.expires_at - r.created_at.replace(microsecond=0) >= timedelta(days=29, hours=23)
        r.expires_at = datetime(2000, 1, 1)
        await db.commit()
        assert await svc.count_active(db, buyer.id) == 0


@pytest.mark.asyncio
async def test_daily_digest_only_when_new(orm, monkeypatch):
    from app.models.channel import Channel, ChannelStatus
    from app.models.wanted import WantedRequest
    from app.services import wanted as svc

    _client, _cur, _ = await _setup(orm, monkeypatch)
    buyer, seller, mute, admin = await _users(orm)
    # 10:30 Kyiv on a summer day = 07:30 UTC
    now = datetime(2026, 7, 1, 7, 30)
    assert svc.digest_due(datetime(2026, 7, 1, 6, 0)) is None
    async with orm.session() as db:
        for u in (seller, mute):
            db.add(Channel(seller_id=u.id, telegram_link=f"https://t.me/s{u.id}", channel_name="S", category="Спорт",
                           price=1, status=ChannelStatus.approved))
        await db.commit()
    FakeBot.sent = []
    assert await svc.send_digest_once(now) == 0 and FakeBot.sent == []  # nothing new -> nothing sent

    async with orm.session() as db:
        db.add(WantedRequest(user_id=buyer.id, category="Спорт", language="en", budget_max=100, status="approved",
                             moderated_at=now - timedelta(hours=5), expires_at=now + timedelta(days=20)))
        db.add(WantedRequest(user_id=buyer.id, category="Гумор", language="ua", budget_max=100, status="pending",
                             expires_at=now + timedelta(days=20)))
        await db.commit()
    assert await svc.send_digest_once(now) == 1
    assert [c for c, _ in FakeBot.sent] == [502]  # only sellers who started the bot
    text = FakeBot.sent[0][1]
    assert "Спорт" in text and "Гумор" not in text and "/sell?wanted=" in text and "src=wanted" in text
    assert "buyer_secret" not in text
    assert await svc.send_digest_once(now + timedelta(hours=1)) == 0  # once per day


def test_sitemap_and_spa_route():
    from app.routers import seo
    from app.utils import spa_meta
    assert any(p == "/wanted" for p, *_ in seo.STATIC_PAGES)
    assert "/wanted" in spa_meta.EXTRA_ROUTE_META


def test_migration_0048_chain():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "alembic/versions/0048_wanted_requests.py").read_text()
    assert 'revision = "0048"' in src and 'down_revision = "0047"' in src
