"""Keep Telegram bot tokens out of logs and error messages."""
import logging
import re

# Matches "bot123456:AA..." in api.telegram.org URLs (incl. /file/bot...) and bare tokens.
_TOKEN_RE = re.compile(r"(bot)?\d{6,12}:[A-Za-z0-9_-]{30,}")

_NOISY_LOGGERS = ("httpx", "httpcore", "aiohttp.access", "aiohttp.client", "aiogram.event")


# Task 33: one-time login tokens in query strings (uvicorn access log of
# /api/auth/bot-check?token=...): mask the value, keep the parameter name.
_QUERY_TOKEN_RE = re.compile(r"([?&](?:token|access_token|refresh_token)=)[^&\s\"']+", re.IGNORECASE)


def redact(text) -> str:
    """Replace any Telegram bot token / query-string token in text with a placeholder."""
    if text is None:
        return text
    out = _TOKEN_RE.sub(lambda m: (m.group(1) or "") + "<redacted>", str(text))
    return _QUERY_TOKEN_RE.sub(lambda m: m.group(1) + "***", out)


class TokenRedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        clean = redact(msg)
        if clean != msg:
            record.msg = clean
            record.args = None
        return True


def setup_log_hygiene() -> None:
    """Silence per-request HTTP logs and redact tokens on all root handlers."""
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    flt = TokenRedactFilter()
    access = logging.getLogger("uvicorn.access")  # bot-check ?token=... in access lines
    if not any(isinstance(f, TokenRedactFilter) for f in access.filters):
        access.addFilter(flt)
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, TokenRedactFilter) for f in handler.filters):
            handler.addFilter(flt)
