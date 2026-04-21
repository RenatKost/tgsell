"""Add telethon_sessions table for persistent session storage.

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.create_table(
        "telethon_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_string", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("telethon_sessions")
