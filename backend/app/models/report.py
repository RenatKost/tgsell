"""Scheduled-report run log (migration 0044): one row per report period = idempotency key."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScheduledReportRun(Base):
    __tablename__ = "scheduled_report_runs"

    # e.g. "weekly_stats:2026-W43" — primary key makes the claim atomic across containers.
    report_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))  # sending | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
