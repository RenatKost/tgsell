"""CatFee.io energy rental client (Task 18).

Before an escrow USDT payout we rent energy for 1h with receiver = escrow address, so the
transfer consumes delegated energy instead of burning ~7–14 TRX. Any problem (no key, API
error, timeout, empty balance) → caller falls back to the TRX-burn scheme (Task 17A).

Auth: HMAC-SHA256(secret, timestamp + METHOD + requestPath-with-query) → base64, headers
CF-ACCESS-KEY / CF-ACCESS-SIGN / CF-ACCESS-TIMESTAMP. Business success = body code == 0.
Idempotency: client_order_id (same id → the existing order is returned, never charged twice).
The API key/secret are NEVER logged.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MIN_QUANTITY = 65_000
DURATION = "1h"
HTTP_TIMEOUT_SEC = 15
# Fallback per-payout rental estimate (TRX) when there's no history: 131k energy ≈ 2.3 TRX (14.10).
DEFAULT_RENT_TRX = 2.5
LOW_BALANCE_PAYOUTS = 5
OK_STATUSES = {"PAYMENT_SUCCESS", "DELEGATE_SUCCESS"}
FAIL_STATUSES = {"DELEGATE_FAIL", "INSUFFICIENT_BALANCE", "QUANTITY_TOO_HIGH", "QUANTITY_TOO_LOW",
                 "ADDRESS_NOT_ACTIVATED", "INVALID_ADDRESS"}


class CatFeeError(Exception):
    """API/transport failure. code = business code (or None for transport errors)."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def enabled() -> bool:
    return bool((settings.catfee_api_key or "").strip() and (settings.catfee_api_secret or "").strip())


def base_url() -> str:
    if (settings.catfee_base_url or "").strip():
        return settings.catfee_base_url.strip().rstrip("/")
    return "https://api.catfee.io" if settings.tron_network == "mainnet" else "https://nile.catfee.io"


def _timestamp() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def sign(secret: str, timestamp: str, method: str, request_path: str) -> str:
    msg = f"{timestamp}{method.upper()}{request_path}".encode()
    return base64.b64encode(hmac.new(secret.encode(), msg, hashlib.sha256).digest()).decode()


def _request(method: str, path: str, params: dict | None = None, *, client: httpx.Client | None = None) -> dict:
    if not enabled():
        raise CatFeeError("CatFee disabled (no CATFEE_API_KEY/CATFEE_API_SECRET)")
    request_path = path + ("?" + urlencode(params) if params else "")
    ts = _timestamp()
    headers = {
        "Content-Type": "application/json",
        "CF-ACCESS-KEY": settings.catfee_api_key.strip(),
        "CF-ACCESS-SIGN": sign(settings.catfee_api_secret.strip(), ts, method, request_path),
        "CF-ACCESS-TIMESTAMP": ts,
    }
    try:
        if client is not None:
            resp = client.request(method, base_url() + request_path, headers=headers)
        else:
            with httpx.Client(timeout=HTTP_TIMEOUT_SEC) as c:
                resp = c.request(method, base_url() + request_path, headers=headers)
    except httpx.HTTPError as e:
        raise CatFeeError(f"{method} {path}: transport error {type(e).__name__}") from e
    try:
        body = resp.json()
    except ValueError:
        raise CatFeeError(f"{method} {path}: HTTP {resp.status_code}, non-JSON body")
    if not isinstance(body, dict):
        raise CatFeeError(f"{method} {path}: HTTP {resp.status_code}, unexpected body")
    code = body.get("code")
    if code != 0:
        raise CatFeeError(f"{method} {path}: code={code} msg={body.get('msg')} sub={body.get('sub_code')}",
                          code=code if isinstance(code, int) else None)
    return body.get("data") or {}


def get_balance_sun() -> int:
    """Prepaid CatFee balance (sun). Raises CatFeeError."""
    data = _request("GET", "/v1/account")
    return int(data.get("balance") or 0)


def create_order(receiver: str, quantity: int, client_order_id: str) -> dict:
    """Rent `quantity` energy for 1h to `receiver` (idempotent by client_order_id)."""
    params = {"quantity": max(MIN_QUANTITY, int(quantity)), "receiver": receiver,
              "duration": DURATION, "client_order_id": client_order_id, "activate": "false"}
    data = _request("POST", "/v1/order", params)
    if not data.get("id"):
        raise CatFeeError("order created without id")
    status = data.get("status")
    if status in FAIL_STATUSES:
        raise CatFeeError(f"order {data.get('id')} status {status}")
    logger.info(f"[CATFEE] order {data.get('id')} ({client_order_id}) {data.get('quantity')} energy → {receiver}: "
                f"status={status} confirm={data.get('confirm_status')} "
                f"pay={int(data.get('pay_amount_sun') or 0) / 1e6:.6f} TRX")
    return data


def get_order(order_id: str) -> dict:
    return _request("GET", f"/v1/order/{order_id}")


def order_cost_sun(order: dict | None) -> int:
    o = order or {}
    return int(o.get("pay_amount_sun") or 0) + int(o.get("activate_amount_sun") or 0)
