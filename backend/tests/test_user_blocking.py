"""User blocking + admin audit log (migration 0027) — real Postgres, TRON mocked."""
from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from tests.test_unified_payouts import SELLER_W, env  # noqa: F401  (fixture)

BACKEND = Path(__file__).resolve().parents[1]


async def _admin(env, role="admin"):
    from app.models.user import User, UserRole

    async with env.orm.session() as db:
        u = User(first_name=f"Staff-{role}", telegram_id=9900 + len(role), role=UserRole(role))
        db.add(u)
        await db.commit()
        return u.id


async def _call(env, fn, *a, admin_id=None, user_id=None, **kw):
    from app.models.user import User

    async with env.orm.session() as db:
        if admin_id is not None:
            kw["admin"] = await db.get(User, admin_id)
        if user_id is not None:
            kw["user"] = await db.get(User, user_id)
        if "response" in inspect.signature(fn).parameters:
            from fastapi import Response
            kw["response"] = Response()
        return await fn(*a, db=db, **kw)


async def _block(env, admin_id, user_id, reason="fraud test"):
    return await _call(env, env.admin.block_user, user_id, env.admin.BlockRequest(reason=reason), admin_id=admin_id)


async def _audit_actions(env):
    from app.models.user import AdminAuditLog

    async with env.orm.session() as db:
        return [r.action for r in (await db.execute(select(AdminAuditLog).order_by(AdminAuditLog.id))).scalars()]


@pytest.mark.asyncio
async def test_block_lists_deals_never_modifies_them_and_audits(env):
    admin = await _admin(env)
    paid, _ = await env.make_deal(env.S.paid)
    pip, _ = await env.make_deal(env.S.payout_in_progress)
    res = await _block(env, admin, env.ids.seller)
    assert res["is_blocked"] and res["blocked_reason"] == "fraud test"
    ids = {d["deal_id"]: d for d in res["active_deals"]}
    assert ids[paid]["needs_admin_decision"] and not ids[pip]["needs_admin_decision"]
    assert res["escrow_total_usdt"] == 200.0
    assert (await env.get(paid)).status == env.S.paid
    assert (await env.get(pip)).status == env.S.payout_in_progress
    assert "user.block" in await _audit_actions(env)
    env.alert.assert_awaited()  # funded deal → admin told, never silently frozen
    res = await _call(env, env.admin.unblock_user, env.ids.seller, admin_id=admin)
    assert not res["is_blocked"] and "user.unblock" in await _audit_actions(env)


@pytest.mark.asyncio
async def test_cannot_block_self_or_admin(env):
    admin = await _admin(env)
    with pytest.raises(HTTPException) as e:
        await _block(env, admin, admin)
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_dependencies_refuse_blocked_and_moderator_money(env):
    from app.utils import security

    admin = await _admin(env)
    mod = await _admin(env, "moderator")
    await _block(env, admin, env.ids.seller)
    async with env.orm.session() as db:
        from app.models.user import User

        seller = await db.get(User, env.ids.seller)
        with pytest.raises(HTTPException) as e:
            await security.get_current_user(seller)
        assert e.value.status_code == 403 and "заблоковано" in e.value.detail
        m = await db.get(User, mod)
        assert await security.get_admin_user(m) is m
        with pytest.raises(HTTPException) as e:
            await security.get_superadmin_user(m)
        assert e.value.status_code == 403


def test_money_and_blocking_endpoints_are_admin_only():
    src = (BACKEND / "app/routers/admin.py").read_text()
    for fn in ("resolve_deal", "admin_cancel_deal", "collect_fee", "sweep_escrow_wallet", "set_user_role",
               "list_users", "get_user_detail", "block_user", "unblock_user", "deal_blocked_party", "get_audit_log"):
        body = src[src.index(f"async def {fn}("):]
        body = body[: body.index("db: AsyncSession")]
        assert "get_superadmin_user" in body, fn


@pytest.mark.asyncio
async def test_login_refused_unless_allowed_active_deal(env):
    from app.models.user import User
    from app.services import moderation

    admin = await _admin(env)
    deal_id, _ = await env.make_deal(env.S.paid)
    await _block(env, admin, env.ids.seller)
    async with env.orm.session() as db:
        seller = await db.get(User, env.ids.seller)
        with pytest.raises(HTTPException) as e:
            await moderation.ensure_login_allowed(db, seller)
        assert e.value.status_code == 403
    await _call(env, env.admin.deal_blocked_party, deal_id, env.admin.BlockedPartyRequest(action="allow"), admin_id=admin)
    async with env.orm.session() as db:
        seller = await db.get(User, env.ids.seller)
        await moderation.ensure_login_allowed(db, seller)  # no raise
        seller.is_active = False
        with pytest.raises(HTTPException) as e:
            await moderation.ensure_login_allowed(db, seller)
        assert "деактивовано" in e.value.detail


@pytest.mark.asyncio
async def test_blocked_party_deal_actions_need_allow(env):
    from app.schemas.deal import SellerWalletRequest

    admin = await _admin(env)
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await _block(env, admin, env.ids.seller)
    with pytest.raises(HTTPException) as e:
        await _call(env, env.deals.set_seller_wallet, deal_id, SellerWalletRequest(wallet_address=SELLER_W),
                    user_id=env.ids.seller)
    assert e.value.status_code == 403
    assert (await env.get(deal_id)).status == env.S.awaiting_payout
    await _call(env, env.admin.deal_blocked_party, deal_id, env.admin.BlockedPartyRequest(action="allow"), admin_id=admin)
    r = await env.call(env.deals.set_seller_wallet, deal_id, SellerWalletRequest(wallet_address=SELLER_W),
                       user=env.ids.seller)
    assert r.status == "completed"


