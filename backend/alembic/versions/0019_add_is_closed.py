"""Add is_closed boolean to channels (closed/join-request channels)

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"


def upgrade() -> None:
    op.add_column("channels", sa.Column("is_closed", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("channels", "is_closed")
