"""«Приведи продавця»: binding, self-referral guard, free «Перевірено TgSell», credit, one reward per seller."""
from __future__ import annotations

import importlib

import pytest
from sqlalchemy import func, select

from tests.test_paid_services import _setup
from tests.test_promo_top import frozen  # noqa: F401
from tests.test_promo_top_paid import _mock_bot

pytestmark = pytest.mark.asyncio


async def _users(orm):
    from app.models.user import User, UserRole
    async with orm.session() as db:
        u = {"ref": User(first_name="R", username="ref", telegram_id=401, ref_code="refcode1"),
             "new": User(first_name="N", username="new", telegram_id=402),
             "new2": User(first_name="M", username="new2", telegram_id=403),
             "adm": User(first_name="A", username="adm", telegram_id=499, role=UserRole.admin)}
        db.add_all(u.values())
        await db.commit()
        return u


async def _lot(orm, seller, link, subs=100, status="approved", **kw):
    from app.models.channel import Channel, ChannelStatus
    async with orm.session() as db:
        c = Channel(seller_id=seller.id, telegram_link=link, channel_name=link[-4:], category="Спорт",
                    subscribers_count=subs, price=10, status=ChannelStatus(status), first_approved_at=None, **kw)
        db.add(c)
        await db.commit()
        return c.id


async def _submit(client, cur, user, link, ref="refcode1"):
    cur.user = user
    r = await client.post("/api/channels", json={"telegram_link": link, "channel_name": "x", "category": "Спорт",
                                                 "price": 50, "ref_code": ref})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _approve(client, cur, adm, cid):
    cur.user = adm
    r = await client.post(f"/api/admin/channels/{cid}/approve")
    assert r.status_code == 200, r.text


async def _get(orm, model, i):
    async with orm.session() as db:
        return await db.get(model, i)


async def _env(orm, monkeypatch):
    _mock_bot(monkeypatch)
    from app.config import settings
    monkeypatch.setattr(settings, "promo_top_until", "2000-01-01T00:00:00")  # promo off: isolate referral
    return await _setup(orm, monkeypatch)


async def test_reward_goes_to_biggest_unbadged_lot(orm, monkeypatch, frozen):  # noqa: F811
    from app.models.channel import Channel
    from app.models.user import User
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    small = await _lot(orm, u["ref"], "https://t.me/r_small", subs=100)
    big_badged = await _lot(orm, u["ref"], "https://t.me/r_bigb", subs=9000, tgsell_verified=True)
    big = await _lot(orm, u["ref"], "https://t.me/r_big", subs=5000)
    cid = await _submit(client, cur, u["new"], "https://t.me/new_one")
    assert (await _get(orm, Channel, cid)).referrer_id == u["ref"].id
    assert (await _get(orm, User, u["new"].id)).referred_by_id == u["ref"].id
    await _approve(client, cur, u["adm"], cid)
    assert (await _get(orm, Channel, big)).tgsell_verified is True
    assert (await _get(orm, Channel, small)).tgsell_verified is False
    assert (await _get(orm, Channel, big_badged)).tgsell_verified is True
    from app.models.paid_service import PaidServiceOrder
    async with orm.session() as db:
        assert (await db.execute(select(func.count(PaidServiceOrder.id)))).scalar() == 0  # free, no payment row


async def test_one_reward_per_referred_seller_first_approval_only(orm, monkeypatch, frozen):  # noqa: F811
    from app.models.channel import Channel, ChannelStatus
    from app.models.referral import ReferralReward
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    a = await _lot(orm, u["ref"], "https://t.me/r_a", subs=10)
    b = await _lot(orm, u["ref"], "https://t.me/r_b", subs=20)
    c1 = await _submit(client, cur, u["new"], "https://t.me/n_1")
    await _approve(client, cur, u["adm"], c1)
    async with orm.session() as db:  # re-moderation of the same lot
        (await db.get(Channel, c1)).status = ChannelStatus.pending
        await db.commit()
    await _approve(client, cur, u["adm"], c1)
    c2 = await _submit(client, cur, u["new"], "https://t.me/n_2", ref=None)  # 2nd lot of the same referred seller
    await _approve(client, cur, u["adm"], c2)
    async with orm.session() as db:
        assert (await db.execute(select(func.count(ReferralReward.id)))).scalar() == 1
    assert (await _get(orm, Channel, b)).tgsell_verified is True
    assert (await _get(orm, Channel, a)).tgsell_verified is False


