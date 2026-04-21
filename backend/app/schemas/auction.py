from datetime import datetime

from pydantic import BaseModel


class AuctionBidCreate(BaseModel):
    amount: float


class AuctionBidResponse(BaseModel):
    id: int
    auction_id: int
    bidder_id: int
    bidder_name: str | None = None
    amount: float
    created_at: datetime

    model_config = {"from_attributes": True}


class AuctionResponse(BaseModel):
    id: int
    channel_id: int
    seller_id: int
    start_price: float
    bid_step: float
    current_price: float
    buyout_price: float | None
    status: str
    starts_at: datetime
    ends_at: datetime
    winner_id: int | None
    bid_count: int
    created_at: datetime

    # Joined channel info
    channel_name: str | None = None
    channel_avatar: str | None = None
    subscribers_count: int | None = None
    category: str | None = None
    avg_views: int | None = None
    er: float | None = None
    monthly_income: float | None = None
    age: str | None = None
    views_hidden: bool = False

    model_config = {"from_attributes": True}


class AuctionListResponse(BaseModel):
    items: list[AuctionResponse]
    total: int


class AuctionDetailResponse(AuctionResponse):
    bids: list[AuctionBidResponse] = []
