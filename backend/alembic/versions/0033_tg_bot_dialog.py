"""Alerts-bot dialog state on users (additive).

Revision ID: 0033
Revises: 0032
"""
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("tg_bot_started_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("tg_bot_unreachable_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("users", "tg_bot_unreachable_at")
    op.drop_column("users", "tg_bot_started_at")
