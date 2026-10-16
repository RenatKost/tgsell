"""AI-powered channel analysis using Groq API (free tier, GPT-OSS 120B)."""
import json
import logging

import httpx

from app.config import settings
from app.services.alerts import alert_service_down

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# llama-3.3-70b-versatile was decommissioned by Groq; gpt-oss-120b is the
# current closest-tier general chat model on the account (checked via
# GET /openai/v1/models on 2026-08-28).
MODEL = "openai/gpt-oss-120b"


NO_DATA = "мало даних"


UNAVAILABLE_STATUS = "unavailable"
UNAVAILABLE_DETAIL = "аналіз тимчасово недоступний"

# Task 28: Groq sometimes returns truncated/invalid JSON. Retry + repair.
GROQ_MAX_ATTEMPTS = 3  # 1 call + 2 retries
CHANNEL_MAX_TOKENS = 6144
BUNDLE_MAX_TOKENS = 4096
# Frontend waits 55 s; all attempts together must fit inside that.
TOTAL_BUDGET_SEC = 50.0
SYSTEM_PROMPT = "Ти — експерт-аналітик Telegram-каналів. Відповідай ТІЛЬКИ валідним JSON без markdown-обгортки."


def unavailable_result(reason: str = "unavailable") -> dict:
    """200-payload shown by the UI as «аналіз тимчасово недоступний». Never cached."""
    return {"status": UNAVAILABLE_STATUS, "error": reason, "detail": UNAVAILABLE_DETAIL}


def is_unavailable(result) -> bool:
    return result is None or (isinstance(result, dict) and bool(result.get("error")))


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        nl = text.find("\n")
        text = text[nl + 1:] if nl != -1 else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _close_truncated(text: str) -> str:
    """Close an unterminated string / open brackets of a truncated JSON object."""
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    out = text
    if in_str:
        if esc:
            out = out[:-1]
        out += '"'
    out = out.rstrip()
    # drop a dangling separator / key without value
    import re as _re
    out = _re.sub(r'(,\s*"[^"]*"\s*:?\s*|,\s*|:\s*)$', "", out)
    if out.endswith(":"):
        out = out[:-1]
    return out + "".join(reversed(stack))


def repair_json(text: str):
    """Best-effort parse of model output. Returns dict or raises json.JSONDecodeError."""
    import re as _re
    text = _strip_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("no JSON object", text, 0)
    body = text[start:]
    end = body.rfind("}")
    candidates = []
    if end != -1:
        candidates.append(body[: end + 1])
    candidates.append(body)
    for cand in candidates:
        cleaned = _re.sub(r",\s*([}\]])", r"\1", cand)  # trailing commas
        for variant in (cleaned, _close_truncated(cleaned)):
            try:
                result = json.loads(variant)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("unrepairable JSON", text, 0)


