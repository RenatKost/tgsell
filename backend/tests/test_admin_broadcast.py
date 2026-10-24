"""Admin one-off broadcast via alerts bot: segment + exclusions, dry run, idempotency, admin-only."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


class TelegramForbiddenError(Exception):
    pass


class FakeBot:
    def __init__(self, blocked=()):
        self.sent, self.blocked = [], set(blocked)

    async def send_message(self, chat_id, text, **kw):
        if chat_id in self.blocked:
            raise TelegramForbiddenError("Forbidden: bot was blocked by the user")
        self.sent.append((chat_id, text))


async def _setup(orm, monkeypatch, bot):
    from fastapi import FastAPI
    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", orm.session)
    svc = importlib.import_module("app.services.broadcast")
    monkeypatch.setattr(svc, "SEND_INTERVAL_SEC", 0)
    monkeypatch.setattr(importlib.import_module("app.services.chat_bridge"), "get_bot", lambda: bot)
    orig = svc.run_campaign

    async def fast(sf, key, text, bot=None, interval=0):
        return await orig(sf, key, text, bot=bot, interval=0)
    monkeypatch.setattr(svc, "run_campaign", fast)
    sec = importlib.import_module("app.utils.security")
    r = importlib.import_module("app.routers.admin_broadcast")
    app = FastAPI()
    app.include_router(r.router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = orm.get_db
    cur = SimpleNamespace(user=None)

    async def superadmin():
        if cur.user is None:
            raise HTTPException(status_code=401)
        if cur.user.role != "admin":
            raise HTTPException(status_code=403, detail="Лише для адміністратора")
        return cur.user
    app.dependency_overrides[sec.get_superadmin_user] = superadmin
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t"), cur, svc


async def _seed(orm):
    from app.models.bundle import BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    from app.utils.timeutil import utcnow_naive
    now = utcnow_naive()
    async with orm.session() as db:
        mk = lambda n, tg, **kw: User(first_name=n, username=n, telegram_id=tg, tg_bot_started_at=now, **kw)
        u = {
            "a": mk("seller_a", 101),                       # 2 approved lots → counted once
            "b": mk("seller_b", 102),                       # only lot will be excluded
            "c": mk("seller_c", 103),                       # bundle seller
            "nosub": User(first_name="n", username="nosub", telegram_id=104),  # not subscribed
            "pend": mk("seller_pending", 105),              # only pending lot
            "renat": mk("Renat_Kos", 106, role=UserRole.admin),
            "ox": mk("ox010010", 107),
            "blk": mk("seller_blocked_bot", 108),           # will block the bot
            "adm": User(first_name="Adm", username="adm", telegram_id=109, role=UserRole.admin),
            "mod": User(first_name="Mod", username="mod", telegram_id=110, role=UserRole.moderator),
        }
        db.add_all(u.values())
        await db.flush()
        ch = lambda s, st=ChannelStatus.approved: Channel(seller_id=u[s].id, telegram_link="https://t.me/x", channel_name="X",
                                                          category="Спорт", subscribers_count=1, price=10, status=st)
        chans = [ch("a"), ch("a"), ch("b"), ch("nosub"), ch("pend", ChannelStatus.pending), ch("renat"), ch("ox"), ch("blk")]
        db.add_all(chans)
        bundle = ChannelBundle(seller_id=u["c"].id, name="Сітка", price=100, status=BundleStatus.approved)
        db.add(bundle)
        await db.commit()
        return u, chans, bundle


@pytest.mark.asyncio
async def test_segment_exclusions_dry_run_and_admin_only(orm, monkeypatch):
    bot = FakeBot()
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u, chans, bundle = await _seed(orm)
    body = {"campaign_key": "promo-1", "text": "Привіт!"}
    async with client:
        cur.user = u["mod"]
        assert (await client.post("/api/admin/broadcast", json=body)).status_code == 403
        assert (await client.get("/api/admin/broadcast/promo-1")).status_code == 403
        cur.user = u["adm"]
        r = (await client.post("/api/admin/broadcast", json=body)).json()  # dry_run default
        assert r["dry_run"] is True and r["recipients"] == 4  # a, b, c, blk
        r = (await client.post("/api/admin/broadcast", json=body | {
            "exclude_channel_ids": [chans[2].id], "exclude_bundle_ids": [bundle.id]})).json()
        assert r["recipients"] == 2  # b and c lose their only active lot
        r = (await client.post("/api/admin/broadcast", json=body | {"exclude_channel_ids": [chans[0].id]})).json()
        assert r["recipients"] == 4  # a still has another lot
        assert bot.sent == []
        st = (await client.get("/api/admin/broadcast/promo-1")).json()
        assert st["total"] == 0
        assert (await client.post("/api/admin/broadcast", json={"campaign_key": "bad key!"})).status_code == 422
    async with orm.session() as db:
        users = await svc.segment_active_sellers(db)
        names = {x.username.lower() for x in users}
        assert names == {"seller_a", "seller_b", "seller_c", "seller_blocked_bot"}


@pytest.mark.asyncio
async def test_send_idempotent_and_forbidden_logged(orm, monkeypatch):
    bot = FakeBot(blocked={108})
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u, chans, bundle = await _seed(orm)
    body = {"campaign_key": "promo-2", "text": "Новина", "dry_run": False}
    async with client:
        cur.user = u["adm"]
        r = (await client.post("/api/admin/broadcast", json=body)).json()
        assert r["started"] and r["to_send"] == 4
        await svc._tasks["promo-2"]
        st = (await client.get("/api/admin/broadcast/promo-2")).json()
        assert st == {"campaign_key": "promo-2", "total": 4, "sent": 3, "failed": 1, "pending": 0, "running": False}
        assert sorted(c for c, _ in bot.sent) == [101, 102, 103]
        # re-run: nobody gets it twice (failed is not retried either)
        r = (await client.post("/api/admin/broadcast", json=body)).json()
        assert r["to_send"] == 0
        await svc._tasks["promo-2"]
        assert len(bot.sent) == 3
        # a new seller joins → only they get the re-run
        from app.models.channel import Channel, ChannelStatus
        from app.models.user import User
        from app.utils.timeutil import utcnow_naive
        async with orm.session() as db:
            nu = User(first_name="n", username="newbie", telegram_id=111, tg_bot_started_at=utcnow_naive())
            db.add(nu)
            await db.flush()
            db.add(Channel(seller_id=nu.id, telegram_link="https://t.me/y", channel_name="Y", category="Спорт",
                           subscribers_count=1, price=5, status=ChannelStatus.approved))
            await db.commit()
        r = (await client.post("/api/admin/broadcast", json=body)).json()
        assert r["to_send"] == 1
        await svc._tasks["promo-2"]
        assert [c for c, _ in bot.sent].count(111) == 1 and len(bot.sent) == 4
    from app.models.broadcast import BroadcastLog
    from app.models.user import User
    from sqlalchemy import select
    async with orm.session() as db:
        row = (await db.execute(select(BroadcastLog).where(BroadcastLog.user_id == u["blk"].id))).scalar_one()
        assert row.status == "failed" and "Forbidden" in row.error
        assert (await db.get(User, u["blk"].id)).tg_bot_unreachable_at is not None


@pytest.mark.asyncio
async def test_unique_constraint_and_sending_never_resent(orm, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from app.models.broadcast import BroadcastLog
    bot = FakeBot()
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u, *_ = await _seed(orm)
    async with orm.session() as db:
        db.add(BroadcastLog(campaign_key="k1", user_id=u["a"].id, status="sending"))
        await db.commit()
        db.add(BroadcastLog(campaign_key="k1", user_id=u["a"].id))
        with pytest.raises(IntegrityError):
            await db.commit()
    await svc.run_campaign(orm.session, "k1", "x", bot=bot, interval=0)
    assert bot.sent == []


@pytest.mark.asyncio
async def test_limit_500(orm, monkeypatch):
    bot = FakeBot()
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u, *_ = await _seed(orm)
    monkeypatch.setattr(svc, "MAX_RECIPIENTS", 2)
    async with client:
        cur.user = u["adm"]
        r = (await client.post("/api/admin/broadcast", json={"campaign_key": "big", "text": "x"})).json()
        assert r["over_limit"] is True
        r = await client.post("/api/admin/broadcast", json={"campaign_key": "big", "text": "x", "dry_run": False})
        assert r.status_code == 400 and bot.sent == []


def test_migration_chain():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "alembic/versions/0053_broadcast_log.py").read_text()
    assert 'revision = "0053"' in src and 'down_revision = "0052"' in src and "uq_broadcast_log_campaign_user" in src
