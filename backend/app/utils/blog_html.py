"""Server-rendered HTML for /blog and /blog/<slug> on top of the Vite index.html shell.

The full article text is in the HTTP response (no JS needed). React's createRoot() later
replaces #root with the same content, using the JSON bootstrap to avoid an empty flash.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

from app.services.blog_content import SITE_URL, Article
from app.utils.spa_meta import _set_meta, _sub, inject_meta

BLOG_TITLE = "Блог TgSell — купівля, продаж і перевірка Telegram-каналів"
BLOG_DESCRIPTION = ("Практичні статті про купівлю, продаж, оцінку та перевірку Telegram-каналів "
                    "і про безпечні угоди через гарант TgSell.")
BLOG_H1 = "Блог TgSell"
BLOG_INTRO = "Практичні поради про купівлю, продаж, оцінку та перевірку Telegram-каналів."
EMPTY_TEXT = "Статті незабаром з’являться."
NOT_FOUND_TITLE = "Статтю не знайдено — Блог TgSell"
NOT_FOUND_DESCRIPTION = "Такої статті в блозі TgSell немає."
BOOTSTRAP_ID = "tgsell-blog-data"

_FALLBACK_SHELL = """<!doctype html>
<html lang="uk">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TgSell</title>
  <meta name="description" content="" />
  <meta name="robots" content="index, follow" />
  <link rel="canonical" href="https://tgsell.me/" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="" />
  <meta property="og:description" content="" />
  <meta property="og:url" content="https://tgsell.me/" />
  <meta property="og:site_name" content="TgSell" />
  <meta property="og:locale" content="uk_UA" />
</head>
<body>
  <div id="root"></div>
</body>
</html>
"""


def safe_json(data) -> str:
    """JSON for embedding inside <script>: no </script> breakout, no HTML-significant chars."""
    s = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def article_schema(a: Article) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": a.title,
        "description": a.description,
        "inLanguage": "uk",
        "url": a.url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": a.url},
        "datePublished": a.date_iso,
        "publisher": {"@type": "Organization", "name": "TgSell", "url": SITE_URL},
    }


def _shell(index_file: Path | None) -> str:
    if index_file is not None and index_file.is_file():
        return index_file.read_text(encoding="utf-8")
    return _FALLBACK_SHELL


def _with_root(html: str, inner: str) -> str:
    return _sub(r'<div id="root">\s*</div>', f'<div id="root">{inner}</div>', html)


def _before_head_end(html: str, snippet: str) -> str:
    return html.replace("</head>", f"  {snippet}\n</head>", 1)


def _bootstrap(data: dict) -> str:
    return f'<script type="application/json" id="{BOOTSTRAP_ID}">{safe_json(data)}</script>'


def _time(a: Article) -> str:
    return f'<time datetime="{a.date_iso}">{escape(a.date_human)}</time>'


def render_blog_index(articles: list[Article], index_file: Path | None) -> str:
    html = inject_meta(_shell(index_file), "/blog",
                       {"title": BLOG_TITLE, "description": BLOG_DESCRIPTION})
    html = _set_meta(html, "property", "og:type", "website")
    if articles:
        items = "".join(
            f'<li class="blog-item"><article><h2><a href="{escape(a.path, quote=True)}">'
            f"{escape(a.title)}</a></h2><p>{escape(a.description)}</p>{_time(a)}</article></li>"
            for a in articles)
        listing = f'<ul class="blog-list">{items}</ul>'
    else:
        listing = f'<p class="blog-empty">{escape(EMPTY_TEXT)}</p>'
    inner = (f'<main class="blog-ssr"><header><h1>{escape(BLOG_H1)}</h1>'
             f"<p>{escape(BLOG_INTRO)}</p></header>{listing}</main>")
    html = _with_root(html, inner)
    return html.replace("</body>", _bootstrap({"page": "index",
                                               "articles": [a.summary() for a in articles]})
                        + "\n</body>", 1)


def render_blog_article(a: Article, index_file: Path | None) -> str:
    html = inject_meta(_shell(index_file), a.path,
                       {"title": f"{a.title} — Блог TgSell", "description": a.description})
    html = _set_meta(html, "property", "og:type", "article")
    html = _set_meta(html, "property", "article:published_time", a.date_iso)
    html = _before_head_end(html, f'<script type="application/ld+json" id="blog-article-schema">'
                                  f"{safe_json(article_schema(a))}</script>")
    inner = (f'<main class="blog-ssr"><article class="blog-article">'
             f'<nav aria-label="Навігація"><a href="/blog">← Блог</a></nav>'
             f"<header><h1>{escape(a.title)}</h1>{_time(a)}</header>"
             f'<div class="blog-body">{a.body_html}</div></article></main>')
    html = _with_root(html, inner)
    return html.replace("</body>", _bootstrap({"page": "article", "article": a.detail()})
                        + "\n</body>", 1)


def render_blog_not_found(full_path: str, index_file: Path | None) -> str:
    # Canonical/og:url of a 404 never echo the requested slug back.
    html = inject_meta(_shell(index_file), "/blog",
                       {"title": NOT_FOUND_TITLE, "description": NOT_FOUND_DESCRIPTION, "noindex": True})
    inner = ('<main class="blog-ssr"><h1>Статтю не знайдено</h1>'
             "<p>Такої статті немає або вона ще не опублікована.</p>"
             '<p><a href="/blog">Усі статті блогу</a></p></main>')
    return _with_root(html, inner)
