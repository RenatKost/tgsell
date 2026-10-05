"""Deal transfer checklist — item definitions, pure gating/reminder logic, DB helpers.

Pure functions (no DB / network) are unit-tested in tests/test_deal_checklist.py.
DB helpers import SQLAlchemy lazily-safe pieces only; they never move money and
never mark a deal completed (see app.services.deal_lifecycle for that).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

from app.models.deal import Deal, DealChecklistItem, DealStatus

logger = logging.getLogger(__name__)

SIDE_SELLER = "seller"
SIDE_BUYER = "buyer"
SIDES = (SIDE_SELLER, SIDE_BUYER)
SIDE_LABELS = {SIDE_SELLER: "Продавець", SIDE_BUYER: "Покупець"}

# Statuses where the channel is being handed over (checklist is active).
TRANSFER_STATUSES = (DealStatus.paid, DealStatus.channel_transferring)


@dataclass(frozen=True)
class ChecklistItemDef:
    key: str
    side: str
    label: str
    required: bool = True
    hint: str | None = None


# Single source of truth for checklist items (Ukrainian UI labels).
# Bundle deals use the same list (applies to every channel of the bundle).
CHECKLIST_ITEMS: tuple[ChecklistItemDef, ...] = (
    ChecklistItemDef(
        "enabled_2fa", SIDE_SELLER, "Увімкнув 2FA",
        hint="Telegram вимагає 2FA (хмарний пароль) для передачі прав власника",
    ),
    ChecklistItemDef(
        "added_buyer_admin", SIDE_SELLER, "Додав покупця адміном",
    ),
    ChecklistItemDef(
        "transferred_ownership", SIDE_SELLER, "Зробив Transfer Ownership",
        hint="Канал → Адміністратори → покупець → Передати права власника",
    ),
    ChecklistItemDef(
        "removed_extra_admins", SIDE_SELLER,
        "Прибрав сторонніх адмінів/ботів, крім узгоджених",
    ),
    ChecklistItemDef(
        "transferred_linked_chat", SIDE_SELLER,
        "Передав прив’язаний чат/групу обговорення — якщо є",
        required=False,
    ),
    ChecklistItemDef(
        "became_owner", SIDE_BUYER, "Став власником каналу",
    ),
    ChecklistItemDef(
        "checked_admins", SIDE_BUYER, "Перевірив список адмінів",
    ),
    ChecklistItemDef(
        "checked_subscribers", SIDE_BUYER,
        "Перевірив підписників/стату — приблизно як у лоті",
    ),
)
ITEMS_BY_KEY: dict[str, ChecklistItemDef] = {d.key: d for d in CHECKLIST_ITEMS}

# Reminder thresholds (idle time since last checklist activity).
REMINDER_6H = timedelta(hours=6)
REMINDER_24H = timedelta(hours=24)
ADMIN_ALERT_48H = timedelta(hours=48)

STAGE_6H = "6h"
STAGE_24H = "24h"
STAGE_ADMIN_48H = "admin_48h"

# Subscriber tolerance for auto-verify ("приблизно як у лоті").
SUBSCRIBERS_TOLERANCE = 0.15


# ── Pure helpers ───────────────────────────────────────────────────────

def defs_for_side(side: str) -> list[ChecklistItemDef]:
    return [d for d in CHECKLIST_ITEMS if d.side == side]


def side_for_user(deal, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    if deal.seller_id == user_id:
        return SIDE_SELLER
    if deal.buyer_id == user_id:
        return SIDE_BUYER
    return None


def _done_keys(items: Iterable) -> set[str]:
    return {i.key for i in items if getattr(i, "done", False)}


def open_required_defs(items: Iterable, side: str | None = None) -> list[ChecklistItemDef]:
    """Required items not done. Missing rows count as open (fail-closed)."""
    done = _done_keys(items)
    return [
        d for d in CHECKLIST_ITEMS
        if d.required and (side is None or d.side == side) and d.key not in done
    ]


def all_required_done(items: Iterable) -> bool:
    return not open_required_defs(list(items))


def side_confirmed(deal, side: str) -> bool:
    if side == SIDE_SELLER:
        return bool(deal.seller_confirmed_transfer)
    return bool(deal.buyer_confirmed_transfer)


def can_advance_to_awaiting_payout(deal, items: Iterable) -> bool:
    """awaiting_payout ONLY when both sides confirmed AND all required items done."""
    items = list(items)
    return (
        deal.status in TRANSFER_STATUSES
        and bool(deal.buyer_confirmed_transfer)
        and bool(deal.seller_confirmed_transfer)
        and all_required_done(items)
    )


def checklist_block_message(open_defs: list[ChecklistItemDef]) -> str:
    labels = "; ".join(f"«{d.label}»" for d in open_defs)
    return (
        "Спершу виконайте обов’язкові пункти чек-листа передачі: "
        f"{labels}. Підтвердження можливе лише після їх виконання."
    )


class ChecklistError(Exception):
    """Permission / gate violation with an HTTP status and a Ukrainian message."""

    def __init__(self, code: str, message: str, *, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def check_toggle_allowed(deal, user_id: int | None, key: str) -> tuple[ChecklistItemDef, str]:
    """Only the owning side may tick its own items, only during transfer."""
    item_def = ITEMS_BY_KEY.get(key)
    if item_def is None:
        raise ChecklistError("unknown_item", "Невідомий пункт чек-листа", http_status=404)
    side = side_for_user(deal, user_id)
    if side is None:
        raise ChecklistError(
            "not_participant", "Відмічати пункти можуть лише учасники угоди", http_status=403
        )
    if item_def.side != side:
        raise ChecklistError(
            "wrong_side", "Цей пункт відмічає інша сторона угоди", http_status=403
        )
    if deal.status not in TRANSFER_STATUSES:
        raise ChecklistError(
            "wrong_status", "Чек-лист доступний лише під час передачі каналу", http_status=400
        )
    return item_def, side


def check_untick_allowed(deal, side: str, currently_done: bool, new_done: bool) -> None:
    if currently_done and not new_done and side_confirmed(deal, side):
        raise ChecklistError(
            "already_confirmed",
            "Ви вже підтвердили передачу — зняти позначку неможливо. "
            "Якщо щось пішло не так, відкрийте спір або викличте адміністратора.",
            http_status=400,
        )


def check_confirm_allowed(deal, user_id: int | None, items: Iterable) -> str:
    """Final confirm gate: caller's required items must all be done (400 otherwise)."""
    side = side_for_user(deal, user_id)
    if side is None:
        raise ChecklistError("not_participant", "Access denied", http_status=403)
    if deal.status not in TRANSFER_STATUSES:
        raise ChecklistError("wrong_status", "Угода не в статусі передачі каналу", http_status=400)
    open_own = open_required_defs(list(items), side)
    if open_own:
        raise ChecklistError("checklist_open", checklist_block_message(open_own), http_status=400)
    return side


