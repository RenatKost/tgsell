"""P0: gas top-up confirmation wait + retry without sweep / double top-up (deal #29 incident)."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from tests.test_unified_payouts import SELLER_W, env  # noqa: F401

SUN = 1_000_000


# ── payouts layer (worker) ──

@pytest.mark.asyncio
async def test_unconfirmed_gas_defers_without_sweep_then_retries_reusing_gas(env):
    escrow = env.payouts.escrow_svc
    env.tron.prepare_raises = [escrow.EscrowTransferRefused(
        "GAS_TOPUP_UNCONFIRMED", "not confirmed (tx g1)", retryable=True, gas_tx="g1")]
    deal_id, escrow_addr = await env.make_deal(env.S.awaiting_payout)
    resp = await env.seller_wallet(deal_id)
    assert resp.status == "payout_in_progress"
    (tx,) = await env.txs(deal_id)
    assert tx.status == env.TS.pending and tx.receipt_status == "QUEUED" and tx.tx_hash is None
    assert tx.gas_tx_hash == "g1" and tx.gas_attempts == 1
    assert env.tron.sweeps == [] and env.tron.broadcasts == []
    # duplicate payout request is still blocked while the job is queued
    await env.work()  # retry: prepare gets prior gas tx → no new top-up needed
    assert env.tron.prior_gas_txs == [None, "g1"]
    d = await env.get(deal_id)
    assert d.status == env.S.completed and d.payout_tx_hash == "txid1"
    assert len(env.tron.broadcasts) == 1 and env.tron.sweeps == [f"enc-{escrow_addr}"]


@pytest.mark.asyncio
async def test_unknown_trx_balance_defers(env):
    escrow = env.payouts.escrow_svc
    env.tron.prepare_raises = [escrow.EscrowTransferRefused("ESCROW_TRX_UNKNOWN", "unknown", retryable=True)] * 2
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    await env.work()
    (tx,) = await env.txs(deal_id)
    assert tx.receipt_status == "QUEUED" and tx.gas_attempts == 2 and env.tron.sweeps == []
    await env.work()
    assert (await env.get(deal_id)).status == env.S.completed


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts_without_sweep(env, monkeypatch):
    escrow = env.payouts.escrow_svc
    monkeypatch.setattr(env.payouts, "MAX_GAS_ATTEMPTS", 2)
    env.tron.prepare_raises = escrow.EscrowTransferRefused("GAS_TOPUP_UNCONFIRMED", "x", retryable=True, gas_tx="g1")
    deal_id, _ = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    await env.work()
    (tx,) = await env.txs(deal_id)
    assert tx.status == env.TS.failed and env.tron.sweeps == []
    assert (await env.get(deal_id)).status == env.S.awaiting_payout


@pytest.mark.asyncio
async def test_non_retryable_prepare_error_still_sweeps(env):
    escrow = env.payouts.escrow_svc
    env.tron.prepare_raises = escrow.EscrowTransferRefused("MASTER_INSUFFICIENT_TRX", "no trx")
    deal_id, addr = await env.make_deal(env.S.awaiting_payout)
    await env.seller_wallet(deal_id)
    (tx,) = await env.txs(deal_id)
    assert tx.status == env.TS.failed and env.tron.sweeps == [f"enc-{addr}"]


# ── escrow layer (prepare_usdt_transfer / wait_gas_topup) ──

class Chain:
    def __init__(self, balances, receipts=None):
        self.bal = balances          # address -> list of sun values (pops; last repeats) or Exception
        self.receipts = receipts or {}
        self.transfers = []

    def balance(self, client, address):
        v = self.bal[address]
        if isinstance(v, list):
            v = v.pop(0) if len(v) > 1 else v[0]
        if isinstance(v, Exception):
            raise v
        return v

    def receipt(self, client, txid, timeout=0):
        script = self.receipts.get(txid) or [{"status": "PENDING", "reason": "nf"}]
        return script.pop(0) if len(script) > 1 else script[0]


@pytest.fixture
def esc(monkeypatch):
    escrow = importlib.import_module("app.services.escrow")
    from tronpy.keys import PrivateKey

    master_pk = PrivateKey(bytes.fromhex("22" * 32))
    master = master_pk.public_key.to_base58check_address()
    escrow_pk = PrivateKey(bytes.fromhex("11" * 32))
    escrow_addr = escrow_pk.public_key.to_base58check_address()
    monkeypatch.setattr(escrow.settings, "tron_master_wallet_address", master)
    monkeypatch.setattr(escrow.settings, "tron_master_wallet_private_key", "22" * 32)
    monkeypatch.setattr(escrow, "decrypt_private_key", lambda enc: "11" * 32)
    monkeypatch.setattr(escrow, "GAS_WAIT_BACKOFF", (0.01,))
    monkeypatch.setattr(escrow, "estimate_usdt_transfer_cost_sun",
                        lambda f, t, a, c: {"required_sun": 20 * SUN, "fee_limit_sun": 30 * SUN})

    class Txn:
        txid = "usdt-tx"

        def sign(self, k):
            return self

    class Contract:
        class functions:
            @staticmethod
            def transfer(to, amt):
                return SimpleNamespace(with_owner=lambda a: SimpleNamespace(
                    fee_limit=lambda f: SimpleNamespace(build=lambda: Txn())))

    monkeypatch.setattr(escrow, "_get_usdt_contract", lambda: Contract)

    def setup(chain: Chain):
        def transfer(frm, to, amount):
            chain.transfers.append((frm, to, amount))
            n = len(chain.transfers)
            return SimpleNamespace(build=lambda: SimpleNamespace(sign=lambda k: SimpleNamespace(
                broadcast=lambda: {"txid": f"g{n}", "result": True})))

        client = SimpleNamespace(trx=SimpleNamespace(transfer=transfer))
        monkeypatch.setattr(escrow, "_get_tron_client", lambda: client)
        monkeypatch.setattr(escrow, "_account_balance_sun", chain.balance)
        monkeypatch.setattr(escrow, "wait_for_receipt", chain.receipt)
        return chain

    return SimpleNamespace(m=escrow, master=master, addr=escrow_addr, setup=setup)


def test_trx_transfer_receipt_with_empty_contract_result_is_success(esc, monkeypatch):
    monkeypatch.undo()
    escrow = importlib.import_module("app.services.escrow")
    monkeypatch.setattr(escrow, "_api", lambda c, path, body: {"id": "x", "blockNumber": 1, "contractResult": [""],
                                                              "receipt": {"net_usage": 268}})
    assert escrow.wait_for_receipt(None, "x", timeout=0)["status"] == "SUCCESS"
    monkeypatch.setattr(escrow, "_api", lambda c, path, body: {"id": "x", "result": "FAILED", "contractResult": [""],
                                                              "receipt": {}})
    assert escrow.wait_for_receipt(None, "x", timeout=0)["status"] == "FAILED"


def test_slow_gas_confirmation_succeeds(esc):
    # escrow 5 TRX → top-up 15; balance shows up only on the 4th poll
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [5 * SUN, 5 * SUN, 5 * SUN, 5 * SUN, 20 * SUN]
    out = esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000)
    assert out["txid"] == "usdt-tx" and out["gas_tx"] == "g1"
    assert c.transfers == [(esc.master, esc.addr, 15 * SUN)]


def test_receipt_success_counts_even_if_balance_lags(esc):
    c = esc.setup(Chain({esc.master: [500 * SUN]}, {"g1": [{"status": "PENDING"}, {"status": "SUCCESS"}]}))
    c.bal[esc.addr] = [5 * SUN]
    # balance known but short + receipt success → keep waiting until timeout (balance authoritative)
    assert esc.m.wait_gas_topup(None, "g1", esc.addr, 20 * SUN, timeout=0.05)["status"] == "PENDING"
    # balance unreadable + receipt success → confirmed
    c.bal[esc.addr] = [RuntimeError("node down")]
    c.receipts["g2"] = [{"status": "SUCCESS"}]
    assert esc.m.wait_gas_topup(None, "g2", esc.addr, 20 * SUN, timeout=1)["status"] == "SUCCESS"


def test_timeout_is_retryable_and_retry_reuses_existing_trx(esc, monkeypatch):
    monkeypatch.setattr(esc.m, "GAS_CONFIRM_TIMEOUT_SEC", 0.05)
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [5 * SUN]
    with pytest.raises(esc.m.EscrowTransferRefused) as ei:
        esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000)
    assert ei.value.retryable and ei.value.gas_tx == "g1" and ei.value.reason == "GAS_TOPUP_UNCONFIRMED"
    assert len(c.transfers) == 1
    # retry later: TRX arrived → no new top-up
    c.bal[esc.addr] = [20 * SUN]
    out = esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, prior_gas_tx="g1")
    assert out["gas_tx"] is None and len(c.transfers) == 1


def test_retry_with_prior_pending_gas_never_tops_up_again(esc, monkeypatch):
    monkeypatch.setattr(esc.m, "GAS_RECHECK_TIMEOUT_SEC", 0.05)
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [5 * SUN]
    with pytest.raises(esc.m.EscrowTransferRefused) as ei:
        esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, prior_gas_tx="g0")
    assert ei.value.retryable and c.transfers == []
    # prior top-up definitively FAILED → a new top-up of the difference is allowed
    c.receipts["g0"] = [{"status": "FAILED", "reason": "x"}]
    monkeypatch.setattr(esc.m, "GAS_CONFIRM_TIMEOUT_SEC", 0.05)
    with pytest.raises(esc.m.EscrowTransferRefused):
        esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000, prior_gas_tx="g0")
    assert c.transfers == [(esc.master, esc.addr, 15 * SUN)]


def test_unknown_escrow_balance_no_topup(esc):
    c = esc.setup(Chain({esc.master: [500 * SUN]}))
    c.bal[esc.addr] = [RuntimeError("timeout")]
    with pytest.raises(esc.m.EscrowTransferRefused) as ei:
        esc.m.prepare_usdt_transfer("enc", SELLER_W, 1_000_000)
    assert ei.value.retryable and ei.value.reason == "ESCROW_TRX_UNKNOWN" and c.transfers == []
