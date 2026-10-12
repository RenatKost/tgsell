"""USDT TRC-20 Escrow Service — wallet generation, balance checking, payouts."""
import logging
import random
import threading
import time

from tronpy import Tron
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider

from app.config import settings
from app.utils.crypto import decrypt_private_key, encrypt_private_key

logger = logging.getLogger(__name__)

# USDT TRC-20 contract addresses
USDT_CONTRACTS = {
    "mainnet": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "nile": "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf",  # Nile testnet USDT
}


def _get_tron_client() -> Tron:
    """Get a Tron client for the configured network."""
    logger.info(f"[TRON] Connecting to network={settings.tron_network}")
    if settings.tron_network == "mainnet":
        if settings.tron_api_key:
            provider = HTTPProvider(
                endpoint_uri="https://api.trongrid.io",
                api_key=settings.tron_api_key,
            )
            return Tron(provider=provider)
        return Tron()
    else:
        return Tron(network=settings.tron_network)


# ── TronGrid throttling for read calls (balance checks) ─────────────────
#
# TronGrid answers bursts with HTTP 429. All balance reads go through one lock with
# a minimum interval between requests, retry 429/5xx/network errors with exponential
# backoff, and reuse the client + USDT contract object (tronpy's get_contract() is
# an extra HTTP request — it caused most of the 429s on /admin/escrow/balances).

class BalanceUnavailable(Exception):
    """USDT balance could not be determined (TronGrid error / rate limit).

    Callers must treat this as UNKNOWN — never as 0 (no cancellations on unknown).
    """


TRON_MIN_INTERVAL_SEC = 0.35
TRON_MAX_RETRIES = 3
TRON_BACKOFF_BASE_SEC = 1.0

_tron_lock = threading.Lock()
_last_tron_request_at = 0.0
_read_client: Tron | None = None
_read_client_key: tuple | None = None
_usdt_contract = None
_usdt_contract_key: tuple | None = None


def _usdt_contract_address() -> str:
    return settings.usdt_contract_address or USDT_CONTRACTS.get(
        settings.tron_network, USDT_CONTRACTS["nile"]
    )


def _is_retryable(exc: Exception) -> bool:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return status == 429 or status >= 500
    try:
        import requests

        return isinstance(exc, (requests.ConnectionError, requests.Timeout))
    except Exception:  # pragma: no cover
        return False


def _throttled(fn, *, what: str):
    """Run one TronGrid request: serialized, min interval, retry 429/5xx with backoff."""
    global _last_tron_request_at
    attempt = 0
    while True:
        with _tron_lock:
            wait = TRON_MIN_INTERVAL_SEC - (time.monotonic() - _last_tron_request_at)
            if wait > 0:
                time.sleep(wait)
            try:
                return fn()
            except Exception as e:
                err = e
            finally:
                _last_tron_request_at = time.monotonic()
        if attempt >= TRON_MAX_RETRIES or not _is_retryable(err):
            raise err
        delay = TRON_BACKOFF_BASE_SEC * (2 ** attempt) + random.uniform(0, 0.25)
        logger.warning(f"[TRON] {what}: {err} — retry {attempt + 1}/{TRON_MAX_RETRIES} in {delay:.1f}s")
        attempt += 1
        time.sleep(delay)


def _get_usdt_contract():
    """Cached USDT contract (one getcontract request per process/config)."""
    global _read_client, _read_client_key, _usdt_contract, _usdt_contract_key
    client_key = (settings.tron_network, settings.tron_api_key)
    if _read_client is None or _read_client_key != client_key:
        _read_client = _get_tron_client()
        _read_client_key = client_key
        _usdt_contract = None
    contract_key = (client_key, _usdt_contract_address())
    if _usdt_contract is None or _usdt_contract_key != contract_key:
        client = _read_client
        _usdt_contract = _throttled(lambda: client.get_contract(_usdt_contract_address()), what="getcontract")
        _usdt_contract_key = contract_key
    return _usdt_contract


