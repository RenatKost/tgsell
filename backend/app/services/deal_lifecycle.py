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


class PayoutClaimError(Exception):
    """Raised when a payout/refund claim cannot be taken (race or wrong state)."""

    def __init__(self, code: str, message: str, *, http_status: int = 409):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def has_payout_tx(deal: Deal) -> bool:
    """True when a non-empty on-chain payout/refund tx hash is already stored."""
    return bool(deal.payout_tx_hash and str(deal.payout_tx_hash).strip())


def claim_deal_for_transfer(deal: Deal, *, expected_status: DealStatus) -> None:
    """Claim exclusive right to broadcast an escrow transfer.

    Caller MUST hold SELECT … FOR UPDATE on the deal row and COMMIT
    immediately after this mutates status → payout_in_progress so a
    concurrent request no longer sees the expected status.

    Raises PayoutClaimError when another request already claimed, the
    deal is in the wrong status, or a payout_tx_hash is already set.
    """
    if has_payout_tx(deal):
        raise PayoutClaimError(
            "already_paid",
            "Payout already completed",
            http_status=409,
        )
    if deal.status == DealStatus.payout_in_progress:
        raise PayoutClaimError(
            "in_progress",
            "Payout already in progress",
            http_status=409,
        )
    if deal.status != expected_status:
        raise PayoutClaimError(
            "wrong_status",
            f"Deal is not {expected_status.value}",
            http_status=400,
        )
    deal.status = DealStatus.payout_in_progress


def release_payout_claim(deal: Deal, *, restore_status: DealStatus) -> None:
    """Roll intermediate payout_in_progress back after a failed transfer."""
    if deal.status == DealStatus.payout_in_progress:
        deal.status = restore_status
