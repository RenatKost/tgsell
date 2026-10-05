"""Deal transfer checklist: gate to awaiting_payout, side permissions, reminders.

Runs without DB/network: stubs app.database before importing models.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

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

from app.models.deal import DealStatus  # noqa: E402
from app.services import deal_checklist as cl  # noqa: E402

BUYER_ID, SELLER_ID, STRANGER_ID = 10, 20, 99
T0 = datetime(2026, 10, 5, 12, 0, 0)

SELLER_REQUIRED = ["enabled_2fa", "added_buyer_admin", "transferred_ownership", "removed_extra_admins"]
BUYER_REQUIRED = ["became_owner", "checked_admins", "checked_subscribers"]


def _deal(**kw):
    base = dict(
        id=7,
        status=DealStatus.channel_transferring,
        buyer_id=BUYER_ID,
        seller_id=SELLER_ID,
        buyer_confirmed_transfer=False,
        seller_confirmed_transfer=False,
        paid_at=T0,
        checklist_started_at=T0,
        last_checklist_activity_at=None,
        reminder_6h_sent_at=None,
        reminder_24h_sent_at=None,
        admin_alert_48h_sent_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _items(done_keys=()):
    return [
        SimpleNamespace(key=d.key, side=d.side, required=d.required, done=d.key in set(done_keys))
        for d in cl.CHECKLIST_ITEMS
    ]


ALL_REQUIRED = SELLER_REQUIRED + BUYER_REQUIRED


# ── Definitions ─────────────────────────────────────────────────────────

def test_item_definitions():
    seller = [d.key for d in cl.defs_for_side(cl.SIDE_SELLER)]
    buyer = [d.key for d in cl.defs_for_side(cl.SIDE_BUYER)]
    assert seller == SELLER_REQUIRED + ["transferred_linked_chat"]
    assert buyer == BUYER_REQUIRED
    assert cl.ITEMS_BY_KEY["transferred_linked_chat"].required is False
    assert cl.ITEMS_BY_KEY["enabled_2fa"].label == "Увімкнув 2FA"
    assert all(d.required for d in cl.CHECKLIST_ITEMS if d.key != "transferred_linked_chat")


# ── Gate: transition to awaiting_payout ──────────────────────────────────

def test_transition_blocked_when_required_items_open():
    deal = _deal(buyer_confirmed_transfer=True, seller_confirmed_transfer=True)
    items = _items(ALL_REQUIRED[:-1])  # one buyer item open
    assert cl.can_advance_to_awaiting_payout(deal, items) is False
    assert [d.key for d in cl.open_required_defs(items)] == ["checked_subscribers"]


def test_transition_blocked_when_rows_missing_fail_closed():
    deal = _deal(buyer_confirmed_transfer=True, seller_confirmed_transfer=True)
    assert cl.can_advance_to_awaiting_payout(deal, []) is False


def test_transition_blocked_without_both_confirmations():
    items = _items(ALL_REQUIRED)
    assert cl.can_advance_to_awaiting_payout(_deal(buyer_confirmed_transfer=True), items) is False
    assert cl.can_advance_to_awaiting_payout(_deal(seller_confirmed_transfer=True), items) is False


def test_transition_allowed_when_all_required_done_optional_open():
    deal = _deal(buyer_confirmed_transfer=True, seller_confirmed_transfer=True)
    items = _items(ALL_REQUIRED)  # optional linked chat NOT done
    assert cl.can_advance_to_awaiting_payout(deal, items) is True
    deal.status = DealStatus.paid  # legacy paid status also accepted
    assert cl.can_advance_to_awaiting_payout(deal, items) is True


def test_transition_never_from_non_transfer_status():
    items = _items(ALL_REQUIRED)
    for st in (DealStatus.disputed, DealStatus.awaiting_payout, DealStatus.payout_in_progress,
               DealStatus.completed, DealStatus.cancelled):
        deal = _deal(status=st, buyer_confirmed_transfer=True, seller_confirmed_transfer=True)
        assert cl.can_advance_to_awaiting_payout(deal, items) is False


def test_confirm_rejected_400_with_ukrainian_message_when_own_items_open():
    deal = _deal()
    items = _items(BUYER_REQUIRED)  # buyer done, seller nothing
    with pytest.raises(cl.ChecklistError) as ei:
        cl.check_confirm_allowed(deal, SELLER_ID, items)
    assert ei.value.http_status == 400
    assert ei.value.code == "checklist_open"
    assert "чек-листа" in ei.value.message and "«Увімкнув 2FA»" in ei.value.message
    # buyer can confirm (own side done) even though seller side is open
    assert cl.check_confirm_allowed(deal, BUYER_ID, items) == cl.SIDE_BUYER


def test_confirm_rejects_stranger_and_wrong_status():
    with pytest.raises(cl.ChecklistError) as ei:
        cl.check_confirm_allowed(_deal(), STRANGER_ID, _items(ALL_REQUIRED))
    assert ei.value.http_status == 403
    with pytest.raises(cl.ChecklistError) as ei:
        cl.check_confirm_allowed(_deal(status=DealStatus.disputed), BUYER_ID, _items(ALL_REQUIRED))
    assert ei.value.http_status == 400


def test_mark_transferring_only_from_paid():
    d = _deal(status=DealStatus.paid)
    assert cl.mark_transferring(d) is True and d.status == DealStatus.channel_transferring
    assert cl.mark_transferring(d) is False
    d2 = _deal(status=DealStatus.disputed)
    assert cl.mark_transferring(d2) is False and d2.status == DealStatus.disputed


# ── Side permissions ─────────────────────────────────────────────────────

def test_seller_can_tick_only_seller_items():
    deal = _deal()
    item, side = cl.check_toggle_allowed(deal, SELLER_ID, "enabled_2fa")
    assert side == cl.SIDE_SELLER and item.key == "enabled_2fa"
    with pytest.raises(cl.ChecklistError) as ei:
        cl.check_toggle_allowed(deal, SELLER_ID, "became_owner")
    assert ei.value.http_status == 403 and ei.value.code == "wrong_side"


def test_buyer_can_tick_only_buyer_items():
    deal = _deal()
    _, side = cl.check_toggle_allowed(deal, BUYER_ID, "checked_admins")
    assert side == cl.SIDE_BUYER
    with pytest.raises(cl.ChecklistError) as ei:
        cl.check_toggle_allowed(deal, BUYER_ID, "transferred_ownership")
    assert ei.value.http_status == 403


def test_stranger_unknown_key_and_status():
    with pytest.raises(cl.ChecklistError) as ei:
        cl.check_toggle_allowed(_deal(), STRANGER_ID, "enabled_2fa")
    assert ei.value.http_status == 403 and ei.value.code == "not_participant"
    with pytest.raises(cl.ChecklistError) as ei:
        cl.check_toggle_allowed(_deal(), SELLER_ID, "nope")
    assert ei.value.http_status == 404
    with pytest.raises(cl.ChecklistError) as ei:
        cl.check_toggle_allowed(_deal(status=DealStatus.awaiting_payout), SELLER_ID, "enabled_2fa")
    assert ei.value.http_status == 400


def test_untick_blocked_after_own_confirmation():
    deal = _deal(seller_confirmed_transfer=True)
    with pytest.raises(cl.ChecklistError):
        cl.check_untick_allowed(deal, cl.SIDE_SELLER, currently_done=True, new_done=False)
    cl.check_untick_allowed(deal, cl.SIDE_SELLER, currently_done=False, new_done=True)  # tick ok
    cl.check_untick_allowed(deal, cl.SIDE_BUYER, currently_done=True, new_done=False)  # buyer not confirmed


# ── Reminders (pure selection with fake now) ─────────────────────────────

def test_no_reminder_before_6h():
    assert cl.plan_deal_reminders(_deal(), _items(), T0 + timedelta(hours=5, minutes=59)) is None


def test_6h_reminder_targets_only_side_with_open_items_and_dedups():
    # seller finished + confirmed; buyer still has open items
    deal = _deal(seller_confirmed_transfer=True)
    items = _items(SELLER_REQUIRED)
    now = T0 + timedelta(hours=6, minutes=5)
    plan = cl.plan_deal_reminders(deal, items, now)
    assert plan is not None
    assert plan.stages == [cl.STAGE_6H]
    assert plan.sides == [cl.SIDE_BUYER]
    assert plan.open_labels[cl.SIDE_BUYER] == [
        "Став власником каналу", "Перевірив список адмінів",
        "Перевірив підписників/стату — приблизно як у лоті",
    ]
    cl.apply_reminder_plan(deal, plan.stages, now)
    assert deal.reminder_6h_sent_at == now
    # same window, next run (+30 min): nothing again
    assert cl.plan_deal_reminders(deal, items, now + timedelta(minutes=30)) is None


def test_6h_reminder_both_sides_when_both_open():
    plan = cl.plan_deal_reminders(_deal(), _items(), T0 + timedelta(hours=7))
    assert plan.sides == [cl.SIDE_SELLER, cl.SIDE_BUYER]


def test_24h_then_48h_admin_once_each():
    deal = _deal()
    items = _items(BUYER_REQUIRED)  # seller open
    t6 = T0 + timedelta(hours=6)
    cl.apply_reminder_plan(deal, cl.plan_deal_reminders(deal, items, t6).stages, t6)

    t24 = T0 + timedelta(hours=24, minutes=1)
    plan = cl.plan_deal_reminders(deal, items, t24)
    assert plan.stages == [cl.STAGE_24H]
    assert cl.SIDE_SELLER in plan.sides
    cl.apply_reminder_plan(deal, plan.stages, t24)
    assert cl.plan_deal_reminders(deal, items, t24 + timedelta(hours=1)) is None

    t48 = T0 + timedelta(hours=48)
    plan = cl.plan_deal_reminders(deal, items, t48)
    assert plan.stages == [cl.STAGE_ADMIN_48H]
    cl.apply_reminder_plan(deal, plan.stages, t48)
    assert deal.admin_alert_48h_sent_at == t48
    assert cl.plan_deal_reminders(deal, items, t48 + timedelta(hours=10)) is None


def test_first_seen_at_30h_sends_only_24h_not_both():
    deal = _deal()
    now = T0 + timedelta(hours=30)
    plan = cl.plan_deal_reminders(deal, _items(), now)
    assert plan.stages == [cl.STAGE_24H]
    cl.apply_reminder_plan(deal, plan.stages, now)
    assert deal.reminder_6h_sent_at == now and deal.reminder_24h_sent_at == now
    assert cl.plan_deal_reminders(deal, _items(), now + timedelta(minutes=30)) is None


def test_activity_resets_idle_timer_and_dedup():
    deal = _deal()
    t7 = T0 + timedelta(hours=7)
    cl.apply_reminder_plan(deal, cl.plan_deal_reminders(deal, _items(), t7).stages, t7)
    t8 = T0 + timedelta(hours=8)
    cl.record_checklist_activity(deal, t8)  # someone ticked an item
    assert deal.reminder_6h_sent_at is None
    assert cl.plan_deal_reminders(deal, _items(), t8 + timedelta(hours=5)) is None
    plan = cl.plan_deal_reminders(deal, _items(), t8 + timedelta(hours=6))
    assert plan.stages == [cl.STAGE_6H]


def test_unconfirmed_side_with_done_items_still_reminded_to_confirm():
    deal = _deal()
    items = _items(ALL_REQUIRED)
    plan = cl.plan_deal_reminders(deal, items, T0 + timedelta(hours=6))
    assert plan.sides == [cl.SIDE_SELLER, cl.SIDE_BUYER]
    assert plan.open_labels == {cl.SIDE_SELLER: [], cl.SIDE_BUYER: []}
    assert plan.needs_confirm == {cl.SIDE_SELLER: True, cl.SIDE_BUYER: True}


def test_no_reminders_for_non_transfer_statuses():
    for st in (DealStatus.disputed, DealStatus.awaiting_payout, DealStatus.completed):
        assert cl.plan_deal_reminders(_deal(status=st), _items(), T0 + timedelta(days=3)) is None


def test_reminder_text_ukrainian():
    txt = cl.build_reminder_text(7, cl.SIDE_SELLER, cl.STAGE_6H, ["Увімкнув 2FA"], True, "https://tgsell.me/")
    assert "угоді <b>#7</b>" in txt and "• Увімкнув 2FA" in txt
    assert "https://tgsell.me/deal/7" in txt and "Підтвердити передачу" in txt


# ── Reminder delivery: logs + side routing (bot stubbed) ──────────────────

@pytest.mark.asyncio
async def test_deliver_logs_and_routes_to_correct_side(monkeypatch, caplog):
    import logging

    # Stub aiogram Bot + bot.main helper + alerts so no network is used.
    sent: list[tuple[int, str]] = []
    alerts: list[str] = []

    class FakeSession:
        async def close(self):
            pass

    class FakeBot:
        def __init__(self, token):
            self.session = FakeSession()

    fake_aiogram = ModuleType("aiogram")
    fake_aiogram.Bot = FakeBot
    monkeypatch.setitem(sys.modules, "aiogram", fake_aiogram)

    async def notify_checklist_reminder(bot, telegram_id, text):
        sent.append((telegram_id, text))
        return True

    fake_bot_main = ModuleType("bot.main")
    fake_bot_main.notify_checklist_reminder = notify_checklist_reminder
    monkeypatch.setitem(sys.modules, "bot.main", fake_bot_main)

    async def send_admin_alert(text, alert_key=None, throttle_minutes=30):
        alerts.append(text)

    fake_alerts = ModuleType("app.services.alerts")
    fake_alerts.send_admin_alert = send_admin_alert
    monkeypatch.setitem(sys.modules, "app.services.alerts", fake_alerts)

    from app.tasks import checklist_reminders as task
    monkeypatch.setattr(task.settings, "bot_token_alerts", "test-token-not-real")

    deal = _deal(seller_confirmed_transfer=True)
    items = _items(SELLER_REQUIRED)
    plan = cl.plan_deal_reminders(deal, items, T0 + timedelta(hours=49))
    assert plan.stages == [cl.STAGE_24H, cl.STAGE_ADMIN_48H]
    buyer = SimpleNamespace(id=BUYER_ID, telegram_id=1001)
    seller = SimpleNamespace(id=SELLER_ID, telegram_id=2002)

    with caplog.at_level(logging.INFO, logger="app.tasks.checklist_reminders"):
        await task._deliver(plan, buyer, seller)

    assert [tg for tg, _ in sent] == [1001]  # only buyer (seller done + confirmed)
    assert len(alerts) == 1 and "угода #7" in alerts[0]
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "[CHECKLIST] deal #7 reminder 24h → buyer" in logs
    assert "[CHECKLIST] deal #7 admin alert 48h → admin group" in logs
    print(logs)


# ── Auto-verify evaluation (pure) ─────────────────────────────────────────

def test_parse_channel_username():
    assert cl.parse_channel_username("https://t.me/my_channel") == "my_channel"
    assert cl.parse_channel_username("@my_channel") == "my_channel"
    assert cl.parse_channel_username("t.me/my_channel?x=1") == "my_channel"
    assert cl.parse_channel_username("https://t.me/+AbCdEf") is None
    assert cl.parse_channel_username("https://t.me/joinchat/xyz") is None
    assert cl.parse_channel_username("") is None


def test_evaluate_auto_verify_owner_and_subs():
    res = cl.evaluate_auto_verify(
        [{"name": "A", "expected_subs": 1000, "actual_subs": 950,
          "admins": [{"id": 1001, "is_creator": True, "is_bot": False},
                     {"id": 5, "is_creator": False, "is_bot": True}],
          "error": None}],
        buyer_tg=1001, seller_tg=2002,
    )
    assert res["became_owner"][0] is True
    assert res["checked_subscribers"][0] is True
    assert res["checked_admins"][0] is None and "ботів: 1" in res["checked_admins"][1]


def test_evaluate_auto_verify_degrades_without_admin_rights():
    res = cl.evaluate_auto_verify(
        [{"name": "A", "expected_subs": 1000, "actual_subs": 500, "admins": None, "error": None}],
        buyer_tg=1001, seller_tg=2002,
    )
    assert res["became_owner"][0] is None
    assert "недоступний" in res["became_owner"][1]
    assert res["checked_subscribers"][0] is False


def test_evaluate_auto_verify_seller_still_owner():
    res = cl.evaluate_auto_verify(
        [{"name": "A", "expected_subs": 10, "actual_subs": 10,
          "admins": [{"id": 2002, "is_creator": True, "is_bot": False}], "error": None}],
        buyer_tg=1001, seller_tg=2002,
    )
    assert res["became_owner"][0] is False and "продавець" in res["became_owner"][1]


# ── Static guards ──────────────────────────────────────────────────────────

def test_migration_0022_shape():
    mig = (BACKEND_ROOT / "alembic/versions/0022_add_deal_checklist.py").read_text(encoding="utf-8")
    assert 'revision: str = "0022"' in mig and '"0021"' in mig
    assert "deal_checklist_items" in mig
    for col in ("reminder_6h_sent_at", "reminder_24h_sent_at", "admin_alert_48h_sent_at",
                "checklist_started_at", "last_checklist_activity_at"):
        assert col in mig
    assert "op.execute(" not in mig  # no PG enum ALTER TYPE needed


def test_routers_use_checklist_gate():
    deals = (BACKEND_ROOT / "app/routers/deals.py").read_text(encoding="utf-8")
    impl = deals[deals.index("async def _confirm_transfer_impl"):deals.index("# ===== Transfer checklist")]
    assert "check_confirm_allowed" in impl
    assert "can_advance_to_awaiting_payout" in impl
    assert "DealStatus.awaiting_payout" not in impl  # only via advance helper
    bot = (BACKEND_ROOT / "bot/main.py").read_text(encoding="utf-8")
    cb = bot[bot.index("async def cb_deal_confirm"):bot.index("async def cb_deal_dispute")]
    assert "can_advance_to_awaiting_payout" in cb
    assert "deal.status = DealStatus.awaiting_payout" not in cb


def test_autoverify_never_touches_done_or_status():
    src = (BACKEND_ROOT / "app/services/checklist_autoverify.py").read_text(encoding="utf-8")
    assert ".done =" not in src
    assert "deal.status" not in src
    assert "transfer_usdt" not in src
    assert 'health.get("ok")' in src
