"""Task 28: AI retries/repair, ER sanity, heartbeat throttling, gas threshold, headers, SEO."""
from __future__ import annotations

import asyncio
import importlib
import json
from datetime import datetime

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.services import ai_analysis as ai


# ── 1) AI analysis ────────────────────────────────────────────────────

def test_repair_json_variants():
    assert ai.repair_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai.repair_json('Ось аналіз: {"a": 1, "b": [1, 2,],}') == {"a": 1, "b": [1, 2]}
    r = ai.repair_json('{"summary": "текст", "risks": ["r1", "r2"], "verdict": "bu')
    assert r["summary"] == "текст" and r["risks"] == ["r1", "r2"]
    r = ai.repair_json('{"summary": "x", "score": 70, "risks": ["a"')
    assert r["score"] == 70 and r["risks"] == ["a"]
    r = ai.repair_json('{"summary": "x", "score":')
    assert r == {"summary": "x"}
    with pytest.raises(json.JSONDecodeError):
        ai.repair_json("Вибачте, не можу")


class _Resp:
    def __init__(self, content=None, status=200):
        self._c, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("POST", ai.GROQ_URL)
            raise httpx.HTTPStatusError("err", request=req, response=httpx.Response(self.status_code, request=req, text="x"))

    def json(self):
        return {"choices": [{"message": {"content": self._c}, "finish_reason": "length"}]}


def _fake_client(responses, sent):
    class C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            sent.append(json)
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
    return C


