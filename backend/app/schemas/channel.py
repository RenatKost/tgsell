from datetime import datetime

from pydantic import BaseModel, Field, model_validator


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
    # Closed (join-request) channels: bot can't auto-read these, so the
    # seller reports stats manually. Only applied server-side when
    # is_closed=True — ignored for normal open channels.
    is_closed: bool = False
    subscribers_count: int | None = None
    avg_views: int | None = None
    er: float | None = None
    # Task 31: seller-stated balance (optional, >= 0; "зі слів продавця")
    stars_balance: int | None = Field(default=None, ge=0, le=10**12)
    ton_balance: float | None = Field(default=None, ge=0, le=10**11)
    # «Шукаю канал»: lot created via «У мене є такий канал»
    wanted_request_id: int | None = None


class ChannelUpdate(BaseModel):
    channel_name: str | None = None
    seller_telegram: str | None = None
    category: str | None = None
    price: float | None = None
    monthly_income: float | None = None
    description: str | None = None
    resources: str | None = None
    is_closed: bool | None = None
    subscribers_count: int | None = None
    avg_views: int | None = None
    er: float | None = None
    # Task 31: seller-stated balance (optional, >= 0; "зі слів продавця")
    stars_balance: int | None = Field(default=None, ge=0, le=10**12)
    ton_balance: float | None = Field(default=None, ge=0, le=10**11)


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
    growth_7d: int | None = None
    growth_30d: int | None = None
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
    is_closed: bool = False
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
    # Task 21: price estimate (populated at runtime by app.services.pricing)
    price_per_sub: float | None = None
    price_per_view: float | None = None
    fair_price_range: list[float] | None = None
    price_verdict: str = "unknown"  # cheaper / fair / expensive / inflated / unknown
    moderation_flags: list[str] = []  # task 33: staff-only info flags (filled in /admin/channels/pending)
    price_reference_scope: str | None = None  # category / overall
    # Task 22: quality index (None = «мало даних»)
    quality_score: int | None = None
    quality_health: str | None = None  # clean / suspicious / insufficient
    quality_breakdown: dict | None = None
    quality_updated_at: datetime | None = None
    # Task 31: seller-stated balance (display only)
    stars_balance: int | None = None
    ton_balance: float | None = None
    # Admin-set warning for buyers (migration 0046)
    buyer_warning: str | None = None

    @model_validator(mode="after")
    def _sanitize_avatar(self):
        from app.utils.avatars import public_channel_avatar_url
        self.avatar_url = public_channel_avatar_url(self.id, self.avatar_url)
        return self

    model_config = {"from_attributes": True}


class ChannelStatsResponse(BaseModel):
    id: int
    channel_id: int
    date: datetime
    subscribers: int | None = None
    avg_views: int
    avg_reach: int
    er: float | None = None
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
