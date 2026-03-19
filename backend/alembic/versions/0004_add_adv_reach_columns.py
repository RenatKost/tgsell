"""Add adv_reach columns to channels

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    for col in ("adv_reach_12h", "adv_reach_24h", "adv_reach_48h"):
        result = conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name='channels' AND column_name='{col}'"
        ))
        if not result.fetchone():
            op.add_column("channels", sa.Column(col, sa.Integer(), nullable=True))


def downgrade() -> None:
    for col in ("adv_reach_48h", "adv_reach_24h", "adv_reach_12h"):
        op.drop_column("channels", col)
