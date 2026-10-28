import asyncio, time
from app.tasks import loop_watchdog as w


def test_watchdog_detects_blocking():
    async def main():
        t = asyncio.create_task(w.run_loop_watchdog(interval=0.05, threshold=0.2))
        await asyncio.sleep(0.1)
        time.sleep(0.4)  # simulate sync blocking call
        await asyncio.sleep(0.2)
        t.cancel()
    before = w.loop_lag_snapshot()["stalls"]
    asyncio.run(main())
    assert w.loop_lag_snapshot()["stalls"] > before
