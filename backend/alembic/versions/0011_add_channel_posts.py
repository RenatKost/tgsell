"""Add channel_posts table for individual post tracking + extend channel_stats

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_msg_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(50), nullable=True),
        sa.Column("link", sa.String(255), nullable=True),
        sa.Column("views", sa.Integer(), default=0),
        sa.Column("views_1h", sa.Integer(), nullable=True),
        sa.Column("views_12h", sa.Integer(), nullable=True),
        sa.Column("views_24h", sa.Integer(), nullable=True),
        sa.Column("views_48h", sa.Integer(), nullable=True),
        sa.Column("forwards", sa.Integer(), default=0),
        sa.Column("reactions", sa.Integer(), default=0),
        sa.Column("comments", sa.Integer(), default=0),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("channel_id", "telegram_msg_id", name="uq_channel_post"),
    )
    op.create_index("ix_channel_posts_channel_date", "channel_posts", ["channel_id", "date"])

    # Extend channel_stats with additional metrics
    op.add_column("channel_stats", sa.Column("avg_forwards", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("channel_stats", sa.Column("avg_reactions", sa.Integer(), nullable=True, server_default="0"))


def downgrade() -> None:
    op.drop_column("channel_stats", "avg_reactions")
    op.drop_column("channel_stats", "avg_forwards")
    op.drop_index("ix_channel_posts_channel_date", "channel_posts")
    op.drop_table("channel_posts")
