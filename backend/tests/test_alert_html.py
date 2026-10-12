"""Every admin alert must be valid Telegram HTML (no bare < > & outside allowed tags).

Regression: "can't parse entities: Unsupported start tag" for the master-TRX-low alert
("8.64 TRX < 30 TRX") and escrow alerts with "<" / exception text.
"""
from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.utils.timeutil import utcnow_naive
from tests.test_unified_payouts import SELLER_W, env  # noqa: F401


def _alerts():
    return importlib.import_module("app.services.alerts")


@pytest.mark.parametrize("raw", [
    "8.64 TRX < 30 TRX",
    "a > b & c",
    "<script>x</script>",
    "<b>bold</b> & <code>x<y</code>",
    "error: <class 'RuntimeError'> & more",
    "&amp; &lt; &#123; ok",
    "<a href=\"https://t.me/x\">link</a> < 5",
    "<unknown> <b",
])
def test_sanitizer_output_always_valid(raw):
    a = _alerts()
    out = a.telegram_html_safe(raw)
    assert a.is_valid_telegram_html(out), out


def test_sanitizer_keeps_allowed_markup_and_entities():
    a = _alerts()
    s = "<b>x</b> <code>y</code> <i>z</i> &lt; &amp;"
    assert a.telegram_html_safe(s) == s
    assert a.telegram_html_safe("1 < 2") == "1 &lt; 2"
    assert a.telegram_html_safe(a.telegram_html_safe("a<b&c")) == "a&lt;b&amp;c"  # idempotent


def test_validator_rejects_bare_and_unbalanced():
    a = _alerts()
    assert not a.is_valid_telegram_html("8.64 TRX < 30 TRX")
    assert not a.is_valid_telegram_html("<b>open")
    assert not a.is_valid_telegram_html("a & b")
    assert a.is_valid_telegram_html("<b>ok</b> &lt; fine")


class _CaptureBot:
    sent: list[str] = []

    def __init__(self, token=None, **_):
        self.session = SimpleNamespace(close=AsyncMock())

    async def send_message(self, chat_id, text, **_):
        _CaptureBot.sent.append(text)


@pytest.fixture
def capture(monkeypatch):
    a = _alerts()
    monkeypatch.setattr(a, "Bot", _CaptureBot)
    monkeypatch.setattr(a.settings, "bot_token_alerts", "1:x")
    monkeypatch.setattr(a.settings, "admin_group_id", -1)
    a._last_alerts.clear()
    _CaptureBot.sent = []
    yield a
    a._last_alerts.clear()


@pytest.mark.asyncio
async def test_alerts_module_texts_valid(capture):
    a = capture
    await a.send_admin_alert("raw 1 < 2 & <weird>")
    await a.alert_service_down("Svc<1>", "boom <class 'X'> & y")
    await a.alert_service_recovered("Svc<1>")
    a.reset_telethon_alert_state()
    await a.alert_telethon_session_down("authkey_duplicated", "detail <x> & y")
    await a.alert_telethon_session_recovered()
    await a.alert_stats_summary(10, 7, 3, False)
    assert len(_CaptureBot.sent) >= 5
    for t in _CaptureBot.sent:
        assert a.is_valid_telegram_html(t), t


@pytest.mark.asyncio
async def test_master_trx_low_alert_text_valid_and_throttled(pg_orm, capture, monkeypatch):
    pw = importlib.import_module("app.tasks.payout_worker")
    escrow = importlib.import_module("app.services.escrow")
    monkeypatch.setattr(escrow, "get_trx_balance", lambda a: 8.64)
    monkeypatch.setattr(pw.settings, "tron_master_wallet_address", "TUExqjcYXyftLqRWzBBigkeXyzY8pTGAkn")
    await pw.check_master_trx()
    await pw.check_master_trx()  # throttled (same alert_key)
    assert len(_CaptureBot.sent) == 1
    assert "&lt; 30 TRX" in _CaptureBot.sent[0]
    assert capture.is_valid_telegram_html(_CaptureBot.sent[0])


@pytest.mark.asyncio
async def test_payout_alert_texts_valid_raw(env):
    """Raw texts built by payouts (before the sanitizer) are already valid HTML."""
    a = _alerts()
    # refused: insufficient escrow ("<" in message) and unknown balance (exception text)
    d1, e1 = await env.make_deal(env.S.awaiting_payout)
    env.tron.balances[e1] = 1
    await env.seller_wallet(d1)
    d2, e2 = await env.make_deal(env.S.awaiting_payout)
    env.tron.balances[e2] = RuntimeError("<html>429 & co</html>")
    await env.seller_wallet(d2)
    # FAILED receipt with odd reason, PENDING, master TRX precheck
    d3, _ = await env.make_deal(env.S.awaiting_payout)
    env.tron.default_receipt = {"status": "FAILED", "reason": "REVERT <x> & y"}
    await env.seller_wallet(d3)
    d4, e4 = await env.make_deal(env.S.awaiting_payout)
    env.tron.default_receipt = {"status": "PENDING", "reason": "not found"}
    await env.seller_wallet(d4)
    env.tron.balances[e4] = 0
    await env.reconcile(utcnow_naive() + timedelta(hours=1))  # unresolved alert ("&gt;")
    d5, _ = await env.make_deal(env.S.awaiting_payout)
    env.tron.gas_result = {"ok": False, "reason": "MASTER_INSUFFICIENT_TRX", "message": "8.64 TRX < 18.9 TRX"}
    with pytest.raises(Exception):
        await env.seller_wallet(d5)
    texts = [c.args[0] for c in env.alert.await_args_list]
    assert len(texts) >= 5
    for t in texts:
        assert a.is_valid_telegram_html(t), t
