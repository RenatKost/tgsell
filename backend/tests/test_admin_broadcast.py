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


async def _confirmed(client, body):
    """Real send the way the admin UI does it: dry-run first, then echo its confirm_token."""
    dry = (await client.post("/api/admin/broadcast", json=body | {"dry_run": True})).json()
    return await client.post("/api/admin/broadcast", json=body | {"dry_run": False, "confirm_token": dry.get("confirm_token", "")})


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
        r = (await _confirmed(client, body)).json()
        assert r["started"] and r["to_send"] == 4
        await svc._tasks["promo-2"]
        st = (await client.get("/api/admin/broadcast/promo-2")).json()
        errs = st.pop("errors")
        assert st == {"campaign_key": "promo-2", "total": 4, "sent": 3, "failed": 1, "pending": 0, "running": False,
                      "fail_reasons": {"unreachable": 1}}
        assert len(errs) == 1 and "blocked" in errs[0]["error"] and errs[0]["username"] == "seller_blocked_bot"
        assert sorted(c for c, _ in bot.sent) == [101, 102, 103]
        # re-run: nobody gets it twice (failed is not retried either)
        r = (await _confirmed(client, body)).json()
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
        r = (await _confirmed(client, body)).json()
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


# ---- PR1: targeted (адресна) розсилка, no_bot, «спробувати надіслати», confirm after dry-run ----

def _rows_count():
    from sqlalchemy import func, select
    from app.models.broadcast import BroadcastLog
    return select(func.count(BroadcastLog.id))


def test_parse_targets():
    from app.services.broadcast import parse_targets
    t = parse_targets("12, @Seller_One #45 lot:46\nuser:13;id:14  seller_two 12 !!bad @ab")
    assert t["user_ids"] == [12, 13, 14]
    assert t["usernames"] == ["seller_one", "seller_two"]
    assert t["lot_ids"] == [45, 46]
    assert t["invalid"] == ["!!bad", "@ab"]


def test_try_no_bot_checkbox_off_by_default():
    r = importlib.import_module("app.routers.admin_broadcast")
    assert r.BroadcastIn(campaign_key="k1").try_no_bot is False
    assert r.BroadcastIn(campaign_key="k1").dry_run is True


@pytest.mark.asyncio
async def test_targeted_dry_run_sends_nothing_and_lists_no_bot(orm, monkeypatch):
    bot = FakeBot()
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u, chans, bundle = await _seed(orm)
    targets = f"#{chans[0].id}, @nosub, {u['b'].id}, @ghost_user, 999999, !!bad, @renat_kos, {u['pend'].id}"
    body = {"campaign_key": "t-1", "text": "Адресно", "segment": "targeted", "targets": targets}
    async with client:
        cur.user = u["adm"]
        r = (await client.post("/api/admin/broadcast", json=body)).json()
        assert r["dry_run"] is True and r["try_no_bot"] is False
        assert {i["username"] for i in r["recipients_list"]} == {"seller_a", "seller_b", "seller_pending"}
        assert r["recipients"] == r["to_send"] == 3
        assert [(i["username"], i["reason"]) for i in r["no_bot"]] == [("nosub", "not_started")]
        assert r["no_bot"][0]["reason_label"] == "не запускав бота" and r["no_bot"][0]["can_try"] is True
        assert set(r["not_found"]) == {"999999", "@ghost_user"} and r["invalid"] == ["!!bad"]
        assert r["excluded"] == [u["renat"].id]
        assert r["confirm_token"]
        # checkbox on: no_bot user joins the audience, token changes
        r2 = (await client.post("/api/admin/broadcast", json=body | {"try_no_bot": True})).json()
        assert r2["recipients"] == 4 and r2["confirm_token"] != r["confirm_token"]
        empty = await client.post("/api/admin/broadcast", json=body | {"targets": "  "})
        assert empty.status_code == 422
    assert bot.sent == []
    async with orm.session() as db:
        assert (await db.execute(_rows_count())).scalar() == 0


