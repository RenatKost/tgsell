"""Task 23: activity tracking endpoints + admin «Користувачі» / funnel."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services import user_activity as ua
from app.utils.security import get_superadmin_user, verify_token

router = APIRouter(tags=["activity-tracking"])
_optional_bearer = HTTPBearer(auto_error=False)


def _optional_user_id(creds: HTTPAuthorizationCredentials | None = Depends(_optional_bearer)) -> int | None:
    if not creds:
        return None
    try:
        sub = verify_token(creds.credentials).get("sub")
        return int(sub) if sub is not None else None
    except Exception:
        return None


class EventIn(BaseModel):
    type: str = Field(..., max_length=32)
    anon: str | None = Field(None, max_length=128)
    channel_id: int | None = Field(None, ge=1)
    page: str | None = Field(None, max_length=32)


class HeartbeatIn(BaseModel):
    sid: str = Field(..., min_length=8, max_length=128)
    anon: str | None = Field(None, max_length=128)


@router.post("/track/event", status_code=status.HTTP_204_NO_CONTENT)
async def track_event(body: EventIn, user_id: int | None = Depends(_optional_user_id),
                      db: AsyncSession = Depends(get_db)):
    if body.type not in ua.CLIENT_EVENTS:
        raise HTTPException(status_code=400, detail="Невідомий тип події")
    anon = ua.hash_id(body.anon)
    key = f"u{user_id}" if user_id is not None else f"a{anon}"
    if anon is None and user_id is None:
        return None
    if not ua.limiter.per_minute("ev:" + key, ua.EVENTS_PER_MINUTE):
        raise HTTPException(status_code=429, detail="Забагато запитів")
    page = body.page if body.page in ua.PAGES else ("other" if body.page else None)
    if body.type == "channel_view":
        if body.channel_id is None:
            raise HTTPException(status_code=400, detail="channel_id обовʼязковий")
        await ua.record_event(db, "channel_view", user_id=user_id, anon_id=anon,
                              object_type="channel", object_id=body.channel_id, page="channel")
    else:
        await ua.record_event(db, body.type, user_id=user_id, anon_id=anon,
                              object_type="page" if page else None, page=page)
    return None


@router.post("/track/heartbeat")
async def track_heartbeat(body: HeartbeatIn, user_id: int | None = Depends(_optional_user_id),
                          db: AsyncSession = Depends(get_db)):
    key = ua.hash_id(body.sid)
    if not key:
        raise HTTPException(status_code=400, detail="Некоректна сесія")
    if not ua.limiter.min_interval("hb:" + key, ua.HEARTBEAT_MIN_INTERVAL):
        raise HTTPException(status_code=429, detail="Забагато запитів")
    credited = await ua.heartbeat(db, key, user_id=user_id, anon_id=ua.hash_id(body.anon))
    return {"ok": True, "credited": credited}


@router.get("/admin/activity/users")
async def admin_activity_users(limit: int = Query(200, ge=1, le=500),
                               admin: User = Depends(get_superadmin_user),
                               db: AsyncSession = Depends(get_db)):
    return {"items": await ua.users_activity(db, limit=limit)}


@router.get("/admin/activity/funnel")
async def admin_activity_funnel(admin: User = Depends(get_superadmin_user),
                                db: AsyncSession = Depends(get_db)):
    return {"funnels": [await ua.funnel(db, 7), await ua.funnel(db, 30)]}
