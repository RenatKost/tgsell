"""Outbox of seller alerts about admin actions on a lot (migration 0067).

One row = one Telegram message via the alerts bot. Rows are enqueued in the same
transaction as the admin action and delivered by the paid-services loop
(app.services.seller_notices). Terminal state: sent_at or failed_at is set.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SellerNotification(Base):
    __tablename__ = "seller_notifications"
    __table_args__ = (
        Index("ix_seller_notifications_due", "next_attempt_at",
              postgresql_where=text("sent_at IS NULL AND failed_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    # unpublish | remove | delete | buyer_warning
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"reason": ...} / {"warning": ...}
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, server_default=func.now())
