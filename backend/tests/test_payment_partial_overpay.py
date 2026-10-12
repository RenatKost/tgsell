"""Task 14 PR A: partial payment chat info + overpayment detection (payment checker)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.test_payment_checker import env  # noqa: F401


async def _sys(env, deal_id, event):
    from app.models.deal import DealMessage

    async with env.orm.session() as db:
        return list((await db.execute(select(DealMessage).where(
            DealMessage.deal_id == deal_id, DealMessage.event == event).order_by(DealMessage.id))).scalars())


@pytest.mark.asyncio
async def test_partial_payment_chat_message_once_per_amount(env):
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=1)
    env.chain.balances[addr] = 5.0
    for _ in range(3):
        await env.pc.check_payments_once()
    msgs = await _sys(env, deal_id, "payment_partial")
    assert len(msgs) == 1
    t = msgs[0].text
    assert "Отримано 5 з 15 USDT" in t and "Доплатіть 10 USDT" in t and "комісію за виведення" in t
    d = await env.get(deal_id)
    assert d.received_usdt == 5.0 and d.status == env.S.payment_pending
    env.chain.balances[addr] = 14.5
    await env.pc.check_payments_once()
    await env.pc.check_payments_once()
    msgs = await _sys(env, deal_id, "payment_partial")
    assert len(msgs) == 2 and "Доплатіть 0.5 USDT" in msgs[1].text
    assert d.overpay_units is None


@pytest.mark.asyncio
async def test_overpay_recorded_with_chat_message(env):
    deal_id, addr = await env.make_deal(env.S.payment_pending, age_hours=1)
    env.chain.balances[addr] = 17.3
    await env.pc.check_payments_once()
    d = await env.get(deal_id)
    assert d.status == env.S.paid and d.overpay_units == 2_300_000 and d.overpay_status == "awaiting_address"
    assert d.service_fee == pytest.approx(0.45)  # fee from price, not overpay
    (m,) = await _sys(env, deal_id, "overpay_detected")
    assert "Переплата 2.3 USDT" in m.text and "буде повернена" in m.text
    await env.pc.check_payments_once()
    assert len(await _sys(env, deal_id, "overpay_detected")) == 1


@pytest.mark.asyncio
async def test_exact_and_dust_overpay_not_recorded(env):
    a, addr_a = await env.make_deal(env.S.payment_pending, age_hours=1)
    b, addr_b = await env.make_deal(env.S.payment_pending, age_hours=1)
    env.chain.balances[addr_a] = 15.0
    env.chain.balances[addr_b] = 15.05
    await env.pc.check_payments_once()
    for i in (a, b):
        d = await env.get(i)
        assert d.status == env.S.paid and d.overpay_units is None and d.overpay_status is None
