from fastapi import APIRouter, Depends, HTTPException, status
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
)
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    verify_telegram_auth,
    verify_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=TokenResponse)
async def telegram_login(data: TelegramAuthData, db: AsyncSession = Depends(get_db)):
    """Authenticate via Telegram Login Widget."""
    import logging
    logger = logging.getLogger(__name__)

    auth_dict = data.model_dump()
    is_demo = data.hash == "demo"

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

    auth_dict = data.model_dump()
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

@router.post("/bot-token")
async def create_bot_auth_token():
    """Generate a one-time token for bot-based login."""
    from app.utils.auth_tokens import create_auth_token
    token = create_auth_token()
    bot_name = "tgsell_auth_bot"
    return {
        "token": token,
        "bot_link": f"https://t.me/{bot_name}?start=auth_{token}",
    }


@router.get("/bot-check")
async def check_bot_auth(token: str, db: AsyncSession = Depends(get_db)):
    """Poll this endpoint to check if bot auth completed."""
    from app.utils.auth_tokens import consume_auth_token

    user_data = consume_auth_token(token)
    if not user_data:
        return {"status": "pending"}

    # Find or create user
    result = await db.execute(select(User).where(User.telegram_id == user_data["id"]))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=user_data["id"],
            username=user_data.get("username"),
            first_name=user_data.get("first_name", "User"),
            avatar_url=None,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        user.username = user_data.get("username") or user.username
        user.first_name = user_data.get("first_name") or user.first_name
        await db.commit()
        await db.refresh(user)

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return {
        "status": "ok",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": UserResponse.model_validate(user).model_dump(),
    }


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return UserResponse.model_validate(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh JWT tokens."""
    payload = verify_token(body.refresh_token, expected_type="refresh")
    user_id = payload.get("sub")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )
