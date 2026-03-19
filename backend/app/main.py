"""TgSell Backend — FastAPI application entry point."""
import asyncio
import logging
import os
from pathlib import Path

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.routers import auth, channels, deals, admin, users, favorites
from app.tasks.payment_checker import run_payment_checker
from app.tasks.stats_collector import run_stats_collector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting background tasks…")
    loop = asyncio.get_event_loop()
    background_tasks.append(loop.create_task(run_payment_checker(interval_seconds=30)))
    background_tasks.append(loop.create_task(run_stats_collector(interval_hours=24)))
    yield
    logger.info("Shutting down background tasks…")
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)


app = FastAPI(
    title="TgSell API",
    version="1.0.0",
    lifespan=lifespan,
)

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

# Routers
app.include_router(auth.router, prefix="/api")
app.include_router(channels.router, prefix="/api")
app.include_router(deals.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(favorites.router, prefix="/api")

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files in production
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA — all non-API routes return index.html."""
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
