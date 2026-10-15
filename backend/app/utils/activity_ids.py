"""Task 23: hashed anonymous ids + in-process rate limiter (no DB / models)."""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict


def hash_id(raw: str | None) -> str | None:
    raw = (raw or "").strip()
    if not raw or len(raw) > 128:
        return None
    return hashlib.sha256(("tgsell-act:" + raw).encode()).hexdigest()[:32]


class _RateLimiter:
    """In-process limiter (single Railway replica). Keys are hashed ids."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._window: dict[str, list[float]] = defaultdict(list)

    def min_interval(self, key: str, seconds: float, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        last = self._last.get(key)
        if last is not None and now - last < seconds:
            return False
        self._last[key] = now
        if len(self._last) > 50000:
            self._last.clear()
        return True

    def per_minute(self, key: str, limit: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        w = [t for t in self._window[key] if now - t < 60]
        if len(w) >= limit:
            self._window[key] = w
            return False
        w.append(now)
        self._window[key] = w
        if len(self._window) > 50000:
            self._window.clear()
        return True

    def reset(self) -> None:
        self._last.clear()
        self._window.clear()


limiter = _RateLimiter()
