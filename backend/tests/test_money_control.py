"""PR 2: transactions/queue/escrow overview/gas monitor/daily summary — Postgres, TRON mocked."""
from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from tests.test_unified_payouts import MASTER, SELLER_W, env  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]


def mm():
    return importlib.import_module("app.routers.admin_money")


def gm():
    return importlib.import_module("app.services.gas_monitor")


async def _admin(env):
    from app.models.user import User, UserRole

    async with env.orm.session() as db:
        u = User(first_name="Admin", telegram_id=9990, role=UserRole.admin)
        db.add(u)
        await db.commit()
        return u


async def _q(env, fn, *a, **kw):
    async with env.orm.session() as db:
        kw.setdefault("admin", None)
        return await fn(*a, db=db, **kw)


async def _broadcast_pending(env, *, age_min=20):
    """Deal in payout_in_progress with a broadcast (tx_hash set) pending release tx."""
    deal_id, escrow = await env.make_deal(env.S.awaiting_payout)
    r = await env.seller_wallet(deal_id, run_worker=False)
    assert r.status == "payout_in_progress"
    env.tron.default_receipt = {"status": "PENDING", "reason": None}
    await env.work()
    tx = (await env.txs(deal_id))[-1]
    assert tx.tx_hash and tx.status == env.TS.pending
    async with env.orm.session() as db:
        t = await db.get(env.Tx, tx.id)
        t.broadcast_at = datetime.utcnow() - timedelta(minutes=age_min)
        await db.commit()
    return deal_id, escrow, tx.id


