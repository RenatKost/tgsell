"""auctions.deleted_at — admin soft-delete (keep row and bids).

Additive and safe: nullable timestamp, existing rows stay visible (NULL).

Revision ID: 0062
Revises: 0061
"""
import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auctions", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_auctions_deleted_at", "auctions", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_auctions_deleted_at", table_name="auctions")
    op.drop_column("auctions", "deleted_at")
