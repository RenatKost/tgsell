"""«Приведи продавця»: users.ref_code / referred_by_id, channels.referrer_id, referral_rewards.

Revision ID: 0055
Revises: 0054
"""
import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ref_code", sa.String(16), nullable=True))
    op.create_index("ix_users_ref_code", "users", ["ref_code"], unique=True)
    op.add_column("users", sa.Column("referred_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("channels", sa.Column("referrer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("referred_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("awarded_channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("referred_user_id", name="uq_referral_rewards_referred_user"),
    )


def downgrade() -> None:
    op.drop_table("referral_rewards")
    op.drop_column("channels", "referrer_id")
    op.drop_column("users", "referred_by_id")
    op.drop_index("ix_users_ref_code", table_name="users")
    op.drop_column("users", "ref_code")
