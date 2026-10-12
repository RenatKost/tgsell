"""Payout gas top-up retry: transactions.gas_tx_hash + gas_attempts (additive).

Revision ID: 0031
Revises: 0030
"""
import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transactions", sa.Column("gas_tx_hash", sa.String(100), nullable=True))
    op.add_column("transactions", sa.Column("gas_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("transactions", "gas_attempts")
    op.drop_column("transactions", "gas_tx_hash")
