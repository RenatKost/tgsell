"""UTM campaign tracking (migration 0057): anonymous landing visits with utm_* (no PII)."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UtmVisit(Base):
    __tablename__ = "utm_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anon_hash: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)  # sha256(anon id)[:32]
    utm_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    utm_content: Mapped[str | None] = mapped_column(String(64), nullable=True)
    path: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ua_class: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ig_inapp | fb_inapp | tg_inapp | mobile | desktop | bot
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class UtmEvent(Base):
    """Funnel step of a UTM visitor (migration 0058): login_click, form_start, form_submit_attempt,
    bot_start, login_success. No PII — hashed anon id + first-touch utm_* only."""
    __tablename__ = "utm_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anon_hash: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(32), index=True)
    utm_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    utm_content: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)  # 0059: whitelisted keys only
    ua_class: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 0059: same classes as utm_visits
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