async def _groq_json(prompt: str, *, temperature: float, max_tokens: int, timeout: float, label: str) -> dict:
    """Call Groq with retries on invalid/truncated JSON, timeouts and 5xx.

    Returns parsed dict, or unavailable_result(reason) after all attempts.
    """
    import time as _time
    reason = "unavailable"
    deadline = _time.monotonic() + TOTAL_BUDGET_SEC
    for attempt in range(1, GROQ_MAX_ATTEMPTS + 1):
        remaining = deadline - _time.monotonic()
        if remaining < 5:
            reason = reason if reason != "unavailable" else "timeout"
            break
        try:
            async with httpx.AsyncClient(timeout=min(timeout, remaining)) as client:
                resp = await client.post(
                    GROQ_URL,
                    headers={
                        "Authorization": f"Bearer {settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": MODEL,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
            try:
                result = repair_json(text)
                logger.info("%s: AI analysis ok (attempt %s)", label, attempt)
                return result
            except json.JSONDecodeError as e:
                reason = "parse_error"
                logger.warning(
                    "%s: invalid JSON from Groq (attempt %s/%s, finish=%s, len=%s): %s",
                    label, attempt, GROQ_MAX_ATTEMPTS, choice.get("finish_reason"), len(text), e,
                )
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            logger.error("%s: Groq API error %s: %s", label, code, e.response.text[:300])
            if code in (401, 403):
                await alert_service_down("Groq AI Analysis", f"{code}")
                return unavailable_result("api_error")
            if code == 429:
                return unavailable_result("rate_limit")
            reason = "api_error"  # 400 (json validation) / 5xx → retry
        except httpx.TimeoutException:
            reason = "timeout"
            logger.warning("%s: Groq timeout (attempt %s/%s)", label, attempt, GROQ_MAX_ATTEMPTS)
        except Exception as e:  # noqa: BLE001
            reason = "unexpected"
            logger.error("%s: AI analysis failed: %s", label, e)
    return unavailable_result(reason)


def _num(value):
    """Return a float for a usable metric, or None for None/garbage/NaN."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _fmt_int(value, suffix: str = "") -> str:
    f = _num(value)
    return f"{int(round(f)):,}{suffix}" if f is not None else NO_DATA


def _fmt_float(value, digits: int = 1, suffix: str = "") -> str:
    f = _num(value)
    return f"{f:.{digits}f}{suffix}" if f is not None else NO_DATA


def build_channel_prompt(
    channel_data: dict,
    posts_data: list[dict] | None,
    stats_data: list[dict] | None,
    is_closed: bool = False,
) -> str:
    """Build the Groq prompt. Missing metrics (None) render as «мало даних»
    instead of crashing on format specs or pretending to be 0."""
    channel_data = channel_data or {}
    views_hidden = channel_data.get('views_hidden', False)
    channel_info = (
        f"Назва: {channel_data.get('channel_name', '?')}\n"
        f"Категорія: {channel_data.get('category', '?')}\n"
        f"Підписників: {_fmt_int(channel_data.get('subscribers_count'))}\n"
        f"Середні перегляди: {'⚠️ ВИМКНЕНІ АДМІНОМ (лічильник переглядів прихований)' if views_hidden else _fmt_int(channel_data.get('avg_views'))}\n"
        f"ER (engagement rate): {_fmt_float(channel_data.get('er'), 2, '%')}\n"
        f"Ціна продажу: {_fmt_int(channel_data.get('price'), ' USDT')}\n"
        f"Поточний прибуток/міс: {_fmt_int(channel_data.get('monthly_income') or 0, ' USDT')}\n"
        f"Вік каналу: {channel_data.get('age', '?')}\n"
        f"Постів загалом: {_fmt_int(channel_data.get('total_posts'))}\n"
        f"Частота публікацій: {_fmt_float(channel_data.get('post_frequency'), 1, ' пост/день')}\n"
        f"Сер. пересилань/пост: {_fmt_float(channel_data.get('avg_forwards'))}\n"
        f"Сер. реакцій/пост: {_fmt_float(channel_data.get('avg_reactions'))}\n"
        f"Telegram: {channel_data.get('telegram_link', '')}\n"
        f"Опис власника: {channel_data.get('description', '') or 'Немає'}\n"
    )

    # Top 20 posts for content analysis (trim text to save tokens)
    posts_text = ""
    for i, p in enumerate((posts_data or [])[:20], 1):
        text_preview = (p.get("text") or "")[:150]
        posts_text += (
            f"#{i}: {text_preview}\n"
            f"  👁{_fmt_int(p.get('views'))} ❤️{_fmt_int(p.get('reactions'))} 🔄{_fmt_int(p.get('forwards'))} 📎{p.get('media_type') or 'txt'}\n"
        )

    # Last 14 stats entries (enough to see trend)
    stats_text = ""
    for s in (stats_data or [])[-14:]:
        stats_text += (
            f"  {s.get('date') or '?'}: subs={_fmt_int(s.get('subscribers'))}, "
            f"views={_fmt_int(s.get('avg_views'))}, er={_fmt_float(s.get('er'), 1, '%')}\n"
        )

    closed_notice = (
        "\n⚠️ ЦЕ ЗАКРИТИЙ КАНАЛ (вступ за заявкою). Дані підписників/переглядів/ER "
        "надані продавцем вручну і НЕ перевірені автоматично ботом — став до них з "
        "обережністю. Постів і історії статистики немає (бот не має доступу).\n"
        if is_closed else ""
    )

    prompt = f"""Ти — аналітик покупки Telegram-каналів. Дай КОНКРЕТНИЙ аналіз без загальних фраз.
{closed_notice}
КАНАЛ: {channel_data.get('channel_name')} | {channel_data.get('category')} | {_fmt_int(channel_data.get('subscribers_count'))} підп.
Перегляди: {'ПРИХОВАНІ' if views_hidden else _fmt_int(channel_data.get('avg_views'))} | ER: {_fmt_float(channel_data.get('er'), 1, '%')} | Ціна: {_fmt_int(channel_data.get('price'), ' USDT')}
Дохід/міс: {_fmt_int(channel_data.get('monthly_income') or 0, ' USDT')} | Вік: {channel_data.get('age', '?')} | Пости/день: {_fmt_float(channel_data.get('post_frequency'))}
Forwards/пост: {_fmt_float(channel_data.get('avg_forwards'))} | Реакції/пост: {_fmt_float(channel_data.get('avg_reactions'))}

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
- Якщо канал закритий (вказано вище), обов'язково познач growth_trend і content_analysis як "недостатньо даних для оцінки" — не вигадуй конкретику, якщо ОСТАННІ 20 ПОСТІВ/СТАТИСТИКА порожні
- Якщо метрика позначена «мало даних» — не вигадуй її значення, у відповідному полі прямо напиши «мало даних»
- Тільки валідний JSON"""
    return prompt


async def analyze_channel(
    channel_data: dict,
    posts_data: list[dict],
    stats_data: list[dict],
    is_closed: bool = False,
) -> dict | None:
    """Send full channel data to Groq/Llama for deep monetization analysis.

    is_closed marks a channel that requires an approved join request — the
    bot cannot read its posts/history, so subscriber/view/ER numbers here are
    self-reported by the seller and stats_data/posts_data will be empty.
    """
    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY not set — skipping AI analysis")
        return unavailable_result("not_configured")

    prompt = build_channel_prompt(channel_data, posts_data, stats_data, is_closed)
    return await _groq_json(
        prompt, temperature=0.7, max_tokens=CHANNEL_MAX_TOKENS, timeout=50.0,
        label=f"channel '{channel_data.get('channel_name')}'",
    )


async def analyze_bundle(bundle_data: dict, channels_data: list[dict]) -> dict | None:
    """Analyze a bundle of Telegram channels for investment potential."""
    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY not set — skipping bundle AI analysis")
        return unavailable_result("not_configured")

    try:
        # Convert to native types to avoid Decimal formatting errors
        price = float(bundle_data.get('price') or 0)
        monthly_income = float(bundle_data.get('monthly_income') or 0)
        total_subs = int(bundle_data.get('total_subscribers') or 0)
        avg_er = float(bundle_data.get('avg_er') or 0)
        channel_count = int(bundle_data.get('channel_count') or 0)

        channels_text = ""
        for i, ch in enumerate(channels_data, 1):
            subs = int(ch.get('subscribers_count') or 0)
            channels_text += (
                f"{i}. {ch.get('channel_name', '?')} — "
                f"{subs:,} підп., ER {_fmt_float(ch.get('er'), 1, '%')}, "
                f"перегляди: {_fmt_int(ch.get('avg_views'))}\n"
            )

        prompt = f"""Ти — аналітик покупки Telegram-сіток. Дай КОНКРЕТНИЙ аналіз без води.

СІТКА: {bundle_data.get('name')} | {channel_count} каналів | {bundle_data.get('category', '?')}
Ціна: {price:,.0f} USDT | Дохід/міс: {monthly_income:,.0f} USDT
Всього підписників: {total_subs:,} | Середній ER: {avg_er:.1f}%

КАНАЛИ:
{channels_text}
Відповідай ТІЛЬКИ JSON (без коментарів, без markdown):
{{
  "summary": "2 речення: що це за сітка і чому варто/не варто купувати. З конкретними числами.",
  "audience_quality": "Одне речення: сумарне охоплення та якість аудиторії на основі ER. Якщо ER<5% — вкажи.",
  "synergy": "Одне речення: чи доповнюють канали одне одного за тематикою та аудиторією.",
  "total_potential_income_min": 400,
  "total_potential_income_max": 1200,
  "risks": ["Конкретний ризик 1 з числами або фактами", "Конкретний ризик 2", "Конкретний ризик 3"],
  "opportunities": ["Конкретна можливість 1: крос-просування", "Конкретна можливість 2: пакетна реклама", "Конкретна можливість 3"],
  "fair_price_estimate": "X USDT. ROI: ціна / (місячний дохід + потенційна монетизація) = Y місяців.",
  "roi_months": 14,
  "verdict": "buy",
  "verdict_reason": "2 речення. Конкретні аргументи: числа, ER, ROI.",
  "score": 70
}}
ПРАВИЛА: verdict "buy" якщо score>=65 і ROI<=18міс, "avoid" якщо score<40, інакше "hold". Тільки валідний JSON."""

    except Exception as e:  # noqa: BLE001 — prompt building
        logger.error(f"Bundle AI prompt failed: {e}")
        return unavailable_result("unexpected")
    return await _groq_json(
        prompt, temperature=0.5, max_tokens=BUNDLE_MAX_TOKENS, timeout=40.0,
        label=f"bundle '{bundle_data.get('name')}'",
    )
