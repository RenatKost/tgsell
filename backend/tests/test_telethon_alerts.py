"""Telethon session death alerts: event-driven down/recovery + startup suppress."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _install_db_stub() -> None:
    if "app.database" in sys.modules:
        return
    stub = ModuleType("app.database")

    class Base:  # noqa: D401
        pass

    stub.Base = Base
    stub.async_session = None
    stub.get_db = None
    sys.modules["app.database"] = stub


_install_db_stub()

from app.services import alerts as alerts_mod  # noqa: E402
from app.services import channel_stats as cs  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_alert_and_telethon_state():
    """Isolate module globals between tests."""
    alerts_mod.reset_telethon_alert_state()
    alerts_mod._last_alerts.clear()

    cs._telethon_client = None
    cs._telethon_was_ok = False
    cs._telethon_retries = 0
    cs._startup_connect_allowed = False
    cs._authkey_duplicated = False
    cs._telethon_status = "waiting"
    cs._telethon_status_detail = None
    cs._intentional_disconnect = False
    if cs._disconnect_watch_task is not None and not cs._disconnect_watch_task.done():
        cs._disconnect_watch_task.cancel()
    cs._disconnect_watch_task = None
    yield
    alerts_mod.reset_telethon_alert_state()
    if cs._disconnect_watch_task is not None and not cs._disconnect_watch_task.done():
        cs._disconnect_watch_task.cancel()
    cs._disconnect_watch_task = None


# ── alerts.py state machine ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_telethon_down_then_recovered_once():
    """ok→down→ok: one down alert, one recovered; second down after recover works."""
    sent: list[str] = []

    async def fake_send(text, alert_key=None, throttle_minutes=30):
        sent.append(text)
        return True

    with patch.object(alerts_mod, "send_admin_alert", side_effect=fake_send):
        assert alerts_mod.telethon_down_alerted() is False

        ok1 = await alerts_mod.alert_telethon_session_down("authkey_duplicated", "dup")
        assert ok1 is True
        assert alerts_mod.telethon_down_alerted() is True
        assert len(sent) == 1
        assert "НЕ ПРАЦЮЄ" in sent[0]
        assert "authkey_duplicated" in sent[0]
        assert "Адмінка → Telethon сесія" in sent[0]
        assert "анульовано" in sent[0] or "AuthKeyDuplicated" in sent[0]

        # Dedup: second down suppressed
        ok2 = await alerts_mod.alert_telethon_session_down("disconnect", "again")
        assert ok2 is False
        assert len(sent) == 1

        # Recovery
        rec = await alerts_mod.alert_telethon_session_recovered()
        assert rec is True
        assert alerts_mod.telethon_down_alerted() is False
        assert len(sent) == 2
        assert "відновлено" in sent[1]
        assert "🟢" in sent[1]

        # Second recovery is no-op
        rec2 = await alerts_mod.alert_telethon_session_recovered()
        assert rec2 is False
        assert len(sent) == 2

        # New down after recovery
        ok3 = await alerts_mod.alert_telethon_session_down("unauthorized")
        assert ok3 is True
        assert len(sent) == 3
        assert "unauthorized" in sent[2]


@pytest.mark.asyncio
async def test_recovered_without_prior_down_is_noop():
    sent: list[str] = []

    async def fake_send(text, alert_key=None, throttle_minutes=30):
        sent.append(text)
        return True

    with patch.object(alerts_mod, "send_admin_alert", side_effect=fake_send):
        assert await alerts_mod.alert_telethon_session_recovered() is False
        assert sent == []


@pytest.mark.asyncio
async def test_first_down_does_not_use_time_throttle():
    """First down signal must not wait for the 30‑min send_admin_alert throttle."""
    calls = []

    async def fake_send(text, alert_key=None, throttle_minutes=30):
        calls.append({"alert_key": alert_key, "throttle_minutes": throttle_minutes})
        return True

    with patch.object(alerts_mod, "send_admin_alert", side_effect=fake_send):
        await alerts_mod.alert_telethon_session_down("connect_failed", "boom")
        assert calls[0]["alert_key"] is None  # no time throttle key


# ── channel_stats suppress + event hooks ───────────────────────────────


@pytest.mark.asyncio
async def test_no_alerts_during_startup_delay():
    """While waiting / startup not allowed — down notify is suppressed."""
    cs._startup_connect_allowed = False
    cs._telethon_status = "waiting"

    with patch.object(
        alerts_mod, "alert_telethon_session_down", new_callable=AsyncMock
    ) as mock_down:
        await cs._notify_telethon_down("disconnect", "should not fire")
        mock_down.assert_not_awaited()

    cs._startup_connect_allowed = True
    cs._telethon_status = "connecting"
    with patch.object(
        alerts_mod, "alert_telethon_session_down", new_callable=AsyncMock
    ) as mock_down:
        await cs._notify_telethon_down("connect_failed", "still connecting")
        mock_down.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_fires_when_failed_after_startup():
    cs._startup_connect_allowed = True
    cs._telethon_status = "failed"

    with patch.object(
        alerts_mod, "alert_telethon_session_down", new_callable=AsyncMock
    ) as mock_down:
        await cs._notify_telethon_down("authkey_duplicated", "dup")
        mock_down.assert_awaited_once_with("authkey_duplicated", "dup")


@pytest.mark.asyncio
async def test_ok_down_ok_via_channel_stats_notify():
    """Simulate connected → down → recovered through channel_stats helpers."""
    sent: list[str] = []

    async def fake_send(text, alert_key=None, throttle_minutes=30):
        sent.append(text)
        return True

    cs._startup_connect_allowed = True
    cs._telethon_status = "failed"

    with patch.object(alerts_mod, "send_admin_alert", side_effect=fake_send):
        await cs._notify_telethon_down("disconnect", "gone")
        assert len(sent) == 1
        assert "disconnect" in sent[0]

        # Dedup
        await cs._notify_telethon_down("disconnect", "gone again")
        assert len(sent) == 1

        cs._telethon_status = "connected"
        await cs._notify_telethon_recovered()
        assert len(sent) == 2
        assert "відновлено" in sent[1]


@pytest.mark.asyncio
async def test_get_telethon_health_keeps_authkey_field():
    cs._telethon_status = "authkey_duplicated"
    cs._authkey_duplicated = True
    cs._startup_connect_allowed = True
    h = cs.get_telethon_health()
    assert h["authkey_duplicated"] is True
    assert h["ok"] is False
    assert h["status"] == "authkey_duplicated"
    assert "startup_delay_sec" in h


@pytest.mark.asyncio
async def test_disconnect_watcher_fires_mid_session_alert():
    """When client.disconnected resolves while status=connected → down alert."""
    cs._startup_connect_allowed = True
    cs._telethon_status = "connected"
    cs._telethon_was_ok = True
    cs._intentional_disconnect = False

    loop = asyncio.get_event_loop()
    disconnected = loop.create_future()

    client = MagicMock()
    client.disconnected = disconnected
    cs._telethon_client = client

    with patch.object(
        alerts_mod, "alert_telethon_session_down", new_callable=AsyncMock
    ) as mock_down:
        cs._attach_disconnect_watcher(client)
        disconnected.set_result(None)
        # Let the watcher run
        await asyncio.sleep(0.05)
        mock_down.assert_awaited()
        assert mock_down.await_args.args[0] == "disconnect"
        assert cs._telethon_status == "failed"
        assert cs._telethon_client is None


@pytest.mark.asyncio
async def test_intentional_shutdown_disconnect_no_alert():
    cs._startup_connect_allowed = True
    cs._telethon_status = "connected"
    cs._intentional_disconnect = True

    loop = asyncio.get_event_loop()
    disconnected = loop.create_future()
    client = MagicMock()
    client.disconnected = disconnected
    cs._telethon_client = client

    with patch.object(
        alerts_mod, "alert_telethon_session_down", new_callable=AsyncMock
    ) as mock_down:
        cs._attach_disconnect_watcher(client)
        disconnected.set_result(None)
        await asyncio.sleep(0.05)
        mock_down.assert_not_awaited()


@pytest.mark.asyncio
async def test_health_monitor_skips_waiting():
    from app.tasks import health_monitor as hm

    hm._prev_telethon_ok = None
    cs._telethon_status = "waiting"
    cs._startup_connect_allowed = False

    with patch.object(
        alerts_mod, "alert_telethon_session_down", new_callable=AsyncMock
    ) as mock_down, patch.object(
        alerts_mod, "alert_telethon_session_recovered", new_callable=AsyncMock
    ) as mock_up:
        ok = await hm._check_telethon()
        assert ok is False
        mock_down.assert_not_awaited()
        mock_up.assert_not_awaited()
