"""Support inbox messages from @tgsell_support_bot."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.timeutil import utcnow_naive

# Delivery status of outbound ('out') messages. NULL = legacy rows / inbound.
DELIVERY_SENDING = "sending"
DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        CheckConstraint("direction IN ('in', 'out')", name="ck_support_messages_direction"),
        CheckConstraint(
            "delivery_status IS NULL OR delivery_status IN ('sending', 'sent', 'failed')",
            name="ck_support_messages_delivery_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_support_messages_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)  # 'in' | 'out'
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # All timestamps here are naive UTC (TIMESTAMP WITHOUT TIME ZONE). created_at is set
    # app-side so the auto-reply cooldown does not depend on the DB session timezone.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=utcnow_naive, nullable=False
    )
    is_urgent: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    handled: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reply_to_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("support_messages.id", ondelete="SET NULL"), nullable=True
    )

    # Outbound delivery tracking (migration 0024)
    delivery_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    send_attempts: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
