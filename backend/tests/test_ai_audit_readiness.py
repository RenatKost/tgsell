"""AI audit never runs on empty stats; cache tied to a stats fingerprint;
closed (invite) channels get subscriber counts without joining; bundle
create/approve schedule a stats refresh."""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace

import pytest
from sqlalchemy import select

AN = {"score": 80, "verdict": "buy", "summary": "ok"}


async def _seed(orm, *, subs=(1000, 2000), snapshots=True, closed_last=False, status="approved"):
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStats, ChannelStatus
    from app.models.user import User

    async with orm.session() as db:
        u = User(first_name="S", telegram_id=936001)
        db.add(u)
        await db.flush()
        chans = []
        for i, n in enumerate(subs):
            closed = closed_last and i == len(subs) - 1
            chans.append(Channel(seller_id=u.id, telegram_link=("+HASH" if closed else f"ch{i}"),
                                 channel_name=f"c{i}", category="Новини", price=0.0,
                                 status=ChannelStatus.approved, subscribers_count=n,
                                 avg_views=100, er=5.0, is_closed=closed))
        db.add_all(chans)
        b = ChannelBundle(seller_id=u.id, name="B", price=33000, status=BundleStatus(status))
        db.add(b)
        await db.flush()
        db.add_all([BundleChannel(bundle_id=b.id, channel_id=c.id, display_order=i) for i, c in enumerate(chans)])
        if snapshots:
            for c in chans:
                if c.subscribers_count and not c.is_closed:
                    db.add(ChannelStats(channel_id=c.id, date=datetime(2026, 10, 22), subscribers=c.subscribers_count,
                                        avg_views=100, avg_reach=100))
        await db.commit()
        return b.id, [c.id for c in chans]


def _counter(monkeypatch, mod, name):
    calls = []

    async def fake(*a, **kw):
        calls.append(a)
        return dict(AN)

    monkeypatch.setattr(mod, name, fake)
    return calls


async def _bundle_ai(orm, bid):
    bundles = importlib.import_module("app.routers.bundles")
    async with orm.session() as db:
        return await bundles.get_bundle_ai_analysis(bundle_id=bid, db=db, viewer=None)


@pytest.mark.asyncio
async def test_bundle_preparing_on_zero_subscribers(orm, monkeypatch):
    bid, _ = await _seed(orm, subs=(1000, 0))
    calls = _counter(monkeypatch, importlib.import_module("app.routers.bundles"), "analyze_bundle")
    res = await _bundle_ai(orm, bid)
    assert res["status"] == "preparing" and "готується" in res["message"]
    assert calls == []
    from app.models.bundle import ChannelBundle
    async with orm.session() as db:
        assert (await db.get(ChannelBundle, bid)).ai_cache is None


@pytest.mark.asyncio
async def test_bundle_preparing_without_dated_snapshot(orm, monkeypatch):
    bid, _ = await _seed(orm, snapshots=False)
    calls = _counter(monkeypatch, importlib.import_module("app.routers.bundles"), "analyze_bundle")
    assert (await _bundle_ai(orm, bid))["status"] == "preparing"
    assert calls == []


@pytest.mark.asyncio
async def test_bundle_cache_fingerprint(orm, monkeypatch):
    from app.models.bundle import ChannelBundle
    from app.models.channel import Channel

    bid, ids = await _seed(orm)
    calls = _counter(monkeypatch, importlib.import_module("app.routers.bundles"), "analyze_bundle")
    assert (await _bundle_ai(orm, bid))["score"] == 80
    assert (await _bundle_ai(orm, bid))["score"] == 80
    assert len(calls) == 1  # second served from cache
    async with orm.session() as db:
        raw = (await db.get(ChannelBundle, bid)).ai_cache
        assert "_stats_fp" in json.loads(raw)
        (await db.get(Channel, ids[0])).subscribers_count = 5555
        await db.commit()
    res = await _bundle_ai(orm, bid)
    assert len(calls) == 2 and "_stats_fp" not in res  # stats changed → regenerated


