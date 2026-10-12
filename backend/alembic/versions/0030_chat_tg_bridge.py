"""Deal chat Telegram bridge: deal_messages.tg_forward_status + deal_chat_tg_links

Revision ID: 0030
Revises: 0029

Additive only. Existing messages keep tg_forward_status NULL (never forwarded).
"""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deal_messages", sa.Column("tg_forward_status", sa.String(16), nullable=True))
    op.create_index("ix_deal_messages_tg_pending", "deal_messages", ["id"],
                    postgresql_where=sa.text("tg_forward_status = 'pending'"))
    op.create_table(
        "deal_chat_tg_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("deal_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("read_synced_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("message_id", "recipient_user_id", name="uq_deal_chat_tg_links_msg_recipient"),
    )
    op.create_index("ix_deal_chat_tg_links_deal_id", "deal_chat_tg_links", ["deal_id"])
    op.create_index("uq_deal_chat_tg_links_tg", "deal_chat_tg_links", ["tg_chat_id", "tg_message_id"], unique=True)


def downgrade() -> None:
    op.drop_table("deal_chat_tg_links")
    op.drop_index("ix_deal_messages_tg_pending", table_name="deal_messages")
    op.drop_column("deal_messages", "tg_forward_status")
