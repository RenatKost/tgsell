"""Close the stale GAS_TOPUP_UNCONFIRMED release record of deal #29 (data-only, idempotent).

The release of deal #29 actually succeeded on-chain (tx bbb3b463…); an earlier attempt's
job row stayed as a failed/queued GAS_TOPUP_UNCONFIRMED record in the payout queue.
Scope: ONLY transactions of deal 29, type=release, WITHOUT tx_hash (never broadcast), whose
receipt status/reason mentions GAS_TOPUP_UNCONFIRMED — and only when the deal's successful
payout tx bbb3b463… is recorded. Deals, escrow balances, other rows: untouched.
Marked receipt_status='SUPERSEDED' (status=failed), hidden from the failed list.

Revision ID: 0035
Revises: 0034
"""
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

CLOSE_SQL = """
UPDATE transactions t
SET status = 'failed',
    receipt_status = 'SUPERSEDED',
    receipt_reason = 'Закрито (міграція 0035): виплату угоди #29 виконано успішно, tx '
                     || (SELECT COALESCE(d.payout_tx_hash, '') FROM deals d WHERE d.id = 29)
                     || '. Попередня спроба: ' || COALESCE(t.receipt_reason, t.receipt_status, ''),
    finalized_at = COALESCE(t.finalized_at, (now() AT TIME ZONE 'UTC'))
WHERE t.deal_id = 29
  AND t.type = 'release'
  AND t.tx_hash IS NULL
  AND t.status IN ('failed', 'pending')
  AND COALESCE(t.receipt_status, '') <> 'SUPERSEDED'
  AND (t.receipt_status = 'GAS_TOPUP_UNCONFIRMED' OR t.receipt_reason LIKE '%GAS_TOPUP_UNCONFIRMED%'
       OR t.receipt_reason LIKE '%Газ-поповнення%не підтверд%' OR t.receipt_reason LIKE '%газ-поповнення ще не підтверджене%')
  AND (
    EXISTS (SELECT 1 FROM deals d WHERE d.id = 29 AND d.payout_tx_hash LIKE 'bbb3b463%')
    OR EXISTS (SELECT 1 FROM transactions s WHERE s.deal_id = 29 AND s.type = 'release'
               AND s.status = 'confirmed' AND s.tx_hash LIKE 'bbb3b463%')
  )
"""


def upgrade():
    op.execute(CLOSE_SQL)


def downgrade():
    pass  # data fix; intentionally not reverted
