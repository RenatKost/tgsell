"""Task 32: balance buttons in the Telegram bot checklist + editing bundle balances.

Bot: «Баланс на місці» / «Баланс не відповідає» — buyer only, only when the deal
snapshot balance > 0, authorization re-checked server-side on every tap, mismatch
asks for confirmation and then goes through the site endpoint (report_balance_mismatch).
Bundles: seller edits only while there is no active deal; admin/moderator always;
edits never touch deals.balance_*.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

for _m in ("activity", "auction", "bundle", "channel", "chat", "deal", "monitoring",
           "saved_search", "settings", "support", "user"):  # register all mappers
    importlib.import_module(f"app.models.{_m}")
from app.models.deal import DealStatus  # noqa: E402
from app.services import deal_checklist as cl  # noqa: E402

BUYER_TG, SELLER_TG, OUTSIDER_TG = 3201, 3202, 3203


# ── helpers ────────────────────────────────────────────────────────────

class FakeMessage:
    def __init__(self):
        self.answers, self.edits, self.markup_edits = [], [], []

    async def answer(self, text, **kw):
        self.answers.append((text, kw.get("reply_markup")))

    async def edit_text(self, text, **kw):
        self.edits.append((text, kw.get("reply_markup")))

    async def edit_reply_markup(self, reply_markup=None, **kw):
        self.markup_edits.append(reply_markup)


class FakeCallback:
    def __init__(self, data, tg_id):
        self.data = data
        self.from_user = SimpleNamespace(id=tg_id)
        self.message = FakeMessage()
        self.alerts = []

    async def answer(self, text=None, show_alert=False, **kw):
        self.alerts.append((text, show_alert))


def _btns(kb):
    return [b for row in kb.inline_keyboard for b in row]


def _deal_ns(**kw):
    base = dict(id=77, status=DealStatus.channel_transferring, buyer_id=2, seller_id=1,
                balance_stars=None, balance_ton=None)
    base.update(kw)
    return SimpleNamespace(**base)


async def _seed(db, *, stars=1500, ton=12.5, status=DealStatus.paid, buyer_blocked=False):
    from app.models.deal import Deal
    from app.models.user import User

    s = User(first_name="Seller", telegram_id=SELLER_TG)
    b = User(first_name="Buyer", telegram_id=BUYER_TG, is_blocked=buyer_blocked)
    o = User(first_name="Other", telegram_id=OUTSIDER_TG)
    db.add_all([s, b, o])
    await db.commit()
    d = Deal(buyer_id=b.id, seller_id=s.id, status=status, escrow_wallet_address="TESC32",
             escrow_private_key_encrypted="enc", amount_usdt=100.0, service_fee=3.0,
             balance_stars=stars, balance_ton=ton)
    db.add(d)
    await db.commit()
    return s.id, b.id, o.id, d.id


@pytest.fixture
def bm(pg_orm, monkeypatch):
    # Other tests juggle sys.modules; make the lazy `from app.x import y` in the bot
    # handlers resolve to the live modules (same as in production).
    import app.routers as routers_pkg
    import app.services as services_pkg
    cl_mod = importlib.import_module("app.services.deal_checklist")
    dr = importlib.import_module("app.routers.deals")
    monkeypatch.setattr(services_pkg, "deal_checklist", cl_mod, raising=False)
    monkeypatch.setattr(dr, "checklist_svc", cl_mod)
    monkeypatch.setattr(routers_pkg, "deals", dr, raising=False)
    m = importlib.import_module("bot.main")
    monkeypatch.setattr(m, "async_session", pg_orm.session)
    return m


async def _deal(pg_orm, deal_id):
    from app.models.deal import Deal
    async with pg_orm.session() as db:
        return await db.get(Deal, deal_id)


async def _balance_row(pg_orm, deal_id):
    from app.models.deal import DealChecklistItem
    async with pg_orm.session() as db:
        return (await db.execute(select(DealChecklistItem).where(
            DealChecklistItem.deal_id == deal_id, DealChecklistItem.key == cl.BALANCE_ITEM_KEY))).scalar_one_or_none()


# ── Bot: visibility (pure) ─────────────────────────────────────────────

def test_balance_buttons_only_for_buyer_with_balance():
    bm = importlib.import_module("bot.main")
    with_bal = _deal_ns(balance_stars=10)
    texts = [b.text for b in _btns(bm.checklist_keyboard(with_bal, "buyer"))]
    assert "✅ Баланс на місці" in texts and "⚠️ Баланс не відповідає" in texts
    datas = [b.callback_data for b in _btns(bm.checklist_keyboard(with_bal, "buyer"))]
    assert "deal_bal_ok:77" in datas and "deal_bal_bad:77" in datas
    # seller / outsider never see them
    for role in ("seller", None):
        assert not any("Баланс" in b.text for b in _btns(bm.checklist_keyboard(with_bal, role)))
    # no balance (NULL / zero) → hidden even for the buyer
    for d in (_deal_ns(), _deal_ns(balance_stars=0, balance_ton=0.0)):
        assert not any("Баланс" in b.text for b in _btns(bm.checklist_keyboard(d, "buyer")))
    # TON-only balance counts too
    assert any("Баланс на місці" in b.text for b in _btns(bm.checklist_keyboard(_deal_ns(balance_ton=0.5), "buyer")))
    # already confirmed → only the mismatch button stays
    done = [SimpleNamespace(key="balance_ok", done=True)]
    t = [b.text for b in _btns(bm.checklist_keyboard(with_bal, "buyer", done))]
    assert "✅ Баланс на місці" not in t and "⚠️ Баланс не відповідає" in t
    # outside the transfer stage nothing to confirm
    assert not any("Баланс" in b.text for b in _btns(
        bm.checklist_keyboard(_deal_ns(balance_stars=10, status=DealStatus.disputed), "buyer")))
    # entry point from /deal and the payment notification
    assert any(b.callback_data == "deal_checklist:5" for b in _btns(bm.deal_keyboard(5, "seller")))


def test_checklist_text_lists_balance_item_and_stated_balance():
    bm = importlib.import_module("bot.main")
    d = _deal_ns(balance_stars=1500, balance_ton=12.5)
    txt = bm.checklist_text(d, [SimpleNamespace(key="balance_ok", done=True)])
    assert "Баланс Stars/TON на місці" in txt and "✅ Баланс Stars/TON на місці" in txt
    assert "1500 Stars" in txt and "12.5 TON" in txt and "зі слів продавця" in txt
    assert "Баланс Stars/TON" not in bm.checklist_text(_deal_ns(), [])


# ── Bot: callbacks against real Postgres ───────────────────────────────

@pytest.mark.asyncio
async def test_bot_balance_ok_buyer_only_and_ticks_item(pg_orm, bm):
    async with pg_orm.session() as db:
        _, _, _, deal_id = await _seed(db)

    for tg in (SELLER_TG, OUTSIDER_TG, 999999):
        cb = FakeCallback(f"deal_bal_ok:{deal_id}", tg)
        await bm.cb_balance_ok(cb)
        assert cb.alerts and cb.alerts[-1][1] is True, tg
        assert await _balance_row(pg_orm, deal_id) is None

    cb = FakeCallback(f"deal_bal_ok:{deal_id}", BUYER_TG)
    await bm.cb_balance_ok(cb)
    row = await _balance_row(pg_orm, deal_id)
    assert row is not None and row.done is True
    d = await _deal(pg_orm, deal_id)
    assert d.status == DealStatus.channel_transferring  # same side effects as the site toggle
    assert d.balance_stars == 1500 and d.balance_ton == 12.5
    text, kb = (cb.message.edits or cb.message.answers)[-1]
    assert "✅ Баланс Stars/TON на місці" in text
    assert "✅ Баланс на місці" not in [b.text for b in _btns(kb)]


@pytest.mark.asyncio
async def test_bot_balance_buttons_refused_without_balance(pg_orm, bm):
    async with pg_orm.session() as db:
        _, _, _, deal_id = await _seed(db, stars=None, ton=None)
    for handler, prefix in ((bm.cb_balance_ok, "deal_bal_ok:"), (bm.cb_balance_bad, "deal_bal_bad:"),
                            (bm.cb_balance_bad_yes, "deal_bal_bad_yes:")):
        cb = FakeCallback(f"{prefix}{deal_id}", BUYER_TG)
        await handler(cb)
        assert cb.alerts[-1] == ("Для цієї угоди баланс не вказано.", True)
    d = await _deal(pg_orm, deal_id)
    assert d.status == DealStatus.paid and d.dispute_reason is None


@pytest.mark.asyncio
async def test_bot_mismatch_asks_confirmation_then_uses_site_endpoint(pg_orm, bm, monkeypatch):
    deals_router = importlib.import_module("app.routers.deals")
    async with pg_orm.session() as db:
        _, buyer_id, _, deal_id = await _seed(db)

    # step 1: only a confirmation prompt, nothing changes
    cb = FakeCallback(f"deal_bal_bad:{deal_id}", BUYER_TG)
    await bm.cb_balance_bad(cb)
    text, kb = cb.message.answers[-1]
    assert "Підтвердіть" in text and "1500 Stars" in text
    datas = [b.callback_data for b in _btns(kb)]
    assert datas == [f"deal_bal_bad_yes:{deal_id}", f"deal_bal_bad_no:{deal_id}"]
    assert (await _deal(pg_orm, deal_id)).status == DealStatus.paid

    # cancel → still nothing
    cb_no = FakeCallback(f"deal_bal_bad_no:{deal_id}", BUYER_TG)
    await bm.cb_balance_bad_no(cb_no)
    assert (await _deal(pg_orm, deal_id)).status == DealStatus.paid

    # seller / outsider cannot confirm (server-side re-check on the second tap too)
    for tg in (SELLER_TG, OUTSIDER_TG):
        c = FakeCallback(f"deal_bal_bad_yes:{deal_id}", tg)
        await bm.cb_balance_bad_yes(c)
        assert c.alerts[-1][1] is True
        c2 = FakeCallback(f"deal_bal_bad:{deal_id}", tg)
        await bm.cb_balance_bad(c2)
        assert c2.alerts[-1][1] is True and not c2.message.answers
    assert (await _deal(pg_orm, deal_id)).status == DealStatus.paid

    # confirm → goes through report_balance_mismatch (same as the site)
    calls = []
    real = deals_router.report_balance_mismatch

    async def spy(did, user, db):
        calls.append((did, user.id))
        return await real(did, user=user, db=db)

    monkeypatch.setattr(deals_router, "report_balance_mismatch", spy)
    cb_yes = FakeCallback(f"deal_bal_bad_yes:{deal_id}", BUYER_TG)
    await bm.cb_balance_bad_yes(cb_yes)
    assert calls == [(deal_id, buyer_id)]
    d = await _deal(pg_orm, deal_id)
    assert d.status == DealStatus.disputed
    assert d.dispute_reason == "Баланс не відповідає заявленому продавцем (⭐ 1500 Stars, 💎 12.5 TON)"
    assert "Спір по угоді" in cb_yes.message.answers[-1][0]
    from app.models.deal import DealMessage
    async with pg_orm.session() as db:
        ev = list((await db.execute(select(DealMessage.event).where(DealMessage.deal_id == deal_id))).scalars())
    assert "dispute_opened" in ev

    # a second confirm cannot reopen (open_dispute refuses: not paid/transferring)
    cb_again = FakeCallback(f"deal_bal_bad_yes:{deal_id}", BUYER_TG)
    await bm.cb_balance_bad_yes(cb_again)
    assert cb_again.alerts[-1] == ("Спір неможливо відкрити в поточному статусі угоди.", True)


@pytest.mark.asyncio
async def test_bot_blocked_buyer_refused(pg_orm, bm):
    async with pg_orm.session() as db:
        _, _, _, deal_id = await _seed(db, buyer_blocked=True)
    for handler, prefix in ((bm.cb_balance_ok, "deal_bal_ok:"), (bm.cb_balance_bad_yes, "deal_bal_bad_yes:")):
        cb = FakeCallback(f"{prefix}{deal_id}", BUYER_TG)
        await handler(cb)
        assert cb.alerts[-1][1] is True and "заблоковано" in cb.alerts[-1][0]
    assert (await _deal(pg_orm, deal_id)).status == DealStatus.paid
    assert await _balance_row(pg_orm, deal_id) is None


@pytest.mark.asyncio
async def test_bot_checklist_view_participants_only(pg_orm, bm):
    async with pg_orm.session() as db:
        _, _, _, deal_id = await _seed(db)
    cb = FakeCallback(f"deal_checklist:{deal_id}", BUYER_TG)
    await bm.cb_deal_checklist(cb)
    text, kb = cb.message.answers[-1]
    assert f"угода #{deal_id}" in text and any("Баланс на місці" in b.text for b in _btns(kb))
    cb_s = FakeCallback(f"deal_checklist:{deal_id}", SELLER_TG)
    await bm.cb_deal_checklist(cb_s)
    assert not any("Баланс" in b.text for b in _btns(cb_s.message.answers[-1][1]))
    cb_o = FakeCallback(f"deal_checklist:{deal_id}", OUTSIDER_TG)
    await bm.cb_deal_checklist(cb_o)
    assert cb_o.alerts[-1] == ("Немає доступу.", True) and not cb_o.message.answers


# ── Bundle balances ────────────────────────────────────────────────────

async def _seed_bundle(db, *, status="approved"):
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole

    seller = User(first_name="S", telegram_id=3211)
    other = User(first_name="O", telegram_id=3212)
    mod = User(first_name="M", telegram_id=3213, role=UserRole.moderator)
    adm = User(first_name="A", telegram_id=3214, role=UserRole.admin)
    db.add_all([seller, other, mod, adm])
    await db.commit()
    a = Channel(seller_id=seller.id, telegram_link="b32a", channel_name="b32a", category="Крипта",
                price=0, status=ChannelStatus.approved, stars_balance=100)
    b = Channel(seller_id=seller.id, telegram_link="b32b", channel_name="b32b", category="Крипта",
                price=0, status=ChannelStatus.approved, ton_balance=2.5)
    foreign = Channel(seller_id=other.id, telegram_link="b32x", channel_name="b32x", category="Крипта",
                      price=0, status=ChannelStatus.approved, stars_balance=7)
    db.add_all([a, b, foreign])
    await db.commit()
    bundle = ChannelBundle(seller_id=seller.id, name="Сітка 32", price=200, status=BundleStatus(status))
    db.add(bundle)
    await db.flush()
    db.add_all([BundleChannel(bundle_id=bundle.id, channel_id=a.id, display_order=0),
                BundleChannel(bundle_id=bundle.id, channel_id=b.id, display_order=1)])
    await db.commit()
    return SimpleNamespace(seller=seller.id, other=other.id, mod=mod.id, admin=adm.id,
                           bundle=bundle.id, a=a.id, b=b.id, foreign=foreign.id)


async def _add_deal(db, ids, status, *, bundle=True, channel_id=None):
    from app.models.deal import Deal
    d = Deal(buyer_id=ids.other, seller_id=ids.seller, status=status, escrow_wallet_address="TESC32B",
             escrow_private_key_encrypted="enc", amount_usdt=200.0, service_fee=6.0,
             bundle_id=ids.bundle if bundle else None, channel_id=channel_id,
             balance_stars=100, balance_ton=2.5)
    db.add(d)
    await db.commit()
    return d.id


def _upd(*rows):
    from app.schemas.bundle import BundleBalancesUpdate
    return BundleBalancesUpdate(channel_balances=[dict(r) for r in rows])


async def _channel(pg_orm, cid):
    from app.models.channel import Channel
    async with pg_orm.session() as db:
        c = await db.get(Channel, cid)
        return c.stars_balance, c.ton_balance


@pytest.mark.asyncio
async def test_seller_edits_without_active_deal(pg_orm):
    from app.models.user import User
    br = importlib.import_module("app.routers.bundles")
    async with pg_orm.session() as db:
        ids = await _seed_bundle(db)
        # finished deals do not block editing
        await _add_deal(db, ids, DealStatus.cancelled)
        await _add_deal(db, ids, DealStatus.completed)
    async with pg_orm.session() as db:
        out = await br.update_bundle_balances(ids.bundle, _upd(
            {"channel_id": ids.a, "stars_balance": 250, "ton_balance": None},
            {"channel_id": ids.b, "stars_balance": None, "ton_balance": 0.75},
        ), user=await db.get(User, ids.seller), db=db)
    by = {c.id: c for c in out.channels}
    assert (by[ids.a].stars_balance, by[ids.a].ton_balance) == (250, None)
    assert (by[ids.b].stars_balance, by[ids.b].ton_balance) == (None, 0.75)
    assert await _channel(pg_orm, ids.a) == (250, None)


@pytest.mark.parametrize("status", [
    DealStatus.created, DealStatus.payment_pending, DealStatus.paid, DealStatus.channel_transferring,
    DealStatus.awaiting_payout, DealStatus.payout_in_progress, DealStatus.disputed,
])
@pytest.mark.asyncio
async def test_seller_blocked_by_active_deal_and_snapshot_untouched(pg_orm, status):
    from app.models.deal import Deal
    from app.models.user import User
    br = importlib.import_module("app.routers.bundles")
    async with pg_orm.session() as db:
        ids = await _seed_bundle(db)
        deal_id = await _add_deal(db, ids, status)
    async with pg_orm.session() as db:
        with pytest.raises(HTTPException) as e:
            await br.update_bundle_balances(ids.bundle, _upd({"channel_id": ids.a, "stars_balance": 1}),
                                            user=await db.get(User, ids.seller), db=db)
    assert e.value.status_code == 409 and "активна угода" in e.value.detail
    assert await _channel(pg_orm, ids.a) == (100, None)
    async with pg_orm.session() as db:
        d = await db.get(Deal, deal_id)
        assert (d.balance_stars, d.balance_ton) == (100, 2.5)


@pytest.mark.asyncio
async def test_seller_blocked_by_active_deal_on_member_channel(pg_orm):
    from app.models.user import User
    br = importlib.import_module("app.routers.bundles")
    async with pg_orm.session() as db:
        ids = await _seed_bundle(db)
        await _add_deal(db, ids, DealStatus.paid, bundle=False, channel_id=ids.b)
    async with pg_orm.session() as db:
        with pytest.raises(HTTPException) as e:
            await br.update_bundle_balances(ids.bundle, _upd({"channel_id": ids.a, "stars_balance": 1}),
                                            user=await db.get(User, ids.seller), db=db)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_seller_rules_owner_sold_foreign_channel(pg_orm):
    from app.models.bundle import BundleStatus, ChannelBundle
    from app.models.user import User
    br = importlib.import_module("app.routers.bundles")
    async with pg_orm.session() as db:
        ids = await _seed_bundle(db)
    async with pg_orm.session() as db:
        with pytest.raises(HTTPException) as e:
            await br.update_bundle_balances(ids.bundle, _upd({"channel_id": ids.a, "stars_balance": 1}),
                                            user=await db.get(User, ids.other), db=db)
        assert e.value.status_code == 403
    # foreign channel → 400 and nothing partially written
    async with pg_orm.session() as db:
        with pytest.raises(HTTPException) as e:
            await br.update_bundle_balances(ids.bundle, _upd(
                {"channel_id": ids.a, "stars_balance": 999},
                {"channel_id": ids.foreign, "stars_balance": 1}),
                user=await db.get(User, ids.seller), db=db)
        assert e.value.status_code == 400
    assert await _channel(pg_orm, ids.a) == (100, None)
    assert await _channel(pg_orm, ids.foreign) == (7, None)
    with pytest.raises(HTTPException) as e:
        async with pg_orm.session() as db:
            await br.update_bundle_balances(424242, _upd({"channel_id": ids.a, "stars_balance": 1}),
                                            user=await db.get(User, ids.seller), db=db)
    assert e.value.status_code == 404
    async with pg_orm.session() as db:
        (await db.get(ChannelBundle, ids.bundle)).status = BundleStatus.sold
        await db.commit()
    async with pg_orm.session() as db:
        with pytest.raises(HTTPException) as e:
            await br.update_bundle_balances(ids.bundle, _upd({"channel_id": ids.a, "stars_balance": 1}),
                                            user=await db.get(User, ids.seller), db=db)
        assert e.value.status_code == 400


def test_schema_rejects_negative_and_empty():
    from pydantic import ValidationError
    from app.schemas.bundle import BundleBalancesUpdate
    for bad in ({"channel_balances": []}, {"channel_balances": [{"channel_id": 1, "stars_balance": -1}]},
                {"channel_balances": [{"channel_id": 1, "ton_balance": -0.1}]},
                {"channel_balances": [{"channel_id": 1, "stars_balance": 1.5}]}):
        with pytest.raises(ValidationError):
            BundleBalancesUpdate(**bad)


@pytest.mark.asyncio
async def test_legacy_put_respects_active_deal_rule(pg_orm):
    from app.models.bundle import BundleStatus, ChannelBundle
    from app.models.user import User
    from app.schemas.bundle import BundleUpdate
    br = importlib.import_module("app.routers.bundles")
    async with pg_orm.session() as db:
        ids = await _seed_bundle(db, status="pending")
    async with pg_orm.session() as db:
        out = await br.update_bundle(ids.bundle, BundleUpdate(
            channel_balances=[{"channel_id": ids.a, "stars_balance": 5}]), user=await db.get(User, ids.seller), db=db)
        assert next(c for c in out.channels if c.id == ids.a).stars_balance == 5
    async with pg_orm.session() as db:
        await _add_deal(db, ids, DealStatus.paid, bundle=False, channel_id=ids.a)
    async with pg_orm.session() as db:
        with pytest.raises(HTTPException) as e:
            await br.update_bundle(ids.bundle, BundleUpdate(
                channel_balances=[{"channel_id": ids.a, "stars_balance": 6}]), user=await db.get(User, ids.seller), db=db)
        assert e.value.status_code == 409
    assert await _channel(pg_orm, ids.a) == (5, None)


@pytest.mark.parametrize("who", ["mod", "admin"])
@pytest.mark.asyncio
async def test_staff_always_edit_audited_snapshot_untouched(pg_orm, who):
    from app.models.deal import Deal
    from app.models.user import AdminAuditLog, User
    ar = importlib.import_module("app.routers.admin")
    async with pg_orm.session() as db:
        ids = await _seed_bundle(db)
        deal_id = await _add_deal(db, ids, DealStatus.channel_transferring)
    async with pg_orm.session() as db:
        out = await ar.admin_update_bundle_balances(ids.bundle, _upd(
            {"channel_id": ids.a, "stars_balance": 5000, "ton_balance": 1}),
            admin=await db.get(User, getattr(ids, who)), db=db)
    assert out["has_active_deal"] is True
    ch = next(c for c in out["channels"] if c["id"] == ids.a)
    assert (ch["stars_balance"], ch["ton_balance"]) == (5000, 1)
    async with pg_orm.session() as db:
        d = await db.get(Deal, deal_id)
        assert (d.balance_stars, d.balance_ton) == (100, 2.5)  # snapshot never changes
        logs = list((await db.execute(select(AdminAuditLog).where(
            AdminAuditLog.action == "bundle.balances_edit"))).scalars())
        assert len(logs) == 1 and logs[0].actor_id == getattr(ids, who) and logs[0].target_id == ids.bundle
    # sold bundle is still editable by staff
    from app.models.bundle import BundleStatus, ChannelBundle
    async with pg_orm.session() as db:
        (await db.get(ChannelBundle, ids.bundle)).status = BundleStatus.sold
        await db.commit()
    async with pg_orm.session() as db:
        await ar.admin_update_bundle_balances(ids.bundle, _upd({"channel_id": ids.b, "ton_balance": None}),
                                              admin=await db.get(User, getattr(ids, who)), db=db)
    assert await _channel(pg_orm, ids.b) == (None, None)
    # foreign channel still refused for staff
    async with pg_orm.session() as db:
        with pytest.raises(HTTPException) as e:
            await ar.admin_update_bundle_balances(ids.bundle, _upd({"channel_id": ids.foreign, "stars_balance": 1}),
                                                  admin=await db.get(User, getattr(ids, who)), db=db)
        assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_list_and_http_permissions(pg_orm, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.models.user import User
    db_mod = importlib.import_module("app.database")
    async with pg_orm.session() as db:
        ids = await _seed_bundle(db)
        await _add_deal(db, ids, DealStatus.paid)
    app = FastAPI()
    for name in ("app.routers.bundles", "app.routers.admin"):
        app.include_router(importlib.import_module(name).router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    current = {}

    async def fake_user():
        async with pg_orm.session() as db:
            return await db.get(User, current["id"])

    import inspect
    br = importlib.import_module("app.routers.bundles")
    ar = importlib.import_module("app.routers.admin")
    # override the exact callables the routes depend on (robust to module juggling)
    seller_dep = inspect.signature(br.update_bundle_balances).parameters["user"].default.dependency
    staff_dep = inspect.signature(ar.admin_update_bundle_balances).parameters["admin"].default.dependency
    inner_dep = inspect.signature(staff_dep).parameters["user"].default.dependency
    assert seller_dep.__name__ == inner_dep.__name__ == "get_current_user"
    assert staff_dep.__name__ == "get_admin_user"
    app.dependency_overrides[seller_dep] = fake_user
    app.dependency_overrides[inner_dep] = fake_user
    body = {"channel_balances": [{"channel_id": ids.a, "stars_balance": 1}]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        current["id"] = ids.seller
        r = await c.put(f"/api/bundles/{ids.bundle}/balances", json=body)
        assert r.status_code == 409, r.text
        r = await c.put(f"/api/admin/bundles/{ids.bundle}/balances", json=body)
        assert r.status_code == 403  # plain user is not staff
        assert (await c.get("/api/admin/bundles")).status_code == 403
        r = await c.put(f"/api/bundles/{ids.bundle}/balances", json={"channel_balances": [
            {"channel_id": ids.a, "stars_balance": -5}]})
        assert r.status_code == 422
        current["id"] = ids.mod
        r = await c.get("/api/admin/bundles", params={"search": f"#{ids.bundle}"})
        assert r.status_code == 200
        (item,) = r.json()["items"]
        assert item["id"] == ids.bundle and item["has_active_deal"] is True
        assert {ch["id"] for ch in item["channels"]} == {ids.a, ids.b}
        assert len((await c.get("/api/admin/bundles", params={"search": "Сітка"})).json()["items"]) == 1
        r = await c.put(f"/api/admin/bundles/{ids.bundle}/balances", json=body)
        assert r.status_code == 200, r.text
    assert await _channel(pg_orm, ids.a) == (1, None)


def test_frontend_wiring():
    api = (REPO_ROOT / "src/services/api.js").read_text(encoding="utf-8")
    assert "/bundles/${id}/balances" in api and "/admin/bundles/${id}/balances" in api
    editor = (REPO_ROOT / "src/components/Balance/BundleBalanceEditor.jsx").read_text(encoding="utf-8")
    assert "Stars" in editor and "TON" in editor and "channel_id" in editor
    assert "Існуючі угоди зберігають баланс" in editor
    cab = (REPO_ROOT / "src/layouts/CabinetPage.jsx").read_text(encoding="utf-8")
    assert "BundleBalanceEditor" in cab and "updateBalances" in cab and "немає активної угоди" in cab
    panel = (REPO_ROOT / "src/components/Admin/BundleBalancesPanel.jsx").read_text(encoding="utf-8")
    assert "updateBundleBalances" in panel and "BundleBalanceEditor" in panel
    moder = (REPO_ROOT / "src/layouts/ModerCabinet.jsx").read_text(encoding="utf-8")
    # visible to moderators too (not adminOnly)
    line = next(l for l in moder.splitlines() if "'bundle_balances'" in l and "label" in l)
    assert "adminOnly" not in line and "Баланси сіток" in line
    assert "section === 'bundle_balances' && <BundleBalancesPanel />" in moder
