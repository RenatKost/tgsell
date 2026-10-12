"""Deal chat v2 (migration 0029): read/delivered markers, presence, attachments."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DealChatRead(Base):
    __tablename__ = "deal_chat_reads"

    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_read_message_id: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_delivered_message_id: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DealChatPresence(Base):
    __tablename__ = "deal_chat_presence"

    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    typing_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DealAttachment(Base):
    __tablename__ = "deal_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("deal_messages.id", ondelete="CASCADE"), nullable=True, index=True)
    uploader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(120))
    mime: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    thumb: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DealChatTgLink(Base):
    """One forwarded copy of a chat message in a recipient's Telegram (stage B bridge).

    Row is committed BEFORE sending (at-most-once); tg_message_id is filled after send.
    Replies in Telegram are matched by (tg_chat_id, tg_message_id).
    """
    __tablename__ = "deal_chat_tg_links"
    __table_args__ = (
        UniqueConstraint("message_id", "recipient_user_id", name="uq_deal_chat_tg_links_msg_recipient"),
        Index("uq_deal_chat_tg_links_tg", "tg_chat_id", "tg_message_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("deal_messages.id", ondelete="CASCADE"))
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tg_chat_id: Mapped[int] = mapped_column(BigInteger)
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    read_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
