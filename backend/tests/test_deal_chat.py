"""Deal chat v2 (migration 0029) — real Postgres."""
from __future__ import annotations

import io
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from tests.test_unified_payouts import SELLER_W, env  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]


def _png(w=40, h=30, exif=False) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (w, h), (200, 10, 10))
    b = io.BytesIO()
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "SecretCam"
        img.save(b, format="JPEG", exif=ex.tobytes())
    else:
        img.save(b, format="PNG")
    return b.getvalue()


@pytest.fixture
def chat():
    import importlib

    return importlib.import_module("app.routers.chat"), importlib.import_module("app.services.chat")


async def _user(env, uid=None, role=None, tg=None):
    from app.models.user import User, UserRole

    async with env.orm.session() as db:
        if uid:
            return await db.get(User, uid)
        u = User(first_name=f"U{tg}", telegram_id=tg, role=UserRole(role or "user"))
        db.add(u)
        await db.commit()
        return u


async def call(env, fn, *a, user, **kw):
    from app.models.user import User

    async with env.orm.session() as db:
        u = await db.get(User, user.id if hasattr(user, "id") else user)
        return await fn(*a, user=u, db=db, **kw)


def upload(name, data):
    return UploadFile(file=io.BytesIO(data), filename=name)


async def send(env, chat, deal_id, uid, text, client_id=None):
    r, _ = chat
    return await call(env, r.post_chat_message, deal_id, r.ChatMessageCreate(text=text, client_id=client_id), user=uid)


async def poll(env, chat, deal_id, uid, after_id=0):
    r, _ = chat
    return await call(env, r.poll_chat, deal_id, after_id=after_id, limit=100, user=uid)


@pytest.mark.asyncio
async def test_access_parties_and_staff_only(env, chat):
    r, _ = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    outsider = await _user(env, tg=7001)
    mod = await _user(env, role="moderator", tg=7002)
    for fn, args in ((r.poll_chat, dict(after_id=0, limit=10)), (r.chat_history, dict(before_id=5, limit=10))):
        with pytest.raises(HTTPException) as e:
            await call(env, fn, deal_id, user=outsider, **args)
        assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        await send(env, chat, deal_id, outsider.id, "hi")
    assert e.value.status_code == 403
    m = await send(env, chat, deal_id, mod.id, "Гарант на звʼязку")
    assert m["sender_role"] == "guarantor"
    p = await poll(env, chat, deal_id, env.ids.buyer)
    assert p["messages"][-1]["id"] == m["id"]


@pytest.mark.asyncio
async def test_cursor_idempotent_send_and_limits(env, chat):
    deal_id, _ = await env.make_deal(env.S.paid)
    a = await send(env, chat, deal_id, env.ids.buyer, "one", client_id="c-1")
    again = await send(env, chat, deal_id, env.ids.buyer, "one", client_id="c-1")
    assert again["id"] == a["id"]
    b = await send(env, chat, deal_id, env.ids.seller, "two")
    p = await poll(env, chat, deal_id, env.ids.seller, after_id=a["id"])
    assert [m["id"] for m in p["messages"]] == [b["id"]]
    with pytest.raises(HTTPException):
        await send(env, chat, deal_id, env.ids.buyer, "x" * 2001)
    with pytest.raises(HTTPException):
        await send(env, chat, deal_id, env.ids.buyer, "   ")
    r, _ = chat
    h = await call(env, r.chat_history, deal_id, before_id=b["id"], limit=50, user=env.ids.buyer)
    assert [m["id"] for m in h["messages"]] == [a["id"]]


@pytest.mark.asyncio
async def test_delivered_read_ticks_and_unread(env, chat):
    r, _ = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    mod = await _user(env, role="moderator", tg=7003)
    m = await send(env, chat, deal_id, env.ids.buyer, "hello")
    p = await poll(env, chat, deal_id, env.ids.buyer)
    assert p["peer_delivered_id"] < m["id"] and p["peer_read_id"] < m["id"]
    # staff reading never produces ticks
    await poll(env, chat, deal_id, mod.id)
    await call(env, r.mark_chat_read, deal_id, r.ReadRequest(message_id=m["id"]), user=mod)
    assert (await poll(env, chat, deal_id, env.ids.buyer))["peer_read_id"] < m["id"]
    sp = await poll(env, chat, deal_id, env.ids.seller)  # delivered to seller
    assert sp["unread"] >= 1
    assert (await poll(env, chat, deal_id, env.ids.buyer))["peer_delivered_id"] >= m["id"]
    res = await call(env, r.mark_chat_read, deal_id, r.ReadRequest(message_id=m["id"]), user=env.ids.seller)
    assert res["unread"] == 0
    # read pointer never goes back, and is clamped to existing messages
    await call(env, r.mark_chat_read, deal_id, r.ReadRequest(message_id=1), user=env.ids.seller)
    res = await call(env, r.mark_chat_read, deal_id, r.ReadRequest(message_id=10**9), user=env.ids.seller)
    assert res["last_read_message_id"] == m["id"]
    bp = await poll(env, chat, deal_id, env.ids.buyer)
    assert bp["peer_read_id"] >= m["id"]
    u = await call(env, r.my_unread, ids=None, user=env.ids.seller)
    assert u["unread"][str(deal_id)] == 0


