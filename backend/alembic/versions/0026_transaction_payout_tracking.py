"""Transactions: outgoing-payout tracking + fee_collection / sweep types

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-12

Additive and backward-compatible only:
- two new values of the native ``transactiontype`` enum (same pattern as 0008/0021);
- nullable columns on ``transactions``; existing rows are NOT backfilled or modified
  (legacy rows keep NULL receipt_status → never eligible for fee collection);
- a plain (non-unique) index for the "open outgoing transfer per deal" lookup.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'fee_collection'")
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'sweep'")
    op.add_column("transactions", sa.Column("amount_units", sa.BigInteger(), nullable=True))
    op.add_column("transactions", sa.Column("restore_status", sa.String(30), nullable=True))
    op.add_column("transactions", sa.Column("receipt_status", sa.String(50), nullable=True))
    op.add_column("transactions", sa.Column("receipt_reason", sa.Text(), nullable=True))
    op.add_column("transactions", sa.Column("fee_limit_sun", sa.BigInteger(), nullable=True))
    op.add_column("transactions", sa.Column("broadcast_at", sa.DateTime(), nullable=True))
    op.add_column("transactions", sa.Column("finalized_at", sa.DateTime(), nullable=True))
    op.create_index("ix_transactions_deal_status", "transactions", ["deal_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_transactions_deal_status", table_name="transactions")
    for col in ("finalized_at", "broadcast_at", "fee_limit_sun", "receipt_reason",
                "receipt_status", "restore_status", "amount_units"):
        op.drop_column("transactions", col)
    # enum values cannot be dropped safely (see 0021)
