"""Task 22: channel quality index.

* channels.quality_score / quality_health / quality_breakdown / quality_updated_at
* channel_quality_history (score + health + breakdown per recompute)

Revision ID: 0039
Revises: 0038
"""
import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("quality_score", sa.Integer(), nullable=True))
    op.add_column("channels", sa.Column("quality_health", sa.String(20), nullable=True))
    op.add_column("channels", sa.Column("quality_breakdown", sa.JSON(), nullable=True))
    op.add_column("channels", sa.Column("quality_updated_at", sa.DateTime(), nullable=True))
    op.create_index("ix_channels_quality_score", "channels", ["quality_score"])
    op.create_table(
        "channel_quality_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("health", sa.String(20), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=True),
    )
    op.create_index("ix_channel_quality_history_channel_id", "channel_quality_history", ["channel_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_quality_history_channel_id", table_name="channel_quality_history")
    op.drop_table("channel_quality_history")
    op.drop_index("ix_channels_quality_score", table_name="channels")
    for c in ("quality_updated_at", "quality_breakdown", "quality_health", "quality_score"):
        op.drop_column("channels", c)
