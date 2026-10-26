"""Seller promo: free «Топ» on first approval (channels.first_approved_at, channels.top_source).

Backfill: every lot that was already approved at least once (status approved/sold/removed or an
audited channel.approve) gets first_approved_at, so the promo is never applied retroactively.

Revision ID: 0054
Revises: 0053
"""
import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("first_approved_at", sa.DateTime(), nullable=True))
    op.add_column("channels", sa.Column("top_source", sa.String(20), nullable=True))
    op.execute(
        "UPDATE channels SET first_approved_at = COALESCE(moderated_at, created_at, now() AT TIME ZONE 'utc') "
        "WHERE CAST(status AS TEXT) IN ('approved', 'sold', 'removed') OR id IN ("
        "SELECT target_id FROM admin_audit_log WHERE action = 'channel.approve' AND target_id IS NOT NULL)"
    )
    op.execute("UPDATE channels SET top_source = 'paid' WHERE top_until IS NOT NULL")


def downgrade() -> None:
    op.drop_column("channels", "top_source")
    op.drop_column("channels", "first_approved_at")
