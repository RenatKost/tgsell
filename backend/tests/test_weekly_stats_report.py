"""PR B: weekly admin report — read-only counts, Ukrainian text, Monday 09:00
Europe/Chisinau schedule, once-per-week idempotency, superadmin endpoint."""
from __future__ import annotations

import asyncio
importlib = __import__("importlib")
import sys
from datetime import datetime, timedelta

import pytest

NOW = datetime(2026, 10, 19, 6, 0, 0)  # Monday 09:00 EEST (UTC+3), naive UTC
OLD = NOW - timedelta(days=30)
RECENT = NOW - timedelta(days=2)
NEXT_MON = datetime(2026, 10, 26, 7, 0, 0)  # Mon 09:00 EET — DST ended on 25.10


async def _seed(orm):
    from app.models.activity import UserEvent, UserSession
    from app.models.auction import Auction
    from app.models.bundle import BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus
    from app.models.saved_search import SavedSearch
    from app.models.user import User, UserRole

    async with orm.session() as db:
        old = User(first_name="Old", telegram_id=7001, created_at=OLD, tg_bot_started_at=OLD)
        new_utm = User(first_name="NewUtm", telegram_id=7002, created_at=RECENT,
                       tg_bot_started_at=RECENT, tg_bot_unreachable_at=RECENT)  # unreachable → not a subscriber
        new_anon = User(first_name="NewAnon", created_at=RECENT)
        new_none = User(first_name="NewNone", telegram_id=7004, created_at=RECENT)  # never /start-ed
        admin = User(first_name="Admin", telegram_id=7005, role=UserRole.admin, created_at=OLD)
        db.add_all([old, new_utm, new_anon, new_none, admin])
        await db.flush()

        def ch(status, created):
            return Channel(seller_id=old.id, telegram_link="https://t.me/c", channel_name="C",
                           category="news", price=10, status=status, created_at=created)
        c_old, c_new, c_pending = ch(ChannelStatus.approved, OLD), ch(ChannelStatus.approved, RECENT), ch(ChannelStatus.pending, RECENT)
        db.add_all([c_old, c_new, c_pending, ch(ChannelStatus.sold, RECENT)])
        await db.flush()
        db.add_all([
            ChannelBundle(seller_id=old.id, name="B1", price=5, status=BundleStatus.approved, created_at=OLD),
            ChannelBundle(seller_id=old.id, name="B2", price=5, status=BundleStatus.approved, created_at=RECENT),
            ChannelBundle(seller_id=old.id, name="B3", price=5, status=BundleStatus.pending, created_at=RECENT),
            Auction(channel_id=c_old.id, seller_id=old.id, start_price=1, current_price=1, status="active",
                    starts_at=OLD, ends_at=NOW + timedelta(days=1), created_at=RECENT),
            Auction(channel_id=c_old.id, seller_id=old.id, start_price=1, current_price=1, status="ended",
                    starts_at=OLD, ends_at=OLD, created_at=OLD),
        ])
        for st, created in [(DealStatus.completed, OLD), (DealStatus.completed, RECENT),
                            (DealStatus.paid, RECENT), (DealStatus.cancelled, OLD)]:
            db.add(Deal(channel_id=c_old.id, buyer_id=new_utm.id, seller_id=old.id, status=st,
                        escrow_wallet_address="T" + "x" * 33, escrow_private_key_encrypted="enc",
                        amount_usdt=10, created_at=created))
        db.add_all([SavedSearch(user_id=old.id, name="s1", filters={}),
                    SavedSearch(user_id=new_utm.id, name="s2", filters={})])
        # Visits: new_utm first came from telegram (anon, later linked), new_anon direct.
        db.add_all([
            UserEvent(anon_id="a-utm", event_type="visit", utm_source="telegram", ref_domain="t.me",
                      created_at=RECENT - timedelta(hours=1)),
            UserEvent(user_id=new_utm.id, anon_id="a-utm", event_type="visit", utm_source="google",
                      created_at=RECENT + timedelta(hours=1)),
            UserSession(session_key="s-anon", user_id=new_anon.id, anon_id="a-anon",
                        started_at=RECENT, last_seen_at=RECENT),
            UserEvent(anon_id="a-anon", event_type="visit", created_at=RECENT),
            UserEvent(anon_id="a-other", event_type="visit", utm_source="<script>", created_at=RECENT),
            UserEvent(anon_id="a-old", event_type="visit", utm_source="telegram", created_at=OLD),
            UserEvent(anon_id="a-other", event_type="channel_view", utm_source=None, created_at=RECENT),
        ])
        await db.commit()
        return {"admin": admin.id, "user": old.id}


def _as_map(items):
    return {i["source"]: i["count"] for i in items}


