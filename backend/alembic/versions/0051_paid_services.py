"""Paid seller services (Топ / пост у каналі / Перевірено TgSell) + app_settings.

Revision ID: 0051
Revises: 0050
"""
import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.add_column("channels", sa.Column("top_until", sa.DateTime(), nullable=True))
    op.add_column("channels", sa.Column("tgsell_verified", sa.Boolean(), nullable=False, server_default="false"))
    op.create_table(
        "paid_service_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("price_usdt", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="awaiting_payment"),
        sa.Column("escrow_wallet_address", sa.String(100), nullable=False),
        sa.Column("escrow_private_key_encrypted", sa.Text(), nullable=False),
        sa.Column("received_usdt", sa.Float(), nullable=True),
        sa.Column("payment_deadline_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("active_until", sa.DateTime(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("handled_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    for col in ("kind", "channel_id", "seller_id", "status"):
        op.create_index(f"ix_paid_service_orders_{col}", "paid_service_orders", [col])


def downgrade() -> None:
    for col in ("kind", "channel_id", "seller_id", "status"):
        op.drop_index(f"ix_paid_service_orders_{col}", table_name="paid_service_orders")
    op.drop_table("paid_service_orders")
    op.drop_column("channels", "tgsell_verified")
    op.drop_column("channels", "top_until")
    op.drop_table("app_settings")
