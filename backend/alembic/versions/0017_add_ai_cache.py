"""add ai_cache to channels and bundles

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("ai_cache", sa.Text(), nullable=True))
    op.add_column("channels", sa.Column("ai_cache_updated_at", sa.DateTime(), nullable=True))
    op.add_column("channel_bundles", sa.Column("ai_cache", sa.Text(), nullable=True))
    op.add_column("channel_bundles", sa.Column("ai_cache_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "ai_cache")
    op.drop_column("channels", "ai_cache_updated_at")
    op.drop_column("channel_bundles", "ai_cache")
    op.drop_column("channel_bundles", "ai_cache_updated_at")
