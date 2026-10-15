import enum
from datetime import datetime

from sqlalchemy import (
    JSON, Index,
    BigInteger, Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DealStatus(str, enum.Enum):
    created = "created"
    payment_pending = "payment_pending"
    paid = "paid"
    channel_transferring = "channel_transferring"
    awaiting_payout = "awaiting_payout"
    payout_in_progress = "payout_in_progress"
    completed = "completed"
    disputed = "disputed"
    cancelled = "cancelled"


class TransactionType(str, enum.Enum):
    deposit = "deposit"
    release = "release"
    refund = "refund"
    fee_collection = "fee_collection"  # admin-manual service fee → master (migration 0026)
    sweep = "sweep"  # admin-manual sweep of stray funds from a cancelled deal (0026)
    overpay_refund = "overpay_refund"  # buyer overpayment → buyer-entered address (0032)
    fee_sweep = "fee_sweep"  # whole remaining escrow USDT → TREASURY_ADDRESS (0037, Task 19)


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    status: Mapped[DealStatus] = mapped_column(
        Enum(DealStatus), default=DealStatus.created
    )
    escrow_wallet_address: Mapped[str] = mapped_column(String(100))
    escrow_private_key_encrypted: Mapped[str] = mapped_column(Text)
    amount_usdt: Mapped[float] = mapped_column(Float)
    service_fee: Mapped[float] = mapped_column(Float, default=0.0)

    deal_group_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    dispute_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    buyer_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    seller_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    buyer_confirmed_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    seller_confirmed_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    seller_payout_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payout_tx_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Admin: a blocked buyer/seller may still act on THIS deal (migration 0027).
    blocked_party_allowed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Partial / over-payment (migration 0032). All NULL on legacy deals ⇒ no refund ever fires.
    received_usdt: Mapped[float | None] = mapped_column(Float, nullable=True)
    partial_notified_units: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    overpay_units: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    overpay_refund_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # awaiting_address | queued | done | failed
    overpay_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Fee sweep to treasury (migration 0037): due | queued | pending_sweep | done | empty | failed
    sweep_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Payment timeout (migration 0025). NULL on legacy deals: a legacy 'created' deal is
    # never auto-cancelled; legacy 'payment_pending' falls back to created_at + timeout.
    # Auto-cancel happens only after a SUCCESSFUL zero-balance check (payment_checker).
    payment_deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    bundle_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channel_bundles.id"), nullable=True
    )

    # Transfer checklist + reminder dedup (migration 0022).
    # Dedup fields are reset on every checklist activity (tick/confirm), so each
    # idle period gets at most one 6h reminder, one 24h reminder, one 48h admin alert.
    checklist_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checklist_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_6h_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_24h_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    admin_alert_48h_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    channel = relationship("Channel", back_populates="deals")
    bundle = relationship("ChannelBundle", back_populates="deals", foreign_keys=[bundle_id])
    buyer = relationship("User", back_populates="deals_as_buyer", foreign_keys=[buyer_id])
    seller = relationship("User", back_populates="deals_as_seller", foreign_keys=[seller_id])
    transactions = relationship("Transaction", back_populates="deal", cascade="all, delete-orphan")
    messages = relationship("DealMessage", back_populates="deal", cascade="all, delete-orphan", order_by="DealMessage.created_at")
    checklist_items = relationship(
        "DealChecklistItem", back_populates="deal", cascade="all, delete-orphan",
        order_by="DealChecklistItem.id",
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_type_status_created", "type", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"))
    tx_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    from_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus), default=TransactionStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Outgoing-transfer bookkeeping (migration 0026, all nullable; legacy rows keep NULL).
    # A row is inserted as `pending` BEFORE broadcast; tx_hash (known pre-broadcast) is
    # written before broadcasting. status=confirmed only when receipt_status == SUCCESS.
    amount_units: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    restore_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    receipt_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    receipt_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee_limit_sun: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    broadcast_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Gas top-up already sent for this job (reused on retry, never topped up twice) + retry count.
    gas_tx_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gas_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Energy source of the payout (migration 0036): 'catfee' (rented) | 'burn' (TRX burned).
    # energy_order_id = CatFee order (persisted → never ordered twice for one job).
    energy_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    energy_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    energy_rent_sun: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Actual on-chain cost from the receipt (gettransactioninfobyid).
    fee_sun: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    energy_fee_sun: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    energy_used: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    deal = relationship("Deal", back_populates="transactions")


class DealMessage(Base):
    __tablename__ = "deal_messages"
    __table_args__ = (
        Index("ix_deal_messages_deal_id_id", "deal_id", "id"),
        Index("uq_deal_messages_client_id", "deal_id", "client_id", unique=True,
              postgresql_where=sa_text("client_id IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    # NULL for system messages created after migration 0029 (legacy rows keep a party id).
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Chat v2 (migration 0029, all nullable; legacy rows: kind NULL → derived from is_system)
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)  # text | system | file
    event: Mapped[str | None] = mapped_column(String(32), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Telegram bridge (0030): NULL = not forwarded (legacy/system), "pending" → worker forwards, "done"
    tg_forward_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    deal = relationship("Deal", back_populates="messages")
    sender = relationship("User")


class DealChecklistItem(Base):
    """One transfer-checklist item for a deal side (seller|buyer).

    side is a plain VARCHAR + CHECK (not a PG enum) to keep migrations simple.
    Keys/labels are defined in app.services.deal_checklist.CHECKLIST_ITEMS.
    """
    __tablename__ = "deal_checklist_items"
    __table_args__ = (
        UniqueConstraint("deal_id", "key", name="uq_deal_checklist_deal_key"),
        CheckConstraint("side IN ('seller', 'buyer')", name="ck_deal_checklist_side"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    side: Mapped[str] = mapped_column(String(10))
    key: Mapped[str] = mapped_column(String(64))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auto_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    auto_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    deal = relationship("Deal", back_populates="checklist_items")
