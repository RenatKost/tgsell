"""Add channel_bundles and bundle_channels tables, bundle_id on deals.

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade() -> None:
    op.create_table(
        "channel_bundles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("moderator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("monthly_income", sa.Float(), nullable=True),
        sa.Column("resources", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", "sold", name="bundlestatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("moderated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "bundle_channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "bundle_id",
            sa.Integer(),
            sa.ForeignKey("channel_bundles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel_id",
            sa.Integer(),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer(), default=0),
        sa.UniqueConstraint("bundle_id", "channel_id", name="uq_bundle_channel"),
    )

    op.add_column(
        "deals",
        sa.Column(
            "bundle_id",
            sa.Integer(),
            sa.ForeignKey("channel_bundles.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("deals", "bundle_id")
    op.drop_table("bundle_channels")
    op.drop_table("channel_bundles")
    op.execute("DROP TYPE IF EXISTS bundlestatus")