@pytest.mark.asyncio
async def test_legacy_cache_without_fingerprint_ignored(orm, monkeypatch):
    from app.models.bundle import ChannelBundle
    from app.utils.timeutil import utcnow_naive

    bid, _ = await _seed(orm)
    async with orm.session() as db:
        b = await db.get(ChannelBundle, bid)
        b.ai_cache = json.dumps({"score": 45, "verdict": "hold", "summary": "0 підписників"})
        b.ai_cache_updated_at = utcnow_naive()
        await db.commit()
    calls = _counter(monkeypatch, importlib.import_module("app.routers.bundles"), "analyze_bundle")
    assert (await _bundle_ai(orm, bid))["score"] == 80 and len(calls) == 1


@pytest.mark.asyncio
async def test_closed_channel_with_count_is_ready(orm, monkeypatch):
    bid, _ = await _seed(orm, subs=(1000, 167640), closed_last=True)
    calls = _counter(monkeypatch, importlib.import_module("app.routers.bundles"), "analyze_bundle")
    assert (await _bundle_ai(orm, bid))["score"] == 80 and len(calls) == 1


@pytest.mark.asyncio
async def test_channel_ai_preparing_and_ready(orm, monkeypatch):
    bid, ids = await _seed(orm, subs=(0, 2000))
    ai = importlib.import_module("app.services.ai_analysis")
    calls = _counter(monkeypatch, ai, "analyze_channel")
    channels = importlib.import_module("app.routers.channels")
    async with orm.session() as db:
        r0 = await channels.get_ai_analysis(channel_id=ids[0], db=db, viewer=None)
    async with orm.session() as db:
        r1 = await channels.get_ai_analysis(channel_id=ids[1], db=db, viewer=None)
    assert r0["status"] == "preparing" and r1["score"] == 80 and len(calls) == 1


@pytest.mark.asyncio
async def test_bundle_info_has_is_closed(orm):
    bid, _ = await _seed(orm, subs=(1000, 167640), closed_last=True)
    bundles = importlib.import_module("app.routers.bundles")
    async with orm.session() as db:
        r = await bundles.get_bundle(bundle_id=bid, db=db, viewer=None)
    assert [c.is_closed for c in r.channels] == [False, True]
    assert r.channels[1].subscribers_count == 167640


# ── invite-link subscriber counts ──────────────────────────────────────

def test_parse_invite_preview_count():
    from app.services.channel_stats import parse_invite_preview_count as p
    assert p('<div class="tgme_page_extra">167 640 subscribers</div>') == 167640
    assert p('<div class="tgme_page_extra">1\u00a0234 members</div>') == 1234
    assert p('<div class="tgme_page_extra">@x</div>') is None


class _FakeClient:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def is_connected(self):
        return True

    async def __call__(self, req):
        self.calls.append(type(req).__name__)
        if self.exc:
            raise self.exc
        return self.result


@pytest.mark.asyncio
async def test_invite_via_connected_telethon(monkeypatch):
    cs = importlib.import_module("app.services.channel_stats")
    client = _FakeClient(result=SimpleNamespace(participants_count=167640))
    monkeypatch.setattr(cs, "_telethon_client", client)
    monkeypatch.setattr(cs, "_telethon_status", "connected")

    async def boom(*a, **kw):
        raise AssertionError("must not create/connect a client")

    monkeypatch.setattr(cs, "_get_telethon_client", boom)
    assert await cs.collect_invite_subscribers("https://t.me/+TNWUA62W9pQ3YzYy") == 167640
    assert client.calls == ["CheckChatInviteRequest"]  # read-only, never ImportChatInvite