def reset_tron_read_cache() -> None:
    """Drop cached client/contract (tests, config change)."""
    global _read_client, _read_client_key, _usdt_contract, _usdt_contract_key, _last_tron_request_at
    with _tron_lock:
        _read_client = _read_client_key = _usdt_contract = _usdt_contract_key = None
        _last_tron_request_at = 0.0


def generate_escrow_wallet() -> tuple[str, str]:
    """Generate a new TRC-20 wallet for escrow.

    Returns:
        (wallet_address, encrypted_private_key)
    """
    priv_key = PrivateKey.random()
    address = priv_key.public_key.to_base58check_address()
    encrypted_key = encrypt_private_key(priv_key.hex())
    logger.info(f"[ESCROW] New wallet generated: {address}")
    return address, encrypted_key


def fetch_usdt_balance(wallet_address: str) -> float:
    """USDT TRC-20 balance (6 decimals). Raises BalanceUnavailable if unknown.

    Blocking (requests + throttle sleeps) — from async code use
    ``await asyncio.to_thread(fetch_usdt_balance, addr)``.
    """
    if not wallet_address:
        raise BalanceUnavailable("empty wallet address")
    try:
        contract = _get_usdt_contract()
        balance_raw = _throttled(
            lambda: contract.functions.balanceOf(wallet_address), what=f"balanceOf {wallet_address}"
        )
        balance = int(balance_raw) / 1_000_000  # USDT has 6 decimals
    except BalanceUnavailable:
        raise
    except Exception as e:
        logger.error(f"[ESCROW] USDT balance UNKNOWN for {wallet_address}: {e}")
        raise BalanceUnavailable(str(e)) from e
    logger.info(f"[ESCROW] Balance check: {wallet_address} = {balance} USDT (contract={_usdt_contract_address()})")
    return balance


def get_usdt_balance(wallet_address: str) -> float | None:
    """USDT balance, or None if it could not be determined (NEVER 0.0 on error)."""
    try:
        return fetch_usdt_balance(wallet_address)
    except BalanceUnavailable:
        return None


def get_trx_balance(wallet_address: str) -> float:
    """Check TRX balance of a wallet. Returns TRX amount."""
    try:
        client = _get_tron_client()
        balance_sun = client.get_account_balance(wallet_address)
        logger.info(f"[ESCROW] TRX balance: {wallet_address} = {balance_sun} TRX")
        return float(balance_sun)
    except Exception as e:
        logger.error(f"[ESCROW] TRX balance check failed for {wallet_address}: {e}")
        return 0.0


def sweep_trx_to_master(from_encrypted_private_key: str) -> str | None:
    """Send remaining TRX from escrow back to master wallet (minus bandwidth fee).

    Returns tx_hash on success, None on failure or no balance.
    """
    try:
        client = _get_tron_client()
        private_key_hex = decrypt_private_key(from_encrypted_private_key)
        priv_key = PrivateKey(bytes.fromhex(private_key_hex))
        from_address = priv_key.public_key.to_base58check_address()

        balance_sun = client.get_account(from_address).get("balance", 0)
        # Keep 1.1 TRX for bandwidth to send TRX itself
        send_amount = balance_sun - 1_100_000
        if send_amount <= 0:
            logger.info(f"[ESCROW] No TRX to sweep from {from_address} (balance={balance_sun/1e6:.2f} TRX)")
            return None

        logger.info(f"[ESCROW] Sweeping {send_amount/1e6:.2f} TRX from {from_address} back to master")
        txn = (
            client.trx.transfer(from_address, settings.tron_master_wallet_address, send_amount)
            .build()
            .sign(priv_key)
        )
        result = txn.broadcast()
        tx_hash = result.get("txid", "")
        logger.info(f"[ESCROW] TRX sweep result: txid={tx_hash}")
        return tx_hash

    except Exception as e:
        logger.error(f"[ESCROW] TRX sweep failed: {e}", exc_info=True)
        return None


