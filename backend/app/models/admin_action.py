"""Audit log for admin/agent-triggered actions.

Right now nothing in admin.py leaves a queryable trail beyond application
logs — approve/reject/cancel/escrow-sweep/role-change all just happen. This
table gives every such action a durable, queryable record of who did what
and when, which is a prerequisite for trusting any autonomous agent to call
these endpoints in the future (see automation/agents/developer.md context).
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminAction(Base):
    """One row per sensitive admin/agent action.

    `actor` is either a user id as a string (e.g. "42") for a human admin,
    or an "agent:<role>" tag (e.g. "agent:developer") for an autonomous
    agent — kept as a plain string rather than a FK so agent actors don't
    need a row in `users`.
    """

    __tablename__ = "admin_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
