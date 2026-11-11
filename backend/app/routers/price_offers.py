"""Buyer price offers on a catalog lot. Messages are to a participant, not a broadcast."""
from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.channel import Channel, ChannelStatus
from app.models.deal import ACTIVE_DEAL_STATUSES, Deal
from app.models.price_offer import PriceOffer, PriceOfferStatus
from app.models.user import User
from app.schemas.price_offer import PriceOfferCreate, PriceOfferResponse
from app.services import price_offers as svc
from app.utils.security import get_current_user
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/price-offers", tags=["price-offers"])


def _name(user: User | None) -> str | None:
    if not user:
        return None
    return (user.first_name or user.username or "").strip() or None


def _to_response(offer: PriceOffer, channel: Channel | None, buyer: User | None, viewer_id: int) -> PriceOfferResponse:
    accepted_unused = (
        offer.status == PriceOfferStatus.accepted
        and offer.deal_id is None
        and svc.acceptance_still_valid(offer)
    )
    return PriceOfferResponse(
        id=offer.id,
        channel_id=offer.channel_id,
        channel_name=channel.channel_name if channel else None,
        channel_avatar_url=getattr(channel, "avatar_url", None) if channel else None,
        buyer_id=offer.buyer_id,
        buyer_name=_name(buyer) if viewer_id == offer.seller_id or viewer_id == offer.buyer_id else None,
        seller_id=offer.seller_id,
        amount_usdt=offer.amount_usdt,
        lot_price_usdt=channel.price if channel else None,
        comment=offer.comment,
        status=offer.status,
        expires_at=offer.expires_at,
        created_at=offer.created_at,
        decided_at=offer.decided_at,
        accepted_at=offer.accepted_at,
        close_reason=offer.close_reason,
        deal_id=offer.deal_id,
        can_create_deal=accepted_unused and viewer_id == offer.buyer_id,
    )


async def _load(db: AsyncSession, offer_id: int) -> PriceOffer | None:
    return (await db.execute(
        select(PriceOffer)
        .options()
        .where(PriceOffer.id == offer_id)
    )).scalar_one_or_none()


async def _channel_buyer(db: AsyncSession, offer: PriceOffer) -> tuple[Channel | None, User | None]:
    ch = await db.get(Channel, offer.channel_id)
    buyer = await db.get(User, offer.buyer_id)
    return ch, buyer


async def _notify_after_commit(kind: str, offer: PriceOffer, channel: Channel, buyer: User, seller: User) -> None:
    """Best-effort participant notify. Failure must not affect the request."""
    try:
        from aiogram import Bot
        from app.config import settings
        from bot.main import notify_price_offer_accepted, notify_price_offer_received
        if not getattr(settings, "bot_token_alerts", None):
            return
        bot = Bot(token=settings.bot_token_alerts)
        try:
            if kind == "received":
                await notify_price_offer_received(bot, offer, channel, buyer, seller)
            else:
                await notify_price_offer_accepted(bot, offer, channel, buyer, seller)
        finally:
            await bot.session.close()
    except Exception as e:
        logger.warning("[OFFER] %s notify failed for offer #%s: %s", kind, getattr(offer, "id", "?"), e)


@router.post("", response_model=PriceOfferResponse, status_code=status.HTTP_201_CREATED)
async def create_offer(
    body: PriceOfferCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.expire_stale(db)
    ch = (await db.execute(
        select(Channel).where(Channel.id == body.channel_id).with_for_update()
    )).scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Лот не знайдено")
    if ch.status != ChannelStatus.approved:
        raise HTTPException(status_code=400, detail="Лот недоступний для пропозиції")
    if ch.seller_id == user.id:
        raise HTTPException(status_code=400, detail="Не можна пропонувати ціну за власний лот")
    from app.models.bundle import BundleChannel
    in_bundle = (await db.execute(
        select(BundleChannel.id).where(BundleChannel.channel_id == ch.id).limit(1)
    )).scalar_one_or_none()
    if in_bundle:
        raise HTTPException(status_code=400, detail="Для каналу в сітці пропозицію ціни не приймаємо")

    try:
        amount = svc.parse_amount(body.amount_usdt, ch.price)
        comment = svc.clean_comment(body.comment)
    except svc.OfferError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if await svc.active_for_lot(db, user.id, ch.id):
        raise HTTPException(status_code=400, detail="У вас уже є активна пропозиція по цьому лоту")
    if await svc.count_today(db, user.id) >= svc.MAX_PER_DAY:
        raise HTTPException(status_code=400, detail="Не більше 5 пропозицій на добу")

    now = utcnow_naive()
    offer = PriceOffer(
        channel_id=ch.id,
        buyer_id=user.id,
        seller_id=ch.seller_id,
        amount_usdt=amount,
        comment=comment,
        status=PriceOfferStatus.pending,
        expires_at=now + timedelta(hours=svc.TTL_HOURS),
        created_at=now,
    )
    db.add(offer)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="У вас уже є активна пропозиція по цьому лоту") from None
    await db.refresh(offer)

    seller = await db.get(User, ch.seller_id)
    await _notify_after_commit("received", offer, ch, user, seller)
    return _to_response(offer, ch, user, user.id)


