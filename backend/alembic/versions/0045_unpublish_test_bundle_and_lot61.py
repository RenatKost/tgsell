"""Task 34 (data-only, approved by owner 21.10.2026): unpublish test bundle #1
«Крипто медіа» and lot #61 (@kriptoludis, channel no longer exists).

No rows are removed. Bundle #1 -> status rejected; channel #61 -> status removed
(soft, same as admin «Зняти з біржі»). Guards on name/link make it a no-op
on any DB where those ids are different listings; re-running is a no-op too.
Channels #15-18 (members of bundle #1) are NOT touched.

Revision ID: 0045
Revises: 0044
"""
import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

BUNDLE_REASON = "Тестова сітка — знято з публікації (task 34)"
CHANNEL_REASON = "Канал @kriptoludis не існує — знято з біржі (task 34)"


def unpublish(conn) -> None:
    conn.execute(sa.text(
        "UPDATE channel_bundles SET status = 'rejected', rejection_reason = :r, "
        "moderated_at = now() AT TIME ZONE 'UTC' "
        "WHERE id = 1 AND name = 'Крипто медіа' AND status IN ('approved', 'pending')"
    ), {"r": BUNDLE_REASON})
    # Only touch channels when the target row exists: on a fresh DB the enum value
    # 'removed' (0034) is uncommitted in the same transaction and PG rejects its use.
    target = conn.execute(sa.text(
        "SELECT id FROM channels WHERE id = 61 AND lower(telegram_link) LIKE '%/kriptoludis' "
        "AND status::text IN ('approved', 'pending')"
    )).first()
    if target is None:
        return
    conn.execute(sa.text(
        "UPDATE channels SET status = 'removed', removed_at = now() AT TIME ZONE 'UTC', "
        "removed_reason = :r "
        "WHERE id = 61 AND lower(telegram_link) LIKE '%/kriptoludis' "
        "AND status IN ('approved', 'pending')"
    ), {"r": CHANNEL_REASON})


def upgrade() -> None:
    unpublish(op.get_bind())


def downgrade() -> None:
    # Data-only unpublish: intentionally not reverted automatically.
    pass
