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
    status: str
    created_at: datetime

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
