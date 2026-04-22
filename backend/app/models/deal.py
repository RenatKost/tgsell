import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DealStatus(str, enum.Enum):
    created = "created"
    payment_pending = "payment_pending"
    paid = "paid"
    channel_transferring = "channel_transferring"
    awaiting_payout = "awaiting_payout"
    completed = "completed"
    disputed = "disputed"
    cancelled = "cancelled"


class TransactionType(str, enum.Enum):
    deposit = "deposit"
    release = "release"
    refund = "refund"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
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

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    bundle_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channel_bundles.id"), nullable=True
    )

    # Relationships
    channel = relationship("Channel", back_populates="deals")
    bundle = relationship("ChannelBundle", back_populates="deals", foreign_keys=[bundle_id])
    buyer = relationship("User", back_populates="deals_as_buyer", foreign_keys=[buyer_id])
    seller = relationship("User", back_populates="deals_as_seller", foreign_keys=[seller_id])
    transactions = relationship("Transaction", back_populates="deal", cascade="all, delete-orphan")
    messages = relationship("DealMessage", back_populates="deal", cascade="all, delete-orphan", order_by="DealMessage.created_at")


class Transaction(Base):
    __tablename__ = "transactions"

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

    deal = relationship("Deal", back_populates="transactions")


class DealMessage(Base):
    __tablename__ = "deal_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    deal = relationship("Deal", back_populates="messages")
    sender = relationship("User")
