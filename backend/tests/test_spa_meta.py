"""SEO landing pages: server-side per-route meta injection, sitemap/robots, content rules."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.utils import spa_meta

REPO = Path(__file__).resolve().parents[2]
LANDINGS = ["/kupyty-telegram-kanal", "/prodaty-telegram-kanal", "/skilky-koshtuye-telegram-kanal"]
INDEX = (REPO / "index.html").read_text(encoding="utf-8")


def _meta(html: str, attr: str, key: str) -> list[str]:
    return re.findall(rf'<meta {attr}="{re.escape(key)}" content="([^"]*)"', html)


def test_backend_meta_copy_matches_frontend():
    front = json.loads((REPO / "src" / "seo" / "routeMeta.json").read_text(encoding="utf-8"))
    assert front == spa_meta.route_meta()


@pytest.mark.parametrize("path", LANDINGS)
def test_landing_meta_injected(path):
    meta = spa_meta.route_meta()[path]
    html = spa_meta.inject_meta(INDEX, path.lstrip("/"))
    assert html.count("<title>") == 1 and f"<title>{meta['title']}</title>" in html
    assert _meta(html, "name", "description") == [meta["description"]]
    assert _meta(html, "property", "og:title") == [meta["title"]]
    assert _meta(html, "property", "og:description") == [meta["description"]]
    assert _meta(html, "property", "og:url") == [f"https://tgsell.me{path}"]
    assert _meta(html, "name", "twitter:title") == [meta["title"]]
    assert _meta(html, "name", "twitter:description") == [meta["description"]]
    assert re.findall(r'<link rel="canonical" href="([^"]*)"', html) == [f"https://tgsell.me{path}"]
    assert f"<h1>{meta['h1']}</h1>" in html


def test_trailing_slash_and_query_normalized():
    html = spa_meta.inject_meta(INDEX, "kupyty-telegram-kanal/")
    assert 'href="https://tgsell.me/kupyty-telegram-kanal"' in html


def test_other_pages_get_own_canonical_only():
    html = spa_meta.inject_meta(INDEX, "catalog")
    assert 'rel="canonical" href="https://tgsell.me/catalog"' in html
    assert _meta(html, "property", "og:url") == ["https://tgsell.me/catalog"]
    assert re.search(r"<title>TgSell — Біржа Telegram каналів", html)
    assert 'href="https://tgsell.me/oferta"' in spa_meta.inject_meta(INDEX, "terms")
    assert 'href="https://tgsell.me/"' in spa_meta.inject_meta(INDEX, "")


def test_content_rules():
    banned = ["TRC-20", "TRC20", "покупцю 0%", "продавцю 3%", "500+", "2.4M"]
    for path, m in spa_meta.route_meta().items():
        for field in ("title", "description"):
            assert not any(b in m[field] for b in banned), (path, field)
        assert len(m["description"]) <= 200
    for d in _meta(INDEX, "name", "description"):
        assert "TRC" not in d
    for f in ["BuyChannelLanding.jsx", "SellChannelLanding.jsx", "ChannelPriceCalculatorPage.jsx"]:
        src = (REPO / "src" / "layouts" / f).read_text(encoding="utf-8")
        assert not any(b in src for b in banned), f


def test_calculator_numbers_match_market_data():
    data = json.loads((Path(spa_meta.__file__).resolve().parents[1] / "data" / "market_prices.json").read_text())
    js = (REPO / "src" / "seo" / "marketData.js").read_text(encoding="utf-8")
    num = lambda k: float(re.search(rf"{k}: ([0-9.]+)", js).group(1))  # noqa: E731
    assert num("medianPerSub") == data["overall"]["pps"]
    assert num("lowPerSub") == data["segments"]["network"]["pps"]
    assert num("highPerSub") == data["segments"]["channel"]["pps"]


# Methodology (sample sizes, source, period, FX rate) must never be user-visible.
METHODOLOGY_LEAKS = ["152", "158", "65 лот", "82 лот", "оголошен", "бірж", "41.5", "41,5", "15.07", "15.10",
                     "ціни запиту", "ціна запиту", "медіан", "tumobog"]


def test_calculator_methodology_not_disclosed():
    calc = spa_meta.route_meta()["/skilky-koshtuye-telegram-kanal"]
    for field in ("title", "description", "h1"):
        assert not any(b in calc[field] for b in METHODOLOGY_LEAKS), field
    html = spa_meta.inject_meta(INDEX, "skilky-koshtuye-telegram-kanal")
    fallback = html[html.index('<div id="root">'):html.index("</main></div>")]
    assert not any(b in fallback for b in METHODOLOGY_LEAKS)
    assert "актуальних ринкових цін" in calc["description"]
    src = (REPO / "src" / "layouts" / "ChannelPriceCalculatorPage.jsx").read_text(encoding="utf-8")
    assert not any(b in src for b in METHODOLOGY_LEAKS)
    assert "MARKET." not in src  # no raw coefficients / counts rendered
    assert "Оцінка базується на аналізі актуальних ринкових цін на українські Telegram-канали" in src
    js = (REPO / "src" / "seo" / "marketData.js").read_text(encoding="utf-8")
    code = "\n".join(l for l in js.splitlines() if not l.lstrip().startswith("//"))
    for k in ("listings", "nPerSub", "nNetwork", "nChannel", "period", "uahRate"):
        assert not re.search(rf"\b{k}\b", code), k
    for f in ["BuyChannelLanding.jsx", "SellChannelLanding.jsx"]:
        lsrc = (REPO / "src" / "layouts" / f).read_text(encoding="utf-8")
        assert not any(b in lsrc for b in ["152", "158", "41.5", "медіан", "реальних оголошень", "ціни оголошень"]), f


def test_sitemap_and_robots_include_landings(pg_orm):
    import importlib  # same import path as test_head_requests (models loaded by pg_orm)
    seo = importlib.import_module("app.routers.seo")
    xml = seo.build_sitemap([])
    for p in LANDINGS:
        assert f"<loc>https://tgsell.me{p}</loc>" in xml
        assert f"Allow: {p}" in seo.ROBOTS_TXT


def test_main_spa_whitelist_includes_landings():
    src = (REPO / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    for p in LANDINGS:
        assert f'"{p.lstrip("/")}"' in src
    assert "render_index(" in src


def test_render_index_reads_file(tmp_path):
    f = tmp_path / "index.html"
    f.write_text(INDEX, encoding="utf-8")
    out = spa_meta.render_index(f, "prodaty-telegram-kanal")
    assert "https://tgsell.me/prodaty-telegram-kanal" in out
