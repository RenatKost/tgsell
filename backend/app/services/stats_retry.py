"""Deferred Telethon stats retries with exponential backoff.

Telethon's default request_retries=5 plus the initial attempt is 6 immediate
tries (2s apart) on RpcCallFailError. That hammers a struggling DC and does
not help. The client is created with request_retries=0; this scheduler
retries the channel later: 5 min, then 15 min, then 60 min. FloodWait is
respected (wait at least e.seconds). The Telethon connection is left alone.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

RETRY_DELAYS_SEC = (5 * 60, 15 * 60, 60 * 60)
MAX_DELAYED_ATTEMPTS = len(RETRY_DELAYS_SEC)

RETRYABLE_ERROR_NAMES = frozenset({
    "RpcCallFailError",
    "ServerError",
    "TimedOutError",
    "RpcMcgetFailError",
    "InterdcCallErrorError",
    "InterdcCallRichErrorError",
    "FloodWaitError",
})


def error_name_of(error: object) -> str:
    if isinstance(error, str):
        return error
    return type(error).__name__


def is_retryable_stats_error(error: object) -> bool:
    return error_name_of(error) in RETRYABLE_ERROR_NAMES


def flood_wait_seconds(error: object) -> int:
    if error_name_of(error) != "FloodWaitError":
        return 0
    try:
        return max(0, int(getattr(error, "seconds", 0) or 0))
    except (TypeError, ValueError):
        return 0


def classify_telethon_stats_error(error: object) -> dict:
    name = error_name_of(error)
    return {
        "telethon_error": name,
        "telethon_retryable": is_retryable_stats_error(error),
        "telethon_flood_wait_sec": flood_wait_seconds(error),
    }


def next_retry_delay_sec(delayed_attempt: int, flood_wait_sec: int = 0) -> int | None:
    """Delay before delayed_attempt (0-based). None if the limit is exhausted."""
    if delayed_attempt < 0 or delayed_attempt >= MAX_DELAYED_ATTEMPTS:
        return None
    return max(RETRY_DELAYS_SEC[delayed_attempt], max(0, int(flood_wait_sec or 0)))


class FloodWaitProxy:
    """Stand-in so schedule() can see name FloodWaitError and .seconds without Telethon."""

    def __init__(self, seconds: int):
        self.seconds = seconds


FloodWaitProxy.__name__ = "FloodWaitError"


@dataclass
class RetryItem:
    channel_id: int
    delayed_attempt: int
    next_at: float
    last_error: str


@dataclass
class StatsRetryScheduler:
    now_fn: object = time.time
    _items: dict[int, RetryItem] = field(default_factory=dict)
    _in_flight: set[int] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _now(self, now: float | None) -> float:
        return self.now_fn() if now is None else now  # type: ignore[operator]

    def schedule(self, channel_id: int, error: object, now: float | None = None) -> RetryItem | None:
        """Schedule or advance a retry. Returns the item, or None if exhausted / not retryable."""
        if not is_retryable_stats_error(error):
            return None
        ts = self._now(now)
        flood = flood_wait_seconds(error)
        name = error_name_of(error)
        with self._lock:
            existing = self._items.get(channel_id)
            attempt = 0 if existing is None else existing.delayed_attempt + 1
            delay = next_retry_delay_sec(attempt, flood)
            if delay is None:
                self._items.pop(channel_id, None)
                logger.warning(
                    "[STATS] Giving up Telethon retry for channel #%s after %s delayed attempts (%s)",
                    channel_id, MAX_DELAYED_ATTEMPTS, name,
                )
                return None
            item = RetryItem(
                channel_id=channel_id,
                delayed_attempt=attempt,
                next_at=ts + delay,
                last_error=name,
            )
            self._items[channel_id] = item
            logger.warning(
                "[STATS] Telethon %s for channel #%s — retry #%s in %ss",
                name, channel_id, attempt + 1, delay,
            )
            return item

    def cancel(self, channel_id: int) -> None:
        with self._lock:
            self._items.pop(channel_id, None)

    def due(self, now: float | None = None) -> list[RetryItem]:
        ts = self._now(now)
        with self._lock:
            return [
                item for item in self._items.values()
                if item.next_at <= ts and item.channel_id not in self._in_flight
            ]

    def mark_in_flight(self, channel_id: int) -> bool:
        with self._lock:
            if channel_id in self._in_flight:
                return False
            self._in_flight.add(channel_id)
            return True

    def clear_in_flight(self, channel_id: int) -> None:
        with self._lock:
            self._in_flight.discard(channel_id)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._items)

    def reset(self) -> None:
        with self._lock:
            self._items.clear()
            self._in_flight.clear()


scheduler = StatsRetryScheduler()


def note_telethon_stats_result(channel_id: int, stats: dict, now: float | None = None) -> None:
    """Cancel on success; schedule a delayed retry when Telethon failed retryably."""
    if stats.get("daily_stats"):
        scheduler.cancel(channel_id)
        return
    if not stats.get("telethon_retryable"):
        return
    error = stats.get("telethon_error") or "RpcCallFailError"
    seconds = int(stats.get("telethon_flood_wait_sec") or 0)
    if error == "FloodWaitError":
        scheduler.schedule(channel_id, FloodWaitProxy(seconds), now=now)
    else:
        scheduler.schedule(channel_id, error, now=now)


async def run_stats_retry_loop(interval_sec: int = 30) -> None:
    """Background loop: run due channel-stat retries. Does not touch the Telethon session."""
    from app.tasks.stats_collector import _refresh_open_channel

    logger.info("Stats retry loop started (interval: %ss, delays: %s)", interval_sec, RETRY_DELAYS_SEC)
    while True:
        try:
            due = scheduler.due()
            for item in due:
                if not scheduler.mark_in_flight(item.channel_id):
                    continue
                try:
                    outcome, telethon_ok = await _refresh_open_channel(item.channel_id)
                    if telethon_ok or outcome == "ok":
                        scheduler.cancel(item.channel_id)
                        logger.info(
                            "[STATS] Deferred Telethon retry succeeded for channel #%s",
                            item.channel_id,
                        )
                except Exception as e:
                    logger.warning(
                        "[STATS] Deferred retry failed for channel #%s: %s",
                        item.channel_id, type(e).__name__,
                    )
                    scheduler.schedule(item.channel_id, e)
                finally:
                    scheduler.clear_in_flight(item.channel_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Stats retry loop error: %s", type(e).__name__)
        await asyncio.sleep(interval_sec)
