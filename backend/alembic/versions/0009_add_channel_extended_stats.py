"""Add extended channel stats columns: total_posts, post_frequency, last_post_date, avg_forwards, avg_reactions

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("total_posts", sa.Integer(), nullable=True))
    op.add_column("channels", sa.Column("post_frequency", sa.Float(), nullable=True))
    op.add_column("channels", sa.Column("last_post_date", sa.DateTime(), nullable=True))
    op.add_column("channels", sa.Column("avg_forwards", sa.Integer(), nullable=True))
    op.add_column("channels", sa.Column("avg_reactions", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "avg_reactions")
    op.drop_column("channels", "avg_forwards")
    op.drop_column("channels", "last_post_date")
    op.drop_column("channels", "post_frequency")
    op.drop_column("channels", "total_posts")
