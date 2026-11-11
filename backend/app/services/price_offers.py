"""Price offers: validation, expiry, anti-spam. Does not touch escrow or fees."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_offer import PriceOffer, PriceOfferStatus
from app.utils.timeutil import utcnow_naive

TTL_HOURS = 48
MIN_FRACTION = Decimal("0.50")
MAX_PER_DAY = 5
COMMENT_MAX = 300


class OfferError(ValueError):
    """User-facing Ukrainian validation error."""


def _cents(value: float | Decimal) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def offer_bounds(lot_price: float) -> tuple[int, int]:
    """Inclusive min cents and inclusive max cents (strictly below the lot price)."""
    price_cents = _cents(lot_price)
    if price_cents <= 0:
        raise OfferError("Лот без ціни")
    min_cents = int((Decimal(price_cents) * MIN_FRACTION).to_integral_value(rounding=ROUND_CEILING))
    max_cents = price_cents - 1
    if min_cents > max_cents:
        raise OfferError("Для цього лота не можна запропонувати нижчу ціну")
    return min_cents, max_cents


def parse_amount(amount, lot_price: float) -> float:
    try:
        raw = Decimal(str(amount))
    except Exception as exc:
        raise OfferError("Вкажіть суму в USDT") from exc
    if raw != raw or raw <= 0:
        raise OfferError("Вкажіть суму в USDT")
    # at most 2 decimal places
    if raw != raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) and raw.as_tuple().exponent < -2:
        raise OfferError("Сума має бути з точністю до 0,01 USDT")
    cents = _cents(raw)
    # reject more than 2 dp (e.g. 10.123 → 1012.3 cents would round; check exact)
    if (raw * 100) != Decimal(cents):
        # 10.123 rounds to 10.12; treat extra precision as invalid
        if raw.as_tuple().exponent < -2:
            raise OfferError("Сума має бути з точністю до 0,01 USDT")
    min_cents, max_cents = offer_bounds(lot_price)
    if cents > max_cents:
        raise OfferError("Пропозиція має бути нижчою за ціну лота")
    if cents < min_cents:
        raise OfferError("Пропозиція має бути не нижчою за 50% ціни лота")
    return float(Decimal(cents) / 100)


def clean_comment(comment: str | None) -> str | None:
    if comment is None:
        return None
    text = " ".join(str(comment).split())
    if not text:
        return None
    if len(text) > COMMENT_MAX:
        raise OfferError(f"Коментар до {COMMENT_MAX} символів")
    return text


async def expire_stale(db: AsyncSession, now=None) -> int:
    """Mark pending offers past expires_at as expired. Idempotent. No notifications."""
    now = now or utcnow_naive()
    res = await db.execute(
        update(PriceOffer)
        .where(PriceOffer.status == PriceOfferStatus.pending, PriceOffer.expires_at <= now)
        .values(status=PriceOfferStatus.expired)
        .execution_options(synchronize_session=False)
    )
    return res.rowcount or 0


async def count_today(db: AsyncSession, buyer_id: int, now=None) -> int:
    now = now or utcnow_naive()
    since = now - timedelta(hours=24)
    return int((await db.execute(
        select(func.count(PriceOffer.id)).where(
            PriceOffer.buyer_id == buyer_id,
            PriceOffer.created_at >= since,
        )
    )).scalar() or 0)


async def active_for_lot(db: AsyncSession, buyer_id: int, channel_id: int) -> PriceOffer | None:
    return (await db.execute(
        select(PriceOffer).where(
            PriceOffer.buyer_id == buyer_id,
            PriceOffer.channel_id == channel_id,
            PriceOffer.status == PriceOfferStatus.pending,
        )
    )).scalar_one_or_none()


logger = logging.getLogger(__name__)

CLOSE_REASON_LOT_IN_DEAL = "lot_in_deal"
ACCEPT_DEAL_TTL_HOURS = TTL_HOURS  # 48h after seller accepted to confirm the deal


def acceptance_deadline(offer) -> datetime | None:
    at = getattr(offer, "accepted_at", None) or getattr(offer, "decided_at", None)
    if not at:
        return None
    return at + timedelta(hours=ACCEPT_DEAL_TTL_HOURS)


def acceptance_still_valid(offer, now=None) -> bool:
    now = now or utcnow_naive()
    deadline = acceptance_deadline(offer)
    return bool(deadline and deadline >= now)


async def close_competing_offers(
    db: AsyncSession,
    channel_ids: list[int],
    *,
    keep_offer_id: int | None = None,
    now=None,
) -> list[PriceOffer]:
    """Close other pending / unused accepted offers on these lots. Same transaction as the deal."""
    ids = [int(x) for x in channel_ids if x]
    if not ids:
        return []
    now = now or utcnow_naive()
    q = select(PriceOffer).where(
        PriceOffer.channel_id.in_(ids),
        PriceOffer.status.in_((PriceOfferStatus.pending, PriceOfferStatus.accepted)),
        PriceOffer.deal_id.is_(None),
    )
    if keep_offer_id is not None:
        q = q.where(PriceOffer.id != keep_offer_id)
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return []
    ids = [offer.id for offer in rows]
    await db.execute(
        update(PriceOffer)
        .where(PriceOffer.id.in_(ids))
        .values(
            status=PriceOfferStatus.closed,
            close_reason=CLOSE_REASON_LOT_IN_DEAL,
            decided_at=func.coalesce(PriceOffer.decided_at, now),
        )
        .execution_options(synchronize_session=False)
    )
    # Detach so the deal flush does not have to sort a stale PriceOffer mapper.
    for offer in rows:
        offer.status = PriceOfferStatus.closed
        offer.close_reason = CLOSE_REASON_LOT_IN_DEAL
        if offer.decided_at is None:
            offer.decided_at = now
        db.expunge(offer)
    return list(rows)


async def notify_offers_closed(offers: list[PriceOffer], db: AsyncSession) -> None:
    """After commit. Participant messages only; failure must not affect the deal."""
    if not offers:
        return
    try:
        from aiogram import Bot
        from app.config import settings
        from app.models.channel import Channel
        from app.models.user import User
        from bot.main import notify_price_offer_closed

        if not getattr(settings, "bot_token_alerts", None):
            return
        bot = Bot(token=settings.bot_token_alerts)
        try:
            for offer in offers:
                buyer = await db.get(User, offer.buyer_id)
                channel = await db.get(Channel, offer.channel_id)
                await notify_price_offer_closed(bot, offer, channel, buyer)
        finally:
            await bot.session.close()
    except Exception as e:
        logger.warning("[OFFER] close-notify failed for %s offer(s): %s", len(offers), e)
