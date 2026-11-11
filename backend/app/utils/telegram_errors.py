"""Classify Telegram Bot API errors for seller notifications."""
from __future__ import annotations

_PERMANENT_TYPES = frozenset({"TelegramForbiddenError", "TelegramNotFound"})

# Substrings from Telegram 403/400 payloads that will never succeed on retry.
_PERMANENT_SNIPPETS = (
    "bot was blocked",
    "bot blocked by the user",
    "user is deactivated",
    "chat not found",
    "chat_not_found",
    "bot can't initiate conversation",
    "bot can't initiate",
    "have no rights to send a message",
    "user not found",
    "peer_id_invalid",
    "peer id invalid",
)


def is_permanent_telegram_error(exc: BaseException) -> bool:
    """True when retrying the same send cannot succeed (blocked bot, missing chat, etc.)."""
    names = {cls.__name__ for cls in type(exc).__mro__}
    if names & _PERMANENT_TYPES:
        return True
    if "TelegramAPIError" in names or "TelegramBadRequest" in names:
        msg = str(exc).lower()
        return any(s in msg for s in _PERMANENT_SNIPPETS)
    return False
