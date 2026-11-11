"""Seller cabinet site-view counts: access, owner/staff exclusion, 7-day window."""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.utils.timeutil import utcnow_naive


async def _setup(orm, monkeypatch):
    from fastapi import FastAPI, HTTPException

    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", orm.session)
    sec = importlib.import_module("app.utils.security")
    channels = importlib.import_module("app.routers.channels")
    admin = importlib.import_module("app.routers.admin")
    app = FastAPI()
    app.include_router(channels.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
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


async def _seed(orm):
    from app.models.activity import UserEvent
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole

    now = utcnow_naive()
    async with orm.session() as db:
        seller = User(first_name="S", username="s", telegram_id=91001)
        other_seller = User(first_name="OS", username="os", telegram_id=91002)
        buyer = User(first_name="B", username="b", telegram_id=91003)
        adm = User(first_name="A", username="a", telegram_id=91004, role=UserRole.admin)
        mod = User(first_name="M", username="m", telegram_id=91005, role=UserRole.moderator)
        db.add_all([seller, other_seller, buyer, adm, mod])
        await db.flush()
        ch_a = Channel(
            seller_id=seller.id, telegram_link="https://t.me/views_a", channel_name="Views A",
            category="Спорт", subscribers_count=1000, price=100, avg_views=50,
            status=ChannelStatus.approved,
        )
        ch_b = Channel(
            seller_id=seller.id, telegram_link="https://t.me/views_b", channel_name="Views B",
            category="Спорт", subscribers_count=2000, price=200, avg_views=80,
            status=ChannelStatus.approved,
        )
        ch_c = Channel(
            seller_id=other_seller.id, telegram_link="https://t.me/views_c", channel_name="Views C",
            category="Спорт", subscribers_count=3000, price=300, avg_views=90,
            status=ChannelStatus.approved,
        )
        db.add_all([ch_a, ch_b, ch_c])
        await db.flush()

        def ev(cid, *, user_id=None, anon=None, when=None):
            return UserEvent(
                user_id=user_id, anon_id=anon, event_type="channel_view",
                object_type="channel", object_id=cid, created_at=when or now,
            )

        db.add_all([
            ev(ch_a.id, anon="anon-1"),
            ev(ch_a.id, anon="anon-2"),
            ev(ch_a.id, user_id=buyer.id),
            ev(ch_a.id, user_id=seller.id),
            ev(ch_a.id, user_id=adm.id),
            ev(ch_a.id, user_id=mod.id),
            ev(ch_a.id, anon="anon-old", when=now - timedelta(days=8)),
            ev(ch_b.id, user_id=seller.id),
            ev(ch_c.id, user_id=buyer.id),
        ])
        await db.commit()
        return SimpleNamespace(
            seller=seller, other_seller=other_seller, buyer=buyer, adm=adm, mod=mod,
            ch_a=ch_a.id, ch_b=ch_b.id, ch_c=ch_c.id, now=now,
        )


def _item(payload, cid):
    if isinstance(payload, dict) and "items" in payload:
        items = payload["items"]
    else:
        items = payload
    return next(x for x in items if x["id"] == cid)


@pytest.mark.asyncio
async def test_owner_sees_counts_buyer_and_public_do_not(orm, monkeypatch):
    ids = await _seed(orm)
    client, cur = await _setup(orm, monkeypatch)

    async with client:
        cur.user = ids.seller
        listed = await client.get("/api/channels", params={"seller_id": ids.seller.id})
        assert listed.status_code == 200
        a = _item(listed.json(), ids.ch_a)
        b = _item(listed.json(), ids.ch_b)
        # 2 anon + 1 buyer in the 7-day window; seller/staff excluded; old anon in total only
        assert a["site_views_7d"] == 3
        assert a["site_views_total"] == 4
        assert b["site_views_7d"] == 0
        assert b["site_views_total"] == 0

        one = await client.get(f"/api/channels/{ids.ch_a}")
        assert one.status_code == 200
        assert one.json()["site_views_7d"] == 3
        assert one.json()["site_views_total"] == 4

        cur.user = ids.other_seller
        foreign = await client.get(f"/api/channels/{ids.ch_a}")
        assert foreign.status_code == 200
        assert "site_views_7d" not in foreign.json()
        assert "site_views_total" not in foreign.json()

        cur.user = ids.buyer
        as_buyer = await client.get(f"/api/channels/{ids.ch_a}")
        assert as_buyer.status_code == 200
        assert "site_views_7d" not in as_buyer.json()
        assert "site_views_total" not in as_buyer.json()

        catalog = await client.get("/api/channels")
        assert catalog.status_code == 200
        pub = _item(catalog.json(), ids.ch_a)
        assert "site_views_7d" not in pub
        assert "site_views_total" not in pub

        cur.user = None
        anon = await client.get(f"/api/channels/{ids.ch_a}")
        assert anon.status_code == 200
        assert "site_views_7d" not in anon.json()
        assert "site_views_total" not in anon.json()


@pytest.mark.asyncio
async def test_staff_sees_counts_and_is_excluded(orm, monkeypatch):
    ids = await _seed(orm)
    client, cur = await _setup(orm, monkeypatch)

    async with client:
        cur.user = ids.adm
        one = await client.get(f"/api/channels/{ids.ch_a}")
        assert one.status_code == 200
        assert one.json()["site_views_7d"] == 3
        assert one.json()["site_views_total"] == 4

        all_admin = await client.get("/api/admin/channels")
        assert all_admin.status_code == 200
        a = _item(all_admin.json(), ids.ch_a)
        assert a["site_views_7d"] == 3 and a["site_views_total"] == 4
        c = _item(all_admin.json(), ids.ch_c)
        assert c["site_views_7d"] == 1 and c["site_views_total"] == 1

        cur.user = ids.mod
        as_mod = await client.get(f"/api/channels/{ids.ch_a}")
        assert as_mod.json()["site_views_7d"] == 3


@pytest.mark.asyncio
async def test_counts_for_is_one_aggregate_and_window(orm):
    from app.services import site_views as sv

    ids = await _seed(orm)
    async with orm.session() as db:
        counts = await sv.counts_for(db, [ids.ch_a, ids.ch_b, ids.ch_c], now=ids.now)
        assert counts[ids.ch_a] == (3, 4)
        assert ids.ch_b not in counts  # zero views → omitted; attach fills (0, 0)
        assert counts[ids.ch_c] == (1, 1)

        from app.models.activity import UserEvent
        db.add(UserEvent(
            anon_id="anon-edge", event_type="channel_view", object_type="channel",
            object_id=ids.ch_a, created_at=ids.now - timedelta(days=7, seconds=1),
        ))
        await db.commit()
        counts2 = await sv.counts_for(db, [ids.ch_a], now=ids.now)
        assert counts2[ids.ch_a] == (3, 5)


@pytest.mark.asyncio
async def test_0065_index_upgrade_downgrade_upgrade(orm, db_url):
    """Live CONCURRENTLY create / drop / create of the seller-views index."""
    url, kind = db_url
    if kind != "postgres":
        pytest.skip("CREATE INDEX CONCURRENTLY requires Postgres")

    src = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "alembic" / "versions" / "0065_user_events_type_object_created.py"
    ).read_text()
    assert "CREATE INDEX CONCURRENTLY" in src
    assert "autocommit_block" in src
    assert "ix_user_events_type_object_created" in src
    assert "down_revision = \"0064\"" in src

    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    index = "ix_user_events_type_object_created"
    create_sql = (
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index} "
        "ON user_events (event_type, object_id, created_at)"
    )
    drop_sql = f"DROP INDEX CONCURRENTLY IF EXISTS {index}"
    exists_sql = text(
        "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = :n"
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text(drop_sql))
            assert (await conn.execute(exists_sql, {"n": index})).first() is None
            await conn.execute(text(create_sql))
            assert (await conn.execute(exists_sql, {"n": index})).first() is not None
            await conn.execute(text(drop_sql))
            assert (await conn.execute(exists_sql, {"n": index})).first() is None
            await conn.execute(text(create_sql))
            assert (await conn.execute(exists_sql, {"n": index})).first() is not None
    finally:
        await engine.dispose()