@pytest.mark.asyncio
async def test_typing_presence_ttl_and_rate_limit(env, chat):
    r, svc = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    assert (await call(env, r.chat_typing, deal_id, user=env.ids.buyer))["ok"] is True
    assert (await call(env, r.chat_typing, deal_id, user=env.ids.buyer))["ok"] is False  # < 2s
    p = await poll(env, chat, deal_id, env.ids.seller)
    me = [x for x in p["presence"] if x["user_id"] == env.ids.buyer][0]
    assert me["typing"] and me["online"] and me["role"] == "buyer"
    async with env.orm.session() as db:
        row = await db.get(svc.DealChatPresence, (deal_id, env.ids.buyer))
        row.typing_until -= timedelta(seconds=6)
        row.last_seen_at -= timedelta(minutes=5)
        await db.commit()
    p = await poll(env, chat, deal_id, env.ids.seller)
    me = [x for x in p["presence"] if x["user_id"] == env.ids.buyer][0]
    assert not me["typing"] and not me["online"] and me["last_seen_at"]


@pytest.mark.asyncio
async def test_no_polling_for_terminal_deals_and_header(env, chat):
    deal_id, _ = await env.make_deal(env.S.completed)
    p = await poll(env, chat, deal_id, env.ids.buyer)
    assert p["deal"]["polling"] is False and p["poll_interval_ms"] is None
    d2, _ = await env.make_deal(env.S.paid)
    p = await poll(env, chat, d2, env.ids.buyer)
    assert p["deal"]["polling"] is True and p["deal"]["status"] == "paid" and "seller" in p["deal"]["checklist"]


@pytest.mark.asyncio
async def test_blocked_party_reads_but_cannot_post(env, chat):
    import importlib

    admin_router = importlib.import_module("app.routers.admin")
    admin = await _user(env, role="admin", tg=7004)
    deal_id, _ = await env.make_deal(env.S.paid)
    async with env.orm.session() as db:
        from app.models.user import User

        await admin_router.block_user(env.ids.seller, admin_router.BlockRequest(reason="test block"),
                                      admin=await db.get(User, admin.id), db=db)
    await poll(env, chat, deal_id, env.ids.seller)
    with pytest.raises(HTTPException) as e:
        await send(env, chat, deal_id, env.ids.seller, "hi")
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_system_messages_from_lifecycle(env, chat):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    p = await poll(env, chat, deal_id, env.ids.buyer)
    events = [m["event"] for m in p["messages"] if m["is_system"]]
    assert events.count("payout_queued") == 1 and events.count("payout_done") == 1
    sysm = [m for m in p["messages"] if m["is_system"]]
    assert all(m["sender_id"] is None and m["sender_role"] is None for m in sysm)


@pytest.mark.asyncio
async def test_system_helper_rolls_back_with_transaction(env, chat):
    _, svc = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    async with env.orm.session() as db:
        svc.system(db, deal_id, "payment_received", "x")
        await db.rollback()
    from app.models.deal import DealMessage

    async with env.orm.session() as db:
        assert (await db.execute(select(DealMessage).where(DealMessage.deal_id == deal_id))).scalars().all() == []


@pytest.mark.asyncio
async def test_legacy_system_rows_render_as_system(env, chat):
    from app.models.deal import DealMessage

    deal_id, _ = await env.make_deal(env.S.paid)
    async with env.orm.session() as db:
        db.add(DealMessage(deal_id=deal_id, sender_id=env.ids.buyer, text="legacy", is_system=True))
        await db.commit()
    m = (await poll(env, chat, deal_id, env.ids.seller))["messages"][0]
    assert m["kind"] == "system" and m["sender_id"] is None


@pytest.mark.asyncio
async def test_image_upload_reencoded_exif_stripped_and_served(env, chat):
    r, _ = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    jpg = _png(exif=True)
    assert b"SecretCam" in jpg
    m = await call(env, r.upload_attachment, deal_id, file=upload("photo.jpg", jpg), caption=None,
                   client_id="f-1", user=env.ids.buyer)
    att = m["attachment"]
    assert att["is_image"] and att["width"] == 40 and att["has_thumb"]
    resp = await call(env, r.download_attachment, deal_id, att["id"], thumb=False, user=env.ids.seller)
    assert b"SecretCam" not in resp.body and resp.media_type == "image/jpeg"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in resp.headers["content-security-policy"]
    assert resp.headers["content-disposition"].startswith("inline")
    th = await call(env, r.download_attachment, deal_id, att["id"], thumb=True, user=env.ids.seller)
    assert th.body[:3] == b"\xff\xd8\xff"
    outsider = await _user(env, tg=7005)
    with pytest.raises(HTTPException) as e:
        await call(env, r.download_attachment, deal_id, att["id"], thumb=False, user=outsider)
    assert e.value.status_code == 403
    other, _ = await env.make_deal(env.S.paid)
    with pytest.raises(HTTPException) as e:  # attachment id from another deal
        await call(env, r.download_attachment, other, att["id"], thumb=False, user=env.ids.buyer)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_pdf_served_as_attachment(env, chat):
    r, _ = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    m = await call(env, r.upload_attachment, deal_id, file=upload("doc.pdf", b"%PDF-1.4\n%%EOF\n"), caption="договір",
                   client_id=None, user=env.ids.seller)
    resp = await call(env, r.download_attachment, deal_id, m["attachment"]["id"], thumb=False, user=env.ids.buyer)
    assert resp.headers["content-disposition"].startswith("attachment") and m["text"] == "договір"