@pytest.mark.asyncio
async def test_invite_floodwait_falls_back_to_preview(monkeypatch):
    from telethon.errors import FloodWaitError

    cs = importlib.import_module("app.services.channel_stats")
    monkeypatch.setattr(cs, "_telethon_client", _FakeClient(exc=FloodWaitError(request=None, capture=120)))
    monkeypatch.setattr(cs, "_telethon_status", "connected")

    async def preview(h):
        assert h == "TNWUA62W9pQ3YzYy"
        return 167000

    monkeypatch.setattr(cs, "_invite_count_via_preview", preview)
    assert await cs.collect_invite_subscribers("+TNWUA62W9pQ3YzYy") == 167000


@pytest.mark.asyncio
async def test_invite_without_client_uses_preview_only(monkeypatch):
    cs = importlib.import_module("app.services.channel_stats")
    monkeypatch.setattr(cs, "_telethon_client", None)
    monkeypatch.setattr(cs, "_telethon_status", "waiting")

    async def boom(*a, **kw):
        raise AssertionError("must not connect")

    async def preview(h):
        return 42

    monkeypatch.setattr(cs, "_get_telethon_client", boom)
    monkeypatch.setattr(cs, "_invite_count_via_preview", preview)
    assert await cs.collect_invite_subscribers("+abc") == 42
    assert await cs.collect_invite_subscribers("@public") is None


@pytest.mark.asyncio
async def test_stats_collector_closed_channel(orm, monkeypatch):
    from app.models.channel import Channel, ChannelStats

    if orm.kind != "postgres":
        pytest.skip("record_stats uses PG upsert")
    bid, ids = await _seed(orm, subs=(1000, 0), closed_last=True)
    sc = importlib.import_module("app.tasks.stats_collector")

    async def count(link):
        return 167640 if link == "+HASH" else None

    async def nosleep(*a):
        return None

    monkeypatch.setattr(sc, "collect_invite_subscribers", count)
    monkeypatch.setattr(sc.asyncio, "sleep", nosleep)
    assert await sc.collect_closed_channels_once() == 1
    async with orm.session() as db:
        ch = await db.get(Channel, ids[1])
        snaps = (await db.execute(select(ChannelStats).where(ChannelStats.channel_id == ids[1]))).scalars().all()
    assert ch.subscribers_count == 167640 and [s.subscribers for s in snaps] == [167640]


# ── refresh scheduled on bundle create / approve ───────────────────────

@pytest.mark.asyncio
async def test_approve_and_create_schedule_refresh(orm, monkeypatch):
    from app.models.user import User, UserRole

    scheduled = []
    sc = importlib.import_module("app.tasks.stats_collector")
    monkeypatch.setattr(sc, "schedule_stats_refresh", lambda ids: scheduled.append(sorted(ids)))
    stub = ModuleType("bot.main")

    async def _noop(*a, **kw):
        return None

    stub.notify_bundle_approved = stub.notify_bundle_rejected = _noop
    monkeypatch.setitem(sys.modules, "bot.main", stub)

    bid, ids = await _seed(orm, status="pending")
    admin_mod = importlib.import_module("app.routers.admin")
    async with orm.session() as db:
        admin = User(first_name="A", telegram_id=936009, role=UserRole.admin)
        db.add(admin)
        await db.commit()
        await admin_mod.approve_bundle(bundle_id=bid, admin=admin, db=db)
    assert scheduled == [sorted(ids)]

    bundles = importlib.import_module("app.routers.bundles")
    from app.schemas.bundle import BundleCreate
    async with orm.session() as db:
        seller = User(first_name="N", telegram_id=936010)
        db.add(seller)
        await db.commit()
        body = BundleCreate(name="Нова", price=100, channel_links=["@open_one", "https://t.me/+CLOSEDhash"],
                            channel_subscribers=[999, 5000])
        r = await bundles.create_bundle(body=body, user=seller, db=db)
    assert len(scheduled) == 2 and len(scheduled[1]) == 2
    by_link = {c.telegram_link: c for c in r.channels}
    closed = by_link["+CLOSEDhash"]
    assert closed.is_closed is True and closed.subscribers_count == 5000
    assert by_link["open_one"].subscribers_count == 0  # seller number ignored for open channels
