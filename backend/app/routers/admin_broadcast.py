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
    # segment=targeted: «12, @seller, #45» (user ID, @username, #лот → його продавець)
    targets: str = Field("", max_length=20000)
    # «Спробувати надіслати» тим, хто без бота. Off by default.
    try_no_bot: bool = False
    dry_run: bool = True
    # Real send only with the token from a dry-run of exactly the same audience/text/checkbox.
    confirm_token: str = ""


@router.post("")
async def broadcast(body: BroadcastIn, admin: User = Depends(get_superadmin_user), db: AsyncSession = Depends(get_db)):
    try:
        key = svc.validate_key(body.campaign_key)
    except svc.BroadcastError as e:
        raise HTTPException(status_code=422, detail=str(e))
    extra: dict = {"segment": body.segment, "try_no_bot": body.try_no_bot}
    text = body.text.strip()
    if body.segment == svc.RELIST_SEGMENT:
        if key != svc.RELIST_KEY:
            raise HTTPException(status_code=422, detail=f"Для цього сегмента campaign_key = {svc.RELIST_KEY}")
        seg = await svc.segment_relist(db, body.exclude_channel_ids, body.exclude_bundle_ids)
        subscribed = [u for u, _ in seg["recipients"]]
        no_bot_users = [u for u, _ in seg["no_bot"]]
        no_bot_items = [i for _, i in seg["no_bot"]]
        text = svc.RELIST_TEXT  # campaign text is fixed (verbatim)
        extra |= {"default_text": svc.RELIST_TEXT, "recipients_list": [i for _, i in seg["recipients"]]}
    elif body.segment == "active_sellers":
        everyone = await svc.segment_active_sellers(db, body.exclude_channel_ids, body.exclude_bundle_ids,
                                                    include_no_bot=True)
        subscribed, no_bot_users = svc.split_no_bot(everyone)
        no_bot_items = [svc.no_bot_item(u) for u in no_bot_users]
    elif body.segment == svc.TARGETED_SEGMENT:
        seg = await svc.segment_targeted(db, body.targets)
        if not seg["users"] and not seg["not_found"] and not seg["invalid"] and not seg["excluded"]:
            raise HTTPException(status_code=422, detail="Вкажіть отримувачів: ID користувачів, @username або #ID лота")
        subscribed, no_bot_users = svc.split_no_bot(seg["users"])
        no_bot_items = [svc.no_bot_item(u) for u in no_bot_users]
        extra |= {"recipients_list": [{"user_id": u.id, "username": u.username} for u in subscribed],
                  "not_found": seg["not_found"], "invalid": seg["invalid"], "excluded": seg["excluded"]}
    else:
        raise HTTPException(status_code=422, detail="Невідомий сегмент")
    users = svc.with_try_no_bot(subscribed, no_bot_users, body.try_no_bot)
    st = await svc.stats(db, key)
    from sqlalchemy import select
    from app.models.broadcast import BroadcastLog
    done_ids = set((await db.execute(select(BroadcastLog.user_id).where(
        BroadcastLog.campaign_key == key, BroadcastLog.status != "pending"))).scalars())
    to_send = [u for u in users if u.id not in done_ids]
    token = svc.confirm_token(key, body.segment, text, body.try_no_bot, [u.id for u in to_send])
    out = {"campaign_key": key, "dry_run": body.dry_run, "recipients": len(users),
           "subscribed": len(subscribed), "no_bot_count": len(no_bot_users), "no_bot": no_bot_items,
           "already_processed": len(users) - len(to_send), "to_send": len(to_send),
           "limit": svc.MAX_RECIPIENTS, "send_interval_sec": svc.SEND_INTERVAL_SEC,
           "stats": st, "confirm_token": token, **extra}
    if len(users) > svc.MAX_RECIPIENTS:
        if body.dry_run:
            return out | {"over_limit": True}
        raise HTTPException(status_code=400, detail=f"Забагато отримувачів: {len(users)} > {svc.MAX_RECIPIENTS}")
    if body.dry_run:
        return out
    out.pop("confirm_token")
    if not body.confirm_token or body.confirm_token != token:
        raise HTTPException(status_code=409, detail="Спершу натисніть «Порахувати» (dry-run) і підтвердьте відправку: "
                                                    "аудиторія, текст або галочка змінились після перевірки")
    if not text:
        raise HTTPException(status_code=422, detail="Порожній текст")
    if svc._tasks.get(key) and not svc._tasks[key].done():
        raise HTTPException(status_code=409, detail="Ця кампанія вже надсилається")
    await svc.prepare(db, key, to_send)
    audit(db, admin, "broadcast.start", "broadcast", None, campaign_key=key, segment=body.segment,
          recipients=len(to_send), no_bot=len(no_bot_users), try_no_bot=body.try_no_bot,
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
