"""deal_messages.as_guarantor — staff message posted explicitly as the TgSell guarantor.

Additive and safe: NOT NULL with server default false (metadata-only on PG 11+),
existing rows keep their current display (party > staff priority).

Revision ID: 0061
Revises: 0060
"""
import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deal_messages", sa.Column(
        "as_guarantor", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("deal_messages", "as_guarantor")
