"""«Гарант для зовнішніх угод» (/escrow): private seller-created escrow offer (migration 0050).

The offer is invisible everywhere public (no Channel row, not in catalog/search/sitemap).
The buyer opens it only via the secret token AND only when logged in with the invited
@username. Accepting it creates an ordinary Deal (channel_id=NULL, bundle_id=NULL,
external_channel_link set) that goes through the standard escrow flow unchanged.
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ExternalOfferStatus(str, enum.Enum):
    open = "open"
    accepted = "accepted"
    cancelled = "cancelled"


class ExternalEscrowOffer(Base):
    __tablename__ = "external_escrow_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    channel_link: Mapped[str] = mapped_column(String(255))
    price_usdt: Mapped[float] = mapped_column(Float)
    fee_percent: Mapped[float] = mapped_column(Float)
    service_fee: Mapped[float] = mapped_column(Float)
    # Stored lowercase, without '@'.
    buyer_username: Mapped[str] = mapped_column(String(64))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # ExternalOfferStatus value (plain string column — no PG enum type to migrate).
    status: Mapped[str] = mapped_column(String(20), default=ExternalOfferStatus.open.value)
    deal_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("deals.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    seller = relationship("User", foreign_keys=[seller_id])
