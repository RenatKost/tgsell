"""Deal chat v2 — single source of truth for deal conversations (website).

* Access: buyer, seller, staff (admin/moderator = guarantor). Everyone else → 403.
  Blocked users can read; they may post only when the admin allowed that deal (PR #18).
* Realtime = short polling with an ``after_id`` cursor. All ephemeral state (typing,
  last seen, delivered/read) lives in Postgres so overlapping instances during a
  deploy agree; nothing is kept in process memory.
* System messages: ``system(db, deal, event, text, **meta)`` — added to the caller's
  transaction (rollback ⇒ no message). sender_id NULL, kind="system".
* Files: Postgres bytea with strict caps; type detected from magic bytes (never from the
  client), images re-encoded by Pillow (EXIF stripped), no HTML/SVG/executables.
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.chat import DealAttachment, DealChatPresence, DealChatRead
from app.models.deal import Deal, DealMessage, DealStatus
from app.models.user import User
from app.utils.timeutil import utcnow_naive

STAFF_ROLES = ("admin", "moderator")
TERMINAL = (DealStatus.completed, DealStatus.cancelled)
MAX_TEXT = 2000
PAGE = 100
TYPING_TTL = timedelta(seconds=5)
TYPING_MIN_INTERVAL = timedelta(seconds=2)
ONLINE_WINDOW = timedelta(seconds=60)

# ── file caps (Postgres volume 5 GB, ~0.285 GB used on 2026-10-12 → free ≈4.7 GB;
#    global cap 900 MB ≈ 19% of free; uploads also refused if DB grows past 3.5 GB) ──
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_DEAL_BYTES = 50 * 1024 * 1024
MAX_GLOBAL_BYTES = 900 * 1024 * 1024
DB_SIZE_GUARD_BYTES = int(3.5 * 1024 ** 3)
MAX_FILES_PER_HOUR = 10
MAX_IMAGE_PIXELS = 40_000_000
THUMB_PX = 320

IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
EXT_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".gif": "image/gif", ".pdf": "application/pdf", ".zip": "application/zip",
    ".txt": "text/plain", ".csv": "text/csv",
}
EXECUTABLE_MAGIC = (b"MZ", b"\x7fELF", b"#!", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                    b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"dex\n")


# ── access ──────────────────────────────────────────────────────────────

def is_staff(user: User) -> bool:
    role = getattr(user.role, "value", user.role)
    return role in STAFF_ROLES


def can_view(user: User, deal: Deal) -> bool:
    return user.id in (deal.buyer_id, deal.seller_id) or is_staff(user)


async def load_deal_for(db, deal_id: int, user: User) -> Deal:
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if not can_view(user, deal):
        raise HTTPException(status_code=403, detail="Access denied")
    return deal


def ensure_can_post(user: User, deal: Deal) -> None:
    from app.services.moderation import ensure_deal_action_allowed

    ensure_deal_action_allowed(user, deal)


def polling_enabled(deal: Deal) -> bool:
    return deal.status not in TERMINAL


# ── system messages ─────────────────────────────────────────────────────

def system(db, deal_or_id, event: str, text: str, **meta) -> DealMessage:
    deal_id = getattr(deal_or_id, "id", deal_or_id)
    msg = DealMessage(deal_id=deal_id, sender_id=None, text=text, is_system=True, kind="system",
                      event=event[:32], meta=meta or None)
    db.add(msg)
    return msg


# ── serialization ───────────────────────────────────────────────────────

def message_kind(m: DealMessage) -> str:
    return m.kind or ("system" if m.is_system else "text")


def role_of(deal: Deal, user: User | None, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    if user_id == deal.buyer_id:
        return "buyer"
    if user_id == deal.seller_id:
        return "seller"
    if user is not None and is_staff(user):
        return "guarantor"
    return None


def serialize(m: DealMessage, deal: Deal, senders: dict, attachments: dict) -> dict:
    kind = message_kind(m)
    system_ = kind == "system"
    sender = senders.get(m.sender_id) if not system_ else None
    att = attachments.get(m.id)
    return {
        "id": m.id, "deal_id": m.deal_id, "kind": kind, "event": m.event, "meta": m.meta,
        "text": m.text, "is_system": system_,
        "sender_id": None if system_ else m.sender_id,
        "sender_name": sender.first_name if sender else None,
        "sender_role": None if system_ else role_of(deal, sender, m.sender_id),
        "client_id": m.client_id, "created_at": m.created_at.isoformat() + "Z" if m.created_at else None,
        "attachment": None if att is None else {
            "id": att.id, "filename": att.filename, "mime": att.mime, "size": att.size,
            "width": att.width, "height": att.height, "is_image": att.mime in IMAGE_MIMES,
            "has_thumb": att.thumb is not None,
        },
    }


async def serialize_many(db, deal: Deal, msgs: list[DealMessage]) -> list[dict]:
    ids = {m.sender_id for m in msgs if m.sender_id}
    senders = {}
    if ids:
        senders = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()}
    atts = {}
    file_ids = [m.id for m in msgs if m.kind == "file"]
    if file_ids:
        rows = (await db.execute(
            select(DealAttachment.id, DealAttachment.message_id, DealAttachment.filename, DealAttachment.mime,
                   DealAttachment.size, DealAttachment.width, DealAttachment.height,
                   (DealAttachment.thumb.isnot(None)).label("has_thumb"))
            .where(DealAttachment.message_id.in_(file_ids), DealAttachment.deleted_at.is_(None))
        )).all()
        for r in rows:
            atts[r.message_id] = _AttView(r)
    return [serialize(m, deal, senders, atts) for m in msgs]


class _AttView:
    def __init__(self, r):
        self.id, self.filename, self.mime, self.size = r.id, r.filename, r.mime, r.size
        self.width, self.height = r.width, r.height
        self.thumb = b"" if r.has_thumb else None


# ── reads / presence (Postgres upserts) ────────────────────────────────

async def _upsert(db, model, keys: dict, values: dict, *, greatest: tuple = ()):
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(model).values(**keys, **values)
    set_ = {}
    for k, v in values.items():
        col = getattr(model, k)
        set_[k] = func.greatest(col, stmt.excluded[k]) if k in greatest else stmt.excluded[k]
    await db.execute(stmt.on_conflict_do_update(index_elements=list(keys), set_=set_))


async def mark_delivered(db, deal_id: int, user_id: int, message_id: int) -> None:
    if message_id <= 0:
        return
    await _upsert(db, DealChatRead, {"deal_id": deal_id, "user_id": user_id},
                  {"last_delivered_message_id": message_id, "updated_at": utcnow_naive()},
                  greatest=("last_delivered_message_id",))


async def mark_read(db, deal_id: int, user_id: int, message_id: int) -> int:
    latest = (await db.execute(select(func.max(DealMessage.id)).where(DealMessage.deal_id == deal_id))).scalar() or 0
    message_id = min(int(message_id), latest)
    if message_id > 0:
        await _upsert(db, DealChatRead, {"deal_id": deal_id, "user_id": user_id},
                      {"last_read_message_id": message_id, "last_delivered_message_id": message_id,
                       "updated_at": utcnow_naive()},
                      greatest=("last_read_message_id", "last_delivered_message_id"))
    return message_id


async def touch_presence(db, deal_id: int, user_id: int, now=None) -> None:
    now = now or utcnow_naive()
    await _upsert(db, DealChatPresence, {"deal_id": deal_id, "user_id": user_id}, {"last_seen_at": now})


async def set_typing(db, deal_id: int, user_id: int, now=None) -> bool:
    """Returns False when rate-limited (called again within 2s)."""
    now = now or utcnow_naive()
    row = await db.get(DealChatPresence, (deal_id, user_id))
    if row is not None and row.typing_until and row.typing_until - TYPING_TTL + TYPING_MIN_INTERVAL > now:
        return False
    await _upsert(db, DealChatPresence, {"deal_id": deal_id, "user_id": user_id},
                  {"typing_until": now + TYPING_TTL, "last_seen_at": now})
    return True


async def unread_count(db, deal_id: int, user_id: int) -> int:
    r = await db.get(DealChatRead, (deal_id, user_id))
    last = r.last_read_message_id if r else 0
    return (await db.execute(select(func.count(DealMessage.id)).where(
        DealMessage.deal_id == deal_id, DealMessage.id > last,
        (DealMessage.sender_id.is_(None)) | (DealMessage.sender_id != user_id),
    ))).scalar() or 0


async def unread_counts(db, user_id: int, deal_ids: list[int]) -> dict[int, int]:
    if not deal_ids:
        return {}
    reads = {r.deal_id: r.last_read_message_id for r in (await db.execute(
        select(DealChatRead).where(DealChatRead.user_id == user_id, DealChatRead.deal_id.in_(deal_ids)))).scalars()}
    out = {}
    rows = (await db.execute(
        select(DealMessage.deal_id, DealMessage.id, DealMessage.sender_id).where(
            DealMessage.deal_id.in_(deal_ids),
            (DealMessage.sender_id.is_(None)) | (DealMessage.sender_id != user_id))
    )).all()
    for d_id, m_id, _ in rows:
        if m_id > reads.get(d_id, 0):
            out[d_id] = out.get(d_id, 0) + 1
    return {d: out.get(d, 0) for d in deal_ids}


async def peer_state(db, deal: Deal, viewer: User, now=None) -> dict:
    """Read/delivered marks of the PARTIES (staff reads never produce ticks) + presence."""
    now = now or utcnow_naive()
    parties = [deal.buyer_id, deal.seller_id]
    reads = {r.user_id: r for r in (await db.execute(
        select(DealChatRead).where(DealChatRead.deal_id == deal.id, DealChatRead.user_id.in_(parties)))).scalars()}
    others = [u for u in parties if u != viewer.id]
    read_id = max((reads[u].last_read_message_id for u in others if u in reads), default=0)
    delivered_id = max((reads[u].last_delivered_message_id for u in others if u in reads), default=0)
    pres_rows = (await db.execute(select(DealChatPresence, User).join(User, User.id == DealChatPresence.user_id)
                                  .where(DealChatPresence.deal_id == deal.id,
                                         DealChatPresence.user_id != viewer.id))).all()
    presence = []
    for p, u in pres_rows:
        presence.append({
            "user_id": u.id, "name": u.first_name, "role": role_of(deal, u, u.id),
            "typing": bool(p.typing_until and p.typing_until > now),
            "online": bool(p.last_seen_at and now - p.last_seen_at <= ONLINE_WINDOW),
            "last_seen_at": p.last_seen_at.isoformat() + "Z" if p.last_seen_at else None,
        })
    return {"peer_read_id": read_id, "peer_delivered_id": max(read_id, delivered_id), "presence": presence}


async def deal_header(db, deal: Deal) -> dict:
    from app.services.deal_checklist import load_items

    items = await load_items(db, deal.id)
    prog = {}
    for side in ("seller", "buyer"):
        req = [i for i in items if i.side == side and i.required]
        prog[side] = {"done": sum(1 for i in req if i.done), "total": len(req)}
    return {"id": deal.id, "status": deal.status.value, "amount_usdt": deal.amount_usdt,
            "checklist": prog, "polling": polling_enabled(deal)}


# ── files ───────────────────────────────────────────────────────────────

def safe_filename(name: str | None) -> str:
    name = unicodedata.normalize("NFKC", (name or "file").replace("\\", "/").split("/")[-1])
    name = re.sub(r"[\x00-\x1f\x7f\"<>:|?*;]", "", name).strip(" .") or "file"
    if len(name) > 100:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 100 - len(ext) - 1] + "." + ext) if dot and len(ext) <= 8 else name[:100]
    return name


def sniff(data: bytes) -> str | None:
    """Detect MIME from content. None = not allowed."""
    head = data[:16]
    if any(head.startswith(m) for m in EXECUTABLE_MAGIC):
        return None
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return "application/zip"
    if b"\x00" in data[:8192]:
        return None
    try:
        sample = data.decode("utf-8")[:4096]
    except UnicodeDecodeError:
        return None
    low = sample.lstrip().lower()
    if low.startswith(("<", "{\\rtf")) or "<svg" in low[:2048] or "<html" in low[:2048] or "<script" in low[:2048]:
        return None  # markup is never accepted (no HTML/SVG/XML)
    return "text/plain"


def validate_type(filename: str, data: bytes) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    claimed = EXT_MIME.get(ext)
    if claimed is None:
        raise HTTPException(status_code=415, detail="Тип файлу не дозволено. Дозволено: JPG, PNG, WEBP, GIF, PDF, TXT, CSV, ZIP")
    detected = sniff(data)
    if detected is None:
        raise HTTPException(status_code=415, detail="Вміст файлу не дозволено (виконувані файли, HTML/SVG заборонені)")
    if claimed in ("text/plain", "text/csv"):
        if detected != "text/plain":
            raise HTTPException(status_code=415, detail="Розширення файлу не відповідає вмісту")
        return claimed
    if detected != claimed:
        raise HTTPException(status_code=415, detail="Розширення файлу не відповідає вмісту")
    return detected


def process_image(data: bytes, mime: str) -> tuple[bytes, int, int, bytes | None]:
    """Re-encode (strips EXIF/metadata, kills polyglots); returns (data, w, h, thumb_jpeg)."""
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            w, h = probe.size
            if w * h > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="Зображення завелике (макс. 40 Мп)")
            probe.verify()
        img = Image.open(io.BytesIO(data))
        fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP", "image/gif": "GIF"}[mime]
        if img.format != fmt:
            raise HTTPException(status_code=415, detail="Розширення файлу не відповідає вмісту")
        out = io.BytesIO()
        if fmt == "GIF":
            frames = getattr(img, "n_frames", 1)
            img.save(out, format="GIF", save_all=frames > 1)
        else:
            img = ImageOps.exif_transpose(img)
            if fmt == "JPEG":
                img = img.convert("RGB")
                img.save(out, format="JPEG", quality=88, optimize=True)
            elif fmt == "PNG":
                img.save(out, format="PNG", optimize=True)
            else:
                img.save(out, format="WEBP", quality=88)
        t = img.copy()
        t.thumbnail((THUMB_PX, THUMB_PX))
        tb = io.BytesIO()
        t.convert("RGB").save(tb, format="JPEG", quality=80)
        return out.getvalue(), img.size[0], img.size[1], tb.getvalue()
    except HTTPException:
        raise
    except Image.DecompressionBombError:
        raise HTTPException(status_code=413, detail="Зображення завелике (макс. 40 Мп)")
    except Exception:
        raise HTTPException(status_code=415, detail="Пошкоджене або непідтримуване зображення")


async def check_quotas(db, deal_id: int, user_id: int, size: int, now=None) -> None:
    now = now or utcnow_naive()
    live = DealAttachment.deleted_at.is_(None)
    recent = (await db.execute(select(func.count(DealAttachment.id)).where(
        DealAttachment.deal_id == deal_id, DealAttachment.uploader_id == user_id,
        DealAttachment.created_at >= now - timedelta(hours=1)))).scalar() or 0
    if recent >= MAX_FILES_PER_HOUR:
        raise HTTPException(status_code=429, detail=f"Ліміт: {MAX_FILES_PER_HOUR} файлів на годину в угоді")
    deal_total = (await db.execute(select(func.coalesce(func.sum(DealAttachment.size), 0)).where(
        DealAttachment.deal_id == deal_id, live))).scalar() or 0
    if deal_total + size > MAX_DEAL_BYTES:
        raise HTTPException(status_code=413, detail="Ліміт файлів угоди (50 МБ) вичерпано")
    total = (await db.execute(select(func.coalesce(func.sum(DealAttachment.size), 0)).where(live))).scalar() or 0
    db_size = (await db.execute(select(func.pg_database_size(func.current_database())))).scalar() or 0
    if total + size > MAX_GLOBAL_BYTES or db_size > DB_SIZE_GUARD_BYTES:
        await _alert_storage(total, db_size)
        raise HTTPException(status_code=507, detail="Сховище файлів тимчасово заповнене. Адміністратора повідомлено.")


async def _alert_storage(total: int, db_size: int) -> None:
    try:
        from app.services.alerts import send_admin_alert

        await send_admin_alert(
            f"🗄 <b>Сховище файлів чату заповнене</b>\nФайли: {total / 2**20:.0f} МБ / {MAX_GLOBAL_BYTES / 2**20:.0f} МБ\n"
            f"БД: {db_size / 2**30:.2f} ГБ (поріг {DB_SIZE_GUARD_BYTES / 2**30:.1f} ГБ)",
            alert_key="chat_storage_full", throttle_minutes=360)
    except Exception:  # pragma: no cover
        pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
