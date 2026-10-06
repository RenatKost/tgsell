"""Support replies: delivery status + idempotency key (no duplicate sends on retry)

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-06

All new columns are nullable or have a server default, so existing rows stay
valid: legacy rows get delivery_status NULL, send_attempts 0.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("support_messages", sa.Column("delivery_status", sa.String(16), nullable=True))
    op.add_column("support_messages", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column("support_messages", sa.Column("sent_at", sa.DateTime(), nullable=True))
    op.add_column("support_messages", sa.Column("telegram_message_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "support_messages",
        sa.Column("send_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("support_messages", sa.Column("last_error", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_support_messages_delivery_status",
        "support_messages",
        "delivery_status IS NULL OR delivery_status IN ('sending', 'sent', 'failed')",
    )
    # Unique among non-NULL keys (Postgres allows many NULLs in a unique constraint).
    op.create_unique_constraint(
        "uq_support_messages_idempotency_key", "support_messages", ["idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_support_messages_idempotency_key", "support_messages", type_="unique")
    op.drop_constraint("ck_support_messages_delivery_status", "support_messages", type_="check")
    op.drop_column("support_messages", "last_error")
    op.drop_column("support_messages", "send_attempts")
    op.drop_column("support_messages", "telegram_message_id")
    op.drop_column("support_messages", "sent_at")
    op.drop_column("support_messages", "idempotency_key")
    op.drop_column("support_messages", "delivery_status")
