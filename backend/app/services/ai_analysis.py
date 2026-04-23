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

    prompt = f"""Ти — аналітик покупки Telegram-каналів. Дай КОНКРЕТНИЙ аналіз без загальних фраз.

КАНАЛ: {channel_data.get('channel_name')} | {channel_data.get('category')} | {channel_data.get('subscribers_count', 0):,} підп.
Перегляди: {'ПРИХОВАНІ' if views_hidden else f"{channel_data.get('avg_views', 0):,}"} | ER: {channel_data.get('er', 0):.1f}% | Ціна: {channel_data.get('price', 0):,} USDT
Дохід/міс: {channel_data.get('monthly_income', 0) or 0:,} USDT | Вік: {channel_data.get('age', '?')} | Пости/день: {channel_data.get('post_frequency', 0):.1f}
Forwards/пост: {channel_data.get('avg_forwards', 0)} | Реакції/пост: {channel_data.get('avg_reactions', 0)}

ОСТАННІ 20 ПОСТІВ:
{posts_text if posts_text else "Немає постів"}

СТАТИСТИКА (останні 14 днів):
{stats_text if stats_text else "Немає даних"}

Відповідай ТІЛЬКИ JSON (без коментарів, без markdown):
{{
  "summary": "2 речення: що це за канал і чому варто/не варто купувати. Конкретно.",
  "audience_quality": "Одне речення: відсоток живої аудиторії на основі ER та переглядів. Якщо ER<5% — назви це.",
  "growth_trend": "Одне речення з конкретними числами: динаміка підписників та переглядів за 14 днів.",
  "content_analysis": "Одне речення: тематика постів, їхня якість, чи є реклама.",
  "content_topics": ["Тема1", "Тема2", "Тема3", "Тема4", "Тема5"],
  "sentiment_positive": 60,
  "sentiment_neutral": 30,
  "sentiment_negative": 10,
  "monetization": [
    {{"method": "Пряма реклама", "description": "Конкретна ставка за пост для цієї ніші та охвату", "income_min": 100, "income_max": 300, "reasoning": "CPM для ніші × охват"}},
    {{"method": "Спонсорський контент", "description": "Огляди продуктів ніші", "income_min": 50, "income_max": 150, "reasoning": "Обґрунтування цифр"}},
    {{"method": "Партнерські програми", "description": "Конкретні партнерки для цієї тематики", "income_min": 30, "income_max": 100, "reasoning": "Обґрунтування"}},
    {{"method": "Платний канал/бот", "description": "Конкретна пропозиція для цієї аудиторії", "income_min": 20, "income_max": 80, "reasoning": "Обґрунтування"}},
    {{"method": "Продаж товарів/послуг", "description": "Що конкретно підходить для цієї ніші", "income_min": 50, "income_max": 200, "reasoning": "Обґрунтування"}}
  ],
  "total_potential_income_min": 250,
  "total_potential_income_max": 830,
  "risks": ["Конкретний ризик 1 з числами", "Конкретний ризик 2 з числами"],
  "opportunities": ["Конкретна можливість 1 з числами", "Конкретна можливість 2 з числами"],
  "fair_price_estimate": "X USDT. Обґрунтування: 12-18 місяців окупності при поточному доході Y USDT/міс.",
  "roi_months": 14,
  "verdict": "buy",
  "verdict_reason": "2 речення чому. Конкретні аргументи з цифрами.",
  "score": 72
}}

ПРАВИЛА:
- verdict: "buy" якщо score>=65 і ROI<=18міс, "avoid" якщо score<40 або явні боти/накрутки, інакше "hold"
- income_min/max — реалістичні числа USDT для ЦЬОГО каналу, не загальні
- Якщо views_hidden=true, зниж score на 10-15 балів і вкажи це в ризиках
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


async def analyze_bundle(bundle_data: dict, channels_data: list[dict]) -> dict | None:
    """Analyze a bundle of Telegram channels for investment potential."""
    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY not set — skipping bundle AI analysis")
        return None

    bundle_info = (
        f"Назва сітки: {bundle_data.get('name', '?')}\n"
        f"Кількість каналів: {bundle_data.get('channel_count', 0)}\n"
        f"Ціна: {bundle_data.get('price', 0)} USDT\n"
        f"Категорія: {bundle_data.get('category', '?')}\n"
        f"Місячний дохід: {bundle_data.get('monthly_income', 0) or 0} USDT\n"
        f"Всього підписників: {bundle_data.get('total_subscribers', 0):,}\n"
        f"Середній ER: {bundle_data.get('avg_er', 0):.2f}%\n"
        f"Опис: {bundle_data.get('description', '') or 'Немає'}\n"
    )

    channels_text = ""
    for i, ch in enumerate(channels_data, 1):
        channels_text += (
            f"{i}. {ch.get('channel_name', '?')} — "
            f"{ch.get('subscribers_count', 0):,} підп., "
            f"ER {ch.get('er') or 0:.1f}%, "
            f"перегляди: {ch.get('avg_views') or 0:,}\n"
        )

    prompt = f"""Ти — аналітик покупки Telegram-сіток. Дай КОНКРЕТНИЙ аналіз без води.

