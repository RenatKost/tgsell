"""Campaign relist_top7_2026_10_27: segment, exclusions, no-bot list, verbatim text, idempotency, errors."""
from __future__ import annotations

from datetime import timedelta

import pytest

from tests.test_admin_broadcast import FakeBot, _setup

pytestmark = pytest.mark.asyncio
KEY = "relist_top7_2026_10_27"


async def _seed(orm):
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus as S
    from app.models.user import User, UserRole
    from app.utils.timeutil import utcnow_naive
    now = utcnow_naive()
    async with orm.session() as db:
        mk = lambda n, tg, sub=True, **kw: User(first_name=n, username=n, telegram_id=tg,
                                                tg_bot_started_at=now if sub else None, **kw)
        u = {k: v for k, v in {
            "rm": mk("rm", 201), "sold": mk("sold2", 202), "inact": mk("inact", 203), "unpub": mk("unpub", 204),
            "multi": mk("multi", 205), "nobot": mk("nobot", 206, sub=False), "unreach": mk("unreach", 207),
            "live": mk("live", 208), "excl": mk("excl", 209), "relisted": mk("relisted", 210), "blk": mk("blk", 211),
            "rejnew": mk("rejnew", 212), "adm": mk("adm", 299, role=UserRole.admin),
        }.items()}
        u["unreach"].tg_bot_unreachable_at = now
        db.add_all(u.values())
        await db.flush()

        def ch(k, st, link=None, cid=None, **kw):
            c = Channel(seller_id=u[k].id, telegram_link=link or f"https://t.me/{k}{st.value}", channel_name=f"Канал {k}",
                        category="Спорт", subscribers_count=10, price=10, status=st, **kw)
            if cid:
                c.id = cid
            return c
        lots = [
            ch("rm", S.removed, cid=500), ch("sold", S.sold, cid=501), ch("inact", S.approved, cid=502, inactive_since=now),
            ch("unpub", S.rejected, cid=503, first_approved_at=now - timedelta(days=9)),
            ch("multi", S.removed, cid=504), ch("multi", S.sold, cid=505),
            ch("nobot", S.removed, cid=506), ch("unreach", S.sold, cid=507), ch("live", S.approved, cid=508),
            ch("excl", S.removed, cid=61), ch("excl", S.sold, cid=16),
            ch("relisted", S.removed, link="https://t.me/again", cid=509), ch("relisted", S.pending, link="https://t.me/again", cid=510),
            ch("blk", S.removed, cid=511), ch("rejnew", S.rejected, cid=512), ch("excl", S.removed, cid=520),
        ]
        db.add_all(lots)
        await db.flush()
        b = ChannelBundle(seller_id=u["excl"].id, name="Сітка 1", price=1, status=BundleStatus.approved)
        b.id = 1
        db.add(b)
        await db.flush()
        db.add(BundleChannel(bundle_id=1, channel_id=520))
        await db.commit()
        return u


async def test_dry_run_lists_recipients_and_no_bot(orm, monkeypatch):
    bot = FakeBot()
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u = await _seed(orm)
    async with client:
        cur.user = u["adm"]
        r = (await client.post("/api/admin/broadcast", json={"campaign_key": KEY, "segment": "relist_top7"})).json()
    assert r["dry_run"] is True and bot.sent == []
    rec = {i["username"]: sorted(l["id"] for l in i["lots"]) for i in r["recipients_list"]}
    assert rec == {"rm": [500], "sold2": [501], "inact": [502], "unpub": [503], "multi": [504, 505], "blk": [511]}
    assert r["recipients"] == r["to_send"] == 6
    statuses = {l["id"]: l["status"] for i in r["recipients_list"] for l in i["lots"]}
    assert statuses[502] == "inactive" and statuses[501] == "sold" and statuses[500] == "removed"
    assert {i["username"] for i in r["no_bot"]} == {"nobot", "unreach"}
    assert r["default_text"] == svc.RELIST_TEXT


async def test_admin_only_and_key_locked(orm, monkeypatch):
    client, cur, svc = await _setup(orm, monkeypatch, FakeBot())
    u = await _seed(orm)
    from app.models.user import UserRole
    async with client:
        cur.user = u["rm"]
        assert (await client.post("/api/admin/broadcast", json={"campaign_key": KEY, "segment": "relist_top7"})).status_code == 403
        cur.user = u["adm"]
        r = await client.post("/api/admin/broadcast", json={"campaign_key": "other", "segment": "relist_top7"})
        assert r.status_code == 422


async def test_send_once_verbatim_with_error_report(orm, monkeypatch):
    bot = FakeBot(blocked={211})
    client, cur, svc = await _setup(orm, monkeypatch, bot)
    u = await _seed(orm)
    body = {"campaign_key": KEY, "segment": "relist_top7", "text": "інший текст", "dry_run": False}
    async with client:
        cur.user = u["adm"]
        r = (await client.post("/api/admin/broadcast", json=body)).json()
        assert r["started"] and r["to_send"] == 6
        await svc._tasks[KEY]
        st = (await client.get(f"/api/admin/broadcast/{KEY}")).json()
        assert st["sent"] == 5 and st["failed"] == 1
        assert st["errors"][0]["username"] == "blk" and "blocked" in st["errors"][0]["error"]
        assert len(bot.sent) == 5 and all(t == svc.RELIST_TEXT for _, t in bot.sent)
        assert [c for c, _ in bot.sent].count(205) == 1  # multi-lot seller: one message
        r = (await client.post("/api/admin/broadcast", json=body)).json()
        assert r["to_send"] == 0
        await svc._tasks[KEY]
        assert len(bot.sent) == 5
    from app.models.channel import Channel
    from sqlalchemy import func, select
    async with orm.session() as db:
        assert (await db.execute(select(func.count(Channel.id)))).scalar() == 16  # nothing deleted
