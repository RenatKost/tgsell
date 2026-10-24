"""«Гарант для зовнішніх угод»: pure validation + fee helpers (no DB, no money moves)."""
from __future__ import annotations

import re
import secrets

from app.config import settings

MIN_PRICE_USDT = 5.0
MAX_PRICE_USDT = 1_000_000.0
TOKEN_BYTES = 24  # secrets.token_urlsafe(24) → 32 chars, ~192 bits

_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{3,31}$")
_LINK_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(\+[A-Za-z0-9_-]{8,64}|joinchat/[A-Za-z0-9_-]{8,64}|[A-Za-z][A-Za-z0-9_]{3,31})/?$"
)
_AT_RE = re.compile(r"^@([A-Za-z][A-Za-z0-9_]{3,31})$")


def normalize_username(raw: str | None) -> str | None:
    """'@Ivan_Buyer ' → 'ivan_buyer'; invalid → None."""
    if not raw:
        return None
    u = raw.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if u.lower().startswith(prefix):
            u = u[len(prefix):]
    u = u.lstrip("@").strip().lower()
    return u if _USERNAME_RE.match(u) else None


def normalize_channel_link(raw: str | None) -> str | None:
    """Accepts t.me/name, https://t.me/+invite, @name → canonical https://t.me/…; invalid → None."""
    if not raw:
        return None
    s = raw.strip()
    m = _AT_RE.match(s)
    if m:
        return f"https://t.me/{m.group(1)}"
    m = _LINK_RE.match(s)
    if m:
        return f"https://t.me/{m.group(1)}"
    return None


def fee_percent() -> float:
    return float(settings.service_fee_percent)


def calc_fee(price: float, percent: float | None = None) -> float:
    pct = fee_percent() if percent is None else percent
    return round(price * pct / 100, 2)


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def buyer_url(token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/escrow/{token}"
