"""Paid seller services API (seller: /services, staff: /admin/services)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.channel import Channel
from app.models.paid_service import PaidServiceOrder
from app.models.user import User
from app.services import paid_services as svc
from app.services.moderation import audit
from app.utils.security import get_admin_user, get_current_user, get_superadmin_user

router = APIRouter(prefix="/services", tags=["services"])
admin_router = APIRouter(prefix="/admin/services", tags=["admin"])

STATUS_LABELS = {
    svc.ST_AWAITING: "Очікує оплату", svc.ST_ACTIVE: "Активний", svc.ST_EXPIRED: "Завершено",
    svc.ST_PAID: "Оплачено, в черзі", svc.ST_IN_REVIEW: "В роботі", svc.ST_PUBLISHED: "Опубліковано",
    svc.ST_VERIFIED: "Перевірено", svc.ST_REJECTED: "Відмовлено", svc.ST_CANCELLED: "Скасовано (не оплачено)",
}


def _view(o: PaidServiceOrder, channel: Channel | None = None) -> dict:
    return {
        "id": o.id, "kind": o.kind, "title": svc.KIND_LABELS.get(o.kind, o.kind), "channel_id": o.channel_id,
        "channel_name": channel.channel_name if channel else None,
        "price_usdt": o.price_usdt, "status": o.status, "status_label": STATUS_LABELS.get(o.status, o.status),
        "escrow_wallet_address": o.escrow_wallet_address, "network": "USDT TRC-20",
        "received_usdt": o.received_usdt, "payment_deadline_at": o.payment_deadline_at,
        "paid_at": o.paid_at, "active_until": o.active_until, "admin_note": o.admin_note, "created_at": o.created_at,
    }


class OrderIn(BaseModel):
    channel_id: int
    kind: str = Field(..., max_length=20)


@router.get("/promo")
async def services_promo():
    """Public, DB-free: seller promo «Топ у подарунок» state (banner on /sell and cabinet)."""
    from app.services.promo_top import promo_info
    return promo_info()


@router.get("/catalog")
async def services_catalog(db: AsyncSession = Depends(get_db)):
    from app.utils.timeutil import utcnow_naive
    cfg = await svc.get_settings(db)
    taken = await svc.top_slots_taken(db, utcnow_naive())
    return {"items": svc.public_catalog(cfg), "top_slots_free": max(0, int(cfg["service_top_max_slots"]) - taken)}


@router.post("/orders", status_code=201)
async def create_order(body: OrderIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ch = (await db.execute(select(Channel).where(Channel.id == body.channel_id).with_for_update())).scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=404, detail="Лот не знайдено")
    try:
        o = await svc.create_order(db, seller_id=user.id, channel=ch, kind=body.kind)
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return _view(o, ch)


@router.get("/orders/my")
async def my_orders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(PaidServiceOrder, Channel).join(Channel, Channel.id == PaidServiceOrder.channel_id)
                             .where(PaidServiceOrder.seller_id == user.id).order_by(PaidServiceOrder.id.desc()))).all()
    return [_view(o, c) for o, c in rows]


class StatusIn(BaseModel):
    status: str = Field(..., max_length=20)
    note: str | None = Field(None, max_length=1000)


@admin_router.get("/orders")
async def admin_orders(kind: str | None = Query(None), status: str | None = Query(None),
                       admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    q = select(PaidServiceOrder, Channel).join(Channel, Channel.id == PaidServiceOrder.channel_id)
    if kind:
        q = q.where(PaidServiceOrder.kind == kind)
    if status:
        q = q.where(PaidServiceOrder.status == status)
    rows = (await db.execute(q.order_by(PaidServiceOrder.id.desc()).limit(200))).all()
    return {"items": [_view(o, c) | {"seller_id": o.seller_id,
                                     "next": list(svc.ADMIN_TRANSITIONS.get(o.kind, {}).get(o.status, ()))}
                      for o, c in rows]}


@admin_router.post("/orders/{order_id}/status")
async def admin_set_status(order_id: int, body: StatusIn, admin: User = Depends(get_admin_user),
                           db: AsyncSession = Depends(get_db)):
    o = (await db.execute(select(PaidServiceOrder).where(PaidServiceOrder.id == order_id).with_for_update())).scalar_one_or_none()
    if o is None:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")
    old = o.status
    try:
        await svc.admin_transition(db, o, body.status, admin.id, body.note)
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(db, admin, "service_order_status", "paid_service_order", o.id, **{"from": old, "to": o.status, "kind": o.kind})
    await db.commit()
    return _view(o, await db.get(Channel, o.channel_id))


@admin_router.get("/settings")
async def admin_get_settings(admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    return await svc.get_settings(db)


@admin_router.put("/settings")
async def admin_put_settings(body: dict, admin: User = Depends(get_superadmin_user), db: AsyncSession = Depends(get_db)):
    try:
        cfg = await svc.update_settings(db, body)
    except (svc.ServiceError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e) or "Некоректні значення")
    audit(db, admin, "service_settings_update", "app_settings", None, **{k: body[k] for k in body if k in svc.DEFAULTS})
    await db.commit()
    return cfg