@pytest.mark.asyncio
@pytest.mark.parametrize("name,data", [
    ("evil.jpg", b"MZ\x90\x00" + b"\x00" * 100),
    ("evil.png", b"\x7fELF" + b"\x00" * 100),
    ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
    ("x.txt", b"<html><script>alert(1)</script></html>"),
    ("x.html", b"<html></html>"),
    ("fake.png", b"%PDF-1.4 not a png"),
    ("run.sh", b"#!/bin/sh\nrm -rf /"),
    ("script.txt", b"#!/usr/bin/env python\nprint(1)"),
    ("app.exe", b"MZ"),
    ("bad.jpg", b"\xff\xd8\xff garbage"),
])
async def test_rejected_files(env, chat, name, data):
    r, _ = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    with pytest.raises(HTTPException) as e:
        await call(env, r.upload_attachment, deal_id, file=upload(name, data), caption=None, client_id=None,
                   user=env.ids.buyer)
    assert e.value.status_code == 415


@pytest.mark.asyncio
async def test_size_and_quotas(env, chat, monkeypatch):
    r, svc = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    with pytest.raises(HTTPException) as e:
        await call(env, r.upload_attachment, deal_id, file=upload("big.txt", b"a" * (svc.MAX_FILE_BYTES + 1)),
                   caption=None, client_id=None, user=env.ids.buyer)
    assert e.value.status_code == 413
    monkeypatch.setattr(svc, "MAX_FILES_PER_HOUR", 2)
    for i in range(2):
        await call(env, r.upload_attachment, deal_id, file=upload(f"n{i}.txt", b"hello"), caption=None,
                   client_id=None, user=env.ids.buyer)
    with pytest.raises(HTTPException) as e:
        await call(env, r.upload_attachment, deal_id, file=upload("n3.txt", b"hello"), caption=None,
                   client_id=None, user=env.ids.buyer)
    assert e.value.status_code == 429
    monkeypatch.setattr(svc, "MAX_DEAL_BYTES", 12)
    with pytest.raises(HTTPException) as e:
        await call(env, r.upload_attachment, deal_id, file=upload("s.txt", b"hello"), caption=None,
                   client_id=None, user=env.ids.seller)
    assert e.value.status_code == 413
    monkeypatch.setattr(svc, "MAX_DEAL_BYTES", 10**9)
    monkeypatch.setattr(svc, "MAX_GLOBAL_BYTES", 12)
    with pytest.raises(HTTPException) as e:
        await call(env, r.upload_attachment, deal_id, file=upload("s.txt", b"hello"), caption=None,
                   client_id=None, user=env.ids.seller)
    assert e.value.status_code == 507
    assert any(c.kwargs.get("alert_key") == "chat_storage_full" for c in env.alert.await_args_list)


@pytest.mark.asyncio
async def test_image_bomb_rejected(env, chat, monkeypatch):
    r, svc = chat
    monkeypatch.setattr(svc, "MAX_IMAGE_PIXELS", 1000)
    deal_id, _ = await env.make_deal(env.S.paid)
    with pytest.raises(HTTPException) as e:
        await call(env, r.upload_attachment, deal_id, file=upload("big.png", _png(100, 100)), caption=None,
                   client_id=None, user=env.ids.buyer)
    assert e.value.status_code == 413


def test_safe_filename():
    import importlib

    svc = importlib.import_module("app.services.chat")
    assert svc.safe_filename("../../etc/passwd") == "passwd"
    assert svc.safe_filename('a"<b>.pdf') == "ab.pdf"
    assert len(svc.safe_filename("x" * 300 + ".pdf")) <= 100


def test_frontend_chat_safety():
    root = BACKEND.parent / "src" / "components" / "DealChat"
    src = "".join(p.read_text() for p in root.glob("*.jsx"))
    assert "dangerouslySetInnerHTML" not in src
    assert "visibilitychange" in src and "poll_interval_ms" in src
    for f in ("DealPage.jsx", "ModerCabinet.jsx"):
        assert "dealsAPI.getMessages" not in (BACKEND.parent / "src" / "layouts" / f).read_text()


def test_all_chat_routes_check_access():
    src = (BACKEND / "app/routers/chat.py").read_text()
    import re

    for fn in re.findall(r"async def (\w+)\(", src):
        if fn.startswith("_") or fn == "my_unread":
            continue
        body = src[src.index(f"async def {fn}("):]
        body = body[: body.index("\n\n\n") if "\n\n\n" in body else len(body)]
        assert "load_deal_for" in body, fn
