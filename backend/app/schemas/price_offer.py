from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.utils.timeutil import UTCDateTime


class PriceOfferCreate(BaseModel):
    channel_id: int = Field(..., ge=1)
    amount_usdt: float
    comment: str | None = None

    @field_validator("comment")
    @classmethod
    def _comment(cls, v):
        if v is None:
            return None
        return str(v)


class PriceOfferResponse(BaseModel):
    id: int
    channel_id: int
    channel_name: str | None = None
    channel_avatar_url: str | None = None
    buyer_id: int
    buyer_name: str | None = None
    seller_id: int
    amount_usdt: float
    lot_price_usdt: float | None = None
    comment: str | None = None
    status: str
    expires_at: UTCDateTime
    created_at: UTCDateTime
    decided_at: datetime | None = None
    deal_id: int | None = None
    # True when this buyer can now create a deal at the agreed amount
    can_create_deal: bool = False
