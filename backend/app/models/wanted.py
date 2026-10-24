"""«Шукаю канал»: buyer requests (migration 0048)."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WantedRequest(Base):
    __tablename__ = "wanted_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(100))
    subs_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subs_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    language: Mapped[str] = mapped_column(String(10))  # ua | ru | en | other
    comment: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # pending -> approved / rejected; closed = withdrawn by the buyer
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Auto-check flags for moderators only (migration 0049); never exposed to the user.
    auto_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class WantedMatch(Base):
    """Dedup for buyer notifications: one message per (request, lot)."""
    __tablename__ = "wanted_matches"
    __table_args__ = (UniqueConstraint("request_id", "channel_id", name="uq_wanted_match"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(Integer, ForeignKey("wanted_requests.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    delivered: Mapped[bool | None] = mapped_column(nullable=True)
