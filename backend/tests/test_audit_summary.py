"""GET /api/audit/summary: key check, rate limit, no PII, aggregates, log redaction."""
from __future__ import annotations

import hashlib
import importlib
import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.utils.timeutil import utcnow_naive

TEST_KEY = "test-audit-key-not-a-real-secret-0123456789"
PII = ("SecretUsername_xyz", "Taras Shevchenko-PII", "pii-mail@example.com", "SuperChannelTitlePII")


# ── redaction (no DB) ──────────────────────────────────────────────────

def test_redact_sample_masks_secrets():
    from app.utils.error_buffer import redact_sample

    bot = "123456789:" + "A" * 35
    hexs = "ab" * 32
    b64 = "Zx9_kQ2-mP7vR4tY8uW1eS5dF3gH6jK0lA"
    raw = (f"call https://api.telegram.org/bot{bot}/getMe failed; hash={hexs} sess {b64} "
           "url?key=hunter2&x=1 token=abc123 secret: s3cr3t password=pw! "
           "user @some_handle mail a.b@c.io link https://t.me/+InviteCodeXyz "
           "addr TXoRpYu5FDgZvrqNQb239bLjcc5oHzavCG deal_payout_worker_failed_badly")
    out = redact_sample(raw)
    for leaked in (bot, hexs, b64, "hunter2", "abc123", "s3cr3t", "pw!", "some_handle",
                   "a.b@c.io", "InviteCodeXyz", "TXoRpYu5FDgZvrqNQb239bLjcc5oHzavCG"):
        assert leaked not in out, leaked
    assert "key=***" in out and "token=***" in out and "password=***" in out
    # long snake_case identifiers stay readable
    assert "deal_payout_worker_failed_badly" in out


def test_error_buffer_groups_by_template():
    from app.utils.error_buffer import ErrorRingBuffer

    buf = ErrorRingBuffer(maxlen=5)
    lg = logging.getLogger("tests.audit.buffer")
    lg.propagate = False
    lg.addHandler(buf)
    lg.setLevel(logging.DEBUG)
    try:
        lg.info("ignored info %s", 1)
        for i in range(3):
            lg.warning("payout failed deal=%s token=%s", i, "zzz")
        lg.error("boom %s", "x")
        for i in range(3):
            lg.warning("payout failed deal=%s token=%s", 10 + i, "zzz")
    finally:
        lg.removeHandler(buf)
    s = buf.summary()
    assert s["buffered"] == 5 and s["buffer_size"] == 5  # ring buffer keeps the last 5
    groups = {g["template"]: g for g in s["groups"]}
    g = groups["payout failed deal=%s token=***"]  # template is redacted too
    assert g["count"] == 4 and g["level"] == "WARNING"
    assert g["sample"] == "payout failed deal=12 token=***"
    assert g["first_seen"] <= g["last_seen"]
    assert groups["boom %s"]["level"] == "ERROR"
    assert "zzz" not in str(s)


def test_sliding_window_limiter():
    from app.routers.audit import SlidingWindowLimiter

    lim = SlidingWindowLimiter(3, 60)
    assert all(lim.allow(now=t) for t in (0, 1, 2))
    assert not lim.allow(now=30)
    assert lim.allow(now=60.5)  # first hit left the window


# ── HTTP (real Postgres) ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def audit(pg_orm, monkeypatch):
    from fastapi import FastAPI
    from app.config import settings

    monkeypatch.setattr(settings, "audit_key_sha256", hashlib.sha256(TEST_KEY.encode()).hexdigest())
    audit_mod = importlib.import_module("app.routers.audit")
    audit_mod.limiter.reset()
    app = FastAPI()
    app.include_router(audit_mod.router, prefix="/api")
    app.dependency_overrides[audit_mod.get_db] = pg_orm.get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield SimpleNamespace(client=client, orm=pg_orm, mod=audit_mod)
    audit_mod.limiter.reset()


async def _get(a, key=TEST_KEY):
    headers = {"x-audit-key": key} if key is not None else {}
    return await a.client.get("/api/audit/summary", headers=headers)


@pytest.mark.asyncio
async def test_requires_key(audit):
    assert (await _get(audit, key=None)).status_code == 403
    assert (await _get(audit, key="wrong")).status_code == 403
    assert (await _get(audit, key="")).status_code == 403
    r = await _get(audit)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")


