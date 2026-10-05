"""Add payout_in_progress to DealStatus enum (payout race guard)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL native ENUM (dealstatus) — same pattern as 0008 awaiting_payout.
    # IF NOT EXISTS keeps re-runs safe; value is not removable in a simple downgrade.
    op.execute(
        "ALTER TYPE dealstatus ADD VALUE IF NOT EXISTS "
        "'payout_in_progress' AFTER 'awaiting_payout'"
    )


def downgrade() -> None:
    # Postgres cannot DROP a single enum value safely without recreating the type.
    pass
