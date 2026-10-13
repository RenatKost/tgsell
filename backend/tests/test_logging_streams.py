"""Task 15 item 5: INFO → stdout, WARNING+ → stderr; library loggers propagate to root."""
import logging
import sys

from app.utils.log_redact import setup_log_hygiene
from app.utils.logging_setup import setup_logging


def test_info_stdout_warning_stderr(capsys):
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    uv = logging.getLogger("uvicorn.error")
    uv.addHandler(logging.StreamHandler(sys.stderr))  # what uvicorn installs
    uv.propagate = False
    try:
        setup_logging()
        setup_log_hygiene()
        for name in ("app.x", "uvicorn.error", "aiogram.dispatcher", "telethon.network"):
            logging.getLogger(name).info("info-%s", name)
            logging.getLogger(name).warning("warn-%s", name)
        logging.getLogger("app.x").error("tok bot123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
        out, err = capsys.readouterr()
        for name in ("app.x", "uvicorn.error", "aiogram.dispatcher", "telethon.network"):
            assert f"info-{name}" in out and f"info-{name}" not in err
            assert f"warn-{name}" in err and f"warn-{name}" not in out
        assert "<redacted>" in err and "AAAAAAAA" not in err
        assert not uv.handlers and uv.propagate
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])
