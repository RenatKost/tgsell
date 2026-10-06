"""Support bot + POST /api/support/reply idempotency — on REAL Postgres (asyncpg).

Covers: /start, incoming message + auto-reply, auto-reply cooldown, /reply with an
idempotency key (retry → Telegram send once), Telegram failure → 'failed' → retry
sends once, 'sending' state is never resent blindly, /handled, and migration 0024
on a database with existing rows. Telegram is always faked.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import subprocess
import sys
import uuid
from urllib.parse import unquote
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select, update  # noqa: E402

from app.utils.timeutil import utcnow_naive  # noqa: E402
from tests.db_harness import SUPPORT_SECRET, _assert_naive_recent, _fake_message  # noqa: E402

HEADERS = {"x-support-secret": SUPPORT_SECRET}
USER_ID = 555001
CHAT_ID = 555001


class TelegramFake:
    """Stands in for aiogram.Bot in the /reply endpoint."""

    def __init__(self):
        self.calls: list[tuple[int, str]] = []
        self.fail_next = 0
        self.delay = 0.0
        self.on_send = None  # optional async hook(chat_id, text)
        self._next_id = 9000

    def bot_class(self):
        fake = self

        class _Bot:
            def __init__(self, token: str, **_kwargs):
                self.session = SimpleNamespace(close=AsyncMock())

            async def send_message(self, chat_id, text, **_kwargs):
                fake.calls.append((chat_id, text))
                if fake.on_send is not None:
                    await fake.on_send(chat_id, text)
                if fake.delay:
                    await asyncio.sleep(fake.delay)
                if fake.fail_next > 0:
                    fake.fail_next -= 1
                    raise RuntimeError("Telegram is down (bot1234567:SECRETTOKENxxxxxxxxxxxxxxxxxxxxxxxxxx)")
                fake._next_id += 1
                return SimpleNamespace(message_id=fake._next_id)

        return _Bot


def _answer_mock():
    counter = iter(range(100, 10_000))
    return AsyncMock(side_effect=lambda *a, **k: SimpleNamespace(message_id=next(counter)))


@pytest_asyncio.fixture
async def env(pg_orm, monkeypatch):
    import aiogram
    import httpx
    from fastapi import FastAPI

    from app.config import settings

    bot_support = importlib.import_module("bot.support")
    support_router = importlib.import_module("app.routers.support")
    from app.models.support import SupportMessage

    monkeypatch.setattr(settings, "support_queue_secret", SUPPORT_SECRET)
    monkeypatch.setattr(settings, "bot_token_support", "123:TEST")
    tg = TelegramFake()
    monkeypatch.setattr(aiogram, "Bot", tg.bot_class())
    bot_support._last_urgent_alert.clear()
    bot_support._last_auto_reply_mem.clear()

    app = FastAPI()
    app.include_router(support_router.router, prefix="/api")
    app.dependency_overrides[support_router.get_db] = pg_orm.get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield SimpleNamespace(
            orm=pg_orm, client=client, tg=tg, bot=bot_support, Msg=SupportMessage,
        )
    bot_support._last_auto_reply_mem.clear()


async def _rows(env, user_id=USER_ID):
    async with env.orm.session() as db:
        return (await db.execute(
            select(env.Msg).where(env.Msg.telegram_user_id == user_id).order_by(env.Msg.id)
        )).scalars().all()


async def _incoming(env, text="як додати канал?", user_id=USER_ID):
    msg = _fake_message(user_id, CHAT_ID, text)
    msg.answer = _answer_mock()
    await env.bot.support_private_message(msg)
    return msg


async def _first_in(env):
    return next(r for r in await _rows(env) if r.direction == "in")


# ── Bot: /start, auto-reply, cooldown ──────────────────────────────────

@pytest.mark.asyncio
async def test_start_saves_incoming_and_welcome(env):
    from app.services.support_logic import WELCOME_TEXT

    msg = _fake_message(USER_ID, CHAT_ID, "/start")
    msg.answer = _answer_mock()
    await env.bot.support_start(msg)

    msg.answer.assert_awaited_once_with(WELCOME_TEXT)
    rows = await _rows(env)
    assert [(r.direction, r.text) for r in rows] == [("in", "/start"), ("out", WELCOME_TEXT)]
    welcome = rows[1]
    assert welcome.handled is True and welcome.delivery_status == "sent"
    assert welcome.telegram_message_id == 100
    _assert_naive_recent(welcome.handled_at)
    _assert_naive_recent(welcome.sent_at)
    _assert_naive_recent(rows[0].created_at)


@pytest.mark.asyncio
async def test_auto_reply_once_then_cooldown(env):
    from app.services.support_logic import AUTO_REPLY_TEXT

    first = await _incoming(env, "перше питання")
    first.answer.assert_awaited_once_with(AUTO_REPLY_TEXT)

    rows = await _rows(env)
    assert [r.direction for r in rows] == ["in", "out"]
    auto = rows[1]
    assert auto.text == AUTO_REPLY_TEXT and auto.delivery_status == "sent"
    _assert_naive_recent(auto.created_at)

    # Within cooldown — DB-based check alone (in-process guard cleared, e.g. after restart)
    env.bot._last_auto_reply_mem.clear()
    second = await _incoming(env, "друге питання")
    second.answer.assert_not_awaited()
    assert [r.direction for r in await _rows(env)] == ["in", "out", "in"]

    # Cooldown elapsed → auto-reply again
    async with env.orm.session() as db:
        await db.execute(
            update(env.Msg).where(env.Msg.id == auto.id)
            .values(created_at=utcnow_naive() - timedelta(minutes=31))
        )
        await db.commit()
    env.bot._last_auto_reply_mem.clear()
    third = await _incoming(env, "третє питання")
    third.answer.assert_awaited_once_with(AUTO_REPLY_TEXT)


@pytest.mark.asyncio
async def test_concurrent_messages_get_single_auto_reply(env):
    a = _fake_message(USER_ID, CHAT_ID, "раз")
    b = _fake_message(USER_ID, CHAT_ID, "два")
    a.answer, b.answer = _answer_mock(), _answer_mock()
    await asyncio.gather(env.bot.support_private_message(a), env.bot.support_private_message(b))
    assert a.answer.await_count + b.answer.await_count == 1
    assert [r.direction for r in await _rows(env)].count("out") == 1


# ── /reply idempotency ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reply_same_key_twice_sends_once(env):
    await _incoming(env)
    incoming = await _first_in(env)
    body = {"telegram_user_id": USER_ID, "text": "Відповідь", "reply_to_id": incoming.id,
            "idempotency_key": "agent-reply-1"}

    r1 = await env.client.post("/api/support/reply", headers=HEADERS, json=body)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    assert j1["ok"] is True and j1["duplicate"] is False and j1["status"] == "sent"
    msg = j1["message"]
    assert msg["delivery_status"] == "sent" and msg["idempotency_key"] == "agent-reply-1"
    assert msg["telegram_message_id"] == 9001 and msg["send_attempts"] == 1

    r2 = await env.client.post("/api/support/reply", headers=HEADERS, json=body)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert j2["duplicate"] is True and j2["message"]["id"] == msg["id"]

    # Same key via the Idempotency-Key header → still a duplicate
    hdr_body = {k: v for k, v in body.items() if k != "idempotency_key"}
    r3 = await env.client.post(
        "/api/support/reply", headers={**HEADERS, "Idempotency-Key": "agent-reply-1"}, json=hdr_body,
    )
    assert r3.status_code == 200 and r3.json()["duplicate"] is True

    assert env.tg.calls == [(CHAT_ID, "Відповідь")]  # Telegram called exactly once
    rows = await _rows(env)
    assert [r.direction for r in rows].count("out") == 2  # auto-reply + one admin reply
    assert all(r.handled for r in rows)
    sent_row = next(r for r in rows if r.idempotency_key == "agent-reply-1")
    _assert_naive_recent(sent_row.sent_at)
    _assert_naive_recent(sent_row.handled_at)


@pytest.mark.asyncio
async def test_reply_body_and_header_key_mismatch_is_400(env):
    await _incoming(env)
    r = await env.client.post(
        "/api/support/reply",
        headers={**HEADERS, "Idempotency-Key": "a"},
        json={"telegram_user_id": USER_ID, "text": "x", "idempotency_key": "b"},
    )
    assert r.status_code == 400
    assert env.tg.calls == []


@pytest.mark.asyncio
async def test_reply_key_reused_for_different_text_is_422(env):
    await _incoming(env)
    base = {"telegram_user_id": USER_ID, "idempotency_key": "k-reuse"}
    assert (await env.client.post("/api/support/reply", headers=HEADERS,
                                  json={**base, "text": "перша"})).status_code == 200
    r = await env.client.post("/api/support/reply", headers=HEADERS, json={**base, "text": "інша"})
    assert r.status_code == 422
    assert r.json()["error"] == "idempotency_key_reused"
    assert len(env.tg.calls) == 1


@pytest.mark.asyncio
async def test_reply_row_is_persisted_as_sending_before_telegram_call(env):
    await _incoming(env)
    seen = {}

    async def on_send(chat_id, text):
        async with env.orm.session() as db:  # separate connection → sees only committed data
            row = (await db.execute(
                select(env.Msg).where(env.Msg.idempotency_key == "k-order")
            )).scalar_one()
        seen["status"] = row.delivery_status

    env.tg.on_send = on_send
    r = await env.client.post("/api/support/reply", headers=HEADERS,
                              json={"telegram_user_id": USER_ID, "text": "t", "idempotency_key": "k-order"})
    assert r.status_code == 200
    assert seen == {"status": "sending"}
    assert r.json()["status"] == "sent"


@pytest.mark.asyncio
async def test_reply_in_sending_state_is_not_resent(env):
    await _incoming(env)
    async with env.orm.session() as db:
        db.add(env.Msg(
            telegram_user_id=USER_ID, chat_id=CHAT_ID, direction="out", text="зависла",
            handled=True, handled_at=utcnow_naive(), delivery_status="sending",
            idempotency_key="k-stuck", send_attempts=1,
        ))
        await db.commit()

    r = await env.client.post("/api/support/reply", headers=HEADERS,
                              json={"telegram_user_id": USER_ID, "text": "зависла", "idempotency_key": "k-stuck"})
    assert r.status_code == 409
    j = r.json()
    assert j["error"] == "reply_in_progress" and j["status"] == "sending"
    assert env.tg.calls == []


@pytest.mark.asyncio
async def test_reply_telegram_failure_marks_failed_and_retry_sends_once(env):
    await _incoming(env)
    incoming = await _first_in(env)
    body = {"telegram_user_id": USER_ID, "text": "Спроба", "idempotency_key": "k-fail"}

    env.tg.fail_next = 1
    r1 = await env.client.post("/api/support/reply", headers=HEADERS, json=body)
    assert r1.status_code == 502
    j1 = r1.json()
    assert j1["detail"] == "Failed to send Telegram message"
    assert j1["error"] == "telegram_send_failed" and j1["status"] == "failed"
    assert "SECRETTOKEN" not in r1.text  # token redacted in last_error
    async with env.orm.session() as db:
        failed = (await db.execute(select(env.Msg).where(env.Msg.idempotency_key == "k-fail"))).scalar_one()
        still_open = (await db.execute(select(env.Msg).where(env.Msg.id == incoming.id))).scalar_one()
    assert failed.delivery_status == "failed" and failed.last_error
    assert still_open.handled is False  # not marked handled when delivery failed

    r2 = await env.client.post("/api/support/reply", headers=HEADERS, json=body)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert j2["duplicate"] is False and j2["status"] == "sent"
    assert j2["message"]["id"] == failed.id and j2["message"]["send_attempts"] == 2
    assert j2["message"]["last_error"] is None

    r3 = await env.client.post("/api/support/reply", headers=HEADERS, json=body)
    assert r3.status_code == 200 and r3.json()["duplicate"] is True

    assert len(env.tg.calls) == 2  # 1 failed attempt + exactly 1 successful resend
    rows = await _rows(env)
    assert [r.direction for r in rows].count("out") == 2  # auto-reply + one admin reply row
    assert all(r.handled for r in rows)


@pytest.mark.asyncio
async def test_concurrent_same_key_sends_once(env):
    await _incoming(env)
    env.tg.delay = 0.2
    body = {"telegram_user_id": USER_ID, "text": "паралельно", "idempotency_key": "k-race"}
    r1, r2 = await asyncio.gather(
        env.client.post("/api/support/reply", headers=HEADERS, json=body),
        env.client.post("/api/support/reply", headers=HEADERS, json=body),
    )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes in ([200, 409], [200, 200]), (r1.text, r2.text)
    assert len(env.tg.calls) == 1


@pytest.mark.asyncio
async def test_reply_without_key_backward_compatible(env):
    await _incoming(env)
    r = await env.client.post("/api/support/reply", headers=HEADERS,
                              json={"telegram_user_id": USER_ID, "text": "без ключа"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True and j["message"]["direction"] == "out"
    assert j["message"]["delivery_status"] == "sent" and j["message"]["idempotency_key"] is None
    assert len(env.tg.calls) == 1

    r404 = await env.client.post("/api/support/reply", headers=HEADERS,
                                 json={"telegram_user_id": 1, "text": "x"})
    assert r404.status_code == 404
    r401 = await env.client.post("/api/support/reply", headers={"x-support-secret": "bad"},
                                 json={"telegram_user_id": USER_ID, "text": "x"})
    assert r401.status_code == 401
    assert len(env.tg.calls) == 1


@pytest.mark.asyncio
async def test_handled_endpoint(env):
    await _incoming(env, "питання")
    incoming = await _first_in(env)
    r = await env.client.post("/api/support/handled", headers=HEADERS, json={"ids": [incoming.id]})
    assert r.status_code == 200 and r.json() == {"ok": True, "updated": 1}
    q = await env.client.get("/api/support/queue", headers=HEADERS)
    assert q.status_code == 200 and q.json()["messages"] == []
    async with env.orm.session() as db:
        row = (await db.execute(select(env.Msg).where(env.Msg.id == incoming.id))).scalar_one()
    _assert_naive_recent(row.handled_at)


# ── Migration 0024 on a database with existing rows ─────────────────────

def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_migration_0024_safe_on_existing_rows(db_url):
    import asyncpg
    from sqlalchemy.engine import make_url

    url, kind = db_url
    if kind != "postgres":
        pytest.skip("!!! REAL POSTGRES UNAVAILABLE — migration test skipped !!!")

    base = make_url(url)
    dbname = f"mig_{uuid.uuid4().hex[:10]}"

    def dsn(db: str) -> str:
        return base.set(drivername="postgresql", database=db).render_as_string(hide_password=False)

    async def admin(sql: str):
        conn = await asyncpg.connect(dsn(base.database or "postgres"))
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    try:
        asyncio.run(admin(f'CREATE DATABASE "{dbname}"'))
    except Exception as e:  # e.g. TEST_DATABASE_URL user without CREATEDB
        pytest.skip(f"cannot create scratch database for migration test: {e}")

    # alembic's configparser chokes on %-escapes (e.g. host=%2Ftmp%2F...) → unquote
    target = unquote(base.set(database=dbname).render_as_string(hide_password=False))
    try:
        _alembic(target, "upgrade", "0023")

        async def seed_and_check():
            conn = await asyncpg.connect(dsn(dbname))
            try:
                await conn.execute(
                    "INSERT INTO support_messages (telegram_user_id, chat_id, direction, text, handled) "
                    "VALUES (1, 1, 'in', 'legacy in', false), (1, 1, 'out', 'legacy out', true)"
                )
            finally:
                await conn.close()

        asyncio.run(seed_and_check())
        _alembic(target, "upgrade", "head")

        async def verify_upgraded():
            conn = await asyncpg.connect(dsn(dbname))
            try:
                rows = await conn.fetch(
                    "SELECT text, delivery_status, idempotency_key, send_attempts, sent_at "
                    "FROM support_messages ORDER BY id"
                )
                assert [r["text"] for r in rows] == ["legacy in", "legacy out"]
                assert all(r["delivery_status"] is None and r["idempotency_key"] is None
                           and r["send_attempts"] == 0 and r["sent_at"] is None for r in rows)
                # many NULL keys allowed, duplicate non-NULL key rejected
                await conn.execute(
                    "INSERT INTO support_messages (telegram_user_id, chat_id, direction, idempotency_key, "
                    "delivery_status) VALUES (2, 2, 'out', 'k1', 'sent')"
                )
                with pytest.raises(asyncpg.UniqueViolationError):
                    await conn.execute(
                        "INSERT INTO support_messages (telegram_user_id, chat_id, direction, idempotency_key) "
                        "VALUES (2, 2, 'out', 'k1')"
                    )
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(
                        "INSERT INTO support_messages (telegram_user_id, chat_id, direction, delivery_status) "
                        "VALUES (2, 2, 'out', 'bogus')"
                    )
            finally:
                await conn.close()

        asyncio.run(verify_upgraded())
        _alembic(target, "downgrade", "0023")
        _alembic(target, "upgrade", "head")
    finally:
        asyncio.run(admin(f'DROP DATABASE IF EXISTS "{dbname}"'))
