"""Task 21: market price estimate for channel listings.

Metrics
  price_per_sub  = price / subscribers_count
  price_per_view = price / avg_views

Market reference = median price_per_sub / price_per_view per category over
approved listings plus completed deals (deal amount vs. the sold channel's
stats). Categories with fewer than MIN_CATEGORY_SAMPLES samples fall back to
the whole catalog (scope="catalog").

Excluded from the medians (and given verdict "unknown" themselves): closed
channels, 0 subscribers, price <= 0 (bundle lots / placeholders).

Fair range: each available metric gives an estimate (subs * median_pps,
views * median_ppv); their mean is the fair price, and the fair range is
fair * [1 - FAIR_BAND, 1 + FAIR_BAND] (±25%). Price below the range is
"cheaper", above "expensive", inside "fair".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

MIN_CATEGORY_SAMPLES = 3
FAIR_BAND = 0.25

VERDICT_CHEAPER = "cheaper"
VERDICT_FAIR = "fair"
VERDICT_EXPENSIVE = "expensive"
VERDICT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Sample:
    category: str
    price: float
    subscribers: int | None
    avg_views: int | None
    is_closed: bool = False


@dataclass
class MarketRef:
    pps: float | None = None  # median price per subscriber
    ppv: float | None = None  # median price per view
    samples: int = 0


@dataclass
class Market:
    by_category: dict[str, MarketRef] = field(default_factory=dict)
    catalog: MarketRef = field(default_factory=MarketRef)

    def ref_for(self, category: str | None) -> tuple[MarketRef, str]:
        ref = self.by_category.get(category or "")
        if ref is not None and ref.samples >= MIN_CATEGORY_SAMPLES:
            return ref, "category"
        return self.catalog, "catalog"


def is_priceable(price, subscribers, is_closed) -> bool:
    return bool(not is_closed and (price or 0) > 0 and (subscribers or 0) > 0)


def price_per_sub(price, subscribers, is_closed=False) -> float | None:
    if not is_priceable(price, subscribers, is_closed):
        return None
    return float(price) / subscribers


def price_per_view(price, subscribers, avg_views, is_closed=False) -> float | None:
    if not is_priceable(price, subscribers, is_closed) or not avg_views or avg_views <= 0:
        return None
    return float(price) / avg_views


def _ref(samples: list[Sample]) -> MarketRef:
    pps = [price_per_sub(s.price, s.subscribers, s.is_closed) for s in samples]
    ppv = [price_per_view(s.price, s.subscribers, s.avg_views, s.is_closed) for s in samples]
    pps = [v for v in pps if v is not None]
    ppv = [v for v in ppv if v is not None]
    return MarketRef(
        pps=median(pps) if pps else None,
        ppv=median(ppv) if ppv else None,
        samples=len(pps),
    )


def build_market(samples: list[Sample]) -> Market:
    valid = [s for s in samples if is_priceable(s.price, s.subscribers, s.is_closed)]
    cats: dict[str, list[Sample]] = {}
    for s in valid:
        cats.setdefault(s.category or "", []).append(s)
    return Market(by_category={c: _ref(v) for c, v in cats.items()}, catalog=_ref(valid))


def estimate(market: Market, *, category, price, subscribers, avg_views, is_closed) -> dict:
    out = {
        "price_per_sub": price_per_sub(price, subscribers, is_closed),
        "price_per_view": price_per_view(price, subscribers, avg_views, is_closed),
        "fair_price_range": None,
        "price_verdict": VERDICT_UNKNOWN,
        "price_reference_scope": None,
    }
    if out["price_per_sub"] is None:
        return out
    ref, scope = market.ref_for(category)
    estimates = []
    if ref.pps is not None:
        estimates.append(subscribers * ref.pps)
    if ref.ppv is not None and out["price_per_view"] is not None:
        estimates.append(avg_views * ref.ppv)
    if not estimates:
        return out
    fair = sum(estimates) / len(estimates)
    low, high = fair * (1 - FAIR_BAND), fair * (1 + FAIR_BAND)
    out["fair_price_range"] = [round(low, 2), round(high, 2)]
    out["price_reference_scope"] = scope
    if price < low:
        out["price_verdict"] = VERDICT_CHEAPER
    elif price > high:
        out["price_verdict"] = VERDICT_EXPENSIVE
    else:
        out["price_verdict"] = VERDICT_FAIR
    return out


async def load_market(db) -> Market:
    """Approved listings + completed deals → Market."""
    from sqlalchemy import select

    from app.models.channel import Channel, ChannelStatus
    from app.models.deal import Deal, DealStatus

    samples: list[Sample] = []
    rows = (await db.execute(
        select(Channel.category, Channel.price, Channel.subscribers_count, Channel.avg_views, Channel.is_closed)
        .where(Channel.status == ChannelStatus.approved)
    )).all()
    samples += [Sample(r[0], r[1] or 0, r[2], r[3], bool(r[4])) for r in rows]
    rows = (await db.execute(
        select(Channel.category, Deal.amount_usdt, Channel.subscribers_count, Channel.avg_views, Channel.is_closed)
        .join(Channel, Deal.channel_id == Channel.id)
        .where(Deal.status == DealStatus.completed)
    )).all()
    samples += [Sample(r[0], r[1] or 0, r[2], r[3], bool(r[4])) for r in rows]
    return build_market(samples)


def apply_estimate(resp, market: Market):
    """Fill pricing fields on a ChannelResponse in place."""
    for k, v in estimate(
        market, category=resp.category, price=resp.price, subscribers=resp.subscribers_count,
        avg_views=resp.avg_views, is_closed=resp.is_closed,
    ).items():
        setattr(resp, k, v)
    return resp
