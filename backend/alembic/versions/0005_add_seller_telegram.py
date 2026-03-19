"""Add seller_telegram column to channels

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='channels' AND column_name='seller_telegram'"
    ))
    if not result.fetchone():
        op.add_column("channels", sa.Column("seller_telegram", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "seller_telegram")
