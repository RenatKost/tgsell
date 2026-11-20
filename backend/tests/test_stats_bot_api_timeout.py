"""P2 20.11: Bot API timeouts in channel_stats — short retry, WARNING on recovery, ERROR only when repeated."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock

import httpx
import pytest


def test_timeout_classification():
    from app.services.channel_stats import is_bot_api_timeout
    req = httpx.Request("GET", "https://api.telegram.org/x")
    assert is_bot_api_timeout(httpx.ConnectTimeout("t", request=req))
    assert is_bot_api_timeout(httpx.ReadTimeout("t", request=req))
    assert is_bot_api_timeout(httpx.PoolTimeout("t"))
    assert is_bot_api_timeout(asyncio.TimeoutError())
    assert is_bot_api_timeout(TimeoutError())

    class ServerTimeoutError(Exception):  # aiohttp-like name
        pass
    assert is_bot_api_timeout(ServerTimeoutError())
    assert not is_bot_api_timeout(httpx.ConnectError("refused", request=req))
    assert not is_bot_api_timeout(ValueError("x"))


def test_log_level():
    from app.services import channel_stats as cs
    assert cs.bot_api_timeout_log_level(False, 0) == logging.WARNING
    assert cs.bot_api_timeout_log_level(True, 1) == logging.WARNING
    assert cs.bot_api_timeout_log_level(True, cs.BOT_API_TIMEOUT_ERROR_STREAK) == logging.ERROR


class _Resp:
    status_code = 200

    def __init__(self, result):
        self._r = result

    def json(self):
        return {"ok": True, "result": self._r}


def _http(fail_times: int | None, calls: list):
    """Fake httpx client: first `fail_times` GETs time out (None = always)."""
    class _Http:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            calls.append(url)
            if fail_times is None or len(calls) <= fail_times:
                raise httpx.ConnectTimeout("timed out", request=httpx.Request("GET", "https://x"))
            return _Resp(5 if url.endswith("getChatMemberCount") else {"title": "Chan"})
    return _Http


@pytest.fixture
def cs(monkeypatch):
    from app.services import channel_stats as cs
    monkeypatch.setattr(cs.settings, "bot_token_stats", "123456789:AAH" + "z" * 32)
    monkeypatch.setattr(cs, "BOT_API_TIMEOUT_BACKOFF_SEC", (0.0, 0.0))
    monkeypatch.setattr(cs, "_bot_api_timeout_streak", 0)
    return cs


@pytest.mark.asyncio
async def test_recovered_after_retry_is_warning(cs, monkeypatch, caplog):
    calls: list = []
    monkeypatch.setattr(httpx, "AsyncClient", _http(1, calls))
    with caplog.at_level(logging.INFO, logger="app.services.channel_stats"):
        info = await cs.get_channel_info_bot_api("somechan")
    assert info["name"] == "Chan" and info["subscribers_count"] == 5
    assert len(calls) == 3  # getChat timeout + retry + getChatMemberCount
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(r.levelno == logging.WARNING and "recovered" in r.getMessage() for r in caplog.records)
    assert cs._bot_api_timeout_streak == 0


@pytest.mark.asyncio
async def test_single_exhausted_timeout_is_warning_repeated_is_error(cs, monkeypatch, caplog):
    calls: list = []
    monkeypatch.setattr(httpx, "AsyncClient", _http(None, calls))
    monkeypatch.setattr(cs, "get_channel_stats_telethon", AsyncMock(return_value=None))
    token = cs.settings.bot_token_stats
    with caplog.at_level(logging.INFO, logger="app.services.channel_stats"):
        assert await cs.get_channel_info_bot_api("c1") is None
        assert len(calls) == 1 + cs.BOT_API_TIMEOUT_RETRIES
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert await cs.get_channel_info_bot_api("c2") is None
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert await cs.get_channel_info_bot_api("c3") is None  # 3 channels in a row → ERROR
    errs = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errs) == 1 and "timed out" in errs[0].getMessage()
    assert all(token not in r.getMessage() for r in caplog.records)
    # recovery resets the streak and is logged as WARNING
    calls.clear()
    monkeypatch.setattr(httpx, "AsyncClient", _http(0, calls))
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.services.channel_stats"):
        assert (await cs.get_channel_info_bot_api("c4"))["name"] == "Chan"
    assert cs._bot_api_timeout_streak == 0
    assert any(r.levelno == logging.WARNING and "recovered" in r.getMessage() for r in caplog.records)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.asyncio
async def test_non_timeout_error_still_error(cs, monkeypatch, caplog):
    class _Http:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            raise httpx.ConnectError("refused", request=httpx.Request("GET", "https://x"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Http())
    with caplog.at_level(logging.INFO, logger="app.services.channel_stats"):
        assert await cs.get_channel_info_bot_api("c5") is None
    assert [r for r in caplog.records if r.levelno >= logging.ERROR]
