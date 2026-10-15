"""Task 23: user activity events + sessions (admin «Користувачі», funnel).

Revision ID: 0040
Revises: 0039
"""
import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("anon_id", sa.String(32), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("object_type", sa.String(16), nullable=True),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("page", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_events_created", "user_events", ["created_at"])
    op.create_index("ix_user_events_user_created", "user_events", ["user_id", "created_at"])
    op.create_index("ix_user_events_type_created", "user_events", ["event_type", "created_at"])
    op.create_index("ix_user_events_anon_id", "user_events", ["anon_id"])
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_key", sa.String(32), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("anon_id", sa.String(32), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("active_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("heartbeats", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index("ix_user_sessions_user_last", "user_sessions", ["user_id", "last_seen_at"])
    op.create_index("ix_user_sessions_last", "user_sessions", ["last_seen_at"])


def downgrade() -> None:
    op.drop_table("user_sessions")
    op.drop_table("user_events")
