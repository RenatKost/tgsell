"""«Приведи продавця»: the free «Перевірено TgSell» badge is no longer a referral reward.

Data-only migration:
* revokes ``channels.tgsell_verified`` ONLY on lots that got it as a referral reward
  (``referral_rewards.status='applied'`` → ``awarded_channel_id``), and only if that lot has no paid
  «Перевірено» order of its own (paid / in_review / verified);
* those reward rows (and every unused ``credit`` row) become a Top credit (``status='credit'``):
  the referrer gets a free 7-day «Топ» on their next approved lot instead.

Revision ID: 0056
Revises: 0055
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT r.id, r.awarded_channel_id FROM referral_rewards r WHERE r.status = 'applied'")).fetchall()
    removed = 0
    for rid, cid in rows:
        if cid is not None:
            paid = bind.execute(sa.text(
                "SELECT 1 FROM paid_service_orders WHERE channel_id = :c AND kind = 'verified' "
                "AND status IN ('paid', 'in_review', 'verified') LIMIT 1"), {"c": cid}).first()
            if paid is None:
                res = bind.execute(sa.text(
                    "UPDATE channels SET tgsell_verified = false WHERE id = :c AND tgsell_verified = true"), {"c": cid})
                removed += res.rowcount or 0
        bind.execute(sa.text(
            "UPDATE referral_rewards SET status = 'credit', awarded_channel_id = NULL, applied_at = NULL "
            "WHERE id = :r"), {"r": rid})
    credits = bind.execute(sa.text("SELECT COUNT(*) FROM referral_rewards WHERE status = 'credit'")).scalar() or 0
    log.info(f"[0056] referral badges removed: {removed}; badge rewards converted: {len(rows)}; "
             f"Top credits now: {credits}")


def downgrade() -> None:
    pass  # data migration: revoked badges are not restored
