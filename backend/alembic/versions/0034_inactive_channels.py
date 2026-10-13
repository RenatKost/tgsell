"""Inactive channels: availability-check fields + soft-remove status (additive).

Revision ID: 0034
Revises: 0033
"""
import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE channelstatus ADD VALUE IF NOT EXISTS 'removed'")
    op.add_column("channels", sa.Column("last_check_ok_at", sa.DateTime(), nullable=True))
    op.add_column("channels", sa.Column("check_error", sa.String(300), nullable=True))
    op.add_column("channels", sa.Column("check_error_at", sa.DateTime(), nullable=True))
    op.add_column("channels", sa.Column("inactive_since", sa.DateTime(), nullable=True))
    op.add_column("channels", sa.Column("removed_at", sa.DateTime(), nullable=True))
    op.add_column("channels", sa.Column("removed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("channels", sa.Column("removed_reason", sa.Text(), nullable=True))


def downgrade():
    for c in ("removed_reason", "removed_by_id", "removed_at", "inactive_since", "check_error_at",
              "check_error", "last_check_ok_at"):
        op.drop_column("channels", c)
    # enum value 'removed' stays (PostgreSQL cannot drop enum values)
