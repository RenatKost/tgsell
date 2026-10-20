"""Task 33: unpublished-lot visibility, per-channel SPA meta, token masking,
view-ratio rules, read-only on-chain escrow total."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils import spa_meta

REPO = Path(__file__).resolve().parents[2]
INDEX = (REPO / "index.html").read_text(encoding="utf-8")
NOW = datetime(2026, 10, 15, 12, 0)


# ── 2) visibility ───────────────────────────────────────────────
async def _setup(orm):
    import httpx
    from fastapi import FastAPI

    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    from app.routers import bundles as bundles_router
    from app.routers import channels as channels_router
    from app.utils.security import create_access_token

    async with orm.session() as db:
        owner = User(first_name="Owner", telegram_id=733001, role=UserRole.user)
        other = User(first_name="Other", telegram_id=733002, role=UserRole.user)
        admin = User(first_name="Admin", telegram_id=733003, role=UserRole.admin)
        moder = User(first_name="Moder", telegram_id=733004, role=UserRole.moderator)
        db.add_all([owner, other, admin, moder])
        await db.flush()
        chans = {}
        for st in ("approved", "pending", "rejected", "removed", "sold"):
            c = Channel(seller_id=owner.id, telegram_link=f"https://t.me/{st}", channel_name=f"Ch {st}",
                        seller_telegram="@secret_seller", category="Гумор", price=100,
                        subscribers_count=1000, status=ChannelStatus(st))
            db.add(c)
            chans[st] = c
        await db.flush()
        bundles = {}
        for st in ("approved", "pending"):
            b = ChannelBundle(seller_id=owner.id, name=f"B {st}", price=10, category="Гумор",
                              status=BundleStatus(st))
            db.add(b)
            bundles[st] = b
        await db.commit()
        ids = {"owner": owner.id, "other": other.id, "admin": admin.id, "moder": moder.id}
        cids = {k: v.id for k, v in chans.items()}
        bids = {k: v.id for k, v in bundles.items()}

    app = FastAPI()
    app.include_router(channels_router.router, prefix="/api")
    app.include_router(bundles_router.router, prefix="/api")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    def hdr(who=None):
        if who is None:
            return {}
        return {"Authorization": f"Bearer {create_access_token({'sub': str(ids[who])})}"}

    return client, ids, cids, bids, hdr


SUBPATHS = ["", "/similar", "/stats", "/posts", "/health", "/ai-analysis"]


@pytest.mark.asyncio
@pytest.mark.parametrize("st", ["pending", "rejected", "removed"])
@pytest.mark.parametrize("who", [None, "other"])
async def test_unpublished_channel_404_for_public(pg_orm, st, who):
    client, ids, cids, _, hdr = await _setup(pg_orm)
    async with client:
        for sub in SUBPATHS:
            r = await client.get(f"/api/channels/{cids[st]}{sub}", headers=hdr(who))
            assert r.status_code == 404, (sub, r.status_code)
            assert "secret_seller" not in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["owner", "admin", "moder"])
async def test_unpublished_channel_visible_to_owner_and_staff(pg_orm, who):
    client, ids, cids, _, hdr = await _setup(pg_orm)
    async with client:
        for st in ("pending", "rejected"):
            for sub in ("", "/stats", "/posts", "/similar"):
                r = await client.get(f"/api/channels/{cids[st]}{sub}", headers=hdr(who))
                assert r.status_code == 200, (st, sub, r.text)


@pytest.mark.asyncio
async def test_published_channel_public_and_seller_listing_filtered(pg_orm):
    client, ids, cids, _, hdr = await _setup(pg_orm)
    async with client:
        assert (await client.get(f"/api/channels/{cids['approved']}")).status_code == 200
        assert (await client.get(f"/api/channels/{cids['sold']}")).status_code == 200
        r = await client.get("/api/channels", params={"seller_id": ids["owner"]})
        names = {c["channel_name"] for c in r.json()["items"]}
        assert names == {"Ch approved", "Ch sold"}
        r = await client.get("/api/channels", params={"seller_id": ids["owner"]}, headers=hdr("owner"))
        assert len(r.json()["items"]) == 5


@pytest.mark.asyncio
async def test_unpublished_bundle_endpoints_404(pg_orm):
    client, ids, _, bids, hdr = await _setup(pg_orm)
    async with client:
        for sub in ("", "/stats", "/ai-analysis"):
            assert (await client.get(f"/api/bundles/{bids['pending']}{sub}")).status_code == 404, sub
        assert (await client.get(f"/api/bundles/{bids['pending']}/stats", headers=hdr("owner"))).status_code == 200
        assert (await client.get(f"/api/bundles/{bids['approved']}/stats")).status_code == 200
        r = await client.get("/api/bundles", params={"seller_id": ids["owner"]})
        assert {b["name"] for b in r.json()["items"]} == {"B approved"}


# ── 1) SPA meta ─────────────────────────────────────────────────
def _meta(html, attr, key):
    return re.findall(rf'<meta {attr}="{re.escape(key)}" content="([^"]*)"', html)


def _ch(status="approved", **kw):
    d = dict(id=95, channel_name="Робота Київ", subscribers_count=12345, price=300.0,
             avatar_url="tg:abc", status=SimpleNamespace(value=status))
    d.update(kw)
    return SimpleNamespace(**d)


def test_channel_page_meta_public():
    html = spa_meta.inject_meta(INDEX, "channel/95", spa_meta.channel_meta(_ch()))
    title = re.findall(r"<title>(.*?)</title>", html)[0]
    assert "Робота Київ" in title and "12\u00a0345" in title
    desc = _meta(html, "name", "description")[0]
    assert "12\u00a0345 підписників" in desc and "300 USDT" in desc
    assert _meta(html, "property", "og:title") == [title]
    assert _meta(html, "property", "og:description") == [desc]
    assert _meta(html, "property", "og:image") == ["https://tgsell.me/api/media/channel-avatar/95"]
    assert re.findall(r'<link rel="canonical" href="([^"]*)"', html) == ["https://tgsell.me/channel/95"]
    assert _meta(html, "name", "robots") == ["index, follow"]
    for word in ("медіан", "методик", "вибірк", "курс"):
        assert word not in desc.lower() and word not in title.lower()


@pytest.mark.parametrize("st", ["pending", "rejected", "removed"])
def test_unpublished_channel_meta_noindex_no_details(st):
    html = spa_meta.inject_meta(INDEX, "channel/96", spa_meta.channel_meta(_ch(st, id=96)))
    assert _meta(html, "name", "robots") == ["noindex, nofollow"]
    assert "Робота Київ" not in html and "12\u00a0345" not in html


def test_unknown_channel_noindex():
    html = spa_meta.inject_meta(INDEX, "channel/9999", spa_meta.channel_meta(None))
    assert _meta(html, "name", "robots") == ["noindex, nofollow"]


def test_catalog_meta():
    html = spa_meta.inject_meta(INDEX, "catalog")
    m = spa_meta.EXTRA_ROUTE_META["/catalog"]
    assert f"<title>{m['title']}</title>" in html
    assert _meta(html, "property", "og:title") == [m["title"]]
    assert _meta(html, "property", "og:description") == [m["description"]]
    assert re.findall(r'<link rel="canonical" href="([^"]*)"', html) == ["https://tgsell.me/catalog"]
    assert "<h1>" not in html


def test_channel_id_from_path():
    assert spa_meta.channel_id_from_path("channel/95") == 95
    assert spa_meta.channel_id_from_path("channel/95/") == 95
    assert spa_meta.channel_id_from_path("channel/abc") is None
    assert spa_meta.channel_id_from_path("catalog") is None


# ── 4) token masking in access logs ─────────────────────────────
def test_bot_check_token_masked_in_access_log():
    from app.utils.log_redact import TokenRedactFilter, redact

    line = '1.2.3.4:5 - "GET /api/auth/bot-check?token=abcDEF123_-xyz HTTP/1.1" 200'
    out = redact(line)
    assert "abcDEF123" not in out and "token=***" in out
    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                            '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "GET", "/api/auth/bot-check?token=SeCrEt42&x=1", "1.1", 200), None)
    TokenRedactFilter().filter(rec)
    msg = rec.getMessage()
    assert "SeCrEt42" not in msg and "token=***&x=1" in msg


def test_access_logger_has_filter():
    from app.utils.log_redact import TokenRedactFilter, setup_log_hygiene
    setup_log_hygiene()
    assert any(isinstance(f, TokenRedactFilter) for f in logging.getLogger("uvicorn.access").filters)


# ── 5) view-ratio rules ─────────────────────────────────────────
def _posts(views, n=10):
    return [(NOW - timedelta(days=i * 2, hours=1), views) for i in range(n)]


def test_high_er_jobs_channel_not_inflated_not_capped():
    from app.services.pricing import build_market, estimate
    from app.services.quality import score_channel
    m = build_market()
    v = estimate(m, category="Вакансія/Робота", price=300, subscribers=16325, avg_views=210730,
                 is_closed=False, last_post_date=NOW - timedelta(days=1), now=NOW)["price_verdict"]
    assert v != "inflated"
    r = score_channel(subscribers=16325, posts=_posts(9500), snapshots=[], now=NOW, price_verdict=v)
    assert r["score"] > 25 and r["breakdown"]["components"]["integrity"]["inflated"] is False
    assert r["breakdown"]["components"]["er"]["points"] == 30.0


@pytest.mark.parametrize("cat", ["Вакансія/Робота", "Гумор", "Регіональні"])
def test_low_ratio_still_inflated_everywhere(cat):
    from app.services.pricing import build_market, estimate
    v = estimate(build_market(), category=cat, price=100, subscribers=10000, avg_views=150,
                 is_closed=False, last_post_date=NOW - timedelta(days=1), now=NOW)["price_verdict"]
    assert v == "inflated"


def test_moderation_info_flag():
    from app.services.pricing import HIGH_VIEWS_FLAG, high_views_flag
    kw = dict(subscribers=1000, avg_views=2000, last_post_date=NOW - timedelta(days=1), now=NOW)
    assert high_views_flag(category="Гумор", **kw) == HIGH_VIEWS_FLAG
    assert HIGH_VIEWS_FLAG == "переглядів більше за підписників — перевірте джерела"
    for cat in ("Вакансія/Робота", "Регіональні", "Товари/Магазини"):
        assert high_views_flag(category=cat, **kw) is None
    assert high_views_flag(category="Гумор", subscribers=1000, avg_views=1200,
                           last_post_date=NOW - timedelta(days=1), now=NOW) is None


# ── 3) on-chain escrow total (read-only) ────────────────────────
def test_onchain_total_all_addresses_and_unknown(monkeypatch):
    import importlib
    admin_router = SimpleNamespace(_collect_escrow_balances=importlib.import_module("app.services.escrow_balances").collect_escrow_balances)
    escrow = importlib.import_module("app.services.escrow")
    fs = importlib.import_module("app.services.fee_sweep")
    EXCLUDED_DEAL_IDS, RENAT_DECISION_DEAL_IDS = fs.EXCLUDED_DEAL_IDS, fs.RENAT_DECISION_DEAL_IDS

    bal = {"TDUbid29": 2.3, "TAddr3": 4.0, "TAddr6": 0.5, "TAddr7": 0.0}

    def fake(addr):
        if addr == "T429":
            raise escrow.BalanceUnavailable("429 Too Many Requests")
        return bal[addr]

    monkeypatch.setattr(escrow, "fetch_usdt_balance", fake)
    send = []
    monkeypatch.setattr(escrow, "broadcast_prepared", lambda *a, **k: send.append(a), raising=False)
    rows = [(29, "TDUbid29", "completed"), (3, "TAddr3", "completed"), (6, "TAddr6", "cancelled"),
            (7, "TAddr7", "cancelled"), (8, None, "created"), (9, "T429", "cancelled")]
    p = admin_router._collect_escrow_balances(rows)
    assert p["onchain_total_usdt"] == pytest.approx(6.8)
    assert p["onchain_unknown_count"] == 1 and p["address_count"] == 5
    assert {w["deal_id"] for w in p["wallets_with_funds"]} == {29, 3, 6}
    # last-known value kept for an address that later hits 429, but not summed
    prev = {"addresses": [{"address": "T429", "balance_usdt": 1.0, "stale": False}]}
    p2 = admin_router._collect_escrow_balances(rows, prev)
    a = next(x for x in p2["addresses"] if x["address"] == "T429")
    assert a["balance_usdt"] is None and a["last_known_usdt"] == 1.0 and a["stale"] is True
    assert p2["onchain_total_usdt"] == pytest.approx(6.8)
    assert send == []
    assert {29, 3} <= RENAT_DECISION_DEAL_IDS and {29, 3, 6} <= EXCLUDED_DEAL_IDS
