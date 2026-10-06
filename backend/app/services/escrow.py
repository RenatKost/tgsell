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


def transfer_usdt(
    from_encrypted_private_key: str,
    to_address: str,
    amount_usdt: float,
) -> str | None:
    """Transfer USDT TRC-20 from escrow wallet to target address.

    Note: The from wallet must have TRX for gas fees.

    Returns tx_hash on success, None on failure.
    """
    try:
        client = _get_tron_client()
        private_key_hex = decrypt_private_key(from_encrypted_private_key)
        priv_key = PrivateKey(bytes.fromhex(private_key_hex))
        from_address = priv_key.public_key.to_base58check_address()

        contract_address = settings.usdt_contract_address or USDT_CONTRACTS.get(
            settings.tron_network, USDT_CONTRACTS["nile"]
        )
        contract = client.get_contract(contract_address)

        amount_raw = int(amount_usdt * 1_000_000)  # 6 decimals
        logger.info(f"[ESCROW] USDT transfer: {amount_usdt} ({amount_raw} raw) from {from_address} to {to_address}, contract={contract_address}")

        txn = (
            contract.functions.transfer(to_address, amount_raw)
            .with_owner(from_address)
            .fee_limit(15_000_000)  # 15 TRX max fee
            .build()
            .sign(priv_key)
        )
        result = txn.broadcast()
        tx_hash = result.get("txid", "")
        logger.info(f"[ESCROW] USDT transfer BROADCAST result: txid={tx_hash}, full_result={result}")
        return tx_hash

    except Exception as e:
        logger.error(f"[ESCROW] USDT transfer FAILED: {amount_usdt} to {to_address}: {e}", exc_info=True)
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


def send_trx_for_gas(to_address: str, amount_trx: int = 10) -> str | None:
    """Send TRX from master wallet to escrow wallet for gas fees.

    Returns tx_hash on success.
    """
    try:
        client = _get_tron_client()
        priv_key = PrivateKey(bytes.fromhex(settings.tron_master_wallet_private_key))
        logger.info(f"[ESCROW] TRX gas: sending {amount_trx} TRX from master {settings.tron_master_wallet_address} to {to_address}")

        txn = (
            client.trx.transfer(
                settings.tron_master_wallet_address,
                to_address,
                amount_trx * 1_000_000,  # TRX in SUN
            )
            .build()
            .sign(priv_key)
        )
        result = txn.broadcast()
        tx_hash = result.get("txid", "")
        logger.info(f"[ESCROW] TRX gas BROADCAST result: txid={tx_hash}, full_result={result}")
        return tx_hash

    except Exception as e:
        logger.error(f"[ESCROW] TRX gas transfer FAILED to {to_address}: {e}", exc_info=True)
        return None
