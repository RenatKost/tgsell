from datetime import datetime

from pydantic import BaseModel, model_validator


class DealCreate(BaseModel):
    channel_id: int | None = None
    bundle_id: int | None = None


class DealResponse(BaseModel):
    id: int
    channel_id: int | None = None
    bundle_id: int | None = None
    buyer_id: int
    seller_id: int
    channel_name: str | None = None
    channel_avatar_url: str | None = None
    channel_link: str | None = None
    bundle_name: str | None = None
    bundle_channel_count: int | None = None
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

    @model_validator(mode="after")
    def _sanitize_avatar(self):
        from app.utils.avatars import public_channel_avatar_url, scrub_leaked_avatar_url
        if self.channel_id is not None:
            self.channel_avatar_url = public_channel_avatar_url(
                self.channel_id, self.channel_avatar_url
            )
        else:
            self.channel_avatar_url = scrub_leaked_avatar_url(self.channel_avatar_url)
        return self

    model_config = {"from_attributes": True}


class DealDisputeRequest(BaseModel):
    reason: str


class DealResolveRequest(BaseModel):
    resolution: str  # "refund_buyer" or "release_seller"
    comment: str | None = None
    wallet_address: str | None = None  # optional override if user wallet missing


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


# ── Transfer checklist ───────────────────────────────────────────────

class ChecklistItemResponse(BaseModel):
    key: str
    side: str
    label: str
    hint: str | None = None
    required: bool = True
    done: bool = False
    done_by: int | None = None
    done_at: datetime | None = None
    auto_verified: bool | None = None
    auto_note: str | None = None
    auto_checked_at: datetime | None = None


class ChecklistSideResponse(BaseModel):
    side: str
    label: str
    items: list[ChecklistItemResponse]
    required_total: int
    required_done: int
    confirmed: bool


class DealChecklistResponse(BaseModel):
    deal_id: int
    status: str
    active: bool  # True while status is paid/channel_transferring
    my_side: str | None = None
    can_edit: bool = False
    seller: ChecklistSideResponse
    buyer: ChecklistSideResponse
    all_required_done: bool
    last_activity_at: datetime | None = None
    telethon_available: bool = False
    auto_verify_message: str | None = None


class ChecklistToggleRequest(BaseModel):
    done: bool | None = None  # None → toggle