# ── Gas estimation + receipt-checked USDT payout ────────────────────────
#
# A USDT transfer to an address holding 0 USDT costs ~130k energy (new storage slot);
# to an address that already holds USDT ~65k. With no staked energy the escrow burns
# TRX at the chain energy fee (100 sun/energy at the time of writing), i.e. ~13 TRX —
# the old fixed 7 TRX top-up made transfers die with OUT_OF_ENERGY while the endpoint
# reported success (broadcast txid ≠ executed). Everything below: estimate per receiver,
# top up only the difference, check master funds BEFORE sending anything, and treat a
# transfer as successful only when the on-chain receipt says SUCCESS.

SUN_PER_TRX = 1_000_000
ENERGY_FALLBACK_NEW_HOLDER = 135_000
ENERGY_FALLBACK_EXISTING_HOLDER = 70_000
ENERGY_FEE_FALLBACK_SUN = 100
BANDWIDTH_RESERVE_SUN = 1 * SUN_PER_TRX
GAS_MARGIN = 1.2
MIN_FEE_LIMIT_SUN = 30 * SUN_PER_TRX
# Master → escrow TRX transfer: bandwidth (~0.27 TRX) + possible 1 TRX activation of a
# brand-new escrow account. Kept on master on top of the top-up amount.
MASTER_TRANSFER_RESERVE_SUN = int(1.5 * SUN_PER_TRX)
RECEIPT_TIMEOUT_SEC = 60
RECEIPT_POLL_SEC = 3
GAS_CONFIRM_TIMEOUT_SEC = 30


def _api(client: Tron, method: str, params: dict | None = None) -> dict:
    return _throttled(lambda: client.provider.make_request(method, params or {}), what=method)


def _addr_hex(address: str) -> str:
    from tronpy.keys import to_hex_address

    return to_hex_address(address)


def _transfer_parameter(to_address: str, amount_raw: int) -> str:
    """ABI-encoded (address,uint256) for transfer(), 41-prefix stripped."""
    to_hex = _addr_hex(to_address)
    return to_hex[2:].rjust(64, "0") + format(int(amount_raw), "x").rjust(64, "0")


def get_energy_fee_sun(client: Tron | None = None) -> int:
    """Current burn price per energy unit (getchainparameters → getEnergyFee)."""
    client = client or _get_tron_client()
    try:
        params = _api(client, "wallet/getchainparameters").get("chainParameter", [])
        for p in params:
            if p.get("key") == "getEnergyFee" and p.get("value"):
                return int(p["value"])
    except Exception as e:
        logger.warning(f"[ESCROW] getchainparameters failed, energy fee fallback: {e}")
    return ENERGY_FEE_FALLBACK_SUN


def estimate_usdt_transfer_energy(
    from_address: str, to_address: str, amount_raw: int, client: Tron | None = None
) -> int:
    """Energy for transfer(to, amount): estimateenergy → triggerconstantcontract → heuristic."""
    client = client or _get_tron_client()
    body = {
        "owner_address": from_address,
        "contract_address": _usdt_contract_address(),
        "function_selector": "transfer(address,uint256)",
        "parameter": _transfer_parameter(to_address, amount_raw),
        "visible": True,
    }
    for method, key in (("wallet/estimateenergy", "energy_required"),
                        ("wallet/triggerconstantcontract", "energy_used")):
        try:
            resp = _api(client, method, body)
            ok = (resp.get("result") or {}).get("result")
            energy = int(resp.get(key) or 0)
            if ok and energy > 0:
                logger.info(f"[ESCROW] {method}: {energy} energy for USDT → {to_address}")
                return energy
        except Exception as e:
            logger.warning(f"[ESCROW] {method} failed: {e}")
    # Heuristic: empty USDT slot on receiver ≈ 130k energy, otherwise ≈ 65k.
    receiver_balance = get_usdt_balance(to_address)
    energy = ENERGY_FALLBACK_EXISTING_HOLDER if receiver_balance else ENERGY_FALLBACK_NEW_HOLDER
    logger.info(f"[ESCROW] energy fallback {energy} (receiver USDT={receiver_balance})")
    return energy


