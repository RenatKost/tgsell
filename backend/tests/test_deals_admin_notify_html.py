"""Admin-group / party notifications triggered from routers/deals.py must be valid Telegram HTML
even with hostile user content (deal #29: "can't parse entities: Unexpected end tag")."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

EVIL = "</b><i>Evil & <a href='x'>Co</a> <3"


class Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


@pytest.fixture
def bm(monkeypatch):
    m = importlib.import_module("bot.main")
    monkeypatch.setattr(m.settings, "admin_group_id", -100123)
    monkeypatch.setattr(m.settings, "frontend_url", "https://tgsell.me/")
    return m


def _ok(texts):
    alerts = importlib.import_module("app.services.alerts")
    for _, t in texts:
        assert alerts.is_valid_telegram_html(t), t
        assert "</b><i>" not in t and "&lt;/b&gt;" in t


@pytest.mark.asyncio
async def test_admin_called_escapes(bm):
    b = Bot()
    await bm.notify_admin_called(b, 29, EVIL, EVIL)
    _ok(b.sent)
    assert 'href="https://tgsell.me/deal/29"' in b.sent[0][1]


@pytest.mark.asyncio
async def test_new_deal_escapes(bm):
    b = Bot()
    buyer = SimpleNamespace(id=1, telegram_id=11, first_name=EVIL)
    seller = SimpleNamespace(id=2, telegram_id=22, first_name=EVIL)
    deal = SimpleNamespace(id=29, amount_usdt=10.0, escrow_wallet_address="TAddr")
    await bm.notify_new_deal(b, deal, buyer, seller)
    admin = [x for x in b.sent if x[0] == -100123]
    assert admin and len(b.sent) == 3
    _ok(admin)
    alerts = importlib.import_module("app.services.alerts")
    assert all(alerts.is_valid_telegram_html(t) for _, t in b.sent)


@pytest.mark.asyncio
async def test_new_bundle_deal_escapes(bm):
    b = Bot()
    buyer = SimpleNamespace(id=1, telegram_id=11, first_name=EVIL)
    seller = SimpleNamespace(id=2, telegram_id=22, first_name="S")
    bundle = SimpleNamespace(id=5, name=EVIL)
    deal = SimpleNamespace(id=29, amount_usdt=10.0)
    await bm.notify_new_bundle_deal(b, deal, bundle, buyer, seller)
    assert len(b.sent) == 2
    _ok(b.sent)