@router.get("/my", response_model=list[PriceOfferResponse])
async def my_offers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.expire_stale(db)
    await db.commit()
    rows = (await db.execute(
        select(PriceOffer).where(PriceOffer.buyer_id == user.id).order_by(PriceOffer.created_at.desc())
    )).scalars().all()
    out = []
    for o in rows:
        ch, buyer = await _channel_buyer(db, o)
        out.append(_to_response(o, ch, buyer, user.id))
    return out


@router.get("/inbox", response_model=list[PriceOfferResponse])
async def seller_inbox(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
):
    """Seller-only inbox. Never returns offers for lots the caller does not own."""
    await svc.expire_stale(db)
    await db.commit()
    q = select(PriceOffer).where(PriceOffer.seller_id == user.id)
    if status_filter:
        if status_filter not in PriceOfferStatus.ALL:
            raise HTTPException(status_code=400, detail="Невідомий статус")
        q = q.where(PriceOffer.status == status_filter)
    rows = (await db.execute(q.order_by(PriceOffer.created_at.desc()))).scalars().all()
    out = []
    for o in rows:
        ch, buyer = await _channel_buyer(db, o)
        out.append(_to_response(o, ch, buyer, user.id))
    return out


@router.get("/{offer_id}", response_model=PriceOfferResponse)
async def get_offer(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.expire_stale(db)
    await db.commit()
    offer = await _load(db, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Пропозицію не знайдено")
    if user.id not in (offer.buyer_id, offer.seller_id):
        raise HTTPException(status_code=403, detail="Немає доступу до цієї пропозиції")
    ch, buyer = await _channel_buyer(db, offer)
    return _to_response(offer, ch, buyer, user.id)


@router.post("/{offer_id}/accept", response_model=PriceOfferResponse)
async def accept_offer(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.expire_stale(db)
    offer = (await db.execute(
        select(PriceOffer).where(PriceOffer.id == offer_id).with_for_update()
    )).scalar_one_or_none()
    if not offer:
        raise HTTPException(status_code=404, detail="Пропозицію не знайдено")
    if offer.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Прийняти може лише продавець лота")
    if offer.status == PriceOfferStatus.expired or offer.expires_at <= utcnow_naive():
        offer.status = PriceOfferStatus.expired
        await db.commit()
        raise HTTPException(status_code=400, detail="Термін дії пропозиції минув")
    if offer.status != PriceOfferStatus.pending:
        raise HTTPException(status_code=400, detail="Пропозицію вже розглянуто")

    ch = await db.get(Channel, offer.channel_id)
    if not ch or ch.status != ChannelStatus.approved:
        raise HTTPException(status_code=400, detail="Лот недоступний")
    busy = (await db.execute(
        select(Deal.id).where(Deal.channel_id == offer.channel_id, Deal.status.in_(ACTIVE_DEAL_STATUSES)).limit(1)
    )).scalar_one_or_none()
    if busy:
        raise HTTPException(status_code=400, detail="По цьому лоту вже є активна угода")

    now = utcnow_naive()
    offer.status = PriceOfferStatus.accepted
    offer.decided_at = now
    offer.accepted_at = now
    await db.commit()
    await db.refresh(offer)

    buyer = await db.get(User, offer.buyer_id)
    await _notify_after_commit("accepted", offer, ch, buyer, user)
    return _to_response(offer, ch, buyer, user.id)


@router.post("/{offer_id}/decline", response_model=PriceOfferResponse)
async def decline_offer(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.expire_stale(db)
    offer = (await db.execute(
        select(PriceOffer).where(PriceOffer.id == offer_id).with_for_update()
    )).scalar_one_or_none()
    if not offer:
        raise HTTPException(status_code=404, detail="Пропозицію не знайдено")
    if offer.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Відхилити може лише продавець лота")
    if offer.status == PriceOfferStatus.expired or offer.expires_at <= utcnow_naive():
        offer.status = PriceOfferStatus.expired
        await db.commit()
        raise HTTPException(status_code=400, detail="Термін дії пропозиції минув")
    if offer.status != PriceOfferStatus.pending:
        raise HTTPException(status_code=400, detail="Пропозицію вже розглянуто")

    offer.status = PriceOfferStatus.declined
    offer.decided_at = utcnow_naive()
    await db.commit()
    await db.refresh(offer)
    ch, buyer = await _channel_buyer(db, offer)
    return _to_response(offer, ch, buyer, user.id)
