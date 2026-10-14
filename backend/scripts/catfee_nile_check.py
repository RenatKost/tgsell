"""CatFee Nile TESTNET check (Task 18). Never touches mainnet.

Usage (from backend/, test-account key from https://nile.catfee.io → User Center → API):
  CATFEE_API_KEY=... CATFEE_API_SECRET=... python scripts/catfee_nile_check.py
      → signature/auth check + test balance
  CATFEE_API_KEY=... CATFEE_API_SECRET=... python scripts/catfee_nile_check.py --order T<nile address> [--quantity 65000]
      → rents energy for 1h on Nile to an ACTIVATED Nile address and waits until
        getaccountresource (nile.trongrid.io) shows it (≤60s).
The key/secret are never printed.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NILE_CATFEE = "https://nile.catfee.io"
NILE_TRONGRID = "https://nile.trongrid.io"


def energy_of(address: str) -> int:
    r = httpx.post(f"{NILE_TRONGRID}/wallet/getaccountresource", json={"address": address, "visible": True},
                   timeout=15).json()
    return max(0, int(r.get("EnergyLimit", 0) or 0) - int(r.get("EnergyUsed", 0) or 0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", metavar="NILE_ADDRESS", help="rent energy to this activated Nile address")
    ap.add_argument("--quantity", type=int, default=65_000)
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args()

    from app.config import settings
    from app.services import catfee

    # Hard pin to the Nile test environment, whatever the env says.
    settings.catfee_base_url = NILE_CATFEE
    settings.tron_network = "nile"
    settings.catfee_api_key = os.environ.get("CATFEE_API_KEY", "")
    settings.catfee_api_secret = os.environ.get("CATFEE_API_SECRET", "")
    assert catfee.base_url() == NILE_CATFEE, "refusing: not the Nile endpoint"
    if not catfee.enabled():
        print("CATFEE_API_KEY / CATFEE_API_SECRET (Nile test account) not set")
        return 2

    bal = catfee.get_balance_sun()
    print(f"[ok] auth/signature accepted by {NILE_CATFEE}; test balance = {bal / 1e6:.6f} TRX")
    if not a.order:
        return 0

    before = energy_of(a.order)
    print(f"[..] {a.order} energy before: {before}")
    order = catfee.create_order(a.order, a.quantity, f"tgsell-nile-{uuid.uuid4().hex[:12]}")
    print(f"[ok] order {order.get('id')} status={order.get('status')} confirm={order.get('confirm_status')} "
          f"cost={catfee.order_cost_sun(order) / 1e6:.6f} TRX")
    deadline = time.monotonic() + a.timeout
    while time.monotonic() < deadline:
        now = energy_of(a.order)
        if now >= before + int(a.quantity * 0.95):
            print(f"[ok] energy arrived: {now} (+{now - before})")
            o = catfee.get_order(str(order["id"]))
            print(f"[ok] order detail: status={o.get('status')} confirm={o.get('confirm_status')} "
                  f"delegate_hash={o.get('delegate_hash')}")
            return 0
        time.sleep(3)
    print(f"[!!] energy not visible within {a.timeout}s (now {energy_of(a.order)})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
