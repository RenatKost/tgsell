"""Server-side per-route meta injection into the SPA index.html.

Crawlers that don't execute JS (and social previews: Telegram, Facebook, X)
must see the correct <title>, description, canonical and OG/Twitter tags.
Meta for SEO landing pages lives in app/data/route_meta.json (a copy of
src/seo/routeMeta.json, kept identical by tests/test_spa_meta.py).
For every other SPA path only canonical/og:url are rewritten to the page's own URL.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from html import escape
from pathlib import Path

SITE_URL = "https://tgsell.me"
_META_FILE = Path(__file__).resolve().parent.parent / "data" / "route_meta.json"
# Paths whose canonical should point elsewhere (redirect aliases).
CANONICAL_ALIASES = {"/terms": "/oferta"}


@lru_cache(maxsize=1)
def route_meta() -> dict[str, dict[str, str]]:
    return json.loads(_META_FILE.read_text(encoding="utf-8"))


def seo_landing_paths() -> list[str]:
    return [p for p in route_meta() if p != "/"]


def normalize_path(full_path: str) -> str:
    p = "/" + (full_path or "").split("?", 1)[0].split("#", 1)[0].strip("/")
    return p


def _sub(pattern: str, repl: str, html: str) -> str:
    return re.sub(pattern, lambda _m: repl, html, count=1, flags=re.IGNORECASE | re.DOTALL)


def _set_meta(html: str, attr: str, key: str, value: str) -> str:
    tag = f'<meta {attr}="{key}" content="{escape(value, quote=True)}" />'
    pat = rf'<meta\s+{attr}="{re.escape(key)}"\s+content="[^"]*"\s*/?>'
    if re.search(pat, html, flags=re.IGNORECASE):
        return _sub(pat, tag, html)
    return html.replace("</head>", f"  {tag}\n</head>", 1)


def _set_canonical(html: str, url: str) -> str:
    tag = f'<link rel="canonical" href="{escape(url, quote=True)}" />'
    pat = r'<link\s+rel="canonical"\s+href="[^"]*"\s*/?>'
    if re.search(pat, html, flags=re.IGNORECASE):
        return _sub(pat, tag, html)
    return html.replace("</head>", f"  {tag}\n</head>", 1)


def inject_meta(html: str, full_path: str) -> str:
    path = normalize_path(full_path)
    canon_path = CANONICAL_ALIASES.get(path, path)
    url = SITE_URL + ("/" if canon_path == "/" else canon_path)
    html = _set_canonical(html, url)
    html = _set_meta(html, "property", "og:url", url)
    meta = route_meta().get(path)
    if not meta:
        return html
    title, desc = meta["title"], meta["description"]
    html = _sub(r"<title>.*?</title>", f"<title>{escape(title, quote=False)}</title>", html)
    html = _set_meta(html, "name", "description", desc)
    html = _set_meta(html, "property", "og:title", title)
    html = _set_meta(html, "property", "og:description", desc)
    html = _set_meta(html, "name", "twitter:title", title)
    html = _set_meta(html, "name", "twitter:description", desc)
    if path != "/" and meta.get("h1"):
        # No-JS fallback content; React's createRoot() replaces it on mount.
        fallback = (f'<div id="root"><main><h1>{escape(meta["h1"], quote=False)}</h1>'
                    f'<p>{escape(desc, quote=False)}</p></main></div>')
        html = _sub(r'<div id="root">\s*</div>', fallback, html)
    return html


@lru_cache(maxsize=64)
def _render_cached(index_path: str, mtime_ns: int, full_path: str) -> str:
    return inject_meta(Path(index_path).read_text(encoding="utf-8"), full_path)


def render_index(index_file: Path, full_path: str) -> str:
    path = normalize_path(full_path)
    return _render_cached(str(index_file), index_file.stat().st_mtime_ns, path)
