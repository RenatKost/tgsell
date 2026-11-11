"""Blog content: markdown articles with YAML frontmatter in ``content/blog/<slug>.md``.

Only ``status: published`` articles are ever exposed (HTML pages, API, sitemap).
Markdown is rendered server-side with raw HTML disabled and a strict link whitelist,
so the resulting HTML is safe to inject into the page (and into React via
dangerouslySetInnerHTML). No DB, no network, no Railway variables.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from markdown_it import MarkdownIt

logger = logging.getLogger(__name__)

SITE_URL = "https://tgsell.me"
_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # backend/ locally, /app in the Railway image
CONTENT_DIR_CANDIDATES = (
    _BACKEND_ROOT / "content" / "blog",          # /app/content/blog (Dockerfile.railway COPY)
    _BACKEND_ROOT.parent / "content" / "blog",   # repository root checkout
)
SERVICE_FILES = frozenset({"readme.md", "qa.md", "sources.md", "topics.md"})
REQUIRED_FIELDS = ("title", "description", "slug", "lang", "status", "date")
STATUSES = frozenset({"draft", "published"})
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG = 120
MAX_TITLE = 200
MAX_DESCRIPTION = 500
MAX_FILE_BYTES = 256 * 1024
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BLOG_LINK_RE = re.compile(r"^(?:https://tgsell\.me)?/blog/([^/?#]+)/?(?:[?#].*)?$")

UK_MONTHS = ("січня", "лютого", "березня", "квітня", "травня", "червня", "липня",
             "серпня", "вересня", "жовтня", "листопада", "грудня")


class BlogContentError(ValueError):
    """Invalid article file (frontmatter, schema or body)."""


@dataclass(frozen=True)
class Article:
    slug: str
    title: str
    description: str
    lang: str
    status: str
    date: _dt.date
    body_html: str
    blog_links: tuple[str, ...]  # slugs this article links to under /blog/

    @property
    def published(self) -> bool:
        return self.status == "published"

    @property
    def path(self) -> str:
        return f"/blog/{self.slug}"

    @property
    def url(self) -> str:
        return SITE_URL + self.path

    @property
    def date_iso(self) -> str:
        return self.date.isoformat()

    @property
    def date_human(self) -> str:
        return format_date_uk(self.date)

    def summary(self) -> dict:
        return {"slug": self.slug, "title": self.title, "description": self.description,
                "date": self.date_iso, "url": self.url}

    def detail(self) -> dict:
        return self.summary() | {"html": self.body_html}


def format_date_uk(d: _dt.date) -> str:
    return f"{d.day} {UK_MONTHS[d.month - 1]} {d.year}"


# ---------------------------------------------------------------- frontmatter

class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""


def _construct_mapping(loader, node, deep=False):
    keys = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise BlogContentError(f"duplicate frontmatter key: {key!r}")
        keys.add(key)
    return loader.construct_mapping(node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _parse_yaml(text: str) -> dict:
    try:
        for ev in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(ev, yaml.AliasEvent) or getattr(ev, "anchor", None):
                raise BlogContentError("YAML anchors/aliases are not allowed")
            tag = getattr(ev, "tag", None)
            implicit = getattr(ev, "implicit", True)
            explicit = (not implicit[0]) if isinstance(implicit, tuple) else (not implicit)
            if tag and explicit:
                raise BlogContentError("explicit YAML tags are not allowed")
        data = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 — strict SafeLoader subclass
    except BlogContentError:
        raise
    except (yaml.YAMLError, ValueError) as e:  # ValueError: e.g. impossible date 2026-02-30
        raise BlogContentError(f"malformed frontmatter: {type(e).__name__}") from None
    if not isinstance(data, dict):
        raise BlogContentError("frontmatter must be a mapping")
    return data


def split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise BlogContentError("missing frontmatter")
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return _parse_yaml("".join(lines[1:i])), "".join(lines[i + 1:])
    raise BlogContentError("unterminated frontmatter")


def _plain(value, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise BlogContentError(f"{field} must be a string")
    v = value.strip()
    if not v:
        raise BlogContentError(f"{field} is empty")
    if len(v) > limit:
        raise BlogContentError(f"{field} is longer than {limit}")
    if _CONTROL_RE.search(v):
        raise BlogContentError(f"{field} contains control characters")
    return v


def _date(value) -> _dt.date:
    if isinstance(value, _dt.datetime):
        raise BlogContentError("date must be YYYY-MM-DD without time")
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str) and _DATE_RE.match(value.strip()):
        try:
            return _dt.date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise BlogContentError("date must be a real YYYY-MM-DD date")


def validate_meta(meta: dict) -> dict:
    unknown = set(meta) - set(REQUIRED_FIELDS)
    if unknown:
        raise BlogContentError(f"unknown frontmatter fields: {sorted(map(str, unknown))}")
    missing = [f for f in REQUIRED_FIELDS if f not in meta]
    if missing:
        raise BlogContentError(f"missing frontmatter fields: {missing}")
    slug = meta["slug"]
    if not isinstance(slug, str) or len(slug) > MAX_SLUG or not SLUG_RE.match(slug):
        raise BlogContentError("invalid slug")
    if meta["lang"] != "uk":
        raise BlogContentError("lang must be uk")
    if meta["status"] not in STATUSES:
        raise BlogContentError("status must be draft or published")
    return {"title": _plain(meta["title"], "title", MAX_TITLE),
            "description": _plain(meta["description"], "description", MAX_DESCRIPTION),
            "slug": slug, "lang": "uk", "status": meta["status"], "date": _date(meta["date"])}


# ---------------------------------------------------------------- markdown

_CTRL_OR_SPACE = re.compile(r"[\x00-\x20\x7f-\x9f\u2028\u2029]")


def safe_url(url: str) -> bool:
    """Whitelist: http(s) absolute URLs, local /paths (not //host) and #anchors."""
    if not isinstance(url, str) or not url or _CTRL_OR_SPACE.search(url) or "\\" in url:
        return False
    if url.startswith("#"):
        return True
    if url.startswith("/"):
        return not url.startswith("//")
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc) and "@" not in parts.netloc


