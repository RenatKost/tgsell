"""Pending bot-auth tokens (in-memory store with TTL)."""
import secrets
import time

_pending: dict[str, dict] = {}
_TTL = 300  # 5 minutes


def create_auth_token() -> str:
    """Generate a random token and store it as pending."""
    token = secrets.token_urlsafe(32)
    _pending[token] = {"created": time.time(), "user": None}
    _cleanup()
    return token


def complete_auth_token(token: str, user_data: dict) -> bool:
    """Mark token as completed with user data (called from bot)."""
    entry = _pending.get(token)
    if not entry or entry["user"] is not None:
        return False
    if time.time() - entry["created"] > _TTL:
        _pending.pop(token, None)
        return False
    entry["user"] = user_data
    return True


def check_auth_token(token: str) -> dict | None:
    """Check if token has been completed. Returns user data or None."""
    entry = _pending.get(token)
    if not entry:
        return None
    if time.time() - entry["created"] > _TTL:
        _pending.pop(token, None)
        return None
    return entry["user"]


def consume_auth_token(token: str) -> dict | None:
    """Get and remove completed token data."""
    entry = _pending.pop(token, None)
    if not entry or not entry["user"]:
        return None
    if time.time() - entry["created"] > _TTL:
        return None
    return entry["user"]


def _cleanup():
    """Remove expired tokens."""
    now = time.time()
    expired = [k for k, v in _pending.items() if now - v["created"] > _TTL]
    for k in expired:
        del _pending[k]
