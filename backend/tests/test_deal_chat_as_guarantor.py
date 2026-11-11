"""Deal chat: staff can post explicitly as the TgSell guarantor (as_guarantor, migration 0061).

Cases from /workspace/tgsell-ceo/deal34-admin-identity.md:
(a) moderator who is not a party → guarantor;
(b) admin who is the seller, without the flag → seller (party priority kept);
(c) admin who is the seller, with the flag → guarantor, signed «TgSell»;
plus: a non-staff party cannot use the flag; files and the Telegram forward honour the flag.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import HTTPException

from tests.test_deal_chat import _user, call, chat, poll, upload  # noqa: F401
from tests.test_unified_payouts import SELLER_W, env  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]


async def _send(env, chat, deal_id, uid, text, *, as_guarantor=False, client_id=None):
    r, _ = chat
    body = r.ChatMessageCreate(text=text, client_id=client_id, as_guarantor=as_guarantor)
    return await call(env, r.post_chat_message, deal_id, body, user=uid)


async def _make_staff(env, uid, role="admin"):
    from app.models.user import User, UserRole

    async with env.orm.session() as db:
        u = await db.get(User, uid)
        u.role = UserRole(role)
        await db.commit()


@pytest.mark.asyncio
async def test_moderator_non_party_is_guarantor_with_and_without_flag(env, chat):
    deal_id, _ = await env.make_deal(env.S.paid)
    mod = await _user(env, role="moderator", tg=7101)
    a = await _send(env, chat, deal_id, mod.id, "Гарант на звʼязку")
    b = await _send(env, chat, deal_id, mod.id, "Ще раз", as_guarantor=True)
    assert a["sender_role"] == "guarantor" and a["as_guarantor"] is False
    assert b["sender_role"] == "guarantor" and b["as_guarantor"] is True
    assert b["sender_name"] == "TgSell"


@pytest.mark.asyncio
async def test_admin_who_is_seller_party_priority_without_flag(env, chat):
    deal_id, _ = await env.make_deal(env.S.paid)
    await _make_staff(env, env.ids.seller, "admin")
    m = await _send(env, chat, deal_id, env.ids.seller, "Я продавець")
    assert m["sender_role"] == "seller" and m["as_guarantor"] is False


@pytest.mark.asyncio
async def test_admin_who_is_seller_with_flag_is_guarantor(env, chat):
    deal_id, _ = await env.make_deal(env.S.paid)
    await _make_staff(env, env.ids.seller, "admin")
    m = await _send(env, chat, deal_id, env.ids.seller, "Пишу як гарант", as_guarantor=True)
    assert m["sender_role"] == "guarantor" and m["as_guarantor"] is True
    assert m["sender_name"] == "TgSell"
    # persisted: the buyer sees it as guarantor too, and the poll payload is consistent
    p = await poll(env, chat, deal_id, env.ids.buyer)
    got = [x for x in p["messages"] if x["id"] == m["id"]][0]
    assert got["sender_role"] == "guarantor" and got["sender_name"] == "TgSell"
    # the same account still speaks as seller without the flag
    n = await _send(env, chat, deal_id, env.ids.seller, "А це від продавця")
    assert n["sender_role"] == "seller"


@pytest.mark.asyncio
async def test_non_staff_party_cannot_post_as_guarantor(env, chat):
    deal_id, _ = await env.make_deal(env.S.paid)
    with pytest.raises(HTTPException) as e:
        await _send(env, chat, deal_id, env.ids.buyer, "Я гарант", as_guarantor=True)
    assert e.value.status_code == 403
    p = await poll(env, chat, deal_id, env.ids.seller)
    assert not [m for m in p["messages"] if m["text"] == "Я гарант"]


@pytest.mark.asyncio
async def test_attachment_as_guarantor_and_non_staff_refused(env, chat):
    r, _ = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    await _make_staff(env, env.ids.seller, "moderator")
    m = await call(env, r.upload_attachment, deal_id, file=upload("note.txt", b"hello"), caption="Інструкція",
                   client_id=None, as_guarantor=True, user=env.ids.seller)
    assert m["sender_role"] == "guarantor" and m["as_guarantor"] is True
    with pytest.raises(HTTPException) as e:
        await call(env, r.upload_attachment, deal_id, file=upload("x.txt", b"hello"), caption=None,
                   client_id=None, as_guarantor=True, user=env.ids.buyer)
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_telegram_forward_uses_guarantor_label(env, chat):
    import app.services.chat_bridge as bridge
    from app.models.deal import Deal, DealMessage
    from app.models.user import User

    deal_id, _ = await env.make_deal(env.S.paid)
    await _make_staff(env, env.ids.seller, "admin")
    m = await _send(env, chat, deal_id, env.ids.seller, "Перевірте передачу", as_guarantor=True)
    async with env.orm.session() as db:
        deal = await db.get(Deal, deal_id)
        msg = await db.get(DealMessage, m["id"])
        sender = await db.get(User, env.ids.seller)
        text = bridge.format_forward(deal, msg, sender, None)
        seller_name = sender.first_name
    assert "TgSell (" in text and bridge.ROLE_UA["guarantor"] in text
    assert seller_name not in text


def test_migration_0061_is_additive():
    src = (BACKEND / "alembic/versions/0061_deal_messages_as_guarantor.py").read_text()
    assert 'down_revision = "0060"' in src
    assert "add_column" in src and "server_default=sa.false()" in src and "nullable=False" in src
    up = src.split("def upgrade")[1].split("def downgrade")[0]
    assert "drop" not in up and "UPDATE" not in up.upper()


@pytest.mark.asyncio
async def test_admin_deal_list_exposes_real_ready_flags(env):
    import importlib

    from app.models.deal import Deal
    from app.models.user import User

    admin_router = importlib.import_module("app.routers.admin")
    admin = await _user(env, role="admin", tg=7102)
    deal_id, _ = await env.make_deal(env.S.created)
    async with env.orm.session() as db:
        d = await db.get(Deal, deal_id)
        d.buyer_ready = True
        await db.commit()
    async with env.orm.session() as db:
        rows = await admin_router.get_all_deals(deal_status=None, admin=await db.get(User, admin.id), db=db)
    row = [x for x in rows if x.id == deal_id][0]
    assert row.buyer_ready is True and row.seller_ready is False
