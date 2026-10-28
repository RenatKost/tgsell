"""UTM tracking: utm_visits + utm_* on users / channels / channel_bundles.

Revision ID: 0057
Revises: 0056
"""
import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

_TABLES = ("users", "channels", "channel_bundles")
_COLS = ("utm_source", "utm_campaign", "utm_content")


def upgrade() -> None:
    op.create_table(
        "utm_visits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("anon_hash", sa.String(32), nullable=True),
        sa.Column("utm_source", sa.String(64), nullable=True),
        sa.Column("utm_campaign", sa.String(64), nullable=True),
        sa.Column("utm_content", sa.String(64), nullable=True),
        sa.Column("path", sa.String(128), nullable=True),
        sa.Column("ua_class", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_utm_visits_anon_hash", "utm_visits", ["anon_hash"])
    op.create_index("ix_utm_visits_utm_campaign", "utm_visits", ["utm_campaign"])
    op.create_index("ix_utm_visits_created_at", "utm_visits", ["created_at"])
    for t in _TABLES:
        for c in _COLS:
            op.add_column(t, sa.Column(c, sa.String(64), nullable=True))


def downgrade() -> None:
    for t in _TABLES:
        for c in _COLS:
            op.drop_column(t, c)
    op.drop_table("utm_visits")
