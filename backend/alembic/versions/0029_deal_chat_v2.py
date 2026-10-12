"""Deal chat v2: message kind/event/meta/client_id, reads, presence, attachments

Revision ID: 0029
Revises: 0028

Additive: new nullable columns, new tables, new indexes; deal_messages.sender_id becomes
nullable (system messages). Existing rows are not modified.
"""
import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("deal_messages", "sender_id", existing_type=sa.Integer(), nullable=True)
    for name, type_ in (("kind", sa.String(16)), ("event", sa.String(32)), ("meta", sa.JSON()),
                        ("client_id", sa.String(64)), ("edited_at", sa.DateTime()), ("deleted_at", sa.DateTime())):
        op.add_column("deal_messages", sa.Column(name, type_, nullable=True))
    op.create_index("ix_deal_messages_deal_id_id", "deal_messages", ["deal_id", "id"])
    op.create_index("uq_deal_messages_client_id", "deal_messages", ["deal_id", "client_id"], unique=True,
                    postgresql_where=sa.text("client_id IS NOT NULL"))
    op.create_table(
        "deal_chat_reads",
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_read_message_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_delivered_message_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "deal_chat_presence",
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("typing_until", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "deal_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("deal_messages.id", ondelete="CASCADE"), nullable=True),
        sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(120), nullable=False),
        sa.Column("mime", sa.String(64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("thumb", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_deal_attachments_deal_id", "deal_attachments", ["deal_id"])
    op.create_index("ix_deal_attachments_message_id", "deal_attachments", ["message_id"])
    op.create_index("ix_deal_attachments_created_at", "deal_attachments", ["created_at"])


def downgrade() -> None:
    op.drop_table("deal_attachments")
    op.drop_table("deal_chat_presence")
    op.drop_table("deal_chat_reads")
    op.drop_index("uq_deal_messages_client_id", table_name="deal_messages")
    op.drop_index("ix_deal_messages_deal_id_id", table_name="deal_messages")
    for name in ("deleted_at", "edited_at", "client_id", "meta", "event", "kind"):
        op.drop_column("deal_messages", name)
    # sender_id stays nullable (re-adding NOT NULL could fail on system rows with NULL)
