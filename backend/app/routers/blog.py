"""Blog: server-rendered /blog and /blog/<slug> + read-only JSON API (no DB)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services import blog_content
from app.utils import blog_html

router = APIRouter(tags=["blog"], include_in_schema=False)
api_router = APIRouter(prefix="/blog", tags=["blog"])

STATIC_INDEX = Path(__file__).resolve().parents[2] / "static" / "index.html"
_HTML_HEADERS = {"Cache-Control": "no-cache"}


def index_file() -> Path | None:
    return STATIC_INDEX if STATIC_INDEX.is_file() else None


def _not_found(full_path: str) -> HTMLResponse:
    return HTMLResponse(blog_html.render_blog_not_found(full_path, index_file()),
                        status_code=404, headers=_HTML_HEADERS)


@router.get("/blog")
async def blog_index():
    return HTMLResponse(blog_html.render_blog_index(blog_content.published_articles(), index_file()),
                        headers=_HTML_HEADERS)


@router.get("/blog/")
async def blog_index_slash():
    return RedirectResponse("/blog", status_code=308)


@router.get("/blog/{slug}")
async def blog_article(slug: str):
    article = blog_content.get_published(slug)
    if article is None:
        return _not_found(f"blog/{slug}")
    return HTMLResponse(blog_html.render_blog_article(article, index_file()), headers=_HTML_HEADERS)


@router.get("/blog/{slug}/")
async def blog_article_slash(slug: str):
    if blog_content.get_published(slug) is None:
        return _not_found(f"blog/{slug}")
    return RedirectResponse(f"/blog/{slug}", status_code=308)


@router.get("/blog/{rest:path}")
async def blog_nested(rest: str):
    return _not_found(f"blog/{rest}")


@api_router.get("")
async def api_blog_list():
    return {"articles": [a.summary() for a in blog_content.published_articles()]}


@api_router.get("/{slug}")
async def api_blog_article(slug: str):
    article = blog_content.get_published(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Статтю не знайдено")
    return article.detail()
