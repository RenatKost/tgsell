"""Add deal flow fields: readiness, transfer confirmation, payout, system messages

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deal: readiness + transfer confirmations
    op.add_column("deals", sa.Column("buyer_ready", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("deals", sa.Column("seller_ready", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("deals", sa.Column("buyer_confirmed_transfer", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("deals", sa.Column("seller_confirmed_transfer", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("deals", sa.Column("seller_payout_address", sa.String(100), nullable=True))
    op.add_column("deals", sa.Column("payout_tx_hash", sa.String(100), nullable=True))

    # DealMessage: system messages flag
    op.add_column("deal_messages", sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False))

    # Add awaiting_payout to the DealStatus enum
    # PostgreSQL requires ALTER TYPE to add enum values
    op.execute("ALTER TYPE dealstatus ADD VALUE IF NOT EXISTS 'awaiting_payout' AFTER 'channel_transferring'")


def downgrade() -> None:
    op.drop_column("deals", "buyer_ready")
    op.drop_column("deals", "seller_ready")
    op.drop_column("deals", "buyer_confirmed_transfer")
    op.drop_column("deals", "seller_confirmed_transfer")
    op.drop_column("deals", "seller_payout_address")
    op.drop_column("deals", "payout_tx_hash")
    op.drop_column("deal_messages", "is_system")
