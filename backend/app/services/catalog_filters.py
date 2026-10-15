"""Shared catalog filter application (list endpoint + saved searches)."""
from __future__ import annotations

from app.models.channel import Channel

# Catalog filters shared by the list endpoint and saved-search matching (Task 24).
CATALOG_FILTER_KEYS = (
    "search", "category", "min_price", "max_price", "roi_max", "er_min", "verified_data",
    "ai_recommended", "pps_min", "pps_max", "no_inflation", "min_subscribers", "max_subscribers",
)


def apply_catalog_filters(query, f: dict):
    g = f.get
    if g("search"):
        query = query.where(Channel.channel_name.ilike(f"%{g('search')}%"))
    if g("category"):
        query = query.where(Channel.category == g("category"))
    if g("min_price") is not None:
        query = query.where(Channel.price >= g("min_price"))
    if g("max_price") is not None:
        query = query.where(Channel.price <= g("max_price"))
    if g("min_subscribers") is not None:
        query = query.where(Channel.subscribers_count >= g("min_subscribers"))
    if g("max_subscribers") is not None:
        query = query.where(Channel.subscribers_count <= g("max_subscribers"))
    if g("er_min") is not None:
        query = query.where(Channel.er >= g("er_min"))
    if g("roi_max") is not None:
        # ROI months = price / monthly_income — only for channels with monthly_income > 0
        query = query.where(Channel.monthly_income > 0)
        query = query.where(Channel.price / Channel.monthly_income <= g("roi_max"))
    if g("verified_data"):
        query = query.where(
            Channel.avg_views.is_not(None),
            Channel.er.is_not(None),
            Channel.is_closed.is_(False),
        )
    if g("ai_recommended"):
        query = query.where(
            Channel.er >= 15,
            Channel.monthly_income > 0,
            Channel.price / Channel.monthly_income <= 12,
        )
    pps_expr = Channel.price / Channel.subscribers_count
    priceable = (Channel.subscribers_count > 0) & (Channel.price > 0) & Channel.is_closed.is_(False)
    if g("pps_min") is not None or g("pps_max") is not None:
        query = query.where(priceable)
        if g("pps_min") is not None:
            query = query.where(pps_expr >= g("pps_min"))
        if g("pps_max") is not None:
            query = query.where(pps_expr <= g("pps_max"))
    if g("no_inflation"):
        query = query.where(Channel.quality_health == "clean")
    return query


