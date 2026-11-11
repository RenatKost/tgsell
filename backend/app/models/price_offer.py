"""Buyer price offers on a catalog lot (migration 0066)."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class PriceOfferStatus:
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    closed = "closed"

    ALL = (pending, accepted, declined, expired, closed)
    ACTIVE = (pending,)  # «активна» = ще чекає рішення продавця


class PriceOffer(Base):
    __tablename__ = "price_offers"
    __table_args__ = (
        Index(
            "uq_price_offers_one_pending",
            "buyer_id", "channel_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_price_offers_deal_id",
            "deal_id",
            unique=True,
            postgresql_where=text("deal_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    buyer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    amount_usdt: Mapped[float] = mapped_column(Float, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=PriceOfferStatus.pending, server_default=PriceOfferStatus.pending, index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Set when the buyer confirms and POST /api/deals creates a deal at this amount.
    deal_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("deals.id"), nullable=True)