@pytest.mark.asyncio
async def test_rate_limit_429_after_30(audit):
    codes = [(await _get(audit)).status_code for _ in range(30)]
    assert codes == [200] * 30
    assert (await _get(audit)).status_code == 429
    assert (await _get(audit, key="wrong")).status_code == 429


@pytest.mark.asyncio
async def test_key_not_logged(audit, caplog):
    caplog.set_level(logging.INFO, logger="app.routers.audit")
    await _get(audit)
    await _get(audit, key="wrong-key-value-123")
    assert "[AUDIT] summary ok" in caplog.text and "[AUDIT] summary denied" in caplog.text
    assert TEST_KEY not in caplog.text and "wrong-key-value-123" not in caplog.text


async def _seed(orm):
    from app.models.bundle import ChannelBundle, BundleStatus
    from app.models.channel import Channel, ChannelClarification, ChannelStatus
    from app.models.deal import Deal, DealMessage, DealStatus
    from app.models.paid_service import PaidServiceOrder
    from app.models.price_offer import PriceOffer
    from app.models.user import User

    now = utcnow_naive()
    async with orm.session() as db:
        seller = User(first_name=PII[1], username=PII[0], email=PII[2], telegram_id=61001,
                      usdt_wallet="TSELLERWALLETPII000000000000000001")
        buyer = User(first_name="BuyerFirstNamePII", username="buyer_handle_pii", telegram_id=61002)
        db.add_all([seller, buyer])
        await db.flush()

        def ch(status, hours, link):
            return Channel(seller_id=seller.id, telegram_link=f"https://t.me/{link}", channel_name=PII[3],
                           category="Новини/ЗМІ", price=100, subscribers_count=10, status=status,
                           created_at=now - timedelta(hours=hours))
        c_old = ch(ChannelStatus.pending, 50, "piilinkold")
        c_new = ch(ChannelStatus.pending, 2, "piilinknew")
        c_clar = ch(ChannelStatus.needs_clarification, 100, "piilinkclar")
        c_ok = ch(ChannelStatus.approved, 10, "piilinkok")
        db.add_all([c_old, c_new, c_clar, c_ok])
        db.add(ChannelBundle(seller_id=seller.id, name="BundleNamePII", price=200,
                             status=BundleStatus.pending, created_at=now - timedelta(hours=5)))
        await db.flush()
        db.add(ChannelClarification(channel_id=c_clar.id, question="q?", asked_by_id=buyer.id,
                                    asked_at=now - timedelta(hours=30)))

        def deal(status, amount, *, created_h, paid_h=None, deadline_h=None):
            return Deal(channel_id=c_ok.id, buyer_id=buyer.id, seller_id=seller.id, status=status,
                        escrow_wallet_address="TESCROWADDRPII0000000000000000001",
                        escrow_private_key_encrypted="enc-private-key-pii", amount_usdt=amount,
                        created_at=now - timedelta(hours=created_h),
                        paid_at=(now - timedelta(hours=paid_h)) if paid_h is not None else None,
                        payment_deadline_at=(now + timedelta(hours=deadline_h)) if deadline_h is not None else None,
                        payout_tx_hash="f" * 64, seller_payout_address="TPAYOUTADDRPII00000000000000001")
        d_pp = deal(DealStatus.payment_pending, 10, created_h=5, deadline_h=-1)   # overdue
        d_cr = deal(DealStatus.created, 20, created_h=1, deadline_h=+5)
        d_paid = deal(DealStatus.paid, 100, created_h=40, paid_h=30)               # stuck
        d_tr = deal(DealStatus.channel_transferring, 50.5, created_h=3, paid_h=2)
        d_aw = deal(DealStatus.awaiting_payout, 25.25, created_h=60, paid_h=48)    # stuck
        d_disp = deal(DealStatus.disputed, 70, created_h=80, paid_h=72)
        d_done = deal(DealStatus.completed, 999, created_h=200, paid_h=190)
        d_canc = deal(DealStatus.cancelled, 5, created_h=300)
        db.add_all([d_pp, d_cr, d_paid, d_tr, d_aw, d_disp, d_done, d_canc])
        await db.flush()
        db.add(DealMessage(deal_id=d_disp.id, text="Відкрито спір", is_system=True, kind="system",
                           event="dispute_opened", created_at=now - timedelta(hours=12)))

        db.add_all([
            PriceOffer(channel_id=c_ok.id, buyer_id=buyer.id, seller_id=seller.id, amount_usdt=60,
                       status="pending", expires_at=now + timedelta(hours=40)),
            PriceOffer(channel_id=c_ok.id, buyer_id=buyer.id, seller_id=seller.id, amount_usdt=70,
                       status="declined", expires_at=now + timedelta(hours=40)),
        ])
        for st in ("awaiting_payment", "awaiting_payment", "active"):
            db.add(PaidServiceOrder(kind="top", channel_id=c_ok.id, seller_id=seller.id, price_usdt=5,
                                    status=st, escrow_wallet_address="TTOPADDRPII00000000000000000001",
                                    escrow_private_key_encrypted="enc",
                                    payment_deadline_at=now - timedelta(hours=1)))
        await db.commit()
        return SimpleNamespace(c_old=c_old.id, c_new=c_new.id, c_clar=c_clar.id, d_pp=d_pp.id,
                               d_cr=d_cr.id, d_paid=d_paid.id, d_aw=d_aw.id, d_disp=d_disp.id,
                               d_done=d_done.id)


