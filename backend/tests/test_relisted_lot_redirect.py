"""Relisted lot: old unpublished /channel/:id exposes replaced_by -> new active lot (still 404)."""
from __future__ import annotations

import pytest

from app.services.listing_visibility import _norm_link


def test_norm_link():
    assert _norm_link("https://t.me/Foo/") == _norm_link("@foo") == _norm_link("t.me/foo?x=1") == "foo"
    assert _norm_link(None) is None


async def _client(orm, rows):
    import httpx
    from fastapi import FastAPI

    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    from app.routers import channels as ch_router

    async with orm.session() as db:
        s1 = User(first_name="S1", telegram_id=771001, role=UserRole.user)
        s2 = User(first_name="S2", telegram_id=771002, role=UserRole.user)
        db.add_all([s1, s2])
        await db.flush()
        sellers = {"s1": s1.id, "s2": s2.id}
        for cid, seller, link, name, st in rows:
            db.add(Channel(id=cid, seller_id=sellers[seller], telegram_link=link, channel_name=name,
                           category="x", price=100, status=ChannelStatus(st)))
        await db.commit()
    app = FastAPI()
    app.include_router(ch_router.router, prefix="/api")
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
@pytest.mark.parametrize("old_status", ["removed", "rejected", "pending"])
async def test_relisted_same_seller_same_link(orm, old_status):
    c = await _client(orm, [
        (102, "s1", "https://t.me/Warsaw", "Товари з Warsaw", old_status),
        (103, "s1", "@warsaw", "Товари з Warsaw (нова ціна)", "approved"),
    ])
    r = await c.get("/api/channels/102")
    assert r.status_code == 404 and r.json()["replaced_by"] == 103
    assert (await c.get("/api/channels/103")).status_code == 200


@pytest.mark.asyncio
async def test_relisted_match_by_name_private_link(orm):
    c = await _client(orm, [
        (102, "s1", "https://t.me/+aaa", "Товари  з Warsaw", "removed"),
        (103, "s1", "https://t.me/+bbb", "товари з warsaw", "approved"),
    ])
    assert (await c.get("/api/channels/102")).json().get("replaced_by") == 103


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [
    # other seller relisted the same channel -> plain 404
    [(102, "s1", "https://t.me/w", "W", "removed"), (103, "s2", "https://t.me/w", "W", "approved")],
    # same seller, different channel
    [(102, "s1", "https://t.me/w", "W", "removed"), (103, "s1", "https://t.me/z", "Z", "approved")],
    # new lot not yet approved
    [(102, "s1", "https://t.me/w", "W", "removed"), (103, "s1", "https://t.me/w", "W", "pending")],
    # older lot is not a replacement
    [(101, "s1", "https://t.me/w", "W", "approved"), (102, "s1", "https://t.me/w", "W", "removed")],
])
async def test_no_replacement_keeps_plain_404(orm, rows):
    c = await _client(orm, rows)
    r = await c.get("/api/channels/102")
    assert r.status_code == 404 and "replaced_by" not in r.json()


@pytest.mark.asyncio
async def test_missing_id_plain_404(orm):
    c = await _client(orm, [])
    r = await c.get("/api/channels/999")
    assert r.status_code == 404 and "replaced_by" not in r.json()
