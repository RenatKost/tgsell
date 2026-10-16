"""Visit attribution: utm_* + referer domain on user_events (no PII).

Revision ID: 0042
Revises: 0041
"""
import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

_COLS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref_domain")


def upgrade() -> None:
    for c in _COLS:
        op.add_column("user_events", sa.Column(c, sa.String(64), nullable=True))


def downgrade() -> None:
    for c in reversed(_COLS):
        op.drop_column("user_events", c)
