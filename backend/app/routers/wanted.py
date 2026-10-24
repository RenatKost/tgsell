"""«Шукаю канал»: public list, buyer CRUD, admin moderation + stats."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.wanted import WantedRequest
from app.services import wanted as svc
from app.services.moderation import audit
from app.utils.security import get_admin_user, get_current_user
from app.utils.timeutil import utcnow_naive

router = APIRouter(prefix="/wanted", tags=["wanted"])
admin_router = APIRouter(prefix="/admin/wanted", tags=["admin"])


class WantedIn(BaseModel):
    category: str = Field(..., max_length=100)
    subs_min: int | None = None
    subs_max: int | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    language: str = Field(..., max_length=10)
    comment: str | None = Field(None, max_length=svc.COMMENT_MAX)


class RejectIn(BaseModel):
    reason: str | None = Field(None, max_length=500)


@router.get("/meta")
async def wanted_meta():
    return {"categories": svc.CATEGORIES, "languages": svc.LANGUAGES,
            "max_active": svc.MAX_ACTIVE_PER_USER, "ttl_days": svc.TTL.days, "comment_max": svc.COMMENT_MAX}


@router.get("")
async def list_wanted(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                      db: AsyncSession = Depends(get_db)):
    now = utcnow_naive()
    rows = (await db.execute(select(WantedRequest).where(svc.public_clause(now))
                             .order_by(WantedRequest.created_at.desc(), WantedRequest.id.desc())
                             .limit(limit).offset(offset))).scalars().all()
    return {"items": [svc.public_out(r) for r in rows]}


@router.get("/mine")
async def my_wanted(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WantedRequest).where(WantedRequest.user_id == user.id)
                             .order_by(WantedRequest.created_at.desc()))).scalars().all()
    return {"items": [svc.owner_out(r) for r in rows], "active": await svc.count_active(db, user.id),
            "max": svc.MAX_ACTIVE_PER_USER}


@router.get("/{request_id}")
async def get_wanted(request_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.get(WantedRequest, request_id)
    if not r or r.status != "approved" or r.expires_at <= utcnow_naive():
        raise HTTPException(status_code=404, detail="Запит не знайдено або він вже неактивний")
    return svc.public_out(r)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_wanted(body: WantedIn, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    try:
        row = await svc.create(db, user, body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.owner_out(row)


@router.delete("/{request_id}")
async def close_wanted(request_id: int, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    r = await db.get(WantedRequest, request_id)
    if not r or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="Запит не знайдено")
    if r.status in ("pending", "approved"):
        r.status = "closed"
        await db.commit()
    return {"ok": True}


# ── admin ──
@admin_router.get("")
async def admin_list(status_: str = Query("pending", alias="status"), admin: User = Depends(get_admin_user),
                     db: AsyncSession = Depends(get_db)):
    q = select(WantedRequest).order_by(WantedRequest.created_at.desc()).limit(200)
    if status_ != "all":
        q = q.where(WantedRequest.status == status_)
    rows = (await db.execute(q)).scalars().all()
    users = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_({r.user_id for r in rows} or {0})))).scalars().all()}
    out = []
    for r in rows:
        u = users.get(r.user_id)
        out.append(svc.owner_out(r) | {"user_id": r.user_id,
                                       "user_name": (u.username or u.first_name) if u else None,
                                       "auto_flags": r.auto_flags or []})
    return {"items": out}


@admin_router.get("/stats")
async def admin_stats(admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    return await svc.admin_stats(db)


async def _pending(db, request_id) -> WantedRequest:
    r = await db.get(WantedRequest, request_id)
    if not r:
        raise HTTPException(status_code=404, detail="Запит не знайдено")
    if r.status != "pending":
        raise HTTPException(status_code=400, detail="Запит вже промодеровано")
    return r


@admin_router.post("/{request_id}/approve")
async def admin_approve(request_id: int, admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    r = await _pending(db, request_id)
    now = utcnow_naive()
    r.status, r.moderator_id, r.moderated_at = "approved", admin.id, now
    audit(db, admin, "wanted.approve", "wanted_request", r.id)
    await db.commit()
    return svc.owner_out(r)


@admin_router.post("/{request_id}/reject")
async def admin_reject(request_id: int, body: RejectIn | None = None, admin: User = Depends(get_admin_user),
                       db: AsyncSession = Depends(get_db)):
    r = await _pending(db, request_id)
    r.status, r.moderator_id, r.moderated_at = "rejected", admin.id, utcnow_naive()
    r.rejection_reason = ((body.reason if body else None) or "").strip() or "Не відповідає правилам"
    audit(db, admin, "wanted.reject", "wanted_request", r.id)
    await db.commit()
    return svc.owner_out(r)
