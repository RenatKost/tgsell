"""Regression: aware datetimes must never be written into naive DateTime columns.

Most columns are ``DateTime`` (TIMESTAMP WITHOUT TIME ZONE, naive UTC). asyncpg
raises ``DataError: can't subtract offset-naive and offset-aware datetimes`` when
an aware ``datetime`` is bound to such a column — this crashed the support bot
(``support_messages.handled_at``) and the view tracker (``ChannelPost.date`` cutoff).

DB backend, in order of preference:
  1. ``TEST_DATABASE_URL`` (``postgresql+asyncpg://...``) — real Postgres;
  2. a throwaway Postgres cluster spawned via ``initdb``/``pg_ctl`` if found on
     PATH or under /usr/lib/postgresql/*/bin (non-root only);
  3. SQLite (aiosqlite) + a strict guard that emulates asyncpg by rejecting any
     aware datetime bound as a statement parameter.
"""
from __future__ import annotations

import glob
import importlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import event, select, text as sa_text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import DeclarativeBase  # noqa: E402

from app.utils.timeutil import to_naive_utc, utcnow_naive  # noqa: E402

SUPPORT_SECRET = "test-support-secret"


# ── Helpers (pure) ─────────────────────────────────────────────────────

def test_utcnow_naive_is_naive_utc():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    value = utcnow_naive()
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert value.tzinfo is None
    assert before <= value <= after


def test_to_naive_utc():
    assert to_naive_utc(None) is None
    naive = datetime(2026, 10, 6, 12, 0, 0)
    assert to_naive_utc(naive) is naive
    kyiv = timezone(timedelta(hours=3))
    aware = datetime(2026, 10, 6, 15, 0, 0, tzinfo=kyiv)
    out = to_naive_utc(aware)
    assert out.tzinfo is None
    assert out == datetime(2026, 10, 6, 12, 0, 0)


# ── DB backend selection ───────────────────────────────────────────────

def _find_pg_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted(glob.glob(f"/usr/lib/postgresql/*/bin/{name}"), reverse=True)
    return candidates[0] if candidates else None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def db_url():
    """Yield (async_url, kind) where kind is 'postgres' or 'sqlite'."""
    env_url = os.environ.get("TEST_DATABASE_URL")
    if env_url:
        yield env_url, "postgres"
        return

    initdb, pg_ctl = _find_pg_bin("initdb"), _find_pg_bin("pg_ctl")
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    if initdb and pg_ctl and not is_root:
        tmp = tempfile.mkdtemp(prefix="tgsell_pg_")
        data_dir = os.path.join(tmp, "data")
        port = _free_port()
        started = False
        try:
            subprocess.run(
                [initdb, "-D", data_dir, "-U", "tgsell_test", "--auth=trust", "-E", "UTF8"],
                check=True, capture_output=True, timeout=120,
            )
            subprocess.run(
                [pg_ctl, "-D", data_dir, "-w", "-t", "60", "-l", os.path.join(tmp, "pg.log"),
                 "-o", f"-p {port} -k {tmp} -c listen_addresses='' -c timezone=UTC -c fsync=off",
                 "start"],
                check=True, capture_output=True, timeout=120,
            )
            started = True
        except Exception:  # pragma: no cover - environment dependent
            started = False
        if started:
            try:
                yield f"postgresql+asyncpg://tgsell_test@/postgres?host={tmp}&port={port}", "postgres"
            finally:
                subprocess.run([pg_ctl, "-D", data_dir, "-m", "immediate", "stop"],
                               capture_output=True, timeout=60)
                shutil.rmtree(tmp, ignore_errors=True)
            return
        shutil.rmtree(tmp, ignore_errors=True)

    pytest.importorskip("aiosqlite")
    yield "sqlite+aiosqlite:///:memory:", "sqlite"


def _contains_aware_datetime(params) -> bool:
    if params is None:
        return False
    if isinstance(params, datetime):
        return params.tzinfo is not None
    if isinstance(params, dict):
        return any(_contains_aware_datetime(v) for v in params.values())
    if isinstance(params, (list, tuple)):
        return any(_contains_aware_datetime(v) for v in params)
    return False


class AwareDatetimeBound(Exception):
    """SQLite-mode emulation of asyncpg's refusal to bind aware → naive."""


