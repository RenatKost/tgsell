"""Shared DB test harness (strict naive-datetime checks, real Postgres when possible).

DB backend, in order of preference:
  1. ``TEST_DATABASE_URL`` (``postgresql+asyncpg://...``) — real Postgres;
  2. a throwaway Postgres cluster spawned via ``initdb``/``pg_ctl`` if found on
     PATH or under /usr/lib/postgresql/*/bin (non-root only);
  3. SQLite (aiosqlite) + a strict guard that emulates asyncpg by rejecting any
     aware datetime bound as a statement parameter.

Fixtures (registered in tests/conftest.py):
  * ``db_url``  — (async_url, kind) for the session;
  * ``orm``     — real-Base models + engine bound to the test DB (any backend);
  * ``pg_orm``  — same, but Postgres is REQUIRED (loud skip otherwise).
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
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import DeclarativeBase  # noqa: E402

from app.utils.timeutil import utcnow_naive  # noqa: E402

SUPPORT_SECRET = "test-support-secret"


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


@pytest.fixture(scope="session")
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

_ISOLATED_PREFIXES = (
    # Everything that binds to app.database.Base / async_session at import time.
    "app.database", "app.models", "app.routers", "app.tasks", "bot.",
    "app.services.deal_checklist", "app.services.deal_lifecycle",
    "app.services.payment_deadlines", "app.services.checklist_autoverify",
    "app.utils.security",
)


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
        # Re-sync package attributes (``from app.services import x``) with sys.modules
        for key in [k for k in sys.modules if k.startswith(("app.", "bot."))] + list(_ISOLATED_PREFIXES):
            parent_name, _, child = key.rpartition(".")
            parent = sys.modules.get(parent_name)
            if parent is None:
                continue
            if key in sys.modules:
                setattr(parent, child, sys.modules[key])
            elif hasattr(parent, child):
                delattr(parent, child)


def _strict_errors():
    from sqlalchemy.exc import DBAPIError, StatementError

    return (AwareDatetimeBound, DBAPIError, StatementError)


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


@pytest_asyncio.fixture
async def pg_orm(orm):
    """Like ``orm`` but requires real Postgres (asyncpg strictness, unique/check constraints)."""
    if orm.kind != "postgres":
        msg = (
            "!!! REAL POSTGRES UNAVAILABLE — skipping Postgres-only test. Set TEST_DATABASE_URL "
            "or install PostgreSQL server binaries (initdb/pg_ctl) and run as non-root. !!!"
        )
        warnings.warn(msg)
        pytest.skip(msg)
    return orm