def pending_sides(deal, items: Iterable) -> list[str]:
    """Sides that still owe something: open required items or missing confirmation."""
    items = list(items)
    out = []
    for side in SIDES:
        if open_required_defs(items, side) or not side_confirmed(deal, side):
            out.append(side)
    return out


def reminder_reference_time(deal) -> datetime | None:
    return (
        getattr(deal, "last_checklist_activity_at", None)
        or getattr(deal, "checklist_started_at", None)
        or getattr(deal, "paid_at", None)
    )


def plan_reminder_stages(
    idle: timedelta,
    *,
    sent_6h: datetime | None,
    sent_24h: datetime | None,
    sent_48h: datetime | None,
) -> list[str]:
    """Which reminder stages are due now (each at most once per idle period).

    If a deal is first seen already ≥24h idle, only the 24h reminder is sent
    (6h is skipped, not sent twice in one run).
    """
    stages: list[str] = []
    if idle >= REMINDER_24H and sent_24h is None:
        stages.append(STAGE_24H)
    elif idle >= REMINDER_6H and sent_6h is None and sent_24h is None:
        stages.append(STAGE_6H)
    if idle >= ADMIN_ALERT_48H and sent_48h is None:
        stages.append(STAGE_ADMIN_48H)
    return stages


@dataclass
class ReminderPlan:
    deal_id: int
    stages: list[str]
    sides: list[str]
    open_labels: dict[str, list[str]] = field(default_factory=dict)
    needs_confirm: dict[str, bool] = field(default_factory=dict)
    idle_hours: float = 0.0


