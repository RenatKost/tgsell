"""«Приведи продавця»: binding, self-referral guard, free 7-day promo Top (no badge), credit, one reward per seller."""
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


from datetime import datetime, timedelta  # noqa: E402

NOW = datetime(2026, 10, 27, 10, 0)
TOP7 = NOW + timedelta(days=7)


def _has_ref_top(ch) -> bool:
    return ch.top_source == "promo" and ch.top_until is not None and ch.top_until >= TOP7 - timedelta(minutes=1)


async def test_reward_is_7d_promo_top_on_biggest_active_lot(orm, monkeypatch, frozen):  # noqa: F811
    from app.models.channel import Channel
    from app.models.user import User
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    small = await _lot(orm, u["ref"], "https://t.me/r_small", subs=100)
    big_sold = await _lot(orm, u["ref"], "https://t.me/r_bigs", subs=9000, status="sold")
    big = await _lot(orm, u["ref"], "https://t.me/r_big", subs=5000)
    cid = await _submit(client, cur, u["new"], "https://t.me/new_one")
    assert (await _get(orm, Channel, cid)).referrer_id == u["ref"].id
    assert (await _get(orm, User, u["new"].id)).referred_by_id == u["ref"].id
    await _approve(client, cur, u["adm"], cid)
    b = await _get(orm, Channel, big)
    assert _has_ref_top(b) and b.tgsell_verified is False  # NO free «Перевірено» badge
    assert (await _get(orm, Channel, small)).top_until is None
    assert (await _get(orm, Channel, big_sold)).top_until is None
    from app.models.paid_service import PaidServiceOrder
    async with orm.session() as db:
        assert (await db.execute(select(func.count(PaidServiceOrder.id)))).scalar() == 0  # free, no payment row
        n = (await db.execute(select(func.count(Channel.id)).where(Channel.tgsell_verified.is_(True)))).scalar()
        assert n == 0


async def test_referral_top_outside_paid_slot_limit(orm, monkeypatch, frozen):  # noqa: F811
    from app.models.channel import Channel
    from app.models.user import User
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    async with orm.session() as db:  # 3 paid Tops already occupy all slots
        o = User(first_name="O", username="o", telegram_id=777)
        db.add(o)
        await db.commit()
        oid = o.id
    for i in range(3):
        await _lot(orm, await _get(orm, User, oid), f"https://t.me/paid_{i}", top_until=TOP7 + timedelta(days=1),
                   top_source="paid")
    mine = await _lot(orm, u["ref"], "https://t.me/r_one")
    await _approve(client, cur, u["adm"], await _submit(client, cur, u["new"], "https://t.me/n_s"))
    assert _has_ref_top(await _get(orm, Channel, mine))


async def test_longer_existing_top_is_kept(orm, monkeypatch, frozen):  # noqa: F811
    from app.models.channel import Channel
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    longer = TOP7 + timedelta(days=10)
    mine = await _lot(orm, u["ref"], "https://t.me/r_long", top_until=longer, top_source="paid")
    await _approve(client, cur, u["adm"], await _submit(client, cur, u["new"], "https://t.me/n_l"))
    ch = await _get(orm, Channel, mine)
    assert ch.top_until == longer and ch.top_source == "paid"


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
    assert _has_ref_top(await _get(orm, Channel, b))
    assert (await _get(orm, Channel, a)).top_until is None


async def test_credit_when_no_active_lot_then_top_on_next_lot(orm, monkeypatch, frozen):  # noqa: F811
    from app.models.channel import Channel
    from app.models.referral import ReferralReward
    client, cur = await _env(orm, monkeypatch)
    u = await _users(orm)
    await _lot(orm, u["ref"], "https://t.me/r_done", status="sold")
    cid = await _submit(client, cur, u["new"], "https://t.me/n_x")
    await _approve(client, cur, u["adm"], cid)
    async with orm.session() as db:
        r = (await db.execute(select(ReferralReward))).scalar_one()
        assert r.status == "credit" and r.awarded_channel_id is None
    own = await _submit(client, cur, u["ref"], "https://t.me/r_next", ref=None)
    await _approve(client, cur, u["adm"], own)
    ch = await _get(orm, Channel, own)
    assert _has_ref_top(ch) and ch.tgsell_verified is False
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


async def test_migration_0056_revokes_only_referral_badges(orm):
    """0056 data step on the test DB: referral-granted badge removed, paid / unrelated badges kept,
    reward rows become Top credits."""
    import importlib.util
    import pathlib
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.models.channel import Channel, ChannelStatus
    from app.models.paid_service import PaidServiceOrder
    from app.models.referral import ReferralReward
    u = await _users(orm)
    async with orm.session() as db:
        mk = lambda link: Channel(seller_id=u["ref"].id, telegram_link=link, channel_name="x", category="Спорт",  # noqa: E731
                                  subscribers_count=1, price=10, status=ChannelStatus.approved, tgsell_verified=True)
        ref_lot, paid_lot, other = mk("https://t.me/m_1"), mk("https://t.me/m_2"), mk("https://t.me/m_3")
        db.add_all([ref_lot, paid_lot, other])
        await db.flush()
        db.add(PaidServiceOrder(kind="verified", channel_id=paid_lot.id, seller_id=u["ref"].id, price_usdt=20,
                                status="verified", escrow_wallet_address="T", escrow_private_key_encrypted="x"))
        db.add_all([
            ReferralReward(referrer_id=u["ref"].id, referred_user_id=u["new"].id, awarded_channel_id=ref_lot.id,
                           status="applied", created_at=NOW, applied_at=NOW),
            ReferralReward(referrer_id=u["ref"].id, referred_user_id=u["new2"].id, awarded_channel_id=paid_lot.id,
                           status="applied", created_at=NOW, applied_at=NOW)])
        await db.commit()
        ids = ref_lot.id, paid_lot.id, other.id
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / "0056_referral_badge_to_top.py"
    spec = importlib.util.spec_from_file_location("m0056", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    async with orm.session() as db:
        def run(sync_conn):
            with Operations.context(MigrationContext.configure(sync_conn)):
                mod.upgrade()
        conn = await db.connection()
        await conn.run_sync(run)
        await db.commit()
    assert (await _get(orm, Channel, ids[0])).tgsell_verified is False
    assert (await _get(orm, Channel, ids[1])).tgsell_verified is True  # paid badge kept
    assert (await _get(orm, Channel, ids[2])).tgsell_verified is True  # not a referral reward
    async with orm.session() as db:
        assert set((await db.execute(select(ReferralReward.status))).scalars().all()) == {"credit"}
