"""Blog loader: frontmatter schema, drafts, safe markdown, cross-link gate, real content."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from app.services import blog_content as bc
from app.utils.blog_html import safe_json

REPO = Path(__file__).resolve().parents[2]
REAL_DIR = REPO / "content" / "blog"
EXPECTED = {"yak-prodaty-telegram-kanal", "yak-kupyty-telegram-kanal", "harant-eskrou-telegram-kanalu",
            "otsinka-vartosti-telegram-kanalu", "perevirka-telegram-kanalu-na-nakrutku"}


def art(slug="test-article", title="Тестова стаття", status="published", date="2026-11-08",
        body="Текст статті.", extra="", description="Опис статті"):
    return (f'---\ntitle: "{title}"\ndescription: "{description}"\nslug: {slug}\nlang: uk\n'
            f"status: {status}\ndate: {date}\n{extra}---\n\n# {title}\n\n{body}\n")


def write(d: Path, slug: str, text: str) -> Path:
    p = d / f"{slug}.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_valid_article_parses():
    a = bc.parse_article(art(body="## Розділ\n\n- пункт\n\n[каталог](https://tgsell.me/catalog)"), "test-article")
    assert a.published and a.date == dt.date(2026, 11, 8) and a.lang == "uk"
    assert "<h1" not in a.body_html  # h1 is rendered once by the page template
    assert "<h2>Розділ</h2>" in a.body_html and "<li>пункт</li>" in a.body_html
    assert '<a href="https://tgsell.me/catalog">каталог</a>' in a.body_html
    assert a.date_human == "8 листопада 2026"


def test_empty_and_missing_directory(tmp_path):
    assert bc.load_directory(tmp_path) == []
    assert bc.load_directory(tmp_path / "nope") == []
    assert bc.published_articles(tmp_path) == []


def test_drafts_and_service_files_hidden(tmp_path):
    write(tmp_path, "pub-one", art(slug="pub-one"))
    write(tmp_path, "draft-one", art(slug="draft-one", status="draft"))
    for name in ("README", "QA", "sources", "topics"):
        (tmp_path / f"{name}.md").write_text("# службовий файл\n", encoding="utf-8")
    assert [a.slug for a in bc.published_articles(tmp_path)] == ["pub-one"]
    assert bc.get_published("draft-one", tmp_path) is None
    assert bc.get_published("pub-one", tmp_path).slug == "pub-one"
    assert {a.slug for a in bc.load_directory(tmp_path, strict=True)} == {"pub-one", "draft-one"}


def test_sorting_date_desc_then_slug(tmp_path):
    write(tmp_path, "b-old", art(slug="b-old", date="2026-01-01"))
    write(tmp_path, "b-new", art(slug="b-new", date="2026-02-01"))
    write(tmp_path, "a-new", art(slug="a-new", date="2026-02-01"))
    assert [a.slug for a in bc.published_articles(tmp_path)] == ["a-new", "b-new", "b-old"]


@pytest.mark.parametrize("text,stem", [
    (art(status="publish"), "test-article"),
    (art(status=""), "test-article"),
    (art().replace("status: published\n", ""), "test-article"),
    (art().replace("lang: uk", "lang: ru"), "test-article"),
    (art(date="2026-02-30"), "test-article"),
    (art(date="08.11.2026"), "test-article"),
    (art(date="2026-11-08 10:00:00"), "test-article"),
    (art(slug="Bad_Slug"), "Bad_Slug"),
    (art(slug="a" * 121), "a" * 121),
    (art(slug="other-slug"), "test-article"),
    (art(title=""), "test-article"),
    (art(title="Заголовок\\u0007"), "test-article"),
    (art(extra="author: Хтось\n"), "test-article"),
    (art(extra="title: Дубль\n"), "test-article"),
    (art(extra="x: &a 1\ny: *a\n"), "test-article"),
    (art(extra="z: !!python/object:os.system ls\n"), "test-article"),
    ("# Без frontmatter\n", "test-article"),
    ("---\ntitle: [unterminated\n---\n# x\n", "test-article"),
    (art().replace("# Тестова стаття", "# Інший заголовок"), "test-article"),
    (art(body="# Другий h1"), "test-article"),
    (art().replace("\n# Тестова стаття\n", "\nВступ\n\n# Тестова стаття\n"), "test-article"),
])
def test_invalid_articles_rejected(text, stem):
    with pytest.raises(bc.BlogContentError):
        bc.parse_article(text, stem)


def test_invalid_file_skipped_not_fatal(tmp_path):
    write(tmp_path, "good", art(slug="good"))
    write(tmp_path, "bad", art(slug="bad", status="maybe"))
    assert [a.slug for a in bc.published_articles(tmp_path)] == ["good"]
    with pytest.raises(bc.BlogContentError):
        bc.load_directory(tmp_path, strict=True)


def test_symlink_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = write(outside, "evil", art(slug="evil"))
    d = tmp_path / "blog"
    d.mkdir()
    (d / "evil.md").symlink_to(target)
    assert bc.published_articles(d) == []
    with pytest.raises(bc.BlogContentError):
        bc.load_directory(d, strict=True)


def test_broken_cross_links_block_publication(tmp_path):
    write(tmp_path, "a-pub", art(slug="a-pub", body="[чернетка](https://tgsell.me/blog/b-draft)"))
    write(tmp_path, "b-draft", art(slug="b-draft", status="draft"))
    write(tmp_path, "c-pub", art(slug="c-pub", body="[a](/blog/a-pub)"))
    with pytest.raises(bc.BlogContentError, match="b-draft"):
        bc.load_directory(tmp_path, strict=True)
    # Runtime: article with a broken link is hidden (no 404 cross-links on the site)
    assert [a.slug for a in bc.published_articles(tmp_path)] == ["c-pub"]


@pytest.mark.parametrize("slug", ["../etc/passwd", "..%2Fetc", "a/b", "A", "", "a--b", "-a", "a" * 121, "a.md"])
def test_get_published_rejects_bad_slugs(tmp_path, slug):
    write(tmp_path, "a", art(slug="a"))
    assert bc.get_published(slug, tmp_path) is None


# ---------------------------------------------------------------- safety

@pytest.mark.parametrize("body", [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    '<iframe src="https://evil.example"></iframe>',
    "<div onclick='x()'>hi</div>",
])
def test_raw_html_escaped(body):
    html, _ = bc.render_body(f"# T\n\n{body}\n", "T")
    low = html.lower()
    assert "<script" not in low and "<img" not in low and "<iframe" not in low and "<div" not in low
    assert "&lt;" in html


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", "vbscript:msgbox(1)", "data:text/html,<b>x</b>",
    "//evil.example/x", "java%0ascript:alert(1)", "file:///etc/passwd", "https://user@evil.example",
])
def test_unsafe_links_dropped(url):
    html, _ = bc.render_body(f"# T\n\n[клік]({url})\n", "T")
    assert "<a " not in html


def test_images_disabled_and_external_links_rel():
    html, _ = bc.render_body("# T\n\n![x](https://evil.example/p.png) [t](https://telegram.org/faq)\n", "T")
    assert "<img" not in html
    assert '<a href="https://telegram.org/faq" rel="noopener noreferrer" target="_blank">' in html


def test_safe_url_whitelist():
    assert bc.safe_url("https://tgsell.me/catalog") and bc.safe_url("/blog/x") and bc.safe_url("#a")
    assert not bc.safe_url("//x") and not bc.safe_url("javascript:x") and not bc.safe_url("/a\\b")


def test_safe_json_no_script_breakout():
    s = safe_json({"t": "</script><script>alert(1)</script>&\u2028"})
    assert "<" not in s and ">" not in s and "&" not in s and "\u2028" not in s
    import json
    assert json.loads(s)["t"].startswith("</script>")


# ---------------------------------------------------------------- real repo content (release gate)

def test_real_content_valid_and_published_together():
    arts = bc.load_directory(REAL_DIR, strict=True)  # raises on any invalid file / broken cross-link
    slugs = {a.slug for a in arts}
    assert slugs == EXPECTED
    assert all(a.published and a.lang == "uk" for a in arts)
    for a in arts:
        assert set(a.blog_links) <= EXPECTED  # every /blog/ link points to a published article


def test_real_content_has_no_service_files():
    names = {p.name.lower() for p in REAL_DIR.iterdir()}
    assert not names & bc.SERVICE_FILES


def test_real_content_no_internal_methodology():
    text = "\n".join(p.read_text(encoding="utf-8") for p in REAL_DIR.glob("*.md")).lower()
    for banned in ("медіан", "реальних оголошень", "uahrate", "курс грн", "за період з", "оголошень у вибірці"):
        assert banned not in text, banned
