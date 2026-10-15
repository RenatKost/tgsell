"""Task 24: saved catalog searches + per-search match queue for bot notifications."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    filters: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # sent / not_started / failed (last notification attempt)
    last_delivery_status: Mapped[str | None] = mapped_column(String(20), nullable=True)


class SavedSearchMatch(Base):
    __tablename__ = "saved_search_matches"
    __table_args__ = (UniqueConstraint("search_id", "channel_id", name="uq_saved_search_match"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(Integer, ForeignKey("saved_searches.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # NULL = waiting; set when the grouped message was attempted
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered: Mapped[bool | None] = mapped_column(nullable=True)
