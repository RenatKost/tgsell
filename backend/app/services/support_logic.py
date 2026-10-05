"""Pure helpers for support bot: urgent keywords, auto-reply / alert dedup."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# Case-insensitive stems (UA / RU / EN) for urgent support tickets.
URGENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"виплат",
        r"выплат",
        r"payout",
        r"спір",
        r"спор",
        r"dispute",
        r"фрод",
        r"шахрай",
        r"мошен",
        r"fraud",
        r"scam",
        r"escrow",
        r"ескроу",
        r"эскроу",
        r"повернен",
        r"возврат",
        r"refund",
    )
)

AUTO_REPLY_TEXT = (
    "Дякуємо! Ваше звернення прийнято, відповімо найближчим часом."
)

WELCOME_TEXT = (
    "👋 Вітаємо в підтримці TgSell!\n\n"
    "Напишіть ваше питання — ми відповімо якнайшвидше.\n"
    "Працюємо з питаннями щодо угод, виплат, акаунту та модерації."
)

AUTO_REPLY_COOLDOWN = timedelta(minutes=30)
URGENT_ALERT_COOLDOWN = timedelta(minutes=30)
MAX_SUPPORT_TEXT_LEN = 4000
EXCERPT_LEN = 300


def is_urgent_text(text: str | None) -> bool:
    """True if text matches any urgent keyword stem (case-insensitive)."""
    if not text:
        return False
    return any(p.search(text) for p in URGENT_PATTERNS)


def should_send_auto_reply(last_auto_reply_at: datetime | None, now: datetime | None = None) -> bool:
    """First message (None) or cooldown elapsed → send auto-reply."""
    if last_auto_reply_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    last = last_auto_reply_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - last) >= AUTO_REPLY_COOLDOWN


def should_send_urgent_alert(last_alert_at: datetime | None, now: datetime | None = None) -> bool:
    """At most one urgent alert per user per 30 minutes."""
    if last_alert_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    last = last_alert_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - last) >= URGENT_ALERT_COOLDOWN


def message_text_from_update(text: str | None, caption: str | None, content_type: str | None) -> str:
    """Normalize inbound message text; for media store type + caption."""
    if text:
        return text
    cap = (caption or "").strip()
    kind = (content_type or "media").strip() or "media"
    if cap:
        return f"[{kind}] {cap}"
    return f"[{kind}]"


def excerpt(text: str | None, limit: int = EXCERPT_LEN) -> str:
    if not text:
        return ""
    t = text.strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def build_urgent_alert_html(
    *,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    text: str | None,
    message_id: int,
) -> str:
    import html

    uname = f"@{html.escape(username)}" if username else "(без username)"
    name = html.escape(first_name or "")
    body = html.escape(excerpt(text))
    return (
        "🚨 <b>Підтримка — термінове звернення</b>\n\n"
        f"Користувач: <a href=\"tg://user?id={telegram_user_id}\">{name or telegram_user_id}</a> "
        f"{uname}\n"
        f"ID: <code>{telegram_user_id}</code>\n"
        f"Повідомлення #{message_id}:\n"
        f"<i>{body}</i>"
    )
