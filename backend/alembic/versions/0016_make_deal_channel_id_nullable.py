"""make deal channel_id nullable for bundle deals

Revision ID: 0016
Revises: 0015
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("deals", "channel_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("deals", "channel_id", existing_type=sa.Integer(), nullable=False)
