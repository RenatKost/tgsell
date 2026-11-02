"""Data: lots that carry a Top (top_source set) but have no top_until get
top_until = (first_approved_at | moderated_at | created_at) + 7 days. Idempotent: only NULL rows.

Revision ID: 0060
Revises: 0059
"""
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

SQL = (
    "UPDATE channels SET top_until = COALESCE(first_approved_at, moderated_at, created_at) + INTERVAL '7 days' "
    "WHERE top_source IS NOT NULL AND top_until IS NULL "
    "AND COALESCE(first_approved_at, moderated_at, created_at) IS NOT NULL"
)


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    pass  # data backfill: nothing to undo
