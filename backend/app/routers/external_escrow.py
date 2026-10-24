"""«Гарант для зовнішніх угод» (/escrow).

Seller creates a PRIVATE offer (channel link, price, buyer @username) and gets a secret
link. Only the invited buyer (matching Telegram @username) can open/accept it via the
token. Accepting creates a regular escrow Deal — same deposit-address generation, same
deadlines, same payment/transfer/payout pipeline as catalog lots. Nothing here is listed
in catalog, search, sitemap or any public API.
"""
from __future__ import annotations

import logging
import secrets as _secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.deal import Deal, DealStatus
from app.models.external_escrow import ExternalEscrowOffer, ExternalOfferStatus
from app.models.user import User
from app.services import external_escrow as svc
from app.services.escrow import generate_escrow_wallet
from app.services.payment_deadlines import created_stage_deadline
from app.utils.money_display import money2_str
from app.utils.security import get_current_user
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/escrow", tags=["escrow"])

NOT_FOUND = "Угоду не знайдено або вона призначена іншому користувачу"


class OfferIn(BaseModel):
    channel_link: str = Field(..., max_length=255)
    price_usdt: float
    buyer_username: str = Field(..., max_length=64)


def _seller_view(o: ExternalEscrowOffer) -> dict:
    return {
        "id": o.id,
        "channel_link": o.channel_link,
        "price_usdt": o.price_usdt,
        "fee_percent": o.fee_percent,
        "service_fee": o.service_fee,
        "seller_receives": round(o.price_usdt - o.service_fee, 2),
        "buyer_username": o.buyer_username,
        "status": o.status,
        "deal_id": o.deal_id,
        "buyer_url": svc.buyer_url(o.token),
        "created_at": o.created_at,
    }


def _buyer_view(o: ExternalEscrowOffer, seller: User | None) -> dict:
    return {
        "channel_link": o.channel_link,
        "price_usdt": o.price_usdt,
        "fee_percent": o.fee_percent,
        "service_fee": o.service_fee,
        "seller_name": seller.first_name if seller else None,
        "status": o.status,
        "deal_id": o.deal_id,
    }


@router.get("/meta")
async def escrow_meta():
    return {"min_price_usdt": svc.MIN_PRICE_USDT, "fee_percent": svc.fee_percent(), "network": "USDT TRC-20"}


@router.post("/offers", status_code=status.HTTP_201_CREATED)
async def create_offer(body: OfferIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.telegram_id:
        raise HTTPException(status_code=403, detail="Увійдіть через Telegram (@tgsell_auth_bot), щоб створити угоду")
    link = svc.normalize_channel_link(body.channel_link)
    if not link:
        raise HTTPException(status_code=422, detail="Вкажіть посилання на канал у форматі t.me/назва або @назва")
    buyer = svc.normalize_username(body.buyer_username)
    if not buyer:
        raise HTTPException(status_code=422, detail="Вкажіть коректний @username покупця в Telegram")
    if user.username and buyer == user.username.lower().lstrip("@"):
        raise HTTPException(status_code=400, detail="Не можна створити угоду із самим собою")
    price = round(float(body.price_usdt), 2)
    if not (price == price) or price < svc.MIN_PRICE_USDT:
        raise HTTPException(status_code=422, detail=f"Мінімальна ціна — {svc.MIN_PRICE_USDT:g} USDT")
    if price > svc.MAX_PRICE_USDT:
        raise HTTPException(status_code=422, detail="Занадто велика сума")
    pct = svc.fee_percent()
    offer = ExternalEscrowOffer(
        seller_id=user.id, channel_link=link, price_usdt=price, fee_percent=pct,
        service_fee=svc.calc_fee(price, pct), buyer_username=buyer, token=svc.new_token(),
        status=ExternalOfferStatus.open.value, created_at=utcnow_naive(),
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    logger.info(f"[ESCROW-EXT] offer #{offer.id} created by seller={user.id}, amount={price}")
    return _seller_view(offer)


@router.get("/offers/my")
async def my_offers(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ExternalEscrowOffer).where(ExternalEscrowOffer.seller_id == user.id)
        .order_by(ExternalEscrowOffer.id.desc())
    )).scalars().all()
    return [_seller_view(o) for o in rows]


