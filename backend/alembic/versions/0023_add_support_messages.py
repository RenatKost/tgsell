"""Support inbox messages table

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # direction is VARCHAR + CHECK (no new PG enum type).
    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("is_urgent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("handled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column(
            "reply_to_id",
            sa.Integer(),
            sa.ForeignKey("support_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("direction IN ('in', 'out')", name="ck_support_messages_direction"),
    )
    op.create_index("ix_support_messages_telegram_user_id", "support_messages", ["telegram_user_id"])
    op.create_index("ix_support_messages_handled", "support_messages", ["handled"])
    op.create_index("ix_support_messages_created_at", "support_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_support_messages_created_at", table_name="support_messages")
    op.drop_index("ix_support_messages_handled", table_name="support_messages")
    op.drop_index("ix_support_messages_telegram_user_id", table_name="support_messages")
    op.drop_table("support_messages")
