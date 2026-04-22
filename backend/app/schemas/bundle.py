from datetime import datetime
from pydantic import BaseModel, field_validator


class BundleChannelInfo(BaseModel):
    id: int
    channel_name: str
    telegram_link: str
    avatar_url: str | None = None
    subscribers_count: int = 0
    avg_views: int | None = None
    er: float | None = None
    category: str = ""

    model_config = {"from_attributes": True}


class BundleCreate(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    price: float
    monthly_income: float | None = None
    resources: str | None = None
    channel_links: list[str]

    @field_validator("channel_links")
    @classmethod
    def validate_links(cls, v: list[str]) -> list[str]:
        cleaned = []
        for link in v:
            link = link.strip()
            if link:
                cleaned.append(link)
        if len(cleaned) < 2:
            raise ValueError("Minimum 2 channel links required")
        if len(cleaned) > 20:
            raise ValueError("Maximum 20 channel links allowed")
        return cleaned

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Price must be positive")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


class BundleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    price: float | None = None
    monthly_income: float | None = None
    resources: str | None = None


class BundleResponse(BaseModel):
    id: int
    seller_id: int
    name: str
    description: str | None = None
    category: str | None = None
    price: float
    monthly_income: float | None = None
    resources: str | None = None
    status: str
    rejection_reason: str | None = None
    created_at: datetime
    moderated_at: datetime | None = None
    channels: list[BundleChannelInfo] = []
    channel_count: int = 0

    model_config = {"from_attributes": True}


class BundleListResponse(BaseModel):
    items: list[BundleResponse]
    total: int
    total_pages: int
    page: int


class BundleStatsResponse(BaseModel):
    bundle_id: int
    total_subscribers: int
    total_monthly_income: float
    avg_er: float
    avg_views: int
    channel_count: int
    channels: list[BundleChannelInfo]
