"""App-level settings and service state stored in DB."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class TelethonSession(Base):
    """Persists the Telethon MTProto session string across Railway container restarts.

    Only one row (id=1) is used. The session is overwritten after each successful
    connection so that any DC migration or key-refresh data is never lost.
    Without this, TELETHON_SESSION_STRING in env is a static snapshot that goes
    stale whenever Telegram rotates auth keys — causing daily session invalidation.
    """

    __tablename__ = "telethon_sessions"

    id = Column(Integer, primary_key=True, default=1)
    session_string = Column(String, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
