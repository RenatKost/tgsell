"""UTM tracking: lightweight anonymous visit beacon + admin «Кампанії» report."""
from __future__ import annotations

from datetime import date
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


class UtmVisitIn(BaseModel):
    anon: str | None = Field(None, max_length=128)
    utm_source: str | None = Field(None, max_length=200)
    utm_campaign: str | None = Field(None, max_length=200)
    utm_content: str | None = Field(None, max_length=200)
    path: str | None = Field(None, max_length=512)


def _client_key(request: Request) -> str:
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    raw = fwd or (request.client.host if request.client else "")
    return hashlib.sha256(("tgsell-utm:" + raw).encode()).hexdigest()[:24]  # in-memory only, never stored


@router.post("/track/utm", status_code=status.HTTP_204_NO_CONTENT)
async def track_utm(body: UtmVisitIn, request: Request, db: AsyncSession = Depends(get_db)):
    d = svc.fields(body)
    if not d:
        return None
    anon = hash_id(body.anon)
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


@router.get("/admin/utm/campaigns")
async def admin_campaigns(date_from: date | None = Query(None), date_to: date | None = Query(None),
                          admin: User = Depends(get_superadmin_user), db: AsyncSession = Depends(get_db)):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="Невірний діапазон дат")
    return await svc.report(db, date_from, date_to)
