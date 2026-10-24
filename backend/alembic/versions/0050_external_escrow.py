"""«Гарант для зовнішніх угод»: private external escrow offers + deals.external_channel_link.

Revision ID: 0050
Revises: 0049
"""
import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("external_channel_link", sa.String(255), nullable=True))
    op.create_table(
        "external_escrow_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel_link", sa.String(255), nullable=False),
        sa.Column("price_usdt", sa.Float(), nullable=False),
        sa.Column("fee_percent", sa.Float(), nullable=False),
        sa.Column("service_fee", sa.Float(), nullable=False),
        sa.Column("buyer_username", sa.String(64), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_external_escrow_offers_seller_id", "external_escrow_offers", ["seller_id"])
    op.create_index("ix_external_escrow_offers_token", "external_escrow_offers", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_external_escrow_offers_token", table_name="external_escrow_offers")
    op.drop_index("ix_external_escrow_offers_seller_id", table_name="external_escrow_offers")
    op.drop_table("external_escrow_offers")
    op.drop_column("deals", "external_channel_link")
