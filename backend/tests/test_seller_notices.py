"""Seller alerts outbox (0067): enqueue rules, delivery, retries, cutoff, audit, escaping, cabinet exposure."""
from __future__ import annotations

import asyncio
import importlib
import itertools
import os
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import unquote

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.utils.timeutil import utcnow_naive

BACKEND_ROOT = Path(__file__).resolve().parents[1]
_seq = itertools.count(1)


class TelegramForbiddenError(Exception):
    """Same class name as aiogram's → classified as permanent."""


class TelegramNetworkError(Exception):
    """Transient."""


@pytest_asyncio.fixture
async def env(pg_orm, monkeypatch):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole

    admin_r = importlib.import_module("app.routers.admin")
    svc = importlib.import_module("app.services.seller_notices")
    monkeypatch.setattr(admin_r, "_notify_seller_channel", AsyncMock())

    async with pg_orm.session() as db:
        admin = User(first_name="A", telegram_id=71011, role=UserRole.admin)
        seller = User(first_name="SellerFirstName", username="seller_handle", telegram_id=71012)
        notg = User(first_name="NoTg", telegram_id=None, google_id="g-71013")
        db.add_all([admin, seller, notg])
        await db.commit()
    ids = SimpleNamespace(admin=admin.id, seller=seller.id, notg=notg.id)

    async def channel(seller_id=None, **kw):
        async with pg_orm.session() as db:
            c = Channel(seller_id=seller_id or ids.seller, telegram_link=f"https://t.me/notice{next(_seq)}",
                        channel_name=kw.pop("channel_name", "Канал"), category="news", price=10.0,
                        status=kw.pop("status", ChannelStatus.approved), **kw)
            db.add(c)
            await db.commit()
            return c.id

    async def call(fn, *a, **kw):
        async with pg_orm.session() as db:
            return await fn(*a, admin=await db.get(User, ids.admin), db=db, **kw)

    async def notices(cid=None):
        from app.models.seller_notification import SellerNotification
        async with pg_orm.session() as db:
            q = select(SellerNotification).order_by(SellerNotification.id)
            if cid is not None:
                q = q.where(SellerNotification.channel_id == cid)
            return (await db.execute(q)).scalars().all()

    async def audits(action="channel.notify"):
        from app.models.user import AdminAuditLog
        async with pg_orm.session() as db:
            return (await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action)
                                     .order_by(AdminAuditLog.id))).scalars().all()

    return SimpleNamespace(orm=pg_orm, admin=admin_r, svc=svc, ids=ids, channel=channel, call=call,
                           notices=notices, audits=audits, CS=ChannelStatus)


class Sender:
    def __init__(self, fail=None):
        self.sent = []
        self.fail = fail

    async def __call__(self, chat_id, text, markup):
        if self.fail is not None:
            raise self.fail
        self.sent.append((chat_id, text, markup))


# ── enqueue rules ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enqueue_on_unpublish_remove_delete(env):
    a = await env.channel()
    await env.call(env.admin.unpublish_channel, a, env.admin.ChannelUnpublishRequest(reason="Накрутка"))
    b = await env.channel()
    await env.call(env.admin.remove_channel_from_market, b, env.admin.ChannelRemoveRequest(confirm=True, reason="Неактивний"))
    c = await env.channel(status=env.CS.pending)
    await env.call(env.admin.admin_delete_channel, c)
    await env.call(env.admin.admin_delete_channel, c)  # already removed → no second notice
    got = [(n.channel_id, n.kind, n.payload, n.user_id) for n in await env.notices()]
    assert got == [
        (a, "unpublish", {"reason": "Накрутка"}, env.ids.seller),
        (b, "remove", {"reason": "Неактивний"}, env.ids.seller),
        (c, "delete", {"reason": "Видалено адміністратором"}, env.ids.seller),
    ]
    assert all(n.sent_at is None and n.failed_at is None and n.attempts == 0 for n in await env.notices())


@pytest.mark.asyncio
async def test_enqueue_rolls_back_with_failed_action(env):
    sold = await env.channel(status=env.CS.sold)
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await env.call(env.admin.admin_delete_channel, sold)
    assert await env.notices() == []


