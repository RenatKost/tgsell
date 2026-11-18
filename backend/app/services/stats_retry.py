"""Deferred Telethon stats retries with exponential backoff.

Telethon's default request_retries=5 plus the initial attempt is 6 immediate
tries (2s apart) on RpcCallFailError. That hammers a struggling DC and does
not help. The client is created with request_retries=0; this scheduler
retries the channel later: 5 min, then 15 min, then 60 min. FloodWait is
respected (wait at least e.seconds). The Telethon connection is left alone.

Telethon's generic ValueError("Request was unsuccessful N time(s)") is the
same class of failure (internal errors / short FloodWait exhausted the
request retries) and is retryable too. A circuit breaker stops a pass when
most channels fail in a row, and channels are throttled (STATS_* env).
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

RETRY_DELAYS_SEC = (5 * 60, 15 * 60, 60 * 60)
MAX_DELAYED_ATTEMPTS = len(RETRY_DELAYS_SEC)

REQUEST_UNSUCCESSFUL = "RequestUnsuccessful"
# Synthetic name used while the circuit breaker is open: the channel is
# deferred without consuming one of the 3 delayed attempts.
CIRCUIT_OPEN = "CircuitOpen"

RETRYABLE_ERROR_NAMES = frozenset({
    "RpcCallFailError",
    "ServerError",
    "TimedOutError",
    "RpcMcgetFailError",
    "InterdcCallErrorError",
    "InterdcCallRichErrorError",
    "FloodWaitError",
    # Telethon raises ValueError("Request was unsuccessful N time(s)") when all
    # request_retries attempts hit one of the internal errors above (or a short
    # FloodWait that Telethon slept through) and raise_last_call_error is off.
    REQUEST_UNSUCCESSFUL,
    CIRCUIT_OPEN,
})

_REQUEST_UNSUCCESSFUL_MARKER = "request was unsuccessful"


def is_request_unsuccessful(error: object) -> bool:
    """Telethon's generic "Request was unsuccessful N time(s)" ValueError."""
    if isinstance(error, str):
        return error == REQUEST_UNSUCCESSFUL or _REQUEST_UNSUCCESSFUL_MARKER in error.lower()
    return isinstance(error, ValueError) and _REQUEST_UNSUCCESSFUL_MARKER in str(error).lower()


def error_name_of(error: object) -> str:
    if is_request_unsuccessful(error):
        return REQUEST_UNSUCCESSFUL
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


# ── Throttling (env, read at use time; Railway Variables are optional) ─────

