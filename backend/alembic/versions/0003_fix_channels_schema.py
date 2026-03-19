"""Add moderated_at column to channels, fix column types

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add moderated_at if not exists
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='channels' AND column_name='moderated_at'"
    ))
    if not result.fetchone():
        op.add_column("channels", sa.Column("moderated_at", sa.DateTime(), nullable=True))

    # Fix daily_growth type if needed
    result = conn.execute(sa.text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='channels' AND column_name='daily_growth'"
    ))
    row = result.fetchone()
    if row and row[0] == 'double precision':
        op.alter_column("channels", "daily_growth",
                        type_=sa.Integer(),
                        existing_type=sa.Float(),
                        existing_nullable=True)

    # Fix age type if needed
    result = conn.execute(sa.text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='channels' AND column_name='age'"
    ))
    row = result.fetchone()
    if row and row[0] == 'integer':
        op.alter_column("channels", "age",
                        type_=sa.String(100),
                        existing_type=sa.Integer(),
                        existing_nullable=True,
                        postgresql_using="age::varchar")

    # Add recorded_at to channel_stats if not exists
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='channel_stats' AND column_name='recorded_at'"
    ))
    if not result.fetchone():
        op.add_column("channel_stats", sa.Column("recorded_at", sa.DateTime(), server_default=sa.func.now(), nullable=True))


def downgrade() -> None:
    op.drop_column("channel_stats", "recorded_at")
    op.alter_column("channels", "age",
                    type_=sa.Integer(),
                    existing_type=sa.String(100),
                    existing_nullable=True,
                    postgresql_using="NULL")
    op.alter_column("channels", "daily_growth",
                    type_=sa.Float(),
                    existing_type=sa.Integer(),
                    existing_nullable=True)
    op.drop_column("channels", "moderated_at")
