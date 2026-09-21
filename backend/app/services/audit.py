"""Audit logging for sensitive admin/agent actions. See models/admin_action.py."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_action import AdminAction

logger = logging.getLogger(__name__)


async def log_admin_action(
    db: AsyncSession,
    actor: str,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    payload: dict | None = None,
    commit: bool = True,
) -> None:
    """Record one audit row.

    `actor` — a user id as a string (e.g. str(user.id)) for a human admin,
    or "agent:<role>" for an autonomous agent. Failures here are logged but
    never raised — an audit-log write must not block the underlying action.
    """
    try:
        db.add(
            AdminAction(
                actor=actor,
                action=action,
                target_type=target_type,
                target_id=target_id,
                payload=payload,
            )
        )
        if commit:
            await db.commit()
    except Exception as e:
        logger.error(f"[AUDIT] Failed to log action '{action}' by '{actor}': {e}")
