from datetime import datetime

from pydantic import BaseModel, model_validator


class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str
    utm_source: str | None = None  # UTM first-touch kept by the site (not part of the Telegram hash)
    utm_campaign: str | None = None
    utm_content: str | None = None


class GoogleAuthData(BaseModel):
    credential: str  # Google ID token from frontend


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    telegram_id: int | None
    google_id: str | None = None
    email: str | None = None
    username: str | None
    first_name: str
    avatar_url: str | None
    role: str
    usdt_wallet: str | None
    created_at: datetime
    is_blocked: bool = False
    alert_bot_started: bool = False

    @model_validator(mode="after")
    def _sanitize_avatar(self):
        from app.utils.avatars import scrub_leaked_avatar_url
        self.avatar_url = scrub_leaked_avatar_url(self.avatar_url)
        return self

    model_config = {"from_attributes": True}


class PublicUserProfile(BaseModel):
    """Profile visible to anyone (GET /api/users/{id}/profile). No PII: never add
    telegram_id / google_id / email / usdt_wallet / blocked_reason here."""

    id: int
    username: str | None = None
    first_name: str
    avatar_url: str | None = None
    created_at: datetime
    is_blocked: bool = False
    # Reputation-style public counters (there is no reviews table yet).
    channels_listed: int = 0
    deals_completed_as_seller: int = 0
    deals_completed_as_buyer: int = 0

    @model_validator(mode="after")
    def _sanitize_avatar(self):
        from app.utils.avatars import scrub_leaked_avatar_url
        self.avatar_url = scrub_leaked_avatar_url(self.avatar_url)
        return self

    model_config = {"from_attributes": True}


class OwnerUserProfile(PublicUserProfile):
    """Same endpoint, but the viewer is the profile owner or an admin."""

    telegram_id: int | None = None
    google_id: str | None = None
    email: str | None = None
    usdt_wallet: str | None = None
    role: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class MeResponse(UserResponse):
    """Own profile: includes the block reason (never exposed on public profiles)."""

    blocked_reason: str | None = None
