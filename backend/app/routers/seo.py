"""Task 28: robots.txt + dynamic sitemap.xml (static pages + published channels)."""
from __future__ import annotations

import logging
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.channel import Channel, ChannelStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["seo"])

SITE_URL = "https://tgsell.me"
STATIC_PAGES = [
    ("/", "daily", "1.0"),
    ("/catalog", "hourly", "0.9"),
    ("/auction", "hourly", "0.8"),
    ("/sell", "monthly", "0.6"),
    ("/sell-bundle", "monthly", "0.5"),
    ("/faq", "monthly", "0.5"),
    ("/contacts", "yearly", "0.3"),
    ("/oferta", "yearly", "0.2"),
    ("/terms", "yearly", "0.2"),
    ("/privacy", "yearly", "0.2"),
]
MAX_CHANNEL_URLS = 45000  # sitemap limit is 50k URLs

ROBOTS_TXT = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /api/
Disallow: /cabinet
Disallow: /profile
Disallow: /deal/

Sitemap: {SITE_URL}/sitemap.xml
"""


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return PlainTextResponse(ROBOTS_TXT, headers={"Cache-Control": "public, max-age=3600"})


def build_sitemap(channels: list[tuple[int, object]]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, freq, prio in STATIC_PAGES:
        out.append(f"  <url><loc>{escape(SITE_URL + path)}</loc>"
                   f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>")
    for cid, created in channels:
        lastmod = f"<lastmod>{created.date().isoformat()}</lastmod>" if created else ""
        out.append(f"  <url><loc>{escape(f'{SITE_URL}/channel/{int(cid)}')}</loc>{lastmod}"
                   f"<changefreq>daily</changefreq><priority>0.7</priority></url>")
    out.append("</urlset>")
    return "\n".join(out) + "\n"


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(db: AsyncSession = Depends(get_db)):
    channels: list[tuple[int, object]] = []
    try:
        rows = await db.execute(
            select(Channel.id, Channel.created_at)
            .where(Channel.status == ChannelStatus.approved)
            .order_by(Channel.id.desc())
            .limit(MAX_CHANNEL_URLS)
        )
        channels = [(r[0], r[1]) for r in rows.all()]
    except Exception as e:  # sitemap must not 500 — static pages are still useful
        logger.warning("sitemap: channel query failed: %s", type(e).__name__)
    return Response(build_sitemap(channels), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=900"})
