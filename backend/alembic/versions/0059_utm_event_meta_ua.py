"""utm_events: meta (JSONB, whitelisted keys e.g. auto) + ua_class (like utm_visits).

Revision ID: 0059
Revises: 0058
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("utm_events", sa.Column(
        "meta", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True))
    op.add_column("utm_events", sa.Column("ua_class", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("utm_events", "ua_class")
    op.drop_column("utm_events", "meta")
