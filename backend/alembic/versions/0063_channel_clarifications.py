"""needs_clarification status + channel_clarifications history.

ADD VALUE runs outside the migration transaction (PostgreSQL forbids
ALTER TYPE ... ADD VALUE inside a transaction). The table is created after.

Revision ID: 0063
Revises: 0062
"""
import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE channelstatus ADD VALUE IF NOT EXISTS 'needs_clarification'")
    op.create_table(
        "channel_clarifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("asked_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("asked_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.Column("answered_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("channel_clarifications")
    # enum value 'needs_clarification' stays (PostgreSQL cannot drop enum values)
