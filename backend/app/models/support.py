"""Support inbox messages from @tgsell_support_bot."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        CheckConstraint("direction IN ('in', 'out')", name="ck_support_messages_direction"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)  # 'in' | 'out'
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    is_urgent: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    handled: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reply_to_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("support_messages.id", ondelete="SET NULL"), nullable=True
    )
