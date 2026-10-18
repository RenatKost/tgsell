"""Weekly admin report: scheduled_report_runs (idempotency log, one row per period).

Revision ID: 0044
Revises: 0043
"""
import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_report_runs",
        sa.Column("report_key", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("scheduled_report_runs")