def _install_strict_guard(engine) -> None:
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _guard(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        # SQLite's DateTime bind processor stringifies values before the cursor sees
        # them, so inspect the raw (pre-processing) compiled parameters instead.
        raw = getattr(context, "compiled_parameters", None) if context is not None else None
        if _contains_aware_datetime(raw) or _contains_aware_datetime(parameters):
            raise AwareDatetimeBound(f"aware datetime bound in: {statement[:120]}")


# ── Real ORM wiring (isolated from the app.database stub other tests use) ──

_ISOLATED_PREFIXES = ("app.database", "app.models", "app.routers.support", "bot.support",
                      "app.tasks.stats_collector")


@pytest_asyncio.fixture
async def orm(db_url):
    """Fresh real-Base models + engine bound to the test DB.

    Other test modules stub ``app.database`` with a plain ``Base`` (no mapping),
    so we temporarily swap in a real DeclarativeBase module, re-import models /
    the modules under test, and restore ``sys.modules`` afterwards.
    """
    url, kind = db_url
    snapshot = {k: v for k, v in sys.modules.items() if k.startswith(("app.", "bot."))}
    for key in list(sys.modules):
        if key.startswith(_ISOLATED_PREFIXES):
            del sys.modules[key]

    engine_kwargs = {}
    if kind == "sqlite":
        from sqlalchemy.pool import StaticPool

        engine_kwargs = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
    else:
        from sqlalchemy.pool import NullPool

        engine_kwargs = {"poolclass": NullPool}
    engine = create_async_engine(url, **engine_kwargs)
    if kind == "sqlite":
        _install_strict_guard(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    class Base(DeclarativeBase):
        pass

    async def get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    db_mod = ModuleType("app.database")
    db_mod.Base = Base
    db_mod.engine = engine
    db_mod.async_session = session_factory
    db_mod.get_db = get_db
    sys.modules["app.database"] = db_mod

    try:
        for path in sorted((BACKEND_ROOT / "app" / "models").glob("*.py")):
            if path.stem != "__init__":
                importlib.import_module(f"app.models.{path.stem}")

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        yield SimpleNamespace(kind=kind, engine=engine, session=session_factory, get_db=get_db)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    finally:
        await engine.dispose()
        for key in list(sys.modules):
            if key.startswith(("app.", "bot.")) and key not in snapshot:
                del sys.modules[key]
        sys.modules.update(snapshot)


def _strict_errors():
    from sqlalchemy.exc import DBAPIError, StatementError

    return (AwareDatetimeBound, DBAPIError, StatementError)


@pytest.mark.asyncio
async def test_backend_rejects_aware_datetime_in_naive_column(orm):
    """Sanity: the test DB is as strict as production asyncpg (else the cycle test proves nothing)."""
    from app.models.support import SupportMessage

    async with orm.session() as db:
        db.add(SupportMessage(
            telegram_user_id=1, chat_id=1, direction="in", text="x",
            handled=True, handled_at=datetime.now(timezone.utc),
        ))
        with pytest.raises(_strict_errors()):
            await db.commit()


# ── Support: full cycle ────────────────────────────────────────────────

class _FakeBot:
    sent: list[tuple[int, str]] = []

    def __init__(self, token: str, **_kwargs):
        self.token = token
        self.session = SimpleNamespace(close=AsyncMock())

    async def send_message(self, chat_id, text, **_kwargs):
        _FakeBot.sent.append((chat_id, text))


def _fake_message(user_id: int, chat_id: int, text: str):
    media = dict.fromkeys(
        ["photo", "document", "video", "voice", "audio", "sticker",
         "animation", "video_note", "contact", "location"]
    )
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, username="buyer", first_name="Ivan"),
        chat=SimpleNamespace(id=chat_id, type="private"),
        text=text,
        caption=None,
        answer=AsyncMock(),
        **media,
    )


def _assert_naive_recent(value: datetime | None) -> None:
    assert value is not None
    assert value.tzinfo is None, f"naive column holds aware value: {value!r}"
    now = utcnow_naive()
    assert now - timedelta(minutes=5) <= value <= now + timedelta(minutes=1), value


