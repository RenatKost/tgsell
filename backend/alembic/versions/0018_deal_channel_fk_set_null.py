"""deals.channel_id FK: add ON DELETE SET NULL so deleting a channel with
a (cancelled/completed) deal history no longer fails with a 500 error.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    constraint_name = conn.execute(
        sa.text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = 'deals'
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'channel_id'
            """
        )
    ).scalar()

    if constraint_name:
        op.drop_constraint(constraint_name, "deals", type_="foreignkey")

    op.create_foreign_key(
        "deals_channel_id_fkey",
        "deals",
        "channels",
        ["channel_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("deals_channel_id_fkey", "deals", type_="foreignkey")
    op.create_foreign_key(
        "deals_channel_id_fkey",
        "deals",
        "channels",
        ["channel_id"],
        ["id"],
    )
