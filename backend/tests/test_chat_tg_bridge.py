"""Task 13 stage B: deal chat ⇄ Telegram bridge."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from tests.test_deal_chat import _user, call, chat, poll, send  # noqa: F401
from tests.test_unified_payouts import env  # noqa: F401


class FakeBot:
    def __init__(self, fail_for=()):
        self.sent, self.edits, self.fail_for, self._n = [], [], set(fail_for), 500

    async def send_message(self, chat_id, text, **kw):
        if chat_id in self.fail_for:
            raise RuntimeError("bot blocked")
        self._n += 1
        self.sent.append(SimpleNamespace(chat_id=chat_id, text=text, kb=kw.get("reply_markup"), mid=self._n))
        return SimpleNamespace(message_id=self._n)

    async def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        self.edits.append((chat_id, message_id, reply_markup))


@pytest.fixture
def br():
    return importlib.import_module("app.services.chat_bridge")


def _buttons(kb):
    return [b for row in kb.inline_keyboard for b in row]


async def _links(env, deal_id):
    from app.models.chat import DealChatTgLink

    async with env.orm.session() as db:
        return list((await db.execute(select(DealChatTgLink).where(
            DealChatTgLink.deal_id == deal_id).order_by(DealChatTgLink.id))).scalars())


@pytest.mark.asyncio
async def test_forward_to_other_party_with_button_not_sender(env, chat, br):
    deal_id, _ = await env.make_deal(env.S.paid)
    m = await send(env, chat, deal_id, env.ids.buyer, "Привіт <b>x</b>")
    bot = FakeBot()
    assert await br.forward_pending(env.orm.session, bot) == 1
    assert [s.chat_id for s in bot.sent] == [9102]  # seller only, never the sender
    s = bot.sent[0]
    assert f"Угода #{deal_id}" in s.text and "&lt;b&gt;x&lt;/b&gt;" in s.text and "Покупець" in s.text
    btns = _buttons(s.kb)
    assert btns[0].text == "Відкрити чат на сайті" and btns[0].url.endswith(f"/deal/{deal_id}#chat")
    assert btns[1].callback_data.startswith("chatread:")
    # at-most-once: second cycle sends nothing
    assert await br.forward_pending(env.orm.session, bot) == 0
    (link,) = await _links(env, deal_id)
    assert link.message_id == m["id"] and link.tg_message_id == s.mid
    # system messages are not forwarded
    from app.models.deal import Deal
    import app.services.chat as chat_svc

    async with env.orm.session() as db:
        chat_svc.system(db, await db.get(Deal, deal_id), "x", "sys")
        await db.commit()
    assert await br.forward_pending(env.orm.session, bot) == 0


@pytest.mark.asyncio
async def test_staff_who_posted_get_forwards_unbound_skipped(env, chat, br):
    from app.models.user import User

    deal_id, _ = await env.make_deal(env.S.paid)
    mod = await _user(env, role="moderator", tg=7101)
    await send(env, chat, deal_id, mod.id, "Гарант тут")
    async with env.orm.session() as db:
        (await db.get(User, env.ids.seller)).telegram_id = None
        await db.commit()
    bot = FakeBot()
    await br.forward_pending(env.orm.session, bot)
    assert [s.chat_id for s in bot.sent] == [9101]  # buyer; seller unbound
    bot.sent.clear()
    await send(env, chat, deal_id, env.ids.buyer, "ок")
    await br.forward_pending(env.orm.session, bot)
    assert [s.chat_id for s in bot.sent] == [7101]


@pytest.mark.asyncio
async def test_send_failure_does_not_block_or_resend(env, chat, br):
    deal_id, _ = await env.make_deal(env.S.paid)
    await send(env, chat, deal_id, env.ids.buyer, "a")
    bot = FakeBot(fail_for={9102})
    assert await br.forward_pending(env.orm.session, bot) == 0
    assert await br.forward_pending(env.orm.session, FakeBot()) == 0


@pytest.mark.asyncio
async def test_reply_writes_into_site_chat_idempotent_and_marks_read(env, chat, br):
    deal_id, _ = await env.make_deal(env.S.paid)
    m = await send(env, chat, deal_id, env.ids.buyer, "Питання")
    bot = FakeBot()
    await br.forward_pending(env.orm.session, bot)
    tgmid = bot.sent[0].mid
    async with env.orm.session() as db:
        out = await br.handle_reply(db, tg_user_id=9102, tg_chat_id=9102, reply_to_message_id=tgmid,
                                    tg_message_id=77, text="Відповідь")
        oid = out.id
    async with env.orm.session() as db:
        again = await br.handle_reply(db, tg_user_id=9102, tg_chat_id=9102, reply_to_message_id=tgmid,
                                      tg_message_id=77, text="Відповідь")
        assert again.id == oid
    p = await poll(env, chat, deal_id, env.ids.buyer)
    mine = [x for x in p["messages"] if x["id"] == oid]
    assert mine and mine[0]["text"] == "Відповідь" and mine[0]["sender_role"] == "seller"
    assert p["peer_read_id"] >= m["id"]  # replying in bot = read
    # reply is forwarded back to the buyer
    bot.sent.clear()
    await br.forward_pending(env.orm.session, bot)
    assert [s.chat_id for s in bot.sent] == [9101]
    # unrelated reply → ignored
    async with env.orm.session() as db:
        assert await br.handle_reply(db, tg_user_id=9102, tg_chat_id=9102, reply_to_message_id=99999,
                                     tg_message_id=78, text="x") is None


@pytest.mark.asyncio
async def test_reply_rejections(env, chat, br):
    from app.models.user import User

    deal_id, _ = await env.make_deal(env.S.paid)
    await send(env, chat, deal_id, env.ids.buyer, "q")
    bot = FakeBot()
    await br.forward_pending(env.orm.session, bot)
    tgmid = bot.sent[0].mid
    await _user(env, tg=7201)  # bound outsider

    async def reply(tg_user, text="hi", n=1):
        async with env.orm.session() as db:
            return await br.handle_reply(db, tg_user_id=tg_user, tg_chat_id=9102, reply_to_message_id=tgmid,
                                         tg_message_id=n, text=text)

    for who in (7201, 9101, 555):  # outsider, other party, unbound
        with pytest.raises(br.BridgeReject):
            await reply(who)
    with pytest.raises(br.BridgeReject):
        await reply(9102, text=None)
    with pytest.raises(br.BridgeReject):
        await reply(9102, text="x" * 2001)
    async with env.orm.session() as db:
        (await db.get(User, env.ids.seller)).is_blocked = True
        await db.commit()
    with pytest.raises(br.BridgeReject):
        await reply(9102)


@pytest.mark.asyncio
async def test_read_sync_both_ways(env, chat, br):
    r, _ = chat
    deal_id, _ = await env.make_deal(env.S.paid)
    m1 = await send(env, chat, deal_id, env.ids.buyer, "1")
    m2 = await send(env, chat, deal_id, env.ids.buyer, "2")
    bot = FakeBot()
    await br.forward_pending(env.orm.session, bot)
    l1, l2 = await _links(env, deal_id)
    # bot tap → site read
    with pytest.raises(br.BridgeReject):
        async with env.orm.session() as db:
            await br.handle_read_tap(db, tg_user_id=9101, link_id=l1.id)
    async with env.orm.session() as db:
        await br.handle_read_tap(db, tg_user_id=9102, link_id=l1.id)
    assert (await poll(env, chat, deal_id, env.ids.buyer))["peer_read_id"] == m1["id"]
    # site read → telegram edit (only l2 pending)
    assert await br.sync_reads_to_telegram(env.orm.session, bot) == 0
    await call(env, r.mark_chat_read, deal_id, r.ReadRequest(message_id=m2["id"]), user=env.ids.seller)
    assert await br.sync_reads_to_telegram(env.orm.session, bot) == 1
    chat_id, mid, kb = bot.edits[0]
    assert (chat_id, mid) == (9102, l2.tg_message_id) and len(_buttons(kb)) == 1
    assert await br.sync_reads_to_telegram(env.orm.session, bot) == 0


@pytest.mark.asyncio
async def test_worker_cycle_runs_bridge(env, chat, br, monkeypatch):
    deal_id, _ = await env.make_deal(env.S.paid)
    await send(env, chat, deal_id, env.ids.buyer, "via worker")
    bot = FakeBot()
    monkeypatch.setattr(br, "get_bot", lambda: bot)
    await env.work()
    assert [s.chat_id for s in bot.sent] == [9102]


@pytest.mark.asyncio
async def test_bot_dispute_adds_system_message(env, monkeypatch):
    from app.models.deal import DealMessage

    bm = importlib.import_module("bot.main")
    monkeypatch.setattr(bm, "async_session", env.orm.session)
    deal_id, _ = await env.make_deal(env.S.paid)
    answers = []

    async def answer(*a, **k):
        answers.append(a)

    async def edit(*a, **k):
        pass

    cb = SimpleNamespace(data=f"deal_dispute:{deal_id}", from_user=SimpleNamespace(id=9101), answer=answer,
                         message=SimpleNamespace(edit_text=edit, answer=answer, edit_reply_markup=edit))
    await bm.cb_deal_dispute(cb)
    async with env.orm.session() as db:
        ev = list((await db.execute(select(DealMessage.event).where(
            DealMessage.deal_id == deal_id, DealMessage.is_system.is_(True)))).scalars())
    assert "dispute_opened" in ev


@pytest.mark.asyncio
async def test_auto_verify_adds_system_message(env, monkeypatch):
    from app.models.deal import DealMessage

    av = importlib.import_module("app.services.checklist_autoverify")
    dr = importlib.import_module("app.routers.deals")

    async def fake(db, deal, items):
        return "Автоперевірку виконано. Результати — біля відповідних пунктів (лише підказка, не замінює ручну перевірку)."

    monkeypatch.setattr(av, "run_auto_verify", fake)
    monkeypatch.setattr(dr, "checklist_svc", importlib.import_module("app.services.deal_checklist"))
    deal_id, _ = await env.make_deal(env.S.channel_transferring)
    await call(env, dr.auto_verify_deal_checklist, deal_id, user=env.ids.buyer)
    async with env.orm.session() as db:
        ev = list((await db.execute(select(DealMessage).where(
            DealMessage.deal_id == deal_id, DealMessage.event == "auto_verify"))).scalars())
    assert len(ev) == 1 and ev[0].tg_forward_status is None


class ChatNotFoundBot(FakeBot):
    async def send_message(self, chat_id, text, **kw):
        if chat_id in self.fail_for:
            raise RuntimeError("Telegram server says - Bad Request: chat not found")
        return await super().send_message(chat_id, text, **kw)


@pytest.mark.asyncio
async def test_chat_not_found_marks_unreachable_and_banner(env, chat, br):
    from app.models.user import User

    r = importlib.import_module("app.routers.chat")
    deal_id, _ = await env.make_deal(env.S.paid)
    st = await call(env, r.tg_notify_state, deal_id, user=env.ids.seller)
    assert st["telegram_bound"] and not st["bot_unreachable"] and not st["bot_started"]
    assert st["deep_link"].endswith(f"?start=deal_{deal_id}")
    await send(env, chat, deal_id, env.ids.buyer, "hi")
    await br.forward_pending(env.orm.session, ChatNotFoundBot(fail_for={9102}))
    st = await call(env, r.tg_notify_state, deal_id, user=env.ids.seller)
    assert st["bot_unreachable"] is True
    # /start deal_<id> → started, unreachable cleared
    async with env.orm.session() as db:
        u = await br.mark_bot_started(db, 9102)
        assert u.id == env.ids.seller
    st = await call(env, r.tg_notify_state, deal_id, user=env.ids.seller)
    assert st["bot_started"] and not st["bot_unreachable"]
    # successful send also clears a stale flag
    async with env.orm.session() as db:
        from app.utils.timeutil import utcnow_naive
        (await db.get(User, env.ids.seller)).tg_bot_unreachable_at = utcnow_naive()
        await db.commit()
    await send(env, chat, deal_id, env.ids.buyer, "again")
    await br.forward_pending(env.orm.session, FakeBot())
    assert not (await call(env, r.tg_notify_state, deal_id, user=env.ids.seller))["bot_unreachable"]
    outsider = await _user(env, tg=7301)
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await call(env, r.tg_notify_state, deal_id, user=outsider)


def test_unreachable_error_classification(br):
    assert br.is_unreachable_error(RuntimeError("Bad Request: chat not found"))
    assert br.is_unreachable_error(RuntimeError("Forbidden: bot was blocked by the user"))
    assert not br.is_unreachable_error(RuntimeError("Too Many Requests: retry after 5"))


@pytest.mark.asyncio
async def test_start_deep_link_answers(env, monkeypatch):
    bm = importlib.import_module("bot.main")
    monkeypatch.setattr(bm, "async_session", env.orm.session)
    out = []

    async def answer(text, **kw):
        out.append(text)

    msg = SimpleNamespace(text="/start deal_5", from_user=SimpleNamespace(id=9101, username="b"), answer=answer)
    await bm.cmd_start(msg)
    assert "#5" in out[-1]
    msg2 = SimpleNamespace(text="/start deal_5", from_user=SimpleNamespace(id=123456, username="x"), answer=answer)
    await bm.cmd_start(msg2)
    assert "не привʼязаний" in out[-1]


@pytest.mark.asyncio
async def test_api_responses_not_cacheable():
    from starlette.responses import JSONResponse

    m = SimpleNamespace(_api_no_store=importlib.import_module("app.utils.http_cache").api_no_store)

    async def nxt(req):
        return JSONResponse({})

    req = SimpleNamespace(url=SimpleNamespace(path="/api/deals/1/chat"))
    assert (await m._api_no_store(req, nxt)).headers["cache-control"] == "no-store"

    async def media(req):
        return JSONResponse({}, headers={"Cache-Control": "public, max-age=86400"})

    assert (await m._api_no_store(req, media)).headers["cache-control"] == "public, max-age=86400"