@pytest.mark.asyncio
async def test_buyer_warning_set_and_change_only(env):
    cid = await env.channel()
    W = env.admin.BuyerWarningRequest
    await env.call(env.admin.set_buyer_warning, cid, W(buyer_warning="Боти в аудиторії"))
    await env.call(env.admin.set_buyer_warning, cid, W(buyer_warning="  Боти в аудиторії  "))  # unchanged
    await env.call(env.admin.set_buyer_warning, cid, W(buyer_warning="Інший текст"))           # changed
    await env.call(env.admin.set_buyer_warning, cid, W(buyer_warning=""))                      # cleared
    await env.call(env.admin.set_buyer_warning, cid, W(buyer_warning=None))                    # still clear
    got = [(n.kind, n.payload) for n in await env.notices(cid)]
    assert got == [("buyer_warning", {"warning": "Боти в аудиторії"}),
                   ("buyer_warning", {"warning": "Інший текст"})]


# ── delivery ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_success_text_escaped_button_and_audit(env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "frontend_url", "https://tgsell.me")
    cid = await env.channel(channel_name="<b>Мій</b> & канал")
    await env.call(env.admin.unpublish_channel, cid, env.admin.ChannelUnpublishRequest(reason="ціна <script>x</script>"))
    snd = Sender()
    st = await env.svc.process_due(env.orm.session, send=snd)
    assert st["sent"] == 1
    chat_id, text, markup = snd.sent[0]
    assert chat_id == 71012
    assert "⛔️ <b>Ваш лот знято з публікації</b>\n" in text
    assert f"📡 «&lt;b&gt;Мій&lt;/b&gt; &amp; канал» (#{cid})" in text
    assert "Причина: ціна &lt;script&gt;x&lt;/script&gt;" in text
    assert "<script>" not in text and "@tgsell_support_bot" in text
    btn = markup.inline_keyboard[0][0]
    assert btn.text == "Відкрити кабінет" and btn.url == "https://tgsell.me/cabinet"
    [n] = await env.notices(cid)
    assert n.sent_at is not None and n.failed_at is None and n.attempts == 1
    [a] = await env.audits()
    assert a.target_id == cid and a.details["kind"] == "unpublish" and a.details["result"] == "sent"
    assert "seller_handle" not in str(a.details) and "71012" not in str(a.details)
    # processed rows are never sent again
    assert (await env.svc.process_due(env.orm.session, send=snd))["sent"] == 0
    assert len(snd.sent) == 1


@pytest.mark.asyncio
async def test_buyer_warning_text_has_no_button(env):
    cid = await env.channel(channel_name="K")
    await env.call(env.admin.set_buyer_warning, cid, env.admin.BuyerWarningRequest(buyer_warning="a < b"))
    snd = Sender()
    await env.svc.process_due(env.orm.session, send=snd)
    _, text, markup = snd.sent[0]
    assert text.startswith("⚠️ <b>На вашому лоті з'явилося попередження для покупців</b>\n")
    assert "Текст: a &lt; b" in text and markup is None


@pytest.mark.asyncio
async def test_permanent_error_and_no_telegram_fail_without_retry(env):
    a = await env.channel()
    await env.call(env.admin.unpublish_channel, a, env.admin.ChannelUnpublishRequest(reason="x x x"))
    b = await env.channel(seller_id=env.ids.notg)
    await env.call(env.admin.unpublish_channel, b, env.admin.ChannelUnpublishRequest(reason="y y y"))
    snd = Sender(fail=TelegramForbiddenError("Forbidden: bot was blocked by the user"))
    st = await env.svc.process_due(env.orm.session, send=snd)
    assert st["failed"] == 2
    na, nb = await env.notices()
    assert na.failed_at is not None and "TelegramForbiddenError" in na.last_error
    assert nb.failed_at is not None and nb.last_error == "no_telegram" and nb.attempts == 1
    results = sorted(x.details["result"] for x in await env.audits())
    assert results == ["no_telegram", "permanent_error"]
    later = utcnow_naive() + timedelta(hours=1)
    assert sum((await env.svc.process_due(env.orm.session, now=later, send=Sender())).values()) == 0


