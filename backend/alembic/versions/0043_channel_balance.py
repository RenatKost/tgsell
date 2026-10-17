"""Task 31: seller-stated Telegram Stars / TON balance on channels + deal snapshot.

Revision ID: 0043
Revises: 0042
"""
import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("stars_balance", sa.Integer(), nullable=True))
    op.add_column("channels", sa.Column("ton_balance", sa.Numeric(20, 9), nullable=True))
    op.create_check_constraint(
        "ck_channels_stars_balance_nonneg", "channels", "stars_balance IS NULL OR stars_balance >= 0"
    )
    op.create_check_constraint(
        "ck_channels_ton_balance_nonneg", "channels", "ton_balance IS NULL OR ton_balance >= 0"
    )
    # Snapshot at deal creation (NULL for all existing deals → no balance checklist item).
    op.add_column("deals", sa.Column("balance_stars", sa.Integer(), nullable=True))
    op.add_column("deals", sa.Column("balance_ton", sa.Numeric(20, 9), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "balance_ton")
    op.drop_column("deals", "balance_stars")
    op.drop_constraint("ck_channels_ton_balance_nonneg", "channels", type_="check")
    op.drop_constraint("ck_channels_stars_balance_nonneg", "channels", type_="check")
    op.drop_column("channels", "ton_balance")
    op.drop_column("channels", "stars_balance")
