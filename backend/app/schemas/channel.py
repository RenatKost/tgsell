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

    model_config = {"from_attributes": True}


class ChannelListResponse(BaseModel):
    items: list[ChannelResponse]
    total: int
    total_pages: int
    page: int