def _is_external(url: str) -> bool:
    if url.startswith(("/", "#")):
        return False
    host = (urlsplit(url).hostname or "").lower()
    return host not in ("tgsell.me", "www.tgsell.me")


def _make_md() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    md.disable(["image", "html_block", "html_inline"])
    md.validateLink = safe_url

    def link_open(self, tokens, idx, options, env):
        tok = tokens[idx]
        href = tok.attrGet("href") or ""
        if _is_external(href):
            tok.attrSet("rel", "noopener noreferrer")
            tok.attrSet("target", "_blank")
        return self.renderToken(tokens, idx, options, env)

    md.add_render_rule("link_open", link_open)
    return md


_MD = _make_md()


def render_body(body: str, title: str) -> tuple[str, tuple[str, ...]]:
    """Render markdown body. It must start with exactly one ``# <title>``; that h1 is
    dropped from the body (the page template renders it once from ``title``)."""
    tokens = _MD.parse(body)
    h1 = [i for i, t in enumerate(tokens) if t.type == "heading_open" and t.tag == "h1"]
    if len(h1) != 1 or h1[0] != 0:
        raise BlogContentError("body must start with exactly one h1")
    heading_text = tokens[1].content.strip()
    if heading_text != title:
        raise BlogContentError("h1 does not match title")
    rest = tokens[3:]  # heading_open, inline, heading_close
    links: list[str] = []
    for t in rest:
        for child in (t.children or []):
            if child.type == "link_open":
                m = _BLOG_LINK_RE.match(child.attrGet("href") or "")
                if m:
                    links.append(m.group(1))
    html = _MD.renderer.render(rest, _MD.options, {})
    return html, tuple(dict.fromkeys(links))


# ---------------------------------------------------------------- loading

def parse_article(text: str, filename_stem: str) -> Article:
    meta, body = split_frontmatter(text)
    m = validate_meta(meta)
    if m["slug"] != filename_stem:
        raise BlogContentError("slug does not match file name")
    html, links = render_body(body, m["title"])
    return Article(slug=m["slug"], title=m["title"], description=m["description"], lang=m["lang"],
                   status=m["status"], date=m["date"], body_html=html, blog_links=links)


def _article_files(directory: Path) -> list[Path]:
    root = directory.resolve()
    out = []
    for p in sorted(directory.glob("*.md")):
        if p.name.lower() in SERVICE_FILES:
            continue
        if p.is_symlink() or p.resolve().parent != root or not p.is_file():
            raise BlogContentError(f"{p.name}: symlinks/outside files are not allowed")
        out.append(p)
    return out


def load_directory(directory: Path, strict: bool = False) -> list[Article]:
    """All valid articles (drafts included), sorted date desc + slug.

    strict=True raises on the first problem (content validation / tests); otherwise invalid
    files are logged and skipped so one bad file never breaks the site.
    """
    if not directory.is_dir():
        return []
    articles: dict[str, Article] = {}
    for p in _article_files(directory):
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                raise BlogContentError("file too large")
            art = parse_article(p.read_text(encoding="utf-8"), p.stem)
            if art.slug in articles:
                raise BlogContentError("duplicate slug")
            articles[art.slug] = art
        except (ValueError, UnicodeDecodeError) as e:  # BlogContentError is a ValueError
            if strict:
                raise BlogContentError(f"{p.name}: {e}") from None
            logger.warning("blog: skipping %s: %s", p.name, e)
    published = {s for s, a in articles.items() if a.published}
    for a in list(articles.values()):
        broken = [s for s in a.blog_links if s not in published] if a.published else []
        if broken:
            msg = f"{a.slug}.md: links to unpublished/unknown blog slugs {broken}"
            if strict:
                raise BlogContentError(msg)
            logger.warning("blog: hiding %s", msg)
            articles.pop(a.slug)
    return sorted(articles.values(), key=lambda a: (-a.date.toordinal(), a.slug))


def content_dir() -> Path:
    for d in CONTENT_DIR_CANDIDATES:
        if d.is_dir():
            return d
    return CONTENT_DIR_CANDIDATES[0]


_cache: dict[Path, tuple[tuple, list[Article]]] = {}


def _signature(directory: Path) -> tuple:
    if not directory.is_dir():
        return ()
    return tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(directory.glob("*.md")))


def published_articles(directory: Path | None = None) -> list[Article]:
    d = directory or content_dir()
    sig = _signature(d)
    hit = _cache.get(d)
    if hit is None or hit[0] != sig:
        try:
            arts = load_directory(d)
        except BlogContentError as e:
            logger.warning("blog: content directory rejected: %s", e)
            arts = []
        hit = (sig, [a for a in arts if a.published])
        _cache[d] = hit
    return list(hit[1])


def get_published(slug: str, directory: Path | None = None) -> Article | None:
    if not isinstance(slug, str) or not SLUG_RE.match(slug) or len(slug) > MAX_SLUG:
        return None
    return next((a for a in published_articles(directory) if a.slug == slug), None)
