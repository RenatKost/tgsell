"""Partial payment info + overpayment refund (additive).

Revision ID: 0032
Revises: 0031

Existing deals keep NULLs ⇒ overpay refund never fires for already paid/completed deals.
"""
import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'overpay_refund'")
    op.add_column("deals", sa.Column("received_usdt", sa.Float(), nullable=True))
    op.add_column("deals", sa.Column("partial_notified_units", sa.BigInteger(), nullable=True))
    op.add_column("deals", sa.Column("overpay_units", sa.BigInteger(), nullable=True))
    op.add_column("deals", sa.Column("overpay_refund_address", sa.String(100), nullable=True))
    op.add_column("deals", sa.Column("overpay_status", sa.String(20), nullable=True))


def downgrade():
    for c in ("overpay_status", "overpay_refund_address", "overpay_units", "partial_notified_units", "received_usdt"):
        op.drop_column("deals", c)
    # enum value 'overpay_refund' is left in place (PostgreSQL cannot drop enum values).
