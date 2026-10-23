"""Add channels.buyer_warning (admin-set warning shown to buyers).

Schema-only, nullable, no data changes.

Revision ID: 0046
Revises: 0045
"""
import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("buyer_warning", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "buyer_warning")
