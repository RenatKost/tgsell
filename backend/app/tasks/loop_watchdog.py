"""Event-loop lag watchdog (diagnostic only).

Trivial endpoints (/api/health, POST /api/auth/bot-token) were seen taking 5-22 s while
normally ~0.15 s. Those handlers do no I/O, so the delay is the single uvicorn event loop
being blocked by synchronous work somewhere else. This task measures how late a short
sleep wakes up and logs stalls (with the task names alive at that moment) so the blocker
can be pinpointed from logs. It does no network, DB or Telethon calls.
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)
_last_lag = {"max_ms": 0.0, "last_stall_ms": 0.0, "stalls": 0}


def loop_lag_snapshot() -> dict:
    return dict(_last_lag)


async def run_loop_watchdog(interval: float = 0.5, threshold: float = 1.0) -> None:
    while True:
        t0 = time.monotonic()
        await asyncio.sleep(interval)
        lag = time.monotonic() - t0 - interval
        if lag > threshold:
            _last_lag["stalls"] += 1
            _last_lag["last_stall_ms"] = round(lag * 1000)
            names = sorted({t.get_name() + ":" + getattr(t.get_coro(), "__qualname__", "?")
                            for t in asyncio.all_tasks()})[:30]
            logger.warning("[LOOP] event loop blocked %.1fs; tasks=%s", lag, names)
        _last_lag["max_ms"] = max(_last_lag["max_ms"], round(lag * 1000))