@pytest.mark.asyncio
async def test_collect_weekly_stats_counts(pg_orm):
    ws = importlib.import_module("app.services.weekly_stats")

    await _seed(pg_orm)
    async with pg_orm.session() as db:
        s = await ws.collect_weekly_stats(db, NOW)
    assert s["users"] == {"total": 5, "new": 3}
    assert s["channels"] == {"total": 2, "new": 1}
    assert s["bundles"] == {"total": 2, "new": 1}
    assert s["auctions"] == {"total": 1, "new": 1}
    assert s["deals"]["total"] == 4 and s["deals"]["new"] == 2
    assert s["deals"]["by_status"]["completed"] == 2
    assert s["deals"]["by_status"]["paid"] == 1
    assert s["deals"]["by_status"]["cancelled"] == 1
    assert s["deals"]["by_status"]["disputed"] == 0
    assert s["bot_subscribers"] == 1  # only "Old"
    assert s["saved_searches"] == 2
    assert _as_map(s["new_users_by_utm_source"]) == {"telegram": 1, ws.NO_SOURCE: 1, ws.UNKNOWN_SOURCE: 1}
    assert _as_map(s["new_users_by_ref_domain"]) == {"t.me": 1, ws.NO_SOURCE: 1, ws.UNKNOWN_SOURCE: 1}
    assert s["visits"]["total"] == 4
    assert _as_map(s["visits"]["by_utm_source"]) == {"telegram": 1, "google": 1, ws.NO_SOURCE: 1, "<script>": 1}


@pytest.mark.asyncio
async def test_collect_is_read_only(pg_orm):
    from sqlalchemy import event

    ws = importlib.import_module("app.services.weekly_stats")

    await _seed(pg_orm)
    writes = []

    def spy(conn, cursor, statement, *a):
        if not statement.lstrip().upper().startswith("SELECT"):
            writes.append(statement)

    event.listen(pg_orm.engine.sync_engine, "before_cursor_execute", spy)
    try:
        async with pg_orm.session() as db:
            await ws.collect_weekly_stats(db, NOW)
    finally:
        event.remove(pg_orm.engine.sync_engine, "before_cursor_execute", spy)
    assert [w for w in writes if not w.strip().upper().startswith(("BEGIN", "ROLLBACK", "COMMIT"))] == []


@pytest.mark.asyncio
async def test_report_text_ukrainian_and_valid_html(pg_orm):
    ws = importlib.import_module("app.services.weekly_stats")
    from app.services.alerts import is_valid_telegram_html, telegram_html_safe

    await _seed(pg_orm)
    async with pg_orm.session() as db:
        text = ws.build_weekly_report_text(await ws.collect_weekly_stats(db, NOW))
    for phrase in ("Тижневий звіт", "Користувачі", "Угоди", "завершено: 2", "Підписники бота: 1",
                   "Збережені пошуки: 2", "Візити за 7 днів", "telegram: 1", "Період: 12.10.2026 — 19.10.2026"):
        assert phrase in text.replace("<b>", "").replace("</b>", ""), phrase
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert is_valid_telegram_html(text)
    assert telegram_html_safe(text) == text
    assert len(text) < 4096


@pytest.mark.parametrize("now,due", [
    (datetime(2026, 10, 19, 6, 0), True),     # Mon 09:00 EEST
    (datetime(2026, 10, 19, 5, 59), False),   # Mon 08:59 EEST
    (datetime(2026, 10, 19, 17, 59), True),   # catch-up window
    (datetime(2026, 10, 19, 18, 0), False),   # window over
    (datetime(2026, 10, 20, 6, 0), False),    # Tuesday
    (datetime(2026, 10, 18, 6, 0), False),    # Sunday
    (datetime(2026, 10, 26, 6, 0), False),    # Mon 08:00 EET (DST ended 25.10)
    (datetime(2026, 10, 26, 7, 0), True),     # Mon 09:00 EET
    (datetime(2026, 11, 2, 7, 0), True),      # Mon 09:00 EET (UTC+2, winter)
    (datetime(2026, 11, 2, 6, 30), False),    # Mon 08:30 EET
])
def test_week_due_monday_9_chisinau(now, due):
    ws = importlib.import_module("app.services.weekly_stats")

    res = ws.week_due(now)
    assert (res is not None) == due
    if res:
        assert res[0].startswith("weekly_stats:2026-W")


def test_week_key_is_iso_week():
    ws = importlib.import_module("app.services.weekly_stats")

    assert ws.week_due(datetime(2026, 10, 19, 6, 0))[0] == "weekly_stats:2026-W43"
    assert ws.week_due(datetime(2026, 10, 19, 12, 0))[0] == "weekly_stats:2026-W43"


def _patch_alert(monkeypatch, results):
    import app.services.alerts as alerts

    sent = []

    async def fake(text, alert_key=None, throttle_minutes=30):
        sent.append(text)
        return results.pop(0) if results else True

    monkeypatch.setattr(alerts, "send_admin_alert", fake)
    return sent