@pytest.mark.asyncio
async def test_transactions_filters_links_and_csv(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    common = dict(status=None, deal_id=None, address=None, date_from=None, date_to=None,
                  receipt_status=None, page=1, limit=50)
    r = await _q(env, mm().list_transactions, type="release", format="json", **common)
    assert r["total"] == 1
    row = r["items"][0]
    assert row["tronscan_url"] == f"https://tronscan.org/#/transaction/{row['tx_hash']}"
    r = await _q(env, mm().list_transactions, type=None, format="json", **{**common, "address": SELLER_W})
    assert r["total"] == 1
    resp = await _q(env, mm().list_transactions, type=None, format="csv", **common)
    body = b"".join([c if isinstance(c, bytes) else c.encode() async for c in resp.body_iterator]).decode()
    assert body.splitlines()[0].startswith("id,deal_id,type") and "tronscan.org" in body
    with pytest.raises(HTTPException):
        await _q(env, mm().list_transactions, type="bogus", format="json", **common)


@pytest.mark.asyncio
async def test_queue_stages_and_recheck_never_resends(env):
    deal_id, _, tx_id = await _broadcast_pending(env, age_min=20)
    q = await _q(env, mm().payout_queue, failed_hours=72)
    assert [r["id"] for r in q["stale"]] == [tx_id]
    sent = len(env.tron.broadcasts)
    admin = await _admin(env)
    r = await _q(env, mm().recheck_transaction, tx_id, admin=admin)
    assert r["outcome"] == "pending" and len(env.tron.broadcasts) == sent
    env.tron.default_receipt = {"status": "SUCCESS", "reason": None}
    r = await _q(env, mm().recheck_transaction, tx_id, admin=admin)
    assert r["outcome"] == "success" and r["deal_status"] == "completed"
    assert len(env.tron.broadcasts) == sent  # never resent
    with pytest.raises(HTTPException) as e:
        await _q(env, mm().recheck_transaction, tx_id, admin=admin)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_mark_failed_preconditions(env):
    admin = await _admin(env)
    body = mm().MarkFailedRequest(note="not on chain")
    # fresh → refused
    deal_id, escrow, tx_id = await _broadcast_pending(env, age_min=1)
    with pytest.raises(HTTPException) as e:
        await _q(env, mm().mark_transaction_failed, tx_id, body, admin=admin)
    assert e.value.status_code == 409
    async with env.orm.session() as db:
        t = await db.get(env.Tx, tx_id)
        t.broadcast_at = datetime.utcnow() - timedelta(minutes=30)
        await db.commit()
    # escrow drained (funds may have gone) → refused
    full = env.tron.balances[escrow]
    env.tron.balances[escrow] = 0
    with pytest.raises(HTTPException) as e:
        await _q(env, mm().mark_transaction_failed, tx_id, body, admin=admin)
    assert e.value.status_code == 409
    assert (await env.get(deal_id)).status == env.S.payout_in_progress
    # unknown balance → refused
    env.tron.balances[escrow] = RuntimeError("tron down")
    with pytest.raises(HTTPException) as e:
        await _q(env, mm().mark_transaction_failed, tx_id, body, admin=admin)
    assert e.value.status_code == 503
    # stale + not found + funds still there → failed, claim released, no resend
    env.tron.balances[escrow] = full
    sent = len(env.tron.broadcasts)
    r = await _q(env, mm().mark_transaction_failed, tx_id, body, admin=admin)
    assert r["outcome"] == "failed" and r["deal_status"] == "awaiting_payout"
    assert len(env.tron.broadcasts) == sent
    from app.models.user import AdminAuditLog

    async with env.orm.session() as db:
        acts = [a.action for a in (await db.execute(select(AdminAuditLog))).scalars()]
    assert "tx.mark_failed" in acts


@pytest.mark.asyncio
async def test_mark_failed_found_on_chain_finalizes_by_receipt(env):
    admin = await _admin(env)
    deal_id, _, tx_id = await _broadcast_pending(env, age_min=30)
    env.tron.default_receipt = {"status": "SUCCESS", "reason": None}
    with pytest.raises(HTTPException) as e:
        await _q(env, mm().mark_transaction_failed, tx_id, mm().MarkFailedRequest(note="xx x"), admin=admin)
    assert e.value.status_code == 409
    assert (await env.get(deal_id)).status == env.S.completed


@pytest.mark.asyncio
async def test_escrow_overview_fee_states_and_stray(env, monkeypatch):
    from app.routers import admin as admin_router

    monkeypatch.setattr(env.payouts.escrow_svc, "fetch_usdt_balance", lambda a: env.tron.fetch_units(a) / 1e6)

    admin_router._escrow_balances_cache.update(at=0.0, payload=None)
    done, esc_done = await env.make_deal(env.S.awaiting_payout, amount=100.0, fee=3.0)
    await env.seller_wallet(done)
    env.tron.balances[esc_done] = 3_000_000  # fee left after release
    legacy, esc_legacy = await env.make_deal(env.S.completed, amount=50.0, fee=1.5, payout_tx_hash="legacyhash")
    env.tron.balances[esc_legacy] = 1_500_000
    stray, esc_stray = await env.make_deal(env.S.cancelled, amount=4.0, fee=0.0)  # like deal #3
    active, _ = await env.make_deal(env.S.paid, amount=20.0, fee=0.6)
    r = await _q(env, mm().escrow_overview, refresh=True)
    rows = {i["deal_id"]: i for i in r["items"]}
    assert rows[done]["fee_state"] == "collectable" and not rows[done]["mismatch"]
    assert rows[legacy]["fee_state"] == "not_collectable"
    assert rows[stray]["stray"] and rows[stray]["read_only"] and rows[stray]["live_usdt"] == 4.0
    assert rows[active]["expected_usdt"] == 20.0 and not rows[active]["mismatch"]
    t = r["totals"]
    assert t["collectable"] == 3.0 and t["not_collectable_legacy"] == 1.5
    assert t["stray_cancelled"] == 4.0 and t["held_active"] == 20.0 and t["accrued"] == 4.5
    assert (await env.get(stray)).status == env.S.cancelled  # read-only
    env.tron.balances[esc_done] = 1_000_000
    admin_router._escrow_balances_cache.update(at=0.0, payload=None)
    r = await _q(env, mm().escrow_overview, refresh=True)
    assert {i["deal_id"]: i for i in r["items"]}[done]["mismatch"] is True


def test_gas_evaluate_levels_and_topup():
    g = gm()
    st = g.evaluate({"trx_sun": 54_000_000, "energy_fee_sun": 100}, address=MASTER)
    assert st["cost_trx"] == {"new_receiver": 17.4, "existing_holder": 9.6}
    assert st["payouts_covered_new"] == 3 and st["level"] == "ok"
    assert st["target_trx"] == 175.5 and st["suggested_topup_trx"] == 122
    assert g.evaluate({"trx_sun": 40_000_000, "energy_fee_sun": 100}, address=MASTER)["level"] == "warning"
    assert g.evaluate({"trx_sun": 18_000_000, "energy_fee_sun": 100}, address=MASTER)["level"] == "critical"
    u = g.evaluate(None, address=MASTER)
    assert u["level"] == "unknown" and u["trx"] is None
    # live energy price is used
    assert g.evaluate({"trx_sun": 1, "energy_fee_sun": 210}, address=MASTER)["cost_trx"]["new_receiver"] == 35.22


@pytest.mark.asyncio
async def test_gas_alerts_warning_critical_unknown_recovered(env):
    g = gm()
    keys = []

    async def send(text, alert_key=None, throttle_minutes=None):
        keys.append((alert_key, throttle_minutes, text))

    env.tron.resources = {"trx_sun": 40_000_000, "energy_fee_sun": 100, "energy_available": 0, "bandwidth_available": 0}
    await g.check_and_alert(send=send)
    env.tron.resources = {"trx_sun": 10_000_000, "energy_fee_sun": 100, "energy_available": 0, "bandwidth_available": 0}
    await g.check_and_alert(send=send)
    env.tron.resources = None
    await g.check_and_alert(send=send)
    env.tron.resources = {"trx_sun": 200_000_000, "energy_fee_sun": 100, "energy_available": 0, "bandwidth_available": 0}
    await g.check_and_alert(send=send)
    await g.check_and_alert(send=send)  # recovered only once
    assert [(k, t) for k, t, _ in keys] == [("gas_warning", 360), ("gas_critical", 60), ("gas_unknown", 60),
                                            ("gas_recovered", 1)]
    assert MASTER in keys[0][2] and "Рекомендовано поповнити" in keys[0][2] and "24 год" in keys[0][2]


@pytest.mark.asyncio
async def test_precheck_refusals_counted(env):
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    env.tron.gas_result = {"ok": False, "reason": "MASTER_INSUFFICIENT_TRX", "message": "low"}
    with pytest.raises(HTTPException):
        await env.seller_wallet(deal_id, run_worker=False)
    assert env.payouts.refused_prechecks_24h() == 1
    st = await gm().fetch_status(force=True)
    assert st["refused_prechecks_24h"] == 1


@pytest.mark.asyncio
async def test_snapshots_every_15_min_and_pruned(env):
    from app.models.monitoring import MasterWalletSnapshot as S

    g = gm()
    st = g.evaluate({"trx_sun": 50_000_000, "energy_fee_sun": 100, "energy_available": 5, "bandwidth_available": 600},
                    address=MASTER)
    t0 = datetime(2026, 10, 1, 12, 0)
    async with env.orm.session() as db:
        db.add(S(at=t0 - timedelta(days=91), trx_sun=1))
        await db.commit()
        assert await g.maybe_snapshot(db, st, t0) is True
        assert await g.maybe_snapshot(db, st, t0 + timedelta(minutes=5)) is False
        assert await g.maybe_snapshot(db, st, t0 + timedelta(minutes=15)) is True
        rows = (await db.execute(select(S).order_by(S.at))).scalars().all()
    assert [r.trx_sun for r in rows] == [50_000_000, 50_000_000]


@pytest.mark.asyncio
async def test_daily_summary_once_after_9_local(env):
    g = gm()
    sent = []

    async def send(text, alert_key=None, throttle_minutes=None):
        sent.append(text)

    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    from app.models.user import AdminAuditLog

    async with env.orm.session() as db:  # worker cycles may already have sent today's summary
        await db.execute(AdminAuditLog.__table__.delete().where(AdminAuditLog.action == g.SUMMARY_ACTION))
        await db.commit()
    now_local_day = g.to_local(datetime.utcnow()).date()
    before9 = datetime.combine(now_local_day, datetime.min.time()) + timedelta(hours=5)  # 08:00 local (UTC+3)
    assert await g.maybe_send_daily_summary(env.orm.session, before9, send=send) is False
    at9 = before9 + timedelta(hours=1, minutes=1)
    assert await g.maybe_send_daily_summary(env.orm.session, at9, send=send) is True
    assert await g.maybe_send_daily_summary(env.orm.session, at9 + timedelta(hours=2), send=send) is False
    assert len(sent) == 1 and "Звіт за" in sent[0]
    from app.services.alerts import is_valid_telegram_html

    assert is_valid_telegram_html(sent[0])
    async with env.orm.session() as db:
        s = await g.build_summary(db, now_local_day)
    assert s["outgoing"]["release"]["confirmed"] == 1 and s["deals"]["completed"] == 1


def test_local_day_bounds_and_dst():
    g = gm()
    assert g.local_day_bounds_utc(date(2026, 10, 12)) == (datetime(2026, 10, 11, 21), datetime(2026, 10, 12, 21))
    assert g.local_day_bounds_utc(date(2026, 12, 1)) == (datetime(2026, 11, 30, 22), datetime(2026, 12, 1, 22))
    assert g._eu_dst_bounds_utc(2026) == (datetime(2026, 3, 29, 1), datetime(2026, 10, 25, 1))


def test_money_control_admin_only_and_no_resend():
    src = (BACKEND / "app/routers/admin_money.py").read_text()
    import re

    for fn in re.findall(r"async def (\w+)\(", src):
        if fn.startswith("_"):
            continue
        body = src[src.index(f"async def {fn}("):]
        body = body[: body.index("db: AsyncSession")]
        assert "get_superadmin_user" in body, fn
    assert "broadcast" not in src.replace('"broadcast"', "").replace("broadcast_at", "").replace("broadcast tx", "").replace("Broadcast", "")


def test_gas_and_summary_run_inside_worker_lock():
    src = (BACKEND / "app/tasks/payout_worker.py").read_text()
    run_once = src[src.index("async def run_once"):src.index("async def _gas_cycle")]
    assert "self.gas_cycle()" in run_once
    assert "maybe_snapshot" in src and "maybe_send_daily_summary" in src
