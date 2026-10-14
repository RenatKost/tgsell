"""Payout energy source + receipt costs (Task 18, CatFee energy rental). Additive, nullable.

Revision ID: 0036
Revises: 0035
"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

COLS = (
    ("energy_source", sa.String(20)),
    ("energy_order_id", sa.String(100)),
    ("energy_rent_sun", sa.BigInteger()),
    ("fee_sun", sa.BigInteger()),
    ("energy_fee_sun", sa.BigInteger()),
    ("energy_used", sa.BigInteger()),
)


def upgrade() -> None:
    for name, type_ in COLS:
        op.add_column("transactions", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLS):
        op.drop_column("transactions", name)
