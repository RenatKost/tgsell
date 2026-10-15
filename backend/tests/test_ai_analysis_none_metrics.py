"""Task 26: AI analysis must not crash on channels with missing metrics (er=None etc.)."""
import asyncio

import pytest

from app.services import ai_analysis
from app.services.ai_analysis import NO_DATA, build_channel_prompt


def _channel(**over):
    base = {
        "channel_name": "Little data", "category": "news",
        "subscribers_count": 120, "avg_views": None, "er": None,
        "price": 50, "monthly_income": None, "age": None, "total_posts": None,
        "post_frequency": None, "avg_forwards": None, "avg_reactions": None,
        "telegram_link": "https://t.me/x", "description": None, "views_hidden": False,
    }
    base.update(over)
    return base


def test_prompt_channel_without_er():
    stats = [
        {"date": "2026-10-01", "subscribers": 100, "avg_views": None, "er": None},
        {"date": None, "subscribers": None, "avg_views": 10, "er": 2.5},
    ]
    posts = [{"text": None, "views": None, "reactions": None, "forwards": None, "media_type": None}]
    prompt = build_channel_prompt(_channel(), posts, stats)
    assert f"ER: {NO_DATA}" in prompt
    assert f"Перегляди: {NO_DATA}" in prompt
    assert f"er={NO_DATA}" in prompt
    assert "er=2.5%" in prompt
    assert "0.0%" not in prompt  # None is not silently turned into 0%


def test_prompt_all_metrics_missing():
    prompt = build_channel_prompt({"channel_name": "x"}, None, None)
    assert NO_DATA in prompt


def test_prompt_with_real_values_unchanged_format():
    prompt = build_channel_prompt(_channel(er=3.456, avg_views=1234, price=1500), [], [])
    assert "ER: 3.5%" in prompt and "1,234" in prompt and "1,500 USDT" in prompt


class _Resp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": '{"summary": "ok", "score": 30}'}}]}


class _Client:
    def __init__(self, *a, **k):
        self.sent = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        _Client.last_prompt = json["messages"][1]["content"]
        return _Resp()


@pytest.mark.parametrize("fn", ["channel", "bundle"])
def test_analyze_without_er_does_not_crash(monkeypatch, fn):
    monkeypatch.setattr(ai_analysis.settings, "groq_api_key", "test-key", raising=False)
    monkeypatch.setattr(ai_analysis.httpx, "AsyncClient", _Client)
    if fn == "channel":
        res = asyncio.run(ai_analysis.analyze_channel(
            _channel(), [], [{"date": "2026-10-01", "subscribers": 1, "avg_views": None, "er": None}]))
    else:
        res = asyncio.run(ai_analysis.analyze_bundle(
            {"name": "b", "price": 10, "channel_count": 1},
            [{"channel_name": "c", "subscribers_count": None, "er": None, "avg_views": None}]))
    assert res == {"summary": "ok", "score": 30}
    assert NO_DATA in _Client.last_prompt