@pytest.mark.asyncio
async def test_transient_backoff_then_success(env):
    cid = await env.channel()
    await env.call(env.admin.remove_channel_from_market, cid, env.admin.ChannelRemoveRequest(confirm=True, reason="r"))
    t0 = utcnow_naive()
    bad = Sender(fail=TelegramNetworkError("timeout"))
    assert (await env.svc.process_due(env.orm.session, now=t0, send=bad))["retry"] == 1
    [n] = await env.notices()
    assert n.failed_at is None and n.sent_at is None and n.attempts == 1 and n.next_attempt_at > t0
    # not due yet → nothing happens
    assert sum((await env.svc.process_due(env.orm.session, now=t0 + timedelta(seconds=30), send=bad)).values()) == 0
    assert (await env.svc.process_due(env.orm.session, now=t0 + timedelta(minutes=2), send=bad))["retry"] == 1
    ok = Sender()
    assert (await env.svc.process_due(env.orm.session, now=t0 + timedelta(minutes=10), send=ok))["sent"] == 1
    [n] = await env.notices()
    assert n.sent_at is not None and n.attempts == 3 and n.last_error is None
    assert [x.details["result"] for x in await env.audits()] == ["sent"]  # no audit spam for retries


@pytest.mark.asyncio
async def test_24h_cutoff_marks_failed(env):
    cid = await env.channel()
    await env.call(env.admin.remove_channel_from_market, cid, env.admin.ChannelRemoveRequest(confirm=True, reason="r"))
    bad = Sender(fail=TelegramNetworkError("timeout"))
    t = utcnow_naive()
    for _ in range(40):
        await env.svc.process_due(env.orm.session, now=t, send=bad)
        [n] = await env.notices()
        if n.failed_at is not None:
            break
        t = n.next_attempt_at + timedelta(seconds=1)
    assert n.failed_at is not None and n.sent_at is None
    assert n.failed_at - n.created_at <= timedelta(hours=24, minutes=5)
    assert [x.details["result"] for x in await env.audits()] == ["expired"]
    # a row that was due but is already older than 24h is not sent
    cid2 = await env.channel()
    await env.call(env.admin.remove_channel_from_market, cid2, env.admin.ChannelRemoveRequest(confirm=True, reason="r"))
    ok = Sender()
    st = await env.svc.process_due(env.orm.session, now=utcnow_naive() + timedelta(hours=25), send=ok)
    assert st["failed"] == 1 and ok.sent == []


@pytest.mark.asyncio
async def test_obsolete_after_republish_or_warning_change(env):
    a = await env.channel()
    await env.call(env.admin.unpublish_channel, a, env.admin.ChannelUnpublishRequest(reason="ой ой"))
    await env.call(env.admin.republish_channel, a)  # undone before delivery
    b = await env.channel()
    W = env.admin.BuyerWarningRequest
    await env.call(env.admin.set_buyer_warning, b, W(buyer_warning="перше"))
    await env.call(env.admin.set_buyer_warning, b, W(buyer_warning="друге"))
    snd = Sender()
    st = await env.svc.process_due(env.orm.session, send=snd)
    assert st == {"sent": 1, "failed": 0, "retry": 0, "obsolete": 2}
    assert len(snd.sent) == 1 and "Текст: друге" in snd.sent[0][1]


@pytest.mark.asyncio
async def test_no_double_send_with_concurrent_loops(env):
    for _ in range(5):
        cid = await env.channel()
        await env.call(env.admin.set_buyer_warning, cid, env.admin.BuyerWarningRequest(buyer_warning="w"))
    calls = []

    async def slow_send(chat_id, text, markup):
        await asyncio.sleep(0.05)
        calls.append(text)

    r1, r2 = await asyncio.gather(env.svc.process_due(env.orm.session, send=slow_send),
                                  env.svc.process_due(env.orm.session, send=slow_send))
    assert r1["sent"] + r2["sent"] == 5 and len(calls) == 5
    assert all(n.sent_at is not None and n.attempts == 1 for n in await env.notices())


@pytest.mark.asyncio
async def test_not_configured_bot_leaves_rows_untouched(env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "bot_token_alerts", "")
    cid = await env.channel()
    await env.call(env.admin.set_buyer_warning, cid, env.admin.BuyerWarningRequest(buyer_warning="w"))
    assert sum((await env.svc.process_due(env.orm.session)).values()) == 0
    [n] = await env.notices()
    assert n.attempts == 0 and n.sent_at is None and n.failed_at is None


# ── cabinet: takedown reason only for the owner / staff ────────────────

