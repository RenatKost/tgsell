"""Keep Telegram bot tokens out of logs and error messages."""
import logging
import re

# Matches "bot123456:AA..." in api.telegram.org URLs (incl. /file/bot...) and bare tokens.
_TOKEN_RE = re.compile(r"(bot)?\d{6,12}:[A-Za-z0-9_-]{30,}")

_NOISY_LOGGERS = ("httpx", "httpcore", "aiohttp.access", "aiohttp.client", "aiogram.event")


def redact(text) -> str:
    """Replace any Telegram bot token in text with a placeholder."""
    if text is None:
        return text
    return _TOKEN_RE.sub(lambda m: (m.group(1) or "") + "<redacted>", str(text))


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
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, TokenRedactFilter) for f in handler.filters):
            handler.addFilter(flt)
