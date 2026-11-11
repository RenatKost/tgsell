"""/blog SSR pages, API, SEO metadata, real 404s and sitemap (no DB data, no prod)."""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routers import blog as blog_router
from app.services import blog_content as bc
from app.utils.head_support import HeadAsGetMiddleware

REPO = Path(__file__).resolve().parents[2]
INDEX = (REPO / "index.html").read_text(encoding="utf-8")
REAL_SLUGS = ["yak-prodaty-telegram-kanal", "yak-kupyty-telegram-kanal", "harant-eskrou-telegram-kanalu",
              "otsinka-vartosti-telegram-kanalu", "perevirka-telegram-kanalu-na-nakrutku"]


def _art(slug, title, status="published", body="Перший абзац статті.", description="Опис <статті> & \"лапки\""):
    return (f"---\ntitle: '{title}'\ndescription: '{description}'\nslug: {slug}\nlang: uk\n"
            f"status: {status}\ndate: 2026-11-08\n---\n\n# {title}\n\n{body}\n")


@pytest.fixture
def blog_dir(tmp_path, monkeypatch):
    d = tmp_path / "blog"
    d.mkdir()
    (d / "pub-article.md").write_text(_art("pub-article", "Опублікована стаття </script>",
                                           body="## Розділ\n\nТекст статті без JS. [інша](/blog/second-article)"),
                                      encoding="utf-8")
    (d / "second-article.md").write_text(_art("second-article", "Друга стаття"), encoding="utf-8")
    (d / "secret-draft.md").write_text(_art("secret-draft", "Секретна чернетка", status="draft",
                                            description="Опис чернетки"), encoding="utf-8")
    monkeypatch.setattr(bc, "content_dir", lambda: d)
    return d


@pytest.fixture
def index_html(tmp_path, monkeypatch):
    f = tmp_path / "index.html"
    f.write_text(INDEX, encoding="utf-8")
    monkeypatch.setattr(blog_router, "index_file", lambda: f)
    return f


def _app():
    app = FastAPI()
    app.add_middleware(HeadAsGetMiddleware)
    app.include_router(blog_router.api_router, prefix="/api")
    app.include_router(blog_router.router)
    return app


async def _get(path, method="GET", app=None):
    async with AsyncClient(transport=ASGITransport(app=app or _app()), base_url="http://evil.host") as cl:
        return await cl.request(method, path)


def _meta(html, attr, key):
    return re.findall(rf'<meta {attr}="{re.escape(key)}" content="([^"]*)"', html)


def _canon(html):
    return re.findall(r'<link rel="canonical" href="([^"]*)"', html)


def _schemas(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)]


@pytest.mark.asyncio
async def test_index_lists_published_only(blog_dir, index_html):
    r = await _get("/blog?utm=x")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    t = r.text
    assert "<h1>Блог TgSell</h1>" in t
    assert 'href="/blog/pub-article"' in t and 'href="/blog/second-article"' in t
    assert "secret-draft" not in t and "Секретна чернетка" not in t and "Опис чернетки" not in t
    assert _canon(t) == ["https://tgsell.me/blog"]
    assert _meta(t, "property", "og:url") == ["https://tgsell.me/blog"]
    assert _meta(t, "property", "og:type") == ["website"]
    assert t.count("<title>") == 1 and "<title>Блог TgSell" in t
    assert _schemas(t) == []  # no Article schema on the index
    assert "evil.host" not in t


@pytest.mark.asyncio
async def test_index_empty_state(tmp_path, monkeypatch, index_html):
    monkeypatch.setattr(bc, "content_dir", lambda: tmp_path / "empty")
    r = await _get("/blog")
    assert r.status_code == 200 and "Статті незабаром з’являться." in r.text


@pytest.mark.asyncio
async def test_published_article_full_html_and_seo(blog_dir, index_html):
    r = await _get("/blog/pub-article?ref=abc")
    assert r.status_code == 200
    t = r.text
    head = t.split("</head>", 1)[0]
    # full article text is in the response (no JS needed), exactly one h1
    assert "Текст статті без JS." in t and "<h2>Розділ</h2>" in t
    assert t.count("<h1") == 1 and "<h1>Опублікована стаття &lt;/script&gt;</h1>" in t
    assert head.count("<title>") == 1
    assert "<title>Опублікована стаття &lt;/script&gt; — Блог TgSell</title>" in head
    assert _canon(t) == ["https://tgsell.me/blog/pub-article"]
    assert _meta(t, "property", "og:url") == ["https://tgsell.me/blog/pub-article"]
    assert _meta(t, "property", "og:type") == ["article"]
    assert _meta(t, "property", "og:title") == ["Опублікована стаття &lt;/script&gt; — Блог TgSell"]
    assert _meta(t, "name", "description") == ["Опис &lt;статті&gt; &amp; &quot;лапки&quot;"]
    assert _meta(t, "property", "og:description") == ["Опис &lt;статті&gt; &amp; &quot;лапки&quot;"]
    assert _meta(t, "property", "og:locale") == ["uk_UA"]
    assert _meta(t, "name", "robots") == ["index, follow"]
    (schema,) = _schemas(t)
    assert schema["@type"] == "Article" and schema["@context"] == "https://schema.org"
    assert schema["headline"] == "Опублікована стаття </script>"
    assert schema["inLanguage"] == "uk" and schema["datePublished"] == "2026-11-08"
    assert schema["mainEntityOfPage"]["@id"] == "https://tgsell.me/blog/pub-article"
    assert "author" not in schema and "dateModified" not in schema
    # no </script> breakout anywhere: only the expected script tags
    assert t.count("</script>") == INDEX.count("</script>") + 2  # JSON-LD + bootstrap
    assert "evil.host" not in t and "ref=abc" not in t


