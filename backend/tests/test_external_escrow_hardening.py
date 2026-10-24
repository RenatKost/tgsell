"""External /escrow deals: payout only after the buyer's (or admin's) confirmation; invite bound to telegram_id."""
from __future__ import annotations

import importlib
from datetime import timedelta

import pytest

from tests.test_external_escrow import BODY, _setup, _users

SELLER_ITEMS = ("enabled_2fa", "added_buyer_admin", "transferred_ownership", "removed_extra_admins")
BUYER_ITEMS = ("became_owner", "checked_admins", "checked_subscribers")
WALLET = "TXoRpYu5FDgZvrqNQb239bLjcc5oHzavCG"


async def _paid_external_deal(orm, monkeypatch):
    from app.models.deal import Deal, DealStatus
    client, cur = await _setup(orm, monkeypatch)
    seller, buyer, other, google = await _users(orm)
    await client.__aenter__()
    cur.user = seller
    o = (await client.post("/api/escrow/offers", json=BODY)).json()
    token = o["buyer_url"].rsplit("/", 1)[1]
    cur.user = buyer
    deal_id = (await client.post(f"/api/escrow/invite/{token}/accept")).json()["deal_id"]
    async with orm.session() as db:  # simulate confirmed payment (payment_checker is tested elsewhere)
        d = await db.get(Deal, deal_id)
        d.status = DealStatus.paid
        await db.commit()
    return client, cur, seller, buyer, other, deal_id, token


async def _status(orm, deal_id):
    from app.models.deal import Deal
    async with orm.session() as db:
        return (await db.get(Deal, deal_id)).status.value


@pytest.mark.asyncio
async def test_seller_alone_cannot_reach_payout(orm, monkeypatch):
    client, cur, seller, buyer, other, deal_id, _ = await _paid_external_deal(orm, monkeypatch)
    try:
        cur.user = seller
        for k in SELLER_ITEMS:
            assert (await client.post(f"/api/deals/{deal_id}/checklist/{k}", json={"done": True})).status_code == 200
        # seller cannot tick the buyer's items
        for k in BUYER_ITEMS:
            assert (await client.post(f"/api/deals/{deal_id}/checklist/{k}", json={"done": True})).status_code == 403
        assert (await client.post(f"/api/deals/{deal_id}/confirm-channel-transfer")).status_code == 200
        assert await _status(orm, deal_id) == "channel_transferring"
        # no payout possible: seller-wallet requires awaiting_payout
        r = await client.post(f"/api/deals/{deal_id}/seller-wallet", json={"wallet_address": WALLET})
        assert r.status_code == 400
        # time passing + reminders never advance the deal
        rem = importlib.import_module("app.tasks.checklist_reminders")
        monkeypatch.setattr(importlib.import_module("app.database"), "async_session", orm.session)
        monkeypatch.setattr(rem, "async_session", orm.session, raising=False)
        from app.utils.timeutil import utcnow_naive
        try:
            await rem.check_checklist_reminders_once(utcnow_naive() + timedelta(days=30))
        except Exception:
            pass  # bot delivery is irrelevant here; status is what matters
        assert await _status(orm, deal_id) == "channel_transferring"
        # buyer's explicit confirmation is the gate
        cur.user = buyer
        assert (await client.post(f"/api/deals/{deal_id}/confirm-channel-transfer")).status_code == 400  # items open
        for k in BUYER_ITEMS:
            assert (await client.post(f"/api/deals/{deal_id}/checklist/{k}", json={"done": True})).status_code == 200
        assert await _status(orm, deal_id) == "channel_transferring"
        assert (await client.post(f"/api/deals/{deal_id}/confirm-channel-transfer")).status_code == 200
        assert await _status(orm, deal_id) == "awaiting_payout"
    finally:
        await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_advance_guard_requires_both_confirmations():
    from types import SimpleNamespace
    from app.services import deal_checklist as cl
    d = SimpleNamespace(buyer_confirmed_transfer=False, seller_confirmed_transfer=True, channel_id=None, bundle_id=None)
    with pytest.raises(cl.ChecklistError):
        await cl.advance_to_awaiting_payout(None, d)


@pytest.mark.asyncio
async def test_invite_bound_to_telegram_id(orm, monkeypatch):
    from app.models.external_escrow import ExternalEscrowOffer
    from app.models.user import User
    client, cur = await _setup(orm, monkeypatch)
    seller, buyer, other, google = await _users(orm)
    async with client:
        cur.user = seller
        o = (await client.post("/api/escrow/offers", json=BODY)).json()
        token = o["buyer_url"].rsplit("/", 1)[1]
        # first open by the invited @username binds telegram_id
        cur.user = buyer
        assert (await client.get(f"/api/escrow/invite/{token}")).status_code == 200
        async with orm.session() as db:
            assert (await db.get(ExternalEscrowOffer, o["id"])).buyer_telegram_id == buyer.telegram_id
        # buyer changes username → still works
        async with orm.session() as db:
            (await db.get(User, buyer.id)).username = "renamed_buyer"
            await db.commit()
        buyer.username = "renamed_buyer"
        assert (await client.get(f"/api/escrow/invite/{token}")).status_code == 200
        # someone else takes the old @username → 404 (binding wins)
        other.username = "buyer_ivan"
        cur.user = other
        assert (await client.get(f"/api/escrow/invite/{token}")).status_code == 404
        assert (await client.post(f"/api/escrow/invite/{token}/accept")).status_code == 404
        cur.user = buyer
        assert (await client.post(f"/api/escrow/invite/{token}/accept")).status_code == 200


@pytest.mark.asyncio
async def test_username_squatter_before_binding_still_needs_username_and_tg(orm, monkeypatch):
    client, cur = await _setup(orm, monkeypatch)
    seller, buyer, other, google = await _users(orm)
    async with client:
        cur.user = seller
        token = (await client.post("/api/escrow/offers", json=BODY)).json()["buyer_url"].rsplit("/", 1)[1]
        google.username = "buyer_ivan"  # matching username but no telegram account
        cur.user = google
        assert (await client.get(f"/api/escrow/invite/{token}")).status_code == 404
        cur.user = other
        assert (await client.get(f"/api/escrow/invite/{token}")).status_code == 404


@pytest.mark.asyncio
async def test_legacy_accepted_offer_binds_only_to_deal_buyer(orm, monkeypatch):
    from app.models.external_escrow import ExternalEscrowOffer
    client, cur = await _setup(orm, monkeypatch)
    seller, buyer, other, google = await _users(orm)
    async with client:
        cur.user = seller
        o = (await client.post("/api/escrow/offers", json=BODY)).json()
        token = o["buyer_url"].rsplit("/", 1)[1]
        cur.user = buyer
        deal_id = (await client.post(f"/api/escrow/invite/{token}/accept")).json()["deal_id"]
        async with orm.session() as db:  # emulate a pre-0052 row: no binding yet
            (await db.get(ExternalEscrowOffer, o["id"])).buyer_telegram_id = None
            await db.commit()
        other.username = "buyer_ivan"
        cur.user = other
        assert (await client.get(f"/api/escrow/invite/{token}")).status_code == 404
        cur.user = buyer
        assert (await client.get(f"/api/escrow/invite/{token}")).json()["deal_id"] == deal_id
