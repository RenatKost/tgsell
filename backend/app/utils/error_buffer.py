"""In-process ring buffer of recent WARNING+ log records (read by GET /api/audit/summary).

Records are stored already redacted; nothing here is persisted or sent anywhere.
"""
from __future__ import annotations

import logging
import re
import threading
from collections import deque
from datetime import datetime, timezone

PROCESS_STARTED_AT = datetime.now(timezone.utc)
BUFFER_SIZE = 200
SAMPLE_MAX_LEN = 300

# Order matters: key=value first (masks the whole value), then specific token shapes.
_KV_RE = re.compile(r"(?i)\b(key|token|secret|password|passwd|pwd|api_key|apikey)(\s*[=:]\s*)([^\s&,;\"']+)")
_BOT_TOKEN_RE = re.compile(r"\d+:[A-Za-z0-9_-]{30,}")
_HEX_RE = re.compile(r"\b(?:0x)?[0-9a-fA-F]{32,}\b")
_B64_RE = re.compile(r"[A-Za-z0-9_\-+]{24,}={0,2}")
_TRON_ADDR_RE = re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b")
_TME_RE = re.compile(r"(?i)(?:https?://)?t\.me/[^\s\"'<>]+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z][A-Za-z0-9_]{3,}")


def _mask_token_like(m: re.Match) -> str:
    """Mask base64/url-safe looking runs; keep long snake_case identifiers readable."""
    tok = m.group(0)
    has_digit = any(c.isdigit() for c in tok)
    has_alpha = any(c.isalpha() for c in tok)
    mixed_case = any(c.isupper() for c in tok) and any(c.islower() for c in tok)
    if (has_digit and has_alpha) or (mixed_case and "_" not in tok) or len(tok) >= 40:
        return "<token>"
    return tok


def redact_sample(text) -> str:
    """Mask anything that could be a secret or contact in a log message sample."""
    if text is None:
        return ""
    s = str(text)
    s = _KV_RE.sub(lambda m: m.group(1) + m.group(2) + "***", s)
    s = _BOT_TOKEN_RE.sub("<bot-token>", s)
    s = _TME_RE.sub("<tg-link>", s)
    s = _EMAIL_RE.sub("<email>", s)
    s = _TRON_ADDR_RE.sub("<address>", s)
    s = _HEX_RE.sub("<hex>", s)
    s = _B64_RE.sub(_mask_token_like, s)
    s = _HANDLE_RE.sub("@<handle>", s)
    if len(s) > SAMPLE_MAX_LEN:
        s = s[:SAMPLE_MAX_LEN] + "…"
    return s


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


class ErrorRingBuffer(logging.Handler):
    """Keeps the last BUFFER_SIZE WARNING+ records as small redacted dicts."""

    def __init__(self, maxlen: int = BUFFER_SIZE):
        super().__init__(level=logging.WARNING)
        self.records: deque[dict] = deque(maxlen=maxlen)
        self._buf_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            try:
                message = record.getMessage()
            except Exception:
                message = str(record.msg)
            template = record.msg if isinstance(record.msg, str) else type(record.msg).__name__
            if record.exc_info and record.exc_info[0] is not None:
                message = f"{message} [{record.exc_info[0].__name__}]"
            item = {
                "logger": record.name,
                "level": record.levelname,
                "template": redact_sample(template)[:200],
                "message": redact_sample(message),
                "ts": record.created,
            }
            with self._buf_lock:
                self.records.append(item)
        except Exception:  # never break logging
            pass

    def snapshot(self) -> list[dict]:
        with self._buf_lock:
            return list(self.records)

    def summary(self) -> dict:
        items = self.snapshot()
        groups: dict[tuple[str, str], dict] = {}
        for it in items:
            key = (it["logger"], it["template"])
            g = groups.get(key)
            if g is None:
                g = groups[key] = {
                    "logger": it["logger"],
                    "template": it["template"],
                    "level": it["level"],
                    "count": 0,
                    "first_seen": _iso(it["ts"]),
                    "last_seen": _iso(it["ts"]),
                    "sample": it["message"],
                    "_last_ts": it["ts"],
                }
            g["count"] += 1
            if logging.getLevelName(it["level"]) > logging.getLevelName(g["level"]):
                g["level"] = it["level"]
            if it["ts"] >= g["_last_ts"]:
                g["_last_ts"] = it["ts"]
                g["last_seen"] = _iso(it["ts"])
                g["sample"] = it["message"]
        out = sorted(groups.values(), key=lambda g: g["_last_ts"], reverse=True)
        for g in out:
            g.pop("_last_ts", None)
        by_level: dict[str, int] = {}
        for it in items:
            by_level[it["level"]] = by_level.get(it["level"], 0) + 1
        return {
            "buffer_size": self.records.maxlen,
            "buffered": len(items),
            "by_level": by_level,
            "groups": out,
        }


_handler: ErrorRingBuffer | None = None


def install_error_buffer() -> ErrorRingBuffer:
    """Attach the ring buffer to the root logger once (idempotent)."""
    global _handler
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, ErrorRingBuffer):
            _handler = h
            return h
    _handler = ErrorRingBuffer()
    root.addHandler(_handler)
    return _handler


def get_error_buffer() -> ErrorRingBuffer | None:
    return _handler
