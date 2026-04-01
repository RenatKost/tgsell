"""USDT TRC-20 Escrow Service — wallet generation, balance checking, payouts."""
import logging

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


def get_usdt_balance(wallet_address: str) -> float:
    """Check USDT TRC-20 balance of a wallet.

    Returns balance in USDT (6 decimals).
    """
    try:
        client = _get_tron_client()
        contract_address = settings.usdt_contract_address or USDT_CONTRACTS.get(
            settings.tron_network, USDT_CONTRACTS["nile"]
        )
        contract = client.get_contract(contract_address)
        balance_raw = contract.functions.balanceOf(wallet_address)
        balance = balance_raw / 1_000_000  # USDT has 6 decimals
        logger.info(f"[ESCROW] Balance check: {wallet_address} = {balance} USDT (contract={contract_address})")
        return balance
    except Exception as e:
        logger.error(f"[ESCROW] Failed to check USDT balance for {wallet_address}: {e}", exc_info=True)
        return 0.0


def transfer_usdt(
    from_encrypted_private_key: str,
    to_address: str,
    amount_usdt: float,
) -> str | None:
    """Transfer USDT TRC-20 from escrow wallet to target address.

    Note: The from wallet must have TRX for gas fees (~5-10 TRX).

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
            .fee_limit(30_000_000)
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
