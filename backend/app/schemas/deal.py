from datetime import datetime

from pydantic import BaseModel


class DealCreate(BaseModel):
    channel_id: int


class DealResponse(BaseModel):
    id: int
    channel_id: int
    buyer_id: int
    seller_id: int
    channel_name: str | None = None
    buyer_name: str | None = None
    seller_name: str | None = None
    status: str
    escrow_wallet_address: str
    amount_usdt: float
    service_fee: float
    deal_group_chat_id: int | None
    dispute_reason: str | None
    created_at: datetime
    paid_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class DealDisputeRequest(BaseModel):
    reason: str


class DealResolveRequest(BaseModel):
    resolution: str  # "refund_buyer" or "release_seller"
    comment: str | None = None
