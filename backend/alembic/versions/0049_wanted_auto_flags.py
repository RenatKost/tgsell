"""«Шукаю канал»: auto-check flags for moderators (no longer block creation).

Revision ID: 0049
Revises: 0048
"""
import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wanted_requests", sa.Column("auto_flags", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("wanted_requests", "auto_flags")
