"""Aiogram getUpdates polling: timeouts, backoff, and quiet logging of transient errors.

Isolated network timeouts, Telegram 5xx (Bad Gateway, TelegramServerError)
and short-lived 409 conflicts must not fill the
audit error buffer. If getUpdates recovers on its own before
POLLING_ERROR_EPISODE_MINUTES (default 20), a WARNING with the episode
duration is logged. One ERROR is emitted only when failures persist longer
than that threshold; INFO is logged when such a long episode recovers.
Unauthorized and HTTP 400 stay immediate ERROR.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.utils.backoff import BackoffConfig

logger = logging.getLogger(__name__)

# Long-poll wait for getUpdates. start_polling() default is 10s; 30s is the
# usual Telegram recommendation and cuts idle request volume.
POLLING_TIMEOUT_SEC = 30
# Session timeout must be greater than the long-poll timeout. aiogram 3.3
# then sets request_timeout = session.timeout + polling_timeout (here 90s).
SESSION_TIMEOUT_SEC = 60
POLLING_BACKOFF = BackoffConfig(min_delay=1.0, max_delay=30.0, factor=1.5, jitter=0.1)

_DEFAULT_EPISODE_MINUTES = 20
# Deploy overlap: TelegramConflictError in the first minutes is expected.
CONFLICT_WARNING_WINDOW_SEC = 180

_FAILED_RE = re.compile(r"Failed to fetch updates - ([A-Za-z0-9_]+): (.*)$")
_BOT_ID_RE = re.compile(r"bot id = (\d+)")

_TRANSIENT_ERROR_NAMES = frozenset({
    "TelegramNetworkError",
    "TelegramRetryAfter",
    "TimeoutError",
    "asyncio.TimeoutError",
    "ClientConnectorError",
    "ClientOSError",
    "ClientPayloadError",
    "ServerDisconnectedError",
    "ServerTimeoutError",
    "SocketTimeoutError",
    "ConnectionError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "OSError",
})
_CONFLICT_ERROR_NAMES = frozenset({"TelegramConflictError"})
# Telegram-side 5xx (Bad Gateway etc.): transient, same WARNING/episode handling.
_SERVER_ERROR_NAMES = frozenset({"TelegramServerError", "RestartingTelegram"})
# Error types that may carry an HTTP 5xx in their text (HTML 502 page → ClientDecodeError,
# aiohttp ClientResponseError, TelegramBadRequest/TelegramAPIError with error_code 50x).
_MAYBE_HTTP_ERROR_NAMES = frozenset({
    "TelegramBadRequest", "TelegramAPIError", "ClientDecodeError",
    "ClientResponseError", "ContentTypeError", "Unknown",
})
_SERVER_ERROR_PHRASES = (
    "bad gateway", "service unavailable", "gateway timeout", "gateway time-out",
    "internal server error", "telegram server says",
)
_HTTP_5XX_RE = re.compile(r"\b5(?:0[0-9]|2[0-9])\b")

POLLING_START_KWARGS = {
    "polling_timeout": POLLING_TIMEOUT_SEC,
    "backoff_config": POLLING_BACKOFF,
}


def polling_error_episode_minutes() -> int:
    """N minutes of consecutive failures before one ERROR. Env override, default 20."""
    raw = os.getenv("POLLING_ERROR_EPISODE_MINUTES", "").strip()
    if not raw:
        return _DEFAULT_EPISODE_MINUTES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_EPISODE_MINUTES
    return value if value > 0 else _DEFAULT_EPISODE_MINUTES


def build_polling_bot(token: str) -> Bot:
    """Bot whose HTTP session outlives a long-poll getUpdates call."""
    return Bot(token=token, session=AiohttpSession(timeout=SESSION_TIMEOUT_SEC))


def is_conflict_error(error_name: str, message: str = "") -> bool:
    name = (error_name or "").split(".")[-1]
    if name in _CONFLICT_ERROR_NAMES:
        return True
    lower = (message or "").lower()
    return "telegramconflicterror" in lower or "terminated by other getupdates" in lower


def is_transient_network_error(error_name: str, message: str = "") -> bool:
    name = (error_name or "").split(".")[-1]
    if name in _TRANSIENT_ERROR_NAMES:
        return True
    lower = (message or "").lower()
    return "request timeout" in lower or "timeout error" in lower or "timed out" in lower


def is_server_error(error_name: str, message: str = "") -> bool:
    """Telegram/HTTP 5xx: TelegramServerError, 502/503/504 Bad Gateway & co."""
    name = (error_name or "").split(".")[-1]
    if name in _SERVER_ERROR_NAMES:
        return True
    lower = (message or "").lower()
    if any(p in lower for p in _SERVER_ERROR_PHRASES):
        return True
    return name in _MAYBE_HTTP_ERROR_NAMES and bool(_HTTP_5XX_RE.search(lower))


def _is_quiet_failure(error_name: str, message: str) -> bool:
    return (
        is_conflict_error(error_name, message)
        or is_transient_network_error(error_name, message)
        or is_server_error(error_name, message)
    )


@dataclass
class FailureVerdict:
    level: str
    skip_error_buffer: bool
    emit_episode_error: bool
    episode_error_message: str | None = None


@dataclass
class SuccessVerdict:
    emit_recovery_info: bool
    recovery_message: str | None = None
    emit_recovery_warning: bool = False


@dataclass
class _Episode:
    started_at: float
    error_emitted: bool = False
    last_error_name: str = ""
    last_error: str = ""


@dataclass
class PollingEpisodeTracker:
    """Pure consecutive-failure tracker, one episode per bot id."""

    episode_minutes: int = field(default_factory=polling_error_episode_minutes)
    conflict_warning_window_sec: int = CONFLICT_WARNING_WINDOW_SEC
    process_started_at: float | None = None
    now_fn: callable = time.time
    _episodes: dict[int, _Episode] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _now(self, now: float | None) -> float:
        return self.now_fn() if now is None else now

    def _process_age(self, now: float) -> float:
        started = self.process_started_at
        if started is None:
            try:
                from app.utils.error_buffer import PROCESS_STARTED_AT
                started = PROCESS_STARTED_AT.timestamp()
            except Exception:
                started = now
        return now - started

    def record_failure(
        self,
        bot_id: int | None,
        error_name: str,
        message: str,
        now: float | None = None,
    ) -> FailureVerdict:
        ts = self._now(now)
        key = int(bot_id) if bot_id is not None else 0
        quiet = _is_quiet_failure(error_name, message)
        in_conflict_window = (
            is_conflict_error(error_name, message)
            and self._process_age(ts) < self.conflict_warning_window_sec
        )

        with self._lock:
            episode = self._episodes.get(key)
            if episode is None:
                episode = _Episode(started_at=ts, last_error_name=error_name, last_error=message)
                self._episodes[key] = episode
            else:
                episode.last_error_name = error_name
                episode.last_error = message

            duration_sec = ts - episode.started_at
            should_error = (
                quiet
                and not in_conflict_window
                and duration_sec >= self.episode_minutes * 60
                and not episode.error_emitted
            )
            if should_error:
                episode.error_emitted = True
                minutes = duration_sec / 60
                text = (
                    f"Polling getUpdates failing for {minutes:.1f} min "
                    f"(bot id={key}, last error: {error_name}: {message})"
                )
                return FailureVerdict(
                    level="ERROR",
                    skip_error_buffer=False,
                    emit_episode_error=True,
                    episode_error_message=text,
                )

            if quiet or in_conflict_window:
                return FailureVerdict(level="WARNING", skip_error_buffer=True, emit_episode_error=False)

            # Unexpected getUpdates errors stay visible in the audit buffer.
            return FailureVerdict(level="ERROR", skip_error_buffer=False, emit_episode_error=False)

    def record_success(self, bot_id: int | None, now: float | None = None) -> SuccessVerdict:
        key = int(bot_id) if bot_id is not None else 0
        with self._lock:
            episode = self._episodes.pop(key, None)
        if episode is None:
            return SuccessVerdict(emit_recovery_info=False, recovery_message=None)
        ts = self._now(now)
        minutes = (ts - episode.started_at) / 60
        if episode.error_emitted:
            text = (
                f"Polling recovered for bot id={key} after {minutes:.1f} min "
                f"(last error: {episode.last_error_name})"
            )
            return SuccessVerdict(emit_recovery_info=True, recovery_message=text)
        # Self-recovered quiet episode (timeouts / 5xx / short 409): WARNING with duration.
        if _is_quiet_failure(episode.last_error_name, episode.last_error):
            text = (
                f"Polling getUpdates recovered after {minutes:.1f} min "
                f"(bot id={key}, last error: {episode.last_error_name}: {episode.last_error})"
            )
            return SuccessVerdict(
                emit_recovery_info=False,
                recovery_message=text,
                emit_recovery_warning=True,
            )
        return SuccessVerdict(emit_recovery_info=False, recovery_message=None)

    def reset(self) -> None:
        with self._lock:
            self._episodes.clear()


_tracker = PollingEpisodeTracker()
_pending_failures: deque[tuple[str, str]] = deque()
_pending_lock = threading.Lock()
_filter_installed = False


def get_tracker() -> PollingEpisodeTracker:
    return _tracker


def parse_failed_fetch(message: str) -> tuple[str, str] | None:
    m = _FAILED_RE.search(message or "")
    if not m:
        if "Failed to fetch updates" in (message or ""):
            return "Unknown", message
        return None
    return m.group(1), m.group(2)


def parse_bot_id(message: str) -> int | None:
    m = _BOT_ID_RE.search(message or "")
    return int(m.group(1)) if m else None


def process_dispatcher_record(
    record: logging.LogRecord,
    tracker: PollingEpisodeTracker | None = None,
    now: float | None = None,
    pending: deque[tuple[str, str]] | None = None,
) -> list[tuple[int, str]]:
    """Mutate an aiogram.dispatcher record and return extra (level, message) logs."""
    tracker = tracker if tracker is not None else _tracker
    pending = pending if pending is not None else _pending_failures
    extras: list[tuple[int, str]] = []
    try:
        message = record.getMessage()
    except Exception:
        return extras

    failed = parse_failed_fetch(message)
    if record.levelno >= logging.ERROR and failed is not None:
        error_name, detail = failed
        pending.append((error_name, detail))
        if _is_quiet_failure(error_name, detail) or _is_quiet_failure(error_name, message):
            record.levelno = logging.WARNING
            record.levelname = "WARNING"
            record.skip_error_buffer = True
        return extras

    if "Sleep for" in message and "bot id" in message:
        bot_id = parse_bot_id(message)
        if pending:
            error_name, detail = pending.popleft()
        else:
            error_name, detail = "Unknown", message
        verdict = tracker.record_failure(bot_id, error_name, detail, now=now)
        record.skip_error_buffer = True
        if verdict.emit_episode_error and verdict.episode_error_message:
            extras.append((logging.ERROR, verdict.episode_error_message))
        return extras

    if "Connection established" in message and "bot id" in message:
        bot_id = parse_bot_id(message)
        verdict = tracker.record_success(bot_id, now=now)
        if verdict.recovery_message:
            if verdict.emit_recovery_warning:
                extras.append((logging.WARNING, verdict.recovery_message))
            elif verdict.emit_recovery_info:
                extras.append((logging.INFO, verdict.recovery_message))
    return extras


class PollingDispatcherFilter(logging.Filter):
    """Downgrade isolated getUpdates timeouts / short-lived 409s on aiogram.dispatcher."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "aiogram.dispatcher":
            return True
        extras = process_dispatcher_record(record)
        for level, text in extras:
            logger.log(level, text)
        return True


def install_polling_log_filter() -> None:
    """Attach the filter once to aiogram.dispatcher (idempotent)."""
    global _filter_installed
    lg = logging.getLogger("aiogram.dispatcher")
    for existing in lg.filters:
        if isinstance(existing, PollingDispatcherFilter):
            _filter_installed = True
            return
    lg.addFilter(PollingDispatcherFilter())
    _filter_installed = True
