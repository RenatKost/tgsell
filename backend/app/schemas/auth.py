from datetime import datetime

from pydantic import BaseModel


class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


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

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
