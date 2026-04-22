import enum
from datetime import datetime

from sqlalchemy import (
    DateTime, Enum, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BundleStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    sold = "sold"


class ChannelBundle(Base):
    __tablename__ = "channel_bundles"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[float] = mapped_column(Float)
    monthly_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    resources: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[BundleStatus] = mapped_column(
        Enum(BundleStatus), default=BundleStatus.pending
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    seller = relationship("User", foreign_keys=[seller_id])
    moderator = relationship("User", foreign_keys=[moderator_id])
    bundle_channels = relationship(
        "BundleChannel",
        back_populates="bundle",
        cascade="all, delete-orphan",
        order_by="BundleChannel.display_order",
    )
    deals = relationship("Deal", back_populates="bundle")


class BundleChannel(Base):
    __tablename__ = "bundle_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_id: Mapped[int] = mapped_column(
        ForeignKey("channel_bundles.id", ondelete="CASCADE")
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE")
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("bundle_id", "channel_id", name="uq_bundle_channel"),
    )

    bundle = relationship("ChannelBundle", back_populates="bundle_channels")
    channel = relationship("Channel")
