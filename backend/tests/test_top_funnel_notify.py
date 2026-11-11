"""Top funnel: approve deep-link, one seller notice after activation, Telegram failure is isolated."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from tests.test_paid_services import _pay_all, _seed, _setup


def test_approve_text_has_cabinet_top_deep_link_and_escapes_name(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "frontend_url", "https://tgsell.me")
    from bot.main import (
        _kyiv_dt_label,
        channel_approved_cabinet_top_url,
        channel_approved_text,
        channel_approved_top_keyboard,
        top_activated_text,
    )

    ch = SimpleNamespace(id=42, channel_name="Кіно <b>Evil</b> & Co")
    text = channel_approved_text(ch, promo_top=False)
    assert "https://tgsell.me/cabinet?top=42" in text
    assert "<b>Evil</b>" not in text
    assert html.escape("Кіно <b>Evil</b> & Co") in text
    assert "Підняти в Топ" in text
    assert channel_approved_cabinet_top_url(ch) == "https://tgsell.me/cabinet?top=42"
    kb = channel_approved_top_keyboard(ch)
    btn = kb.inline_keyboard[0][0]
    assert btn.url == "https://tgsell.me/cabinet?top=42" and btn.text == "Підняти в Топ"

    until = datetime(2026, 11, 18, 14, 35, tzinfo=timezone.utc)
    assert _kyiv_dt_label(until.replace(tzinfo=None)) == "18.11.2026, 16:35"
    activated = top_activated_text(ch, until.replace(tzinfo=None))
    assert "Топ увімкнено" in activated
    assert "18.11.2026, 16:35" in activated
    assert "Київ" in activated
    assert "/channel/42" in activated
    assert "<b>Evil</b>" not in activated
    assert html.escape("Кіно <b>Evil</b> & Co") in activated


async def _patch_notify(monkeypatch, svc, impl):
    """Make check_orders_once's post-commit hook use `impl` as the Telegram sender."""
    real = svc.notify_pending_top_activations

    async def hooked(session_factory, now=None, notify=None):
        return await real(session_factory, now=now, notify=notify or impl)

    monkeypatch.setattr(svc, "notify_pending_top_activations", hooked)


@pytest.mark.asyncio
async def test_top_activation_notifies_seller_once(orm, monkeypatch):
    from app.models.channel import Channel
    from app.models.paid_service import PaidServiceOrder
    from app.services import paid_services as svc

    client, cur = await _setup(orm, monkeypatch)
    seller, _adm, _other, ids = await _seed(orm, n=1)
    notify = AsyncMock(return_value=True)
    await _patch_notify(monkeypatch, svc, notify)

    async with client:
        cur.user = seller
        posted = await client.post("/api/services/orders", json={"channel_id": ids[0], "kind": "top"})
        assert posted.status_code == 201
        oid = posted.json()["id"]

    st = await _pay_all(orm)
    assert st["paid"] == 1
    assert notify.await_count == 1
    channel, seller_arg, until = notify.await_args.args
    assert channel.id == ids[0] and seller_arg.id == seller.id and until is not None

    async with orm.session() as db:
        o = await db.get(PaidServiceOrder, oid)
        ch = await db.get(Channel, ids[0])
        assert o.status == "active" and o.seller_notified_at is not None
        assert ch.top_until is not None and ch.top_source == "paid"

    st2 = await _pay_all(orm)
    assert st2["paid"] == 0
    assert notify.await_count == 1


@pytest.mark.asyncio
async def test_telegram_failure_does_not_rollback_activation_and_retries(orm, monkeypatch):
    from app.models.channel import Channel
    from app.models.paid_service import PaidServiceOrder
    from app.services import paid_services as svc

    client, cur = await _setup(orm, monkeypatch)
    seller, _adm, _other, ids = await _seed(orm, n=1)
    fail = AsyncMock(side_effect=RuntimeError("telegram down"))
    await _patch_notify(monkeypatch, svc, fail)

    async with client:
        cur.user = seller
        posted = await client.post("/api/services/orders", json={"channel_id": ids[0], "kind": "top"})
        assert posted.status_code == 201
        oid = posted.json()["id"]

    st = await _pay_all(orm)
    assert st["paid"] == 1
    async with orm.session() as db:
        o = await db.get(PaidServiceOrder, oid)
        ch = await db.get(Channel, ids[0])
        assert o.status == "active"
        assert o.seller_notified_at is None
        assert ch.top_until is not None and ch.top_source == "paid"

    ok = AsyncMock(return_value=True)
    await _patch_notify(monkeypatch, svc, ok)
    st2 = await _pay_all(orm)
    assert st2["paid"] == 0
    assert ok.await_count == 1
    async with orm.session() as db:
        o = await db.get(PaidServiceOrder, oid)
        ch = await db.get(Channel, ids[0])
        assert o.status == "active" and o.seller_notified_at is not None
        assert ch.top_until is not None
