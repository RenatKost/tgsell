"""Deal transfer checklist items + reminder dedup fields on deals

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # side is VARCHAR + CHECK (no new PG enum type → nothing to ALTER TYPE).
    op.create_table(
        "deal_checklist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "deal_id",
            sa.Integer(),
            sa.ForeignKey("deals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("done", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "done_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.Column("auto_verified", sa.Boolean(), nullable=True),
        sa.Column("auto_note", sa.Text(), nullable=True),
        sa.Column("auto_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("deal_id", "key", name="uq_deal_checklist_deal_key"),
        sa.CheckConstraint("side IN ('seller', 'buyer')", name="ck_deal_checklist_side"),
    )
    op.create_index(
        "ix_deal_checklist_items_deal_id", "deal_checklist_items", ["deal_id"]
    )

    op.add_column("deals", sa.Column("checklist_started_at", sa.DateTime(), nullable=True))
    op.add_column("deals", sa.Column("last_checklist_activity_at", sa.DateTime(), nullable=True))
    op.add_column("deals", sa.Column("reminder_6h_sent_at", sa.DateTime(), nullable=True))
    op.add_column("deals", sa.Column("reminder_24h_sent_at", sa.DateTime(), nullable=True))
    op.add_column("deals", sa.Column("admin_alert_48h_sent_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "admin_alert_48h_sent_at")
    op.drop_column("deals", "reminder_24h_sent_at")
    op.drop_column("deals", "reminder_6h_sent_at")
    op.drop_column("deals", "last_checklist_activity_at")
    op.drop_column("deals", "checklist_started_at")
    op.drop_index("ix_deal_checklist_items_deal_id", table_name="deal_checklist_items")
    op.drop_table("deal_checklist_items")
