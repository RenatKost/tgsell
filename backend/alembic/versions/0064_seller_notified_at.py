"""paid_service_orders.seller_notified_at — idempotent «Топ увімкнено» seller alert.

Nullable. Existing paid rows are backfilled so the first deploy does not
message sellers whose Top was already activated.

Revision ID: 0064
Revises: 0063
"""
import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paid_service_orders",
        sa.Column("seller_notified_at", sa.DateTime(), nullable=True),
    )
    # Already-paid orders must not get a retroactive «Топ увімкнено» message.
    op.execute(
        "UPDATE paid_service_orders SET seller_notified_at = COALESCE(paid_at, updated_at, created_at) "
        "WHERE seller_notified_at IS NULL AND paid_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("paid_service_orders", "seller_notified_at")
