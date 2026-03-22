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
    buyer_ready: bool = False
    seller_ready: bool = False
    buyer_confirmed_transfer: bool = False
    seller_confirmed_transfer: bool = False
    seller_payout_address: str | None = None
    payout_tx_hash: str | None = None
    created_at: datetime
    paid_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class DealDisputeRequest(BaseModel):
    reason: str


class DealResolveRequest(BaseModel):
    resolution: str  # "refund_buyer" or "release_seller"
    comment: str | None = None


class SellerWalletRequest(BaseModel):
    wallet_address: str


class DealMessageCreate(BaseModel):
    text: str


class DealMessageResponse(BaseModel):
    id: int
    deal_id: int
    sender_id: int
    sender_name: str | None = None
    text: str
    is_system: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
