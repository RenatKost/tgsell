"""Initial tables

Revision ID: 0001
Revises:
Create Date: 2024-01-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, nullable=False),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("first_name", sa.String(200), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("role", sa.Enum("user", "moderator", "admin", name="userrole"), server_default="user"),
        sa.Column("usdt_wallet", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Channels
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("telegram_link", sa.String(200), nullable=False),
        sa.Column("channel_name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("subscribers_count", sa.Integer(), default=0),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("monthly_income", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resources", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("avg_views", sa.Integer(), nullable=True),
        sa.Column("er", sa.Float(), nullable=True),
        sa.Column("daily_growth", sa.Float(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("status", sa.Enum("pending", "approved", "rejected", "sold", name="channelstatus"), server_default="pending"),
        sa.Column("moderator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Channel stats
    op.create_table(
        "channel_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("subscribers", sa.Integer(), default=0),
        sa.Column("avg_views", sa.Integer(), default=0),
        sa.Column("avg_reach", sa.Integer(), default=0),
        sa.Column("er", sa.Float(), default=0.0),
    )

    # Deals
    op.create_table(
        "deals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("buyer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.Enum("created", "payment_pending", "paid", "channel_transferring", "completed", "disputed", "cancelled", name="dealstatus"), server_default="created"),
        sa.Column("escrow_wallet_address", sa.String(100), nullable=False),
        sa.Column("escrow_private_key_encrypted", sa.Text(), nullable=False),
        sa.Column("amount_usdt", sa.Float(), nullable=False),
        sa.Column("service_fee", sa.Float(), server_default="0"),
        sa.Column("deal_group_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("dispute_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    # Transactions
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tx_hash", sa.String(100), nullable=True),
        sa.Column("from_address", sa.String(100), nullable=True),
        sa.Column("to_address", sa.String(100), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("type", sa.Enum("deposit", "release", "refund", name="transactiontype"), nullable=False),
        sa.Column("status", sa.Enum("pending", "confirmed", "failed", name="transactionstatus"), server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("deals")
    op.drop_table("channel_stats")
    op.drop_table("channels")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS transactionstatus")
    op.execute("DROP TYPE IF EXISTS transactiontype")
    op.execute("DROP TYPE IF EXISTS dealstatus")
    op.execute("DROP TYPE IF EXISTS channelstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
