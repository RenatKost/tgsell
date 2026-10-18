"""PR A (security): GET /api/users/{id}/profile must not leak PII to anonymous/other users.

Private fields (telegram_id, google_id, email, usdt_wallet, role) are returned only to the
profile owner or an admin (role == admin, same rule as get_superadmin_user).
"""
from __future__ import annotations

import pytest

PRIVATE = {"telegram_id", "google_id", "email", "usdt_wallet", "role", "blocked_reason"}


async def _setup(orm):
    import httpx
    from fastapi import FastAPI

    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    from app.routers import users as users_router
    from app.utils.security import create_access_token, create_refresh_token

    async with orm.session() as db:
        owner = User(first_name="Owner", username="owner", telegram_id=555001, google_id="g-555",
                     email="owner@example.com", usdt_wallet="TOwnerWallet111", role=UserRole.user)
        other = User(first_name="Other", telegram_id=555002, role=UserRole.user)
        admin = User(first_name="Admin", telegram_id=555003, role=UserRole.admin)
        moder = User(first_name="Moder", telegram_id=555004, role=UserRole.moderator)
        db.add_all([owner, other, admin, moder])
        await db.flush()
        db.add(Channel(seller_id=owner.id, telegram_link="https://t.me/x", channel_name="X",
                       category="news", price=10, status=ChannelStatus.approved))
        await db.commit()
        ids = {"owner": owner.id, "other": other.id, "admin": admin.id, "moder": moder.id}

    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    def hdr(who=None, token=None):
        if token is not None:
            return {"Authorization": f"Bearer {token}"}
        if who is None:
            return {}
        return {"Authorization": f"Bearer {create_access_token({'sub': str(ids[who])})}"}

    return client, ids, hdr, create_refresh_token


@pytest.mark.asyncio
async def test_anonymous_gets_public_fields_only(pg_orm):
    client, ids, hdr, _ = await _setup(pg_orm)
    async with client:
        r = await client.get(f"/api/users/{ids['owner']}/profile")
    assert r.status_code == 200
    body = r.json()
    assert not (PRIVATE & body.keys()), body
    assert body["id"] == ids["owner"] and body["username"] == "owner" and body["first_name"] == "Owner"
    assert {"avatar_url", "created_at", "deals_completed_as_seller", "channels_listed"} <= body.keys()
    assert body["channels_listed"] == 1
    raw = r.text
    for secret in ("owner@example.com", "g-555", "555001", "TOwnerWallet111"):
        assert secret not in raw


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["other", "moder"])
async def test_other_user_and_moderator_get_public_only(pg_orm, who):
    client, ids, hdr, _ = await _setup(pg_orm)
    async with client:
        r = await client.get(f"/api/users/{ids['owner']}/profile", headers=hdr(who))
    assert r.status_code == 200
    assert not (PRIVATE & r.json().keys())


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["garbage", "a.b.c"])
async def test_invalid_token_is_anonymous_not_error(pg_orm, token):
    client, ids, hdr, _ = await _setup(pg_orm)
    async with client:
        r = await client.get(f"/api/users/{ids['owner']}/profile", headers=hdr(token=token))
    assert r.status_code == 200
    assert not (PRIVATE & r.json().keys())


@pytest.mark.asyncio
async def test_refresh_token_does_not_unlock_private_fields(pg_orm):
    client, ids, hdr, make_refresh = await _setup(pg_orm)
    async with client:
        r = await client.get(f"/api/users/{ids['owner']}/profile",
                             headers=hdr(token=make_refresh({"sub": str(ids["owner"])})))
    assert r.status_code == 200
    assert not (PRIVATE & r.json().keys())


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["owner", "admin"])
async def test_owner_and_admin_get_private_fields(pg_orm, who):
    client, ids, hdr, _ = await _setup(pg_orm)
    async with client:
        r = await client.get(f"/api/users/{ids['owner']}/profile", headers=hdr(who))
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "owner@example.com"
    assert body["google_id"] == "g-555"
    assert body["telegram_id"] == 555001
    assert body["usdt_wallet"] == "TOwnerWallet111"
    assert body["role"] == "user"
    assert "blocked_reason" not in body


@pytest.mark.asyncio
async def test_unknown_user_404_ukrainian(pg_orm):
    client, ids, hdr, _ = await _setup(pg_orm)
    async with client:
        r = await client.get("/api/users/999999/profile")
    assert r.status_code == 404
    assert r.json()["detail"] == "Користувача не знайдено"


def test_public_schema_has_no_pii_fields():
    from app.schemas.auth import PublicUserProfile

    assert not (PRIVATE & set(PublicUserProfile.model_fields))
