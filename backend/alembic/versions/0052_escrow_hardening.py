"""External escrow: bind invite to buyer telegram_id; paid services: fee sweep state + one-shot partial alert.

Revision ID: 0052
Revises: 0051
"""
import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

_SWEEP_COLS = (
    ("sweep_status", sa.String(20)),
    ("sweep_tx_hash", sa.String(100)),
    ("sweep_amount_units", sa.BigInteger()),
    ("sweep_gas_tx_hash", sa.String(100)),
    ("sweep_energy_order_id", sa.String(100)),
    ("sweep_broadcast_at", sa.DateTime()),
    ("sweep_finalized_at", sa.DateTime()),
    ("sweep_reason", sa.Text()),
    ("partial_alerted_at", sa.DateTime()),
)


def upgrade() -> None:
    op.add_column("external_escrow_offers", sa.Column("buyer_telegram_id", sa.BigInteger(), nullable=True))
    for name, type_ in _SWEEP_COLS:
        op.add_column("paid_service_orders", sa.Column(name, type_, nullable=True))
    op.add_column("paid_service_orders",
                  sa.Column("sweep_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_paid_service_orders_sweep_status", "paid_service_orders", ["sweep_status"])


def downgrade() -> None:
    op.drop_index("ix_paid_service_orders_sweep_status", table_name="paid_service_orders")
    op.drop_column("paid_service_orders", "sweep_attempts")
    for name, _ in reversed(_SWEEP_COLS):
        op.drop_column("paid_service_orders", name)
    op.drop_column("external_escrow_offers", "buyer_telegram_id")
