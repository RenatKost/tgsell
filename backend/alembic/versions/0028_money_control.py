"""Money control: transactions(type, status, created_at) index + master_wallet_snapshots

Revision ID: 0028
Revises: 0027
"""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_transactions_type_status_created", "transactions", ["type", "status", "created_at"])
    op.create_table(
        "master_wallet_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("trx_sun", sa.BigInteger(), nullable=True),
        sa.Column("energy_available", sa.BigInteger(), nullable=True),
        sa.Column("bandwidth_available", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_master_wallet_snapshots_at", "master_wallet_snapshots", ["at"])


def downgrade() -> None:
    op.drop_index("ix_master_wallet_snapshots_at", table_name="master_wallet_snapshots")
    op.drop_table("master_wallet_snapshots")
    op.drop_index("ix_transactions_type_status_created", table_name="transactions")
