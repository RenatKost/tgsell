"""AI-powered channel analysis using Google Gemini API (free tier)."""
import json
import logging
from datetime import datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


async def analyze_channel(channel_data: dict, posts_data: list[dict], stats_data: list[dict]) -> dict | None:
    """Send channel data to Gemini for deep analysis. Returns structured JSON."""
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — skipping AI analysis")
        return None

    # Build context for the AI
    channel_info = (
        f"Назва: {channel_data.get('channel_name', '?')}\n"
        f"Категорія: {channel_data.get('category', '?')}\n"
        f"Підписників: {channel_data.get('subscribers_count', 0):,}\n"
        f"Середні перегляди: {channel_data.get('avg_views', 0):,}\n"
        f"ER: {channel_data.get('er', 0):.2f}%\n"
        f"Ціна: {channel_data.get('price', 0):,} USDT\n"
        f"Прибуток/міс: {channel_data.get('monthly_income', 0) or 0:,} USDT\n"
        f"Вік: {channel_data.get('age', '?')}\n"
        f"Постів загалом: {channel_data.get('total_posts', 0)}\n"
        f"Частота: {channel_data.get('post_frequency', 0)} пост/день\n"
        f"Пересилань/пост: {channel_data.get('avg_forwards', 0)}\n"
        f"Реакцій/пост: {channel_data.get('avg_reactions', 0)}\n"
        f"Посилання: {channel_data.get('telegram_link', '')}\n"
    )

    # Include last 15 posts for content analysis
    posts_text = ""
    for i, p in enumerate(posts_data[:15], 1):
        text_preview = (p.get("text") or "")[:200]
        posts_text += (
            f"\nПост {i}: {text_preview}\n"
            f"  Перегляди: {p.get('views', 0)} | Реакції: {p.get('reactions', 0)} | "
            f"Пересилань: {p.get('forwards', 0)} | Медіа: {p.get('media_type', 'немає')}\n"
        )

    # Stats trend
    stats_text = ""
    if stats_data:
        for s in stats_data[-10:]:
            stats_text += f"  {s.get('date', '?')}: subs={s.get('subscribers', 0)}, views={s.get('avg_views', 0)}, er={s.get('er', 0):.2f}%\n"

    prompt = f"""Ти — експерт-аналітик Telegram-каналів для інвесторів. Проаналізуй канал та дай розгорнуту аналітику для потенційного покупця.

ДАНІ КАНАЛУ:
{channel_info}

ОСТАННІ ПУБЛІКАЦІЇ:
{posts_text if posts_text else "Немає даних про пости"}

ДИНАМІКА СТАТИСТИКИ (останні записи):
{stats_text if stats_text else "Немає історичних даних"}

Дай відповідь СТРОГО у форматі JSON (без markdown, без ```):
{{
  "summary": "Короткий висновок про канал (2-3 речення)",
  "audience_quality": "Оцінка якості аудиторії та залученості (2-3 речення)",
  "growth_trend": "Аналіз тренду росту/падіння підписників та переглядів",
  "content_analysis": "Аналіз контенту: тематика, якість, унікальність",
  "monetization": [
    "Спосіб монетизації 1",
    "Спосіб монетизації 2",
    "Спосіб монетизації 3"
  ],
  "risks": [
    "Ризик 1",
    "Ризик 2"
  ],
  "opportunities": [
    "Можливість 1",
    "Можливість 2"
  ],
  "fair_price_estimate": "Приблизна справедлива ціна каналу та обґрунтування",
  "verdict": "buy" | "hold" | "avoid",
  "verdict_reason": "Пояснення вердикту (1-2 речення)",
  "score": число від 1 до 100
}}

Відповідай ТІЛЬКИ валідним JSON. Мова — українська."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GEMINI_URL,
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 2048,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

            # Extract text from Gemini response
            text = data["candidates"][0]["content"]["parts"][0]["text"]

            # Clean up potential markdown fences
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            result = json.loads(text)
            logger.info(f"AI analysis completed for channel '{channel_data.get('channel_name')}'")
            return result

    except httpx.HTTPStatusError as e:
        logger.error(f"Gemini API error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return None