def plan_deal_reminders(deal, items: Iterable, now: datetime) -> ReminderPlan | None:
    """Pure: decide reminders for one deal at `now` (naive UTC)."""
    if deal.status not in TRANSFER_STATUSES:
        return None
    items = list(items)
    sides = pending_sides(deal, items)
    if not sides:
        return None
    ref = reminder_reference_time(deal)
    if ref is None:
        return None
    idle = now - ref
    stages = plan_reminder_stages(
        idle,
        sent_6h=getattr(deal, "reminder_6h_sent_at", None),
        sent_24h=getattr(deal, "reminder_24h_sent_at", None),
        sent_48h=getattr(deal, "admin_alert_48h_sent_at", None),
    )
    if not stages:
        return None
    return ReminderPlan(
        deal_id=deal.id,
        stages=stages,
        sides=sides,
        open_labels={s: [d.label for d in open_required_defs(items, s)] for s in sides},
        needs_confirm={s: not side_confirmed(deal, s) for s in sides},
        idle_hours=round(idle.total_seconds() / 3600, 1),
    )


def apply_reminder_plan(deal, stages: list[str], now: datetime) -> None:
    """Persist dedup markers for the stages that are about to be sent."""
    if STAGE_24H in stages:
        deal.reminder_24h_sent_at = now
        if getattr(deal, "reminder_6h_sent_at", None) is None:
            deal.reminder_6h_sent_at = now
    if STAGE_6H in stages:
        deal.reminder_6h_sent_at = now
    if STAGE_ADMIN_48H in stages:
        deal.admin_alert_48h_sent_at = now


def record_checklist_activity(deal, now: datetime) -> None:
    """Any tick/confirm resets the idle timer and the reminder dedup markers."""
    deal.last_checklist_activity_at = now
    deal.reminder_6h_sent_at = None
    deal.reminder_24h_sent_at = None
    deal.admin_alert_48h_sent_at = None


def mark_transferring(deal) -> bool:
    """paid → channel_transferring on first checklist action. Returns True if changed."""
    if deal.status == DealStatus.paid:
        deal.status = DealStatus.channel_transferring
        return True
    return False


