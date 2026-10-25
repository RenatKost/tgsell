"""TgSell Backend — FastAPI application entry point."""
import asyncio
import logging
import os
from pathlib import Path

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.config import settings
from app.routers import auth, channels, deals, admin, users, favorites, auctions, activity, media, support
from app.routers import bundles as bundles_router
from app.routers import admin_money
from app.routers import user_activity as user_activity_router
from app.routers import saved_searches as saved_searches_router
from app.routers import me as me_router
from app.routers import chat as chat_router
from app.routers import wanted as wanted_router
from app.routers import external_escrow as external_escrow_router
from app.routers import paid_services as paid_services_router
from app.tasks.payment_checker import run_payment_checker
from app.tasks.payout_worker import run_payout_worker
from app.tasks.stats_collector import run_stats_collector, run_view_tracker
from app.tasks.auction_manager import run_auction_manager
from app.tasks.health_monitor import run_health_monitor
from app.tasks.checklist_reminders import run_checklist_reminders
from app.tasks.weekly_report import run_weekly_report
from bot.main import run_bots_background

from app.utils.logging_setup import setup_logging  # noqa: E402
setup_logging()  # INFO → stdout, WARNING+ → stderr
from app.utils.log_redact import setup_log_hygiene  # noqa: E402
setup_log_hygiene()  # no bot tokens in logs (httpx logs full request URLs at INFO)
logger = logging.getLogger(__name__)

background_tasks: list[asyncio.Task] = []



async def _scrub_leaked_avatar_urls() -> None:
    """Idempotent: NULL out any avatar_url that still embeds a Bot API token."""
    from sqlalchemy import text as sa_text
    from app.database import async_session

    try:
        async with async_session() as db:
            ch = await db.execute(
                sa_text(
                    "UPDATE channels SET avatar_url = NULL "
                    "WHERE avatar_url LIKE '%api.telegram.org/file/bot%'"
                )
            )
            us = await db.execute(
                sa_text(
                    "UPDATE users SET avatar_url = NULL "
                    "WHERE avatar_url LIKE '%api.telegram.org/file/bot%'"
                )
            )
            await db.commit()
            logger.info(
                "Scrubbed leaked avatar URLs: channels=%s users=%s",
                ch.rowcount,
                us.rowcount,
            )
    except Exception as e:
        from app.utils.log_redact import redact
        logger.error("Avatar URL scrub failed: %s", redact(e))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Telegram config diagnostics
    from app.config import settings as cfg
    logger.info("── Telegram config check ──")
    logger.info(f"  BOT_TOKEN_STATS: {'✓ set' if cfg.bot_token_stats else '✗ MISSING'}")
    logger.info(f"  BOT_TOKEN_SUPPORT: {'✓ set' if cfg.bot_token_support else '✗ MISSING (support bot disabled)'}")
    logger.info(f"  TELEGRAM_API_ID: {'✓ set' if cfg.telegram_api_id else '✗ MISSING'}")
    logger.info(f"  TELEGRAM_API_HASH: {'✓ set' if cfg.telegram_api_hash else '✗ MISSING'}")
    logger.info(f"  TELETHON_SESSION_STRING: {'✓ set' if cfg.telethon_session_string else '✗ MISSING — no deep analytics'}")
    if not cfg.telethon_session_string:
        logger.warning("Channel analytics (views, ER, posts) require TELETHON_SESSION_STRING!")

    await _scrub_leaked_avatar_urls()

    logger.info("Starting background tasks…")
    loop = asyncio.get_event_loop()
    # Delay first Telethon connect past Railway healthcheck so old container is gone
    from app.services.channel_stats import delayed_telethon_startup
    background_tasks.append(loop.create_task(delayed_telethon_startup()))
    background_tasks.append(loop.create_task(run_payment_checker(interval_seconds=30)))
    background_tasks.append(loop.create_task(run_payout_worker(interval_seconds=5)))
    background_tasks.append(loop.create_task(run_stats_collector(interval_hours=3)))
    background_tasks.append(loop.create_task(run_view_tracker(interval_hours=3)))
    background_tasks.append(loop.create_task(run_auction_manager(interval_seconds=60)))
    background_tasks.append(loop.create_task(run_bots_background()))
    background_tasks.append(loop.create_task(run_health_monitor(interval_minutes=10)))
    background_tasks.append(loop.create_task(run_checklist_reminders(interval_minutes=30)))
    background_tasks.append(loop.create_task(run_weekly_report()))
    # Task 22: quality index from stored data only (no Telethon), <= every 6h
    from app.services.quality import run_quality_scorer
    background_tasks.append(loop.create_task(run_quality_scorer(startup_delay_sec=60)))
    from app.services.saved_searches import run_saved_search_notifier
    background_tasks.append(loop.create_task(run_saved_search_notifier()))
    from app.services.wanted import run_wanted_digest
    background_tasks.append(loop.create_task(run_wanted_digest()))
    from app.services.paid_services import run_service_payment_checker
    background_tasks.append(loop.create_task(run_service_payment_checker()))
    yield
    logger.info("Shutting down background tasks…")
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)

    from app.services.channel_stats import disconnect_telethon_client
    await disconnect_telethon_client()


