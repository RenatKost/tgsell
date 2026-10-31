"""UTM tracking: lightweight anonymous visit beacon + admin «Кампанії» report."""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services import utm as svc
from app.utils.activity_ids import hash_id, limiter
from app.utils.security import get_superadmin_user
from app.utils.timeutil import utcnow_naive

router = APIRouter(tags=["utm"])
PER_ANON_PER_MINUTE = 10
PER_CLIENT_PER_MINUTE = 60
GLOBAL_PER_MINUTE = 600  # endpoint-wide cap: floods from many IPs never reach the DB


class UtmVisitIn(BaseModel):
    anon: str | None = Field(None, max_length=128)
    utm_source: str | None = Field(None, max_length=200)
    utm_campaign: str | None = Field(None, max_length=200)
    utm_content: str | None = Field(None, max_length=200)
    path: str | None = Field(None, max_length=512)


class UtmEventIn(UtmVisitIn):
    event: str = Field(..., max_length=32)
    auto: bool | None = None  # legacy top-level flag (sell_open auto-open) → meta.auto
    meta: dict | None = None  # whitelisted + size-capped in svc.clean_meta; unknown keys dropped


def _client_key(request: Request) -> str:
    from app.utils.client_ip import client_ip
    raw = client_ip(request)  # rightmost XFF hop (added by Railway edge), not the spoofable first
    return hashlib.sha256(("tgsell-utm:" + raw).encode()).hexdigest()[:24]  # in-memory only, never stored


@router.post("/track/utm", status_code=status.HTTP_204_NO_CONTENT)
async def track_utm(body: UtmVisitIn, request: Request, db: AsyncSession = Depends(get_db)):
    d = svc.fields(body)
    if not d:
        return None
    anon = hash_id(body.anon)
    if not limiter.per_minute("utm:global", GLOBAL_PER_MINUTE):
        raise HTTPException(status_code=429, detail="Забагато запитів")
    if not limiter.per_minute("utm:c:" + _client_key(request), PER_CLIENT_PER_MINUTE) or \
            (anon and not limiter.per_minute("utm:a:" + anon, PER_ANON_PER_MINUTE)):
        raise HTTPException(status_code=429, detail="Забагато запитів")
    path = svc.clean_path(body.path)
    ua = svc.ua_class(request.headers.get("user-agent"))
    svc.log_visit(d, path, ua)
    from app.models.utm import UtmVisit
    db.add(UtmVisit(anon_hash=anon, path=path, ua_class=ua, created_at=utcnow_naive(), **d))
    await db.commit()
    return None


@router.post("/track/funnel", status_code=status.HTTP_204_NO_CONTENT)
async def track_funnel(body: UtmEventIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Client funnel step of a UTM visitor (sell_open / login_click / form_start / form_submit_attempt)."""
    d = svc.fields(body)
    if not d or body.event not in svc.CLIENT_EVENTS:
        return None
    anon = hash_id(body.anon)
    if not limiter.per_minute("utm:global", GLOBAL_PER_MINUTE) or \
            not limiter.per_minute("utm:c:" + _client_key(request), PER_CLIENT_PER_MINUTE) or \
            (anon and not limiter.per_minute("utm:e:" + anon, PER_ANON_PER_MINUTE)):
        raise HTTPException(status_code=429, detail="Забагато запитів")
    from app.models.utm import UtmEvent
    meta = svc.clean_meta(body.meta, auto=body.auto)
    ua = svc.ua_class(request.headers.get("user-agent"))
    svc.log_event(body.event, d)
    db.add(UtmEvent(anon_hash=anon, event=body.event, meta=meta, ua_class=ua, created_at=utcnow_naive(), **d))
    await db.commit()
    return None


@router.get("/admin/utm/campaigns")
async def admin_campaigns(date_from: str | None = Query(None, max_length=40), date_to: str | None = Query(None, max_length=40),
                          admin: User = Depends(get_superadmin_user), db: AsyncSession = Depends(get_db)):
    """date_from/date_to: a date (YYYY-MM-DD, whole day, as before) or an exact ISO datetime
    (with offset/Z → converted to UTC; naive → treated as UTC)."""
    try:
        start = svc.parse_bound(date_from, end=False)
        end = svc.parse_bound(date_to, end=True)
    except ValueError:
        raise HTTPException(status_code=400, detail="Невірний формат дати")
    if start and end and start >= end:
        raise HTTPException(status_code=400, detail="Невірний діапазон дат")
    return await svc.report(db, start, end)