def estimate_usdt_transfer_cost_sun(
    from_address: str, to_address: str, amount_raw: int, client: Tron | None = None
) -> dict:
    """{energy, energy_fee_sun, required_sun (with bandwidth + margin), fee_limit_sun}."""
    client = client or _get_tron_client()
    energy = estimate_usdt_transfer_energy(from_address, to_address, amount_raw, client)
    fee = get_energy_fee_sun(client)
    required = int((energy * fee + BANDWIDTH_RESERVE_SUN) * GAS_MARGIN)
    return {
        "energy": energy,
        "energy_fee_sun": fee,
        "required_sun": required,
        "fee_limit_sun": max(MIN_FEE_LIMIT_SUN, required),
    }


def _account_balance_sun(client: Tron, address: str) -> int:
    resp = _api(client, "wallet/getaccount", {"address": address, "visible": True})
    return int(resp.get("balance", 0) or 0)


def wait_for_receipt(client: Tron, txid: str, timeout: float = RECEIPT_TIMEOUT_SEC) -> dict:
    """Poll gettransactioninfobyid. Returns {status: SUCCESS|FAILED|PENDING, reason, info}."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            info = _api(client, "wallet/gettransactioninfobyid", {"value": txid})
        except Exception as e:
            logger.warning(f"[ESCROW] receipt poll {txid}: {e}")
            info = {}
        if info and info.get("id"):
            receipt = info.get("receipt") or {}
            rres = receipt.get("result")
            if rres == "SUCCESS":
                return {"status": "SUCCESS", "reason": None, "info": info}
            # TRX transfers have no receipt.result; contract calls always do.
            if rres is None and info.get("result") != "FAILED" and not info.get("contractResult"):
                return {"status": "SUCCESS", "reason": None, "info": info}
            reason = rres or info.get("result") or "FAILED"
            msg = info.get("resMessage")
            if msg:
                try:
                    msg = bytes.fromhex(msg).decode(errors="replace")
                except ValueError:
                    pass
                reason = f"{reason}: {msg}"
            return {"status": "FAILED", "reason": reason, "info": info}
        if time.monotonic() >= deadline:
            return {"status": "PENDING", "reason": "receipt not found within timeout", "info": info}
        time.sleep(RECEIPT_POLL_SEC)


def _broadcast_ok(result: dict) -> str:
    result = result or {}
    txid = result.get("txid") or ""
    if not txid or (result.get("result") is False):
        raise RuntimeError(f"broadcast rejected: {result}")
    return txid


def fetch_usdt_balance_units(wallet_address: str) -> int:
    """Raw USDT balance (integer, 6 decimals). Raises BalanceUnavailable if unknown."""
    if not wallet_address:
        raise BalanceUnavailable("empty wallet address")
    try:
        contract = _get_usdt_contract()
        raw = _throttled(
            lambda: contract.functions.balanceOf(wallet_address), what=f"balanceOf {wallet_address}"
        )
        return int(raw)
    except BalanceUnavailable:
        raise
    except Exception as e:
        logger.error(f"[ESCROW] USDT balance UNKNOWN for {wallet_address}: {e}")
        raise BalanceUnavailable(str(e)) from e


class EscrowTransferRefused(Exception):
    """Transfer was not prepared — NOTHING broadcast (USDT). reason is a short code."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def prepare_usdt_transfer(
    from_encrypted_private_key: str,
    to_address: str,
    amount_units: int,
    *,
    allow_master: bool = False,
) -> dict:
    """Estimate gas, top up escrow TRX (difference only), build + sign the USDT transfer.

    Does NOT broadcast the USDT transfer. Returns {txid, txn, gas_tx, estimate,
    from_address, fee_limit_sun}. The txid is known before broadcast so the caller
    records it first (crash/timeout after broadcast can then be reconciled by receipt).
    Raises EscrowTransferRefused (nothing USDT-related was sent).
    Blocking — call via asyncio.to_thread.
    """
    master = (settings.tron_master_wallet_address or "").strip()
    to_address = (to_address or "").strip()
    if not to_address:
        raise EscrowTransferRefused("EMPTY_ADDRESS", "Порожня адреса отримувача")
    if master and to_address == master and not allow_master:
        raise EscrowTransferRefused(
            "MASTER_DESTINATION",
            "Адреса отримувача = master-гаманець платформи. Вкажіть гаманець покупця/продавця.",
        )
    amount_units = int(amount_units)
    if amount_units <= 0:
        raise EscrowTransferRefused("BAD_AMOUNT", "Некоректна сума")
    client = _get_tron_client()
    priv_key = PrivateKey(bytes.fromhex(decrypt_private_key(from_encrypted_private_key)))
    from_address = priv_key.public_key.to_base58check_address()
    if to_address == from_address:
        raise EscrowTransferRefused("SELF_DESTINATION", "Адреса отримувача = сам escrow-гаманець")

    est = estimate_usdt_transfer_cost_sun(from_address, to_address, amount_units, client)
    escrow_bal = _account_balance_sun(client, from_address)
    topup = max(0, est["required_sun"] - escrow_bal)
    logger.info(
        f"[ESCROW] prepare {amount_units} units {from_address}→{to_address}: est={est}, "
        f"escrow TRX={escrow_bal / SUN_PER_TRX:.6f}, top-up={topup / SUN_PER_TRX:.6f}"
    )
    gas_tx = None
    if topup > 0:
        master_bal = _account_balance_sun(client, master)
        need = topup + MASTER_TRANSFER_RESERVE_SUN
        if master_bal < need:
            raise EscrowTransferRefused(
                "MASTER_INSUFFICIENT_TRX",
                f"Недостатньо TRX на master-гаманці {master}: є {master_bal / SUN_PER_TRX:.2f} TRX, "
                f"потрібно ≈{need / SUN_PER_TRX:.2f} TRX (газ {topup / SUN_PER_TRX:.2f} + резерв). "
                f"Нічого не відправлено.",
            )
        master_key = PrivateKey(bytes.fromhex(settings.tron_master_wallet_private_key))
        try:
            gas_txn = client.trx.transfer(master, from_address, topup).build().sign(master_key)
            gas_tx = _broadcast_ok(gas_txn.broadcast())
        except Exception as e:
            raise EscrowTransferRefused("GAS_TOPUP_FAILED", f"Газ-поповнення не вдалося: {e}") from e
        logger.info(f"[ESCROW] gas top-up {topup / SUN_PER_TRX:.6f} TRX tx={gas_tx}")
        gas_r = wait_for_receipt(client, gas_tx, timeout=GAS_CONFIRM_TIMEOUT_SEC)
        if gas_r["status"] != "SUCCESS":
            raise EscrowTransferRefused(
                "GAS_TOPUP_UNCONFIRMED",
                f"Газ-поповнення escrow не підтвердилось: {gas_r['reason']} (tx {gas_tx})",
            )

    contract = _get_usdt_contract()
    txn = (
        contract.functions.transfer(to_address, amount_units)
        .with_owner(from_address)
        .fee_limit(est["fee_limit_sun"])
        .build()
        .sign(priv_key)
    )
    return {
        "txid": txn.txid,
        "txn": txn,
        "gas_tx": gas_tx,
        "estimate": est,
        "from_address": from_address,
        "fee_limit_sun": est["fee_limit_sun"],
    }


def broadcast_prepared(prepared: dict) -> str:
    """Broadcast a prepared transfer. Raises on rejection/network error (tx may still be live)."""
    return _broadcast_ok(prepared["txn"].broadcast())


def get_receipt(txid: str, timeout: float = 0) -> dict:
    """Receipt status of txid: SUCCESS | FAILED | PENDING (not found yet / unknown)."""
    return wait_for_receipt(_get_tron_client(), txid, timeout=timeout)
