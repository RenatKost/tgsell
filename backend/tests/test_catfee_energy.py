"""Task 18: CatFee energy rental before escrow payouts (all network mocked)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import logging

import httpx
import pytest

from tests.test_gas_topup_retry import Chain, esc  # noqa: F401
from tests.test_unified_payouts import SELLER_W, env  # noqa: F401

SUN = 1_000_000
KEY, SECRET = "test-key-AAAA", "test-secret-BBBB"


@pytest.fixture
def cf(monkeypatch):
    catfee = importlib.import_module("app.services.catfee")
    monkeypatch.setattr(catfee.settings, "catfee_api_key", KEY)
    monkeypatch.setattr(catfee.settings, "catfee_api_secret", SECRET)
    monkeypatch.setattr(catfee.settings, "catfee_base_url", "")
    return catfee


# ── client ──

def test_signature_matches_docs_algorithm(cf):
    ts, path = "2023-08-26T12:34:56.789Z", "/v1/order?quantity=65000&receiver=TRON_ADDRESS&duration=1h"
    want = base64.b64encode(hmac.new(SECRET.encode(), (ts + "POST" + path).encode(), hashlib.sha256).digest()).decode()
    assert cf.sign(SECRET, ts, "post", path) == want


def test_enabled_and_base_url(cf, monkeypatch):
    assert cf.enabled()
    monkeypatch.setattr(cf.settings, "tron_network", "mainnet")
    assert cf.base_url() == "https://api.catfee.io"
    monkeypatch.setattr(cf.settings, "tron_network", "nile")
    assert cf.base_url() == "https://nile.catfee.io"
    monkeypatch.setattr(cf.settings, "catfee_api_secret", "")
    assert not cf.enabled()
    with pytest.raises(cf.CatFeeError):
        cf.get_balance_sun()


def _mock_http(monkeypatch, cf, handler):
    seen = []

    def h(req):
        seen.append(req)
        return handler(req)
    transport = httpx.MockTransport(h)
    real = httpx.Client
    monkeypatch.setattr(cf.httpx, "Client", lambda **kw: real(transport=transport))
    return seen


def test_create_order_signed_request_and_idempotency_key(cf, monkeypatch, caplog):
    seen = _mock_http(monkeypatch, cf, lambda r: httpx.Response(200, json={"code": 0, "data": {
        "id": "ord1", "status": "DELEGATE_SUCCESS", "confirm_status": "UNCONFIRMED", "quantity": 143000,
        "pay_amount_sun": 2_500_000}}))
    caplog.set_level(logging.DEBUG)
    o = cf.create_order("TReceiver", 142_100, "tgsell-tx7")
    assert o["id"] == "ord1" and cf.order_cost_sun(o) == 2_500_000
    (req,) = seen
    assert req.method == "POST" and req.url.path == "/v1/order"
    q = dict(req.url.params)
    assert q == {"quantity": "142100", "receiver": "TReceiver", "duration": "1h",
                 "client_order_id": "tgsell-tx7", "activate": "false"}
    ts = req.headers["CF-ACCESS-TIMESTAMP"]
    assert req.headers["CF-ACCESS-KEY"] == KEY
    assert req.headers["CF-ACCESS-SIGN"] == cf.sign(SECRET, ts, "POST", req.url.raw_path.decode())
    assert KEY not in caplog.text and SECRET not in caplog.text


def test_min_quantity_and_business_errors(cf, monkeypatch):
    seen = _mock_http(monkeypatch, cf, lambda r: httpx.Response(200, json={"code": 201, "msg": "Insufficient balance"}))
    with pytest.raises(cf.CatFeeError) as ei:
        cf.create_order("TR", 10, "k")
    assert ei.value.code == 201 and dict(seen[0].url.params)["quantity"] == "65000"
    _mock_http(monkeypatch, cf, lambda r: httpx.Response(200, json={"code": 0, "data": {
        "id": "x", "status": "INSUFFICIENT_BALANCE"}}))
    with pytest.raises(cf.CatFeeError):
        cf.create_order("TR", 65000, "k")
    _mock_http(monkeypatch, cf, lambda r: httpx.Response(502, text="<html>bad gateway"))
    with pytest.raises(cf.CatFeeError):
        cf.get_balance_sun()

    def boom(r):
        raise httpx.ConnectTimeout("t")
    _mock_http(monkeypatch, cf, boom)
    with pytest.raises(cf.CatFeeError):
        cf.get_balance_sun()


def test_balance(cf, monkeypatch):
    _mock_http(monkeypatch, cf, lambda r: httpx.Response(200, json={"code": 0, "data": {"balance": 12_340_000}}))
    assert cf.get_balance_sun() == 12_340_000


# ── escrow layer ──

class Energy:
    """Mocks escrow energy + CatFee: energy appears after `arrive_after` polls once ordered."""

    def __init__(self, monkeypatch, escrow, cf, *, create=None, arrive_after=1, quantity=145_000):
        self.orders, self.gets, self.polls = [], [], 0
        self.ordered = False
        self.arrive_after, self.quantity = arrive_after, quantity
        self.create = create

        def est(f, t, a, c):
            avail = self.available()
            burn = max(0, int(131_000 * 1.2) - avail)
            req = int(burn * 100 + 1.2 * SUN)
            return {"energy": 131_000, "energy_available": avail, "energy_fee_sun": 100,
                    "required_sun": req, "fee_limit_sun": max(30 * SUN, req)}
        monkeypatch.setattr(escrow, "estimate_usdt_transfer_cost_sun", est)
        monkeypatch.setattr(escrow, "get_available_energy", lambda c, a: self.poll())
        monkeypatch.setattr(escrow, "ENERGY_WAIT_BACKOFF", (0.01,))
        monkeypatch.setattr(escrow, "GAS_CONFIRM_TIMEOUT_SEC", 0.2)
        monkeypatch.setattr(escrow, "GAS_RECHECK_TIMEOUT_SEC", 0.2)
        monkeypatch.setattr(escrow, "ENERGY_WAIT_TIMEOUT_SEC", 0.3)
        self.expired_ms = 0

        def create_order(receiver, quantity, key):
            self.orders.append((receiver, quantity, key))
            if self.create:
                return self.create()
            self.ordered = True
            return {"id": "ord1", "status": "DELEGATE_SUCCESS", "pay_amount_sun": 2_400_000}
        monkeypatch.setattr(cf, "create_order", create_order)

        def get_order(oid):
            self.gets.append(oid)
            return {"id": oid, "status": "DELEGATE_SUCCESS", "confirm_status": "DELEGATION_CONFIRMED",
                    "pay_amount_sun": 2_400_000, "expired_timestamp": self.expired_ms}
        monkeypatch.setattr(cf, "get_order", get_order)

    def available(self):
        return self.quantity if self.ordered and self.polls >= self.arrive_after else 0

    def poll(self):
        if self.ordered:
            self.polls += 1
        return self.available()


def test_disabled_keeps_burn_scheme(esc, cf, monkeypatch):
    monkeypatch.setattr(cf.settings, "catfee_api_key", "")
    e = Energy(monkeypatch, esc.m, cf)
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [0, 0, 18 * SUN]
    out = esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, energy_key="tgsell-tx1")
    assert e.orders == [] and out["energy"]["source"] == "burn"
    assert c.transfers == [(esc.master, esc.addr, int(157_200 * 100 + 1.2 * SUN))]


def test_rents_energy_then_only_bandwidth_topup(esc, cf, monkeypatch):
    e = Energy(monkeypatch, esc.m, cf)
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [0, 0, int(1.2 * SUN)]
    out = esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, energy_key="tgsell-tx5")
    assert e.orders == [(esc.addr, 145_000, "tgsell-tx5")]  # 131k × 1.1 → rounded up to 1000
    assert out["energy"] == {"source": "catfee", "order_id": "ord1", "rent_sun": 2_400_000, "reason": None}
    assert out["estimate"]["energy_source"] == "catfee"
    # only activation/bandwidth TRX from master, nothing to burn for energy
    assert c.transfers == [(esc.master, esc.addr, int(1.2 * SUN))]


def test_catfee_error_falls_back_to_burn(esc, cf, monkeypatch):
    def fail():
        raise cf.CatFeeError("code=201 msg=Insufficient balance", 201)
    e = Energy(monkeypatch, esc.m, cf, create=fail)
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [int(1.2 * SUN), int(1.2 * SUN), 20 * SUN]
    out = esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, energy_key="tgsell-tx5")
    assert len(e.orders) == 1 and out["energy"]["source"] == "burn" and "201" in out["energy"]["reason"]
    assert c.transfers == [(esc.master, esc.addr, int(157_200 * 100 + 1.2 * SUN) - int(1.2 * SUN))]


def test_energy_timeout_falls_back_to_burn_keeps_order_id(esc, cf, monkeypatch):
    monkeypatch.setattr(esc.m, "ENERGY_WAIT_TIMEOUT_SEC", 0.05)
    e = Energy(monkeypatch, esc.m, cf, arrive_after=10**9)
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [int(1.2 * SUN), int(1.2 * SUN), 20 * SUN]
    out = esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, energy_key="tgsell-tx5")
    assert out["energy"]["source"] == "burn" and out["energy"]["order_id"] == "ord1"
    assert len(e.orders) == 1 and len(c.transfers) == 1


def test_prior_order_is_never_reordered(esc, cf, monkeypatch):
    import time as _t
    e = Energy(monkeypatch, esc.m, cf)
    e.expired_ms = int((_t.time() - 10) * 1000)  # rental already expired
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [int(1.2 * SUN), int(1.2 * SUN), 20 * SUN]
    out = esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, energy_key="tgsell-tx5",
                                      prior_energy_order="ord0")
    assert e.orders == [] and e.gets[0] == "ord0"
    assert out["energy"]["source"] == "burn" and out["energy"]["order_id"] == "ord0"
    assert "no re-order" in out["energy"]["reason"]


def test_prior_live_order_is_reused(esc, cf, monkeypatch):
    import time as _t
    e = Energy(monkeypatch, esc.m, cf)
    e.expired_ms = int((_t.time() + 3000) * 1000)
    e.ordered = True  # energy of the earlier order is arriving
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [int(1.2 * SUN)]
    out = esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, energy_key="tgsell-tx5",
                                      prior_energy_order="ord0")
    assert e.orders == [] and out["energy"]["source"] == "catfee" and c.transfers == []


def test_refusal_carries_order_id(esc, cf, monkeypatch):
    Energy(monkeypatch, esc.m, cf)
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [int(1.2 * SUN), int(1.2 * SUN), 0]  # final check fails
    with pytest.raises(esc.m.EscrowTransferRefused) as ei:
        esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, energy_key="tgsell-tx5")
    assert ei.value.reason == "ESCROW_GAS_SHORT" and ei.value.energy_order_id == "ord1"


# ── payouts layer: persistence of order id / source / receipt fee ──

@pytest.mark.asyncio
async def test_payout_persists_order_and_costs(env, cf, monkeypatch):
    escrow = env.payouts.escrow_svc
    calls = []

    def prepare(enc, to, units, allow_master=False, prior_gas_tx=None, energy_key=None, prior_energy_order=None):
        calls.append((energy_key, prior_energy_order))
        if len(calls) == 1:
            raise escrow.EscrowTransferRefused("ESCROW_GAS_SHORT", "short", retryable=True, energy_order_id="ord9")
        return {"txid": "txidX", "txn": None, "gas_tx": None, "fee_limit_sun": 30 * SUN, "estimate": {},
                "energy": {"source": "catfee", "order_id": prior_energy_order, "rent_sun": 2_300_000}}
    monkeypatch.setattr(escrow, "prepare_usdt_transfer", prepare)
    env.tron.default_receipt = {"status": "SUCCESS", "reason": None, "info": {
        "id": "txidX", "fee": 345_000, "receipt": {"result": "SUCCESS", "energy_usage_total": 130_500,
                                                  "energy_fee": 0, "net_fee": 345_000}}}
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    (tx,) = await env.txs(deal_id)
    assert tx.energy_order_id == "ord9" and tx.receipt_status == "QUEUED"
    await env.work()
    assert calls == [(f"tgsell-tx{tx.id}", None), (f"tgsell-tx{tx.id}", "ord9")]
    (tx,) = await env.txs(deal_id)
    assert tx.energy_source == "catfee" and tx.energy_rent_sun == 2_300_000
    assert tx.fee_sun == 345_000 and tx.energy_used == 130_500 and tx.energy_fee_sun == 0
    assert (await env.get(deal_id)).status == env.S.completed


@pytest.mark.asyncio
async def test_payout_without_keys_does_not_pass_energy_args(env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "catfee_api_key", "")
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)  # FakeTron.prepare has no energy kwargs → would TypeError
    assert (await env.get(deal_id)).status == env.S.completed
    (tx,) = await env.txs(deal_id)
    assert tx.energy_source == "burn"


# ── admin balance / alert ──

@pytest.mark.asyncio
async def test_catfee_low_balance_alert(env, cf, monkeypatch):
    gm = importlib.import_module("app.services.gas_monitor")
    gm._catfee_cache.update(at=0.0, payload=None)
    gm._catfee_alert_state["low"] = False
    monkeypatch.setattr(cf, "get_balance_sun", lambda: 9 * SUN)  # 9 / 2.5 = 3 payouts < 5
    sent = []

    async def send(text, **kw):
        sent.append((text, kw))
    async with env.orm.session() as db:
        st = await gm.catfee_check_and_alert(db, send=send)
    assert st["level"] == "low" and st["payouts_covered"] == 3 and sent[0][1]["alert_key"] == "catfee_low"
    monkeypatch.setattr(cf, "get_balance_sun", lambda: 100 * SUN)
    async with env.orm.session() as db:
        st = await gm.catfee_check_and_alert(db, send=send)
    assert st["level"] == "ok" and sent[-1][1]["alert_key"] == "catfee_ok"
    assert gm.evaluate_catfee(None, 2.5, enabled=False)["level"] == "disabled"
