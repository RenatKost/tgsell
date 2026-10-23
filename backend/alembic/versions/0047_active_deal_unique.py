"""Partial unique indexes: at most one active (non-terminal) deal per channel / bundle.

Schema-only (indexes), no data changes. If legacy duplicates exist the index for
that column is skipped with a warning instead of failing the deploy; the
application-level row-lock (FOR-UPDATE) checks still apply.

Revision ID: 0047
Revises: 0046
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.0047")

ACTIVE = ("created", "payment_pending", "paid", "channel_transferring",
          "disputed", "awaiting_payout", "payout_in_progress")
WHERE = "status IN (" + ", ".join(f"'{s}'" for s in ACTIVE) + ")"
INDEXES = (("uq_deals_active_channel", "channel_id"), ("uq_deals_active_bundle", "bundle_id"))


def upgrade() -> None:
    bind = op.get_bind()
    for name, col in INDEXES:
        dup = bind.execute(sa.text(
            f"SELECT {col} FROM deals WHERE {col} IS NOT NULL AND {WHERE} GROUP BY {col} HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
        if dup is not None:
            log.warning("0047: duplicate active deals on %s=%s — skipping %s", col, dup[0], name)
            continue
        op.create_index(name, "deals", [col], unique=True,
                        postgresql_where=sa.text(f"{col} IS NOT NULL AND {WHERE}"))


def downgrade() -> None:
    for name, _ in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