def _env_number(name: str, default: float, lo: float, hi: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(hi, max(lo, value))


def channel_pause_sec() -> float:
    """Pause between channels in a Telethon stats / view-tracking pass (always, also after failures)."""
    return _env_number("STATS_CHANNEL_PAUSE_SEC", 3.0, 0.0, 60.0)


def batch_size() -> int:
    """Channels per batch in the daily stats pass."""
    return int(_env_number("STATS_BATCH_SIZE", 10, 1, 1000))


def batch_pause_sec() -> float:
    """Extra pause between batches of the daily stats pass."""
    return _env_number("STATS_BATCH_PAUSE_SEC", 30.0, 0.0, 600.0)


def breaker_threshold() -> int:
    """Consecutive retryable Telethon failures that open the circuit."""
    return int(_env_number("STATS_BREAKER_FAILURES", 5, 2, 100))


def breaker_cooldown_sec() -> float:
    """How long the circuit stays open before one probe request is allowed."""
    return _env_number("STATS_BREAKER_COOLDOWN_SEC", 30 * 60, 60.0, 6 * 3600)


@dataclass
class TelethonCircuitBreaker:
    """Stops hammering the Telethon session when most channels fail in a row.

    Closed: requests go through; consecutive retryable failures are counted.
    Open: no Telethon stats requests until the cooldown ends (callers defer).
    Half-open (after cooldown): the next failure re-opens it at once, a success closes it.
    A raised FloodWaitError (longer than Telethon's own sleep threshold) opens it
    immediately for max(cooldown, wait). The session is never reconnected here.
    """

    threshold: int | None = None
    cooldown_sec: float | None = None
    now_fn: object = time.time
    _consecutive: int = 0
    _open_until: float = 0.0
    _half_open: bool = False
    _trips: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _now(self, now: float | None) -> float:
        return self.now_fn() if now is None else now  # type: ignore[operator]

    def _threshold(self) -> int:
        return self.threshold if self.threshold is not None else breaker_threshold()

    def _cooldown(self) -> float:
        return self.cooldown_sec if self.cooldown_sec is not None else breaker_cooldown_sec()

    def is_open(self, now: float | None = None) -> bool:
        with self._lock:
            return self._open_until > self._now(now)

    def remaining_sec(self, now: float | None = None) -> float:
        with self._lock:
            return max(0.0, self._open_until - self._now(now))

    def record_success(self) -> None:
        with self._lock:
            was = self._half_open
            self._consecutive = 0
            self._half_open = False
        if was:
            logger.info("[STATS] Telethon circuit closed — stats requests succeed again")

    def record_failure(self, error: object, now: float | None = None) -> bool:
        """Count a failure. Returns True when this call opened the circuit."""
        name = error_name_of(error)
        if name == CIRCUIT_OPEN or not is_retryable_stats_error(error):
            return False  # channel-specific errors (private, invalid…) say nothing about the session
        ts = self._now(now)
        flood = flood_wait_seconds(error)
        with self._lock:
            if self._open_until > ts:
                return False
            self._consecutive += 1
            trip = bool(flood) or self._half_open or self._consecutive >= self._threshold()
            if not trip:
                return False
            duration = max(self._cooldown(), float(flood))
            self._open_until = ts + duration
            self._half_open = True
            self._trips += 1
            count = self._consecutive
            self._consecutive = 0
        logger.warning(
            "[STATS] Telethon circuit opened for %ss after %s consecutive failure(s) (last: %s)",
            int(duration), count, name,
        )
        return True

    def snapshot(self, now: float | None = None) -> dict:
        ts = self._now(now)
        with self._lock:
            return {
                "open": self._open_until > ts,
                "open_for_sec": int(max(0.0, self._open_until - ts)),
                "consecutive_failures": self._consecutive,
                "trips": self._trips,
            }

    def reset(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._open_until = 0.0
            self._half_open = False
            self._trips = 0


breaker = TelethonCircuitBreaker()


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
        if error_name_of(error) == CIRCUIT_OPEN:
            return self.defer(channel_id, breaker.remaining_sec(now), CIRCUIT_OPEN, now=now)
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

    def defer(self, channel_id: int, delay_sec: float, reason: str = CIRCUIT_OPEN,
              now: float | None = None) -> RetryItem:
        """Postpone a channel without consuming a delayed attempt (circuit breaker)."""
        ts = self._now(now)
        with self._lock:
            existing = self._items.get(channel_id)
            # Stagger deferred channels so they do not all fire at the same moment.
            stagger = len(self._items) * channel_pause_sec()
            next_at = ts + max(0.0, float(delay_sec or 0)) + stagger
            if existing is not None:
                existing.next_at = max(existing.next_at, next_at)
                existing.last_error = reason
                return existing
            item = RetryItem(channel_id=channel_id, delayed_attempt=-1, next_at=next_at, last_error=reason)
            self._items[channel_id] = item
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
# Set while collect_stats_once runs; the retry loop then waits (no parallel Telethon streams).
pass_running = threading.Event()


def note_telethon_stats_result(channel_id: int, stats: dict, now: float | None = None) -> None:
    """Cancel on success; schedule a delayed retry when Telethon failed retryably."""
    if stats.get("daily_stats"):
        scheduler.cancel(channel_id)
        return
    if not stats.get("telethon_retryable"):
        return
    error = stats.get("telethon_error") or "RpcCallFailError"
    seconds = int(stats.get("telethon_flood_wait_sec") or 0)
    if error == CIRCUIT_OPEN:
        scheduler.defer(channel_id, breaker.remaining_sec(now), CIRCUIT_OPEN, now=now)
    elif error == "FloodWaitError":
        scheduler.schedule(channel_id, FloodWaitProxy(seconds), now=now)
    else:
        scheduler.schedule(channel_id, error, now=now)


async def run_stats_retry_loop(interval_sec: int = 30) -> None:
    """Background loop: run due channel-stat retries. Does not touch the Telethon session."""
    from app.tasks.stats_collector import _refresh_open_channel

    logger.info("Stats retry loop started (interval: %ss, delays: %s)", interval_sec, RETRY_DELAYS_SEC)
    while True:
        try:
            due = [] if (breaker.is_open() or pass_running.is_set()) else scheduler.due()
            for n, item in enumerate(due):
                if breaker.is_open() or pass_running.is_set():
                    break  # circuit opened / full pass started: leave the rest for later
                if n:
                    await asyncio.sleep(channel_pause_sec())
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
