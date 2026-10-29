"""Pending bot-auth tokens (in-memory store with TTL)."""
import secrets
import time

_pending: dict[str, dict] = {}
_TTL = 300  # 5 minutes


def create_auth_token(meta: dict | None = None) -> str:
    """Generate a random token and store it as pending. `meta` = {anon_hash, utm_*} of the site visitor
    (carried server-side across the Telegram deep-link roundtrip; no PII)."""
    token = secrets.token_urlsafe(32)
    _pending[token] = {"created": time.time(), "user": None, "meta": meta or {}}
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


def get_meta(token: str) -> dict:
    """Visitor meta bound to a still-valid token ({} when unknown/expired)."""
    entry = _pending.get(token)
    if not entry or time.time() - entry["created"] > _TTL:
        return {}
    return dict(entry.get("meta") or {})


def is_known(token: str) -> bool:
    entry = _pending.get(token)
    return bool(entry) and time.time() - entry["created"] <= _TTL


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
