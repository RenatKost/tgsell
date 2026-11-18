"""Audit 18.11: Telethon ValueError retry, throttling/circuit breaker, polling 5xx,
deduplicated error buffer, Bot API stats failure reason (no DB)."""
import logging
from collections import deque
from unittest.mock import AsyncMock

import pytest

from app.services import stats_retry as sr
from app.services.stats_retry import (
    CIRCUIT_OPEN,
    REQUEST_UNSUCCESSFUL,
    FloodWaitProxy,
    StatsRetryScheduler,
    TelethonCircuitBreaker,
    classify_telethon_stats_error,
    is_retryable_stats_error,
    note_telethon_stats_result,
)


class RpcCallFailError(Exception):
    pass


# ── P0: classification ────────────────────────────────────────────────────

def test_request_unsuccessful_valueerror_is_retryable():
    e = ValueError("Request was unsuccessful 1 time(s)")
    assert is_retryable_stats_error(e)
    info = classify_telethon_stats_error(e)
    assert info["telethon_error"] == REQUEST_UNSUCCESSFUL and info["telethon_retryable"] is True
    assert is_retryable_stats_error(ValueError("Request was unsuccessful 6 time(s)"))
    # other ValueErrors (e.g. "Cannot find any entity") stay non-retryable
    assert not is_retryable_stats_error(ValueError('Cannot find any entity corresponding to "x"'))
    assert not is_retryable_stats_error("ValueError")
    for name in ("RpcCallFailError", "ServerError", "TimedOutError"):
        assert is_retryable_stats_error(name)
    assert is_retryable_stats_error(RpcCallFailError())


def test_valueerror_schedules_5_15_60_retries():
    sched = StatsRetryScheduler()
    prev = sr.scheduler
    sr.scheduler = sched
    try:
        stats = {"daily_stats": [], **classify_telethon_stats_error(ValueError("Request was unsuccessful 1 time(s)"))}
        for expected in (5 * 60, 15 * 60, 60 * 60):
            note_telethon_stats_result(84, stats, now=0)
            assert sched._items[84].next_at == expected
        note_telethon_stats_result(84, stats, now=0)
        assert sched.pending_count() == 0  # max 3 delayed attempts
    finally:
        sr.scheduler = prev


def test_flood_wait_still_honored():
    sched = StatsRetryScheduler()
    item = sched.schedule(99, FloodWaitProxy(3600), now=0)
    assert item.next_at == 3600


# ── P0: circuit breaker / throttling ─────────────────────────────────────

def test_breaker_opens_after_consecutive_failures_and_half_opens():
    b = TelethonCircuitBreaker(threshold=3, cooldown_sec=600)
    err = ValueError("Request was unsuccessful 1 time(s)")
    assert not b.record_failure(err, now=0)
    assert not b.record_failure(err, now=1)
    assert b.record_failure(err, now=2)
    assert b.is_open(now=3) and b.remaining_sec(now=2) == 600
    assert not b.record_failure(err, now=5)  # ignored while open
    assert not b.is_open(now=603)
    assert b.record_failure(err, now=603)  # half-open: one failure re-opens
    assert b.is_open(now=604)
    b2 = TelethonCircuitBreaker(threshold=3, cooldown_sec=600)
    b2.record_failure(err, now=0)
    b2.record_success()
    b2.record_failure(err, now=1)
    b2.record_failure(err, now=2)
    assert not b2.is_open(now=3)  # success reset the streak


def test_breaker_ignores_channel_specific_errors_and_trips_on_floodwait():
    b = TelethonCircuitBreaker(threshold=2, cooldown_sec=600)
    for _ in range(5):
        assert not b.record_failure(ValueError("Cannot find any entity"), now=0)
    assert not b.is_open(now=0)
    assert b.record_failure(FloodWaitProxy(1800), now=0)
    assert b.remaining_sec(now=0) == 1800


def test_circuit_open_defers_without_consuming_attempts():
    sched = StatsRetryScheduler()
    item = sched.defer(7, 600, now=0)
    assert item.delayed_attempt == -1 and item.next_at == 600
    nxt = sched.schedule(7, "RpcCallFailError", now=700)
    assert nxt.delayed_attempt == 0 and nxt.next_at == 700 + 5 * 60
    assert is_retryable_stats_error(CIRCUIT_OPEN)
    assert not TelethonCircuitBreaker(threshold=1).record_failure(CIRCUIT_OPEN, now=0)


