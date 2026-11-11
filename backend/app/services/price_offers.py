"""Price offers: validation, expiry, anti-spam. Does not touch escrow or fees."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_offer import PriceOffer, PriceOfferStatus
from app.utils.timeutil import utcnow_naive

TTL_HOURS = 48
MIN_FRACTION = Decimal("0.30")
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
        raise OfferError("Пропозиція має бути не нижчою за 30% ціни лота")
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
