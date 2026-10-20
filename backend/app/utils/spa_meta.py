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


# Task 33: static meta for /catalog (not an SEO landing: no no-JS h1 fallback).
EXTRA_ROUTE_META: dict[str, dict[str, str]] = {
    "/catalog": {
        "title": "Каталог Telegram-каналів на продаж — TgSell",
        "description": ("Каталог Telegram-каналів на продаж: фільтри за тематикою, ціною, "
                        "кількістю підписників і переглядами. Безпечна угода через гарант-ескроу в USDT."),
    },
}

_CHANNEL_RE = re.compile(r"^/channel/(\d+)$")


def channel_id_from_path(full_path: str) -> int | None:
    m = _CHANNEL_RE.match(normalize_path(full_path))
    return int(m.group(1)) if m else None


def _fmt_int(n) -> str:
    return f"{int(n or 0):,}".replace(",", "\u00a0")


def _fmt_price(p) -> str:
    v = float(p or 0)
    return _fmt_int(v) if v == int(v) else f"{v:,.2f}".replace(",", "\u00a0")


def channel_meta(channel) -> dict:
    """Per-channel meta for /channel/:id. channel=None → unknown lot (noindex).

    Only publicly visible facts (name, subscribers, price, avatar) — never internal
    methodology. Unpublished lots (pending/rejected/removed) get a generic noindex
    page without any details.
    """
    from app.services.listing_visibility import channel_is_public
    from app.utils.avatars import public_channel_avatar_url
    if channel is None or not channel_is_public(channel):
        return {"title": "Оголошення недоступне — TgSell",
                "description": "Це оголошення недоступне або ще не опубліковане на TgSell.",
                "noindex": True}
    name = (channel.channel_name or "Telegram-канал").strip()
    subs = _fmt_int(channel.subscribers_count)
    price = _fmt_price(channel.price)
    sold = getattr(channel.status, "value", channel.status) == "sold"
    title = f"{name} — Telegram-канал на продаж, {subs} підписників | TgSell"
    if sold:
        title = f"{name} — Telegram-канал (продано) | TgSell"
    desc = (f"Telegram-канал «{name}»: {subs} підписників, ціна {price} USDT. "
            "Купівля через гарант-ескроу TgSell — кошти продавцю лише після передачі каналу.")
    if sold:
        desc = f"Telegram-канал «{name}»: {subs} підписників. Канал уже продано через TgSell."
    meta = {"title": title, "description": desc}
    avatar = public_channel_avatar_url(channel.id, channel.avatar_url)
    if avatar:
        meta["image"] = SITE_URL + avatar
    return meta


def _set_robots(html: str, value: str) -> str:
    return _set_meta(html, "name", "robots", value)


def inject_meta(html: str, full_path: str, override: dict | None = None) -> str:
    path = normalize_path(full_path)
    canon_path = CANONICAL_ALIASES.get(path, path)
    url = SITE_URL + ("/" if canon_path == "/" else canon_path)
    html = _set_canonical(html, url)
    html = _set_meta(html, "property", "og:url", url)
    meta = override or route_meta().get(path) or EXTRA_ROUTE_META.get(path)
    if not meta:
        return html
    if meta.get("noindex"):
        html = _set_robots(html, "noindex, nofollow")
    if meta.get("image"):
        html = _set_meta(html, "property", "og:image", meta["image"])
        html = _set_meta(html, "name", "twitter:image", meta["image"])
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


@lru_cache(maxsize=2)
def _index_text(index_path: str, mtime_ns: int) -> str:
    return Path(index_path).read_text(encoding="utf-8")


def render_index(index_file: Path, full_path: str, override: dict | None = None) -> str:
    path = normalize_path(full_path)
    if override is not None:  # dynamic (DB-backed) meta: never cached
        return inject_meta(_index_text(str(index_file), index_file.stat().st_mtime_ns), path, override)
    return _render_cached(str(index_file), index_file.stat().st_mtime_ns, path)
