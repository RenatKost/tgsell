"""Task 23: first-party user activity (no IP / UA / query text stored)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserEvent(Base):
    __tablename__ = "user_events"
    __table_args__ = (
        Index("ix_user_events_created", "created_at"),
        Index("ix_user_events_user_created", "user_id", "created_at"),
        Index("ix_user_events_type_created", "event_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # sha256 of a random client-side id (localStorage); never IP / UA.
    anon_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    object_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # channel | page
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Attribution (visit events only): utm_* values + referer *domain*, never full URL.
    utm_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_user_last", "user_id", "last_seen_at"),
        Index("ix_user_sessions_last", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_key: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    anon_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    active_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    heartbeats: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
