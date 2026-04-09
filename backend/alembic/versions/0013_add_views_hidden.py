"""Add views_hidden boolean to channels

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.add_column("channels", sa.Column("views_hidden", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("channels", "views_hidden")