@pytest.mark.asyncio
async def test_blocked_party_dispute_rules(env):
    admin = await _admin(env)
    req = env.admin.BlockedPartyRequest
    paid, _ = await env.make_deal(env.S.paid)
    r = await _call(env, env.admin.deal_blocked_party, paid, req(action="dispute", note="blocked"), admin_id=admin)
    assert r["status"] == "disputed"
    pip, _ = await env.make_deal(env.S.payout_in_progress)
    with pytest.raises(HTTPException) as e:
        await _call(env, env.admin.deal_blocked_party, pip, req(action="dispute"), admin_id=admin)
    assert e.value.status_code == 409
    assert (await env.get(pip)).status == env.S.payout_in_progress
    created, _ = await env.make_deal(env.S.created, funded=False)
    with pytest.raises(HTTPException) as e:
        await _call(env, env.admin.deal_blocked_party, created, req(action="dispute"), admin_id=admin)
    assert e.value.status_code == 409
    # open outgoing tx → 409
    aw, _ = await env.make_deal(env.S.awaiting_payout)
    async with env.orm.session() as db:
        d = await db.get(env.Deal, aw)
        env.payouts.enqueue_transfer(db, d, tx_type=env.TT.release, to_address=SELLER_W,
                                     amount_units=1, restore_status=env.S.awaiting_payout)
        await db.commit()
    with pytest.raises(HTTPException) as e:
        await _call(env, env.admin.deal_blocked_party, aw, req(action="dispute"), admin_id=admin)
    assert e.value.status_code == 409
    assert "deal.blocked_party.dispute" in await _audit_actions(env)


@pytest.mark.asyncio
async def test_payout_in_progress_finishes_for_blocked_seller(env):
    """Blocking never interrupts a claimed payout: the worker completes it."""
    admin = await _admin(env)
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    r = await env.seller_wallet(deal_id, run_worker=False)
    assert r.status == "payout_in_progress"
    await _block(env, admin, env.ids.seller)
    await env.work()
    assert (await env.get(deal_id)).status == env.S.completed


@pytest.mark.asyncio
async def test_blocked_seller_listing_hidden_and_no_new_deals(env):
    from app.schemas.deal import DealCreate

    admin = await _admin(env)
    await _block(env, admin, env.ids.seller)
    channels = importlib.import_module("app.routers.channels")
    async with env.orm.session() as db:
        with pytest.raises(HTTPException) as e:
            await channels.get_channel(env.ids.channel, db=db)
        assert e.value.status_code == 404
        ch = await db.get(env.Channel, env.ids.channel)
        assert ch.status == env.CS.approved  # status untouched
    with pytest.raises(HTTPException) as e:
        await _call(env, env.deals.create_deal, DealCreate(channel_id=env.ids.channel), user_id=env.ids.buyer)
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_audit_log_and_users_search(env):
    admin = await _admin(env)
    await _block(env, admin, env.ids.seller, reason="spam spam")
    log = await _call(env, env.admin.get_audit_log, admin_id=admin, action=None, target_type=None,
                      target_id=None, actor_id=None, page=1, limit=50)
    assert log["items"][0]["action"] == "user.block" and log["items"][0]["actor_id"] == admin
    users = await _call(env, env.admin.list_users, admin_id=admin, q="Seller", blocked=True, role=None, page=1, limit=50)
    assert users["total"] == 1 and users["items"][0]["id"] == env.ids.seller


@pytest.mark.asyncio
async def test_money_actions_write_audit(env):
    admin = await _admin(env)
    deal_id, _ = await env.make_deal(env.S.disputed)
    from app.models.user import User
    from app.schemas.deal import DealResolveRequest

    async with env.orm.session() as db:
        from fastapi import Response
        await env.admin.resolve_deal(deal_id, DealResolveRequest(resolution="release_seller"),
                                     response=Response(), admin=await db.get(User, admin), db=db)
    assert "deal.resolve" in await _audit_actions(env)


@pytest.mark.asyncio
async def test_auction_frozen_when_party_blocked(env):
    from datetime import timedelta

    from app.models.auction import Auction
    from app.utils.timeutil import utcnow_naive

    am = importlib.import_module("app.tasks.auction_manager")
    admin = await _admin(env)
    async with env.orm.session() as db:
        a = Auction(channel_id=env.ids.channel, seller_id=env.ids.seller, start_price=10, current_price=20,
                    bid_step=1, status="active", starts_at=utcnow_naive() - timedelta(days=2),
                    ends_at=utcnow_naive() - timedelta(minutes=1), winner_id=env.ids.buyer)
        db.add(a)
        await db.commit()
        aid = a.id
    await _block(env, admin, env.ids.buyer)
    async with env.orm.session() as db:
        await am._process_auctions(db)
    async with env.orm.session() as db:
        assert (await db.get(Auction, aid)).status == "active"
        n = (await db.execute(select(env.Deal).where(env.Deal.buyer_id == env.ids.buyer))).scalars().all()
        assert n == []


def test_bot_refuses_blocked_confirm_and_dispute():
    src = (BACKEND / "bot/main.py").read_text()
    assert "user.is_blocked and not deal.blocked_party_allowed" in src
    assert "відкриття спору недоступне" in src
