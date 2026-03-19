import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DealStatus(str, enum.Enum):
    created = "created"
    payment_pending = "payment_pending"
    paid = "paid"
    channel_transferring = "channel_transferring"
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
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
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

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    channel = relationship("Channel", back_populates="deals")
    buyer = relationship("User", back_populates="deals_as_buyer", foreign_keys=[buyer_id])
    seller = relationship("User", back_populates="deals_as_seller", foreign_keys=[seller_id])
    transactions = relationship("Transaction", back_populates="deal", cascade="all, delete-orphan")


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
