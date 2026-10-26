"""Sitemap lists only truly public lots: channels of unpublished bundles are excluded."""
from __future__ import annotations

import importlib

import pytest
from httpx import ASGITransport, AsyncClient


async def _seed(pg_orm):
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    async with pg_orm.session() as db:
        u = User(telegram_id=778001, username="sm_seller", first_name="S", role=UserRole.user)
        db.add(u)
        await db.flush()
        ids = {}
        for key in ("solo", "in_approved", "in_rejected", "in_pending", "removed"):
            ch = Channel(seller_id=u.id, channel_name=key, telegram_link=f"https://t.me/sm_{key}",
                         category="news", subscribers_count=100, price=10,
                         status=ChannelStatus.removed if key == "removed" else ChannelStatus.approved)
            db.add(ch)
            await db.flush()
            ids[key] = ch.id
        for key, st in (("in_approved", BundleStatus.approved), ("in_rejected", BundleStatus.rejected),
                        ("in_pending", BundleStatus.pending)):
            b = ChannelBundle(seller_id=u.id, name=f"B-{key}", price=100, status=st)
            db.add(b)
            await db.flush()
            db.add(BundleChannel(bundle_id=b.id, channel_id=ids[key], display_order=0))
        await db.commit()
        return ids


@pytest.mark.asyncio
async def test_sitemap_excludes_channels_of_unpublished_bundles(pg_orm):
    from fastapi import FastAPI
    db_mod = importlib.import_module("app.database")
    seo = importlib.import_module("app.routers.seo")
    ids = await _seed(pg_orm)
    app = FastAPI()
    app.include_router(seo.router)
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
        r = await cl.get("/sitemap.xml")
    assert r.status_code == 200

    def has(cid):
        return f"<loc>https://tgsell.me/channel/{cid}</loc>" in r.text

    assert has(ids["solo"])
    assert has(ids["in_approved"])  # channels of a published bundle stay (their pages are public)
    assert not has(ids["in_rejected"])
    assert not has(ids["in_pending"])
    assert not has(ids["removed"])
