"""Deal lifecycle invariants — completed requires a real on-chain payout tx hash."""
from __future__ import annotations

from datetime import datetime

from app.models.deal import Deal, DealStatus


class DealCompletionError(ValueError):
    """Raised when a deal would be marked completed without a payout tx hash."""


def assert_completed_has_payout(deal: Deal) -> None:
    """Refuse completed deals that lack a non-empty payout_tx_hash."""
    if deal.status != DealStatus.completed:
        return
    if not deal.payout_tx_hash or not str(deal.payout_tx_hash).strip():
        raise DealCompletionError(
            f"Deal #{getattr(deal, 'id', '?')} is completed but payout_tx_hash is empty"
        )


def mark_deal_completed(
    deal: Deal,
    payout_tx_hash: str | None,
    *,
    completed_at: datetime | None = None,
) -> Deal:
    """Set deal to completed ONLY when a real on-chain payout tx hash is provided.

    All code paths that set DealStatus.completed must go through this helper.
    """
    if payout_tx_hash is None or not str(payout_tx_hash).strip():
        raise DealCompletionError(
            "Cannot mark deal completed without a non-empty payout_tx_hash"
        )
    deal.payout_tx_hash = str(payout_tx_hash).strip()
    deal.status = DealStatus.completed
    deal.completed_at = completed_at or datetime.utcnow()
    assert_completed_has_payout(deal)
    return deal
