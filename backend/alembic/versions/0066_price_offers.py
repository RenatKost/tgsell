"""price_offers — buyer counter-offers on a catalog lot.

Additive. Does not change channels.price, deals, escrow or fees.
Partial unique index: at most one pending offer per (buyer, lot).

Revision ID: 0066
Revises: 0065
"""
import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount_usdt", sa.Float(), nullable=False),
        sa.Column("comment", sa.String(300), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id"), nullable=True),
    )
    op.create_index("ix_price_offers_channel_id", "price_offers", ["channel_id"])
    op.create_index("ix_price_offers_buyer_id", "price_offers", ["buyer_id"])
    op.create_index("ix_price_offers_seller_id", "price_offers", ["seller_id"])
    op.create_index("ix_price_offers_status", "price_offers", ["status"])
    op.create_index("ix_price_offers_expires_at", "price_offers", ["expires_at"])
    op.create_index(
        "uq_price_offers_one_pending",
        "price_offers",
        ["buyer_id", "channel_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_price_offers_deal_id",
        "price_offers",
        ["deal_id"],
        unique=True,
        postgresql_where=sa.text("deal_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_price_offers_deal_id", table_name="price_offers")
    op.drop_index("uq_price_offers_one_pending", table_name="price_offers")
    op.drop_index("ix_price_offers_expires_at", table_name="price_offers")
    op.drop_index("ix_price_offers_status", table_name="price_offers")
    op.drop_index("ix_price_offers_seller_id", table_name="price_offers")
    op.drop_index("ix_price_offers_buyer_id", table_name="price_offers")
    op.drop_index("ix_price_offers_channel_id", table_name="price_offers")
    op.drop_table("price_offers")