СІТКА: {bundle_data.get('name')} | {bundle_data.get('channel_count')} каналів | {bundle_data.get('category', '?')}
Ціна: {bundle_data.get('price', 0):,} USDT | Дохід/міс: {bundle_data.get('monthly_income', 0) or 0:,} USDT
Всього підписників: {bundle_data.get('total_subscribers', 0):,} | Середній ER: {bundle_data.get('avg_er', 0):.1f}%

КАНАЛИ:
{channels_text}

Відповідай ТІЛЬКИ JSON (без коментарів, без markdown):
{{
  "summary": "2 речення: що це за сітка і чому варто/не варто купувати. З конкретними числами.",
  "audience_quality": "Одне речення: сумарне охоплення та якість аудиторії на основі ER. Якщо ER<5% — вкажи.",
  "synergy": "Одне речення: чи доповнюють канали одне одного за тематикою та аудиторією.",
  "total_potential_income_min": 400,
  "total_potential_income_max": 1200,
  "risks": [
    "Конкретний ризик 1 з числами або фактами",
    "Конкретний ризик 2",
    "Конкретний ризик 3"
  ],
  "opportunities": [
    "Конкретна можливість 1: крос-просування між каналами збільшить охоплення на X%",
    "Конкретна можливість 2: пакетна реклама для рекламодавців",
    "Конкретна можливість 3"
  ],
  "fair_price_estimate": "X USDT. ROI: ціна / (місячний дохід + потенційна монетизація) = Y місяців.",
  "roi_months": 14,
  "verdict": "buy",
  "verdict_reason": "2 речення. Конкретні аргументи: числа, ER, ROI.",
  "score": 70
}}

ПРАВИЛА:
- verdict: "buy" якщо score>=65 і ROI<=18міс, "avoid" якщо score<40, інакше "hold"
- total_potential_income_min/max — реалістичні USDT на місяць для ЦІЄЇ сітки
- roi_months — число (місяців)
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
                    "max_tokens": 2048,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            if text.startswith("```"):
                first_newline = text.find("\n")
                text = text[first_newline + 1:] if first_newline != -1 else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            result = json.loads(text)
            logger.info(f"Bundle AI analysis completed for '{bundle_data.get('name')}'")
            return result
    except httpx.HTTPStatusError as e:
        body = e.response.text[:300]
        logger.error(f"Groq API error {e.response.status_code}: {body}")
        if e.response.status_code == 429:
            return {"error": "rate_limit", "detail": "API ліміт вичерпано. Спробуйте через хвилину."}
        return {"error": "api_error", "detail": f"Groq API помилка {e.response.status_code}"}
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Groq bundle response as JSON: {e}")
        return {"error": "parse_error", "detail": "AI повернув невалідну відповідь. Спробуйте ще раз."}
    except Exception as e:
        logger.error(f"Bundle AI analysis failed: {e}")
        return None
