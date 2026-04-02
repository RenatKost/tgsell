import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ChannelStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    sold = "sold"


class ListingType(str, enum.Enum):
    sale = "sale"
    auction = "auction"


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    telegram_link: Mapped[str] = mapped_column(String(255))
    channel_name: Mapped[str] = mapped_column(String(255))
    seller_telegram: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(100))
    subscribers_count: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Float)
    monthly_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resources: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Computed/fetched stats
    avg_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    er: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_growth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age: Mapped[str | None] = mapped_column(String(100), nullable=True)
    adv_reach_12h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adv_reach_24h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adv_reach_48h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_posts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    post_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_post_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    avg_forwards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_reactions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Listing type & auction params
    listing_type: Mapped[str] = mapped_column(
        String(20), default="sale"
    )
    auction_start_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    auction_bid_step: Mapped[float | None] = mapped_column(Float, nullable=True)
    auction_duration_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus), default=ChannelStatus.pending
    )
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    seller = relationship("User", back_populates="channels", foreign_keys=[seller_id])
    stats = relationship("ChannelStats", back_populates="channel", cascade="all, delete-orphan")
    posts = relationship("ChannelPost", back_populates="channel", cascade="all, delete-orphan")
    deals = relationship("Deal", back_populates="channel")
    auction = relationship("Auction", back_populates="channel", uselist=False)


class ChannelStats(Base):
    __tablename__ = "channel_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    date: Mapped[datetime] = mapped_column(DateTime)
    subscribers: Mapped[int] = mapped_column(Integer, default=0)
    avg_views: Mapped[int] = mapped_column(Integer, default=0)
    avg_reach: Mapped[int] = mapped_column(Integer, default=0)
    er: Mapped[float] = mapped_column(Float, default=0.0)
    post_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    avg_forwards: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    avg_reactions: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    channel = relationship("Channel", back_populates="stats")


class ChannelPost(Base):
    __tablename__ = "channel_posts"
    __table_args__ = (
        UniqueConstraint("channel_id", "telegram_msg_id", name="uq_channel_post"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    telegram_msg_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[datetime] = mapped_column(DateTime)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)

    views: Mapped[int] = mapped_column(Integer, default=0)
    views_1h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    views_12h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    views_24h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    views_48h: Mapped[int | None] = mapped_column(Integer, nullable=True)

    forwards: Mapped[int] = mapped_column(Integer, default=0)
    reactions: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    is_deleted: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    channel = relationship("Channel", back_populates="posts")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "channel_id", name="uq_favorite_user_channel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
