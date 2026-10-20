"""Task 21 (v2): listing price estimate against an external market baseline.

Baseline = backend/app/data/market_prices.json: median $/subscriber (pps) and
$/view (ppv) per segment from the @tumobog_bir market table (158 lots),
plus a mapping from our categories to those segments. Update the JSON to
refresh the baseline; no code change is needed.

Hook for real TgSell deals: completed deals (deal amount vs. channel stats)
are blended into a segment's medians as a weighted median, each deal counting
DEAL_WEIGHT times, the baseline counting its sample size n. Deals only start
affecting a segment once it has at least MIN_DEALS of them.

Rules
- Unpriceable (closed, 0 subs, price <= 0) -> "unknown".
- Views are used only when fresh: not hidden and the last post is not older
  than FRESH_VIEWS_DAYS. Fresh views/subs < MIN_VIEW_RATIO (2%) -> "inflated"
  (likely bought subs) in every category.
- Task 33: views/subs > MAX_VIEW_RATIO is NOT an auto-verdict any more (reach
  channels — jobs, regional, classifieds — legitimately get views from search
  and forwards). Outside HIGH_REACH_CATEGORIES it only raises an info flag for
  moderators (see high_views_flag); inside them the upper threshold is skipped.
- Fair price = median of the available estimates (subs*pps, views*ppv),
  range = fair ±FAIR_BAND.
- Price differs from fair by more than MAX_RATIO (3x) either way -> numbers
  hidden, verdict "unknown" (estimate is not trustworthy for this lot).
- Category without mapping -> overall median is used for the badge only;
  fair_price_range is not exposed (scope "overall").
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "market_prices.json"

FAIR_BAND = 0.25
MAX_RATIO = 3.0
MIN_VIEW_RATIO = 0.02
MAX_VIEW_RATIO = 1.5
FRESH_VIEWS_DAYS = 30
DEAL_WEIGHT = 5
MIN_DEALS = 3

# Task 33: categories where views > subscribers is normal (existing category values).
# vacancies/jobs → «Вакансія/Робота»; regional → «Регіональні»; classifieds/ads and
# shops → «Товари/Магазини». Events/afisha has no category yet; the aliases below
# are accepted if such categories are added later.
HIGH_REACH_CATEGORIES = frozenset({
    "Вакансія/Робота", "Регіональні", "Товари/Магазини",
    "Афіша/Події", "Афіша", "Події", "Оголошення",
})
HIGH_VIEWS_FLAG = "переглядів більше за підписників — перевірте джерела"

VERDICT_CHEAPER = "cheaper"
VERDICT_FAIR = "fair"
VERDICT_EXPENSIVE = "expensive"
VERDICT_INFLATED = "inflated"
VERDICT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Sample:
    """A real TgSell completed deal (hook for weighting)."""
    category: str
    price: float
    subscribers: int | None
    avg_views: int | None
    is_closed: bool = False


@dataclass
class MarketRef:
    pps: float | None = None
    ppv: float | None = None
    samples: int = 0


@dataclass
class Market:
    by_segment: dict[str, MarketRef] = field(default_factory=dict)
    overall: MarketRef = field(default_factory=MarketRef)
    category_map: dict[str, str] = field(default_factory=dict)

    def ref_for(self, category: str | None) -> tuple[MarketRef, str]:
        seg = self.category_map.get(category or "")
        ref = self.by_segment.get(seg) if seg else None
        if ref is not None and ref.pps is not None:
            return ref, "category"
        return self.overall, "overall"


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


def _weighted_median(pairs: list[tuple[float, float]]) -> float | None:
    pairs = sorted((v, w) for v, w in pairs if v is not None and w > 0)
    if not pairs:
        return None
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return v
    return pairs[-1][0]


def load_baseline(path: Path = DATA_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_market(baseline: dict | None = None, deals: list[Sample] | None = None) -> Market:
    baseline = baseline if baseline is not None else load_baseline()
    cmap = dict(baseline.get("category_map", {}))
    o = baseline.get("overall", {})
    overall = MarketRef(o.get("pps"), o.get("ppv"), int(o.get("n", 0)))
    segs = {k: MarketRef(v.get("pps"), v.get("ppv"), int(v.get("n", 0)))
            for k, v in baseline.get("segments", {}).items()}

    by_seg: dict[str, list[Sample]] = {}
    for d in deals or []:
        seg = cmap.get(d.category or "")
        if seg in segs and is_priceable(d.price, d.subscribers, d.is_closed):
            by_seg.setdefault(seg, []).append(d)
    for seg, ds in by_seg.items():
        if len(ds) < MIN_DEALS:
            continue
        ref = segs[seg]
        pps = [(ref.pps, ref.samples)] + [(price_per_sub(d.price, d.subscribers), DEAL_WEIGHT) for d in ds]
        ppv = [(ref.ppv, ref.samples)] + [
            (price_per_view(d.price, d.subscribers, d.avg_views), DEAL_WEIGHT) for d in ds]
        segs[seg] = MarketRef(_weighted_median(pps), _weighted_median(ppv), ref.samples + len(ds))
    return Market(by_segment=segs, overall=overall, category_map=cmap)


def fresh_views(avg_views, views_hidden=False, last_post_date=None, now=None) -> int | None:
    if views_hidden or not avg_views or avg_views <= 0:
        return None
    if last_post_date is not None:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        lp = last_post_date.replace(tzinfo=None) if last_post_date.tzinfo else last_post_date
        if now - lp > timedelta(days=FRESH_VIEWS_DAYS):
            return None
    return int(avg_views)


def estimate(market: Market, *, category, price, subscribers, avg_views, is_closed,
             views_hidden=False, last_post_date=None, now=None) -> dict:
    out = {
        "price_per_sub": price_per_sub(price, subscribers, is_closed),
        "price_per_view": None,
        "fair_price_range": None,
        "price_verdict": VERDICT_UNKNOWN,
        "price_reference_scope": None,
    }
    if out["price_per_sub"] is None:
        return out
    views = fresh_views(avg_views, views_hidden, last_post_date, now)
    out["price_per_view"] = price_per_view(price, subscribers, views, is_closed)
    if views is not None:
        ratio = views / subscribers
        if ratio < MIN_VIEW_RATIO:
            out["price_verdict"] = VERDICT_INFLATED
            return out
    ref, scope = market.ref_for(category)
    estimates = []
    if ref.pps is not None:
        estimates.append(subscribers * ref.pps)
    if ref.ppv is not None and views is not None:
        estimates.append(views * ref.ppv)
    if not estimates:
        return out
    fair = median(estimates)
    if fair <= 0 or price > fair * MAX_RATIO or price < fair / MAX_RATIO:
        return out  # too far from the market: not trustworthy, hide numbers
    low, high = fair * (1 - FAIR_BAND), fair * (1 + FAIR_BAND)
    out["price_reference_scope"] = scope
    if scope == "category":
        out["fair_price_range"] = [round(low, 2), round(high, 2)]
    if price < low:
        out["price_verdict"] = VERDICT_CHEAPER
    elif price > high:
        out["price_verdict"] = VERDICT_EXPENSIVE
    else:
        out["price_verdict"] = VERDICT_FAIR
    return out


def upper_threshold_applies(category) -> bool:
    return (category or "") not in HIGH_REACH_CATEGORIES


def high_views_flag(*, category, subscribers, avg_views, is_closed=False,
                    views_hidden=False, last_post_date=None, now=None) -> str | None:
    """Moderator-only info flag (no verdict): fresh views/subs > MAX_VIEW_RATIO
    outside HIGH_REACH_CATEGORIES."""
    if is_closed or not subscribers or subscribers <= 0 or not upper_threshold_applies(category):
        return None
    views = fresh_views(avg_views, views_hidden, last_post_date, now)
    if views is not None and views / subscribers > MAX_VIEW_RATIO:
        return HIGH_VIEWS_FLAG
    return None


async def load_market(db) -> Market:
    """Market baseline (JSON) + completed TgSell deals as weighted samples."""
    from sqlalchemy import select

    from app.models.channel import Channel
    from app.models.deal import Deal, DealStatus

    rows = (await db.execute(
        select(Channel.category, Deal.amount_usdt, Channel.subscribers_count, Channel.avg_views, Channel.is_closed)
        .join(Channel, Deal.channel_id == Channel.id)
        .where(Deal.status == DealStatus.completed)
    )).all()
    deals = [Sample(r[0], r[1] or 0, r[2], r[3], bool(r[4])) for r in rows]
    return build_market(deals=deals)


def apply_estimate(resp, market: Market):
    """Fill pricing fields on a ChannelResponse in place."""
    for k, v in estimate(
        market, category=resp.category, price=resp.price, subscribers=resp.subscribers_count,
        avg_views=resp.avg_views, is_closed=resp.is_closed,
        views_hidden=getattr(resp, "views_hidden", False), last_post_date=getattr(resp, "last_post_date", None),
    ).items():
        setattr(resp, k, v)
    return resp
