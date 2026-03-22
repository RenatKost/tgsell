"""Add Google auth fields to users

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check which columns already exist
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='users'"
    ))
    existing = {row[0] for row in result}

    if "google_id" not in existing:
        op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
        op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)

    if "email" not in existing:
        op.add_column("users", sa.Column("email", sa.String(255), nullable=True))
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Make telegram_id nullable (users can now sign up via Google only)
    op.alter_column("users", "telegram_id", nullable=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "email")
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_column("users", "google_id")
    op.alter_column("users", "telegram_id", nullable=False)