@pytest.mark.asyncio
async def test_takedown_reason_owner_only(env, monkeypatch):
    from fastapi import FastAPI, HTTPException
    from app.models.user import User

    db_mod = importlib.import_module("app.database")
    monkeypatch.setattr(db_mod, "async_session", env.orm.session)
    sec = importlib.import_module("app.utils.security")
    channels = importlib.import_module("app.routers.channels")
    app = FastAPI()
    app.include_router(channels.router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = env.orm.get_db
    cur = SimpleNamespace(user=None)

    async def optional():
        return cur.user

    async def current():
        if cur.user is None:
            raise HTTPException(status_code=401)
        return cur.user
    app.dependency_overrides[sec.get_optional_user] = optional
    app.dependency_overrides[sec.get_current_user] = current

    rej = await env.channel()
    await env.call(env.admin.unpublish_channel, rej, env.admin.ChannelUnpublishRequest(reason="Секретна причина"))
    rem = await env.channel()
    await env.call(env.admin.remove_channel_from_market, rem, env.admin.ChannelRemoveRequest(confirm=True, reason="Неактивний канал"))
    live = await env.channel()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
        async with env.orm.session() as db:
            cur.user = await db.get(User, env.ids.seller)
        r = await cl.get("/api/channels", params={"seller_id": env.ids.seller, "limit": 50})
        assert r.status_code == 200
        by_id = {c["id"]: c for c in r.json()["items"]}
        assert by_id[rej]["takedown_reason"] == "Секретна причина" and by_id[rej]["takedown_at"]
        assert by_id[rem]["takedown_reason"] == "Неактивний канал"
        assert "takedown_reason" not in by_id[live]

        cur.user = None  # anonymous: unpublished lots hidden, no reason anywhere
        r = await cl.get("/api/channels", params={"seller_id": env.ids.seller, "limit": 50})
        assert "Секретна причина" not in r.text and "takedown_reason" not in r.text
        async with env.orm.session() as db:
            cur.user = await db.get(User, env.ids.notg)  # another user
        r = await cl.get("/api/channels", params={"seller_id": env.ids.seller, "limit": 50})
        assert "Секретна причина" not in r.text and "Неактивний канал" not in r.text


# ── migration 0067 up / down on real Postgres ──────────────────────────

def _alembic(url: str, *args: str) -> None:
    proc = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND_ROOT,
                          env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]


def test_migration_0067_up_down(db_url):
    import asyncpg
    from sqlalchemy.engine import make_url

    url, kind = db_url
    if kind != "postgres":
        pytest.skip("!!! REAL POSTGRES UNAVAILABLE — migration test skipped !!!")
    base = make_url(url)
    dbname = f"mig_{uuid.uuid4().hex[:10]}"

    def dsn(db):
        return base.set(drivername="postgresql", database=db).render_as_string(hide_password=False)

    async def run(db, sql, fetch=False):
        conn = await asyncpg.connect(dsn(db))
        try:
            return await (conn.fetch(sql) if fetch else conn.execute(sql))
        finally:
            await conn.close()

    try:
        asyncio.run(run(base.database or "postgres", f'CREATE DATABASE "{dbname}"'))
    except Exception as e:
        pytest.skip(f"cannot create scratch database: {e}")
    target = unquote(base.set(database=dbname).render_as_string(hide_password=False))
    exists = "SELECT to_regclass('public.seller_notifications') AS t"
    try:
        # A fresh chain can't run in one transaction (0047 uses an enum value added earlier
        # in the same run), so stop once before it — prod upgrades incrementally anyway.
        _alembic(target, "upgrade", "0046")
        _alembic(target, "upgrade", "0066")
        assert asyncio.run(run(dbname, exists, fetch=True))[0]["t"] is None
        _alembic(target, "upgrade", "head")
        assert asyncio.run(run(dbname, exists, fetch=True))[0]["t"] == "seller_notifications"
        cols = {r["column_name"] for r in asyncio.run(run(dbname,
                "SELECT column_name FROM information_schema.columns WHERE table_name='seller_notifications'", fetch=True))}
        assert cols == {"id", "user_id", "channel_id", "kind", "payload", "created_at", "sent_at", "failed_at",
                        "attempts", "last_error", "next_attempt_at"}
        _alembic(target, "downgrade", "0066")
        assert asyncio.run(run(dbname, exists, fetch=True))[0]["t"] is None
        _alembic(target, "upgrade", "head")
    finally:
        asyncio.run(run(base.database or "postgres", f'DROP DATABASE IF EXISTS "{dbname}"'))