app = FastAPI(
    title="TgSell API",
    version="1.0.0",
    lifespan=lifespan,
)

from app.utils.limits import install_price_limit_handler  # noqa: E402

install_price_limit_handler(app)

# CORS
allowed_origins = [settings.frontend_url]
if os.getenv("RAILWAY_ENVIRONMENT"):
    allowed_origins = ["*"]  # Railway serves frontend from same origin

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.utils.http_cache import api_no_store  # noqa: E402

app.middleware("http")(api_no_store)

from app.utils.security_headers import security_headers  # noqa: E402

app.middleware("http")(security_headers)

from app.utils.head_support import HeadAsGetMiddleware  # noqa: E402

app.add_middleware(HeadAsGetMiddleware)  # outermost: HEAD -> GET, body stripped


# Routers
app.include_router(auth.router, prefix="/api")
app.include_router(channels.router, prefix="/api")
app.include_router(chat_router.router, prefix="/api")
app.include_router(deals.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(admin_money.router, prefix="/api")
from app.routers import admin_broadcast as admin_broadcast_router  # noqa: E402
app.include_router(admin_broadcast_router.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(me_router.router, prefix="/api")
app.include_router(favorites.router, prefix="/api")
app.include_router(auctions.router, prefix="/api")
app.include_router(activity.router, prefix="/api")
app.include_router(bundles_router.router, prefix="/api")
app.include_router(external_escrow_router.router, prefix="/api")
app.include_router(paid_services_router.router, prefix="/api")
app.include_router(paid_services_router.admin_router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(support.router, prefix="/api")
app.include_router(user_activity_router.router, prefix="/api")
app.include_router(saved_searches_router.router, prefix="/api")
app.include_router(wanted_router.router, prefix="/api")
app.include_router(wanted_router.admin_router, prefix="/api")

from app.routers import seo as seo_router  # noqa: E402

app.include_router(seo_router.router)  # /robots.txt, /sitemap.xml (before SPA catch-all)

@app.get("/api/health")
async def health():
    """Liveness for Railway. Always 200 once the web app is up.

    Telethon may still be in 'waiting'/'connecting' during the startup delay
    (TELETHON_STARTUP_DELAY_SEC, default 150 > healthcheckTimeout 120).
    telethon.ok is True only when connected and authorized.
    """
    from app.services.channel_stats import get_telethon_health
    return {
        "status": "ok",
        "telethon": get_telethon_health(),
    }


# Serve frontend static files in production
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # Exact SPA paths and dynamic prefixes matching React Router
    SPA_EXACT = {
        "",
        "sell",
        "catalog",
        "wanted",
        "auction",
        "cabinet",
        "admin",
        "sell-bundle",
        "profile",
        "privacy",
        "oferta",
        "faq",
        "contacts",
        "terms",
        "kupyty-telegram-kanal",
        "prodaty-telegram-kanal",
        "skilky-koshtuye-telegram-kanal",
        "escrow",
    }
    SPA_PREFIXES = (
        "channel/",
        "bundle/",
        "deal/",
        "escrow/",  # private buyer invite (noindex, never cached by path)
    )

    _NOT_FOUND_HTML = """<!DOCTYPE html>
<html lang="uk"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>404 — TgSell</title>
<style>body{margin:0;font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:1.5rem}
h1{font-size:4rem;margin:0;color:#334155}h2{margin:.5rem 0;font-size:1.5rem}p{color:#94a3b8}a{color:#00FF88;font-weight:600;text-decoration:none}</style>
</head><body><div><h1>404</h1><h2>Сторінку не знайдено</h2><p>Такої адреси на TgSell немає.</p><a href="/">На головну</a></div></body></html>"""

    async def _channel_page_meta(channel_id: int) -> dict:
        """Task 33: per-channel <head> for crawlers; unpublished/blocked → noindex, no details."""
        from sqlalchemy import select as _select
        from app.database import async_session
        from app.models.channel import Channel
        from app.services.moderation import not_blocked_seller
        from app.utils.spa_meta import channel_meta
        try:
            async with async_session() as db:
                ch = (await db.execute(
                    _select(Channel).where(Channel.id == channel_id)
                    .where(not_blocked_seller(Channel.seller_id))
                )).scalar_one_or_none()
                meta = channel_meta(ch)
                if ch is None or meta.get("noindex"):
                    meta["not_found"] = True  # missing / unpublished / blocked seller → HTTP 404
                return meta
        except Exception as e:  # DB hiccup: serve generic page, not a 500
            logger.warning("channel meta lookup failed for %s: %s", channel_id, type(e).__name__)
            return channel_meta(None) | {"noindex": False, "title": "Telegram-канал на продаж — TgSell",
                                         "description": "Telegram-канал на продаж на TgSell."}

    async def _bundle_page_meta(bundle_id: int) -> dict:
        """Task 34: /bundle/:id <head>; unpublished/blocked → noindex, no details."""
        from sqlalchemy import select as _select
        from app.database import async_session
        from app.models.bundle import ChannelBundle
        from app.services.moderation import not_blocked_seller
        from app.utils.spa_meta import bundle_meta
        try:
            async with async_session() as db:
                b = (await db.execute(
                    _select(ChannelBundle).where(ChannelBundle.id == bundle_id)
                    .where(not_blocked_seller(ChannelBundle.seller_id))
                )).scalar_one_or_none()
                return bundle_meta(b)
        except Exception as e:
            logger.warning("bundle meta lookup failed for %s: %s", bundle_id, type(e).__name__)
            return bundle_meta(None)

    def _is_spa_path(full_path: str) -> bool:
        path = (full_path or "").strip("/")
        if path in SPA_EXACT:
            return True
        return any(path.startswith(prefix) for prefix in SPA_PREFIXES)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA for known routes; real HTTP 404 for unknown paths."""
        file_path = STATIC_DIR / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        if _is_spa_path(full_path):
            # Per-route title/description/canonical/OG injected server-side for crawlers.
            from app.utils.spa_meta import render_index, channel_id_from_path, channel_meta
            override = None
            ch_id = channel_id_from_path(full_path)
            if full_path.strip("/").startswith("escrow/"):
                from app.utils.spa_meta import ESCROW_INVITE_META
                override = dict(ESCROW_INVITE_META)  # dynamic branch → secret token never enters lru_cache
            elif ch_id is not None:
                override = await _channel_page_meta(ch_id)
            else:
                from app.utils.spa_meta import bundle_id_from_path
                b_id = bundle_id_from_path(full_path)
                if b_id is not None:
                    override = await _bundle_page_meta(b_id)
            from app.utils.spa_meta import spa_status
            status, override = spa_status(full_path, override)
            return HTMLResponse(render_index(STATIC_DIR / "index.html", full_path, override),
                                status_code=status, headers={"Cache-Control": "no-cache"})
        not_found = STATIC_DIR / "404.html"
        if not_found.is_file():
            return FileResponse(not_found, status_code=404)
        return Response(content=_NOT_FOUND_HTML, status_code=404, media_type="text/html; charset=utf-8")
