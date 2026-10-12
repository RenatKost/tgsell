"""Escrow USDT payout: gas estimation, receipt checking, master-destination guard.

TronGrid is fully faked (no network, nothing broadcast on-chain).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tronpy.keys import PrivateKey  # noqa: E402

MASTER_KEY = PrivateKey(bytes.fromhex("11" * 32))
MASTER = MASTER_KEY.public_key.to_base58check_address()
ESCROW_KEY = PrivateKey(bytes.fromhex("22" * 32))
ESCROW = ESCROW_KEY.public_key.to_base58check_address()
RECEIVER = PrivateKey(bytes.fromhex("33" * 32)).public_key.to_base58check_address()


class FakeTxn:
    def __init__(self, chain, kind, **kw):
        self.chain, self.kind, self.kw = chain, kind, kw

    def fee_limit(self, v):
        self.kw["fee_limit"] = v
        return self

    def with_owner(self, o):
        self.kw["owner"] = o
        return self

    def build(self):
        return self

    def sign(self, _k):
        return self

    def broadcast(self):
        txid = f"tx{len(self.chain.broadcasts) + 1}"
        self.chain.broadcasts.append((self.kind, txid, dict(self.kw)))
        if self.kind == "trx":
            self.chain.balances[self.kw["frm"]] -= self.kw["amount"]
            self.chain.balances[self.kw["to"]] = self.chain.balances.get(self.kw["to"], 0) + self.kw["amount"]
        return {"result": True, "txid": txid}


class FakeChain:
    def __init__(self):
        self.balances = {MASTER: 50_000_000, ESCROW: 0}
        self.broadcasts: list = []
        self.requests: list = []
        self.energy_fee = 100
        self.estimate = 130_285
        self.estimate_fails = False
        self.usdt_receipt = "SUCCESS"
        self.receipt_delay_polls = 0
        self.receiver_usdt = 0

    def make_request(self, method, params=None):
        self.requests.append(method)
        params = params or {}
        if method == "wallet/getchainparameters":
            if self.energy_fee is None:
                return {"chainParameter": [{"key": "getFoo", "value": 1}]}
            return {"chainParameter": [{"key": "getEnergyFee", "value": self.energy_fee}]}
        if method in ("wallet/estimateenergy", "wallet/triggerconstantcontract"):
            if self.estimate_fails:
                raise RuntimeError("estimateenergy disabled")
            key = "energy_required" if method.endswith("estimateenergy") else "energy_used"
            return {"result": {"result": True}, key: self.estimate}
        if method == "wallet/getaccount":
            return {"balance": self.balances.get(params["address"], 0)}
        if method == "wallet/gettransactioninfobyid":
            txid = params["value"]
            kind = next(k for k, t, _ in self.broadcasts if t == txid)
            if self.receipt_delay_polls > 0:
                self.receipt_delay_polls -= 1
                return {}
            if kind == "trx":
                return {"id": txid, "blockNumber": 1}
            if self.usdt_receipt == "SUCCESS":
                return {"id": txid, "receipt": {"result": "SUCCESS", "energy_usage_total": 130000}}
            return {"id": txid, "result": "FAILED", "receipt": {"result": self.usdt_receipt}}
        raise AssertionError(f"unexpected {method}")

    def client(self):
        chain = self
        trx = SimpleNamespace(transfer=lambda frm, to, amount: FakeTxn(chain, "trx", frm=frm, to=to, amount=amount))
        return SimpleNamespace(provider=SimpleNamespace(make_request=self.make_request), trx=trx)

    def contract(self):
        chain = self
        return SimpleNamespace(functions=SimpleNamespace(
            transfer=lambda to, amount: FakeTxn(chain, "usdt", to=to, amount=amount),
            balanceOf=lambda a: chain.receiver_usdt,
        ))


@pytest.fixture
def env(monkeypatch):
    escrow = importlib.import_module("app.services.escrow")
    chain = FakeChain()
    clock = {"t": 1000.0}

    def fake_sleep(sec):
        clock["t"] += sec

    monkeypatch.setattr(escrow.time, "sleep", fake_sleep)
    monkeypatch.setattr(escrow.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(escrow, "_get_tron_client", chain.client)
    monkeypatch.setattr(escrow, "_get_usdt_contract", chain.contract)
    monkeypatch.setattr(escrow, "decrypt_private_key", lambda _e: ESCROW_KEY.hex())
    monkeypatch.setattr(escrow.settings, "tron_master_wallet_address", MASTER)
    monkeypatch.setattr(escrow.settings, "tron_master_wallet_private_key", MASTER_KEY.hex())
    sweeps = []
    monkeypatch.setattr(escrow, "sweep_trx_to_master", lambda k: sweeps.append(k) or "sweep1")
    escrow.reset_tron_read_cache()
    yield SimpleNamespace(escrow=escrow, chain=chain, sweeps=sweeps)
    escrow.reset_tron_read_cache()


# ── estimation ──

def test_estimate_uses_estimateenergy_and_chain_fee(env):
    est = env.escrow.estimate_usdt_transfer_cost_sun(ESCROW, RECEIVER, 4_000_000, env.chain.client())
    assert est["energy"] == 130_285 and est["energy_fee_sun"] == 100
    assert est["required_sun"] == int((130_285 * 100 + 1_000_000) * 1.2)  # ≈16.83 TRX
    assert est["fee_limit_sun"] == max(30_000_000, est["required_sun"])


def test_estimate_fallback_new_vs_existing_holder(env):
    env.chain.estimate_fails = True
    env.chain.energy_fee = None  # param missing → 100 sun
    c = env.chain.client()
    env.chain.receiver_usdt = 0
    assert env.escrow.estimate_usdt_transfer_energy(ESCROW, RECEIVER, 1, c) == 135_000
    env.chain.receiver_usdt = 5_000_000
    assert env.escrow.estimate_usdt_transfer_energy(ESCROW, RECEIVER, 1, c) == 70_000
    assert env.escrow.get_energy_fee_sun(c) == 100


def test_estimate_fallback_when_receiver_balance_unknown_is_conservative(env, monkeypatch):
    env.chain.estimate_fails = True
    monkeypatch.setattr(env.escrow, "get_usdt_balance", lambda a: None)
    assert env.escrow.estimate_usdt_transfer_energy(ESCROW, RECEIVER, 1, env.chain.client()) == 135_000


def test_fee_limit_grows_above_30_trx_when_needed(env):
    env.chain.energy_fee = 420
    est = env.escrow.estimate_usdt_transfer_cost_sun(ESCROW, RECEIVER, 1, env.chain.client())
    assert est["fee_limit_sun"] == est["required_sun"] > 30_000_000


def test_transfer_parameter_encoding():
    escrow = importlib.import_module("app.services.escrow")
    p = escrow._transfer_parameter(RECEIVER, 4_000_000)
    assert len(p) == 128 and p.endswith(format(4_000_000, "x").rjust(64, "0"))


# ── payout flow ──

def test_payout_tops_up_only_difference_and_succeeds(env):
    env.chain.balances[ESCROW] = 5_000_000
    r = env.escrow.escrow_usdt_payout("enc", RECEIVER, 4.0)
    assert r["ok"] is True and r["tx_hash"] and r["error"] is None
    gas = [b for b in env.chain.broadcasts if b[0] == "trx"]
    assert len(gas) == 1
    assert gas[0][2]["amount"] == r["estimate"]["required_sun"] - 5_000_000
    usdt = [b for b in env.chain.broadcasts if b[0] == "usdt"][0]
    assert usdt[2]["fee_limit"] >= 30_000_000 and usdt[2]["amount"] == 4_000_000
    assert env.sweeps == ["enc"]


def test_payout_no_topup_when_escrow_has_enough(env):
    env.chain.balances[ESCROW] = 40_000_000
    r = env.escrow.escrow_usdt_payout("enc", RECEIVER, 4.0)
    assert r["ok"] is True and r["gas_tx"] is None
    assert [b[0] for b in env.chain.broadcasts] == ["usdt"]


def test_receipt_out_of_energy_is_failure_and_sweeps(env):
    env.chain.usdt_receipt = "OUT_OF_ENERGY"
    r = env.escrow.escrow_usdt_payout("enc", RECEIVER, 4.0)
    assert r["ok"] is False and r["reason"] == "OUT_OF_ENERGY"
    assert "OUT_OF_ENERGY" in r["error"] and r["tx_hash"]
    assert env.sweeps == ["enc"]


def test_receipt_polled_until_available(env):
    env.chain.balances[ESCROW] = 40_000_000
    env.chain.receipt_delay_polls = 3
    r = env.escrow.escrow_usdt_payout("enc", RECEIVER, 4.0)
    assert r["ok"] is True
    assert env.chain.requests.count("wallet/gettransactioninfobyid") == 4


def test_receipt_timeout_is_not_success(env):
    env.chain.balances[ESCROW] = 40_000_000
    env.chain.receipt_delay_polls = 10_000
    r = env.escrow.escrow_usdt_payout("enc", RECEIVER, 4.0)
    assert r["ok"] is False and "PENDING" in r["error"]


def test_destination_master_rejected_nothing_sent(env):
    r = env.escrow.escrow_usdt_payout("enc", MASTER, 4.0)
    assert r["ok"] is False and "master" in r["error"]
    assert env.chain.broadcasts == [] and env.chain.requests == []


def test_master_insufficient_trx_fails_early_no_partial_gas(env):
    env.chain.balances[MASTER] = 8_640_000  # ~8.64 TRX
    r = env.escrow.escrow_usdt_payout("enc", RECEIVER, 4.0)
    assert r["ok"] is False and r["reason"] == "MASTER_INSUFFICIENT_TRX"
    assert "Нічого не відправлено" in r["error"]
    assert env.chain.broadcasts == []


# ── admin endpoints ──

@pytest.mark.asyncio
async def test_admin_escrow_transfer_returns_error_on_failed_receipt(pg_orm, env):
    admin_router = importlib.import_module("app.routers.admin")
    env.chain.usdt_receipt = "OUT_OF_ENERGY"
    deal = SimpleNamespace(id=1, escrow_private_key_encrypted="enc", escrow_wallet_address=ESCROW)
    tx, err = await admin_router._escrow_transfer_usdt(deal, RECEIVER, 4.0)
    assert tx is None and "OUT_OF_ENERGY" in err


@pytest.mark.asyncio
async def test_admin_escrow_transfer_rejects_master(pg_orm, env):
    admin_router = importlib.import_module("app.routers.admin")
    deal = SimpleNamespace(id=1, escrow_private_key_encrypted="enc", escrow_wallet_address=ESCROW)
    tx, err = await admin_router._escrow_transfer_usdt(deal, MASTER, 4.0)
    assert tx is None and "master" in err and env.chain.broadcasts == []