@pytest.mark.asyncio
async def test_support_full_cycle_incoming_reply_handled(orm, monkeypatch):
    import aiogram
    import httpx
    from fastapi import FastAPI

    from app.config import settings
    from app.models.support import SupportMessage

    bot_support = importlib.import_module("bot.support")
    support_router = importlib.import_module("app.routers.support")

    monkeypatch.setattr(settings, "support_queue_secret", SUPPORT_SECRET)
    monkeypatch.setattr(settings, "bot_token_support", "123:TEST")
    monkeypatch.setattr(aiogram, "Bot", _FakeBot)
    _FakeBot.sent = []
    bot_support._last_urgent_alert.clear()

    user_id, chat_id = 777001, 777001

    # 1) Incoming DM → stored as 'in' + auto-reply stored as 'out' (handled=True → handled_at written)
    msg = _fake_message(user_id, chat_id, "як додати канал?")
    await bot_support.support_private_message(msg)
    msg.answer.assert_awaited_once()

    async with orm.session() as db:
        rows = (await db.execute(
            select(SupportMessage).where(SupportMessage.telegram_user_id == user_id)
            .order_by(SupportMessage.id)
        )).scalars().all()
    assert [r.direction for r in rows] == ["in", "out"]
    incoming, auto_reply = rows
    assert incoming.handled is False and incoming.handled_at is None
    assert auto_reply.handled is True
    _assert_naive_recent(auto_reply.handled_at)

    app = FastAPI()
    app.include_router(support_router.router, prefix="/api")
    app.dependency_overrides[support_router.get_db] = orm.get_db
    headers = {"x-support-secret": SUPPORT_SECRET}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # auth is enforced
        r = await client.get("/api/support/queue", headers={"x-support-secret": "wrong"})
        assert r.status_code == 401

        r = await client.get("/api/support/queue", headers=headers)
        assert r.status_code == 200
        assert [m["id"] for m in r.json()["messages"]] == [incoming.id]

        # 2) Admin reply
        r = await client.post(
            "/api/support/reply",
            headers=headers,
            json={"telegram_user_id": user_id, "text": "Відповідь підтримки", "reply_to_id": incoming.id},
        )
        assert r.status_code == 200, r.text
        out = r.json()["message"]
        assert out["direction"] == "out" and out["handled"] is True
        assert out["handled_at"] is not None
        assert _FakeBot.sent == [(chat_id, "Відповідь підтримки")]

        # 3) Another incoming message, then explicit /handled
        await bot_support.support_private_message(_fake_message(user_id, chat_id, "ще питання"))
        async with orm.session() as db:
            second_in = (await db.execute(
                select(SupportMessage).where(
                    SupportMessage.telegram_user_id == user_id,
                    SupportMessage.direction == "in",
                    SupportMessage.handled.is_(False),
                )
            )).scalar_one()

        r = await client.post("/api/support/handled", headers=headers, json={"ids": [second_in.id]})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "updated": 1}

        r = await client.get("/api/support/queue", headers=headers)
        assert r.status_code == 200
        assert r.json()["messages"] == []

    async with orm.session() as db:
        rows = (await db.execute(
            select(SupportMessage).where(SupportMessage.telegram_user_id == user_id)
        )).scalars().all()
    assert rows and all(r.handled for r in rows)
    for r in rows:
        _assert_naive_recent(r.handled_at)

    if orm.kind == "postgres":
        async with orm.engine.connect() as conn:
            col_type = (await conn.execute(sa_text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='support_messages' AND column_name='handled_at'"
            ))).scalar_one()
        assert col_type == "timestamp without time zone"


# ── View tracker: naive cutoff for ChannelPost.date ─────────────────────

@pytest.mark.asyncio
async def test_update_post_views_once_uses_naive_cutoff(orm, monkeypatch):
    from app.models.channel import Channel, ChannelPost, ChannelStatus
    from app.models.user import User
    from app.services import channel_stats as cs

    stats_collector = importlib.import_module("app.tasks.stats_collector")

    post_date = utcnow_naive() - timedelta(hours=13)
    async with orm.session() as db:
        user = User(first_name="Seller")
        db.add(user)
        await db.flush()
        channel = Channel(
            seller_id=user.id, telegram_link="https://t.me/test_channel", channel_name="Test",
            category="news", price=10.0, status=ChannelStatus.approved, is_closed=False,
        )
        db.add(channel)
        await db.flush()
        db.add(ChannelPost(channel_id=channel.id, telegram_msg_id=101, date=post_date, views=10))
        await db.commit()
        channel_id = channel.id

    fake_client = SimpleNamespace(
        get_entity=AsyncMock(return_value=SimpleNamespace(id=1)),
        get_messages=AsyncMock(return_value=[
            SimpleNamespace(id=101, views=555, forwards=7, reactions=None),
        ]),
    )
    monkeypatch.setattr(cs, "_get_telethon_client", AsyncMock(return_value=fake_client))
    monkeypatch.setattr(stats_collector.asyncio, "sleep", AsyncMock())

    await stats_collector.update_post_views_once()

    fake_client.get_messages.assert_awaited_once()
    async with orm.session() as db:
        post = (await db.execute(
            select(ChannelPost).where(ChannelPost.channel_id == channel_id)
        )).scalar_one()
    assert post.views == 555
    assert post.forwards == 7
    assert post.views_1h == 555 and post.views_12h == 555
    assert post.views_24h is None