@pytest.mark.asyncio
async def test_aggregates_and_no_pii(audit):
    from app.utils import error_buffer

    ids = await _seed(audit.orm)
    buf = error_buffer.install_error_buffer()
    logging.getLogger("tests.audit.http").error("lookup failed for @%s token=%s", PII[0], "tok-123")
    try:
        r = await _get(audit)
    finally:
        logging.getLogger().removeHandler(buf)
        error_buffer._handler = None
    assert r.status_code == 200
    body = r.json()
    raw = r.text
    for leaked in PII + ("BuyerFirstNamePII", "buyer_handle_pii", "BundleNamePII", "piilink", "t.me",
                         "TSELLERWALLET", "TESCROWADDR", "TPAYOUTADDR", "TTOPADDR", "enc-private-key",
                         "f" * 64, "tok-123", TEST_KEY):
        assert leaked not in raw, leaked

    assert body["generated_at"].endswith("+00:00")
    m = body["moderation"]
    assert m["channels"] == {"pending": 2, "needs_clarification": 1}
    assert m["bundles_pending"] == 1 and m["total"] == 4
    assert m["oldest"][0]["id"] == ids.c_old and m["oldest"][0]["kind"] == "channel"
    assert m["oldest_waiting_hours"] == pytest.approx(50, abs=0.2)
    clar = next(it for it in m["oldest"] if it["id"] == ids.c_clar)
    assert clar["waiting_hours"] == pytest.approx(30, abs=0.2)  # since the question, not creation

    d = body["deals"]
    assert d["by_status"]["payment_pending"] == 1 and d["by_status"]["completed"] == 1
    assert d["by_status"]["cancelled"] == 1 and d["by_status"]["payout_in_progress"] == 0
    assert d["active_total"] == 6 and d["payment_deadline_overdue"] == 1
    active = {x["id"]: x for x in d["active"]}
    assert ids.d_done not in active
    assert active[ids.d_pp]["payment_deadline_overdue"] is True
    assert active[ids.d_cr]["payment_deadline_overdue"] is False
    assert active[ids.d_paid]["hours_since_last_change"] == pytest.approx(30, abs=0.2)
    assert d["open_disputes"] == [{"deal_id": ids.d_disp, "age_hours": pytest.approx(12, abs=0.2),
                                   "age_source": "dispute_opened"}]

    e = body["escrow"]
    assert e["deals"] == 3
    assert e["amount_usdt"] == pytest.approx(175.75)
    assert e["by_status"]["channel_transferring"] == {"count": 1, "amount_usdt": 50.5}
    assert e["stuck_over_24h"] == 2
    assert e["disputed_deals"] == 1 and e["disputed_amount_usdt"] == 70

    assert body["price_offers"]["pending"] == 1 and body["price_offers"]["accepted"] == 0
    assert body["paid_services"]["unpaid_top_invoices"] == 2
    assert body["paid_services"]["unpaid_top_past_deadline"] == 2

    assert body["seller_notifications"] == {"pending": 0, "sent_24h": 0, "failed_24h": 0,
                                            "oldest_pending_hours": None}

    errs = body["errors"]
    assert errs["installed"] is True
    g = next(g for g in errs["groups"] if g["logger"] == "tests.audit.http")
    assert g["count"] == 1 and g["level"] == "ERROR"
    assert g["sample"] == "lookup failed for @<handle> token=***"

    rt = body["runtime"]
    assert "status" in rt["telethon"] and rt["process_started_at"]
