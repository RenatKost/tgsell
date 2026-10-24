"""«Шукаю канал» (/wanted): buyer requests, auto-checks, matching and notifications.

Lifecycle: pending -> approved / rejected (admin), or closed (buyer). A request is
"active" while pending, or approved and not yet expired (30 days from creation).
Buyer contacts are never exposed publicly — only the platform notifies the buyer.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel, ChannelStatus
from app.models.user import User
from app.models.wanted import WantedMatch, WantedRequest
from app.utils.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

MAX_ACTIVE_PER_USER = 3
TTL = timedelta(days=30)
COMMENT_MAX = 300
BUDGET_TOLERANCE = 1.2  # lot price <= budget_max * 1.2 still notifies the buyer
LANGUAGES = {"ua": "Україна", "ru": "RU", "en": "EN", "other": "Інше"}
SRC = "src=wanted"

# Mirrors src/components/Main/Calculator.jsx `options` (catalog categories) minus 18+.
CATEGORIES = [
    "Новини/ЗМІ", "Регіональні", "Пізнавальні", "Гумор", "Жіночі", "Лінгвістика", "Вульгарні",
    "Кулінарія", "Вакансія/Робота", "Криптовалюта", "Чоловіче", "Авто/Мото", "Політика",
    "Медицина", "Музика", "Подорожі/Країни", "Бізнес", "ІТ/Додатки", "Дизайн", "Авторські",
    "Історичні", "Спорт", "Товари/Магазини", "Кіно/Мультфільми", "Інвестиції/Акції", "Блогери",
    "Гороскопи", "Фотографії", "Ігри", "Тварини", "Цитати", "Аніме", "Нерухомість", "Релігія",
    "Нейромережі", "Щоу бізнес", "Мистецтво", "Інше",
]

# ── auto-checks ───────────────────────────────────────────────────────
_CONTACT_PATTERNS = [
    re.compile(r"(?<![\w.])@[a-zA-Z][\w]{3,}"),                      # @username
    re.compile(r"(?:t\.me|telegram\.me|telegram\.dog|wa\.me)\s*/", re.I),
    re.compile(r"https?://|www\.", re.I),
    re.compile(r"\b[\w-]+\.(?:com|net|org|ru|ua|me|io|xyz|info|site|online|shop|top|biz)\b", re.I),
    re.compile(r"\+?\d[\d\s().-]{8,}\d"),                              # phone-like
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                            # email
]
_ADULT = re.compile(r"18\s*\+|порн|porn|xxx|onlyfans|еротик|эротик|інтим|интим|nsfw|секс|sex", re.I)
_GAMBLING = re.compile(r"казино|casino|ставк|ставок|беттинг|бетинг|betting|букмекер|bookmaker|1xbet|слоти|слоты|slots|gambl", re.I)


def check_text(text: str | None) -> str | None:
    """Return a Ukrainian rejection reason, or None if the text is clean."""
    t = (text or "").strip()
    if not t:
        return None
    if _ADULT.search(t):
        return "Запити 18+ заборонені"
    if _GAMBLING.search(t):
        return "Запити на канали ставок/казино заборонені"
    if any(p.search(t) for p in _CONTACT_PATTERNS):
        return "Не вказуйте контакти, юзернейми, телефони чи посилання — покупця сповістить платформа"
    return None


def validate(data: dict) -> dict:
    """Normalize + validate a request body. Raises ValueError(ua message)."""
    cat = (data.get("category") or "").strip()
    if cat not in CATEGORIES:
        raise ValueError("Оберіть тематику зі списку")
    lang = (data.get("language") or "").strip()
    if lang not in LANGUAGES:
        raise ValueError("Оберіть мову/гео")

    def _num(key, cast):
        v = data.get(key)
        if v is None or v == "":
            return None
        try:
            v = cast(v)
        except (TypeError, ValueError):
            raise ValueError("Введіть число")
        if v < 0:
            raise ValueError("Значення не може бути від'ємним")
        return v

    smin, smax = _num("subs_min", int), _num("subs_max", int)
    bmin, bmax = _num("budget_min", float), _num("budget_max", float)
    if smin is not None and smax is not None and smin > smax:
        raise ValueError("Підписники «від» більше ніж «до»")
    if bmin is not None and bmax is not None and bmin > bmax:
        raise ValueError("Бюджет «від» більший ніж «до»")
    if bmax is None:
        raise ValueError("Вкажіть бюджет «до»")
    comment = (data.get("comment") or "").strip() or None
    if comment and len(comment) > COMMENT_MAX:
        raise ValueError(f"Коментар до {COMMENT_MAX} символів")
    reason = check_text(comment)
    if reason:
        raise ValueError(reason)
    return {"category": cat, "language": lang, "subs_min": smin, "subs_max": smax,
            "budget_min": bmin, "budget_max": bmax, "comment": comment}


def active_clause(now: datetime):
    return or_(WantedRequest.status == "pending",
               and_(WantedRequest.status == "approved", WantedRequest.expires_at > now))


def public_clause(now: datetime):
    return and_(WantedRequest.status == "approved", WantedRequest.expires_at > now)


def public_out(r: WantedRequest) -> dict:
    """Public card: no user / contact fields."""
    return {
        "id": r.id, "category": r.category, "subs_min": r.subs_min, "subs_max": r.subs_max,
        "budget_min": r.budget_min, "budget_max": r.budget_max, "language": r.language,
        "language_label": LANGUAGES.get(r.language, r.language), "comment": r.comment,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def owner_out(r: WantedRequest) -> dict:
    return public_out(r) | {
        "status": r.status, "rejection_reason": r.rejection_reason,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
    }


async def count_active(db: AsyncSession, user_id: int, now: datetime | None = None) -> int:
    now = now or utcnow_naive()
    return (await db.execute(select(func.count()).select_from(WantedRequest).where(
        WantedRequest.user_id == user_id, active_clause(now)))).scalar() or 0


async def create(db: AsyncSession, user: User, data: dict) -> WantedRequest:
    clean = validate(data)
    now = utcnow_naive()
    if await count_active(db, user.id, now) >= MAX_ACTIVE_PER_USER:
        raise ValueError(f"Максимум {MAX_ACTIVE_PER_USER} активні запити")
    row = WantedRequest(user_id=user.id, status="pending", expires_at=now + TTL, **clean)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    try:
        await notify_admin_new_request(row)
    except Exception as e:  # never fail the request on alert problems
        logger.warning("[WANTED] admin alert failed: %s", type(e).__name__)
    return row


def fmt_range(lo, hi, unit: str = "") -> str:
    def f(v):
        if v is None:
            return None
        v = float(v)
        s = f"{v:,.0f}" if v.is_integer() else f"{v:,.2f}"
        return s.replace(",", " ")
    a, b = f(lo), f(hi)
    if a and b:
        s = f"{a}–{b}"
    elif b:
        s = f"до {b}"
    elif a:
        s = f"від {a}"
    else:
        s = "будь-яка"
    return f"{s} {unit}".strip() if (a or b) else s


def summary(r: WantedRequest) -> str:
    return (f"{escape(r.category)} · {fmt_range(r.subs_min, r.subs_max, 'підп.')} · "
            f"{fmt_range(r.budget_min, r.budget_max, 'USDT')} · {LANGUAGES.get(r.language, r.language)}")


async def notify_admin_new_request(r: WantedRequest) -> bool:
    from app.services.alerts import send_admin_alert
    lines = [f"🔎 <b>Новий запит «Шукаю канал» #{r.id}</b> — на модерації", summary(r)]
    if r.comment:
        lines.append(f"💬 {escape(r.comment)}")
    lines.append("Адмінка → «Шукаю канал»")
    return bool(await send_admin_alert("\n".join(lines), alert_key=None))


def site_url(path: str) -> str:
    from app.config import settings
    base = settings.frontend_url.rstrip("/")
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}{SRC}"


def channel_matches(r: WantedRequest, ch: Channel) -> bool:
    if (ch.category or "") != r.category:
        return False
    subs = ch.subscribers_count or 0
    if r.subs_min is not None and subs < r.subs_min:
        return False
    if r.subs_max is not None and subs > r.subs_max:
        return False
    if r.budget_max is not None and (ch.price or 0) > r.budget_max * BUDGET_TOLERANCE:
        return False
    return True


async def _bot_send(chat_id: int, text: str) -> str:
    """'sent' | 'not_started' | 'failed' via @tgsell_alert_bot."""
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from app.config import settings
    from app.services.alerts import telegram_html_safe
    if not settings.bot_token_alerts:
        return "failed"
    bot = Bot(token=settings.bot_token_alerts)
    try:
        await bot.send_message(chat_id, telegram_html_safe(text), parse_mode=ParseMode.HTML,
                               disable_web_page_preview=True)
        return "sent"
    except Exception as e:
        from app.services.chat_bridge import is_unreachable_error
        logger.warning("[WANTED] send failed: %s", type(e).__name__)
        return "not_started" if is_unreachable_error(e) else "failed"
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass


def _reachable(u: User | None) -> bool:
    return bool(u and u.telegram_id and u.tg_bot_started_at and not u.tg_bot_unreachable_at
                and not getattr(u, "is_blocked", False))


async def notify_buyers_for_channel(db: AsyncSession, channel_id: int) -> int:
    """After a lot is approved: tell each matching buyer once. Never raises."""
    now = utcnow_naive()
    ch = await db.get(Channel, channel_id)
    if not ch or ch.status != ChannelStatus.approved:
        return 0
    reqs = (await db.execute(select(WantedRequest).where(
        public_clause(now), WantedRequest.category == ch.category,
        WantedRequest.user_id != ch.seller_id))).scalars().all()
    price = f"{ch.price:g}" if ch.price is not None else "—"
    subs = f"{ch.subscribers_count:,}".replace(",", " ") if ch.subscribers_count else "—"
    url = escape(site_url(f"/channel/{ch.id}"), quote=True)
    lot_line = f"• <a href=\"{url}\">{escape(ch.channel_name or f'#{ch.id}')}</a> — {subs} підп., {price} USDT"
    todo = [(r.id, r.user_id, summary(r)) for r in reqs if channel_matches(r, ch)]
    sent = 0
    for rid, uid, summ in todo:
        exists = (await db.execute(select(WantedMatch.id).where(
            WantedMatch.request_id == rid, WantedMatch.channel_id == channel_id).limit(1))).first()
        if exists:
            continue
        m = WantedMatch(request_id=rid, channel_id=channel_id)
        db.add(m)
        try:
            await db.commit()  # claim before sending: at most one message per (request, lot)
        except IntegrityError:
            await db.rollback()
            continue
        user = await db.get(User, uid)
        status = "not_started"
        if _reachable(user):
            text = f"🔎 <b>З'явився канал під ваш запит «Шукаю канал»</b>\n{summ}\n\n{lot_line}"
            status = await _bot_send(user.telegram_id, text)
        m.delivered = status == "sent"
        await db.commit()
        sent += int(status == "sent")
    return sent


# ── daily digest for sellers ─────────────────────────────────────────
DIGEST_TZ = ZoneInfo("Europe/Kiev")
DIGEST_HOUR = 10
DIGEST_CATCH_UP_HOURS = 6


def digest_due(now_utc: datetime) -> tuple[str, datetime] | None:
    local = now_utc.replace(tzinfo=timezone.utc).astimezone(DIGEST_TZ)
    d = local.date()
    due_local = datetime(d.year, d.month, d.day, DIGEST_HOUR, tzinfo=DIGEST_TZ)
    due_utc = due_local.astimezone(timezone.utc).replace(tzinfo=None)
    if not (due_utc <= now_utc < due_utc + timedelta(hours=DIGEST_CATCH_UP_HOURS)):
        return None
    return f"wanted_digest:{d.isoformat()}", due_utc


async def digest_requests(db: AsyncSession, due_utc: datetime) -> list[WantedRequest]:
    since = due_utc - timedelta(days=1)
    return list((await db.execute(select(WantedRequest).where(
        public_clause(due_utc), WantedRequest.moderated_at >= since, WantedRequest.moderated_at < due_utc,
    ).order_by(WantedRequest.moderated_at.desc()))).scalars().all())


def digest_text(reqs: list[WantedRequest]) -> str:
    lines = [f"🔎 <b>Нові запити «Шукаю канал» за добу: {len(reqs)}</b>", ""]
    for r in reqs[:10]:
        url = escape(site_url(f"/sell?wanted={r.id}"), quote=True)
        lines.append(f"• {summary(r)} — <a href=\"{url}\">У мене є такий канал</a>")
    if len(reqs) > 10:
        lines.append(f"…ще {len(reqs) - 10}")
    lines += ["", f"Усі запити: {escape(site_url('/wanted'))}"]
    return "\n".join(lines)


async def send_digest_once(now: datetime | None = None) -> int:
    """One tick. Claims the day key (shared with weekly report idempotency table) before sending."""
    from app.database import async_session
    from app.services.weekly_stats import claim_weekly_report, finish_weekly_report
    now = now or utcnow_naive()
    due = digest_due(now)
    if due is None:
        return 0
    key, due_utc = due
    async with async_session() as db:
        reqs = await digest_requests(db, due_utc)
        if not reqs:
            return 0  # nothing new — no digest at all
        if not await claim_weekly_report(db, key):
            return 0
        sellers = (await db.execute(select(User).where(
            User.id.in_(select(Channel.seller_id).distinct()),
            User.telegram_id.isnot(None), User.tg_bot_started_at.isnot(None),
            User.tg_bot_unreachable_at.is_(None), User.is_blocked.is_(False),
        ))).scalars().all()
        text = digest_text(reqs)
    sent = 0
    for u in sellers:
        if await _bot_send(u.telegram_id, text) == "sent":
            sent += 1
        await asyncio.sleep(0.05)
    async with async_session() as db:
        await finish_weekly_report(db, key, True)
    logger.info("[WANTED] digest %s: %s request(s), sent to %s seller(s)", key, len(reqs), sent)
    return sent


async def run_wanted_digest(interval_seconds: int = 300, initial_delay_sec: int = 300):
    await asyncio.sleep(initial_delay_sec)
    while True:
        try:
            await send_digest_once()
        except Exception as e:
            logger.error("[WANTED] digest loop error: %s", e)
        await asyncio.sleep(interval_seconds)


async def admin_stats(db: AsyncSession) -> dict:
    from app.models.deal import Deal
    now = utcnow_naive()
    by_status = dict((await db.execute(
        select(WantedRequest.status, func.count()).group_by(WantedRequest.status))).all())
    active = (await db.execute(select(func.count()).select_from(WantedRequest).where(public_clause(now)))).scalar() or 0
    lots_q = select(Channel.id).where(Channel.wanted_request_id.isnot(None))
    lots = (await db.execute(select(func.count()).select_from(lots_q.subquery()))).scalar() or 0
    deals = (await db.execute(select(func.count()).select_from(Deal).where(Deal.channel_id.in_(lots_q)))).scalar() or 0
    return {
        "requests_total": sum(by_status.values()),
        "pending": by_status.get("pending", 0), "approved": by_status.get("approved", 0),
        "rejected": by_status.get("rejected", 0), "closed": by_status.get("closed", 0),
        "active": active, "lots_from_button": lots, "deals_from_lots": deals,
    }