def test_throttle_env(monkeypatch):
    monkeypatch.delenv("STATS_CHANNEL_PAUSE_SEC", raising=False)
    assert sr.channel_pause_sec() == 3.0 and sr.batch_size() == 10
    monkeypatch.setenv("STATS_CHANNEL_PAUSE_SEC", "5")
    monkeypatch.setenv("STATS_BATCH_SIZE", "4")
    assert sr.channel_pause_sec() == 5.0 and sr.batch_size() == 4
    monkeypatch.setenv("STATS_CHANNEL_PAUSE_SEC", "oops")
    assert sr.channel_pause_sec() == 3.0
    monkeypatch.setenv("STATS_CHANNEL_PAUSE_SEC", "9999")
    assert sr.channel_pause_sec() == 60.0


@pytest.mark.asyncio
async def test_pass_pauses_after_every_channel_and_breaker_stops_pass(monkeypatch):
    from app.tasks import stats_collector as sc
    import app.services.alerts as alerts

    ids = list(range(1, 11))

    class _Res:
        def scalars(self):
            return self

        def all(self):
            return ids

    class _DB:
        async def execute(self, *_a, **_k):
            return _Res()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(sc, "async_session", lambda: _DB())
    monkeypatch.setattr(sc, "reset_telethon_retries", lambda: None)
    monkeypatch.setattr(sc, "collect_closed_channels_once", AsyncMock(return_value=0))
    monkeypatch.setattr(alerts, "alert_stats_summary", AsyncMock())
    sleeps = []

    async def fake_sleep(sec):
        sleeps.append(sec)

    monkeypatch.setattr(sc.asyncio, "sleep", fake_sleep)
    monkeypatch.setenv("STATS_BREAKER_FAILURES", "3")
    monkeypatch.setenv("STATS_CHANNEL_PAUSE_SEC", "2")
    calls = []

    async def failing_refresh(cid):
        calls.append(cid)
        assert sr.pass_running.is_set()
        sr.breaker.record_failure(ValueError("Request was unsuccessful 1 time(s)"))
        return "failed", False

    monkeypatch.setattr(sc, "_refresh_open_channel", failing_refresh)
    await sc.collect_stats_once()
    assert calls == [1, 2, 3]  # breaker opened after 3 failures → pass stopped
    assert sleeps == [2.0, 2.0]  # paused after failures too
    assert sr.scheduler.pending_count() == 7  # the rest deferred, not dropped
    assert all(i.delayed_attempt == -1 for i in sr.scheduler._items.values())
    assert not sr.pass_running.is_set()


@pytest.mark.asyncio
async def test_telethon_stats_skipped_while_circuit_open(monkeypatch):
    from app.services import channel_stats as cs

    client = AsyncMock()
    monkeypatch.setattr(cs, "_get_telethon_client", AsyncMock(return_value=client))
    sr.breaker.record_failure(FloodWaitProxy(900))
    assert await cs.get_channel_stats_telethon("somechan") is None
    client.get_entity.assert_not_called()
    assert cs._last_telethon_stats_fail.pop("somechan")["telethon_error"] == CIRCUIT_OPEN


# ── P1: polling 5xx ──────────────────────────────────────────────────────

@pytest.mark.parametrize("name,msg", [
    ("TelegramServerError", "Telegram server says - Bad Gateway"),
    ("RestartingTelegram", "Telegram server says - restarting"),
    ("TelegramBadRequest", "Telegram server says - 502: Bad Gateway"),
    ("ClientDecodeError", "Failed to decode object: <html>502 Bad Gateway</html>"),
    ("ClientResponseError", "503, message='Service Unavailable'"),
    ("TelegramAPIError", "504 Gateway Time-out"),
])
def test_polling_5xx_is_quiet_with_episode(name, msg):
    from app.utils.polling_watch import PollingEpisodeTracker, is_server_error, process_dispatcher_record

    assert is_server_error(name, msg)
    rec = logging.LogRecord("aiogram.dispatcher", logging.ERROR, __file__, 1,
                            f"Failed to fetch updates - {name}: {msg}", None, None)
    tracker = PollingEpisodeTracker(episode_minutes=5)
    pending = deque()
    process_dispatcher_record(rec, tracker=tracker, now=0, pending=pending)
    assert rec.levelno == logging.WARNING and rec.skip_error_buffer is True
    v = tracker.record_failure(1, name, msg, now=10)
    assert v.level == "WARNING" and not v.emit_episode_error
    v = tracker.record_failure(1, name, msg, now=10 + 5 * 60)
    assert v.level == "ERROR" and v.emit_episode_error
    assert not tracker.record_failure(1, name, msg, now=20 + 5 * 60).emit_episode_error  # once per episode