@pytest.fixture
def groq(monkeypatch):
    monkeypatch.setattr(ai.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(ai, "alert_service_down", lambda *a, **k: asyncio.sleep(0))

    def setup(responses):
        sent = []
        monkeypatch.setattr(ai.httpx, "AsyncClient", _fake_client(list(responses), sent))
        return sent
    return setup


def test_bundle_retries_then_succeeds_with_bigger_token_limit(groq):
    sent = groq([_Resp("not json at all"), _Resp('{"summary": "ok", "score": 70}')])
    res = asyncio.run(ai.analyze_bundle({"name": "b"}, []))
    assert res == {"summary": "ok", "score": 70}
    assert len(sent) == 2 and sent[0]["max_tokens"] >= 4096


def test_channel_all_attempts_fail_gives_unavailable(groq):
    sent = groq([_Resp("garbage")] * ai.GROQ_MAX_ATTEMPTS)
    res = asyncio.run(ai.analyze_channel({"channel_name": "c"}, [], []))
    assert res["status"] == "unavailable" and res["detail"] == "аналіз тимчасово недоступний"
    assert len(sent) == ai.GROQ_MAX_ATTEMPTS and sent[0]["max_tokens"] >= 6144


def test_timeout_and_5xx_are_retried_429_not(groq):
    groq([httpx.ReadTimeout("t"), _Resp(status=502), _Resp('{"ok": 1}')])
    assert asyncio.run(ai.analyze_bundle({"name": "b"}, [])) == {"ok": 1}
    sent = groq([_Resp(status=429), _Resp('{"ok": 1}')])
    assert asyncio.run(ai.analyze_bundle({"name": "b"}, []))["status"] == "unavailable"
    assert len(sent) == 1


def test_truncated_json_is_repaired_without_retry(groq):
    sent = groq([_Resp('{"summary": "довгий текст", "score": 55, "risks": ["a", "b"')])
    res = asyncio.run(ai.analyze_channel({"channel_name": "c"}, [], []))
    assert res["score"] == 55 and len(sent) == 1


async def _app(pg_orm, monkeypatch, router_mod):
    from fastapi import FastAPI
    db_mod = importlib.import_module("app.database")
    mod = importlib.import_module(router_mod)
    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _seed_channel(pg_orm, **kw):
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole
    async with pg_orm.session() as db:
        u = User(telegram_id=777001, username="seller28", first_name="S", role=UserRole.user)
        db.add(u)
        await db.flush()
        ch = Channel(seller_id=u.id, channel_name="Test28", telegram_link="https://t.me/test28",
                     category="news", subscribers_count=kw.get("subs", 1000), er=kw.get("er", 5.0),
                     price=100, status=kw.get("status", ChannelStatus.approved))
        db.add(ch)
        await db.commit()
        return ch.id


@pytest.mark.asyncio
async def test_channel_endpoint_returns_200_unavailable_and_does_not_cache(pg_orm, monkeypatch):
    from app.models.channel import Channel
    cid = await _seed_channel(pg_orm)

    async def fail(*a, **k):
        return ai.unavailable_result("parse_error")
    monkeypatch.setattr(ai, "analyze_channel", fail)
    cl = await _app(pg_orm, monkeypatch, "app.routers.channels")
    async with cl:
        r = await cl.get(f"/api/channels/{cid}/ai-analysis")
    assert r.status_code == 200 and r.json()["status"] == "unavailable"
    async with pg_orm.session() as db:
        ch = await db.get(Channel, cid)
        assert ch.ai_cache is None and ch.ai_cache_updated_at is None


@pytest.mark.asyncio
async def test_bundle_endpoint_returns_200_unavailable_and_does_not_cache(pg_orm, monkeypatch):
    from app.models.bundle import ChannelBundle
    bundles = importlib.import_module("app.routers.bundles")
    cid = await _seed_channel(pg_orm)
    async with pg_orm.session() as db:
        from app.models.channel import Channel
        ch = await db.get(Channel, cid)
        from app.models.bundle import BundleStatus
        b = ChannelBundle(seller_id=ch.seller_id, name="B28", price=100, status=BundleStatus.approved)
        db.add(b)
        await db.commit()
        bid = b.id

    async def fail(*a, **k):
        return None
    monkeypatch.setattr(bundles, "analyze_bundle", fail)
    cl = await _app(pg_orm, monkeypatch, "app.routers.bundles")
    async with cl:
        r = await cl.get(f"/api/bundles/{bid}/ai-analysis")
    assert r.status_code == 200 and r.json()["detail"] == "аналіз тимчасово недоступний"
    async with pg_orm.session() as db:
        assert (await db.get(ChannelBundle, bid)).ai_cache is None


# ── 2) ER ─────────────────────────────────────────────────────────────

def test_reliable_er():
    from app.utils.er import reliable_er
    assert reliable_er(2200, 30) is None
    assert reliable_er(654.0, 5000) is None
    assert reliable_er(12.5, 10) is None  # too few subscribers
    assert reliable_er(12.5, 1000) == 12.5 and reliable_er(100, 1000) == 100
    assert reliable_er(None) is None and reliable_er("x") is None and reliable_er(float("nan")) is None


# ── 3) heartbeat ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heartbeat_45s_passes_and_close_beats_are_noop_not_429(pg_orm, monkeypatch):
    from datetime import timedelta
    ua = importlib.import_module("app.services.user_activity")
    ua.limiter.reset()
    clock = {"t": 1000.0}
    real_mi, real_pm = ua.limiter.min_interval, ua.limiter.per_minute
    monkeypatch.setattr(ua.limiter, "min_interval", lambda k, s, now=None: real_mi(k, s, now=clock["t"]))
    monkeypatch.setattr(ua.limiter, "per_minute", lambda k, n, now=None: real_pm(k, n, now=clock["t"]))
    base = datetime(2026, 10, 16, 12, 0, 0)
    wall = {"now": base}
    monkeypatch.setattr(ua, "utcnow_naive", lambda: wall["now"])
    cl = await _app(pg_orm, monkeypatch, "app.routers.user_activity")
    async with cl:
        async def beat(dt):
            clock["t"] += dt
            wall["now"] += timedelta(seconds=dt)
            return await cl.post("/api/track/heartbeat", json={"sid": "sess-task28"})
        r = await beat(0)
        assert r.status_code == 200
        total = 0
        for _ in range(5):  # normal 45 s beats
            r = await beat(45)
            assert r.status_code == 200 and not r.json().get("throttled")
            total += r.json()["credited"]
        assert total == 225
        # second tab with the same sid 5 s later: no-op, not 429
        r = await beat(5)
        assert r.status_code == 200 and r.json()["throttled"] is True and r.json()["credited"] == 0
        # next normal beat credits the whole gap (no activity lost)
        r = await beat(40)
        assert r.status_code == 200 and r.json()["credited"] == 45
        # real flood → 429
        codes = [(await beat(1)).status_code for _ in range(20)]
        assert 429 in codes


# ── 4) gas threshold ─────────────────────────────────────────────────

def test_gas_threshold_single_source():
    gm = importlib.import_module("app.services.gas_monitor")
    st = gm.evaluate({"trx_sun": 40_000_000}, address="T")
    assert st["warning_threshold_trx"] == gm.warning_threshold_trx(st["energy_fee_sun"])
    assert round(gm.warning_threshold_trx()) == 54
    assert st["level"] == "warning"  # 40 TRX < 54


# master_trx_status threshold: covered in test_payout_worker (uses its stubbed env)


# ── 5) headers + SEO ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_security_headers_robots_sitemap(pg_orm, monkeypatch):
    from fastapi import FastAPI
    from app.models.channel import ChannelStatus
    from app.utils.security_headers import security_headers
    db_mod = importlib.import_module("app.database")
    seo = importlib.import_module("app.routers.seo")
    cid = await _seed_channel(pg_orm)
    app = FastAPI()
    app.middleware("http")(security_headers)
    app.include_router(seo.router)
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
        r = await cl.get("/robots.txt")
        assert r.status_code == 200
        assert "Disallow: /admin" in r.text and "Disallow: /api/" in r.text
        assert "Sitemap: https://tgsell.me/sitemap.xml" in r.text
        h = r.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert "max-age=" in h["strict-transport-security"]
        assert h["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "frame-ancestors 'none'" in h["content-security-policy"]
        r = await cl.get("/sitemap.xml")
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
        assert "<loc>https://tgsell.me/</loc>" in r.text and "/faq</loc>" in r.text
        assert f"<loc>https://tgsell.me/channel/{cid}</loc>" in r.text
        assert "/admin" not in r.text and "/cabinet" not in r.text
    xml = seo.build_sitemap([(5, None)])
    assert xml.count("<url>") == len(seo.STATIC_PAGES) + 1