@pytest.mark.asyncio
async def test_article_works_without_built_frontend(blog_dir, monkeypatch):
    monkeypatch.setattr(blog_router, "index_file", lambda: None)
    r = await _get("/blog/second-article")
    assert r.status_code == 200 and "<h1>Друга стаття</h1>" in r.text
    assert _canon(r.text) == ["https://tgsell.me/blog/second-article"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/blog/secret-draft", "/blog/unknown-slug", "/blog/Bad_Slug",
                                  "/blog/a/b", "/blog/..%2Fsecret-draft", "/blog/secret-draft/",
                                  "/blog/pub-article/extra"])
async def test_draft_unknown_nested_are_real_404(blog_dir, index_html, path):
    r = await _get(path)
    assert r.status_code == 404
    t = r.text
    assert "Статтю не знайдено" in t
    assert _meta(t, "name", "robots") == ["noindex, nofollow"]
    assert "Секретна чернетка" not in t and "Опис чернетки" not in t
    assert _canon(t) == ["https://tgsell.me/blog"]
    assert _schemas(t) == []


@pytest.mark.asyncio
async def test_trailing_slash_redirects(blog_dir, index_html):
    r = await _get("/blog/")
    assert r.status_code == 308 and r.headers["location"] == "/blog"
    r = await _get("/blog/pub-article/")
    assert r.status_code == 308 and r.headers["location"] == "/blog/pub-article"


@pytest.mark.asyncio
@pytest.mark.parametrize("path,status", [("/blog", 200), ("/blog/pub-article", 200), ("/blog/secret-draft", 404)])
async def test_head_matches_get(blog_dir, index_html, path, status):
    g = await _get(path)
    h = await _get(path, "HEAD")
    assert g.status_code == h.status_code == status and h.content == b""


@pytest.mark.asyncio
async def test_api_published_only(blog_dir):
    r = await _get("/api/blog")
    assert r.status_code == 200
    assert [a["slug"] for a in r.json()["articles"]] == ["pub-article", "second-article"]
    r = await _get("/api/blog/pub-article")
    assert r.status_code == 200 and "<h2>Розділ</h2>" in r.json()["html"]
    for slug in ("secret-draft", "nope", "Bad_Slug"):
        assert (await _get(f"/api/blog/{slug}")).status_code == 404


@pytest.mark.asyncio
async def test_bootstrap_json_matches_api(blog_dir, index_html):
    t = (await _get("/blog/pub-article")).text
    m = re.search(r'<script type="application/json" id="tgsell-blog-data">(.*?)</script>', t, re.S)
    data = json.loads(m.group(1))
    assert data["page"] == "article"
    assert data["article"] == (await _get("/api/blog/pub-article")).json()


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", REAL_SLUGS)
async def test_real_articles_published(slug, index_html):
    r = await _get(f"/blog/{slug}")
    assert r.status_code == 200
    a = bc.get_published(slug)
    assert f"<title>{a.title} — Блог TgSell</title>" in r.text
    assert _canon(r.text) == [f"https://tgsell.me/blog/{slug}"]
    assert _schemas(r.text)[0]["headline"] == a.title


@pytest.mark.asyncio
async def test_real_index_lists_all_five(index_html):
    t = (await _get("/blog")).text
    for slug in REAL_SLUGS:
        assert f'href="/blog/{slug}"' in t


# ---------------------------------------------------------------- sitemap / robots

class _BrokenDB:
    async def execute(self, *a, **kw):
        raise RuntimeError("db down")


@pytest.mark.asyncio
async def test_sitemap_lists_published_articles(blog_dir, orm):
    seo = importlib.import_module("app.routers.seo")
    db_mod = importlib.import_module("app.database")
    app = FastAPI()
    app.include_router(seo.router)

    async def broken_db():
        yield _BrokenDB()

    app.dependency_overrides[db_mod.get_db] = broken_db  # channel lookup fails → blog URLs still present
    r = await _get("/sitemap.xml", app=app)
    assert r.status_code == 200
    x = r.text
    assert x.count("<loc>https://tgsell.me/blog</loc>") == 1
    assert x.count("<loc>https://tgsell.me/blog/pub-article</loc><lastmod>2026-11-08</lastmod>") == 1
    assert x.count("<loc>https://tgsell.me/blog/second-article</loc>") == 1
    assert "secret-draft" not in x
    import xml.etree.ElementTree as ET
    ET.fromstring(x.encode())


def test_sitemap_real_articles(orm):
    seo = importlib.import_module("app.routers.seo")
    xml = seo.build_sitemap([], bc.published_articles())
    for slug in REAL_SLUGS:
        assert xml.count(f"<loc>https://tgsell.me/blog/{slug}</loc>") == 1


def test_robots_allows_blog(orm):
    seo = importlib.import_module("app.routers.seo")
    assert "Disallow: /blog" not in seo.ROBOTS_TXT and "Allow: /\n" in seo.ROBOTS_TXT
    assert "Sitemap: https://tgsell.me/sitemap.xml" in seo.ROBOTS_TXT


def test_main_includes_blog_before_spa_catch_all():
    src = (REPO / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert src.index("app.include_router(blog_router.router)") < src.index('@app.get("/{full_path:path}")')


def test_railway_image_ships_blog_content():
    assert "COPY content/blog/ ./content/blog/" in (REPO / "Dockerfile.railway").read_text(encoding="utf-8")
