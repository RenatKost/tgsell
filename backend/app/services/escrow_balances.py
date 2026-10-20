"""Task 33: READ-ONLY on-chain USDT balances of all escrow addresses (no signing, no transfers)."""
from __future__ import annotations


def collect_escrow_balances(rows: list[tuple[int, str, str]], previous: dict | None = None) -> dict:
    """Blocking, READ-ONLY: one throttled TronGrid balanceOf per distinct escrow address.

    Covers ALL deals (any status, incl. cancelled). Unknown ≠ 0: an address whose balance
    could not be read (TronGrid 429 after retries, network) is reported as unknown; if a
    previous read exists it is shown as ``stale`` last-known value but NOT summed into the
    confirmed total. Nothing here signs or sends anything.
    """
    from app.services.escrow import BalanceUnavailable, fetch_usdt_balance

    prev_by_addr = {a["address"]: a for a in (previous or {}).get("addresses", [])
                    if a.get("balance_usdt") is not None and not a.get("stale")}
    by_addr: dict[str, list[tuple[int, str]]] = {}
    for deal_id, escrow, status_value in rows:
        if escrow:
            by_addr.setdefault(escrow, []).append((deal_id, status_value))
    with_funds, unknown, addresses = [], [], []
    for escrow, deals in by_addr.items():
        deal_ids = [d for d, _ in deals]
        try:
            balance = fetch_usdt_balance(escrow)
        except BalanceUnavailable as e:
            for deal_id, status_value in deals:
                unknown.append({
                    "deal_id": deal_id, "escrow": escrow, "status": status_value,
                    "balance_usdt": None, "error": "unknown", "detail": str(e)[:200],
                })
            last = prev_by_addr.get(escrow)
            addresses.append({"address": escrow, "deal_ids": deal_ids,
                              "statuses": [st for _, st in deals], "balance_usdt": None,
                              "last_known_usdt": last["balance_usdt"] if last else None,
                              "stale": True})
            continue
        addresses.append({"address": escrow, "deal_ids": deal_ids, "statuses": [st for _, st in deals],
                          "balance_usdt": balance, "stale": False})
        if balance > 0:
            deal_id, status_value = deals[0]
            with_funds.append({
                "deal_id": deal_id, "escrow": escrow, "status": status_value, "balance_usdt": balance,
            })
    total = round(sum(a["balance_usdt"] for a in addresses if a["balance_usdt"] is not None), 6)
    return {
        "wallets_with_funds": with_funds,
        "total": total,
        "onchain_total_usdt": total,
        "onchain_unknown_count": sum(1 for a in addresses if a["balance_usdt"] is None),
        "onchain_last_known_unknown_usdt": round(sum(a.get("last_known_usdt") or 0 for a in addresses
                                                     if a["balance_usdt"] is None), 6),
        "addresses": sorted(addresses, key=lambda a: -(a["balance_usdt"] or a.get("last_known_usdt") or 0)),
        "unknown": unknown,
        "unknown_count": len(unknown),
        "checked_count": len(rows),
        "address_count": len(by_addr),
    }
