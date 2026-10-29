import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    GoogleAuthData,
    RefreshRequest,
    TelegramAuthData,
    TokenResponse,
    UserResponse,
    MeResponse,
)
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_current_user_or_blocked,
    verify_telegram_auth,
    verify_token,
)

from app.services.moderation import ensure_login_allowed

router = APIRouter(prefix="/auth", tags=["auth"])


def _utm_apply(user, src) -> None:
    try:
        from app.services.utm import apply
        apply(user, src)
    except Exception:  # attribution must never block a login
        pass


async def _track_login(db, user_id: int) -> None:
    from app.services.user_activity import record_event_detached
    await record_event_detached("login", user_id=user_id)


@router.post("/telegram", response_model=TokenResponse)
async def telegram_login(data: TelegramAuthData, db: AsyncSession = Depends(get_db)):
    """Authenticate via Telegram Login Widget."""
    import logging
    logger = logging.getLogger(__name__)

    auth_dict = data.model_dump(exclude={"utm_source", "utm_campaign", "utm_content"})
    # Demo login bypasses Telegram signature verification — it exists only
    # for local frontend development (see the import.meta.env.DEV-gated
    # button in AuthModal.jsx, which always sends this fixed id). It must
    # never work in production, and even then only for that exact id —
    # otherwise anyone could hijack an arbitrary real account by POSTing
    # hash="demo" with that account's telegram_id directly to this endpoint.
    is_demo = (
        data.hash == "demo"
        and data.id == 123456789
        and not os.getenv("RAILWAY_ENVIRONMENT")
    )

    logger.info(f"[AUTH] Telegram login attempt: tg_id={data.id}, username={data.username}, first_name={data.first_name}, auth_date={data.auth_date}, has_photo={'yes' if data.photo_url else 'no'}, has_last_name={'yes' if data.last_name else 'no'}")

    if not is_demo and not verify_telegram_auth(auth_dict):
        # Log detailed debug info
        check_data = {k: v for k, v in auth_dict.items() if k != "hash" and v is not None}
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_data.items()))
        logger.warning(
            f"[AUTH] HASH MISMATCH for tg_id={data.id} ({data.username}). "
            f"auth_date={data.auth_date}, "
            f"check_keys={sorted(check_data.keys())}, "
            f"check_string_preview='{check_string[:200]}', "
            f"received_hash={data.hash[:16]}..."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram auth data — hash mismatch",
        )

    # Find or create user
    result = await db.execute(select(User).where(User.telegram_id == data.id))
    user = result.scalar_one_or_none()

    if not user:
        logger.info(f"[AUTH] Creating NEW user for tg_id={data.id} ({data.username})")
        user = User(
            telegram_id=data.id,
            username=data.username,
            first_name=data.first_name,
            avatar_url=data.photo_url,
        )
        _utm_apply(user, data)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"[AUTH] New user created: id={user.id}, tg_id={user.telegram_id}")
    else:
        logger.info(f"[AUTH] Existing user found: id={user.id}, tg_id={user.telegram_id}")
        # Update profile info
        user.username = data.username or user.username
        user.first_name = data.first_name or user.first_name
        user.avatar_url = data.photo_url or user.avatar_url
        await db.commit()
        await db.refresh(user)

    await ensure_login_allowed(db, user)
    await _track_login(db, user.id)
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    logger.info(f"[AUTH] Telegram login SUCCESS: user_id={user.id}, tg_id={user.telegram_id}, role={user.role}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/google", response_model=TokenResponse)
async def google_login(data: GoogleAuthData, db: AsyncSession = Depends(get_db)):
    """Authenticate via Google Sign-In."""
    import logging
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests

    logger = logging.getLogger(__name__)

    try:
        idinfo = id_token.verify_oauth2_token(
            data.credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError:
        logger.warning("Google auth: invalid ID token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    google_id = idinfo["sub"]
    email = idinfo.get("email")
    name = idinfo.get("name", email or "User")
    picture = idinfo.get("picture")

    # Find user by google_id or email
    result = await db.execute(
        select(User).where(or_(User.google_id == google_id, User.email == email))
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            google_id=google_id,
            email=email,
            first_name=name,
            avatar_url=picture,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Link google_id if user found by email but no google_id yet
        if not user.google_id:
            user.google_id = google_id
        user.email = email or user.email
        user.first_name = name or user.first_name
        user.avatar_url = picture or user.avatar_url
        await db.commit()
        await db.refresh(user)

    await ensure_login_allowed(db, user)
    await _track_login(db, user.id)
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/link/telegram", response_model=UserResponse)
async def link_telegram(
    data: TelegramAuthData,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link Telegram account to existing user (e.g. Google user)."""
    import logging
    logger = logging.getLogger(__name__)

    auth_dict = data.model_dump(exclude={"utm_source", "utm_campaign", "utm_content"})
    if not verify_telegram_auth(auth_dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram auth data")

    # Check if telegram_id already belongs to another user
    existing = await db.execute(select(User).where(User.telegram_id == data.id))
    existing_user = existing.scalar_one_or_none()

    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Цей Telegram вже прив'язаний до іншого аккаунту")

    current_user.telegram_id = data.id
    current_user.username = data.username or current_user.username
    if not current_user.avatar_url:
        current_user.avatar_url = data.photo_url
    await db.commit()
    await db.refresh(current_user)

    return UserResponse.model_validate(current_user)


# ── Bot-based auth (for switching Telegram accounts) ─────────────────

class BotTokenIn(BaseModel):
    anon: str | None = Field(None, max_length=128)
    utm_source: str | None = Field(None, max_length=200)
    utm_campaign: str | None = Field(None, max_length=200)
    utm_content: str | None = Field(None, max_length=200)


@router.post("/bot-token")
async def create_bot_auth_token(body: BotTokenIn | None = None):
    """Generate a one-time token for bot-based login. The visitor's anon id + first-touch UTM (optional)
    are bound to the token so registration is attributed even if the visitor never returns from Telegram."""
    from app.services.utm import fields
    from app.utils.activity_ids import hash_id
    from app.utils.auth_tokens import create_auth_token
    meta = {}
    if body is not None:
        meta = {**fields(body), "anon_hash": hash_id(body.anon)}
    token = create_auth_token(meta)
    bot_name = "tgsell_auth_bot"
    return {
        "token": token,
        "bot_link": f"https://t.me/{bot_name}?start=auth_{token}",
    }


@router.get("/bot-check")
async def check_bot_auth(token: str, utm_source: str | None = None, utm_campaign: str | None = None,
                         utm_content: str | None = None, anon: str | None = None,
                         db: AsyncSession = Depends(get_db)):
    """Poll this endpoint to check if bot auth completed."""
    from app.services.bot_auth import ensure_bot_user
    from app.services.utm import fields, record_event_detached
    from app.utils.activity_ids import hash_id
    from app.utils.auth_tokens import check_auth_token, consume_auth_token, get_meta

    # Non-destructive check first (polling every 2s)
    user_data = check_auth_token(token)
    if not user_data:
        return {"status": "pending"}

    meta = get_meta(token)
    # Auth completed — now consume (remove) the token
    user_data = consume_auth_token(token)
    if not user_data:
        return {"status": "pending"}

    q_utm = {"utm_source": utm_source, "utm_campaign": utm_campaign, "utm_content": utm_content}
    utm_src = q_utm if fields(q_utm) else meta  # site storage first, token-bound UTM as fallback
    user, _created = await ensure_bot_user(db, user_data, utm_src)
    await record_event_detached("login_success", hash_id(anon) or meta.get("anon_hash"), utm_src)

    await ensure_login_allowed(db, user)
    await _track_login(db, user.id)
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return {
        "status": "ok",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": UserResponse.model_validate(user).model_dump(),
    }


@router.get("/me", response_model=MeResponse)
async def get_me(user: User = Depends(get_current_user_or_blocked)):
    """Get current authenticated user (blocked users see their block reason)."""
    return MeResponse.model_validate(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh JWT tokens."""
    payload = verify_token(body.refresh_token, expected_type="refresh")
    user_id = payload.get("sub")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    await ensure_login_allowed(db, user)
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )
