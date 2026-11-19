"""Unit tests for polling timeout/episode logging (no DB)."""
from __future__ import annotations

import logging
from collections import deque

from app.utils.error_buffer import ErrorRingBuffer
from app.utils.polling_watch import (
    CONFLICT_WARNING_WINDOW_SEC,
    POLLING_TIMEOUT_SEC,
    SESSION_TIMEOUT_SEC,
    PollingEpisodeTracker,
    is_conflict_error,
    is_transient_network_error,
    polling_error_episode_minutes,
    process_dispatcher_record,
)


def _record(level: int, message: str, name: str = "aiogram.dispatcher") -> logging.LogRecord:
    rec = logging.LogRecord(name, level, __file__, 0, message, (), None)
    return rec


def test_timeouts_are_sane():
    assert POLLING_TIMEOUT_SEC == 30
    assert SESSION_TIMEOUT_SEC > POLLING_TIMEOUT_SEC
    assert polling_error_episode_minutes() == 20


def test_classifies_timeout_and_conflict():
    assert is_transient_network_error("TelegramNetworkError", "Request timeout error")
    assert is_transient_network_error("TimeoutError", "")
    assert is_conflict_error("TelegramConflictError", "terminated by other getUpdates request")
    assert not is_transient_network_error("RuntimeError", "boom")


def test_isolated_timeouts_are_warning_and_skip_buffer():
    tracker = PollingEpisodeTracker(episode_minutes=5, process_started_at=0, now_fn=lambda: 1000)
    pending: deque = deque()
    rec = _record(logging.ERROR, "Failed to fetch updates - TelegramNetworkError: Request timeout error")
    extras = process_dispatcher_record(rec, tracker=tracker, now=1000, pending=pending)
    assert rec.levelno == logging.WARNING
    assert rec.skip_error_buffer is True
    assert extras == []

    sleep = _record(
        logging.WARNING,
        "Sleep for 1.000000 seconds and try again... (tryings = 0, bot id = 8777160217)",
    )
    extras = process_dispatcher_record(sleep, tracker=tracker, now=1000, pending=pending)
    assert sleep.skip_error_buffer is True
    assert extras == []

    # A success before N minutes is WARNING with duration, not ERROR/INFO.
    ok = _record(logging.INFO, "Connection established (tryings = 1, bot id = 8777160217)")
    extras = process_dispatcher_record(ok, tracker=tracker, now=1060, pending=pending)
    assert len(extras) == 1 and extras[0][0] == logging.WARNING
    assert "1.0 min" in extras[0][1] and "8777160217" in extras[0][1]


def test_one_error_after_episode_and_info_on_recovery():
    tracker = PollingEpisodeTracker(episode_minutes=5, process_started_at=0, now_fn=lambda: 0)
    pending: deque = deque()
    t0 = 1_000.0

    def fail_once(ts: float) -> list[tuple[int, str]]:
        rec = _record(logging.ERROR, "Failed to fetch updates - TelegramNetworkError: Request timeout error")
        process_dispatcher_record(rec, tracker=tracker, now=ts, pending=pending)
        sleep = _record(
            logging.WARNING,
            "Sleep for 2.000000 seconds and try again... (tryings = 3, bot id = 8777160217)",
        )
        return process_dispatcher_record(sleep, tracker=tracker, now=ts, pending=pending)

    assert fail_once(t0) == []
    # 4:59 later — still WARNING, no ERROR.
    assert fail_once(t0 + 4 * 60 + 59) == []
    # Crossing 5 minutes — exactly one ERROR for the episode.
    extras = fail_once(t0 + 5 * 60)
    assert len(extras) == 1 and extras[0][0] == logging.ERROR
    assert "8777160217" in extras[0][1]
    assert "5.0 min" in extras[0][1]
    # Further failures in the same episode do not emit another ERROR.
    assert fail_once(t0 + 8 * 60) == []

    ok = _record(logging.INFO, "Connection established (tryings = 20, bot id = 8777160217)")
    extras = process_dispatcher_record(ok, tracker=tracker, now=t0 + 9 * 60, pending=pending)
    assert len(extras) == 1 and extras[0][0] == logging.INFO
    assert "recovered" in extras[0][1] and "8777160217" in extras[0][1]


def test_episodes_are_per_bot():
    tracker = PollingEpisodeTracker(episode_minutes=5, process_started_at=0)
    pending: deque = deque()
    t0 = 100.0
    rec = _record(logging.ERROR, "Failed to fetch updates - TelegramNetworkError: Request timeout error")
    process_dispatcher_record(rec, tracker=tracker, now=t0, pending=pending)
    process_dispatcher_record(
        _record(logging.WARNING, "Sleep for 1s ... (tryings = 0, bot id = 1)"),
        tracker=tracker, now=t0, pending=pending,
    )
    # Other bot recovers — must not reset bot 1's episode.
    process_dispatcher_record(
        _record(logging.INFO, "Connection established (tryings = 1, bot id = 2)"),
        tracker=tracker, now=t0 + 10, pending=pending,
    )
    rec = _record(logging.ERROR, "Failed to fetch updates - TelegramNetworkError: Request timeout error")
    process_dispatcher_record(rec, tracker=tracker, now=t0 + 5 * 60, pending=pending)
    extras = process_dispatcher_record(
        _record(logging.WARNING, "Sleep for 1s ... (tryings = 4, bot id = 1)"),
        tracker=tracker, now=t0 + 5 * 60, pending=pending,
    )
    assert extras and extras[0][0] == logging.ERROR and "bot id=1" in extras[0][1]


