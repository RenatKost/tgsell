"""UTM funnel events: utm_events (login_click, form_start, form_submit_attempt, bot_start, login_success).

Revision ID: 0058
Revises: 0057
"""
import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "utm_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("anon_hash", sa.String(32), nullable=True),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("utm_source", sa.String(64), nullable=True),
        sa.Column("utm_campaign", sa.String(64), nullable=True),
        sa.Column("utm_content", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_utm_events_anon_hash", "utm_events", ["anon_hash"])
    op.create_index("ix_utm_events_event", "utm_events", ["event"])
    op.create_index("ix_utm_events_utm_campaign", "utm_events", ["utm_campaign"])
    op.create_index("ix_utm_events_created_at", "utm_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("utm_events")
