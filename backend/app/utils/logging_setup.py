"""Logging setup: DEBUG/INFO → stdout, WARNING+ → stderr (task 15 item 5).

Railway shows everything on stderr as an error, so INFO must not go there. uvicorn
installs its own handlers (uvicorn.error → stderr) before importing the app; we drop
them and let uvicorn/aiogram/telethon propagate to the root handlers below.
"""
import logging
import sys

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_PROPAGATE_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "aiogram", "telethon", "sqlalchemy")


class _MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int):
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.max_level


def setup_logging(level: int = logging.INFO) -> None:
    fmt = logging.Formatter(FORMAT)
    out = logging.StreamHandler(sys.stdout)
    out.setLevel(logging.DEBUG)
    out.addFilter(_MaxLevelFilter(logging.WARNING))
    out.setFormatter(fmt)
    err = logging.StreamHandler(sys.stderr)
    err.setLevel(logging.WARNING)
    err.setFormatter(fmt)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(out)
    root.addHandler(err)
    root.setLevel(level)

    for name in _PROPAGATE_LOGGERS:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True
