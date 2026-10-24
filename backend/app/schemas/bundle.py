from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator


from app.utils.limits import check_max_price


class BundleChannelInfo(BaseModel):
    id: int
    channel_name: str
    telegram_link: str
    avatar_url: str | None = None
    subscribers_count: int = 0
    avg_views: int | None = None
    er: float | None = None
    category: str = ""
    stars_balance: int | None = None
    ton_balance: float | None = None
    is_closed: bool = False

    @model_validator(mode="after")
    def _sanitize_avatar(self):
        from app.utils.avatars import public_channel_avatar_url
        self.avatar_url = public_channel_avatar_url(self.id, self.avatar_url)
        return self

    model_config = {"from_attributes": True}


class ChannelBalanceIn(BaseModel):
    """Task 31: seller-stated per-channel balance in a bundle."""
    stars_balance: int | None = Field(default=None, ge=0, le=10**12)
    ton_balance: float | None = Field(default=None, ge=0, le=10**11)


class ChannelBalanceUpdate(ChannelBalanceIn):
    channel_id: int


class BundleBalancesUpdate(BaseModel):
    """Task 32: edit per-channel balances of an existing bundle."""
    channel_balances: list[ChannelBalanceUpdate] = Field(min_length=1, max_length=100)


class BundleCreate(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    price: float
    monthly_income: float | None = None
    resources: str | None = None
    channel_links: list[str]
    # Task 31: optional, aligned with channel_links by index
    channel_balances: list[ChannelBalanceIn | None] | None = None
    # Optional seller-stated subscriber counts, aligned with channel_links by index.
    # Used only for closed (invite-link) channels that can't be read automatically.
    channel_subscribers: list[int | None] | None = None

    @field_validator("channel_subscribers")
    @classmethod
    def validate_subscribers(cls, v):
        if v is None:
            return v
        for n in v:
            if n is not None and not (0 <= n <= 100_000_000):
                raise ValueError("subscribers must be between 0 and 100000000")
        return v

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
        return check_max_price(v)

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
    channel_balances: list[ChannelBalanceUpdate] | None = None


    @field_validator("price")
    @classmethod
    def _max_price(cls, v):
        return check_max_price(v)

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
    total_subscribers: int = 0
    avg_er: float | None = None

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