@pytest.mark.asyncio
async def test_real_send_requires_confirm_token_from_dry_run(orm, monkeypatch):
    bot = FakeBot()
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u, chans, bundle = await _seed(orm)
    body = {"campaign_key": "t-2", "text": "Адресно", "segment": "targeted", "targets": "@seller_a, @nosub"}
    async with client:
        cur.user = u["adm"]
        r = await client.post("/api/admin/broadcast", json=body | {"dry_run": False})
        assert r.status_code == 409  # no dry-run → no send
        dry = (await client.post("/api/admin/broadcast", json=body)).json()
        # text changed after the dry-run → refused
        r = await client.post("/api/admin/broadcast", json=body | {"text": "Інше", "dry_run": False,
                                                                   "confirm_token": dry["confirm_token"]})
        assert r.status_code == 409
        # checkbox ticked after the dry-run → refused
        r = await client.post("/api/admin/broadcast", json=body | {"try_no_bot": True, "dry_run": False,
                                                                   "confirm_token": dry["confirm_token"]})
        assert r.status_code == 409
        assert bot.sent == []
        r = (await client.post("/api/admin/broadcast", json=body | {"dry_run": False,
                                                                    "confirm_token": dry["confirm_token"]})).json()
        assert r["started"] and r["to_send"] == 1 and "confirm_token" not in r
        await svc._tasks["t-2"]
        assert [c for c, _ in bot.sent] == [101]  # nosub skipped: checkbox off


@pytest.mark.asyncio
async def test_try_no_bot_sends_to_no_bot_and_reports_reasons(orm, monkeypatch):
    from app.models.user import User
    from app.utils.timeutil import utcnow_naive
    bot = FakeBot(blocked={105})
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u, chans, bundle = await _seed(orm)
    async with orm.session() as db:
        (await db.get(User, u["pend"].id)).tg_bot_unreachable_at = utcnow_naive()
        (await db.get(User, u["c"].id)).tg_bot_unreachable_at = utcnow_naive()
        db.add(User(first_name="w", username="webonly"))  # no Telegram at all
        await db.commit()
    body = {"campaign_key": "t-3", "text": "Спроба", "segment": "targeted",
            "targets": "@nosub @seller_pending @seller_c @webonly @seller_a", "try_no_bot": True}
    async with client:
        cur.user = u["adm"]
        dry = (await client.post("/api/admin/broadcast", json=body)).json()
        reasons = {i["username"]: i["reason"] for i in dry["no_bot"]}
        assert reasons == {"nosub": "not_started", "seller_pending": "unreachable", "seller_c": "unreachable",
                           "webonly": "no_telegram"}
        assert dry["recipients"] == 4  # webonly cannot be tried
        r = (await client.post("/api/admin/broadcast", json=body | {"dry_run": False,
                                                                    "confirm_token": dry["confirm_token"]})).json()
        await svc._tasks["t-3"]
        st = (await client.get("/api/admin/broadcast/t-3")).json()
        assert st["sent"] == 3 and st["failed"] == 1 and st["fail_reasons"] == {"unreachable": 1}
        assert st["errors"][0]["reason_label"]
    assert sorted(c for c, _ in bot.sent) == [101, 103, 104]
    async with orm.session() as db:
        assert (await db.get(User, u["c"].id)).tg_bot_unreachable_at is None  # delivered → reachable again
        assert (await db.get(User, u["pend"].id)).tg_bot_unreachable_at is not None


@pytest.mark.asyncio
async def test_active_sellers_dry_run_lists_no_bot(orm, monkeypatch):
    bot = FakeBot()
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u, *_ = await _seed(orm)
    async with client:
        cur.user = u["adm"]
        r = (await client.post("/api/admin/broadcast", json={"campaign_key": "p-9", "text": "x"})).json()
    assert r["recipients"] == 4 and [i["username"] for i in r["no_bot"]] == ["nosub"]
    assert bot.sent == []


@pytest.mark.asyncio
async def test_retry_after_respected(orm, monkeypatch):
    class TelegramRetryAfter(Exception):
        def __init__(self):
            super().__init__("Too Many Requests: retry after 0")
            self.retry_after = 0

    class FloodBot(FakeBot):
        flooded = False

        async def send_message(self, chat_id, text, **kw):
            if not self.flooded:
                self.flooded = True
                raise TelegramRetryAfter()
            await super().send_message(chat_id, text, **kw)

    bot = FloodBot()
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u, *_ = await _seed(orm)
    async with orm.session() as db:
        await svc.prepare(db, "fl-1", [u["a"]])
    res = await svc.run_campaign(orm.session, "fl-1", "x", bot=bot, interval=0)
    assert res == {"sent": 1, "failed": 0} and bot.sent == [(101, "x")]
