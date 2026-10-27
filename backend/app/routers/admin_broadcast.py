"""Admin one-off broadcast (alerts bot). Admin role only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services import broadcast as svc
from app.services.moderation import audit
from app.utils.security import get_superadmin_user

router = APIRouter(prefix="/admin/broadcast", tags=["admin"])


class BroadcastIn(BaseModel):
    campaign_key: str = Field(..., max_length=64)
    text: str = Field("", max_length=svc.TEXT_MAX)
    segment: str = "active_sellers"
    exclude_channel_ids: list[int] = Field(default_factory=list)
    exclude_bundle_ids: list[int] = Field(default_factory=list)
    dry_run: bool = True


@router.post("")
async def broadcast(body: BroadcastIn, admin: User = Depends(get_superadmin_user), db: AsyncSession = Depends(get_db)):
    try:
        key = svc.validate_key(body.campaign_key)
    except svc.BroadcastError as e:
        raise HTTPException(status_code=422, detail=str(e))
    extra: dict = {}
    if body.segment == svc.RELIST_SEGMENT:
        if key != svc.RELIST_KEY:
            raise HTTPException(status_code=422, detail=f"Для цього сегмента campaign_key = {svc.RELIST_KEY}")
        seg = await svc.segment_relist(db, body.exclude_channel_ids, body.exclude_bundle_ids)
        users = [u for u, _ in seg["recipients"]]
        extra = {"segment": body.segment, "default_text": svc.RELIST_TEXT,
                 "recipients_list": [i for _, i in seg["recipients"]], "no_bot": [i for _, i in seg["no_bot"]]}
    elif body.segment == "active_sellers":
        users = await svc.segment_active_sellers(db, body.exclude_channel_ids, body.exclude_bundle_ids)
    else:
        raise HTTPException(status_code=422, detail="Невідомий сегмент")
    st = await svc.stats(db, key)
    from sqlalchemy import select
    from app.models.broadcast import BroadcastLog
    done_ids = set((await db.execute(select(BroadcastLog.user_id).where(
        BroadcastLog.campaign_key == key, BroadcastLog.status != "pending"))).scalars())
    to_send = [u for u in users if u.id not in done_ids]
    out = {"campaign_key": key, "dry_run": body.dry_run, "recipients": len(users),
           "already_processed": len(users) - len(to_send), "to_send": len(to_send),
           "limit": svc.MAX_RECIPIENTS, "stats": st, **extra}
    if len(users) > svc.MAX_RECIPIENTS:
        if body.dry_run:
            return out | {"over_limit": True}
        raise HTTPException(status_code=400, detail=f"Забагато отримувачів: {len(users)} > {svc.MAX_RECIPIENTS}")
    if body.dry_run:
        return out
    text = body.text.strip()
    if body.segment == svc.RELIST_SEGMENT:
        text = svc.RELIST_TEXT  # campaign text is fixed (verbatim)
    if not text:
        raise HTTPException(status_code=422, detail="Порожній текст")
    if svc._tasks.get(key) and not svc._tasks[key].done():
        raise HTTPException(status_code=409, detail="Ця кампанія вже надсилається")
    await svc.prepare(db, key, to_send)
    audit(db, admin, "broadcast.start", "broadcast", None, campaign_key=key, recipients=len(to_send),
          exclude_channel_ids=body.exclude_channel_ids, exclude_bundle_ids=body.exclude_bundle_ids)
    await db.commit()
    import importlib
    session_factory = importlib.import_module("app.database").async_session
    svc.start_background(session_factory, key, text)
    return out | {"started": True, "stats": await svc.stats(db, key)}


@router.get("/{campaign_key}")
async def broadcast_stats(campaign_key: str, admin: User = Depends(get_superadmin_user), db: AsyncSession = Depends(get_db)):
    try:
        key = svc.validate_key(campaign_key)
    except svc.BroadcastError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return await svc.stats(db, key)
