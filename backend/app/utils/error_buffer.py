"""In-process deduplicated buffer of recent WARNING+ log records (read by GET /api/audit/summary).

Records are stored already redacted; nothing here is persisted or sent anywhere.
"""
from __future__ import annotations

import logging
import re
import threading
from collections import OrderedDict
from datetime import datetime, timezone

PROCESS_STARTED_AT = datetime.now(timezone.utc)
BUFFER_SIZE = 1000  # distinct (deduplicated) entries
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


_NUM_RE = re.compile(r"\d+")


def dedup_key(logger_name: str, exc_type: str, message: str) -> str:
    """Normalized key: logger + exception type + redacted message with numbers/ids collapsed."""
    norm = _NUM_RE.sub("#", message or "")
    return f"{logger_name}|{exc_type}|{norm}"


class ErrorRingBuffer(logging.Handler):
    """Deduplicated buffer of recent WARNING+ records as small redacted dicts.

    Identical messages (same logger, exception type and text up to numbers/ids)
    share one entry with count / first_seen / last_seen, so a burst of one error
    no longer pushes everything else out. Up to ``maxlen`` distinct entries are
    kept; the least recently seen one is evicted first.
    """

    def __init__(self, maxlen: int = BUFFER_SIZE):
        super().__init__(level=logging.WARNING)
        self.maxlen = maxlen
        self.entries: OrderedDict[str, dict] = OrderedDict()
        self.evicted = 0
        self._buf_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "skip_error_buffer", False):
            return
        try:
            try:
                message = record.getMessage()
            except Exception:
                message = str(record.msg)
            template = record.msg if isinstance(record.msg, str) else type(record.msg).__name__
            exc_type = ""
            if record.exc_info and record.exc_info[0] is not None:
                exc_type = record.exc_info[0].__name__
                message = f"{message} [{exc_type}]"
            message = redact_sample(message)
            key = dedup_key(record.name, exc_type, message)
            ts = record.created
            with self._buf_lock:
                item = self.entries.get(key)
                if item is None:
                    self.entries[key] = {
                        "logger": record.name,
                        "level": record.levelname,
                        "template": redact_sample(template)[:200],
                        "message": message,
                        "ts": ts,
                        "count": 1,
                        "first_ts": ts,
                    }
                    while len(self.entries) > self.maxlen:
                        self.entries.popitem(last=False)
                        self.evicted += 1
                else:
                    item["count"] += 1
                    item["message"] = message
                    item["ts"] = max(item["ts"], ts)
                    item["first_ts"] = min(item["first_ts"], ts)
                    if record.levelno > logging.getLevelName(item["level"]):
                        item["level"] = record.levelname
                    self.entries.move_to_end(key)
        except Exception:  # never break logging
            pass

    def snapshot(self) -> list[dict]:
        """Distinct entries, oldest-seen first. Each has count, first_seen, last_seen."""
        with self._buf_lock:
            items = [dict(it) for it in self.entries.values()]
        for it in items:
            it["first_seen"] = _iso(it["first_ts"])
            it["last_seen"] = _iso(it["ts"])
        return items

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
                    "distinct": 0,
                    "first_seen": it["first_seen"],
                    "last_seen": it["last_seen"],
                    "sample": it["message"],
                    "_first_ts": it["first_ts"],
                    "_last_ts": it["ts"],
                }
            g["count"] += it["count"]
            g["distinct"] += 1
            if logging.getLevelName(it["level"]) > logging.getLevelName(g["level"]):
                g["level"] = it["level"]
            if it["first_ts"] < g["_first_ts"]:
                g["_first_ts"] = it["first_ts"]
                g["first_seen"] = it["first_seen"]
            if it["ts"] >= g["_last_ts"]:
                g["_last_ts"] = it["ts"]
                g["last_seen"] = it["last_seen"]
                g["sample"] = it["message"]
        out = sorted(groups.values(), key=lambda g: g["_last_ts"], reverse=True)
        for g in out:
            g.pop("_last_ts", None)
            g.pop("_first_ts", None)
        by_level: dict[str, int] = {}
        for it in items:
            by_level[it["level"]] = by_level.get(it["level"], 0) + it["count"]
        oldest = min((it["first_ts"] for it in items), default=None)
        return {
            "buffer_size": self.maxlen,
            "buffered": sum(it["count"] for it in items),
            "by_level": by_level,
            "groups": out,
            "dedup": True,
            "distinct_entries": len(items),
            "evicted_entries": self.evicted,
            "oldest_seen": _iso(oldest) if oldest is not None else None,
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