def parse_channel_username(link: str | None) -> str | None:
    """t.me/name, https://t.me/name, @name, name → name. Private invite links → None."""
    if not link:
        return None
    s = link.strip()
    if s.startswith("@"):
        s = s[1:]
    m = re.match(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/(.+)$", s, re.I)
    if m:
        s = m.group(1)
    s = s.split("?")[0].strip("/")
    if not s or s.startswith("+") or s.lower().startswith("joinchat") or "/" in s:
        return None
    if not re.match(r"^[A-Za-z0-9_]{4,64}$", s):
        return None
    return s


def evaluate_auto_verify(
    channel_results: list[dict],
    *,
    buyer_tg: int | None,
    seller_tg: int | None,
) -> dict[str, tuple[bool | None, str]]:
    """Pure: turn Telethon observations into {key: (auto_verified, note)}.

    channel_results items: {name, expected_subs, actual_subs|None,
    admins: [{id, is_creator, is_bot}] | None, error: str|None}
    """
    owner_notes, owner_flags = [], []
    subs_notes, subs_flags = [], []
    admin_notes = []
    multi = len(channel_results) > 1

    for r in channel_results:
        prefix = f"{r.get('name') or 'канал'}: " if multi else ""
        if r.get("error"):
            owner_notes.append(prefix + r["error"])
            subs_notes.append(prefix + r["error"])
            admin_notes.append(prefix + r["error"])
            owner_flags.append(None)
            subs_flags.append(None)
            continue

        actual, expected = r.get("actual_subs"), r.get("expected_subs") or 0
        if actual is None:
            subs_flags.append(None)
            subs_notes.append(prefix + "кількість підписників недоступна")
        else:
            ok = expected <= 0 or abs(actual - expected) <= expected * SUBSCRIBERS_TOLERANCE
            subs_flags.append(ok)
            subs_notes.append(
                prefix + f"зараз {actual} підписників, у лоті {expected}"
                + ("" if ok else " — відхилення понад 15%")
            )

        admins = r.get("admins")
        if admins is None:
            owner_flags.append(None)
            owner_notes.append(prefix + "список адмінів недоступний (сервісний акаунт не адмін каналу)")
            admin_notes.append(prefix + "список адмінів недоступний")
            continue
        creator = next((a for a in admins if a.get("is_creator")), None)
        if creator is None:
            owner_flags.append(None)
            owner_notes.append(prefix + "власника не видно")
        elif buyer_tg and creator.get("id") == buyer_tg:
            owner_flags.append(True)
            owner_notes.append(prefix + "покупець — власник каналу ✓")
        else:
            owner_flags.append(False)
            who = "продавець" if seller_tg and creator.get("id") == seller_tg else "інший акаунт"
            owner_notes.append(prefix + f"власник — {who}, не покупець")
        bots = sum(1 for a in admins if a.get("is_bot"))
        seller_admin = bool(seller_tg) and any(a.get("id") == seller_tg for a in admins)
        admin_notes.append(
            prefix + f"адмінів: {len(admins)} (ботів: {bots})"
            + ("; продавець ще адмін" if seller_admin else "")
        )

    def _agg(flags: list[bool | None]) -> bool | None:
        if flags and all(f is True for f in flags):
            return True
        if any(f is False for f in flags):
            return False
        return None

    owner_v, subs_v = _agg(owner_flags), _agg(subs_flags)
    owner_note = "; ".join(owner_notes) or None
    admin_note = "; ".join(admin_notes) or None
    subs_note = "; ".join(subs_notes) or None
    return {
        "became_owner": (owner_v, owner_note),
        "transferred_ownership": (owner_v, owner_note),
        "checked_subscribers": (subs_v, subs_note),
        # Agreed admins are not known to the system → informational only.
        "checked_admins": (None, admin_note),
        "removed_extra_admins": (None, admin_note),
    }


# ── DB helpers (async) ─────────────────────────────────────────────────

async def load_items(db, deal_id: int) -> list[DealChecklistItem]:
    from sqlalchemy import select

    res = await db.execute(
        select(DealChecklistItem)
        .where(DealChecklistItem.deal_id == deal_id)
        .order_by(DealChecklistItem.id)
    )
    return list(res.scalars().all())


async def ensure_checklist(db, deal: Deal, now: datetime | None = None) -> list[DealChecklistItem]:
    """Idempotently create missing checklist rows (ON CONFLICT DO NOTHING). No commit."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = now or datetime.utcnow()
    existing = await load_items(db, deal.id)
    have = {i.key for i in existing}
    missing = [d for d in CHECKLIST_ITEMS if d.key not in have]
    if missing:
        stmt = pg_insert(DealChecklistItem.__table__).values([
            {"deal_id": deal.id, "side": d.side, "key": d.key,
             "required": d.required, "done": False}
            for d in missing
        ]).on_conflict_do_nothing(index_elements=["deal_id", "key"])
        await db.execute(stmt)
        existing = await load_items(db, deal.id)
        logger.info(f"[CHECKLIST] deal #{deal.id} checklist created ({len(missing)} items)")
    if deal.checklist_started_at is None:
        deal.checklist_started_at = now
    return existing


async def advance_to_awaiting_payout(db, deal: Deal) -> None:
    """Move deal → awaiting_payout and mark channel/bundle sold. Caller commits.

    Caller MUST have checked can_advance_to_awaiting_payout() (gate).
    """
    from sqlalchemy import select
    from app.models.channel import Channel, ChannelStatus

    deal.status = DealStatus.awaiting_payout
    if deal.channel_id:
        ch = await db.get(Channel, deal.channel_id)
        if ch:
            ch.status = ChannelStatus.sold
        logger.info(
            f"[DEAL] Deal #{deal.id}: STATUS → awaiting_payout, channel #{deal.channel_id} SOLD, "
            f"payout={deal.amount_usdt - deal.service_fee:.2f} USDT"
        )
    elif deal.bundle_id:
        from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle

        bc_rows = (await db.execute(
            select(BundleChannel).where(BundleChannel.bundle_id == deal.bundle_id)
        )).scalars().all()
        for bc in bc_rows:
            ch = await db.get(Channel, bc.channel_id)
            if ch:
                ch.status = ChannelStatus.sold
        bundle = await db.get(ChannelBundle, deal.bundle_id)
        if bundle:
            bundle.status = BundleStatus.sold
        logger.info(f"[DEAL] Bundle deal #{deal.id}: STATUS → awaiting_payout, bundle #{deal.bundle_id} SOLD")


def payout_request_message(deal: Deal) -> str:
    payout_amount = deal.amount_usdt - deal.service_fee
    return (
        f"🎉 Канал успішно передано, чек-лист виконано!\n\n"
        f"Продавець, вкажіть свій USDT (TRC-20) гаманець для отримання коштів:\n"
        f"💰 Вартість каналу: {deal.amount_usdt} USDT\n"
        f"📊 Комісія сервісу (3%): {deal.service_fee:.2f} USDT\n"
        f"💵 До виплати: {payout_amount:.2f} USDT"
    )


def build_reminder_text(
    deal_id: int,
    side: str,
    stage: str,
    open_labels: list[str],
    needs_confirm: bool,
    frontend_url: str,
) -> str:
    """HTML bot message for a checklist reminder (Ukrainian)."""
    import html as _html

    head = "⏰ Нагадування" if stage == STAGE_6H else "⏰ Повторне нагадування"
    lines = [f"{head} по угоді <b>#{deal_id}</b>", ""]
    if open_labels:
        lines.append("Залишились пункти чек-листа передачі:")
        lines += [f"• {_html.escape(lbl)}" for lbl in open_labels]
    if needs_confirm:
        if open_labels:
            lines.append("")
        lines.append(
            "Після виконання натисніть «Підтвердити отримання»."
            if side == SIDE_BUYER else
            "Після виконання натисніть «Підтвердити передачу»."
        )
    lines += ["", f"<a href='{frontend_url.rstrip('/')}/deal/{deal_id}'>Відкрити угоду →</a>"]
    if stage == STAGE_24H:
        lines += ["", "Якщо виникли труднощі — викличте адміністратора в чаті угоди."]
    return "\n".join(lines)


def build_admin_alert_text(plan: "ReminderPlan", frontend_url: str) -> str:
    sides = ", ".join(SIDE_LABELS[s] for s in plan.sides)
    return (
        f"🟠 <b>Передача каналу зависла</b> — угода #{plan.deal_id}\n\n"
        f"Без активності по чек-листу: ~{plan.idle_hours} год (≥48 год).\n"
        f"Чекаємо на: {sides}.\n\n"
        f"<a href='{frontend_url.rstrip('/')}/deal/{plan.deal_id}'>Перейти до угоди →</a>"
    )
