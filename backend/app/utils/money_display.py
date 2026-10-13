"""Display/serialization helpers for USDT amounts (NOT used for on-chain math)."""
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def money2(value) -> float | None:
    """Round an amount to 2 decimals (ROUND_HALF_UP) for API/UI output only."""
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP))


def money2_str(value) -> str:
    """Same as money2 but formatted with exactly 2 decimals, e.g. '3.00'."""
    return f"{Decimal(str(value or 0)).quantize(_CENT, rounding=ROUND_HALF_UP):.2f}"
