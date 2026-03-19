import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the encryption key in settings."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"tgsell-escrow-salt",  # Fixed salt (key is already unique)
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.encryption_key.encode()))
    return Fernet(key)


def encrypt_private_key(private_key: str) -> str:
    """Encrypt a private key for storage in DB."""
    f = _get_fernet()
    return f.encrypt(private_key.encode()).decode()


def decrypt_private_key(encrypted_key: str) -> str:
    """Decrypt a private key from DB."""
    f = _get_fernet()
    return f.decrypt(encrypted_key.encode()).decode()