async def test_credit_when_no_unbadged_lot_then_applied_to_next_lot(orm, monkeypatch, frozen):  # noqa: F811
    from app.models.channel import Channel
    from app.models.referral import ReferralReward
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    await _lot(orm, u["ref"], "https://t.me/r_done", tgsell_verified=True)
    cid = await _submit(client, cur, u["new"], "https://t.me/n_x")
    await _approve(client, cur, u["adm"], cid)
    async with orm.session() as db:
        r = (await db.execute(select(ReferralReward))).scalar_one()
        assert r.status == "credit" and r.awarded_channel_id is None
    own = await _submit(client, cur, u["ref"], "https://t.me/r_next", ref=None)
    await _approve(client, cur, u["adm"], own)
    assert (await _get(orm, Channel, own)).tgsell_verified is True
    async with orm.session() as db:
        r = (await db.execute(select(ReferralReward))).scalar_one()
        assert r.status == "applied" and r.awarded_channel_id == own


async def test_credit_when_referrer_has_no_lots(orm, monkeypatch, frozen):  # noqa: F811
    from app.models.referral import ReferralReward
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    await _approve(client, cur, u["adm"], await _submit(client, cur, u["new"], "https://t.me/n_y"))
    async with orm.session() as db:
        assert (await db.execute(select(ReferralReward.status))).scalar_one() == "credit"


@pytest.mark.parametrize("case", ["same_user", "same_tg", "same_channel"])
async def test_self_referral_blocked(orm, monkeypatch, frozen, case):  # noqa: F811
    from app.models.channel import Channel
    from app.models.referral import ReferralReward
    from app.models.user import User
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    mine = await _lot(orm, u["ref"], "https://t.me/r_mine")
    submitter, link = u["new"], "https://t.me/n_z"
    if case == "same_user":
        submitter = u["ref"]
    elif case == "same_tg":
        async with orm.session() as db:  # a second account sharing the referrer's telegram_id
            twin = User(first_name="T", username="twin", google_id="g-twin")
            db.add(twin)
            await db.commit()
        twin = await _get(orm, User, twin.id)
        twin.telegram_id = u["ref"].telegram_id  # simulated (unique in DB): checked in memory
        from app.services import referral
        async with orm.session() as db:
            assert await referral.is_self_referral(db, u["ref"], twin, "https://t.me/other") is True
        return
    else:
        link = "https://t.me/r_mine"  # referrer already has this channel
        async with orm.session() as db:
            from app.models.channel import ChannelStatus
            (await db.get(Channel, mine)).status = ChannelStatus.sold  # so a new listing is allowed
            await db.commit()
    cid = await _submit(client, cur, submitter, link)
    assert (await _get(orm, Channel, cid)).referrer_id is None
    await _approve(client, cur, u["adm"], cid)
    async with orm.session() as db:
        assert (await db.execute(select(func.count(ReferralReward.id)))).scalar() == 0
    assert (await _get(orm, User, submitter.id)).referred_by_id is None


async def test_first_referrer_wins_and_unknown_code_ignored(orm, monkeypatch, frozen):  # noqa: F811
    from app.models.channel import Channel
    from app.models.user import User
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    c0 = await _submit(client, cur, u["new2"], "https://t.me/q_0", ref="nope")
    assert (await _get(orm, Channel, c0)).referrer_id is None
    async with orm.session() as db:
        (await db.get(User, u["new"].id)).ref_code = "othercode"
        await db.commit()
    c1 = await _submit(client, cur, u["new2"], "https://t.me/q_1", ref="refcode1")
    c2 = await _submit(client, cur, u["new2"], "https://t.me/q_2", ref="othercode")
    assert (await _get(orm, Channel, c1)).referrer_id == u["ref"].id
    assert (await _get(orm, Channel, c2)).referrer_id == u["ref"].id


async def test_my_referral_link(orm, monkeypatch):
    from fastapi import FastAPI
    db_mod = importlib.import_module("app.database")
    sec = importlib.import_module("app.utils.security")
    me = importlib.import_module("app.routers.me")
    from httpx import ASGITransport, AsyncClient
    u = await _users(orm)
    app = FastAPI()
    app.include_router(me.router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = orm.get_db

    async def cur():
        async with orm.session() as db:
            from app.models.user import User
            return await db.get(User, u["new"].id)
    app.dependency_overrides[sec.get_current_user] = cur
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        j1 = (await c.get("/api/me/referral")).json()
        j2 = (await c.get("/api/me/referral")).json()
    assert j1["code"] == j2["code"] and len(j1["code"]) == 8 and j1["link"].endswith(f"/?ref={j1['code']}")