def test_polling_non_5xx_stays_error():
    from app.utils.polling_watch import PollingEpisodeTracker, is_server_error

    assert not is_server_error("TelegramUnauthorizedError", "Unauthorized")
    assert not is_server_error("TelegramBadRequest", "Bad Request: chat not found (bot id = 8777160217)")
    v = PollingEpisodeTracker().record_failure(1, "TelegramUnauthorizedError", "Unauthorized", now=0)
    assert v.level == "ERROR"


# ── P1: deduplicated error buffer ────────────────────────────────────────

def test_error_buffer_dedup_and_capacity():
    from app.utils.error_buffer import BUFFER_SIZE, ErrorRingBuffer

    assert BUFFER_SIZE >= 1000
    buf = ErrorRingBuffer(maxlen=3)
    lg = logging.getLogger("tests.audit1811.buf")
    lg.propagate = False
    lg.addHandler(buf)
    lg.setLevel(logging.DEBUG)
    try:
        for i in range(65):
            lg.error("Telethon stats failed for channel #%s: Request was unsuccessful %s time(s)", 80 + i, 1)
        lg.warning("view tracking failed for channel #%s", 84)
        lg.warning("view tracking failed for channel #%s", 99)
        lg.error("other a")
        lg.error("other b")
    finally:
        lg.removeHandler(buf)
    snap = buf.snapshot()
    assert len(snap) == 3 and buf.evicted == 1  # LRU: the oldest distinct entry is evicted
    s = buf.summary()
    assert s["distinct_entries"] == 3 and s["evicted_entries"] == 1
    views = [e for e in snap if e["message"].startswith("view tracking")][0]
    assert views["count"] == 2 and views["message"].endswith("#99")
    assert views["first_seen"] <= views["last_seen"]
    for key in ("buffer_size", "buffered", "by_level", "groups"):
        assert key in s  # backward-compatible summary format


def test_error_buffer_burst_does_not_push_out_others():
    from app.utils.error_buffer import ErrorRingBuffer

    buf = ErrorRingBuffer(maxlen=10)
    lg = logging.getLogger("tests.audit1811.burst")
    lg.propagate = False
    lg.addHandler(buf)
    try:
        lg.error("rare important error")
        for i in range(500):
            lg.error("Failed to fetch updates - TelegramServerError: Bad Gateway (try %s)", i)
    finally:
        lg.removeHandler(buf)
    s = buf.summary()
    assert s["buffered"] == 501 and s["distinct_entries"] == 2
    assert any(g["sample"] == "rare important error" for g in s["groups"])


# ── P2: Bot API stats failure reason ─────────────────────────────────────

def test_bot_api_failure_reason_is_concrete_and_token_free():
    from app.services.channel_stats import describe_bot_api_failure

    assert describe_bot_api_failure(401, "Unauthorized") == "401 Unauthorized — check BOT_TOKEN_STATS"
    assert "check BOT_TOKEN_STATS" in describe_bot_api_failure(404, "Not Found")
    assert "channel not reachable" in describe_bot_api_failure(400, "Bad Request: chat not found")
    assert "server error" in describe_bot_api_failure(502, "Bad Gateway")
    token = "123456789:AAH" + "x" * 32
    out = describe_bot_api_failure(None, f"ConnectError: https://api.telegram.org/bot{token}/getChat")
    assert token not in out and "network error" in out


@pytest.mark.asyncio
async def test_bot_api_failure_logged_with_reason(monkeypatch, caplog):
    from app.services import channel_stats as cs

    token = "123456789:AAH" + "y" * 32
    monkeypatch.setattr(cs.settings, "bot_token_stats", token)

    class _Resp:
        status_code = 401

        def json(self):
            return {"ok": False, "error_code": 401, "description": "Unauthorized"}

    class _Http:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Http())
    monkeypatch.setattr(cs, "get_channel_stats_telethon", AsyncMock(return_value=None))
    with caplog.at_level(logging.WARNING, logger="app.services.channel_stats"):
        await cs.collect_channel_stats("@somechan")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "Bot API stats failed: 401 Unauthorized — check BOT_TOKEN_STATS" in text
    assert token not in text