@router.post("/offers/{offer_id}/cancel")
async def cancel_offer(offer_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    o = await db.get(ExternalEscrowOffer, offer_id)
    if o is None or o.seller_id != user.id:
        raise HTTPException(status_code=404, detail="Угоду не знайдено")
    if o.status != ExternalOfferStatus.open.value:
        raise HTTPException(status_code=400, detail="Скасувати можна лише угоду, яку покупець ще не прийняв")
    o.status = ExternalOfferStatus.cancelled.value
    await db.commit()
    return _seller_view(o)


async def _offer_for_buyer(db: AsyncSession, token: str, user: User, lock: bool = False) -> ExternalEscrowOffer:
    if not token or len(token) > 64:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    q = select(ExternalEscrowOffer).where(ExternalEscrowOffer.token == token)
    if lock:
        q = q.with_for_update()
    o = (await db.execute(q)).scalar_one_or_none()
    uname = (user.username or "").lower().lstrip("@")
    # Same 404 for unknown token and wrong user → token existence is not revealed.
    if o is None or not uname or not _secrets.compare_digest(uname, o.buyer_username):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if o.seller_id == user.id:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return o


@router.get("/invite/{token}")
async def view_invite(token: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    o = await _offer_for_buyer(db, token, user)
    return _buyer_view(o, await db.get(User, o.seller_id))


@router.post("/invite/{token}/accept")
async def accept_invite(token: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    o = await _offer_for_buyer(db, token, user, lock=True)
    if o.status == ExternalOfferStatus.accepted.value and o.deal_id:
        return {"deal_id": o.deal_id}
    if o.status != ExternalOfferStatus.open.value:
        raise HTTPException(status_code=400, detail="Продавець скасував цю угоду")
    seller = await db.get(User, o.seller_id)
    if seller is None or seller.is_blocked or not seller.is_active:
        raise HTTPException(status_code=400, detail="Продавець недоступний — нові угоди заборонені")

    # Same escrow mechanism as catalog lots (routers/deals.py::create_deal).
    wallet_address, encrypted_private_key = generate_escrow_wallet()
    deal = Deal(
        channel_id=None,
        bundle_id=None,
        external_channel_link=o.channel_link,
        buyer_id=user.id,
        seller_id=o.seller_id,
        status=DealStatus.created,
        escrow_wallet_address=wallet_address,
        escrow_private_key_encrypted=encrypted_private_key,
        amount_usdt=o.price_usdt,
        service_fee=o.service_fee,
        payment_deadline_at=created_stage_deadline(utcnow_naive()),
    )
    db.add(deal)
    await db.flush()
    o.deal_id = deal.id
    o.status = ExternalOfferStatus.accepted.value

    import app.services.chat as chat_svc
    payout = deal.amount_usdt - deal.service_fee
    chat_svc.system(db, deal.id, "deal_created", (
        f"Угоду через гарант TgSell створено! Канал: {o.channel_link}\n"
        f"Вартість: {money2_str(deal.amount_usdt)} USDT\n"
        f"Комісія сервісу: {o.fee_percent:g}% ({money2_str(deal.service_fee)} USDT)\n"
        f"Продавець отримає: {money2_str(payout)} USDT\n\n"
        f"Підтвердіть готовність, щоб перейти до оплати."
    ), actor_id=user.id)
    await db.commit()
    await db.refresh(deal)
    logger.info(f"[DEAL] External deal #{deal.id} CREATED from offer #{o.id}: buyer={user.id}, seller={o.seller_id}, amount={deal.amount_usdt} USDT")

    try:
        from bot.main import notify_new_deal
        from aiogram import Bot
        bot = Bot(token=settings.bot_token_alerts)
        await notify_new_deal(bot, deal, user, seller)
        await bot.session.close()
    except Exception as e:  # notifications never block the deal
        logger.error(f"[DEAL] Failed to notify about external deal #{deal.id}: {e}", exc_info=True)
    return {"deal_id": deal.id}
