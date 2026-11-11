"""Index user_events (event_type, object_id, created_at) for seller lot-view aggregates.

CREATE INDEX CONCURRENTLY cannot run inside a transaction, so both upgrade
and downgrade use autocommit_block. Safe to re-run (IF NOT EXISTS / IF EXISTS).

Revision ID: 0065
Revises: 0064
"""
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

INDEX = "ix_user_events_type_object_created"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} "
            "ON user_events (event_type, object_id, created_at)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
