from datetime import datetime

from pydantic import BaseModel


class ChannelCreate(BaseModel):
    telegram_link: str
    channel_name: str = ""
    seller_telegram: str | None = None
    category: str
    price: float
    monthly_income: float | None = None
    description: str | None = None
    resources: str | None = None
    listing_type: str = "sale"
    auction_start_price: float | None = None
    auction_bid_step: float | None = None
    auction_duration_hours: int | None = None


class ChannelUpdate(BaseModel):
    channel_name: str | None = None
    seller_telegram: str | None = None
    category: str | None = None
    price: float | None = None
    monthly_income: float | None = None
    description: str | None = None
    resources: str | None = None


class ChannelResponse(BaseModel):
    id: int
    seller_id: int
    telegram_link: str
    channel_name: str
    seller_telegram: str | None
    category: str
    subscribers_count: int
    price: float
    monthly_income: float | None
    description: str | None
    resources: str | None
    avatar_url: str | None
    avg_views: int | None
    er: float | None
    daily_growth: int | None
    age: str | None
    adv_reach_12h: int | None
    adv_reach_24h: int | None
    adv_reach_48h: int | None
    total_posts: int | None = None
    post_frequency: float | None = None
    last_post_date: datetime | None = None
    avg_forwards: int | None = None
    avg_reactions: int | None = None
    views_hidden: bool = False
    listing_type: str = "sale"
    auction_start_price: float | None = None
    auction_bid_step: float | None = None
    auction_duration_hours: int | None = None
    status: str
    created_at: datetime
    # Active auction data (populated at runtime if available)
    active_auction_id: int | None = None
    active_auction_price: float | None = None
    active_auction_ends_at: datetime | None = None
    # Bundle info (populated at runtime if channel is part of a bundle)
    bundle_id: int | None = None
    bundle_name: str | None = None

    model_config = {"from_attributes": True}


class ChannelStatsResponse(BaseModel):
    id: int
    channel_id: int
    date: datetime
    subscribers: int
    avg_views: int
    avg_reach: int
    er: float
    post_count: int | None = 0
    avg_forwards: int | None = 0
    avg_reactions: int | None = 0

    model_config = {"from_attributes": True}


class ChannelPostResponse(BaseModel):
    id: int
    channel_id: int
    telegram_msg_id: int
    date: datetime
    text: str | None = None
    media_type: str | None = None
    link: str | None = None
    views: int = 0
    views_1h: int | None = None
    views_12h: int | None = None
    views_24h: int | None = None
    views_48h: int | None = None
    forwards: int = 0
    reactions: int = 0
    comments: int = 0
    is_deleted: bool = False

    model_config = {"from_attributes": True}


class ChannelPostsListResponse(BaseModel):
    items: list[ChannelPostResponse]
    total: int


class ChannelListResponse(BaseModel):
    items: list[ChannelResponse]
    total: int
    total_pages: int
    page: int


class ChannelHealthResponse(BaseModel):
    """Bot detection & channel health analysis."""
    # Overall score 0-100 (higher = healthier)
    health_score: int = 0
    health_label: str = "Невідомо"  # Здоровий / Підозрілий / Мертвий

    # View velocity analysis
    views_1h_ratio: float | None = None  # % of total views gained in 1st hour
    view_velocity_label: str = "Невідомо"  # Нормально / Підозріло / Накрутка

    # Subscriber-to-views ratio (engagement)
    views_to_subs_ratio: float | None = None  # avg_views / subscribers * 100
    activity_label: str = "Невідомо"  # Активний / Низька активність / Мертвий

    # ER analysis
    er: float | None = None
    er_label: str = "Невідомо"

    # Posts consistency
    avg_views: int | None = None
    subscribers: int | None = None
    posts_analyzed: int = 0
    suspicious_posts: int = 0  # posts with bot-like view patterns

    # Detailed flags
    flags: list[str] = []  # textual warnings
