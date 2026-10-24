from datetime import datetime

from app.models.user import User
from app.schemas.auth import UserResponse


def _u(**kw):
    base = dict(id=1, telegram_id=42, username="u", first_name="U", avatar_url=None, role="user",
                usdt_wallet=None, created_at=datetime(2026, 1, 1), is_blocked=False)
    base.update(kw)
    return User(**base)


def test_alert_bot_started_flag():
    assert UserResponse.model_validate(_u()).alert_bot_started is False
    assert UserResponse.model_validate(_u(tg_bot_started_at=datetime(2026, 1, 2))).alert_bot_started is True
    assert UserResponse.model_validate(_u(tg_bot_started_at=datetime(2026, 1, 2),
                                          tg_bot_unreachable_at=datetime(2026, 1, 3))).alert_bot_started is False
    assert UserResponse.model_validate(_u(telegram_id=None, tg_bot_started_at=datetime(2026, 1, 2))).alert_bot_started is False
