"""Unit tests for deferred Telethon stats backoff (no DB)."""
from app.services.stats_retry import (
    MAX_DELAYED_ATTEMPTS,
    RETRY_DELAYS_SEC,
    FloodWaitProxy,
    StatsRetryScheduler,
    is_retryable_stats_error,
    next_retry_delay_sec,
    note_telethon_stats_result,
)


def test_delays_are_5_15_60_minutes():
    assert RETRY_DELAYS_SEC == (5 * 60, 15 * 60, 60 * 60)
    assert MAX_DELAYED_ATTEMPTS == 3
    assert next_retry_delay_sec(0) == 5 * 60
    assert next_retry_delay_sec(1) == 15 * 60
    assert next_retry_delay_sec(2) == 60 * 60
    assert next_retry_delay_sec(3) is None


def test_flood_wait_extends_delay():
    assert next_retry_delay_sec(0, flood_wait_sec=120) == 5 * 60  # 2 min flood < 5 min
    assert next_retry_delay_sec(0, flood_wait_sec=20 * 60) == 20 * 60  # honor longer FloodWait


def test_rpc_call_fail_is_retryable_valueerror_is_not():
    assert is_retryable_stats_error("RpcCallFailError")
    assert is_retryable_stats_error(FloodWaitProxy(30))
    assert not is_retryable_stats_error("ValueError")
    assert not is_retryable_stats_error("AuthKeyDuplicatedError")


def test_scheduler_backoff_and_limit():
    sched = StatsRetryScheduler()
    first = sched.schedule(42, "RpcCallFailError", now=1000)
    assert first is not None and first.delayed_attempt == 0
    assert first.next_at == 1000 + 5 * 60
    assert sched.due(now=1000 + 5 * 60 - 1) == []
    assert [i.channel_id for i in sched.due(now=1000 + 5 * 60)] == [42]

    second = sched.schedule(42, "RpcCallFailError", now=first.next_at)
    assert second is not None and second.delayed_attempt == 1
    assert second.next_at == first.next_at + 15 * 60

    third = sched.schedule(42, "RpcCallFailError", now=second.next_at)
    assert third is not None and third.delayed_attempt == 2
    assert third.next_at == second.next_at + 60 * 60

    assert sched.schedule(42, "RpcCallFailError", now=third.next_at) is None
    assert sched.pending_count() == 0


def test_flood_wait_and_success_cancel():
    sched = StatsRetryScheduler(now_fn=lambda: 10_000)
    import app.services.stats_retry as mod
    prev = mod.scheduler
    mod.scheduler = sched
    try:
        note_telethon_stats_result(7, {
            "daily_stats": [],
            "telethon_retryable": True,
            "telethon_error": "FloodWaitError",
            "telethon_flood_wait_sec": 20 * 60,
        }, now=10_000)
        item = sched._items[7]
        assert item.last_error == "FloodWaitError"
        assert item.next_at == 10_000 + 20 * 60

        note_telethon_stats_result(7, {"daily_stats": [{"date": "2026-11-17", "views": 1}]})
        assert sched.pending_count() == 0
    finally:
        mod.scheduler = prev


def test_non_retryable_does_not_schedule():
    sched = StatsRetryScheduler()
    import app.services.stats_retry as mod
    prev = mod.scheduler
    mod.scheduler = sched
    try:
        note_telethon_stats_result(3, {
            "daily_stats": [],
            "telethon_retryable": False,
            "telethon_error": "UsernameNotOccupiedError",
        })
        assert sched.pending_count() == 0
    finally:
        mod.scheduler = prev
