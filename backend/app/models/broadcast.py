"""Admin one-off broadcasts via the alerts bot (migration 0053)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BroadcastLog(Base):
    __tablename__ = "broadcast_log"
    __table_args__ = (UniqueConstraint("campaign_key", "user_id", name="uq_broadcast_log_campaign_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_key: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    # pending → sending → sent | failed  (a 'sending' row is never re-sent)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
