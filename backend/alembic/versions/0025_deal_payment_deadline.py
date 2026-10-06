"""Deals: explicit payment deadline + cancel metadata (balance-first timeout)

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-06

All columns are nullable and NOT backfilled on purpose:
- payment_deadline_at IS NULL on existing deals → a legacy deal still in
  'created' is never auto-cancelled by the new created-stage timeout (no mass
  cancel on deploy). Legacy 'payment_pending' deals keep the old rule
  (created_at + PAYMENT_TIMEOUT_HOURS) but now only after a successful
  zero-balance check.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("payment_deadline_at", sa.DateTime(), nullable=True))
    op.add_column("deals", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("deals", sa.Column("cancel_reason", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "cancel_reason")
    op.drop_column("deals", "cancelled_at")
    op.drop_column("deals", "payment_deadline_at")
