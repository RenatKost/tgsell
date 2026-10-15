"""Honest channel-stats time series (Task 20).

* channel_stats.subscribers / er become NULLable (NULL = unknown);
* dedupe rows per (channel_id, day) — keep the most recently recorded one —
  then normalize ``date`` to 00:00 and add UNIQUE (channel_id, date);
* clear fake retro subscribers / ER (current subscribers written into past
  dates): per channel keep only the latest real snapshot;
* channels.growth_7d / growth_30d (daily_growth already exists).

Downgrade restores the schema only; cleared values are not restored.

Revision ID: 0038
Revises: 0037
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def _report(msg: str) -> None:
    log.info(msg)
    print(msg, flush=True)


def upgrade() -> None:
    conn = op.get_bind()

    op.alter_column("channel_stats", "subscribers", existing_type=sa.Integer(), nullable=True, server_default=None)
    op.alter_column("channel_stats", "er", existing_type=sa.Float(), nullable=True, server_default=None)
    op.add_column("channels", sa.Column("growth_7d", sa.Integer(), nullable=True))
    op.add_column("channels", sa.Column("growth_30d", sa.Integer(), nullable=True))

    deleted = conn.execute(sa.text("""
        DELETE FROM channel_stats cs
        USING (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY channel_id, date_trunc('day', date)
                ORDER BY recorded_at DESC NULLS LAST, id DESC
            ) AS rn
            FROM channel_stats
        ) d
        WHERE cs.id = d.id AND d.rn > 1
    """)).rowcount

    normalized = conn.execute(sa.text("""
        UPDATE channel_stats SET date = date_trunc('day', date)
        WHERE date <> date_trunc('day', date)
    """)).rowcount

    cleared = conn.execute(sa.text("""
        UPDATE channel_stats cs SET subscribers = NULL, er = NULL
        WHERE (cs.subscribers IS NOT NULL OR cs.er IS NOT NULL)
          AND cs.id NOT IN (
            SELECT DISTINCT ON (channel_id) id FROM channel_stats
            WHERE subscribers IS NOT NULL AND subscribers > 0
            ORDER BY channel_id, date DESC, recorded_at DESC NULLS LAST, id DESC
          )
    """)).rowcount

    op.create_unique_constraint("uq_channel_stats_channel_date", "channel_stats", ["channel_id", "date"])

    _report(
        f"[0038] channel_stats: deduped(deleted)={deleted} date_normalized={normalized} "
        f"fake_subscribers_cleared={cleared}"
    )


def downgrade() -> None:
    op.drop_constraint("uq_channel_stats_channel_date", "channel_stats", type_="unique")
    op.drop_column("channels", "growth_30d")
    op.drop_column("channels", "growth_7d")
    op.execute("UPDATE channel_stats SET subscribers = 0 WHERE subscribers IS NULL")
    op.execute("UPDATE channel_stats SET er = 0 WHERE er IS NULL")
    op.alter_column("channel_stats", "subscribers", existing_type=sa.Integer(), nullable=False)
    op.alter_column("channel_stats", "er", existing_type=sa.Float(), nullable=False)
