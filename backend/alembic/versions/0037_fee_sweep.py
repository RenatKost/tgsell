"""Fee sweep to treasury (Task 19): transactiontype 'fee_sweep' + deals.sweep_status.

Backfill: historical deals that are already eligible (completed with a confirmed SUCCESS
release / cancelled with a confirmed refund, no open overpay, not legacy #3/#6/#29) are
marked 'pending_sweep' — NOT auto-sent; the admin "Зібрати все" button collects them.

Revision ID: 0037
Revises: 0036
"""
import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'fee_sweep'")
    op.add_column("deals", sa.Column("sweep_status", sa.String(20), nullable=True))
    op.execute("""
        UPDATE deals d SET sweep_status = 'pending_sweep'
        WHERE d.id NOT IN (3, 6, 29)
          AND d.payout_tx_hash IS NOT NULL
          AND (d.overpay_status IS NULL OR d.overpay_status = 'done')
          AND (
            (d.status::text = 'completed' AND EXISTS (
               SELECT 1 FROM transactions t WHERE t.deal_id = d.id AND t.type::text = 'release'
                 AND t.tx_hash = d.payout_tx_hash AND t.status::text = 'confirmed' AND t.receipt_status = 'SUCCESS'))
            OR
            (d.status::text = 'cancelled' AND EXISTS (
               SELECT 1 FROM transactions t WHERE t.deal_id = d.id AND t.type::text = 'refund'
                 AND t.tx_hash = d.payout_tx_hash AND t.status::text = 'confirmed' AND t.receipt_status = 'SUCCESS'))
          )
          AND NOT EXISTS (
            SELECT 1 FROM transactions t WHERE t.deal_id = d.id AND t.status::text = 'pending'
              AND t.type::text IN ('release', 'refund', 'fee_collection', 'sweep', 'overpay_refund'))
    """)


def downgrade() -> None:
    op.drop_column("deals", "sweep_status")
    # enum value 'fee_sweep' is left in place (PostgreSQL cannot drop enum values).