@pytest.mark.asyncio
async def test_sends_once_per_week_across_restarts(pg_orm, monkeypatch):
    wr = importlib.import_module("app.tasks.weekly_report")

    await _seed(pg_orm)
    sent = _patch_alert(monkeypatch, [])
    assert await wr.send_weekly_report_once(NOW) is True
    assert await wr.send_weekly_report_once(NOW + timedelta(minutes=5)) is False
    # "restart": fresh module import, same DB state
    sys.modules.pop("app.tasks.weekly_report", None)
    wr2 = importlib.import_module("app.tasks.weekly_report")
    assert wr2 is not wr
    assert await wr2.send_weekly_report_once(NOW + timedelta(hours=1)) is False
    assert len(sent) == 1 and "Тижневий звіт" in sent[0]
    # next Monday → new report
    assert await wr2.send_weekly_report_once(NEXT_MON) is True
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_not_sent_outside_window(pg_orm, monkeypatch):
    wr = importlib.import_module("app.tasks.weekly_report")

    sent = _patch_alert(monkeypatch, [])
    assert await wr.send_weekly_report_once(NOW - timedelta(minutes=1)) is False
    assert await wr.send_weekly_report_once(NOW + timedelta(days=1)) is False
    assert sent == []


@pytest.mark.asyncio
async def test_concurrent_containers_send_once(pg_orm, monkeypatch):
    wr = importlib.import_module("app.tasks.weekly_report")

    sent = _patch_alert(monkeypatch, [])
    res = await asyncio.gather(*(wr.send_weekly_report_once(NOW) for _ in range(4)))
    assert sum(bool(r) for r in res) == 1
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_failed_send_retried_then_capped(pg_orm, monkeypatch):
    from sqlalchemy import select

    from app.models.report import ScheduledReportRun
    ws = importlib.import_module("app.services.weekly_stats")
    wr = importlib.import_module("app.tasks.weekly_report")

    sent = _patch_alert(monkeypatch, [False, False, False, True])
    for i in range(5):
        await wr.send_weekly_report_once(NOW + timedelta(minutes=5 * i))
    assert len(sent) == ws.MAX_ATTEMPTS
    async with pg_orm.session() as db:
        row = (await db.execute(select(ScheduledReportRun))).scalar_one()
    assert row.status == "failed" and row.attempts == ws.MAX_ATTEMPTS

    sent2 = _patch_alert(monkeypatch, [False, True])
    await wr.send_weekly_report_once(NEXT_MON)
    await wr.send_weekly_report_once(NEXT_MON + timedelta(minutes=5))
    await wr.send_weekly_report_once(NEXT_MON + timedelta(minutes=10))
    assert len(sent2) == 2
    async with pg_orm.session() as db:
        row = await db.get(ScheduledReportRun, "weekly_stats:2026-W44")
    assert row.status == "sent" and row.sent_at is not None


@pytest.mark.asyncio
async def test_admin_endpoint_superadmin_only(pg_orm):
    import httpx
    from fastapi import FastAPI

    from app.models.user import User, UserRole
    from app.routers import admin as admin_router
    from app.utils.security import create_access_token

    ids = await _seed(pg_orm)
    async with pg_orm.session() as db:
        mod = User(first_name="Mod", telegram_id=7010, role=UserRole.moderator)
        db.add(mod)
        await db.commit()
        ids["mod"] = mod.id
    app = FastAPI()
    app.include_router(admin_router.router, prefix="/api")

    def hdr(who):
        return {"Authorization": f"Bearer {create_access_token({'sub': str(ids[who])})}"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/admin/stats/weekly")).status_code in (401, 403)
        assert (await c.get("/api/admin/stats/weekly", headers=hdr("user"))).status_code == 403
        r = await c.get("/api/admin/stats/weekly", headers=hdr("mod"))
        assert r.status_code == 403 and r.json()["detail"] == "Лише для адміністратора"
        r = await c.get("/api/admin/stats/weekly", headers=hdr("admin"))
    assert r.status_code == 200
    body = r.json()
    assert body["users"]["total"] == 6 and body["saved_searches"] == 2
    assert {"deals", "bot_subscribers", "visits", "new_users_by_utm_source"} <= body.keys()


def test_scheduler_registered_in_lifespan():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    assert "run_weekly_report()" in src


def test_migration_0044_single_head():
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    mig = (versions / "0044_scheduled_report_runs.py").read_text(encoding="utf-8")
    assert 'revision = "0044"' in mig and 'down_revision = "0043"' in mig
    assert [p.name for p in versions.glob("*.py") if 'down_revision = "0044"' in p.read_text(encoding="utf-8")] == []
