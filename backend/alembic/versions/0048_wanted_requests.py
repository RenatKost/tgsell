"""«Шукаю канал»: wanted_requests, wanted_matches, channels.wanted_request_id.

Schema-only, no data changes.

Revision ID: 0048
Revises: 0047
"""
import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wanted_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("subs_min", sa.Integer(), nullable=True),
        sa.Column("subs_max", sa.Integer(), nullable=True),
        sa.Column("budget_min", sa.Float(), nullable=True),
        sa.Column("budget_max", sa.Float(), nullable=True),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("comment", sa.String(300), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("moderator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("moderated_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_wanted_requests_user_id", "wanted_requests", ["user_id"])
    op.create_index("ix_wanted_requests_status", "wanted_requests", ["status"])
    op.create_table(
        "wanted_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("wanted_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=True),
        sa.UniqueConstraint("request_id", "channel_id", name="uq_wanted_match"),
    )
    op.create_index("ix_wanted_matches_request_id", "wanted_matches", ["request_id"])
    op.add_column("channels", sa.Column("wanted_request_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_channels_wanted_request_id", "channels", "wanted_requests",
                          ["wanted_request_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_channels_wanted_request_id", "channels", ["wanted_request_id"])


def downgrade() -> None:
    op.drop_index("ix_channels_wanted_request_id", table_name="channels")
    op.drop_constraint("fk_channels_wanted_request_id", "channels", type_="foreignkey")
    op.drop_column("channels", "wanted_request_id")
    op.drop_table("wanted_matches")
    op.drop_table("wanted_requests")
