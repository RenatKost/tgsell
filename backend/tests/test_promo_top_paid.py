"""Promo Top vs paid Top: slot limit, ordering, promo→paid upgrade, single-lot approval message."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from tests.test_paid_services import _setup, _wallet
from tests.test_promo_top import _approve, _cfg, _seed_pending, frozen  # noqa: F401

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 10, 27, 10, 0)


async def _seed_lots(orm, specs):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User
    async with orm.session() as db:
        seller = User(first_name="S", username="s", telegram_id=21)
        db.add(seller)
        await db.flush()
        chs = [Channel(seller_id=seller.id, telegram_link=f"https://t.me/l{i}", channel_name=f"L{i}", category="Спорт",
                       subscribers_count=1000 + i, price=100 + i, status=ChannelStatus.approved, **kw)
               for i, kw in enumerate(specs)]
        db.add_all(chs)
        await db.commit()
        return seller, [c.id for c in chs]


async def test_slot_limit_ignores_promo(orm):
    from app.services import paid_services as svc
    from app.models.channel import Channel
    up = NOW + timedelta(days=5)
    seller, ids = await _seed_lots(orm, [dict(top_until=up, top_source="promo")] * 5
                                   + [dict(top_until=up, top_source="paid"), {}])
    async with orm.session() as db:
        assert await svc.top_slots_taken(db, NOW) == 1
        ch = await db.get(Channel, ids[-1])
        o = await svc.create_order(db, seller_id=seller.id, channel=ch, kind="top", now=NOW, wallet_factory=_wallet)
        assert o.id
        promo_ch = await db.get(Channel, ids[0])  # a promo-Top lot can still buy paid Top
        o2 = await svc.create_order(db, seller_id=seller.id, channel=promo_ch, kind="top", now=NOW, wallet_factory=_wallet)
        assert o2.id


async def test_order_paid_then_promo_then_rest(orm, monkeypatch):
    from app.services import paid_services as svc
    from app.models.channel import Channel
    up = NOW + timedelta(days=3)
    _, ids = await _seed_lots(orm, [{}, dict(top_until=up, top_source="promo"), dict(top_until=up, top_source="paid"),
                                    dict(top_until=NOW - timedelta(days=1), top_source="paid"), dict(top_until=up)])
    async with orm.session() as db:
        rows = (await db.execute(select(Channel.id).order_by(svc.top_rank_expr(NOW), Channel.id))).scalars().all()
    assert rows == [ids[2], ids[4], ids[1], ids[0], ids[3]]


async def test_public_listing_order(orm, monkeypatch):
    client, cur = await _setup(orm, monkeypatch)
    from datetime import datetime as real
    up = real.utcnow() + timedelta(days=3)
    _, ids = await _seed_lots(orm, [{}, dict(top_until=up, top_source="promo"), dict(top_until=up, top_source="paid")])
    r = await client.get("/api/channels", params={"sort": "newest"})
    assert r.status_code == 200, r.text
    got = [c["id"] for c in r.json()["items"]]
    assert got[:3] == [ids[2], ids[1], ids[0]]


@pytest.mark.parametrize("promo_days,expect_days", [(2, 7), (10, 10)])
async def test_promo_upgrade_to_paid_takes_longer(orm, promo_days, expect_days):
    from app.services import paid_services as svc
    from app.models.channel import Channel
    seller, ids = await _seed_lots(orm, [dict(top_until=NOW + timedelta(days=promo_days), top_source="promo")])
    async with orm.session() as db:
        ch = await db.get(Channel, ids[0])
        o = await svc.create_order(db, seller_id=seller.id, channel=ch, kind="top", now=NOW, wallet_factory=_wallet)
        await svc.mark_paid(db, o, 10.0, NOW)
        assert ch.top_source == "paid"
        assert ch.top_until == o.active_until == NOW + timedelta(days=expect_days)


class _Bot:
    sent: list = []

    def __init__(self, token=None):
        self.session = self

    async def close(self):
        pass

    async def send_message(self, chat_id, text, **kw):
        _Bot.sent.append((chat_id, text))


def _mock_bot(monkeypatch, fail=False):
    import aiogram
    _Bot.sent = []

    class B(_Bot):
        async def send_message(self, chat_id, text, **kw):
            if fail:
                raise RuntimeError("telegram down")
            await super().send_message(chat_id, text, **kw)
    monkeypatch.setattr(aiogram, "Bot", B)
    return _Bot.sent


@pytest.mark.parametrize("until,promo", [("2026-11-01T23:59:00", True), ("2026-10-01T00:00:00", False)])
async def test_single_lot_approval_message(orm, monkeypatch, frozen, until, promo):  # noqa: F811
    _cfg(monkeypatch, until)
    sent = _mock_bot(monkeypatch)
    client, cur = await _setup(orm, monkeypatch)
    adm, cid = await _seed_pending(orm)
    await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert len(sent) == 1
    chat, text = sent[0]
    assert chat == 11
    assert "Ваш лот схвалено" in text and "«P»" in text and f"/channel/{cid}" in text and "/cabinet" in text
    assert ("🎁 Акція: ваш лот отримав «Топ» на 7 днів безкоштовно" in text) is promo


async def test_approval_message_once_per_approval_and_failure_safe(orm, monkeypatch, frozen):  # noqa: F811
    _cfg(monkeypatch)
    _mock_bot(monkeypatch, fail=True)
    client, cur = await _setup(orm, monkeypatch)
    adm, cid = await _seed_pending(orm)
    ch = await _approve(orm, monkeypatch, client, cur, adm, cid)  # asserts 200 despite Telegram failure
    assert ch.status.value == "approved" and ch.top_source == "promo"
    sent = _mock_bot(monkeypatch)
    from app.models.channel import Channel, ChannelStatus
    async with orm.session() as db:
        c = await db.get(Channel, cid)
        c.status = ChannelStatus.pending
        await db.commit()
    await _approve(orm, monkeypatch, client, cur, adm, cid)
    assert len(sent) == 1 and "🎁" not in sent[0][1]  # re-approval: one message, no second gift
