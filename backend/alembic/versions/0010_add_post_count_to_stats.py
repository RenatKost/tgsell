"""Add post_count column to channel_stats for daily posting frequency chart

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channel_stats", sa.Column("post_count", sa.Integer(), nullable=True, server_default="0"))


def downgrade() -> None:
    op.drop_column("channel_stats", "post_count")
