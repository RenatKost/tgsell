"""seller_notifications — outbox for seller alerts about admin actions on a lot.

Additive: new table only. Nothing existing is altered and no rows are backfilled,
so the deploy itself sends nothing.

Revision ID: 0067
Revises: 0066
"""
import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seller_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_seller_notifications_user_id", "seller_notifications", ["user_id"])
    op.create_index("ix_seller_notifications_channel_id", "seller_notifications", ["channel_id"])
    op.create_index(
        "ix_seller_notifications_due", "seller_notifications", ["next_attempt_at"],
        postgresql_where=sa.text("sent_at IS NULL AND failed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_seller_notifications_due", table_name="seller_notifications")
    op.drop_index("ix_seller_notifications_channel_id", table_name="seller_notifications")
    op.drop_index("ix_seller_notifications_user_id", table_name="seller_notifications")
    op.drop_table("seller_notifications")
