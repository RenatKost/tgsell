"""Admin broadcast log: UNIQUE(campaign_key, user_id); paid_service_orders.overpay_alerted_at.

Revision ID: 0053
Revises: 0052
"""
import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broadcast_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_key", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("campaign_key", "user_id", name="uq_broadcast_log_campaign_user"),
    )
    op.create_index("ix_broadcast_log_campaign_key", "broadcast_log", ["campaign_key"])
    op.add_column("paid_service_orders", sa.Column("overpay_alerted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("paid_service_orders", "overpay_alerted_at")
    op.drop_index("ix_broadcast_log_campaign_key", table_name="broadcast_log")
    op.drop_table("broadcast_log")
