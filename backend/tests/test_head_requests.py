"""HEAD on SPA catch-all, static files, SEO and /api/health: 200, same headers as GET, no body."""
from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse
from httpx import ASGITransport, AsyncClient


def _build(tmp_path, pg_orm):
    from app.utils.head_support import HeadAsGetMiddleware
    from app.utils.http_cache import api_no_store
    from app.utils.security_headers import SECURITY_HEADERS, security_headers
    seo = importlib.import_module("app.routers.seo")
    db_mod = importlib.import_module("app.database")
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "favicon.ico").write_bytes(b"\x00\x00\x01\x00icon")
    app = FastAPI()
    app.middleware("http")(api_no_store)
    app.middleware("http")(security_headers)
    app.add_middleware(HeadAsGetMiddleware)
    app.include_router(seo.router)
    app.dependency_overrides[db_mod.get_db] = pg_orm.get_db

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        f = tmp_path / full_path
        return FileResponse(f if full_path and f.is_file() else tmp_path / "index.html")

    return app, SECURITY_HEADERS


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/", "/catalog", "/robots.txt", "/sitemap.xml", "/favicon.ico", "/api/health"])
async def test_head_matches_get(tmp_path, pg_orm, path):
    app, sec = _build(tmp_path, pg_orm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
        g = await cl.get(path)
        h = await cl.head(path)
    assert g.status_code == 200 and h.status_code == 200
    assert h.content == b""
    for k in sec:
        assert h.headers.get(k) == g.headers.get(k) and h.headers.get(k)
    for k in ("content-type", "content-length", "cache-control"):
        assert h.headers.get(k) == g.headers.get(k)
    assert int(h.headers["content-length"]) == len(g.content)


def test_real_app_registers_head_middleware():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    assert "app.add_middleware(HeadAsGetMiddleware)" in src
