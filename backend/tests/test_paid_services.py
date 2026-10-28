"""Paid seller services: Top limit, expiry, prices from DB settings, status transitions, revenue row."""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

_n = {"i": 0}


def _wallet():
    _n["i"] += 1
    return (f"TSvc{_n['i']:030d}", "enc")


async def _setup(orm, monkeypatch):
    from fastapi import FastAPI, HTTPException
    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", orm.session)
    monkeypatch.setattr(importlib.import_module("app.services.escrow"), "generate_escrow_wallet", _wallet)
    sec = importlib.import_module("app.utils.security")
    ps = importlib.import_module("app.routers.paid_services")
    channels = importlib.import_module("app.routers.channels")
    admin = importlib.import_module("app.routers.admin")
    app = FastAPI()
    for r in (ps.router, ps.admin_router, channels.router, admin.router):
        app.include_router(r, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = orm.get_db
    cur = SimpleNamespace(user=None)

    async def current():
        if cur.user is None:
            raise HTTPException(status_code=401, detail="no")
        return cur.user

    async def staff():
        u = await current()
        if u.role not in ("admin", "moderator"):
            raise HTTPException(status_code=403, detail="no")
        return u

    async def optional():
        return cur.user

    app.dependency_overrides[sec.get_current_user] = current
    app.dependency_overrides[sec.get_current_user_or_blocked] = current
    app.dependency_overrides[sec.get_admin_user] = staff
    app.dependency_overrides[sec.get_superadmin_user] = staff
    app.dependency_overrides[sec.get_optional_user] = optional
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t"), cur


async def _seed(orm, n=5):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    async with orm.session() as db:
        seller = User(first_name="S", username="s", telegram_id=1)
        adm = User(first_name="A", username="a", telegram_id=2, role=UserRole.admin)
        other = User(first_name="O", username="o", telegram_id=3)
        db.add_all([seller, adm, other])
        await db.flush()
        chs = [Channel(seller_id=seller.id, telegram_link=f"https://t.me/c{i}", channel_name=f"C{i}", category="Спорт",
                       subscribers_count=1000 + i, price=100 + i, status=ChannelStatus.approved) for i in range(n)]
        db.add_all(chs)
        await db.commit()
        return seller, adm, other, [c.id for c in chs]


async def _pay_all(orm, now=None, amount=None):
    from app.services import paid_services as svc
    from app.utils.timeutil import utcnow_naive
    from app.models.paid_service import PaidServiceOrder

    # Prices are read up-front: opening a second session inside the checker's transaction shares the
    # single in-memory SQLite connection and its close() rolls back the checker's flushed changes.
    from sqlalchemy import select
    async with orm.session() as db:
        prices = {o.escrow_wallet_address: o.price_usdt for o in (await db.execute(select(PaidServiceOrder))).scalars()}

    async def fetch(addr):
        if amount is not None:
            return amount
        return prices[addr]
    return await svc.check_orders_once(orm.session, now=now or utcnow_naive(), fetch_balance=fetch)


@pytest.mark.asyncio
async def test_prices_from_settings_and_terms(orm, monkeypatch):
    client, cur = await _setup(orm, monkeypatch)
    seller, adm, other, ids = await _seed(orm)
    async with client:
        cat = (await client.get("/api/services/catalog")).json()
        prices = {i["kind"]: i["price_usdt"] for i in cat["items"]}
        assert prices == {"top": 10.0, "post": 15.0, "verified": 20.0} and cat["top_slots_free"] == 3
        ver = next(i for i in cat["items"] if i["kind"] == "verified")
        assert "не повертаються" in ver["terms"] and "аудиту" in ver["terms"] and ver["refundable"] is False
        cur.user = other
        assert (await client.put("/api/admin/services/settings", json={"service_price_top": 12})).status_code == 403
        cur.user = adm
        assert (await client.put("/api/admin/services/settings", json={"service_price_top": -1})).status_code == 400
        r = await client.put("/api/admin/services/settings", json={"service_price_top": 12.5, "service_price_post": 17})
        assert r.status_code == 200 and r.json()["service_price_top"] == 12.5
        cur.user = seller
        o = (await client.post("/api/services/orders", json={"channel_id": ids[0], "kind": "top"})).json()
        assert o["price_usdt"] == 12.5 and o["status"] == "awaiting_payment" and o["escrow_wallet_address"].startswith("T")
        assert "escrow_private_key_encrypted" not in o
        o = (await client.post("/api/services/orders", json={"channel_id": ids[0], "kind": "post"})).json()
        assert o["price_usdt"] == 17.0
        # not owner
        cur.user = other
        assert (await client.post("/api/services/orders", json={"channel_id": ids[1], "kind": "top"})).status_code == 400


@pytest.mark.asyncio
async def test_top_limit_ordering_and_expiry(orm, monkeypatch):
    from app.models.channel import Channel
    from app.models.paid_service import PaidServiceOrder
    from app.utils.timeutil import utcnow_naive
    client, cur = await _setup(orm, monkeypatch)
    seller, adm, other, ids = await _seed(orm)
    async with client:
        cur.user = seller
        for cid in ids[:3]:
            assert (await client.post("/api/services/orders", json={"channel_id": cid, "kind": "top"})).status_code == 201
        # 3 reserved (unpaid) → 4th refused
        r = await client.post("/api/services/orders", json={"channel_id": ids[3], "kind": "top"})
        assert r.status_code == 400 and "зайняті" in r.json()["detail"]
        assert (await client.post("/api/services/orders", json={"channel_id": ids[0], "kind": "top"})).status_code == 400
        st = await _pay_all(orm)
        assert st["paid"] == 3
        assert (await client.post("/api/services/orders", json={"channel_id": ids[3], "kind": "top"})).status_code == 400
        # catalog: Top lots first with flag, regardless of sort
        items = (await client.get("/api/channels", params={"sort": "price_desc"})).json()["items"]
        assert [i["id"] for i in items[:3]] == sorted(ids[:3], reverse=True) and all(i["is_top"] for i in items[:3])
        assert not items[3]["is_top"]
        # after 7 days → removed and slot freed
        later = utcnow_naive() + timedelta(days=7, minutes=1)
        st = await _pay_all(orm, now=later)
        assert st["expired"] == 3
        async with orm.session() as db:
            ch = await db.get(Channel, ids[0])
            assert ch.top_until is not None and ch.top_until <= later
            o = await db.get(PaidServiceOrder, 1)
            assert o.status == "expired" and abs((o.active_until - o.paid_at).total_seconds() - 7 * 86400) < 5


@pytest.mark.asyncio
async def test_unpaid_top_reservation_released_after_deadline(orm, monkeypatch):
    from app.utils.timeutil import utcnow_naive
    client, cur = await _setup(orm, monkeypatch)
    seller, adm, other, ids = await _seed(orm)
    async with client:
        cur.user = seller
        for cid in ids[:3]:
            await client.post("/api/services/orders", json={"channel_id": cid, "kind": "top"})
        st = await _pay_all(orm, now=utcnow_naive() + timedelta(hours=25), amount=0.0)
        assert st["cancelled"] == 3
        assert (await client.post("/api/services/orders", json={"channel_id": ids[3], "kind": "top"})).status_code == 201


@pytest.mark.asyncio
async def test_partial_and_unknown_balance_never_cancel(orm, monkeypatch):
    from app.models.paid_service import PaidServiceOrder
    from app.services import paid_services as svc
    from app.utils.timeutil import utcnow_naive
    client, cur = await _setup(orm, monkeypatch)
    seller, adm, other, ids = await _seed(orm)
    async with client:
        cur.user = seller
        await client.post("/api/services/orders", json={"channel_id": ids[0], "kind": "post"})
        late = utcnow_naive() + timedelta(days=2)
        await _pay_all(orm, now=late, amount=3.0)

        async def unknown(_a):
            return None
        await svc.check_orders_once(orm.session, now=late, fetch_balance=unknown)
        async with orm.session() as db:
            o = await db.get(PaidServiceOrder, 1)
            assert o.status == "awaiting_payment" and o.received_usdt == 3.0


@pytest.mark.asyncio
async def test_status_transitions_and_badge(orm, monkeypatch):
    from app.models.channel import Channel
    client, cur = await _setup(orm, monkeypatch)
    seller, adm, other, ids = await _seed(orm)
    async with client:
        cur.user = seller
        post = (await client.post("/api/services/orders", json={"channel_id": ids[0], "kind": "post"})).json()
        ver = (await client.post("/api/services/orders", json={"channel_id": ids[1], "kind": "verified"})).json()
        ver2 = (await client.post("/api/services/orders", json={"channel_id": ids[2], "kind": "verified"})).json()
        cur.user = adm
        # unpaid → no admin transition
        assert (await client.post(f"/api/admin/services/orders/{post['id']}/status", json={"status": "published"})).status_code == 400
        await _pay_all(orm)
        q = (await client.get("/api/admin/services/orders", params={"status": "paid"})).json()["items"]
        assert {i["id"] for i in q} == {post["id"], ver["id"], ver2["id"]}
        assert (await client.post(f"/api/admin/services/orders/{post['id']}/status", json={"status": "verified"})).status_code == 400
        assert (await client.post(f"/api/admin/services/orders/{post['id']}/status", json={"status": "in_review"})).status_code == 200
        assert (await client.post(f"/api/admin/services/orders/{post['id']}/status", json={"status": "published"})).json()["status"] == "published"
        assert (await client.post(f"/api/admin/services/orders/{post['id']}/status", json={"status": "rejected"})).status_code == 400
        assert (await client.post(f"/api/admin/services/orders/{ver['id']}/status", json={"status": "verified"})).status_code == 200
        r = await client.post(f"/api/admin/services/orders/{ver2['id']}/status", json={"status": "rejected", "note": "накрутка"})
        assert r.json()["status"] == "rejected"
        cur.user = other
        assert (await client.post(f"/api/admin/services/orders/{ver['id']}/status", json={"status": "rejected"})).status_code == 403
    async with orm.session() as db:
        assert (await db.get(Channel, ids[1])).tgsell_verified is True
        assert (await db.get(Channel, ids[2])).tgsell_verified is False


@pytest.mark.asyncio
async def test_revenue_row_on_dashboard(orm, monkeypatch):
    from app.utils.timeutil import utcnow_naive
    client, cur = await _setup(orm, monkeypatch)
    seller, adm, other, ids = await _seed(orm)
    async with client:
        cur.user = seller
        await client.post("/api/services/orders", json={"channel_id": ids[0], "kind": "top"})       # 10 paid
        await client.post("/api/services/orders", json={"channel_id": ids[1], "kind": "verified"})  # 20 paid → rejected (counted)
        await _pay_all(orm)
        await client.post("/api/services/orders", json={"channel_id": ids[2], "kind": "post"})      # 15 unpaid (not counted)
        cur.user = adm
        await client.post("/api/admin/services/orders/2/status", json={"status": "rejected"})
        d = (await client.get("/api/admin/dashboard-stats")).json()
        assert d["services_revenue"] == 30.0
        assert d["total_revenue"] == 0  # deal fees unaffected


def test_migration_chain():
    from pathlib import Path
    v = Path(__file__).resolve().parents[1] / "alembic/versions"
    src = (v / "0051_paid_services.py").read_text()
    assert 'revision = "0051"' in src and 'down_revision = "0050"' in src
