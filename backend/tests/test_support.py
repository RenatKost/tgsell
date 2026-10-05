"""Support bot helpers + queue auth (no DB/network)."""
from __future__ import annotations

import hmac
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _install_db_stub() -> None:
    if "app.database" in sys.modules:
        return
    stub = ModuleType("app.database")

    class Base:  # noqa: D401
        pass

    stub.Base = Base
    stub.async_session = None
    stub.get_db = None
    sys.modules["app.database"] = stub


_install_db_stub()

from app.services import support_logic as sl  # noqa: E402


# ── Keyword detection ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text,expected",
    [
        ("коли буде виплата?", True),
        ("Жду выплату", True),
        ("Where is my PAYOUT?", True),
        ("відкриваю спір", True),
        ("это спор", True),
        ("open a dispute please", True),
        ("підозра на фрод", True),
        ("это мошенничество", True),
        ("шахрайство на сайті", True),
        ("FRAUD alert", True),
        ("scam channel", True),
        ("проблема з escrow", True),
        ("ескроу зависло", True),
        ("эскроу не отпустил", True),
        ("хочу повернення коштів", True),
        ("прошу возврат", True),
        ("need a refund", True),
        ("як додати канал?", False),
        ("", False),
        (None, False),
        ("привіт підтримка", False),
    ],
)
def test_is_urgent_text(text, expected):
    assert sl.is_urgent_text(text) is expected


def test_message_text_from_update_plain():
    assert sl.message_text_from_update("hello", None, None) == "hello"


def test_message_text_from_update_media():
    assert sl.message_text_from_update(None, "cap", "photo") == "[photo] cap"
    assert sl.message_text_from_update(None, None, "voice") == "[voice]"


def test_excerpt_truncates():
    long = "x" * 500
    out = sl.excerpt(long, 50)
    assert len(out) == 50
    assert out.endswith("…")


# ── Dedup helpers ──────────────────────────────────────────────────────

T0 = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)


def test_auto_reply_first_message():
    assert sl.should_send_auto_reply(None, now=T0) is True


def test_auto_reply_within_cooldown():
    last = T0 - timedelta(minutes=10)
    assert sl.should_send_auto_reply(last, now=T0) is False


def test_auto_reply_after_cooldown():
    last = T0 - timedelta(minutes=31)
    assert sl.should_send_auto_reply(last, now=T0) is True


def test_auto_reply_naive_datetime():
    last = (T0 - timedelta(minutes=31)).replace(tzinfo=None)
    assert sl.should_send_auto_reply(last, now=T0) is True


def test_urgent_alert_dedup():
    assert sl.should_send_urgent_alert(None, now=T0) is True
    assert sl.should_send_urgent_alert(T0 - timedelta(minutes=5), now=T0) is False
    assert sl.should_send_urgent_alert(T0 - timedelta(minutes=30), now=T0) is True


def test_build_urgent_alert_contains_user_link():
    html = sl.build_urgent_alert_html(
        telegram_user_id=12345,
        username="buyer",
        first_name="Ivan",
        text="виплата не прийшла " + ("x" * 400),
        message_id=99,
    )
    assert "tg://user?id=12345" in html
    assert "@buyer" in html
    assert "#99" in html or "99" in html
    assert "виплата" in html


# ── Queue auth (pure, mirrors router logic) ─────────────────────────────

def _check_support_secret(expected: str, provided: str | None) -> int:
    """Return HTTP status code the endpoint would emit."""
    if not expected:
        return 503
    if not hmac.compare_digest(provided or "", expected):
        return 401
    return 200


def test_queue_auth_unset_secret():
    assert _check_support_secret("", "anything") == 503
    assert _check_support_secret("", None) == 503


def test_queue_auth_bad_secret():
    assert _check_support_secret("real-secret", "wrong") == 401
    assert _check_support_secret("real-secret", None) == 401
    assert _check_support_secret("real-secret", "") == 401


def test_queue_auth_ok():
    assert _check_support_secret("real-secret", "real-secret") == 200