def test_conflict_is_warning_in_first_minutes():
    started = 0.0
    tracker = PollingEpisodeTracker(
        episode_minutes=5,
        conflict_warning_window_sec=CONFLICT_WARNING_WINDOW_SEC,
        process_started_at=started,
    )
    pending: deque = deque()
    # 30s after process start (typical deploy overlap).
    rec = _record(
        logging.ERROR,
        "Failed to fetch updates - TelegramConflictError: Conflict: terminated by other getUpdates request",
    )
    process_dispatcher_record(rec, tracker=tracker, now=30, pending=pending)
    assert rec.levelno == logging.WARNING and rec.skip_error_buffer is True
    extras = process_dispatcher_record(
        _record(logging.WARNING, "Sleep for 1s ... (tryings = 0, bot id = 9)"),
        tracker=tracker, now=30, pending=pending,
    )
    assert extras == []


def test_skipped_warnings_do_not_enter_error_buffer():
    buf = ErrorRingBuffer(maxlen=20)
    rec = _record(logging.ERROR, "Failed to fetch updates - TelegramNetworkError: Request timeout error")
    process_dispatcher_record(rec, tracker=PollingEpisodeTracker(), pending=deque())
    buf.emit(rec)
    other = _record(logging.ERROR, "unrelated boom")
    buf.emit(other)
    snap = buf.snapshot()
    assert len(snap) == 1
    assert snap[0]["message"] == "unrelated boom"

def test_episode_minutes_default_and_env(monkeypatch):
    monkeypatch.delenv("POLLING_ERROR_EPISODE_MINUTES", raising=False)
    assert polling_error_episode_minutes() == 20
    monkeypatch.setenv("POLLING_ERROR_EPISODE_MINUTES", "25")
    assert polling_error_episode_minutes() == 25
    monkeypatch.setenv("POLLING_ERROR_EPISODE_MINUTES", "0")
    assert polling_error_episode_minutes() == 20
    monkeypatch.setenv("POLLING_ERROR_EPISODE_MINUTES", "nope")
    assert polling_error_episode_minutes() == 20


def test_short_502_episode_recovers_as_warning():
    """A ~5 min Telegram 502 that self-recovers must be WARNING, not ERROR."""
    tracker = PollingEpisodeTracker(episode_minutes=20, process_started_at=0)
    pending: deque = deque()
    t0 = 1_000.0

    rec = _record(
        logging.ERROR,
        "Failed to fetch updates - TelegramServerError: Telegram server says - Bad Gateway",
    )
    process_dispatcher_record(rec, tracker=tracker, now=t0, pending=pending)
    assert rec.levelno == logging.WARNING and rec.skip_error_buffer is True
    extras = process_dispatcher_record(
        _record(
            logging.WARNING,
            "Sleep for 1.000000 seconds and try again... (tryings = 0, bot id = 8997383465)",
        ),
        tracker=tracker, now=t0, pending=pending,
    )
    assert extras == []

    rec = _record(
        logging.ERROR,
        "Failed to fetch updates - TelegramServerError: Telegram server says - Bad Gateway",
    )
    process_dispatcher_record(rec, tracker=tracker, now=t0 + 5 * 60, pending=pending)
    extras = process_dispatcher_record(
        _record(
            logging.WARNING,
            "Sleep for 1.000000 seconds and try again... (tryings = 4, bot id = 8997383465)",
        ),
        tracker=tracker, now=t0 + 5 * 60, pending=pending,
    )
    assert extras == []  # still under the 20 min threshold

    ok = _record(logging.INFO, "Connection established (tryings = 5, bot id = 8997383465)")
    extras = process_dispatcher_record(ok, tracker=tracker, now=t0 + 5 * 60, pending=pending)
    assert len(extras) == 1 and extras[0][0] == logging.WARNING
    assert "5.0 min" in extras[0][1]
    assert "8997383465" in extras[0][1]
    assert "TelegramServerError" in extras[0][1]


def test_unauthorized_and_400_are_immediate_error():
    tracker = PollingEpisodeTracker(episode_minutes=20, process_started_at=0)
    pending: deque = deque()

    rec = _record(logging.ERROR, "Failed to fetch updates - TelegramUnauthorizedError: Unauthorized")
    extras = process_dispatcher_record(rec, tracker=tracker, now=1, pending=pending)
    assert rec.levelno == logging.ERROR
    assert extras == []
    extras = process_dispatcher_record(
        _record(logging.WARNING, "Sleep for 1s ... (tryings = 0, bot id = 8997383465)"),
        tracker=tracker, now=1, pending=pending,
    )
    assert extras == []
    # Immediate ERROR is on the original record (not quiet); no delayed episode ERROR.
    # Recovery of a non-quiet failure must not emit WARNING/INFO.
    ok = _record(logging.INFO, "Connection established (tryings = 1, bot id = 8997383465)")
    extras = process_dispatcher_record(ok, tracker=tracker, now=30, pending=pending)
    assert extras == []

    rec = _record(
        logging.ERROR,
        "Failed to fetch updates - TelegramBadRequest: Bad Request: chat not found",
    )
    process_dispatcher_record(rec, tracker=tracker, now=40, pending=pending)
    assert rec.levelno == logging.ERROR
    v = tracker.record_failure(2, "TelegramBadRequest", "Bad Request: chat not found", now=40)
    assert v.level == "ERROR" and not v.emit_episode_error and v.skip_error_buffer is False
