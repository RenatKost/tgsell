"""Payment deadlines for unpaid deals (naive UTC).

* 'created' stage (waiting for both sides' readiness — the buyer already has the
  escrow address): created_at + CREATED_DEAL_TIMEOUT_HOURS.
* 'payment_pending' stage: PAYMENT_TIMEOUT_HOURS from the moment both sides are ready.
* Legacy deals (payment_deadline_at NULL, created before migration 0025):
  'payment_pending' → created_at + PAYMENT_TIMEOUT_HOURS (old rule);
  'created' → never auto-cancelled (manual admin decision).

A deadline only allows cancelling after a SUCCESSFUL zero-balance check.
"""
from datetime import datetime, timedelta

from app.config import settings
from app.models.deal import Deal, DealStatus


def created_stage_deadline(created_at: datetime) -> datetime:
    return created_at + timedelta(hours=settings.created_deal_timeout_hours)


def payment_stage_deadline(now: datetime) -> datetime:
    return now + timedelta(hours=settings.payment_timeout_hours)


def effective_payment_deadline(deal: Deal) -> datetime | None:
    """When a confirmed-zero-balance deal may be auto-cancelled; None = never."""
    if deal.payment_deadline_at is not None:
        return deal.payment_deadline_at
    if deal.status == DealStatus.payment_pending and deal.created_at is not None:
        return deal.created_at + timedelta(hours=settings.payment_timeout_hours)
    return None
