"""AI-powered channel analysis using Groq API (free tier, Llama 3.3 70B)."""
import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


async def analyze_channel(channel_data: dict, posts_data: list[dict], stats_data: list[dict]) -> dict | None:
    """Send full channel data to Groq/Llama for deep monetization analysis."""
    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY not set — skipping AI analysis")
        return None

    # ── Build rich context ──
    views_hidden = channel_data.get('views_hidden', False)
    channel_info = (
        f"Назва: {channel_data.get('channel_name', '?')}\n"
        f"Категорія: {channel_data.get('category', '?')}\n"
        f"Підписників: {channel_data.get('subscribers_count', 0):,}\n"
        f"Середні перегляди: {'⚠️ ВИМКНЕНІ АДМІНОМ (лічильник переглядів прихований)' if views_hidden else f'{channel_data.get('avg_views', 0):,}'}\n"
        f"ER (engagement rate): {channel_data.get('er', 0):.2f}%\n"
        f"Ціна продажу: {channel_data.get('price', 0):,} USDT\n"
        f"Поточний прибуток/міс: {channel_data.get('monthly_income', 0) or 0:,} USDT\n"
        f"Вік каналу: {channel_data.get('age', '?')}\n"
        f"Постів загалом: {channel_data.get('total_posts', 0)}\n"
        f"Частота публікацій: {channel_data.get('post_frequency', 0)} пост/день\n"
        f"Сер. пересилань/пост: {channel_data.get('avg_forwards', 0)}\n"
        f"Сер. реакцій/пост: {channel_data.get('avg_reactions', 0)}\n"
        f"Telegram: {channel_data.get('telegram_link', '')}\n"
        f"Опис власника: {channel_data.get('description', '') or 'Немає'}\n"
    )

    # Top 20 posts for content analysis (trim text to save tokens)
    posts_text = ""
    for i, p in enumerate(posts_data[:20], 1):
        text_preview = (p.get("text") or "")[:150]
        posts_text += (
            f"#{i}: {text_preview}\n"
            f"  👁{p.get('views', 0)} ❤️{p.get('reactions', 0)} 🔄{p.get('forwards', 0)} 📎{p.get('media_type', 'txt')}\n"
        )

    # Last 14 stats entries (enough to see trend)
    stats_text = ""
    for s in (stats_data or [])[-14:]:
        stats_text += (
            f"  {s.get('date', '?')}: subs={s.get('subscribers', 0)}, "
            f"views={s.get('avg_views', 0)}, er={s.get('er', 0):.1f}%\n"
        )

    prompt = f"""Ти — топовий аналітик Telegram-каналів з досвідом оцінки та монетизації медіа-активів. Проведи ГЛИБОКИЙ аналіз каналу для потенційного покупця.

══════ ДАНІ КАНАЛУ ══════
{channel_info}

══════ ПУБЛІКАЦІЇ (останні 20) ══════
{posts_text if posts_text else "Немає публікацій"}

══════ СТАТИСТИКА (останні 14 днів) ══════
{stats_text if stats_text else "Немає історичних даних"}

══════ ЗАВДАННЯ ══════

Проаналізуй ВСЕ: контент, аудиторію, динаміку, тренди, тематику, потенціал.

Запропонуй РІВНО 5 конкретних способів монетизації цього каналу з РЕАЛЬНИМИ цифрами доходу (в USDT на місяць), враховуючи:
- Кількість підписників та охват
- Тематику та аудиторію
- Середній CPM для цієї ніші
- Ринкові ставки на рекламу в Telegram

Для кожного способу вкажи: назву, опис як це працює, очікуваний дохід (від-до), і чому саме цей канал для цього підходить.

Відповідь СТРОГО у форматі JSON (без markdown, без ```, без коментарів):
{{
  "summary": "Загальний висновок про канал та його інвестиційну привабливість (3-4 речення)",
  "audience_quality": "Детальна оцінка аудиторії: жива/мертва, залученість, боти, демографія (2-3 речення)",
  "growth_trend": "Аналіз динаміки: ріст/стагнація/падіння підписників та переглядів з цифрами",
  "content_analysis": "Оцінка контенту: тематика, унікальність, якість, регулярність (2-3 речення)",
  "content_topics": ["Тема1", "Тема2", "Тема3", "Тема4", "Тема5"],
  "sentiment_positive": 63,
  "sentiment_neutral": 30,
  "sentiment_negative": 7,
  "monetization": [
    {{
      "method": "Назва способу",
      "description": "Як це працює для цього каналу",
      "income_min": 100,
      "income_max": 300,
      "reasoning": "Чому підходить і як порахували"
    }},
    {{
      "method": "Назва способу 2",
      "description": "Опис",
      "income_min": 50,
      "income_max": 150,
      "reasoning": "Обґрунтування"
    }}
  ],
  "total_potential_income_min": 500,
  "total_potential_income_max": 1500,
  "risks": [
    "Ризик 1 з поясненням",
    "Ризик 2 з поясненням"
  ],
  "opportunities": [
    "Можливість 1 з поясненням",
    "Можливість 2 з поясненням"
  ],
  "fair_price_estimate": "Приблизна справедлива ціна (число USDT) з обґрунтуванням",
  "roi_months": "Через скільки місяців окупиться інвестиція при максимальній монетизації",
  "verdict": "buy",
  "verdict_reason": "Чому купувати/чекати/уникати (2-3 речення з аргументами)",
  "score": 75
}}

ВАЖЛИВО:
- "verdict" — одне з: "buy", "hold", "avoid"
- "score" — число від 1 до 100
- "income_min" та "income_max" — числа в USDT
- "content_topics" — рівно 5 ключових тем/слів контенту каналу
- "sentiment_positive", "sentiment_neutral", "sentiment_negative" — відсотки сентименту постів (сума = 100)
- Рівно 5 способів монетизації
- Мова відповіді — українська
- Тільки валідний JSON"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ти — експерт-аналітик Telegram-каналів. Відповідай ТІЛЬКИ валідним JSON без markdown-обгортки.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4096,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            text = data["choices"][0]["message"]["content"]

            # Clean up potential markdown fences
            text = text.strip()
            if text.startswith("```"):
                first_newline = text.find("\n")
                text = text[first_newline + 1:] if first_newline != -1 else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            result = json.loads(text)
            logger.info(f"AI analysis completed for channel '{channel_data.get('channel_name')}'")
            return result

    except httpx.HTTPStatusError as e:
        body = e.response.text[:300]
        logger.error(f"Groq API error {e.response.status_code}: {body}")
        if e.response.status_code == 429:
            return {"error": "rate_limit", "detail": "API ліміт вичерпано. Спробуйте через хвилину."}
        return {"error": "api_error", "detail": f"Groq API помилка {e.response.status_code}"}
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Groq response as JSON: {e}")
        return {"error": "parse_error", "detail": "AI повернув невалідну відповідь. Спробуйте ще раз."}
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return None
